from src.models.state import OverallState
from src.utils.llm import get_llm
from langchain_core.messages import HumanMessage

def hello_agent(state: OverallState):
    """A simple agent that says hello using Gemini."""
    llm = get_llm()
    response = llm.invoke([HumanMessage(content="Say 'Hello World from Gemini Agent!'")])
    print(f"\nAgent Response: {response.content}\n")
    return state