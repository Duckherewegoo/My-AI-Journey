import ahocorasick
from pathlib import Path
from typing import Tuple


def build_sensitive_automaton(vocab_dir: str) -> ahocorasick.Automaton:
    """
    遍历目录下所有txt词库，构建AC自动机
    :param vocab_dir: 词库目录路径，如 "./docs/Vocabulary"
    """
    automaton = ahocorasick.Automaton()
    # 用set自动去重，避免不同文件出现重复词条
    all_words = set()

    vocab_path = Path(vocab_dir)
    # 遍历目录下所有 .txt 文件（不递归子目录）
    # 如果要递归子目录，改成 vocab_path.rglob("*.txt")
    for txt_file in vocab_path.glob("*.txt"):
        try:
            with open(txt_file, "r", encoding="utf-8") as f:
                for line in f:
                    word = line.strip()
                    # 跳过空行
                    if word:
                        all_words.add(word)
        except UnicodeDecodeError:
            # 遇到非utf-8编码的文件，可按需处理，这里跳过并提示
            print(f"警告：文件 {txt_file.name} 编码非utf-8，已跳过")
            continue

    # 批量注册到自动机
    for word in all_words:
        automaton.add_word(word, word)

    # 构建失败指针，完成初始化（仅执行一次）
    automaton.make_automaton()
    print(
        f"词库加载完成：共加载 {len(all_words)} 个敏感词，来自 {len(list(vocab_path.glob('*.txt')))} 个文件")
    return automaton


# ======================
# 程序启动时执行一次，全局复用
# 路径根据你的项目根目录位置调整
SENSITIVE_AC = build_sensitive_automaton("../docs/Vocabulary")
# ======================


def moderate_content(content: str) -> Tuple[bool, str]:
    """内容安全审核，找到第一个匹配就返回"""
    for _, word in SENSITIVE_AC.iter(content):
        return False, f"包含敏感内容：{word}"
    return True, ""
