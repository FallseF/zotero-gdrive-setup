"""共通ユーティリティ: 設定読込、環境検証、DBバックアップ、安全ロック."""
import io
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

# Windows cp932環境でも非ASCII文字（"へん"等）を安全に出力するためUTF-8強制
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, io.UnsupportedOperation):
        pass


def err_exit(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


@dataclass(frozen=True)
class SchemaIds:
    """Zotero DBのfieldID/creatorTypeIDは環境ごとに異なる可能性があるため実行時に解決."""
    title: int
    date: int
    author: int


def resolve_schema_ids(cur: sqlite3.Cursor) -> SchemaIds:
    def lookup(table: str, name_col: str, name: str, id_col: str) -> int:
        cur.execute(f"SELECT {id_col} FROM {table} WHERE {name_col} = ?", (name,))
        row = cur.fetchone()
        if row is None:
            err_exit(f"❌ Zotero DBに {table}.{name_col}='{name}' が見つかりまへん")
        return row[0]

    return SchemaIds(
        title=lookup("fields", "fieldName", "title", "fieldID"),
        date=lookup("fields", "fieldName", "date", "fieldID"),
        author=lookup("creatorTypes", "creatorType", "author", "creatorTypeID"),
    )


def load_config(config_path: Optional[str] = None) -> Dict:
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(config_path):
        err_exit(
            f"設定ファイルが見つかりまへん: {config_path}\n"
            f"   config.example.json を config.json にコピーして編集してくれや。"
        )

    try:
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        err_exit(f"config.jsonが不正なJSONです: {e}")

    required = ["zotero_data_dir", "linked_attachments_base_dir", "rename_template"]
    missing = [k for k in required if k not in cfg]
    if missing:
        err_exit(f"config.jsonに必須キーがありません: {missing}")

    for k in ("title_max_length", "separator"):
        if k not in cfg["rename_template"]:
            err_exit(f"config.json の rename_template に {k} がありません")

    cfg["zotero_data_dir"] = os.path.expanduser(cfg["zotero_data_dir"])
    cfg["linked_attachments_base_dir"] = os.path.expanduser(cfg["linked_attachments_base_dir"])
    return cfg


def validate_environment(cfg: Dict) -> None:
    zotero_dir = Path(cfg["zotero_data_dir"]).resolve()
    if not zotero_dir.is_dir():
        err_exit(f"Zoteroデータディレクトリが存在しまへん: {zotero_dir}")
    if not (zotero_dir / "zotero.sqlite").is_file():
        err_exit(f"zotero.sqliteが見つかりまへん: {zotero_dir}/zotero.sqlite")

    base_dir = Path(cfg["linked_attachments_base_dir"]).resolve()
    if not base_dir.is_dir():
        err_exit(
            f"リンク添付ベースディレクトリが存在しまへん: {base_dir}\n"
            f"   Google Drive等が同期されてるか確認してから、ディレクトリを作ってくれや。"
        )

    # base_dir が Zotero data_dir の中だと、Zoteroの「Reset Storage」操作で消える危険
    try:
        base_dir.relative_to(zotero_dir)
        err_exit(
            f"base_dir ({base_dir}) が Zotero data dir ({zotero_dir}) の中にあります。\n"
            f"   別の場所（Google Drive等のクラウドフォルダ）に変更してくれや。"
        )
    except ValueError:
        pass  # 正常: base_dir は data_dir の外


def verify_zotero_base_attachment_path(cur: sqlite3.Cursor, configured: str) -> None:
    """Zotero側に保存された baseAttachmentPath とconfigが一致するか確認.

    Zotero 7+ では baseAttachmentPath は prefs.js に保存される場合が多く、
    DB側に無いケースは正常。値が見つかってかつ違うときだけ警告する。
    """
    try:
        cur.execute(
            "SELECT value FROM settings WHERE setting = 'baseAttachmentPath' OR key = 'baseAttachmentPath'"
        )
        row = cur.fetchone()
    except sqlite3.OperationalError:
        return
    if row is None:
        return  # prefs.js側に保存されているケース。確認できない
    stored = os.path.expanduser(str(row[0]))
    if os.path.realpath(stored) != os.path.realpath(configured):
        print(
            f"⚠️  Zotero側のbaseAttachmentPathと設定がズレてます:\n"
            f"   Zotero: {stored}\n"
            f"   config: {configured}\n"
            f"   そろえないと、リネーム後にZotero側でファイルが見つからない可能性があります。",
            file=sys.stderr,
        )


def open_db_with_exclusive_lock(db_path: str) -> sqlite3.Connection:
    """DBを開いてEXCLUSIVEロックを取得。Zoteroが起動中だと失敗する."""
    conn = sqlite3.connect(db_path, timeout=2.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN EXCLUSIVE")
    except sqlite3.OperationalError as e:
        conn.close()
        err_exit(
            f"DBロック取得失敗: {e}\n"
            "   Zoteroが起動中の可能性があります。終了してから再実行してくれや。\n"
            "   コマンド: osascript -e 'tell application \"Zotero\" to quit'"
        )
    return conn


def backup_database(zotero_dir: str, label: str = "backup") -> str:
    """SQLite Online Backup APIを使ってDBスナップショット取得（WAL対応）."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(zotero_dir).parent / f"Zotero_backup_{timestamp}_{label}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    src_path = Path(zotero_dir) / "zotero.sqlite"
    dst_path = backup_dir / "zotero.sqlite"

    src = sqlite3.connect(str(src_path), timeout=5.0)
    dst = sqlite3.connect(str(dst_path))
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()

    size_mb = dst_path.stat().st_size / (1024 * 1024)
    print(f"📦 DBバックアップ: {dst_path} ({size_mb:.1f} MB)")
    return str(dst_path)
