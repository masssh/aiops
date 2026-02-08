from langgraph.graph import StateGraph, END
from src.models.state import OverallState
from src.agents.hello_agent import hello_agent
from src.agents.github_agent import github_agent
from src.agents.gradle_agent import gradle_agent

def create_analysis_graph():
    workflow = StateGraph(OverallState)

    # Nodes
    workflow.add_node("github", github_agent)
    workflow.add_node("gradle", gradle_agent)
    workflow.add_node("hello", hello_agent)
    
    # Workflow
    workflow.set_entry_point("github")
    workflow.add_edge("github", "gradle")
    workflow.add_edge("gradle", "hello")
    workflow.add_edge("hello", END)

    return workflow.compile()
