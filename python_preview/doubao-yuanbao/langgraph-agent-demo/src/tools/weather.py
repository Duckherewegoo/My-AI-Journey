from langchain_core.tools import tool


@tool
def get_weather(city: str) -> str:
    """
    查询指定城市的实时天气信息。
    参数:
        city: 城市名称，例如 "北京"、"上海"
    """
    # 模拟天气数据，实际使用可接入真实天气API
    mock_data = {
        "北京": "晴，26℃，湿度45%，南风3级",
        "上海": "多云，28℃，湿度62%，东风2级",
        "广州": "雷阵雨，32℃，湿度78%，无持续风向",
        "哈尔滨": "晴，22℃，湿度38%，北风4级"
    }
    return mock_data.get(city, f"暂无{city}的天气数据")
