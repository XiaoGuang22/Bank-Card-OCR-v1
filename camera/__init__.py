"""
相机控制模块

包含 Teledyne DALSA Genie 相机的驱动和控制代码：
- GenieCameraTriggerOptimized: 优化的相机触发控制类
- SaperaCameraDiscovery: Sapera SDK 相机发现
- SaperaCameraManager: Sapera 相机切换管理
- CameraInfo: 增强的相机信息模型
"""

from .GenieCameraTriggerOptimized import GenieLiveCamera
from .sapera_camera_discovery import (
    SaperaCameraDiscovery, 
    SaperaCameraController, 
    SaperaCameraInfo,
    get_sapera_discovery,
    get_sapera_controller
)
from .sapera_camera_manager import (
    SaperaCameraManager,
    get_sapera_camera_manager
)
from .camera_info_model import (
    EnhancedCameraInfo,
    CameraInfo,
    CameraConnectionStatus
)

__all__ = [
    'GenieLiveCamera',
    'SaperaCameraDiscovery',
    'SaperaCameraController', 
    'SaperaCameraInfo',
    'SaperaCameraManager',
    'EnhancedCameraInfo',
    'CameraInfo',
    'CameraConnectionStatus',
    'get_sapera_discovery',
    'get_sapera_controller',
    'get_sapera_camera_manager'
]
