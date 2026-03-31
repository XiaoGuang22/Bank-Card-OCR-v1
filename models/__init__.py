"""
数据模型模块

包含Card-OCR运行界面的核心数据模型类
"""

from .recognition_result import RecognitionResult
from .statistics import Statistics
from .time_info import TimeInfo
from .system_variable import SystemVariable

__all__ = [
    'RecognitionResult',
    'Statistics',
    'TimeInfo',
    'SystemVariable'
]
