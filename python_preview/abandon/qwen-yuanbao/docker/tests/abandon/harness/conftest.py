"""
conftest.py — pytest 全局 fixture
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def harness():
    """每个测试会话创建一个 Harness"""
    import os

    from tests.harness.agent_harness import AgentHarness

    os.environ["USE_MOCK_LLM"] = "false"
    return AgentHarness(enable_refine=True)


@pytest.fixture(scope="session")
def expectations():
    from tests.run_eval import EXPECTATIONS

    return EXPECTATIONS
