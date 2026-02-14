import os
import sys

# Ensure local src is prioritized
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from loguru import logger
from src.utils.config import load_products_config
from src.models.state import OverallState
from src.graph import create_analysis_graph
from dotenv import load_dotenv
import argparse

def main():
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="AIOps Repository Analysis System")
    parser.add_argument("--agent", type=str, help="Specific agent to run (e.g., github, hello)")
    parser.add_argument("--prompt", type=str, help="Custom prompt for the agent")
    parser.add_argument("--config", type=str, default="products.yaml", help="Path to products.yaml config file")
    args = parser.parse_args()

    try:
        config = load_products_config(args.config)
        logger.info(f"Loaded config from {args.config} with {len(config.get('products', []))} products.")
        
        # Initialize state
        initial_state: OverallState = {
            "products_config": config,
            "results": {}
        }
        
        # Prepare graph config with configurable parameters
        graph_config = {"configurable": {"prompt": args.prompt}} if args.prompt else {}
        
        graph = create_analysis_graph()
        
        if args.agent:
            logger.info(f"Running specific agent: {args.agent}")
            from src.agents.github_agent import github_agent
            from src.agents.hello_agent import hello_agent

            agent_map = {
                "github": github_agent,
                "hello": hello_agent,
            }
            
            if args.agent in agent_map:
                # Call agent with state and config
                final_state = agent_map[args.agent](initial_state, config=graph_config)
                logger.info(f"Agent {args.agent} completed.")
            else:
                logger.error(f"Error: Agent '{args.agent}' not found. Available agents: {list(agent_map.keys())}")
                sys.exit(1)
        else:
            logger.info("Running full analysis graph.")
            final_state = graph.invoke(initial_state, config=graph_config)
            logger.info("Analysis complete.")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
