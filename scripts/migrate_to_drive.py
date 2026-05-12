#!/usr/bin/env python3
"""
Zoteroのローカル保存PDFをGoogle Drive（または任意のクラウドフォルダ）へ
一括移行し、リンク添付に変換する。

使い方:
    python3 migrate_to_drive.py            # dry-run（プレビューのみ）
    python3 migrate_to_drive.py --execute  # 本実行

事前準備:
    1. scripts/config.json を作成（config.example.json をコピーして編集）
    2. Zoteroを終了
    3. Zotero側の Linked Attachments Base Directory も同じパスに設定済みであること

このスクリプトは zotero.sqlite を直接編集します。実行前に必ずバックアップを取ります。
"""
import argparse
import os
import shutil
import sqlite3
import sys

from _common import (
    backup_database,
    check_zotero_not_running,
    load_config,
    validate_environment,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="本実行（指定なしならdry-run）")
    parser.add_argument("--config", default=None,
                        help="設定ファイルパス（デフォルト: scripts/config.json）")
    args = parser.parse_args()

    cfg = load_config(args.config)
    validate_environment(cfg)

    if args.execute:
        check_zotero_not_running()
        backup_database(cfg["zotero_data_dir"], label="pre_migration")

    storage_dir = os.path.join(cfg["zotero_data_dir"], "storage")
    db_path = os.path.join(cfg["zotero_data_dir"], "zotero.sqlite")
    base_dir = cfg["linked_attachments_base_dir"]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT
            ia.itemID,
            i.key as storageKey,
            ia.path,
            ia.contentType
        FROM itemAttachments ia
        JOIN items i ON ia.itemID = i.itemID
        LEFT JOIN deletedItems di ON ia.itemID = di.itemID
        WHERE ia.linkMode IN (0, 1)
          AND ia.contentType = 'application/pdf'
          AND di.itemID IS NULL
          AND ia.path LIKE 'storage:%'
        ORDER BY ia.itemID
    """)
    rows = cur.fetchall()
    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"\n[{mode}] 対象: {len(rows)}件のローカルPDF\n")

    if rows:
        print("=== 最初の5件サンプル ===")
        for r in rows[:5]:
            filename = r["path"][len("storage:"):]
            src = os.path.join(storage_dir, r["storageKey"], filename)
            exists = "✓" if os.path.exists(src) else "✗欠落"
            print(f"  [{exists}] itemID={r['itemID']} key={r['storageKey']}")
            print(f"        file={filename[:80]}")
        print()

    stats = {"moved": 0, "skipped_missing": 0, "already_at_dst": 0, "errors": []}

    for idx, r in enumerate(rows, 1):
        item_id = r["itemID"]
        key = r["storageKey"]
        filename = r["path"][len("storage:"):]
        src = os.path.join(storage_dir, key, filename)
        dst_dir = os.path.join(base_dir, key)
        dst = os.path.join(dst_dir, filename)

        if not os.path.exists(src):
            stats["skipped_missing"] += 1
            continue
        if os.path.exists(dst):
            stats["already_at_dst"] += 1
            continue
        if not args.execute:
            stats["moved"] += 1
            continue

        try:
            os.makedirs(dst_dir, exist_ok=True)
            shutil.move(src, dst)
            cur.execute(
                "UPDATE itemAttachments SET linkMode = 2, path = ? WHERE itemID = ?",
                (f"attachments:{key}/{filename}", item_id),
            )
            stats["moved"] += 1

            src_parent = os.path.join(storage_dir, key)
            try:
                if not os.listdir(src_parent):
                    os.rmdir(src_parent)
            except OSError:
                pass

            if idx % 25 == 0:
                conn.commit()
                print(f"  進捗: {idx}/{len(rows)} ({stats['moved']}件移動済)")
        except Exception as e:
            stats["errors"].append((item_id, filename, str(e)))

    if args.execute:
        conn.commit()
    conn.close()

    print("\n=== 結果 ===")
    print(f"  移動成功: {stats['moved']}件")
    print(f"  既に移動先に存在: {stats['already_at_dst']}件")
    print(f"  ファイル欠落でスキップ: {stats['skipped_missing']}件")
    print(f"  エラー: {len(stats['errors'])}件")

    if stats["errors"]:
        print("\n=== エラー詳細 (最大10件) ===")
        for item_id, fname, err in stats["errors"][:10]:
            print(f"  itemID={item_id} {fname}: {err}")

    if not args.execute:
        print("\n💡 dry-runでした。問題なければ --execute で本実行してくれや。")


if __name__ == "__main__":
    main()
