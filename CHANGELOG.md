# Changelog

このプロジェクトの主な変更を記録します。

## [Unreleased]

## [0.2.0] - 2026-05-12

### Added
- `scripts/filenames.py`: ファイル名生成ロジックを純粋関数として切り出し（テスタブル）
- `tests/test_filenames.py`: 36件のユニットテスト
- Windows予約名（CON, PRN, AUX 等）の検出と回避
- Unicode NFC正規化（macOS/Windows間のファイル名不一致を回避）
- 制御文字の除去
- SQLite Online Backup API による WAL対応のバックアップ
- `BEGIN EXCLUSIVE` によるDB ロック取得（pgrep ではなく実際のロック状態で判定）
- 安全な copy+verify+unlink ベースのファイル移動（クラウドFUSEの silent truncation 対策）
- DB更新失敗時の自動ロールバック（ファイルを元に戻す）
- `seen_destinations` トラッキングによる計画フェーズでの衝突検出
- 実行時の Zotero schema ID 解決（fieldID/creatorTypeID）
- `linked_attachments_base_dir` が Zotero data dir の外であることの検証
- config.json の必須キー検証

### Changed
- ファイル移動方式: `shutil.move` → `safe_copy_and_unlink` （データ消失リスク軽減）
- 年抽出のロジック: 1500-2199 の範囲、開始位置や区切り文字の文脈を考慮
- エラーメッセージから絵文字を一部除去（Windows cp932環境での `UnicodeEncodeError` 回避）
- UTF-8 出力強制（`sys.stdout.reconfigure`）
- README に Python 3.9+ 要件を明記

### Fixed
- `fieldID`/`creatorTypeID` のハードコーディング（環境によって異なる可能性に対処）
- `extract_year` が "(2022)" のような括弧内年を取れなかった
- `sanitize` が `\t\n` を制御文字として除去してしまい単語が連結されていた
- `first_creator_string` で None creator がそのまま文字列化される問題

## [0.1.0] - 2026-05-12

Initial release.

- `scripts/migrate_to_drive.py`: ローカル保存 → クラウドフォルダ移行
- `scripts/rename_attachments.py`: リンク添付ファイルの一括リネーム
- README に GUI 手順と CLI スクリプト手順の両方を記載
