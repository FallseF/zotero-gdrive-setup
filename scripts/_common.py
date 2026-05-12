"""共通ユーティリティ: 設定読込、Zotero状態確認、バックアップ."""
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def load_config(config_path: Optional[str] = None) -> dict:
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(config_path):
        sys.exit(
            f"❌ 設定ファイルが見つかりまへん: {config_path}\n"
            f"   config.example.json を config.json にコピーして編集してくれや。"
        )
    with open(config_path) as f:
        cfg = json.load(f)
    cfg["zotero_data_dir"] = os.path.expanduser(cfg["zotero_data_dir"])
    cfg["linked_attachments_base_dir"] = os.path.expanduser(cfg["linked_attachments_base_dir"])
    return cfg


def validate_environment(cfg: dict) -> None:
    if platform.system() != "Darwin":
        print(
            f"⚠️  このスクリプトはmacOSで検証済み。{platform.system()}での動作は未保証です。"
        )

    zotero_dir = Path(cfg["zotero_data_dir"])
    if not zotero_dir.is_dir():
        sys.exit(f"❌ Zoteroデータディレクトリが存在しまへん: {zotero_dir}")
    if not (zotero_dir / "zotero.sqlite").is_file():
        sys.exit(f"❌ zotero.sqliteが見つかりまへん: {zotero_dir}/zotero.sqlite")

    base_dir = Path(cfg["linked_attachments_base_dir"])
    if not base_dir.is_dir():
        sys.exit(
            f"❌ リンク添付ベースディレクトリが存在しまへん: {base_dir}\n"
            f"   Google Drive等が同期されてるか確認してから、ディレクトリを手で作ってくれや。"
        )


def check_zotero_not_running() -> None:
    try:
        out = subprocess.check_output(["pgrep", "-i", "zotero"], text=True).strip()
        if out:
            sys.exit(
                "❌ Zoteroが起動中ですわ。終了してから再実行してくれや。\n"
                "   コマンド: osascript -e 'tell application \"Zotero\" to quit'"
            )
    except subprocess.CalledProcessError:
        pass


def backup_database(zotero_dir: str, label: str = "backup") -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(zotero_dir).parent / f"Zotero_backup_{timestamp}_{label}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    src = Path(zotero_dir) / "zotero.sqlite"
    dst = backup_dir / "zotero.sqlite"
    shutil.copy2(src, dst)
    size_mb = dst.stat().st_size / (1024 * 1024)
    print(f"📦 DBバックアップ: {dst} ({size_mb:.1f} MB)")
    return str(dst)


def confirm_execute(dry_run: bool) -> bool:
    return not dry_run
