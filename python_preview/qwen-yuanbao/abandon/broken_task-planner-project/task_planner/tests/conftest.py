"""
conftest.py — pytest 全局 fixture
"""
import pytest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def harness():
    """每个测试会话创建一个 Harness"""
    from task_planner.tests.harness.agent_harness import AgentHarness
    import os
    os.environ["USE_MOCK_LLM"] = "false"
    return AgentHarness(enable_refine=True)


@pytest.fixture(scope="session")
def expectations():
    from task_planner.tests.run_eval import EXPECTATIONS
    return EXPECTATIONS
