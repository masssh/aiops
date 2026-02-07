import os
import sys

# Ensure local src is prioritized
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.config import load_products_config
from src.models.state import OverallState
from src.graph import create_analysis_graph
from dotenv import load_dotenv
import argparse

def main():
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="AIOps Repository Analysis System")
    parser.add_argument("--agent", type=str, help="Specific agent to run (e.g., github, hello)")
    args = parser.parse_args()

    try:
        config = load_products_config()
        print(f"Loaded config with {len(config.get('products', []))} products.")
        
        # Initialize state
        initial_state: OverallState = {
            "products_config": config,
            "results": {}
        }
        
        graph = create_analysis_graph()
        
        if args.agent:
            print(f"Running specific agent: {args.agent}")
            # To run a specific node in LangGraph, we can use the graph's nodes directly
            # or invoke with a config that targets the node if supported, 
            # but for a simple "run this node", we can call the agent function.
            
            # Retrieve node from the compiled graph's internal structure if possible,
            # or better, just define a mapping.
            from src.agents.github_agent import github_agent
            from src.agents.hello_agent import hello_agent
            
            agent_map = {
                "github": github_agent,
                "hello": hello_agent
            }
            
            if args.agent in agent_map:
                final_state = agent_map[args.agent](initial_state)
                print(f"Agent {args.agent} completed.")
            else:
                print(f"Error: Agent '{args.agent}' not found. Available agents: {list(agent_map.keys())}")
                sys.exit(1)
        else:
            print("Running full analysis graph.")
            final_state = graph.invoke(initial_state)
            print("Analysis complete.")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
