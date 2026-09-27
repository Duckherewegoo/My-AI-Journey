"""
文件操作 Skill
==============
文件和目录操作的Skill。

提供安全的文件操作能力，包括：
- 文件读写
- 目录操作
- 文件搜索
- 文件信息查询
"""

import os
import glob
from typing import List
from pathlib import Path
from langchain_core.tools import StructuredTool

from ..base import BaseSkill


class FileSkill(BaseSkill):
    """
    文件操作Skill
    
    提供文件和目录的读写、查询、搜索等能力。
    带有工作目录限制，防止越权访问。
    """
    
    name = "file"
    description = "文件和目录操作能力，包括文件读写、目录浏览、文件搜索等"
    version = "1.0.0"
    author = "nano-harness"
    category = "system"
    tags = ["file", "directory", "io", "filesystem"]
    
    def __init__(self, work_dir: str = "."):
        super().__init__()
        self.work_dir = os.path.abspath(work_dir)
    
    def get_tools(self) -> List:
        return [
            StructuredTool.from_function(
                func=self.read_file,
                name="read_file",
                description="""读取文件内容。
                
                读取指定文件的文本内容。
                支持读取各种文本文件格式。
                
                参数：
                - file_path: 文件路径（相对于工作目录或绝对路径）
                """,
            ),
            StructuredTool.from_function(
                func=self.write_file,
                name="write_file",
                description="""写入文件内容。
                
                将内容写入指定文件。
                如果文件不存在会创建，如果存在会覆盖。
                
                参数：
                - file_path: 文件路径
                - content: 要写入的内容
                """,
            ),
            StructuredTool.from_function(
                func=self.list_directory,
                name="list_directory",
                description="""列出目录内容。
                
                显示指定目录下的文件和子目录。
                
                参数：
                - dir_path: 目录路径，默认为当前目录
                - show_hidden: 是否显示隐藏文件，默认False
                """,
            ),
            StructuredTool.from_function(
                func=self.search_files,
                name="search_files",
                description="""搜索文件。
                
                按文件名模式搜索文件。
                支持通配符，如 *.py, **/*.txt 等。
                
                参数：
                - pattern: 搜索模式
                - dir_path: 搜索起始目录，默认为当前目录
                """,
            ),
            StructuredTool.from_function(
                func=self.get_file_info,
                name="get_file_info",
                description="""获取文件信息。
                
                返回文件的详细信息，包括大小、修改时间等。
                
                参数：
                - file_path: 文件路径
                """,
            ),
            StructuredTool.from_function(
                func=self.create_directory,
                name="create_directory",
                description="""创建目录。
                
                创建新的目录，如果父目录不存在也会创建。
                
                参数：
                - dir_path: 目录路径
                """,
            ),
        ]
    
    # ===== 安全检查 =====
    
    def _safe_path(self, path: str) -> str:
        """
        安全路径检查
        
        确保路径在工作目录内，防止路径穿越攻击。
        """
        abs_path = os.path.abspath(path)
        
        # 如果是相对路径，加上工作目录
        if not os.path.isabs(path):
            abs_path = os.path.abspath(os.path.join(self.work_dir, path))
        
        # 检查是否在工作目录内
        if not abs_path.startswith(self.work_dir):
            raise ValueError(f"路径超出工作目录范围: {path}")
        
        return abs_path
    
    # ===== 工具实现 =====
    
    def read_file(self, file_path: str) -> str:
        """读取文件"""
        try:
            safe_path = self._safe_path(file_path)
            
            if not os.path.exists(safe_path):
                return f"❌ 文件不存在：{file_path}"
            
            if os.path.isdir(safe_path):
                return f"❌ 这是一个目录，不是文件：{file_path}"
            
            with open(safe_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            # 限制输出大小
            if len(content) > 10000:
                content = content[:10000] + f"\n\n... [文件已截断，共 {len(content)} 字符]"
            
            return f"【文件内容】{file_path}\n\n{content}"
            
        except ValueError as e:
            return f"❌ {str(e)}"
        except Exception as e:
            return f"❌ 读取文件失败：{str(e)}"
    
    def write_file(self, file_path: str, content: str) -> str:
        """写入文件"""
        try:
            safe_path = self._safe_path(file_path)
            
            # 确保父目录存在
            parent_dir = os.path.dirname(safe_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            
            with open(safe_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            size = len(content.encode('utf-8'))
            return f"✅ 文件写入成功：{file_path} ({size} 字节)"
            
        except ValueError as e:
            return f"❌ {str(e)}"
        except Exception as e:
            return f"❌ 写入文件失败：{str(e)}"
    
    def list_directory(self, dir_path: str = ".", show_hidden: bool = False) -> str:
        """列出目录内容"""
        try:
            safe_path = self._safe_path(dir_path)
            
            if not os.path.exists(safe_path):
                return f"❌ 目录不存在：{dir_path}"
            
            if not os.path.isdir(safe_path):
                return f"❌ 这不是一个目录：{dir_path}"
            
            entries = sorted(os.listdir(safe_path))
            
            if not show_hidden:
                entries = [e for e in entries if not e.startswith('.')]
            
            if not entries:
                return f"📂 目录为空：{dir_path}"
            
            lines = [f"📂 目录内容：{dir_path}"]
            lines.append("")
            
            dirs = []
            files = []
            
            for entry in entries:
                full_path = os.path.join(safe_path, entry)
                if os.path.isdir(full_path):
                    size = self._get_dir_size(full_path)
                    dirs.append(f"📁 {entry}/  ({size})")
                else:
                    size = self._format_size(os.path.getsize(full_path))
                    files.append(f"📄 {entry}  ({size})")
            
            if dirs:
                lines.append("【目录】")
                lines.extend(dirs)
                lines.append("")
            
            if files:
                lines.append("【文件】")
                lines.extend(files)
            
            lines.append("")
            lines.append(f"共 {len(entries)} 项")
            
            return "\n".join(lines)
            
        except ValueError as e:
            return f"❌ {str(e)}"
        except Exception as e:
            return f"❌ 列出目录失败：{str(e)}"
    
    def search_files(self, pattern: str, dir_path: str = ".") -> str:
        """搜索文件"""
        try:
            safe_path = self._safe_path(dir_path)
            
            search_pattern = os.path.join(safe_path, pattern)
            results = glob.glob(search_pattern, recursive=True)
            
            # 过滤掉目录，只保留文件
            results = [r for r in results if os.path.isfile(r)]
            
            # 转换为相对路径
            relative_results = []
            for r in results:
                rel = os.path.relpath(r, self.work_dir)
                relative_results.append(rel)
            
            if not relative_results:
                return f"🔍 没有找到匹配的文件：{pattern}"
            
            lines = [f"🔍 搜索结果：{pattern}"]
            lines.append(f"找到 {len(relative_results)} 个文件")
            lines.append("")
            
            for i, f in enumerate(sorted(relative_results)[:50], 1):
                lines.append(f"{i}. {f}")
            
            if len(relative_results) > 50:
                lines.append(f"... 还有 {len(relative_results) - 50} 个文件")
            
            return "\n".join(lines)
            
        except ValueError as e:
            return f"❌ {str(e)}"
        except Exception as e:
            return f"❌ 搜索文件失败：{str(e)}"
    
    def get_file_info(self, file_path: str) -> str:
        """获取文件信息"""
        try:
            safe_path = self._safe_path(file_path)
            
            if not os.path.exists(safe_path):
                return f"❌ 文件不存在：{file_path}"
            
            stat = os.stat(safe_path)
            
            import datetime
            
            lines = ["【文件信息】"]
            lines.append(f"路径：{file_path}")
            lines.append(f"类型：{'目录' if os.path.isdir(safe_path) else '文件'}")
            lines.append(f"大小：{self._format_size(stat.st_size)}")
            lines.append(f"创建时间：{datetime.datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"修改时间：{datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append(f"访问时间：{datetime.datetime.fromtimestamp(stat.st_atime).strftime('%Y-%m-%d %H:%M:%S')}")
            
            return "\n".join(lines)
            
        except ValueError as e:
            return f"❌ {str(e)}"
        except Exception as e:
            return f"❌ 获取文件信息失败：{str(e)}"
    
    def create_directory(self, dir_path: str) -> str:
        """创建目录"""
        try:
            safe_path = self._safe_path(dir_path)
            
            if os.path.exists(safe_path):
                if os.path.isdir(safe_path):
                    return f"ℹ️  目录已存在：{dir_path}"
                else:
                    return f"❌ 路径已存在但不是目录：{dir_path}"
            
            os.makedirs(safe_path, exist_ok=True)
            return f"✅ 目录创建成功：{dir_path}"
            
        except ValueError as e:
            return f"❌ {str(e)}"
        except Exception as e:
            return f"❌ 创建目录失败：{str(e)}"
    
    # ===== 辅助方法 =====
    
    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    
    def _get_dir_size(self, dir_path: str) -> str:
        """获取目录大小（粗略估算，只算第一层）"""
        try:
            total = 0
            count = 0
            for entry in os.scandir(dir_path):
                if entry.is_file():
                    total += entry.stat().st_size
                    count += 1
                elif entry.is_dir():
                    count += 1
            return f"{count}项, ~{self._format_size(total)}"
        except:
            return "?"
