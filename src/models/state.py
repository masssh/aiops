from typing import List, Dict, TypedDict, Annotated, Optional
import operator

def merge_dicts(a: Dict, b: Dict) -> Dict:
    res = a.copy()
    res.update(b)
    return res

class ProjectState(TypedDict):
    project_id: str
    path: str
    type: str  # api, batch, consumer, web, ios, android, kubernetes
    tech_stack: Optional[Dict]
    databases: Optional[List[Dict]]
    dependencies: Optional[List[Dict]]
    interfaces: Optional[Dict[str, List]]
    summary: Optional[str]

class RepositoryState(TypedDict):
    repository_id: str
    repository_name: str
    path: str
    projects: Annotated[List[ProjectState], operator.add]
    repo_summary: Optional[str]

class OverallState(TypedDict):
    products_config: Dict
    # Map of product_id to list of repository states
    results: Annotated[Dict[str, List[RepositoryState]], merge_dicts]