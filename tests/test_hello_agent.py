import pytest
from src.graph import create_analysis_graph
from src.models.state import OverallState

def test_hello_agent_with_ollama():
    """Tests hello agent with Ollama provider."""
    graph = create_analysis_graph()

    initial_state: OverallState = {
        "products_config": {"products": []},
        "results": {}
    }

    config = {
        "configurable": {
            "provider": "ollama",
            "model": "qwen2.5-coder:7b"
        }
    }

    try:
        final_state = graph.invoke(initial_state, config=config)
        assert final_state is not None
        assert "products_config" in final_state
    except Exception as e:
        pytest.fail(f"Ollama test failed: {e}")

def test_hello_agent_with_gemini():
    """Tests hello agent with Gemini provider."""
    graph = create_analysis_graph()

    initial_state: OverallState = {
        "products_config": {"products": []},
        "results": {}
    }

    config = {
        "configurable": {
            "provider": "gemini",
            "model": "gemini-flash-latest"
        }
    }

    try:
        final_state = graph.invoke(initial_state, config=config)
        assert final_state is not None
        assert "products_config" in final_state
    except Exception as e:
        error_msg = str(e)
        if "GOOGLE_API_KEY not found" in error_msg:
            pytest.skip("Skipping Gemini test because GOOGLE_API_KEY is not set.")
        elif "ResourceExhausted" in error_msg or "429" in error_msg:
            pytest.skip(f"Skipping test due to Gemini API quota limit: {error_msg}")
        else:
            pytest.fail(f"Gemini test failed: {e}")