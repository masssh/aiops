import yaml
from pathlib import Path

def load_products_config(config_path: str = "products.yaml"):
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(path, "r") as f:
        return yaml.safe_load(f)
