"""
相机信息数据模型 & 辅助函数

提供 CameraInfo 数据类（相机的 IP、端口、名称等）以及网段定位辅助函数。
TCP 局域网扫描功能（CameraDiscovery 类）已移除，目前仅通过 Sapera SDK 进行相机发现。
"""

import socket
from dataclasses import dataclass
from typing import Optional


# 默认扫描端口（与 config.py 中 TCP_SETTINGS 保持一致）
DEFAULT_CAMERA_PORT = 5024


@dataclass
class CameraInfo:
    """描述一台相机的基本信息"""
    ip: str
    port: int
    name: str = ""          # 相机自定义名称（从设备读取，读不到则留空）
    serial: str = ""        # 序列号
    model: str = ""         # 型号
    server_name: str = ""   # Sapera服务器名

    @property
    def display_name(self) -> str:
        """返回 'CAM-A (192.168.10.11)' 格式的显示名，若无名称则只显示 IP"""
        if self.name:
            return f"{self.name} ({self.ip})"
        else:
            return self.ip

    @property
    def target_object_str(self) -> str:
        """返回日志用的 'CAM-A@192.168.10.x' 格式"""
        label = self.name if self.name else self.ip
        return f"{label}@{self.ip}"

    def __eq__(self, other):
        if not isinstance(other, CameraInfo):
            return False
        return self.ip == other.ip and self.port == other.port

    def __hash__(self):
        return hash((self.ip, self.port))


def _find_camera_subnet_ip() -> str:
    """在所有本地私有网卡中找到相机所在网段的基准IP（排除上网网卡）"""
    ips = []
    try:
        for addr in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = addr[4][0]
            if ip.startswith("127."):
                continue
            if any(ip.startswith(p) for p in ("192.168.", "10.", "172.")):
                ips.append(ip)
    except Exception:
        pass

    default_subnet = ""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        default_subnet = s.getsockname()[0].rsplit(".", 1)[0] + "."
        s.close()
    except Exception:
        pass

    # 排除虚拟网卡常见网段 (VMware: 192.168.192.x, 192.168.40.x 等)
    VIRTUAL_PREFIXES = ("192.168.192.", "192.168.40.", "192.168.56.", "192.168.75.")
    for ip in ips:
        if not ip.startswith(default_subnet) and not any(ip.startswith(v) for v in VIRTUAL_PREFIXES):
            return ip.rsplit(".", 1)[0] + ".0"
    for ip in ips:
        if not any(ip.startswith(v) for v in VIRTUAL_PREFIXES):
            return ip.rsplit(".", 1)[0] + ".0"
    if ips:
        return ips[0].rsplit(".", 1)[0] + ".0"
    return ""
