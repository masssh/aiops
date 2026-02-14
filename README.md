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


## Agent の種類

このシステムは複数のSpecialized Agentを提供しています。
各Agentの詳細な使い方は、対応するドキュメントを参照してください。

### GitHub Agent (`src/agents/github_agent.py`)

📖 **詳細**: [GitHub Agent 使用ガイド](docs/github_agent_usage.md)

Git/GitHub操作を専門に担当するAgent。以下の機能を提供：

**リポジトリ管理:**
- リポジトリのクローン (`gh_repo_clone`, `git_clone`)
- リポジトリのフォーク (`gh_repo_fork`)
- リポジトリ情報の表示 (`gh_repo_view`)

**Git基本操作:**
- ステータス確認 (`git_status`)
- プル/プッシュ (`git_pull`, `git_push`)
- ブランチ作成/切り替え (`git_branch_create`, `git_checkout`)
- コミット (`git_add`, `git_commit`)

**Pull Request:**
- PR作成 (`gh_pr_create`)
- PR一覧/詳細表示 (`gh_pr_list`, `gh_pr_view`)
- PRマージ (`gh_pr_merge`)
- PRコメント (`gh_pr_comment`)

**Issue管理:**
- Issue作成/クローズ (`gh_issue_create`, `gh_issue_close`)
- Issue一覧/詳細表示 (`gh_issue_list`, `gh_issue_view`)
- Issueコメント (`gh_issue_comment`)

**Release管理:**
- Release作成 (`gh_release_create`)
- Release一覧/詳細表示 (`gh_release_list`, `gh_release_view`)

### Gradle Agent (`src/agents/gradle_agent.py`)

📖 **詳細**: [Gradle Agent 使用ガイド](docs/gradle_agent_usage.md)

Gradleビルドシステムを専門に担当するAgent。以下の機能を提供：

**ビルド操作:**
- プロジェクトのビルド (`gradle_build`)
- クリーン (`gradle_clean`)
- アセンブル (`gradle_assemble`)

**テスト操作:**
- テスト実行 (`gradle_test`)
- 検証タスク実行 (`gradle_check`)

**タスク管理:**
- タスク一覧表示 (`gradle_tasks`)
- 特定タスクの実行 (`gradle_run_task`)

**依存関係分析:**
- 依存関係ツリー表示 (`gradle_dependencies`)
- 依存関係の詳細情報 (`gradle_dependency_insight`)
- ビルド環境情報 (`gradle_build_environment`)

**プロジェクト情報:**
- プロジェクト一覧 (`gradle_projects`)
- プロジェクトプロパティ表示 (`gradle_properties`)

**Gradle Wrapper:**
- バージョン確認 (`gradlew_version`)
- Wrapperアップグレード (`gradlew_wrapper_upgrade`)

### Base Command Agent (`src/agents/base_command_agent.py`)

📖 **詳細**: [Base Command Agent 開発ガイド](docs/base_command_agent_usage.md)

GitHub AgentやGradle Agentのような、コマンドラインツールを操作するAgentの共通基盤。
新しいコマンド系Agentを実装する際のベースクラスとして使用可能。

**提供機能:**
- 設定管理の標準化
- ロギングの自動セットアップ
- ツール実行ループの共通化
- LLMとの統一的なインタラクションパターン

**カスタムAgentの作成**:
Base Command Agentを継承して、独自のコマンドラインツール用Agentを作成できます。
詳細は[開発ガイド](docs/base_command_agent_usage.md)を参照してください。

## ログ出力

Agent実行時のログは以下のように出力されます：

```
logs/
├── {agent_name}_{timestamp}.log  # Agent実行ごとの詳細ログ
└── app.log                       # アプリケーション全体のログ
```

環境変数で以下のログレベルを設定可能：
- `LOG_LEVEL_FILE`: ファイル出力のログレベル（デフォルト: DEBUG）
- `LOG_LEVEL_CONSOLE`: コンソール出力のログレベル（デフォルト: INFO）

## LangGraph Studio



このプロジェクトは [LangGraph Studio](https://github.com/langchain-ai/langgraph-studio) をサポートしています。



1. [LangGraph Studio プレビュー版](https://github.com/langchain-ai/langgraph-studio?tab=readme-ov-file#download) をインストールします。

2. アプリを起動し、このプロジェクトのディレクトリを選択します。

3. `langgraph.json` の設定に基づいてグラフが読み込まれ、視覚的なデバッグやトレースが可能になります。



詳細な設計思想については [GEMINI.md](GEMINI.md) を参照してください。
