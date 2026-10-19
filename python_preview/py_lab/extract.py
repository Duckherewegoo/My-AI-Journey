import os
import re
from pathlib import Path

# ====== 配置区：按你的喜好调整 ======
OUTPUT_FILE = "code_summary.txt"
EXCLUDE_DIRS = {".git", ".venv", "venv", "__pycache__", "abandon", "node_modules", "tests"}
# 是否去掉以 # 开头的纯注释行和空行（保留 Docstrings）
REMOVE_COMMENTS = True 
# ===================================

def clean_line(line: str) -> str:
    """过滤掉纯空行和废话注释"""
    stripped = line.strip()
    if not stripped:
        return ""
    if REMOVE_COMMENTS:
        # 跳过纯单行注释（保留 Docstrings，因为它在三引号里）
        if stripped.startswith("#"):
            return ""
        # 跳过明显的分割线注释
        if re.match(r"^[#\-=*_]{3,}$", stripped):
            return ""
    return line.rstrip()

def extract_code():
    root = Path.cwd()
    output_path = root / OUTPUT_FILE
    
    total_files = 0
    total_lines = 0

    with open(output_path, "w", encoding="utf-8") as out:
        for path in root.rglob("*.py"):
            # 排除不需要的目录
            if any(part in EXCLUDE_DIRS for part in path.parts):
                continue
            
            rel_path = path.relative_to(root)
            out.write(f"\n{'='*60}\n")
            out.write(f"FILE: {rel_path}\n")
            out.write(f"{'='*60}\n")

            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.readlines()
                    
                # 过滤并写入
                file_lines = 0
                for line in content:
                    cleaned = clean_line(line)
                    if cleaned:
                        out.write(cleaned + "\n")
                        file_lines += 1
                
                total_files += 1
                total_lines += file_lines
                print(f"已提取: {rel_path} ({file_lines} 行)")

            except Exception as e:
                print(f"❌ 读取失败: {rel_path} - {e}")

    print(f"\n✨ 汇总完成！共提取 {total_files} 个文件，{total_lines} 行核心代码。")
    print(f"📄 输出文件: {output_path}")

if __name__ == "__main__":
    extract_code()
