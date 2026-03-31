"""
UI 组件模块

包含所有用户界面相关的组件：
- SensorSettingsFrame: 传感器设置面板
- SolutionMakerFrame: 解决方案制作工具
- ScrollableFrame: 可滚动框架组件
"""

from .SensorSettingsFrame import SensorSettingsFrame
from .SolutionMakerFrame import SolutionMakerFrame
from .ScrollableFrame import ResponsiveScrollableFrame, BankCardTrainerApp

__all__ = [
    'SensorSettingsFrame',
    'SolutionMakerFrame',
    'ResponsiveScrollableFrame',
    'BankCardTrainerApp'
]
