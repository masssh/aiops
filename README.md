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

`.env` ファイルで設定可能な項目：
- `GOOGLE_API_KEY`: Google Gemini APIキー（必須）
- `LOG_LEVEL_FILE`: ファイル出力のログレベル（デフォルト: DEBUG）
- `LOG_LEVEL_CONSOLE`: コンソール出力のログレベル（デフォルト: INFO）

利用可能なログレベル: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

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

### コマンドライン実行

1. `products.yaml` に解析対象のリポジトリ情報を定義します。
2. 解析を実行します（※メインロジック実装中）。

```bash
python3 src/main.py
```

### Jupyter Notebookで対話的に実行

各agentをJupyter notebookで対話的に実行できます。promptを渡すだけで簡単に使えます。

```bash
# Jupyter Labを起動
./start_notebook.sh

# または直接
jupyter lab
```

利用可能なnotebook:
- `notebooks/hello_agent.ipynb` - LLMプロバイダーのテスト
- `notebooks/github_agent.ipynb` - Git/GitHub操作（クローン、PR作成など）
- `notebooks/gradle_agent.ipynb` - Gradleプロジェクト解析

詳細は [notebooks/README.md](notebooks/README.md) を参照してください。



## LangGraph Studio



このプロジェクトは [LangGraph Studio](https://github.com/langchain-ai/langgraph-studio) をサポートしています。



1. [LangGraph Studio プレビュー版](https://github.com/langchain-ai/langgraph-studio?tab=readme-ov-file#download) をインストールします。

2. アプリを起動し、このプロジェクトのディレクトリを選択します。

3. `langgraph.json` の設定に基づいてグラフが読み込まれ、視覚的なデバッグやトレースが可能になります。



詳細な設計思想については [GEMINI.md](GEMINI.md) を参照してください。
