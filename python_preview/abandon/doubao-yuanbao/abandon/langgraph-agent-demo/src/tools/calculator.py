from langchain_core.tools import tool
import numexpr


@tool
def calculator(expression: str) -> str:
    """
    安全数值计算器，支持加减乘除、括号、常见数学运算。
    参数:
        expression: 数学表达式字符串，例如 "23 * 45 + 128 / 4"
    """
    try:
        result = numexpr.evaluate(expression).item()
        return f"计算结果：{expression} = {result}"
    except Exception as e:
        return f"计算失败：{str(e)}"
