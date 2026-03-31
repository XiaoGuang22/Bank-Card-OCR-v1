"""
时间信息数据模型

定义时间相关信息的数据结构
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TimeInfo:
    """时间信息数据模型"""
    
    # 当前时间戳
    timestamp: datetime
    
    # 检测时间（毫秒）
    detection_time_ms: float
    
    # 触发频率（Hz）
    trigger_frequency_hz: float
    
    def format_timestamp(self) -> str:
        """
        格式化时间戳为 MM/DD/YYYY HH:MM:SS.mmm
        
        返回:
            str: 格式化的时间戳字符串
        """
        return self.timestamp.strftime("%m/%d/%Y %H:%M:%S.%f")[:-3]
    
    def __post_init__(self):
        """验证数据有效性"""
        if self.detection_time_ms < 0:
            raise ValueError(f"Invalid detection_time_ms: {self.detection_time_ms}. Must be non-negative")
        if self.trigger_frequency_hz < 0:
            raise ValueError(f"Invalid trigger_frequency_hz: {self.trigger_frequency_hz}. Must be non-negative")
