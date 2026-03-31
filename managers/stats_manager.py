"""
统计管理器

负责管理统计数据（Pass/Reject/Recycle 计数和百分比）
"""

from models.statistics import Statistics


class StatsManager:
    """统计管理器类
    
    管理统计数据，提供计数增加、获取统计信息和重置功能。
    
    验证需求: 11.4, 11.5
    """
    
    def __init__(self):
        """初始化统计管理器"""
        self._statistics = Statistics()
    
    def increment_pass(self):
        """Pass 计数加1
        
        增加Pass计数，用于记录识别成功的卡片数量。
        """
        self._statistics = Statistics(
            pass_count=self._statistics.pass_count + 1,
            reject_count=self._statistics.reject_count,
            recycle_count=self._statistics.recycle_count
        )
    
    def increment_reject(self):
        """Reject 计数加1
        
        增加Reject计数，用于记录识别失败的卡片数量。
        """
        self._statistics = Statistics(
            pass_count=self._statistics.pass_count,
            reject_count=self._statistics.reject_count + 1,
            recycle_count=self._statistics.recycle_count
        )
    
    def increment_recycle(self):
        """Recycle 计数加1
        
        增加Recycle计数，用于记录需要重新处理的卡片数量。
        """
        self._statistics = Statistics(
            pass_count=self._statistics.pass_count,
            reject_count=self._statistics.reject_count,
            recycle_count=self._statistics.recycle_count + 1
        )
    
    def reset(self):
        """重置所有统计数据
        
        将Pass、Reject、Recycle计数全部清零。
        """
        self._statistics = Statistics()
    
    def get_statistics(self):
        """获取统计数据
        
        返回包含所有统计信息的字典，包括计数和百分比。
        
        返回:
            dict: 统计数据字典，包含以下键：
                - pass: Pass数量 (int)
                - reject: Reject数量 (int)
                - recycle: Recycle数量 (int)
                - total: 总处理数量 (int)
                - pass_rate: Pass率百分比 (float)
                - reject_rate: Reject率百分比 (float)
                - recycle_rate: Recycle率百分比 (float)
        """
        return {
            "pass": self._statistics.pass_count,
            "reject": self._statistics.reject_count,
            "recycle": self._statistics.recycle_count,
            "total": self._statistics.total_count,
            "pass_rate": self._statistics.pass_rate,
            "reject_rate": self._statistics.reject_rate,
            "recycle_rate": self._statistics.recycle_rate
        }
