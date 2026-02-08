import os
import yaml
from typing import Any, Dict, Optional

def get_metadata_path(repo_name: str, project_id: Optional[str] = None) -> str:
    """
    Returns the path to the metadata directory for a given repository and optionally a project.
    
    Args:
        repo_name: The name of the repository.
        project_id: Optional project ID within the repository.
        
    Returns:
        The absolute path to the directory.
    """
    project_root = os.getcwd()
    path = os.path.join(project_root, "metadata", repo_name)
    if project_id:
        path = os.path.join(path, project_id)
    return path

def save_yaml(data: Any, repo_name: str, filename: str, project_id: Optional[str] = None) -> str:
    """
    Saves data as a YAML file in the appropriate metadata directory.
    
    Args:
        data: The data to save.
        repo_name: The name of the repository.
        filename: The name of the YAML file (e.g., 'tech_stack.yaml').
        project_id: Optional project ID.
        
    Returns:
        The path where the file was saved.
    """
    output_dir = get_metadata_path(repo_name, project_id)
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, filename)
    with open(output_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    return output_file
