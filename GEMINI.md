# Repository Analysis System (LangGraph Multi-Agent)

このプロジェクトは、複数のリポジトリで構成される複雑なシステムを自動解析するためのLangGraphベースのMulti-Agentシステムです。

## システム構成要素

- **Product**: 1つのプロダクトを構成するリポジトリ群の単位。
- **Repository**: ソースコードの管理単位。
- **Project**: リポジトリ内のディレクトリ、またはDockerイメージ単位で定義される「実行プロセス」の単位。言語やフレームワーク（api, batch, consumer, web, ios, android, kubernetes等）の種別はこのレベルで特定・定義されます。

## Agent 設計

階層的なAgent構造を採用し、各Agentは役割に特化します。解析結果はディレクトリごとにYAML形式で出力され、後続のAgentや要約プロセスで使用されます。

### 1. Orchestrator Agent (Top-level)
- `products.yaml` を読み込み、解析の全体スケジュールを管理。
- 各リポジトリに対して `Repository Analyzer` を起動。

### 2. Repository Analyzer (Coordinator)
- 特定のリポジトリ内の解析フローを管理。
- **Project Discovery Agent** を呼び出し、リポジトリ内に存在するプロジェクト（api, batch, consumer, web, ios, android, kubernetes等）を特定する。
- 各プロジェクトの種別（type）を判定し、適切な `Project Analyzer` を起動。

### 3. Project Discovery Agent
- Dockerfile, docker-compose, Kubernetes manifests, ビルド設定（pom.xml, package.json等）を走査。
- 実行プロセスの単位を特定し、`project_id` を発行。
- プロジェクトの種別（api, batch, consumer, web, ios, android, kubernetes等）を自動判定する。

### 4. Specialized Analysis Agents (Worker)
- **Tech Stack Profiler**: プロジェクト種別に応じた詳細な言語、フレームワーク等を特定。
- **Database Analyst**: 使用しているDBのリストアップとスキーマ定義の抽出。
- **Dependency Analyst**: 依存ライブラリや内部モジュール間の依存関係を解析。
- **Interface Analyst**: Inbound (REST, gRPC, Kafka Consumer等) と Outbound (外部API, Kafka Producer等) を解析。

### 5. Summary Agent
- **Project Summarizer**: 各プロジェクトの解析結果（YAML）を統合・要約。
- **Repository Summarizer**: リポジトリ全体のプロジェクト群を統合・要約。

## 出力ディレクトリ構造

```text
analysis_results/
└── {product_name}/
    ├── {repository_name}/
    │   ├── repo_summary.yaml
    │   └── {project_id}/
    │       ├── tech_stack.yaml
    │       ├── database.yaml
    │       ├── dependencies.yaml
    │       ├── interfaces.yaml
    │       └── project_summary.yaml
    └── summary.yaml
```

## 入力YAMLスキーマ定義

### products.yaml
解析対象のプロダクトとリポジトリを定義します。リポジトリは一意のIDで管理され、プロダクトからID参照されます。プロジェクトの種別（type）は解析時に自動判定されるため、ここでは定義しません。

```yaml
repositories:
  - id: "repo_id"
    name: "display_name"
    path: "workspace/repo_name"

products:
  - id: "product_id"
    name: "display_name"
    repository_ids:
      - "repo_id"
```

## 出力YAMLスキーマ定義

### 1. tech_stack.yaml
```yaml
project_id: "string"
type: "api | batch | consumer | web | ios | android | kubernetes"
language: "string"
framework: "string"
build_tool: "string"
runtime: "string"
```

### 2. database.yaml
```yaml
databases:
  - name: "db_name"
    type: "postgresql | mysql | redis | etc"
    schemas:
      - table_name: "string"
        columns:
          - name: "string"
            type: "string"
```

### 3. dependencies.yaml
```yaml
dependencies:
  internal:
    - project_id: "string"
      type: "library | service"
  external:
    - name: "package_name"
      version: "string"
```

### 4. interfaces.yaml
```yaml
interfaces:
  inbound:
    - type: "rest | grpc | kafka_consumer | redis_sub"
      endpoint: "string"
      protocol: "string"
      description: "string"
  outbound:
    - type: "rest | grpc | kafka_producer | redis_pub"
      destination: "string"
      protocol: "string"
      description: "string"
```

## 解析ワークフロー

1. **Input**: `products.yaml` の定義。
2. **Phase 1: Discovery**: Dockerイメージを起点に解析対象（Project）を特定。
3. **Phase 2: Deep Dive**: 各Projectに対して技術スタック、DB、依存、I/Fの並列解析。
4. **Phase 3: Aggregation**: 小粒度の解析結果をYAMLから読み取り、上位の要約を作成。

## 前提知識・依存ツール

- **Tool Management**: [mise](https://mise.jdx.dev/) を使用して Python (3.11+) および Node.js のバージョンを管理します。
- **Project Configuration**: `pyproject.toml` を使用した現代的な Python プロジェクト構成を採用しています。
- **LLM Backend**: Google Gemini (gemini-1.5-pro) を使用します。実行には `GOOGLE_API_KEY` が必要です。
- **Workspace**: 解析対象のリポジトリはプロジェクトルートの `workspace/` ディレクトリ配下にクローンされます。
- **LangGraph**: Agentのステート管理とワークフロー制御。
- **Source Code Analysis**: 各言語（Go, Java, TypeScript, Swift等）の静的解析手法。
- **YAML Schemas**: Agent間通信および永続化のための共通フォーマット定義。
