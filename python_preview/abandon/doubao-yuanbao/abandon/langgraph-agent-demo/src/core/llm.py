from openai import OpenAI
import os


def create_llm():
    try:
        client = OpenAI(
            api_key=os.getenv("SILI_API_KEY"),
            base_url="https://api.siliconflow.cn/v1"
        )

        llm = client.chat.completions.create(
            model="Pro/zai-org/GLM-4.7",
            messages=[
                {"role": "user", "content": "你好，请介绍一下你自己"}
            ]
        )

        return llm

    except Exception as e:
        return f"llm is not working as expected: {str(e)}"


if "__name__" == "__main__":
    create_llm()
