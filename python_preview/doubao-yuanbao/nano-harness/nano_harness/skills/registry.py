"""
Skill 注册中心
==============
管理所有已注册的Skill，提供统一的工具发现和调用接口。

核心功能：
- Skill的注册与注销
- 工具的统一发现
- 按类别/标签筛选Skill
- 依赖检查与自动加载
- 动态热插拔
"""

from typing import Dict, List, Optional, Set
from langchain_core.tools import BaseTool

from .base import BaseSkill


class SkillRegistry:
    """
    Skill注册中心
    
    这是整个系统的能力管理中心，所有Skill都在这里注册和管理。
    Agent通过注册中心获取可用工具。
    
    高级特性：
    - 分类管理：按类别组织Skill
    - 标签筛选：按标签快速查找
    - 依赖解析：自动加载依赖的Skill
    - 热插拔：运行时动态增删Skill
    - 工具去重：同名工具自动处理
    """
    
    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}
        self._tool_cache: Optional[List[BaseTool]] = None
        self._cache_dirty: bool = True
    
    # ===== Skill 管理 =====
    
    def register(self, skill: BaseSkill) -> bool:
        """
        注册一个Skill
        
        Args:
            skill: Skill对象
        
        Returns:
            是否注册成功
        """
        if skill.name in self._skills:
            print(f"Warning: Skill '{skill.name}' already registered, overwriting.")
        
        # 检查依赖
        missing_deps = self._check_dependencies(skill)
        if missing_deps:
            print(f"Warning: Skill '{skill.name}' has missing dependencies: {missing_deps}")
        
        # 初始化Skill
        if not skill.is_initialized:
            skill.initialize()
        
        self._skills[skill.name] = skill
        self._cache_dirty = True
        return True
    
    def unregister(self, skill_name: str) -> bool:
        """
        注销一个Skill
        
        Args:
            skill_name: Skill名称
        
        Returns:
            是否注销成功
        """
        if skill_name not in self._skills:
            return False
        
        skill = self._skills[skill_name]
        
        # 检查是否有其他Skill依赖它
        dependents = self._get_dependents(skill_name)
        if dependents:
            print(f"Warning: Skills {dependents} depend on '{skill_name}', they may break.")
        
        # 清理
        skill.cleanup()
        del self._skills[skill_name]
        self._cache_dirty = True
        return True
    
    def get_skill(self, name: str) -> Optional[BaseSkill]:
        """获取指定Skill"""
        return self._skills.get(name)
    
    def list_skills(self) -> List[BaseSkill]:
        """列出所有已注册的Skill"""
        return list(self._skills.values())
    
    def get_skill_names(self) -> List[str]:
        """获取所有Skill名称"""
        return list(self._skills.keys())
    
    # ===== 工具管理 =====
    
    def get_all_tools(self) -> List[BaseTool]:
        """
        获取所有已注册Skill的所有工具
        
        这是Agent获取工具的主要入口。
        使用缓存提高性能，只有Skill变化时才重新构建。
        """
        if self._cache_dirty or self._tool_cache is None:
            self._rebuild_tool_cache()
        return self._tool_cache.copy()
    
    def get_tools_by_skill(self, skill_name: str) -> List[BaseTool]:
        """获取指定Skill的工具"""
        skill = self._skills.get(skill_name)
        if not skill:
            return []
        return skill.get_tools()
    
    def get_tool_by_name(self, tool_name: str) -> Optional[BaseTool]:
        """按名称查找工具"""
        for tool in self.get_all_tools():
            if tool.name == tool_name:
                return tool
        return None
    
    def _rebuild_tool_cache(self):
        """重建工具缓存"""
        tools = []
        seen_names: Set[str] = set()
        
        for skill in self._skills.values():
            for tool in skill.get_tools():
                # 处理重名工具
                if tool.name in seen_names:
                    # 加前缀避免冲突
                    original_name = tool.name
                    tool.name = f"{skill.name}_{original_name}"
                    print(f"Warning: Tool name '{original_name}' conflicts, renamed to '{tool.name}'")
                
                tools.append(tool)
                seen_names.add(tool.name)
        
        self._tool_cache = tools
        self._cache_dirty = False
    
    # ===== 筛选与搜索 =====
    
    def search_skills_by_category(self, category: str) -> List[BaseSkill]:
        """按类别搜索Skill"""
        return [
            s for s in self._skills.values()
            if s.category == category
        ]
    
    def search_skills_by_tag(self, tag: str) -> List[BaseSkill]:
        """按标签搜索Skill"""
        return [
            s for s in self._skills.values()
            if tag in s.tags
        ]
    
    def search_skills(self, query: str) -> List[BaseSkill]:
        """
        搜索Skill
        
        在名称、描述、标签中搜索匹配的Skill。
        """
        query = query.lower()
        results = []
        
        for skill in self._skills.values():
            if (
                query in skill.name.lower()
                or query in skill.description.lower()
                or any(query in tag.lower() for tag in skill.tags)
            ):
                results.append(skill)
        
        return results
    
    # ===== 依赖管理 =====
    
    def _check_dependencies(self, skill: BaseSkill) -> List[str]:
        """检查Skill的依赖是否满足"""
        missing = []
        for dep in skill.dependencies:
            if dep not in self._skills:
                missing.append(dep)
        return missing
    
    def _get_dependents(self, skill_name: str) -> List[str]:
        """获取依赖于指定Skill的所有Skill名称"""
        dependents = []
        for name, skill in self._skills.items():
            if skill_name in skill.dependencies:
                dependents.append(name)
        return dependents
    
    # ===== 统计信息 =====
    
    def get_stats(self) -> Dict:
        """获取注册中心统计信息"""
        return {
            "total_skills": len(self._skills),
            "total_tools": len(self.get_all_tools()),
            "categories": list(set(s.category for s in self._skills.values())),
            "skills": [s.get_metadata() for s in self._skills.values()],
        }
    
    def __len__(self) -> int:
        return len(self._skills)
    
    def __contains__(self, name: str) -> bool:
        return name in self._skills
