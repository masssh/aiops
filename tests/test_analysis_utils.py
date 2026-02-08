import os
import shutil
import pytest
from src.utils.analysis import get_metadata_path, save_yaml

def test_get_metadata_path():
    repo_name = "test-repo"
    project_root = os.getcwd()
    
    # Test repo-level path
    expected_repo_path = os.path.join(project_root, "metadata", repo_name)
    assert get_metadata_path(repo_name) == expected_repo_path
    
    # Test project-level path
    project_id = "test-project"
    expected_project_path = os.path.join(project_root, "metadata", repo_name, project_id)
    assert get_metadata_path(repo_name, project_id) == expected_project_path

def test_save_yaml():
    repo_name = "test-repo-save"
    filename = "test_analysis.yaml"
    data = {"key": "value", "list": [1, 2, 3]}
    
    # Cleanup before test
    repo_metadata_dir = os.path.join(os.getcwd(), "metadata", repo_name)
    if os.path.exists(repo_metadata_dir):
        shutil.rmtree(repo_metadata_dir)
        
    try:
        # Save at repo level
        saved_path = save_yaml(data, repo_name, filename)
        assert os.path.exists(saved_path)
        assert filename in saved_path
        assert repo_name in saved_path
        
        import yaml
        with open(saved_path, "r") as f:
            loaded_data = yaml.safe_load(f)
        assert loaded_data == data
        
        # Save at project level
        project_id = "sub-project"
        saved_project_path = save_yaml(data, repo_name, filename, project_id)
        assert os.path.exists(saved_project_path)
        assert project_id in saved_project_path
        
    finally:
        # Cleanup after test
        if os.path.exists(repo_metadata_dir):
            shutil.rmtree(repo_metadata_dir)
