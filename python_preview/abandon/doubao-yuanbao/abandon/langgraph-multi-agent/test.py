import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 加载环境变量
load_dotenv()

# 打印配置（只打前几位，防泄露）
api_key = os.getenv("DASHSCOPE_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL")
print(f"API Key 前缀: {api_key[:10]}...")
print(f"Base URL: {base_url}")

try:
    llm = ChatOpenAI(
        model="qwen-plus",
        api_key=api_key,
        base_url=base_url,
        timeout=30,
        temperature=0.7
    )
    res = llm.invoke("你好，请回复一句话测试")
    print("✅ API 调用成功！")
    print("返回内容：", res.content)
except Exception as e:
    print("❌ API 调用失败！")
    print("错误信息：", str(e))
