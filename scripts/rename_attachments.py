#!/usr/bin/env python3
"""
Google Drive内のリンク添付PDFを「Author et al. - Year - Title.pdf」形式に一括リネーム。

使い方:
    python3 rename_attachments.py            # dry-run
    python3 rename_attachments.py --execute  # 本実行

事前準備:
    1. migrate_to_drive.py 実行後に走らせること
    2. Zoteroを終了
"""
import argparse
import os
import posixpath
import shutil
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import (
    backup_database,
    err_exit,
    load_config,
    open_db_with_exclusive_lock,
    resolve_schema_ids,
    validate_environment,
    verify_zotero_base_attachment_path,
    SchemaIds,
)
from filenames import build_filename

PREVIEW_N = 15


def get_parent_metadata(cur, parent_id: int, ids: SchemaIds) -> Tuple[str, str, List[str]]:
    if not parent_id:
        return ("", "", [])

    cur.execute(
        "SELECT idv.value FROM itemData id "
        "JOIN itemDataValues idv ON id.valueID = idv.valueID "
        "WHERE id.itemID = ? AND id.fieldID = ?",
        (parent_id, ids.title),
    )
    row = cur.fetchone()
    title = row["value"] if row else ""

    cur.execute(
        "SELECT idv.value FROM itemData id "
        "JOIN itemDataValues idv ON id.valueID = idv.valueID "
        "WHERE id.itemID = ? AND id.fieldID = ?",
        (parent_id, ids.date),
    )
    row = cur.fetchone()
    date = row["value"] if row else ""

    cur.execute(
        "SELECT c.lastName, c.firstName FROM itemCreators ic "
        "JOIN creators c ON ic.creatorID = c.creatorID "
        "WHERE ic.itemID = ? AND ic.creatorTypeID = ? "
        "ORDER BY ic.orderIndex",
        (parent_id, ids.author),
    )
    authors = []
    for r in cur.fetchall():
        name = (r["lastName"] or r["firstName"] or "").strip()
        if name:
            authors.append(name)

    return (title or "", date or "", authors)


def safe_rename(src: str, dst: str) -> None:
    """サイズ確認付きの安全なリネーム.

    同一ボリュームなら os.rename（POSIXは上書き、Windowsは衝突時エラー）。
    跨る場合は copy+verify+unlink。呼び出し側で dst の事前存在チェック必須。
    """
    if os.path.exists(dst):
        raise FileExistsError(f"宛先ファイル既存: {dst}")
    src_size = os.path.getsize(src)
    try:
        os.rename(src, dst)
        return
    except OSError:
        pass  # cross-filesystem 等

    tmp_dst = dst + ".part"
    shutil.copy2(src, tmp_dst)
    if os.path.getsize(tmp_dst) != src_size:
        os.unlink(tmp_dst)
        raise IOError("コピー後サイズ不一致")
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

    base_dir = cfg["linked_attachments_base_dir"]
    db_path = os.path.join(cfg["zotero_data_dir"], "zotero.sqlite")
    max_title = cfg["rename_template"]["title_max_length"]
    sep = cfg["rename_template"]["separator"]

    if args.execute:
        backup_database(cfg["zotero_data_dir"], label="pre_rename")

    conn = open_db_with_exclusive_lock(db_path)
    cur = conn.cursor()
    verify_zotero_base_attachment_path(cur, base_dir)
    ids = resolve_schema_ids(cur)

    cur.execute("""
        SELECT ia.itemID, ia.parentItemID, ia.path
        FROM itemAttachments ia
        LEFT JOIN deletedItems di ON ia.itemID = di.itemID
        WHERE ia.linkMode = 2
          AND ia.contentType = 'application/pdf'
          AND ia.path LIKE 'attachments:%'
          AND di.itemID IS NULL
        ORDER BY ia.itemID
    """)
    rows = cur.fetchall()
    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"\n[{mode}] 対象: {len(rows)}件のリンク添付PDF\n")

    plan: List[Tuple[int, str, str]] = []
    stats = {
        "renamed": 0, "no_change": 0, "no_metadata": 0,
        "missing_file": 0, "conflict": 0, "errors": [],
    }
    planned_destinations = set()

    for r in rows:
        rel = r["path"][len("attachments:"):]
        src_full = os.path.join(base_dir, rel)
        if not os.path.exists(src_full):
            stats["missing_file"] += 1
            continue

        title, date, authors = get_parent_metadata(cur, r["parentItemID"], ids)
        new_filename = build_filename(title, date, authors, max_title, sep)
        if not new_filename:
            stats["no_metadata"] += 1
            continue

        key_dir = posixpath.dirname(rel)
        new_rel = posixpath.join(key_dir, new_filename) if key_dir else new_filename
        dst_full = os.path.join(base_dir, new_rel)

        if os.path.normcase(os.path.normpath(src_full)) == os.path.normcase(os.path.normpath(dst_full)):
            stats["no_change"] += 1
            continue
        if os.path.exists(dst_full) or new_rel in planned_destinations:
            stats["conflict"] += 1
            continue

        plan.append((r["itemID"], rel, new_rel))
        planned_destinations.add(new_rel)
        stats["renamed"] += 1

    print(f"=== プレビュー (最初の{min(PREVIEW_N, len(plan))}件) ===")
    for item_id, old, new in plan[:PREVIEW_N]:
        print(f"  itemID={item_id}")
        print(f"    BEFORE: {os.path.basename(old)}")
        print(f"    AFTER : {os.path.basename(new)}")
    print()

    if args.execute:
        for item_id, old_rel, new_rel in plan:
            src = os.path.join(base_dir, old_rel)
            dst = os.path.join(base_dir, new_rel)
            try:
                safe_rename(src, dst)
            except Exception as e:
                stats["errors"].append((item_id, f"リネーム失敗: {e}"))
                continue
            try:
                cur.execute(
                    "UPDATE itemAttachments SET path = ? WHERE itemID = ?",
                    ("attachments:" + new_rel, item_id),
                )
            except Exception as e:
                try:
                    safe_rename(dst, src)
                except Exception as rb_err:
                    stats["errors"].append((item_id, f"DB更新失敗かつロールバックも失敗: {e} / {rb_err}"))
                else:
                    stats["errors"].append((item_id, f"DB更新失敗（ロールバック済）: {e}"))
        conn.commit()
    conn.close()

    print("=== 結果 ===")
    print(f"  リネーム対象: {stats['renamed']}件")
    print(f"  既に同名で変更不要: {stats['no_change']}件")
    print(f"  メタデータ不足でスキップ: {stats['no_metadata']}件")
    print(f"  ファイル欠落でスキップ: {stats['missing_file']}件")
    print(f"  ファイル名衝突でスキップ: {stats['conflict']}件")
    print(f"  エラー: {len(stats['errors'])}件")
    if stats["errors"]:
        for e in stats["errors"][:5]:
            print(f"    {e}")

    if not args.execute:
        print("\n💡 dry-runでした。問題なければ --execute で本実行してくれや。")

    return 0 if not stats["errors"] else 2


if __name__ == "__main__":
    sys.exit(main())
