# AI-powered Repository Analysis System

LangGraphとGeminiを使用した、複数リポジトリ構成システムの自動解析システム。
リポジトリ内の実行プロセス（Project）を特定し、技術スタック、データベース、インターフェースを自動解析します。

## 初期セットアップ

### 1. ツール管理の準備

このプロジェクトでは、PythonおよびNode.jsのバージョン管理に [mise](https://mise.jdx.dev/) を使用しています。

```bash
# miseのインストール（未導入の場合）
curl https://mise.jdx.dev/install.sh | sh

# ツール（Python 3.12等）のインストール
mise install
```

### 2. 環境変数の設定

Gemini APIを使用するために `GOOGLE_API_KEY` の設定が必要です。

```bash
cp .env.example .env
# .env を編集して実際の API キーを記入してください
```

### 3. 依存関係のインストール

```bash
# プロジェクトと依存ライブラリのインストール
pip install .
```

### 4. 動作確認

初期セットアップが正しく完了したか、テストを実行して確認します。

```bash
python3 -m pytest tests/test_hello_agent.py
```
※ APIのクォータ制限によりテストがスキップされる場合がありますが、エラーが出なければセットアップ自体は成功です。

## 使用方法

1. `products.yaml` に解析対象のリポジトリ情報を定義します。
2. 解析を実行します（※メインロジック実装中）。

```bash
python3 src/main.py
```

詳細な設計思想については [GEMINI.md](GEMINI.md) を参照してください。