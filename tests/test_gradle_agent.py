import pytest
from unittest.mock import patch
from src.agents.gradle_agent import (
    gradle_agent,
    gradle_build,
    gradle_test,
    gradle_dependencies,
    gradle_tasks,
    gradlew_version,
)
from src.models.state import OverallState


def test_gradle_agent_basic_workflow():
    """
    Tests the gradle_agent with a basic build workflow.
    Mocks shell command execution to avoid side effects.
    """
    state: OverallState = {
        "products_config": {},
        "results": {}
    }

    with patch("src.utils.command.run_command") as mock_run:
        mock_run.return_value = "BUILD SUCCESSFUL"

        custom_instructions = (
            "In the Gradle project at 'workspace/test-gradle-project':\n"
            "1. Check Gradle version\n"
            "2. List available tasks\n"
            "3. Run the build task"
        )

        config = {
            "configurable": {
                "provider": "ollama",
                "model": "qwen3:8b",
                "gradle_agent_prompt": custom_instructions,
                "max_iterations": 10,
                "verbose": False
            }
        }

        try:
            final_state = gradle_agent(state, config=config)
            assert final_state == state

            # Verify that some commands were called
            assert mock_run.call_count > 0, "Gradle agent should have called tools"
            print(f"✓ Gradle agent basic workflow test passed. Command count: {mock_run.call_count}")

        except Exception as e:
            error_msg = str(e)
            if "Ollama" in error_msg or "connection" in error_msg.lower():
                pytest.skip(f"Skipping Ollama test: {error_msg}")
            else:
                pytest.fail(f"Gradle agent test failed: {e}")


def test_gradle_agent_test_workflow():
    """
    Tests the gradle_agent with test execution workflow.
    """
    state: OverallState = {
        "products_config": {},
        "results": {}
    }

    with patch("src.utils.command.run_command") as mock_run:
        mock_run.return_value = "BUILD SUCCESSFUL"

        custom_instructions = (
            "In the Gradle project at 'workspace/test-gradle-project':\n"
            "1. Run all tests\n"
            "2. Display test results"
        )

        config = {
            "configurable": {
                "provider": "ollama",
                "model": "qwen3:8b",
                "gradle_agent_prompt": custom_instructions,
                "max_iterations": 10,
                "verbose": False
            }
        }

        try:
            final_state = gradle_agent(state, config=config)
            assert final_state == state
            print(f"✓ Gradle test workflow test passed")

        except Exception as e:
            error_msg = str(e)
            if "Ollama" in error_msg or "connection" in error_msg.lower():
                pytest.skip(f"Skipping Ollama test: {error_msg}")
            else:
                pytest.fail(f"Gradle test workflow failed: {e}")


def test_gradlew_version_tool():
    """Test the gradlew_version tool directly."""
    with patch("src.utils.command.run_command") as mock_run:
        mock_run.return_value = """
------------------------------------------------------------
Gradle 8.5
------------------------------------------------------------

Build time:   2023-11-29 14:08:57 UTC
Revision:     28aca86a7180baa17117e0e5ba01d8ea9feca598
"""

        result = gradlew_version.invoke({"project_path": "/test/gradle-project"})

        assert "Gradle 8.5" in result or "Success" in result
        mock_run.assert_called_once_with(
            ["./gradlew", "--version"],
            cwd="/test/gradle-project"
        )


def test_gradle_tasks_tool():
    """Test the gradle_tasks tool directly."""
    with patch("src.utils.command.run_command") as mock_run:
        mock_run.return_value = """
Build tasks
-----------
assemble - Assembles the outputs of this project.
build - Assembles and tests this project.
clean - Deletes the build directory.
"""

        result = gradle_tasks.invoke({
            "project_path": "/test/gradle-project",
            "all_tasks": False
        })

        assert "build" in result or "assemble" in result or "Success" in result
        mock_run.assert_called_once_with(
            ["./gradlew", "tasks"],
            cwd="/test/gradle-project"
        )


def test_gradle_build_tool():
    """Test the gradle_build tool directly."""
    with patch("src.utils.command.run_command") as mock_run:
        mock_run.return_value = "BUILD SUCCESSFUL in 5s"

        result = gradle_build.invoke({
            "project_path": "/test/gradle-project",
            "skip_tests": False,
            "parallel": False
        })

        assert "BUILD SUCCESSFUL" in result or "Success" in result
        mock_run.assert_called_once_with(
            ["./gradlew", "build"],
            cwd="/test/gradle-project"
        )


def test_gradle_build_skip_tests():
    """Test the gradle_build tool with skip_tests option."""
    with patch("src.utils.command.run_command") as mock_run:
        mock_run.return_value = "BUILD SUCCESSFUL in 3s"

        result = gradle_build.invoke({
            "project_path": "/test/gradle-project",
            "skip_tests": True,
            "parallel": False
        })

        assert "BUILD SUCCESSFUL" in result or "Success" in result
        # Verify that -x test was included in the command
        called_cmd = mock_run.call_args[0][0]
        assert "-x" in called_cmd
        assert "test" in called_cmd


def test_gradle_test_tool():
    """Test the gradle_test tool directly."""
    with patch("src.utils.command.run_command") as mock_run:
        mock_run.return_value = "BUILD SUCCESSFUL\n10 tests completed, 10 passed"

        result = gradle_test.invoke({
            "project_path": "/test/gradle-project",
            "test_filter": None,
            "parallel": False
        })

        assert "BUILD SUCCESSFUL" in result or "tests" in result or "Success" in result
        mock_run.assert_called_once_with(
            ["./gradlew", "test"],
            cwd="/test/gradle-project"
        )


def test_gradle_test_with_filter():
    """Test the gradle_test tool with test filter."""
    with patch("src.utils.command.run_command") as mock_run:
        mock_run.return_value = "BUILD SUCCESSFUL\n5 tests completed"

        result = gradle_test.invoke({
            "project_path": "/test/gradle-project",
            "test_filter": "*IntegrationTest",
            "parallel": False
        })

        assert "BUILD SUCCESSFUL" in result or "Success" in result
        called_cmd = mock_run.call_args[0][0]
        assert "--tests" in called_cmd
        assert "*IntegrationTest" in called_cmd


def test_gradle_dependencies_tool():
    """Test the gradle_dependencies tool directly."""
    with patch("src.utils.command.run_command") as mock_run:
        mock_run.return_value = """
compileClasspath - Compile classpath for source set 'main'.
+--- org.springframework.boot:spring-boot-starter:3.0.0
|    +--- org.springframework.boot:spring-boot:3.0.0
"""

        result = gradle_dependencies.invoke({
            "project_path": "/test/gradle-project",
            "configuration": None,
            "project_name": None
        })

        assert "compileClasspath" in result or "Success" in result
        mock_run.assert_called_once_with(
            ["./gradlew", "dependencies"],
            cwd="/test/gradle-project"
        )


def test_gradle_dependencies_with_configuration():
    """Test the gradle_dependencies tool with configuration filter."""
    with patch("src.utils.command.run_command") as mock_run:
        mock_run.return_value = """
compileClasspath - Compile classpath for source set 'main'.
"""

        result = gradle_dependencies.invoke({
            "project_path": "/test/gradle-project",
            "configuration": "compileClasspath",
            "project_name": None
        })

        assert "Success" in result or "compileClasspath" in result
        called_cmd = mock_run.call_args[0][0]
        assert "--configuration" in called_cmd
        assert "compileClasspath" in called_cmd
