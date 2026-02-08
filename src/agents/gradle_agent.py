import os
import logging
import yaml
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from src.models.state import OverallState, RepositoryState, ProjectState
from src.utils.llm import get_llm
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

@tool
def list_files_recursive(path: str) -> List[str]:
    """Lists all files in a directory recursively, useful for finding build.gradle files."""
    file_list = []
    for root, _, files in os.walk(path):
        for file in files:
            file_list.append(os.path.relpath(os.path.join(root, file), path))
    return file_list

@tool
def read_gradle_file(path: str) -> str:
    """Reads the content of a gradle file."""
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file {path}: {str(e)}"

@tool
def save_analysis_result(repo_path: str, analysis: Dict[str, Any]) -> str:
    """Saves the analysis result to a YAML file in the project root's metadata directory."""
    try:
        # Get repository name from path (e.g., workspace/gradle-masterclass -> gradle-masterclass)
        repo_name = os.path.basename(repo_path)
        
        # Define project root metadata directory
        project_root = os.getcwd()
        output_dir = os.path.join(project_root, "metadata", repo_name)
        
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "gradle_analysis.yaml")
        with open(output_file, "w") as f:
            yaml.dump(analysis, f, default_flow_style=False)
        return f"Analysis saved to {output_file}"
    except Exception as e:
        return f"Error saving analysis: {str(e)}"

def gradle_agent(state: OverallState, config: RunnableConfig = None) -> OverallState:
    """
    Analyzes Gradle projects within the repositories.
    """
    llm = get_llm()
    tools = [list_files_recursive, read_gradle_file, save_analysis_result]
    llm_with_tools = llm.bind_tools(tools)
    
    results = state.get("results", {})
    products_config = state.get("products_config", {})
    repositories = products_config.get("repositories", [])

    for repo in repositories:
        repo_path = repo.get("path")
        if not repo_path or not os.path.exists(repo_path):
            continue
        
        logger.info(f"Analyzing Gradle project at {repo_path}")
        
        system_msg = SystemMessage(content=(
            "You are an expert in Gradle and Java/Kotlin project structures. "
            "Your task is to analyze the given repository and identify all Gradle modules. "
            "For each module, determine:\n"
            "1. Its relative path.\n"
            "2. Whether it's a 'main' application (has a main class or application plugin) or a library.\n"
            "3. Its dependencies (both internal and external).\n"
            "4. The technology stack (language, framework versions).\n"
            "Use the provided tools to explore the codebase. "
            "Finally, save the integrated analysis as a YAML file using 'save_analysis_result'."
        ))
        
        prompt = f"Analyze the repository at path: {repo_path}"
        messages = [system_msg, HumanMessage(content=prompt)]
        
        # Tool execution loop
        import time
        for i in range(15):
            try:
                ai_msg = llm_with_tools.invoke(messages)
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    logger.warning(f"Rate limit hit, waiting 30 seconds... (Attempt {i+1}/15)")
                    time.sleep(30)
                    continue
                raise e
            
            messages.append(ai_msg)
            
            if not ai_msg.tool_calls:
                break
                
            for tool_call in ai_msg.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                
                if tool_name == "list_files_recursive":
                    res = list_files_recursive.invoke(tool_args)
                elif tool_name == "read_gradle_file":
                    res = read_gradle_file.invoke(tool_args)
                elif tool_name == "save_analysis_result":
                    res = save_analysis_result.invoke(tool_args)
                else:
                    res = f"Error: Tool {tool_name} not found."
                    
                messages.append(ToolMessage(content=str(res), tool_call_id=tool_call["id"]))

    return state