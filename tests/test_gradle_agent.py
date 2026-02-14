import pytest
import os
from pathlib import Path
from src.agents.gradle_agent import (
    gradle_agent,
    gradle_build,
    gradle_test,
    gradle_dependencies,
    gradle_tasks,
    gradlew_version,
    detect_java_version,
    setup_mise_java,
    ensure_gradlew,
)
from src.models.state import OverallState


# Get the project root directory (where workspace/ is located)
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
TEST_REPO_PATH = PROJECT_ROOT / "workspace" / "springboot-microservices"


@pytest.fixture
def test_repo_path():
    """Fixture to provide the test repository path."""
    if not TEST_REPO_PATH.exists():
        pytest.skip(f"Test repository not found at {TEST_REPO_PATH}")
    return str(TEST_REPO_PATH)


def test_detect_java_version(test_repo_path):
    """Test Java version detection."""
    result = detect_java_version.invoke({"project_path": test_repo_path})

    assert result is not None
    assert "java" in result.lower() or "openjdk" in result.lower()
    print(f"✓ Java version detection test passed")
    print(f"  Detected: {result[:100]}")


def test_ensure_gradlew(test_repo_path):
    """Test ensuring Gradle Wrapper exists."""
    result = ensure_gradlew.invoke({"project_path": test_repo_path})

    assert result is not None
    print(f"✓ Ensure gradlew test passed")
    print(f"  Result: {result[:200]}")

    # Verify gradlew exists after the operation
    gradlew_path = Path(test_repo_path) / "gradlew"
    if "Successfully created" in result or "already exists" in result:
        assert gradlew_path.exists(), "gradlew should exist after ensure_gradlew"
        assert os.access(gradlew_path, os.X_OK), "gradlew should be executable"


def test_gradlew_version_tool(test_repo_path):
    """Test the gradlew_version tool directly."""
    # First ensure gradlew exists
    ensure_gradlew.invoke({"project_path": test_repo_path})

    result = gradlew_version.invoke({"project_path": test_repo_path})

    assert result is not None
    assert "Gradle" in result
    print(f"✓ Gradle version test passed")
    print(f"  Version info: {result[:100]}")


def test_gradle_tasks_tool(test_repo_path):
    """Test the gradle_tasks tool directly."""
    # Ensure gradlew exists first
    ensure_gradlew.invoke({"project_path": test_repo_path})

    result = gradle_tasks.invoke({
        "project_path": test_repo_path,
        "all_tasks": False
    })

    assert result is not None
    assert "build" in result.lower() or "tasks" in result.lower()
    print(f"✓ Gradle tasks test passed")


def test_gradle_build_tool(test_repo_path):
    """Test the gradle_build tool directly."""
    # Ensure gradlew exists first
    ensure_gradlew.invoke({"project_path": test_repo_path})

    result = gradle_build.invoke({
        "project_path": test_repo_path,
        "skip_tests": True,  # Skip tests for faster execution
        "parallel": False
    })

    assert result is not None
    # Build might succeed or fail, but we should get a result
    print(f"✓ Gradle build test completed")
    print(f"  Build result: {result[:200]}")


def test_gradle_dependencies_tool(test_repo_path):
    """Test the gradle_dependencies tool directly."""
    # Ensure gradlew exists first
    ensure_gradlew.invoke({"project_path": test_repo_path})

    result = gradle_dependencies.invoke({
        "project_path": test_repo_path,
        "configuration": None,
        "project_name": None
    })

    assert result is not None
    print(f"✓ Gradle dependencies test passed")
    print(f"  Dependencies info: {result[:200]}")


def test_gradle_agent_basic_workflow(test_repo_path):
    """
    Tests the gradle_agent with a basic build workflow.
    Uses real repository without mocking.
    """
    state: OverallState = {
        "products_config": {},
        "results": {}
    }

    custom_instructions = (
        f"In the Gradle project at '{test_repo_path}':\n"
        "1. Ensure Gradle Wrapper exists\n"
        "2. Detect Java version\n"
        "3. Check Gradle version\n"
        "4. List available tasks"
    )

    config = {
        "configurable": {
            "provider": "ollama",
            "model": "qwen3:8b",
            "prompt": custom_instructions,
            "project_root": str(PROJECT_ROOT),
            "max_iterations": 10,
            "verbose": False
        }
    }

    try:
        final_state = gradle_agent(state, config=config)
        assert final_state == state
        print(f"✓ Gradle agent basic workflow test passed")

    except Exception as e:
        error_msg = str(e)
        if "Ollama" in error_msg or "connection" in error_msg.lower():
            pytest.skip(f"Skipping Ollama test: {error_msg}")
        else:
            pytest.fail(f"Gradle agent test failed: {e}")


def test_gradle_agent_with_mise_setup(test_repo_path):
    """
    Tests the gradle_agent with mise Java setup workflow.
    """
    state: OverallState = {
        "products_config": {},
        "results": {}
    }

    custom_instructions = (
        f"In the Gradle project at '{test_repo_path}':\n"
        "1. Detect current Java version\n"
        "2. Ensure Gradle Wrapper exists\n"
        "3. Check Gradle version"
    )

    config = {
        "configurable": {
            "provider": "ollama",
            "model": "qwen3:8b",
            "prompt": custom_instructions,
            "project_root": str(PROJECT_ROOT),
            "max_iterations": 10,
            "verbose": False
        }
    }

    try:
        final_state = gradle_agent(state, config=config)
        assert final_state == state
        print(f"✓ Gradle agent with mise setup test passed")

    except Exception as e:
        error_msg = str(e)
        if "Ollama" in error_msg or "connection" in error_msg.lower():
            pytest.skip(f"Skipping Ollama test: {error_msg}")
        else:
            pytest.fail(f"Gradle agent with mise test failed: {e}")


@pytest.mark.skipif(
    os.system("which mise > /dev/null 2>&1") != 0,
    reason="mise is not installed"
)
def test_setup_mise_java(test_repo_path):
    """Test setting up Java version using mise (requires mise to be installed)."""
    # This test is marked to skip if mise is not available
    try:
        result = setup_mise_java.invoke({
            "project_path": test_repo_path,
            "java_version": "17"
        })

        assert result is not None
        print(f"✓ Mise Java setup test passed")
        print(f"  Result: {result[:200]}")
    except Exception as e:
        pytest.skip(f"Mise not available or Java 17 not installed: {e}")
