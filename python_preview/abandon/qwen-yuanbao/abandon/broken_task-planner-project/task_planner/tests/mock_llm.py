"""
tests/mock_llm.py — 测试专用 Mock LLM
═══════════════════════════════════════════════════
⚠️ 此文件仅用于单元测试 / CI / 离线开发。
   主链路代码（llm_client / agent / app）绝不导入此文件。
   Mock 数据仅供测试验证代码逻辑，不代表真实 LLM 行为。

用法：
    # 在测试代码中 monkey-patch
    from task_planner.tests.mock_llm import install_mock
    install_mock()

    # 之后所有 llm_client 调用都走 Mock
    from task_planner.llm_client import recognize_intent
    intent = recognize_intent("test input")
"""
import json
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("task_planner.tests.mock_llm")

# ═══════════════════════════════════════════════════
#  Mock 数据（仅供测试）
# ═══════════════════════════════════════════════════
_INTENT_RESPONSES = {
    "default": {
        "needs_planning": True,
        "category": "other",
        "summary": "通用任务规划请求",
        "complexity": "medium",
    },
    "做菜": {
        "needs_planning": True,
        "category": "cooking",
        "summary": "提供甜口西红柿炒鸡蛋的详细烹饪步骤",
        "complexity": "simple",
    },
    "旅游": {
        "needs_planning": True,
        "category": "travel",
        "summary": "西双版纳3天3夜美食娱乐美景之旅",
        "complexity": "complex",
    },
    "hello": {
        "needs_planning": False,
        "category": "other",
        "summary": "你好！有什么可以帮你的吗？",
        "complexity": "simple",
    },
}

_PLAN_TEMPLATES = {
    "cooking": {
        "task_name": "甜口西红柿炒鸡蛋",
        "description": "经典家常菜，注意火候和糖的用量",
        "nodes": [
            {"id": 1, "name": "准备食材", "detail": "西红柿2个切滚刀块，鸡蛋3个打散加少许盐"},
            {"id": 2, "name": "炒鸡蛋", "detail": "热锅冷油，中火炒至八分熟盛出"},
            {"id": 3, "name": "炒西红柿", "detail": "少油煸炒西红柿至出汁，加糖调味"},
            {"id": 4, "name": "合并调味", "detail": "回锅鸡蛋，加盐和糖调整甜咸，翻匀出锅"},
        ],
        "edges": [
            {"from": 1, "to": 2, "label": "食材备好"},
            {"from": 2, "to": 3, "label": "鸡蛋盛出"},
            {"from": 3, "to": 4, "label": "西红柿出汁"},
        ],
    },
    "travel": {
        "task_name": "西双版纳3天3夜",
        "description": "美食+美景+民族风情",
        "nodes": [
            {"id": 1, "name": "曼听夜市傣味烧烤", "detail": "香竹糯米饭+烤罗非鱼，人均60元"},
            {"id": 2, "name": "中科院植物园", "detail": "西区王莲+东区原始森林，门票104元"},
            {"id": 3, "name": "告庄篝火晚会", "detail": "傣族舞蹈+放水灯，晚8点开始"},
            {"id": 4, "name": "野象谷半日游", "detail": "索道上山+大象学校，早8点前到"},
            {"id": 5, "name": "澜沧江游船日落", "detail": "告庄码头出发1.5h，票价约120元"},
        ],
        "edges": [
            {"from": 1, "to": 2, "label": "第一天"},
            {"from": 2, "to": 3, "label": "晚上"},
            {"from": 1, "to": 4, "label": "第二天"},
            {"from": 4, "to": 5, "label": "下午"},
        ],
    },
    "default": {
        "task_name": "示例任务计划",
        "description": "Mock 模式下的示例任务",
        "nodes": [
            {"id": 1, "name": "需求分析", "detail": "明确任务目标和约束条件"},
            {"id": 2, "name": "方案设计", "detail": "制定可行方案并评估资源"},
            {"id": 3, "name": "执行准备", "detail": "准备所需材料和工具"},
            {"id": 4, "name": "实施执行", "detail": "按计划逐步执行"},
            {"id": 5, "name": "验收交付", "detail": "检查结果并交付成果"},
        ],
        "edges": [
            {"from": 1, "to": 2, "label": "需求明确"},
            {"from": 2, "to": 3, "label": "方案确定"},
            {"from": 3, "to": 4, "label": "准备就绪"},
            {"from": 4, "to": 5, "label": "执行完成"},
        ],
    },
}

_REFINE_TEMPLATES = {
    "default": {
        "name": "优化后的步骤名称",
        "detail": "1. 第一步：关键参数校验\n2. 第二步：按标准流程执行\n3. 第三步：验证结果",
        "meta": {
            "preconditions": ["前置资源已就绪", "执行权限已校验"],
            "postconditions": ["动作执行完成", "结果符合预期"],
            "retry_policy": "失败后重试最多3次",
        },
    },
}


# ═══════════════════════════════════════════════════
#  Mock 实现
# ═══════════════════════════════════════════════════
def _mock_recognize_intent(user_input: str) -> str:
    """返回意图识别的 Mock JSON 字符串"""
    text = user_input.lower()
    for key, data in _INTENT_RESPONSES.items():
        if key in text:
            return json.dumps(data, ensure_ascii=False)
    return json.dumps(_INTENT_RESPONSES["default"], ensure_ascii=False)


def _mock_generate_plan(user_input: str, intent_info: Dict) -> str:
    """返回任务规划的 Mock JSON 字符串"""
    category = intent_info.get("category", "default")
    template = _PLAN_TEMPLATES.get(category, _PLAN_TEMPLATES["default"])
    return json.dumps(template, ensure_ascii=False)


def _mock_refine_node(node: Dict) -> str:
    """返回节点细化的 Mock JSON 字符串"""
    template = dict(_REFINE_TEMPLATES["default"])
    template["name"] = node.get("name", "优化步骤")
    return json.dumps(template, ensure_ascii=False)


# ═══════════════════════════════════════════════════
#  安装函数（monkey-patch 到 llm_client）
# ═══════════════════════════════════════════════════
def install_mock():
    """
    把 Mock 注入到 task_planner.llm_client 模块。
    调用后，所有 llm_client 的公开接口都走 Mock。

    用法：
        from task_planner.tests.mock_llm import install_mock
        install_mock()
        # 之后所有调用都是 Mock
    """
    import sys
    from unittest import mock

    # 延迟导入（避免循环）
    from .. import llm_client as real_llm

    # Patch 核心调用函数
    real_llm._call_dashscope = mock.MagicMock(
        side_effect=lambda model, prompt, enable_thinking, req_id: _route_mock(prompt, req_id)
    )

    # Patch 公开接口
    real_llm.recognize_intent = mock.MagicMock(
        side_effect=lambda user_input: json.loads(_mock_recognize_intent(user_input))
    )
    real_llm.generate_plan = mock.MagicMock(
        side_effect=lambda user_input, intent_info: json.loads(
            _mock_generate_plan(user_input, intent_info)
        )
    )
    real_llm.refine_node = mock.MagicMock(
        side_effect=lambda node: json.loads(_mock_refine_node(node))
    )

    logger.info("✅ Mock LLM 已安装（仅用于测试）")


def uninstall_mock():
    """恢复真实 LLM 调用"""
    from .. import llm_client as real_llm
    # 重新加载模块以恢复原始函数
    import importlib
    importlib.reload(real_llm)
    logger.info("✅ Mock LLM 已卸载，恢复真实调用")


def _route_mock(prompt: str, req_id: str) -> str:
    """根据 prompt 内容路由到不同的 Mock 数据"""
    # 简单启发式：判断 prompt 类型
    if "意图识别" in prompt or "intent" in prompt.lower():
        # 提取用户输入
        user_input = _extract_user_input(prompt)
        return _mock_recognize_intent(user_input)
    elif "节点细化" in prompt or "refine" in prompt.lower():
        return _mock_refine_node({})
    else:
        # 默认当 plan
        user_input = _extract_user_input(prompt)
        intent = json.loads(_mock_recognize_intent(user_input))
        return _mock_generate_plan(user_input, intent)


def _extract_user_input(prompt: str) -> str:
    """从 prompt 中提取用户输入部分"""
    for marker in ["用户输入：", "用户输入:", "user_input="]:
        if marker in prompt:
            return prompt.split(marker)[-1].strip()[:100]
    return prompt[-50:]
