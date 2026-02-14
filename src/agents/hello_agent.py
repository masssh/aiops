from src.models.state import OverallState
from src.utils.llm import get_llm, Provider
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

def hello_agent(state: OverallState, config: RunnableConfig = None):
    """
    A simple agent that says hello using a configurable LLM provider.

    Can be configured via RunnableConfig:
        config = {"configurable": {"provider": "ollama", "model": "qwen2.5-coder:7b"}}
    """
    # Extract provider and model from config, with defaults
    provider: Provider = "ollama"
    model: str | None = None

    if config and "configurable" in config:
        provider = config["configurable"].get("provider", "ollama")
        model = config["configurable"].get("model", None)

    llm = get_llm(provider=provider, model=model)
    response = llm.invoke([HumanMessage(content=f"Say 'Hello World from {provider.title()} Agent!'")])
    print(f"\nAgent Response: {response.content}\n")
    return state