# zotero-gdrive-setup

ZoteroのPDF添付ファイルをGoogle Drive（または任意のクラウドストレージ）に保存し、Zoteroクラウドストレージの容量制限を回避するためのセットアップガイドとCLIツール。

[![CI](https://github.com/FallseF/zotero-gdrive-setup/actions/workflows/ci.yml/badge.svg)](https://github.com/FallseF/zotero-gdrive-setup/actions/workflows/ci.yml)

## 何ができる

- 🌐 Zotero ConnectorでブラウザからクリックしたPDFが、自動的にGoogle Driveへ移動・リンク化される
- 📦 既存のローカル保存PDFを一括でGoogle Driveへ移行（CLIスクリプト）
- 🏷 ファイル名を「Author et al. - Year - Title.pdf」形式に統一、カスタマイズも可能
- 💰 Zoteroクラウド有料プラン不要、研究室メンバーでGoogle Drive容量を活用

---

## 📍 自分のユースケースは？

| やりたいこと | 使うもの |
|---|---|
| **新規追加されるPDFを自動でDrive送り** | GUIのみ（[セットアップ手順](#-セットアップgui)） |
| **新規追加時のファイル名を統一** | GUIのみ（Zoteroのrename template設定） |
| **既存の数百〜数千件をDriveへ移行** | CLI `migrate_to_drive.py` |
| **既存ファイル名を全部統一フォーマットへ** | CLI `rename_attachments.py` |
| **dry-runで影響範囲を事前確認** | CLI |
| **命名ロジックをカスタマイズ（CiteKey風等）** | CLI（`scripts/filenames.py`を編集） |
| **CI/cron組み込みで自動運用** | CLI |

GUI（ZotMoov + Zotero標準）で日常運用は完結します。CLIは**バッチ処理 / カスタム命名 / 監査ログ**が要るとき真価が出ます。

---

## 🏗 仕組み

```
[ブラウザ]                    [Zotero]                        [Google Drive]
   │                            │                                  │
   │ 1. Connectorクリック       │                                  │
   │ ───────────────────────► │ 2. PDF取得＋メタデータ保存       │
   │                            │ 3. 自動リネーム（テンプレ適用）   │
   │                            │ 4. ZotMoovが移動＋リンク化       │
   │                            │ ─────────────────────────────► │
   │                            │                                  │ 5. クラウド保存
   │                            │ 6. Zotero項目は「リンク添付」    │
```

DBはローカル、PDF本体はGoogle Drive。Zoteroは参照（リンク）だけ持つ構造。Zoteroクラウドのストレージ枠を一切食わない。

---

## 🚀 セットアップ（GUI）

これだけで新規追加の自動化までは完結します。

### 1. ZotMoovインストール

1. [ZotMoov Releases](https://github.com/wileyyugioh/zotmoov/releases) から最新の `.xpi` をダウンロード
2. Zotero起動 → メニュー `Tools → Plugins`
3. 右上の歯車アイコン ⚙️ → **Install Plugin From File...** → `.xpi` を選択
4. Zoteroを再起動

### 2. Google DriveにZotero用フォルダを作成

例: `マイドライブ/Zotero`

macOS: `/Users/<USERNAME>/Library/CloudStorage/GoogleDrive-<EMAIL>/マイドライブ/Zotero`

### 3. Zotero設定

**Settings → Sync → File Syncing**

- 「Sync attachment files in My Library using」**チェックを外す**（Zoteroクラウドへのアップを止める。これ忘れると無料300MB枠を食う）
- 「Sync attachment files in group libraries using」も外す
- Data Syncingは有効のまま（メタデータsyncは継続）

**Settings → Advanced → Files and Folders**

- 「Linked Attachments」セクションの **Base directory** に上記Google Driveパスを設定

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

ブラウザでPDFを開いてZotero Connectorをクリック。10秒ほどでGoogle Drive側にファイルが現れたらOK。

---

## 🧰 CLIツールの真価

CLIは「新規追加の自動化」のためのものではない（GUIで十分）。
**既存ライブラリの一括処理・命名ロジックのカスタマイズ・予測可能な大量変更**のための道具です。

### 強み1: ファイル名生成ロジックが純粋関数

`scripts/filenames.py` に切り出された `build_filename` は副作用ナシの純粋関数：

```python
build_filename(
    title="Ultrafast small-scale soft electromagnetic robots",
    date="2022-01-15",
    authors=["Mao", "Smith", "Brown"],
    max_title_len=100,
    sep=" - ",
) → "Mao et al. - 2022 - Ultrafast small-scale soft electromagnetic robots.pdf"
```

これによって：

- **36件のユニットテスト**でmacOS/Linux × Python 3.9-3.12 のCIに乗っとる
- **`config.json` 一発で命名フォーマット変更可能**：`"separator": "_"` → 全部 `Author_Year_Title.pdf` に
- **命名ロジック自体の差し替えが容易**：Better BibTeX風 `mao2022ultrafast.pdf` を作りたい等
- **エッジケース対応がZotero標準より細かい**:
  - Windows予約名（CON, AUX等を `_CON` に prefix）
  - Unicode NFC正規化（macOS NFD ↔ Windows NFC の不一致を排除）
  - 制御文字（NUL, ESC等）の除去
  - 末尾ピリオドの保持と最終クリーンアップの両立（"Smith et al." は維持、"Title."→ "Title"）
  - 自由形式の date 文字列からのロバストな年抽出（"April 15, 2023" "(2022)" "1999-2003" 等）

### 強み2: dry-runで未来が見える

```bash
$ python3 rename_attachments.py
[DRY-RUN] 対象: 90件のリンク添付PDF

=== プレビュー (最初の15件) ===
  itemID=420
    BEFORE: Zhu et al. - 2024 - High-speed flexible NIR photodiode.pdf
    AFTER : Zhu et al. - 2023 - High-speed flexible NIR photodiode.pdf
    （メタデータ修正で年が変わる）
  ...

=== 結果 ===
  リネーム対象: 56件
  既に同名で変更不要: 33件
  メタデータ不足でスキップ: 1件   ← itemID=475 を後で手動修正、と分かる
  ファイル名衝突でスキップ: 0件
```

Zotero GUIの「Rename File from Parent Metadata」は押した瞬間に走る。CLIは**実行前にプレビュー＋カウントで確信を持って実行できる**。

### 強み3: 安全機構の層が厚い

| 機構 | 詳細 |
|---|---|
| dry-run default | `--execute` 明示なしならファイル/DB一切変更ナシ |
| EXCLUSIVE DBロック | `BEGIN EXCLUSIVE` でZoteroとの同時編集を物理的に拒否 |
| WAL対応バックアップ | `sqlite3.Connection.backup()` で実行前に自動取得 |
| copy+verify+unlink | クラウドFUSEのsilent truncationを検出 |
| 自動ロールバック | ファイル移動成功・DB更新失敗時にファイルを元に戻す |
| 衝突検出 | 計画フェーズ + 実行直前 + `seen_destinations` set の3層 |
| schema ID解決 | `fieldID`/`creatorTypeID` を実行時に問い合わせ（環境差対応） |
| ベースディレクトリ検証 | Zotero data dir内を指定すると即拒否（誤削除防止） |

### 強み4: 監査ログ

GUIは「完了」ぐらいしか教えてくれへんが、CLIは：

```
=== 結果 ===
  移動成功: 90件
  既に移動先に存在: 0件
  ファイル欠落でスキップ: 115件   ← Sync未完了でローカルに無い分
  エラー: 0件
```

何件が何状態かを構造化出力。シェルスクリプトに組み込んでメール通知・Slack通知も可能。

---

## 🛠 CLIセットアップ

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
python3 migrate_to_drive.py             # dry-run
python3 migrate_to_drive.py --execute   # 本実行
```

### ファイル名を一括整形

```bash
python3 rename_attachments.py             # dry-run
python3 rename_attachments.py --execute   # 本実行
```

### 命名ルールのカスタマイズ

`scripts/filenames.py` の `build_filename` を編集してテストするだけ：

```bash
python3 -m unittest tests.test_filenames -v
```

純粋関数なのでテスト即追加可能。

---

## 動作環境

- **動作確認済**: macOS 14+ / Zotero 7+ / Python 3.9+
- **CIで検証**: Linux (Ubuntu) と macOS で Python 3.9-3.12 の構文・テスト
- **未検証**: Windows（path/Drive mountの差で実環境動作未確認）

実環境動作はテスト範囲外なので、Windows/Linuxで使う場合は **少数アイテムでdry-runしてから本実行** を強く推奨。

---

## トラブルシュート

### Q. Zoteroで「ファイルが見つからない」と出る

1. Google Driveが同期されているか（オフラインだとファイル取得不可）
2. Settings → Advanced → Files and Folders の Base directory が正しいか
3. アイテムのパスが `attachments:<filename>` 形式になっているか

### Q. ZotMoovがインストールできない（"sideload" 警告）

Zotero 7のセキュリティ機能で、初回はGUIから手動承認が必要。Tools → Plugins から該当プラグインを「Enable」。

### Q. 移行スクリプト実行後、Zoteroで一部アイテムが「missing file」になった

Zotero Sync未完了でローカルに実体がなかった分。Zotero側でSyncを完了させてから再実行可能。

### Q. ロールバックしたい

```bash
osascript -e 'tell application "Zotero" to quit'
cp ~/Zotero_backup_<TIMESTAMP>_pre_migration/zotero.sqlite ~/Zotero/zotero.sqlite
# (必要なら) Google Driveからローカルstorage/<KEY>/へファイルを戻す
```

### Q. 標準添付アイテム（Standalone Attachment）が対象外になる

`rename_attachments.py` は親メタデータが必須なのでスキップする。Zoteroに親アイテムを追加してから再実行。

---

## ファイル構成

```
zotero-gdrive-setup/
├── README.md
├── LICENSE                          # MIT
├── CHANGELOG.md
├── CONTRIBUTING.md
├── pyproject.toml
├── .github/
│   ├── workflows/ci.yml             # GitHub Actions CI
│   └── ISSUE_TEMPLATE/
├── docs/
│   └── architecture.md
├── scripts/
│   ├── _common.py                   # 設定/DBロック/バックアップ
│   ├── filenames.py                 # ファイル名生成（純粋関数、テスタブル）
│   ├── config.example.json
│   ├── migrate_to_drive.py
│   └── rename_attachments.py
└── tests/
    └── test_filenames.py            # 36件のユニットテスト
```

## ライセンス

MIT License - 詳細は [LICENSE](./LICENSE) 参照。

## 免責

このツールはZoteroのSQLiteデータベースを直接編集します。安全機構を実装してますが、データ損失のリスクを完全には排除できません。**重要なライブラリは事前に手動バックアップ推奨**。本ツールの使用によって生じた損害について作者は責任を負いません。

## 貢献

バグ報告・改善提案は [Issues](https://github.com/FallseF/zotero-gdrive-setup/issues) へ。詳細は [CONTRIBUTING.md](./CONTRIBUTING.md)。
