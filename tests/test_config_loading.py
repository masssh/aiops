import pytest
from src.models.state import OverallState

def test_load_custom_config(load_config):
    """Verify that we can load a specific products.yaml for a test case."""
    config = load_config("tests/data/test_products.yaml")
    
    assert "products" in config
    assert len(config["products"]) == 1
    assert config["products"][0]["id"] == "test-product"
    
    # Example of how to use it with state
    state: OverallState = {
        "products_config": config,
        "results": {}
    }
    assert state["products_config"]["products"][0]["name"] == "Test Product"

def test_load_default_config(load_config):
    """Verify that it can also load the default products.yaml."""
    try:
        config = load_config("products.yaml")
        assert "products" in config
    except FileNotFoundError:
        pytest.skip("Default products.yaml not found in root.")
