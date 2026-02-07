from src.utils.config import load_products_config
from src.models.state import OverallState
from dotenv import load_dotenv
import sys

def main():
    load_dotenv()
    try:
        config = load_products_config()
        print(f"Loaded config with {len(config.get('products', []))} products.")
        
        # Initialize state
        initial_state: OverallState = {
            "products_config": config,
            "results": {}
        }
        
        # TODO: Initialize and run LangGraph
        print("Ready to run LangGraph analysis.")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
