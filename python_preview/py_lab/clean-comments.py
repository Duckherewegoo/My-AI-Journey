import re
from pathlib import Path

def clean_comments(file_path):
    content = file_path.read_text(encoding="utf-8")
    original = content

    # 1. 删掉 "# " 或 "# "
    content = re.sub(r"#\s*✅\s*严谨鲁棒[:：]\s*", "# ", content)
    
    # 2. 删掉注释里其他的 "# "
    content = re.sub(r"#\s*✅\s*", "# ", content)

    # 3. 删掉字符串或日志里的 ""
    content = content.replace("", "")
    
    # 4. 清理多余的空格
    content = re.sub(r"#\s{2,}", "# ", content)

    if content != original:
        file_path.write_text(content, encoding="utf-8")
        print(f"已清理: {file_path}")

if __name__ == "__main__":
    for path in Path(".").rglob("*.py"):
        if any(part in path.parts for part in [".venv", "venv", "__pycache__", "abandon", ".git"]):
            continue
        clean_comments(path)
    print("清理完成！")
