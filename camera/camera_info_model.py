"""
相机信息模型

定义统一的相机信息数据结构，支持 Sapera SDK 和网络相机的标识信息。
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum


class CameraConnectionStatus(Enum):
    """相机连接状态枚举"""
    DISCONNECTED = "disconnected"    # 红色 - 未连接
    CONNECTING = "connecting"        # 黄色闪烁 - 连接中
    SCANNING = "scanning"           # 黄色闪烁 - 扫描中
    CONNECTED = "connected"         # 绿色 - 已连接
    ERROR = "error"                 # 红色 - 连接失败


@dataclass
class EnhancedCameraInfo:
    """
    增强的相机信息模型
    
    支持 Sapera SDK 和网络相机的完整标识信息，
    符合需求文档中的相机标识规范。
    """
    
    # 基础标识信息
    device_user_id: str = ""        # 用户自定义名称 (DeviceUserID)
    device_serial_number: str = ""  # 序列号 (DeviceSerialNumber) - 唯一标识
    device_model_name: str = ""     # 型号 (DeviceModelName)
    current_ip_address: str = ""    # 当前IP地址 (GevCurrentIPAddress)
    
    # Sapera SDK 特有信息
    server_name: str = ""           # Sapera 服务器名称
    server_index: int = -1          # 服务器索引
    resource_count: int = 0         # 资源数量
    is_accessible: bool = False     # 是否可访问
    
    # 网络相机信息（兼容现有系统）
    port: int = 5024               # TCP 端口
    
    # 设备详细信息
    device_vendor_name: str = ""    # 厂商名称
    device_version: str = ""        # 设备版本
    pixel_formats: list = None      # 支持的像素格式
    available_features: list = None # 可用特征列表
    
    # 连接状态
    connection_status: CameraConnectionStatus = CameraConnectionStatus.DISCONNECTED
    
    def __post_init__(self):
        """初始化后处理"""
        if self.pixel_formats is None:
            self.pixel_formats = []
        if self.available_features is None:
            self.available_features = []
    
    @property
    def display_name(self) -> str:
        """
        显示名称，格式：用户自定义名(IP) 或 型号(IP)
        
        按需求文档 FC-05 的格式要求
        """
        name = self.device_user_id or self.device_model_name or "未知设备"
        ip = self.current_ip_address or "未知IP"
        return f"{name} ({ip})"
    
    @property
    def unique_identifier(self) -> str:
        """
        唯一标识符，优先使用序列号
        
        用于方案文件关联和日志记录
        """
        return self.device_serial_number or self.server_name or self.current_ip_address
    
    @property
    def log_target_object(self) -> str:
        """
        日志记录格式：用户自定义名(序列号)@IP
        
        按需求文档日志规范要求
        """
        name = self.device_user_id or self.device_model_name or "未知设备"
        serial = f"({self.device_serial_number})" if self.device_serial_number else ""
        ip = self.current_ip_address or "未知IP"
        return f"{name}{serial}@{ip}"
    
    @property
    def is_sapera_camera(self) -> bool:
        """是否为 Sapera SDK 相机"""
        return bool(self.server_name)
    
    @property
    def is_network_camera(self) -> bool:
        """是否为网络相机"""
        return bool(self.current_ip_address and not self.server_name)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于方案文件保存）"""
        return {
            "device_user_id": self.device_user_id,
            "device_serial_number": self.device_serial_number,
            "device_model_name": self.device_model_name,
            "current_ip_address": self.current_ip_address,
            "server_name": self.server_name,
            "port": self.port,
            "device_vendor_name": self.device_vendor_name,
            "device_version": self.device_version,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EnhancedCameraInfo':
        """从字典创建实例（用于方案文件加载）"""
        return cls(
            device_user_id=data.get("device_user_id", ""),
            device_serial_number=data.get("device_serial_number", ""),
            device_model_name=data.get("device_model_name", ""),
            current_ip_address=data.get("current_ip_address", ""),
            server_name=data.get("server_name", ""),
            port=data.get("port", 5024),
            device_vendor_name=data.get("device_vendor_name", ""),
            device_version=data.get("device_version", ""),
        )
    
    @classmethod
    def from_sapera_info(cls, sapera_info) -> 'EnhancedCameraInfo':
        """从现有的 SaperaCameraInfo 创建实例"""
        device_info = sapera_info.device_info or {}
        
        return cls(
            device_user_id=device_info.get("user_id", ""),
            device_serial_number=device_info.get("serial", ""),
            device_model_name=device_info.get("model", ""),
            current_ip_address=device_info.get("ip_address", ""),
            server_name=sapera_info.server_name,
            server_index=sapera_info.server_index,
            resource_count=sapera_info.resource_count,
            is_accessible=sapera_info.is_accessible,
            device_vendor_name=device_info.get("vendor", ""),
            device_version=device_info.get("version", ""),
            pixel_formats=device_info.get("pixel_formats", []),
            available_features=device_info.get("features", []),
        )
    
    @classmethod
    def from_network_camera(cls, ip: str, port: int = 5024, name: str = "") -> 'EnhancedCameraInfo':
        """从网络相机信息创建实例"""
        return cls(
            device_user_id=name,
            current_ip_address=ip,
            port=port,
            device_model_name="网络相机",
        )
    
    def __eq__(self, other):
        """相等比较，优先使用序列号，其次使用服务器名或IP"""
        if not isinstance(other, EnhancedCameraInfo):
            return False
        
        # 优先比较序列号
        if self.device_serial_number and other.device_serial_number:
            return self.device_serial_number == other.device_serial_number
        
        # 其次比较 Sapera 服务器名
        if self.server_name and other.server_name:
            return self.server_name == other.server_name
        
        # 最后比较 IP 地址
        if self.current_ip_address and other.current_ip_address:
            return (self.current_ip_address == other.current_ip_address and 
                   self.port == other.port)
        
        return False
    
    def __hash__(self):
        """哈希值，用于集合操作"""
        if self.device_serial_number:
            return hash(self.device_serial_number)
        elif self.server_name:
            return hash(self.server_name)
        else:
            return hash((self.current_ip_address, self.port))
    
    def __str__(self):
        """字符串表示"""
        return self.display_name
    
    def __repr__(self):
        """调试表示"""
        return (f"EnhancedCameraInfo(display_name='{self.display_name}', "
                f"serial='{self.device_serial_number}', "
                f"server='{self.server_name}', "
                f"ip='{self.current_ip_address}')")


# 兼容性别名，保持与现有代码的兼容
CameraInfo = EnhancedCameraInfo