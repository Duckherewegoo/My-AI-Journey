"""Prompt 模板库。使用 string.Template，$var 语法。"""
from string import Template

INTENT_PROMPT = Template("...")
PLANNER_PROMPT = Template("...")
NODE_REFINE_PROMPT = Template("...")
EXECUTE_NODE_PROMPT = Template("...")
