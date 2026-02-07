from src.models.state import OverallState
from src.utils.llm import get_llm
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

def hello_agent(state: OverallState, config: RunnableConfig = None):
    """A simple agent that says hello using Gemini."""
    llm = get_llm()
    response = llm.invoke([HumanMessage(content="Say 'Hello World from Gemini Agent!'")])
    print(f"\nAgent Response: {response.content}\n")
    return state