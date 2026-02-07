import pytest
from src.graph import create_analysis_graph
from src.models.state import OverallState

def test_hello_agent_execution():
    """Tests if the hello agent runs successfully in the graph."""
    graph = create_analysis_graph()
    
    initial_state: OverallState = {
        "products_config": {"products": []},
        "results": {}
    }
    
    # Run the graph
    # Note: This requires GOOGLE_API_KEY to be set in the environment
    try:
        final_state = graph.invoke(initial_state)
        assert final_state is not None
        assert "products_config" in final_state
    except Exception as e:
        error_msg = str(e)
        if "GOOGLE_API_KEY not found" in error_msg:
            pytest.skip("Skipping test because GOOGLE_API_KEY is not set.")
        elif "ResourceExhausted" in error_msg or "429" in error_msg:
            pytest.skip(f"Skipping test due to Gemini API quota limit: {error_msg}")
        elif "NotFound" in error_msg or "404" in error_msg:
            pytest.fail(f"Model not found. Please check the model name in src/utils/llm.py: {error_msg}")
        else:
            raise e