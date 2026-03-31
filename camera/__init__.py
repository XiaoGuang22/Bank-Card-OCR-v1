"""
相机控制模块

包含 Teledyne DALSA Genie 相机的驱动和控制代码：
- GenieCameraTriggerOptimized: 优化的相机触发控制类
"""

from .GenieCameraTriggerOptimized import GenieLiveCamera

__all__ = ['GenieLiveCamera']
