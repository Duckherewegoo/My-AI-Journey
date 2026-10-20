"""自动将项目中的日志调用迁移到 Loguru 标准风格。

规则：
1. 把 `extra={"k": v}` 转换为直接在日志方法中传 `k=v`。
2. 把 `logger.warning("msg %s", var)` 转换为 f-string 或 `{}` 占位符。
有一定缺陷，暴力正则会一定程度上导致一些模块的括号可能不匹配，并且居然会自己修改自己
"""

import re
from pathlib import Path

# 匹配 extra={...} 里的键值对，并提取出来
EXTRA_PATTERN = re.compile(r',\s*extra=\{([^}]+)\}')
# 匹配 logger.xxx("msg", extra={...}) 
LOG_WITH_EXTRA = re.compile(r'(logger\.(?:debug|info|warning|error|exception|critical)\([^,)]+)(,\s*extra=\{([^}]+)\})')

def fix_extra_kwargs(content: str) -> str:
    """将 extra={"k": v} 转换为 logger.xxx("msg", k=v)。"""
    
    def replacer(match):
        prefix = match.group(1)  # logger.warning("msg"
        extra_content = match.group(3)  # "k": v, "k2": v2
        
        # 将 {"k": v, "k2": v2} 转换为 k=v, k2=v2
        # 处理单引号和双引号
        pairs = re.findall(r'["\']([^"\']+)["\']\s*:\s*([^,}]+)', extra_content)
        if not pairs:
            return match.group(0)
            
        kwargs = ", ".join(f"{k}={v.strip()}" for k, v in pairs)
        return f"{prefix}, {kwargs})"
    
    return LOG_WITH_EXTRA.sub(replacer, content)


def fix_percent_format(content: str) -> str:
    """将 logger.xxx("msg %s", var) 转换为 logger.xxx("msg {}", var) (Loguru 风格)。"""
    # 这是一个简化的替换，只处理 %s 和 %d
    # 注意：不能误伤字符串内部的 %
    
    def replacer(match):
        return match.group(0).replace("%s", "{}").replace("%d", "{}")
    
    # 简单粗暴地把日志调用里的 %s 替换掉
    log_calls = re.compile(r'(logger\.(?:debug|info|warning|error|exception|critical)\([^)]+)')
    return log_calls.sub(replacer, content)


def process_file(path: Path):
    if any(part in path.parts for part in [".venv", "venv", "__pycache__", ".git"]):
        return
    
    content = path.read_text(encoding="utf-8")
    original = content
    
    # 1. 修复 extra={"k": v}
    content = fix_extra_kwargs(content)
    # 2. 修复 %s 占位符
    content = fix_percent_format(content)
    
    if content != original:
        path.write_text(content, encoding="utf-8")
        print(f"✅ 已修复: {path}")

if __name__ == "__main__":
    for path in Path(".").rglob("*.py"):
        process_file(path)
    print("🎉 修复完成！请手动检查并运行测试。")
