import re
from pathlib import Path

def refactor_imports(target_dir: str, dry_run: bool = True):
    """
    遍历目标目录，将 from exceptions 或 from observability 
    批量修改为 from base.exceptions 或 from base.observability
    """
    root_path = Path(target_dir)
    if not root_path.exists() or not root_path.is_dir():
        print(f"❌ 错误：目录 '{target_dir}' 不存在或不是文件夹。")
        return

    # 正则解析：
    # \bfrom\s+ : 匹配 "from" 加上至少一个空格
    # (exceptions|observability) : 匹配这两个目标词
    # \b : 确保是完整的单词边界（防止匹配到 exceptions_test 这种情况）
    # (?!\s*\.) : 这是一个负向预查，确保它后面没有紧跟一个点（防止误伤 from exceptions.sub 这种，如果你需要连子模块一起改，可以去掉这个）
    pattern = re.compile(r'\bfrom\s+(exceptions|observability)\b')

    # 统计变量
    modified_files_count = 0
    total_replacements = 0

    print(f"🔍 开始扫描目录: {root_path.absolute()}")
    if dry_run:
        print("⚠️ 当前是 [预览模式]，不会实际修改文件。确认无误后请将 dry_run 设为 False。\n")

    # rglob("*.py") 会递归查找所有 .py 文件
    for py_file in root_path.rglob("*.py"):
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 执行替换：替换为 from base.模块名
            new_content, count = pattern.subn(r'from base.\1', content)

            if count > 0:
                print(f"📄 [{py_file.relative_to(root_path)}] 找到 {count} 处匹配")
                if not dry_run:
                    with open(py_file, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                modified_files_count += 1
                total_replacements += count

        except Exception as e:
            print(f"❌ 处理文件 {py_file} 时发生错误: {e}")

    print("\n" + "="*40)
    print(f"✅ 扫描完成！")
    print(f"共修改了 {modified_files_count} 个文件，替换了 {total_replacements} 处导入。")
    if dry_run:
        print("提示：确认无误后，请把脚本里的 dry_run 改成 False 再跑一次。")

if __name__ == "__main__":
    # 👇 这里填你要处理的目录，'.' 代表当前目录
    TARGET_DIRECTORY = "src" 
    
    # 👇 先设为 True 看预览，没问题再改成 False 实际修改
    DRY_RUN = False

    refactor_imports(TARGET_DIRECTORY, dry_run=DRY_RUN)
