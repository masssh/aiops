import pytest
from src.utils.config import load_products_config

@pytest.fixture
def load_config():
    return load_products_config
