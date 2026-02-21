# aiops

LangChain/LangGraph + Gemini によるマルチエージェントシステム。

## セットアップ

```
mise run install
```

## 実行

```
mise run run          # 対話モード
mise run query -- "質問"  # 一問一答
mise run debug        # デバッグログ有効
```

## 構成

- `main.py` — エントリポイント
- `src/agents/` — エージェント実装
- `src/core/` — ロギング・LLM設定
