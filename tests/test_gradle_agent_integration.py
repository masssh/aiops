"""
Integration tests for Gradle Agent using real springboot-microservices project.

These tests use the actual springboot-microservices repository in workspace/
and execute real Gradle commands (not mocked).
"""

import pytest
from pathlib import Path
from src.agents.gradle_agent import gradle_agent
from src.models.state import OverallState


# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent
GRADLE_PROJECT_PATH = PROJECT_ROOT / "workspace" / "springboot-microservices"


def is_gradle_project_available():
    """Check if the springboot-microservices Gradle project is available."""
    gradlew_path = GRADLE_PROJECT_PATH / "gradlew"
    return GRADLE_PROJECT_PATH.exists() and gradlew_path.exists()


@pytest.mark.skipif(
    not is_gradle_project_available(),
    reason="springboot-microservices project not found in workspace/"
)
class TestGradleAgentIntegration:
    """Integration tests using real Gradle project."""

    def test_gradle_version_check(self):
        """Test checking Gradle version on real project."""
        state: OverallState = {
            "products_config": {},
            "results": {}
        }

        config = {
            "configurable": {
                "provider": "ollama",
                "model": "qwen3:8b",
                "gradle_agent_prompt": f"""
                    {GRADLE_PROJECT_PATH} でGradleバージョンを確認してください。
                """,
                "max_iterations": 5,
                "verbose": False
            }
        }

        try:
            final_state = gradle_agent(state, config=config)
            assert final_state == state
            print("✓ Gradle version check integration test passed")

        except Exception as e:
            error_msg = str(e)
            if "Ollama" in error_msg or "connection" in error_msg.lower():
                pytest.skip(f"Skipping Ollama test: {error_msg}")
            else:
                pytest.fail(f"Integration test failed: {e}")

    def test_gradle_tasks_listing(self):
        """Test listing Gradle tasks on real project."""
        state: OverallState = {
            "products_config": {},
            "results": {}
        }

        config = {
            "configurable": {
                "provider": "ollama",
                "model": "qwen3:8b",
                "gradle_agent_prompt": f"""
                    {GRADLE_PROJECT_PATH} で利用可能なGradleタスクの一覧を表示してください。
                """,
                "max_iterations": 5,
                "verbose": False
            }
        }

        try:
            final_state = gradle_agent(state, config=config)
            assert final_state == state
            print("✓ Gradle tasks listing integration test passed")

        except Exception as e:
            error_msg = str(e)
            if "Ollama" in error_msg or "connection" in error_msg.lower():
                pytest.skip(f"Skipping Ollama test: {error_msg}")
            else:
                pytest.fail(f"Integration test failed: {e}")

    def test_gradle_projects_listing(self):
        """Test listing subprojects in multi-project build."""
        state: OverallState = {
            "products_config": {},
            "results": {}
        }

        config = {
            "configurable": {
                "provider": "ollama",
                "model": "qwen3:8b",
                "gradle_agent_prompt": f"""
                    {GRADLE_PROJECT_PATH} のプロジェクト一覧を表示してください。
                    これはマルチプロジェクトビルドです。
                """,
                "max_iterations": 5,
                "verbose": False
            }
        }

        try:
            final_state = gradle_agent(state, config=config)
            assert final_state == state
            print("✓ Gradle projects listing integration test passed")

        except Exception as e:
            error_msg = str(e)
            if "Ollama" in error_msg or "connection" in error_msg.lower():
                pytest.skip(f"Skipping Ollama test: {error_msg}")
            else:
                pytest.fail(f"Integration test failed: {e}")

    def test_gradle_dependencies_analysis(self):
        """Test analyzing dependencies on real project."""
        state: OverallState = {
            "products_config": {},
            "results": {}
        }

        config = {
            "configurable": {
                "provider": "ollama",
                "model": "qwen3:8b",
                "gradle_agent_prompt": f"""
                    {GRADLE_PROJECT_PATH} の依存関係を分析してください。
                    product-service サブプロジェクトの依存関係を表示してください。
                """,
                "max_iterations": 10,
                "verbose": False
            }
        }

        try:
            final_state = gradle_agent(state, config=config)
            assert final_state == state
            print("✓ Gradle dependencies analysis integration test passed")

        except Exception as e:
            error_msg = str(e)
            if "Ollama" in error_msg or "connection" in error_msg.lower():
                pytest.skip(f"Skipping Ollama test: {error_msg}")
            else:
                pytest.fail(f"Integration test failed: {e}")

    @pytest.mark.slow
    def test_gradle_build_workflow(self):
        """
        Test complete build workflow: clean, assemble (skip tests).
        Marked as slow because it actually builds the project.
        """
        state: OverallState = {
            "products_config": {},
            "results": {}
        }

        config = {
            "configurable": {
                "provider": "ollama",
                "model": "qwen3:8b",
                "gradle_agent_prompt": f"""
                    {GRADLE_PROJECT_PATH} で以下を順番に実行してください：
                    1. クリーンを実行
                    2. テストをスキップしてアセンブルを実行
                """,
                "max_iterations": 15,
                "verbose": False
            }
        }

        try:
            final_state = gradle_agent(state, config=config)
            assert final_state == state
            print("✓ Gradle build workflow integration test passed")

        except Exception as e:
            error_msg = str(e)
            if "Ollama" in error_msg or "connection" in error_msg.lower():
                pytest.skip(f"Skipping Ollama test: {error_msg}")
            else:
                pytest.fail(f"Integration test failed: {e}")


# Manual test runner (for development)
if __name__ == "__main__":
    if is_gradle_project_available():
        print(f"✓ Gradle project found at: {GRADLE_PROJECT_PATH}")
        print("Running integration tests...")
        pytest.main([__file__, "-v", "-s"])
    else:
        print(f"✗ Gradle project not found at: {GRADLE_PROJECT_PATH}")
        print("Please ensure springboot-microservices is cloned in workspace/")
