from langchain_core.tools import tool
import pandas as pd
import os


@tool
def csv_analyzer(file_path: str, operation: str = "summary") -> str:
    """
    读取CSV文件并进行基础数据分析。
    参数:
        file_path: CSV文件的本地路径
        operation: 分析类型，可选 summary(概览统计) / columns(列名) / rows(行数)
    """
    if not os.path.exists(file_path):
        return f"错误：文件 {file_path} 不存在"

    try:
        df = pd.read_csv(file_path)
        if operation == "summary":
            return f"数据概览：\n{df.describe().to_string()}"
        elif operation == "columns":
            return f"列名列表：{', '.join(df.columns.tolist())}"
        elif operation == "rows":
            return f"数据总行数：{len(df)}，总列数：{len(df.columns)}"
        else:
            return f"不支持的操作类型：{operation}"
    except Exception as e:
        return f"CSV解析失败：{str(e)}"
