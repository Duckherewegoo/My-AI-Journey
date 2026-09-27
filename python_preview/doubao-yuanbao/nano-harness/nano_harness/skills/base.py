"""
Skill 基类
==========
所有Skill的基类，定义Skill的标准接口。

Skill是一组相关工具的集合，代表某一领域的能力。
每个Skill应该：
1. 有明确的名称和描述
2. 提供一组工具
3. 可以被动态加载和卸载
4. 可以被MCP协议暴露
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from langchain_core.tools import BaseTool


class BaseSkill(ABC):
    """
    Skill基类
    
    子类需要实现：
    - name: Skill名称
    - description: Skill描述
    - get_tools(): 返回工具列表
    
    可选实现：
    - version: 版本号
    - author: 作者
    - dependencies: 依赖的其他Skill
    - initialize(): 初始化钩子
    - cleanup(): 清理钩子
    """
    
    # 子类必须定义
    name: str = "base_skill"
    description: str = "基础Skill"
    
    # 可选元数据
    version: str = "0.1.0"
    author: str = ""
    category: str = "general"
    tags: List[str] = []
    
    # 依赖的其他Skill名称
    dependencies: List[str] = []
    
    # Skill状态
    _initialized: bool = False
    
    @abstractmethod
    def get_tools(self) -> List[BaseTool]:
        """
        返回该Skill提供的所有工具
        
        Returns:
            LangChain工具对象列表
        """
        pass
    
    def initialize(self, context: Optional[Dict] = None):
        """
        初始化钩子 - Skill被加载时调用
        
        可以在这里做一些初始化工作，比如加载模型、建立连接等。
        """
        self._initialized = True
    
    def cleanup(self):
        """
        清理钩子 - Skill被卸载时调用
        
        可以在这里做一些清理工作，比如关闭连接、释放资源等。
        """
        self._initialized = False
    
    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized
    
    def get_metadata(self) -> Dict[str, Any]:
        """获取Skill元数据"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "category": self.category,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "tool_count": len(self.get_tools()),
        }
    
    def __repr__(self) -> str:
        return f"<Skill {self.name} v{self.version}>"
