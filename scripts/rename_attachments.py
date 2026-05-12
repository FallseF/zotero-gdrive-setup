#!/usr/bin/env python3
"""
Google Drive内のリンク添付PDFを「Author et al. - Year - Title.pdf」形式に一括リネーム。

使い方:
    python3 rename_attachments.py            # dry-run（プレビューのみ）
    python3 rename_attachments.py --execute  # 本実行

事前準備:
    1. migrate_to_drive.py 実行後に走らせること（リンク添付になってないと対象にならん）
    2. Zoteroを終了
"""
import argparse
import os
import re
import shutil
import sqlite3
import sys

from _common import (
    backup_database,
    check_zotero_not_running,
    load_config,
    validate_environment,
)

ILLEGAL_CHARS = str.maketrans({
    "/": "-", "\\": "-", ":": "-",
    "?": "", "*": "", '"': "",
    "<": "", ">": "", "|": "",
    "\n": " ", "\r": " ", "\t": " ",
})

PREVIEW_N = 15


def sanitize(s, max_len=None):
    if not s:
        return ""
    s = s.translate(ILLEGAL_CHARS)
    s = re.sub(r"\s+", " ", s).strip()
    if max_len and len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


def extract_year(date_str):
    if not date_str:
        return ""
    m = re.search(r"\b(1[89]\d{2}|20\d{2}|21\d{2})\b", date_str)
    return m.group(1) if m else ""


def first_creator_string(authors):
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    if len(authors) == 2:
        return f"{authors[0]} and {authors[1]}"
    return f"{authors[0]} et al."


def get_parent_metadata(cur, parent_id):
    if not parent_id:
        return ("", "", [])
    cur.execute(
        "SELECT idv.value FROM itemData id JOIN itemDataValues idv ON id.valueID = idv.valueID "
        "WHERE id.itemID = ? AND id.fieldID = 1",
        (parent_id,),
    )
    row = cur.fetchone()
    title = row["value"] if row else ""

    cur.execute(
        "SELECT idv.value FROM itemData id JOIN itemDataValues idv ON id.valueID = idv.valueID "
        "WHERE id.itemID = ? AND id.fieldID = 6",
        (parent_id,),
    )
    row = cur.fetchone()
    date = row["value"] if row else ""

    cur.execute(
        "SELECT c.lastName, c.firstName FROM itemCreators ic "
        "JOIN creators c ON ic.creatorID = c.creatorID "
        "WHERE ic.itemID = ? AND ic.creatorTypeID = 10 ORDER BY ic.orderIndex",
        (parent_id,),
    )
    authors = [r["lastName"] or r["firstName"] for r in cur.fetchall()]
    return (title, date, authors)


def build_filename(title, date, authors, max_title_len, sep):
    fc = sanitize(first_creator_string(authors))
    year = extract_year(date)
    t = sanitize(title, max_len=max_title_len)
    parts = [p for p in (fc, year, t) if p]
    base = sep.join(parts)
    return base.rstrip(". ")


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
        backup_database(cfg["zotero_data_dir"], label="pre_rename")

    base_dir = cfg["linked_attachments_base_dir"]
    db_path = os.path.join(cfg["zotero_data_dir"], "zotero.sqlite")
    max_title = cfg["rename_template"]["title_max_length"]
    sep = cfg["rename_template"]["separator"]

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

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

    plan = []
    stats = {
        "renamed": 0, "no_change": 0, "no_metadata": 0,
        "missing_file": 0, "conflict": 0, "errors": [],
    }

    for r in rows:
        rel = r["path"][len("attachments:"):]
        src_full = os.path.join(base_dir, rel)
        if not os.path.exists(src_full):
            stats["missing_file"] += 1
            continue

        title, date, authors = get_parent_metadata(cur, r["parentItemID"])
        if not title or not title.strip():
            stats["no_metadata"] += 1
            continue

        new_base = build_filename(title, date, authors, max_title, sep)
        if not new_base:
            stats["no_metadata"] += 1
            continue

        new_filename = f"{new_base}.pdf"
        key_dir = os.path.dirname(rel)
        new_rel = os.path.join(key_dir, new_filename) if key_dir else new_filename
        dst_full = os.path.join(base_dir, new_rel)

        if src_full == dst_full:
            stats["no_change"] += 1
            continue
        if os.path.exists(dst_full):
            stats["conflict"] += 1
            continue

        plan.append((r["itemID"], rel, new_rel))
        stats["renamed"] += 1

    print(f"=== プレビュー (最初の{min(PREVIEW_N, len(plan))}件) ===")
    for item_id, old, new in plan[:PREVIEW_N]:
        print(f"  itemID={item_id}")
        print(f"    BEFORE: {os.path.basename(old)}")
        print(f"    AFTER : {os.path.basename(new)}")
    print()

    if args.execute:
        for item_id, old_rel, new_rel in plan:
            try:
                shutil.move(
                    os.path.join(base_dir, old_rel),
                    os.path.join(base_dir, new_rel),
                )
                cur.execute(
                    "UPDATE itemAttachments SET path = ? WHERE itemID = ?",
                    (f"attachments:{new_rel}", item_id),
                )
            except Exception as e:
                stats["errors"].append((item_id, str(e)))
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


if __name__ == "__main__":
    main()
