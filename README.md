# zotero-gdrive-setup

ZoteroのPDF添付ファイルをGoogle Drive（または任意のクラウドストレージ）に保存し、Zoteroクラウドストレージの容量制限を回避するためのセットアップガイドとCLIツール。

[![CI](https://github.com/FallseF/zotero-gdrive-setup/actions/workflows/ci.yml/badge.svg)](https://github.com/FallseF/zotero-gdrive-setup/actions/workflows/ci.yml)

## 何ができる

- Zotero ConnectorでブラウザからクリックしたPDFが、自動的にGoogle Driveへ移動・リンク化される
- 既存のローカル保存PDFを一括でGoogle Driveへ移行
- ファイル名を「Author et al. - Year - Title.pdf」形式に統一
- Zoteroクラウド有料プラン不要、研究室メンバーでGoogle Drive容量を活用

## 仕組み

```
[ブラウザ]                    [Zotero]                        [Google Drive]
   │                            │                                  │
   │ 1. Connectorクリック       │                                  │
   │ ───────────────────────► │ 2. PDF取得＋メタデータ保存       │
   │                            │ 3. 自動リネーム（標準機能）       │
   │                            │ 4. ZotMoovが移動＋リンク化       │
   │                            │ ─────────────────────────────► │
   │                            │                                  │ 5. クラウド保存
   │                            │ 6. Zotero項目は「リンク添付」    │
```

DBはローカル、PDF本体はGoogle Drive。Zoteroは参照（リンク）だけ持つ構造。

## 動作環境

- **動作確認済**: macOS 14+ / Zotero 7+ / Python 3.9+
- **未検証だが理論上動く**: macOS の Python 3.9-3.12
- **CIで検証**: Linux (Ubuntu) と macOS で Python 3.9-3.12 のスクリプト構文・テスト
- **未対応**: Windows（`os.path.exists` の Unicode 正規化の差や Drive のマウントパスの違いで実環境動作未検証）

実環境動作はテスト範囲外なので、Windows/Linuxで使う場合は **少数アイテムでdry-runしてから本実行** を強く推奨します。

## 必要なもの

- Zotero 7+
- [ZotMoov](https://github.com/wileyyugioh/zotmoov) プラグイン
- Google Drive for desktop（あるいは同期マウントされたクラウドストレージ）
- Python 3.9+（スクリプト使う場合のみ、stdlib のみ依存）

---

## セットアップ手順（GUI推奨版）

ほとんどのユーザーはこの手順だけで完結します。スクリプト不要。

### 1. ZotMoovインストール

1. [ZotMoov Releases](https://github.com/wileyyugioh/zotmoov/releases) から最新の `.xpi` をダウンロード
2. Zotero起動 → メニュー `Tools → Plugins`
3. 右上の歯車アイコン ⚙️ → **Install Plugin From File...** → `.xpi` を選択
4. Zoteroを再起動

### 2. Google DriveにZotero用フォルダを作成

例: `マイドライブ/Zotero`

macOS: `/Users/<USERNAME>/Library/CloudStorage/GoogleDrive-<EMAIL>/マイドライブ/Zotero`

### 3. Zotero側の設定

**Settings → Advanced → Files and Folders**

- 「Linked Attachments」セクションの **Base directory** に 上記Google Driveパスを設定

**Settings → ZotMoov**

| 項目 | 値 |
|---|---|
| Directory to move files to | 同じGoogle Driveパス |
| Behavior | Move |
| Automatically move files added via Zotero Connector | ✓ |
| Rename file using title | ✓ |

### 4. ファイル命名規則の設定（Zotero標準）

**Settings → General → File Renaming** に以下を設定:

```
{{ firstCreator suffix=" - " }}{{ year suffix=" - " }}{{ title truncate="100" }}
```

「Rename linked files」もチェック。

### 5. 動作確認

ブラウザでPDFを開いてZotero Connectorをクリック。数秒後にGoogle Drive側にファイルが現れたらOK。

---

## 既存ファイルの一括処理（GUI版）

ZotMoovインストール後、既存のローカルPDFも一括移行できる：

1. Zoteroの「My Library」を選択
2. `Cmd+A` で全選択
3. 右クリック → **Manage Attachments → ZotMoov: Move Selected Items**
4. 完了後、リンク添付化されGoogle Driveに移動

ファイル名の一括リネーム:

1. 全選択した状態で
2. 右クリック → **Rename File from Parent Metadata**

---

## 上級者向け: スクリプトによる一括処理

GUI操作が面倒、あるいは数千件以上の大量処理をしたい場合のCLIスクリプト。

> ⚠️ **DBを直接編集します。** 自動でバックアップ取得、トランザクション境界明示、失敗時ロールバック等の安全機構は実装してますが、リスクをゼロにはできません。重要なライブラリは事前に手動バックアップを推奨。

### 準備

```bash
git clone https://github.com/FallseF/zotero-gdrive-setup.git
cd zotero-gdrive-setup
cp scripts/config.example.json scripts/config.json
# config.json を自分の環境に合わせて編集
```

`config.json` の例:

```json
{
  "zotero_data_dir": "~/Zotero",
  "linked_attachments_base_dir": "~/Library/CloudStorage/GoogleDrive-yourname@gmail.com/マイドライブ/Zotero",
  "rename_template": {
    "format": "{author} - {year} - {title}",
    "title_max_length": 100,
    "separator": " - "
  }
}
```

### 既存ファイルをGoogle Driveへ移行

Zoteroを終了してから:

```bash
cd scripts
python3 migrate_to_drive.py             # dry-run（プレビューのみ）
python3 migrate_to_drive.py --execute   # 本実行
```

挙動:
- `linkMode IN (0, 1)` かつ `contentType = 'application/pdf'` の添付を対象（ゴミ箱を除く）
- ローカルstorage → クラウドフォルダ（`<storage_key>/<filename>` の構造）
- DBの `linkMode` を 2 (linked_file) に、`path` を `attachments:...` に更新
- ファイル移動は **copy → サイズ検証 → unlink** の順で、中断耐性あり

### ファイル名を一括リネーム

```bash
python3 rename_attachments.py             # dry-run
python3 rename_attachments.py --execute   # 本実行
```

挙動:
- 全てのリンク添付PDF（`linkMode = 2`）を対象
- 親アイテムのメタデータから `Author et al. - Year - Title.pdf` を生成
- タイトル欠落のアイテムはスキップ（情報損失防止）

### 安全機構

| 機構 | 詳細 |
|---|---|
| dry-run default | `--execute` を明示しない限りファイル/DBに変更しない |
| EXCLUSIVEロック | `BEGIN EXCLUSIVE` で他プロセス（Zotero）と排他制御 |
| WAL対応バックアップ | `sqlite3.Connection.backup()` で実行前に自動取得 |
| 衝突検出 | ファイル名衝突を計画フェーズと実行直前の両方で検出 |
| ロールバック | ファイル移動成功・DB更新失敗 → 自動でファイルを元に戻す |
| schema ID解決 | `fieldID`/`creatorTypeID` を実行時に問い合わせ（環境差対応） |
| ベースディレクトリ検証 | Zoteroデータディレクトリの内側を指定不可（誤削除防止） |

---

## トラブルシュート

### Q. Zoteroで「ファイルが見つからない」と出る

以下を順に確認:

1. Google Driveが同期されているか（オフラインだとファイル取得不可）
2. Settings → Advanced → Files and Folders の Base directory が正しいか
3. 該当アイテムのパスが `attachments:<KEY>/<filename>` 形式になっているか
   - Zoteroで「Show File」→ 表示されるパスを確認

### Q. ZotMoovがインストールできない（"sideload" 警告）

Zotero 7のセキュリティ機能で、初回はGUIから手動承認が必要。Tools → Plugins から該当プラグインを「Enable」する。

### Q. 移行スクリプト実行後、Zoteroで一部アイテムが「missing file」になった

Zotero Sync未完了でローカルに実体がなかった分。Zotero側でSyncを完了させてから再実行可能。

### Q. ロールバックしたい

バックアップから戻す:

```bash
# Zotero終了後
osascript -e 'tell application "Zotero" to quit'

# DB復元
cp ~/Zotero_backup_<TIMESTAMP>_pre_migration/zotero.sqlite ~/Zotero/zotero.sqlite

# (必要なら) Google Drive側のファイルもローカルstorage/<KEY>/へ戻す
# 注意: migrateスクリプトは安全のためcopy+verify+unlinkを使うので、
# 移動済ファイルはGoogle Drive側にしか存在しない。
# ローカルに戻すには手動移動が必要。
```

### Q. 標準添付アイテム（Standalone Attachment）が対象外になる

`migrate_to_drive.py` は標準添付（親アイテムなし）も移動するが、`rename_attachments.py` は親メタデータが必須なのでスキップする。Zoteroに親アイテムを追加してから再実行してくれや。

---

## ファイル構成

```
zotero-gdrive-setup/
├── README.md
├── LICENSE                          # MIT
├── CHANGELOG.md
├── CONTRIBUTING.md
├── pyproject.toml
├── .gitignore
├── .github/
│   ├── workflows/ci.yml             # GitHub Actions CI
│   └── ISSUE_TEMPLATE/              # Issue雛形
├── docs/
│   └── architecture.md              # 内部構造
├── scripts/
│   ├── _common.py                   # 共通処理
│   ├── filenames.py                 # ファイル名生成（純粋関数）
│   ├── config.example.json
│   ├── migrate_to_drive.py
│   └── rename_attachments.py
└── tests/
    └── test_filenames.py            # filenames.py のユニットテスト
```

## ライセンス

MIT License - 詳細は [LICENSE](./LICENSE) 参照。

## 免責

このツールはZoteroのSQLiteデータベースを直接編集します。安全機構を実装してますが、データ損失のリスクを完全には排除できません。**重要なライブラリはこのツールを使う前に手動でバックアップしてください。** 本ツールの使用によって生じた損害について作者は責任を負いません。

## 貢献

バグ報告・改善提案は [Issues](https://github.com/FallseF/zotero-gdrive-setup/issues) へ。

詳細は [CONTRIBUTING.md](./CONTRIBUTING.md) を参照。
