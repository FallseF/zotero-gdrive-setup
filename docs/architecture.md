# Architecture

## Zoteroの添付ファイル管理の基礎

Zoteroの `itemAttachments` テーブルには、各添付ファイルの `linkMode` というカラムがある：

| linkMode | 名称 | 意味 |
|---|---|---|
| 0 | imported_file | 手動で追加されたローカル保存ファイル |
| 1 | imported_url | Connector等経由で保存されたファイル（PDFスナップショット） |
| 2 | linked_file | リンク添付（ファイル本体は外部、Zoteroは参照のみ） |
| 3 | linked_url | Webリンク（ローカルファイルなし） |

`path` カラムの形式は linkMode によって異なる:

- `linkMode IN (0, 1)`: `storage:<filename>` → `<dataDir>/storage/<itemKey>/<filename>`
- `linkMode = 2` (相対パス): `attachments:<rel_path>` → `<baseAttachmentPath>/<rel_path>`
- `linkMode = 2` (絶対パス): `/Users/.../full/path.pdf`
- `linkMode = 3`: URL文字列

## 本ツールの動作原理

### `migrate_to_drive.py`

1. `itemAttachments` から `linkMode IN (0, 1) AND contentType = 'application/pdf'` を抽出
2. 各アイテムについて:
   - `<dataDir>/storage/<key>/<filename>` を `<baseDir>/<key>/<filename>` に移動
   - DBの `linkMode = 2`、`path = 'attachments:<key>/<filename>'` に更新
3. 空になった `storage/<key>/` ディレクトリは削除

storage_key単位でサブディレクトリを維持する理由:
- ファイル名衝突を完全回避（複数論文で同じファイル名は珍しくない）
- Zotero標準storage構造との対称性を保ち、ロールバックが容易

### `rename_attachments.py`

1. `linkMode = 2 AND contentType = 'application/pdf'` を抽出
2. 各アイテムの親アイテムからメタデータ取得:
   - title (`fieldID = 1`)
   - date (`fieldID = 6`)
   - authors (`itemCreators.creatorTypeID = 10`)
3. ファイル名を生成: `<firstCreator> - <year> - <title>.pdf`
4. ファイル名サニタイズ:
   - 不正文字 (`/ \ : ? * " < > |`) を除去/置換
   - 連続空白を単一空白に
   - title を100文字で切り詰め
5. ファイル名衝突がない場合のみ、ファイル移動＋DB更新

firstCreator のフォーマット:
- 1人: `Smith`
- 2人: `Smith and Jones`
- 3人以上: `Smith et al.`

## なぜZoteroのGUIではなく直接DB操作するか

ZotMoovとZotero標準機能でほぼ同じことができる。本スクリプトの存在意義は:

- **大量処理時のスピード**: 数千件のライブラリで右クリックメニュー操作するより速い
- **冪等性**: dry-runで結果確認 → 確信を持って実行できる
- **自動化**: シェルスクリプトに組み込み可能、定期実行も可能
- **ロールバック容易**: バックアップが自動取得される

ただし、GUI操作の方が安全であることに変わりはない。一般ユーザーにはGUI手順を推奨。

## なぜ ZotMoov の Move Selected Items を呼ばない？

ZotMoovのJSはZotero内部から呼ばれることを前提としており、外部Pythonからは触れない。CLI連携APIも提供されていない。

代替案として:
- Zoteroの `--purgeCaches` のような起動時オプションで自動移行を仕込む → そんなオプションは存在しない
- Zoteroをheadless起動して JavaScript Run → 公式に対応していない

結果として、外部スクリプトからの直接DB操作が最も実用的なアプローチとなる。

## 安全機構

| 機構 | 実装 |
|---|---|
| Zotero起動中チェック | `pgrep -i zotero` で確認、起動中なら実行拒否 |
| DBバックアップ | `--execute` 時に必ず `Zotero_backup_<TIMESTAMP>_<label>/` を作成 |
| dry-run デフォルト | `--execute` を明示しない限りファイル・DBに変更を加えない |
| 衝突回避 | 移動先ファイルが既存の場合はスキップ |
| メタデータ欠落チェック | title が空のアイテムはリネームをスキップ（情報損失防止） |
| ゴミ箱除外 | `deletedItems` テーブルにあるアイテムは対象外 |

## 想定リスク

- **Google Drive非同期時の挙動**: マウントされていない状態で実行するとファイル移動が失敗する。スクリプトは事前にbase directoryの存在をチェックする。
- **Zotero Syncとの相互作用**: Zoteroクラウドへのファイル同期を有効にしている場合、リンク添付はクラウドへアップロードされない。これは想定された挙動。
- **複数端末での共有**: 同じGoogle Driveを別の端末でも参照する場合、Zoteroのライブラリ自体もSyncで同期する必要がある。本ツールはローカルDB操作のみ。
