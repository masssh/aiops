from langgraph.graph import StateGraph, END
from src.models.state import OverallState
from src.agents.hello_agent import hello_agent

def create_analysis_graph():
    workflow = StateGraph(OverallState)

    # Simple hello world node
    workflow.add_node("hello", hello_agent)
    
    workflow.set_entry_point("hello")
    workflow.add_edge("hello", END)

    return workflow.compile()
