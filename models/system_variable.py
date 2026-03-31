"""
系统变量数据模型

定义系统变量的数据结构（用于树形结构显示）
"""

from dataclasses import dataclass, field
from typing import Any, Optional, List


@dataclass
class SystemVariable:
    """系统变量数据模型（用于树形结构显示）"""
    
    # 变量路径
    path: str  # 例如: "AppVar.Result"
    
    # 变量名
    name: str
    
    # 变量值
    value: Any
    
    # 父节点路径
    parent_path: Optional[str] = None
    
    # 子节点
    children: List['SystemVariable'] = field(default_factory=list)
    
    def add_child(self, child: 'SystemVariable'):
        """
        添加子节点
        
        参数:
            child: 子节点
        """
        if child not in self.children:
            self.children.append(child)
            child.parent_path = self.path
    
    def remove_child(self, child: 'SystemVariable'):
        """
        移除子节点
        
        参数:
            child: 子节点
        """
        if child in self.children:
            self.children.remove(child)
            child.parent_path = None
    
    def find_child(self, name: str) -> Optional['SystemVariable']:
        """
        查找子节点
        
        参数:
            name: 子节点名称
            
        返回:
            SystemVariable: 找到的子节点，如果不存在则返回None
        """
        for child in self.children:
            if child.name == name:
                return child
        return None
    
    def get_full_path(self) -> str:
        """
        获取完整路径
        
        返回:
            str: 完整路径
        """
        return self.path
