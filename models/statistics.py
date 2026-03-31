"""
统计数据模型

定义统计信息的数据结构
"""

from dataclasses import dataclass


@dataclass
class Statistics:
    """统计数据模型"""
    
    # 计数
    pass_count: int = 0
    reject_count: int = 0
    recycle_count: int = 0
    
    @property
    def total_count(self) -> int:
        """总数"""
        return self.pass_count + self.reject_count + self.recycle_count
    
    @property
    def pass_rate(self) -> float:
        """Pass率百分比"""
        if self.total_count == 0:
            return 0.0
        return (self.pass_count / self.total_count) * 100
    
    @property
    def reject_rate(self) -> float:
        """Reject率百分比"""
        if self.total_count == 0:
            return 0.0
        return (self.reject_count / self.total_count) * 100
    
    @property
    def recycle_rate(self) -> float:
        """Recycle率百分比"""
        if self.total_count == 0:
            return 0.0
        return (self.recycle_count / self.total_count) * 100
    
    def __post_init__(self):
        """验证数据有效性"""
        if self.pass_count < 0:
            raise ValueError(f"Invalid pass_count: {self.pass_count}. Must be non-negative")
        if self.reject_count < 0:
            raise ValueError(f"Invalid reject_count: {self.reject_count}. Must be non-negative")
        if self.recycle_count < 0:
            raise ValueError(f"Invalid recycle_count: {self.recycle_count}. Must be non-negative")
