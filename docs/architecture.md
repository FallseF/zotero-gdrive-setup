# Architecture

## Zoteroの添付ファイル管理の基礎

Zoteroの `itemAttachments` テーブルには、各添付ファイルの `linkMode` というカラムがある：

| linkMode | 名称 | 意味 |
|---|---|---|
| 0 | imported_file | 手動で追加されたローカル保存ファイル |
| 1 | imported_url | Connector等経由で保存されたファイル |
| 2 | linked_file | リンク添付（ファイル本体は外部、Zoteroは参照のみ） |
| 3 | linked_url | Webリンク（ローカルファイルなし） |

`path` カラムの形式は linkMode によって異なる:

- `linkMode IN (0, 1)`: `storage:<filename>` → `<dataDir>/storage/<itemKey>/<filename>`
- `linkMode = 2` (相対パス): `attachments:<rel_path>` → `<baseAttachmentPath>/<rel_path>`
- `linkMode = 2` (絶対パス): `/Users/.../full/path.pdf`
- `linkMode = 3`: URL文字列

## モジュール構成

```
scripts/
├── _common.py       # 設定/環境バリデーション、DBロック、バックアップ、schema ID解決
├── filenames.py     # 純粋関数: sanitize, extract_year, first_creator_string, build_filename
├── migrate_to_drive.py   # storage → linked 移行（DB＋ファイル）
└── rename_attachments.py # 既存リンク添付のファイル名整形（DB＋ファイル）
```

純粋関数は `filenames.py` に隔離し、`tests/` で単体テスト可能にしている。

## `migrate_to_drive.py` の動作

1. config を読み、環境（パス存在、base_dir が data_dir の外）を検証
2. `BEGIN EXCLUSIVE` で DB ロックを取得（Zotero起動中ならここで失敗）
3. `sqlite3.Connection.backup()` で WAL対応バックアップを取得
4. 対象クエリ実行（`linkMode IN (0, 1) AND contentType = 'application/pdf'`、ゴミ箱除外）
5. 各行に対して:
   a. `safe_copy_and_unlink`: 一時ファイルへコピー → サイズ検証 → リネーム → 元削除
   b. DB更新: `linkMode = 2`、`path = 'attachments:<key>/<filename>'`
   c. DB更新失敗時は `safe_copy_and_unlink` を逆向きに走らせてロールバック
   d. ソースディレクトリが空（hidden ファイル除く）なら削除
6. 全件処理後に `conn.commit()`

storage_key単位でサブディレクトリを維持する理由:
- ファイル名衝突を完全回避
- Zotero標準storage構造との対称性
- ロールバック容易

DB path に POSIX区切り（`/`）を使う理由:
- Zotero内部は `/` 区切りで扱われる（Windowsでも `\` ではなく `/`）
- `posixpath.join` を明示的に使ってクロスプラットフォーム整合性確保

## `rename_attachments.py` の動作

1. config 読み、環境検証、DBロック、バックアップ
2. `resolve_schema_ids()` で `fieldID(title)`, `fieldID(date)`, `creatorTypeID(author)` を実行時取得
3. 対象クエリ実行（`linkMode = 2 AND contentType = 'application/pdf'`、ゴミ箱除外）
4. 計画フェーズ:
   - 各行で親メタデータ取得、`build_filename` で新ファイル名生成
   - title 欠落・衝突などをスキップ判定
   - `planned_destinations` set で計画内重複も検出
5. 実行フェーズ（`--execute` 時のみ）:
   - `safe_rename`: 同一FSなら `os.rename`、跨る場合は copy+verify+unlink
   - DB更新失敗時は逆方向リネームでロールバック

## 安全機構

| 機構 | 実装 | 防げる失敗 |
|---|---|---|
| dry-run default | `--execute` opt-in | 誤実行 |
| EXCLUSIVEロック | `BEGIN EXCLUSIVE` | Zoteroとの同時編集 |
| WAL対応バックアップ | `Connection.backup()` | 古いWALの紛失 |
| 衝突検出 | 計画フェーズ + 実行直前 + `seen_destinations` | ファイル上書き |
| copy+verify+unlink | `safe_copy_and_unlink` | クラウドFUSEのsilent truncation |
| ロールバック | DB更新失敗時に逆方向移動 | FS/DB のdesync |
| schema ID解決 | `resolve_schema_ids` | 環境差によるID不整合 |
| ベースディレクトリ検証 | `relative_to` チェック | data_dir 内誤指定 |
| Unicode NFC正規化 | `unicodedata.normalize("NFC")` | macOS/Windows間の不一致 |
| Windows予約名回避 | `is_windows_reserved` で `_` prefix | CON/AUX等のクラッシュ |
| 制御文字除去 | `[\x00-\x1f\x7f-\x9f]` | embedded null byte |

## 既知の限界

- **Standalone attachment（親なし）**: migrate は移動するが rename はメタデータ無いのでスキップ
- **arXiv IDの埋め込み年**: `extract_year` は最初の有効年を取るが、`"arXiv 2305.12345 (2024)"` のような曖昧文字列では誤抽出の可能性
- **NFD/NFC片付け**: 既存ファイル名がmacOS APFS上でNFDで保存されている場合、planning フェーズの conflict 検出が見逃す可能性（実害は薄いが完全に閉じてはいない）
- **大量のWAL diff**: バックアップは `sqlite3.Connection.backup()` を使うので問題ないが、source DBのWALが極端に大きい状態（数GB）だとバックアップに時間がかかる

## なぜZoteroのGUIではなく直接DB操作するか

ZotMoovとZotero標準機能でほぼ同じことができる。本スクリプトの存在意義は:

- **大量処理時のスピード**: 数千件のライブラリで右クリックメニュー操作するより速い
- **冪等性**: dry-runで結果確認 → 確信を持って実行できる
- **自動化**: シェルスクリプトに組み込み可能、定期実行も可能
- **ロールバック容易**: バックアップが自動取得される

ただし、GUI操作の方が安全であることに変わりはない。一般ユーザーにはGUI手順を推奨。
