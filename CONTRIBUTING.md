# Contributing

このプロジェクトへの貢献歓迎します。

## バグ報告・機能要望

GitHub の [Issues](https://github.com/FallseF/zotero-gdrive-setup/issues) に投稿してください。

特に以下の情報があると対応しやすいです:
- OS と Zotero バージョン
- 実行コマンドと出力（エラーがあればフルスタックトレース）
- `config.json` の内容（メアド等は伏せて構いません）

## Pull Request

1. Issue を立てて方針を相談（大きな変更の場合）
2. fork → ブランチ作成 → 変更
3. `python3 -m unittest discover tests` でテストが通ることを確認
4. PR 作成

### コードスタイル

- Python 3.9+ 互換
- Standard library のみ（外部依存追加は議論したい）
- 型ヒントは可能な範囲で
- ユーザー向けメッセージは日本語（関西弁ベース、当プロジェクトの雰囲気）

### テスト

純粋関数 (`filenames.py` 等) は `tests/` にユニットテストを追加してください。

DBやファイルシステムに副作用のあるコード (`migrate_to_drive.py` 等) は、現状は実環境でのdry-run確認で代用しています。CIで動かす形のインテグレーションテストの整備は今後の課題です。

## 開発環境

```bash
git clone https://github.com/FallseF/zotero-gdrive-setup.git
cd zotero-gdrive-setup
cp scripts/config.example.json scripts/config.json
# config.json を自環境に合わせて編集
python3 -m unittest discover tests
```

## リリースプロセス

1. `CHANGELOG.md` を更新
2. バージョンタグを切る: `git tag v0.2.0`
3. `git push --tags`

## ライセンス

貢献いただいたコードは MIT License として配布されることに同意したものとみなします。
