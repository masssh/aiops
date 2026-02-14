# Interactive Agent Notebooks

このディレクトリには、各agentをJupyter notebookで対話的に実行できるnotebookが含まれています。

## セットアップ

1. 依存パッケージをインストール:
```bash
pip install -e .
```

2. 環境変数を設定:
```bash
cp .env.example .env
# .envファイルを編集してAPIキーを設定
```

3. Jupyter Labを起動:
```bash
jupyter lab
```

または、プロジェクトルートから:
```bash
./start_notebook.sh
```

## 利用可能なNotebook

### 1. hello_agent.ipynb
シンプルなHello Worldエージェント。異なるLLMプロバイダー（Gemini, OpenAI, Anthropic, Ollama）をテストできます。

**使い方:**
1. notebookを開く
2. プロバイダーとモデルを設定
3. セルを実行

### 2. github_agent.ipynb
Git/GitHub操作のための包括的なエージェント。

**主な機能:**
- リポジトリのクローン
- ブランチ管理
- コミット・プッシュ
- Pull Request作成・管理
- Issue管理
- Release管理

**思考過程のロギング機能:**
- LLMの判断、ツール選択、実行結果を詳細にログ記録
- 標準出力（INFO レベル以上）とログファイル（全ログ）に同時出力
- ログファイル: `logs/github_agent_YYYYMMDD_HHMMSS.log`

**使い方:**
1. notebookを開く
2. セットアップセルを実行すると、**自動的に `products.yaml` が読み込まれます**
3. そのまま実行すると、products.yamlの全リポジトリを同期
4. または `PROMPT` 変数にカスタム指示を記述（日本語OK）

**例:**
```python
# デフォルト動作: products.yamlの全リポジトリを同期
result = github_agent(state, config)

# カスタム指示
PROMPT = "リポジトリ owner/repo を workspace/repo にクローンしてください"

# ログディレクトリのカスタマイズ
config = RunnableConfig(
    configurable={
        "log_dir": "../logs",  # ログファイルの出力先
        ...
    }
)
```

### 3. gradle_agent.ipynb
Gradleプロジェクトを解析するエージェント。

**主な機能:**
- モジュール構成の特定
- 依存関係の抽出
- 技術スタックの分析
- 解析結果をYAML形式で保存

**使い方:**
1. notebookを開く
2. セットアップセルを実行すると、**自動的に `products.yaml` が読み込まれます**
3. そのまま実行すると、products.yamlの全リポジトリを解析
4. または特定のリポジトリを指定してカスタム解析
5. 結果は `metadata/` ディレクトリに保存される

## LLMプロバイダーの設定

各notebookで以下のプロバイダーを選択できます:

### Ollama（ローカル実行）
```python
PROVIDER = "ollama"
MODEL = "qwen3:8b"  # または "qwen2.5-coder:7b" など
```

### Gemini
```python
PROVIDER = "gemini"
MODEL = None  # デフォルトは "gemini-flash-latest"
```
環境変数 `GOOGLE_API_KEY` が必要です。

### OpenAI
```python
PROVIDER = "openai"
MODEL = "gpt-4o"  # または "gpt-4o-mini" など
```
環境変数 `OPENAI_API_KEY` が必要です。

### Anthropic
```python
PROVIDER = "anthropic"
MODEL = "claude-sonnet-4-5-20250929"
```
環境変数 `ANTHROPIC_API_KEY` が必要です。

## トラブルシューティング

### モジュールが見つからない
notebookの最初のセルで `sys.path.append('..')` を実行していることを確認してください。

### APIキーエラー
`.env` ファイルに必要なAPIキーが設定されているか確認してください。

### Ollamaが使えない
Ollamaをインストールして起動してください:
```bash
# macOS
brew install ollama
ollama serve

# モデルをダウンロード
ollama pull qwen3:8b
```

## ディレクトリ構造

```
notebooks/
├── README.md              # このファイル
├── hello_agent.ipynb      # Hello Worldエージェント
├── github_agent.ipynb     # GitHub操作エージェント
└── gradle_agent.ipynb     # Gradle解析エージェント
```

## Tips

1. **products.yamlの自動読み込み**: github_agentとgradle_agentは、notebookを開いた時点で自動的にプロジェクトルートの `products.yaml` を読み込みます。リポジトリ設定を毎回手動で入力する必要はありません。

2. **promptは日本語でOK**: github_agentなど、promptを受け付けるagentは日本語で指示できます。

3. **複数リポジトリの一括処理**: products.yamlに複数のリポジトリを定義しておけば、一度に全リポジトリを処理できます。

4. **解析結果の確認**: gradle_agentの解析結果は `metadata/{repo_name}/gradle_analysis.yaml` に保存されます。

5. **エラー時の再実行**: github_agentは最大20回まで自動でツールを実行します。エラーが出た場合、promptを調整して再実行してください。

6. **カスタマイズも可能**: products.yamlを使わず、notebook内で直接カスタムのリポジトリリストを定義することもできます。
