#!/usr/bin/env python3
"""
Zoteroのローカル保存PDFを Google Drive 等のクラウドフォルダへ移行し、
リンク添付に変換するスクリプト。

使い方:
    python3 migrate_to_drive.py            # dry-run
    python3 migrate_to_drive.py --execute  # 本実行

事前準備:
    1. scripts/config.json を作成（config.example.json をコピーして編集）
    2. Zotero側の Linked Attachments Base Directory を config と同じパスに設定
    3. Zoteroを終了
"""
import argparse
import os
import posixpath
import shutil
import sys

# 親ディレクトリ内のモジュールをインポート可能にする
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import (
    backup_database,
    load_config,
    open_db_with_exclusive_lock,
    validate_environment,
    verify_zotero_base_attachment_path,
)


def safe_copy_and_unlink(src: str, dst: str) -> None:
    """copy → サイズ確認 → unlink(src) の順で安全にファイル移動.

    クラウドFUSEでの silent truncation や、移動中の中断によるデータ消失を防ぐ。
    """
    src_size = os.path.getsize(src)
    tmp_dst = dst + ".part"

    shutil.copy2(src, tmp_dst)
    try:
        with open(tmp_dst, "rb") as f:
            os.fsync(f.fileno())
    except OSError:
        pass  # FUSE等でfsyncが効かない場合は無視

    dst_size = os.path.getsize(tmp_dst)
    if dst_size != src_size:
        os.unlink(tmp_dst)
        raise OSError(f"サイズ不一致: src={src_size} dst={dst_size}")

    os.rename(tmp_dst, dst)
    os.unlink(src)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="本実行（指定なしならdry-run）")
    parser.add_argument("--config", default=None,
                        help="設定ファイルパス（デフォルト: scripts/config.json）")
    args = parser.parse_args()

    cfg = load_config(args.config)
    validate_environment(cfg)

    storage_dir = os.path.join(cfg["zotero_data_dir"], "storage")
    db_path = os.path.join(cfg["zotero_data_dir"], "zotero.sqlite")
    base_dir = cfg["linked_attachments_base_dir"]

    if args.execute:
        backup_database(cfg["zotero_data_dir"], label="pre_migration")

    conn = open_db_with_exclusive_lock(db_path)
    cur = conn.cursor()
    verify_zotero_base_attachment_path(cur, base_dir)

    cur.execute("""
        SELECT ia.itemID, i.key as storageKey, ia.path
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
            mark = "✓" if os.path.exists(src) else "欠落"
            print(f"  [{mark}] itemID={r['itemID']} key={r['storageKey']}")
            print(f"        file={filename[:80]}")
        print()

    stats = {"moved": 0, "skipped_missing": 0, "already_at_dst": 0, "errors": []}
    seen_destinations = set()

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
        if os.path.exists(dst) or dst in seen_destinations:
            stats["already_at_dst"] += 1
            continue
        if not args.execute:
            seen_destinations.add(dst)
            stats["moved"] += 1
            continue

        try:
            os.makedirs(dst_dir, exist_ok=True)
            safe_copy_and_unlink(src, dst)
            seen_destinations.add(dst)
        except Exception as e:
            stats["errors"].append((item_id, filename, f"ファイル移動失敗: {e}"))
            continue

        # ファイル移動成功後にDB更新。失敗したら即座にファイルを戻す
        try:
            db_path_value = "attachments:" + posixpath.join(key, filename)
            cur.execute(
                "UPDATE itemAttachments SET linkMode = 2, path = ? WHERE itemID = ?",
                (db_path_value, item_id),
            )
            stats["moved"] += 1
        except Exception as e:
            try:
                safe_copy_and_unlink(dst, src)
            except Exception as rb_err:
                stats["errors"].append((item_id, filename,
                                       f"DB更新失敗かつロールバックも失敗: {e} / {rb_err}"))
            else:
                stats["errors"].append((item_id, filename, f"DB更新失敗（ロールバック済）: {e}"))
            continue

        # 空になった source key dir を片付け（hidden file が残ってる場合は触らない）
        src_parent = os.path.join(storage_dir, key)
        try:
            remaining = [n for n in os.listdir(src_parent) if not n.startswith(".")]
            if not remaining:
                shutil.rmtree(src_parent, ignore_errors=True)
        except OSError:
            pass

        if idx % 10 == 0 and args.execute:
            print(f"  進捗: {idx}/{len(rows)} ({stats['moved']}件移動済)")

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

    return 0 if not stats["errors"] else 2


if __name__ == "__main__":
    sys.exit(main())
