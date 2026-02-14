from langgraph.graph import StateGraph, END
from src.models.state import OverallState
from src.agents.hello_agent import hello_agent
from src.agents.github_agent import github_agent

def create_analysis_graph():
    workflow = StateGraph(OverallState)

    # Nodes
    workflow.add_node("github", github_agent)
    workflow.add_node("hello", hello_agent)
    
    # Workflow
    workflow.set_entry_point("github")
    workflow.add_edge("github", "hello")
    workflow.add_edge("hello", END)

    return workflow.compile()
