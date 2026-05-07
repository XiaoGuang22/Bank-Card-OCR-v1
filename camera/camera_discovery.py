"""
相机自动发现模块

扫描局域网内可用的相机，通过 TCP 探测指定端口（默认 5024）。
支持手动刷新和启动时自动扫描。
"""

import socket
import ipaddress
import threading
import struct
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Optional, Callable


# 默认扫描端口（与 config.py 中 TCP_SETTINGS 保持一致）
DEFAULT_CAMERA_PORT = 5024
# 每个 IP 的连接超时（毫秒）
PROBE_TIMEOUT_MS = 200
# 并发探测线程数
MAX_WORKERS = 64


@dataclass
class CameraInfo:
    """描述一台发现的相机"""
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
            return self.ip  # 无名称时只显示 IP，不重复

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


def _get_local_ips() -> set:
    """获取本机所有 IP 地址（用于扫描时排除自身）"""
    local_ips = {"127.0.0.1"}
    try:
        import socket as _socket
        hostname = _socket.gethostname()
        addrs = _socket.getaddrinfo(hostname, None, _socket.AF_INET)
        for addr in addrs:
            local_ips.add(addr[4][0])
    except Exception:
        pass
    return local_ips


def _get_local_network_ranges() -> List[str]:
    """
    获取本机所有活动网卡的网段（CIDR 格式，如 192.168.10.0/24）。
    跳过回环地址和虚拟网卡（Hyper-V、VPN 等产生的 198.18.x.x 等非真实局域网段）。
    """
    # 只扫描这些私有网段前缀，排除虚拟网卡
    PRIVATE_PREFIXES = ("192.168.", "10.", "172.")
    ranges = []
    try:
        import socket as _socket
        hostname = _socket.gethostname()
        addrs = _socket.getaddrinfo(hostname, None, _socket.AF_INET)
        seen = set()
        for addr in addrs:
            ip = addr[4][0]
            if ip.startswith("127.") or ip in seen:
                continue
            # 只保留真实私有网段
            if not any(ip.startswith(p) for p in PRIVATE_PREFIXES):
                continue
            seen.add(ip)
            network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
            ranges.append(str(network))
    except Exception:
        pass

    # 备用：通过 UDP 路由获取主网卡 IP
    if not ranges:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            # 备用路由也只保留私有网段
            if any(ip.startswith(p) for p in PRIVATE_PREFIXES):
                network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
                ranges.append(str(network))
        except Exception:
            pass

    return list(set(ranges))


def _probe_camera(ip: str, port: int, timeout_ms: int) -> Optional[CameraInfo]:
    """
    尝试 TCP 连接目标 IP:port，成功则返回 CameraInfo，失败返回 None。
    连接成功后尝试发送简单的厂商发现指令读取相机名称。
    """
    timeout_s = timeout_ms / 1000.0
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout_s)
            s.connect((ip, port))

            # 尝试读取相机标识（发送简单握手，读取响应）
            name = ""
            try:
                s.settimeout(0.1)
                # 发送一个简单的查询指令（厂商自定义协议，读不到也没关系）
                s.sendall(b"IDENTIFY\r\n")
                resp = s.recv(256).decode("utf-8", errors="ignore").strip()
                if resp:
                    name = resp.split("\n")[0][:32]  # 取第一行，最多32字符
            except Exception:
                pass

            return CameraInfo(ip=ip, port=port, name=name)
    except Exception:
        return None


def _find_camera_subnet_ip() -> str:
    """在所有本地私有网卡中找到相机所在网段的基准IP（排除上网网卡）"""
    import socket as _sk
    ips = []
    try:
        for addr in _sk.getaddrinfo(_sk.gethostname(), None, _sk.AF_INET):
            ip = addr[4][0]
            if ip.startswith("127."): continue
            if any(ip.startswith(p) for p in ("192.168.", "10.", "172.")):
                ips.append(ip)
    except Exception: pass
    default_subnet = ""
    try:
        s = _sk.socket(_sk.AF_INET, _sk.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        default_subnet = s.getsockname()[0].rsplit(".", 1)[0] + "."
        s.close()
    except Exception: pass
    for ip in ips:
        if not ip.startswith(default_subnet):
            return ip.rsplit(".", 1)[0] + ".0"
    if ips:
        return ips[0].rsplit(".", 1)[0] + ".0"
    return ""


class CameraDiscovery:
    """
    局域网相机扫描器。

    用法：
        discovery = CameraDiscovery(port=5024)
        discovery.scan(on_complete=lambda cameras: print(cameras))
    """

    def __init__(self, port: int = DEFAULT_CAMERA_PORT, timeout_ms: int = PROBE_TIMEOUT_MS):
        self.port = port
        self.timeout_ms = timeout_ms
        self._scanning = False
        self._lock = threading.Lock()
        self._last_results: List[CameraInfo] = []

    @property
    def is_scanning(self) -> bool:
        return self._scanning

    @property
    def last_results(self) -> List[CameraInfo]:
        return list(self._last_results)

    def scan(
        self,
        on_complete: Optional[Callable[[List[CameraInfo]], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
        blocking: bool = False,
    ):
        """
        扫描局域网内的相机。

        Args:
            on_complete: 扫描完成回调，参数为 List[CameraInfo]（按 IP 排序）
            on_progress: 进度回调，参数为 (已完成数, 总数)
            blocking: True 则阻塞等待扫描完成，False 则在后台线程运行
        """
        with self._lock:
            if self._scanning:
                return  # 已在扫描中，忽略重复请求
            self._scanning = True

        if blocking:
            self._do_scan(on_complete, on_progress)
        else:
            t = threading.Thread(
                target=self._do_scan,
                args=(on_complete, on_progress),
                daemon=True,
            )
            t.start()

    def _do_scan(
        self,
        on_complete: Optional[Callable],
        on_progress: Optional[Callable],
    ):
        try:
            ranges = _get_local_network_ranges()
            if not ranges:
                self._last_results = []
                if on_complete:
                    on_complete([])
                return

            # 收集所有待探测 IP（排除网络地址、广播地址和本机 IP）
            local_ips = _get_local_ips()
            all_ips = []
            for cidr in ranges:
                network = ipaddress.IPv4Network(cidr, strict=False)
                all_ips.extend(
                    str(host) for host in network.hosts()
                    if str(host) not in local_ips  # 排除本机 IP
                )
            all_ips = list(set(all_ips))
            total = len(all_ips)
            found: List[CameraInfo] = []
            completed = 0

            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(_probe_camera, ip, self.port, self.timeout_ms): ip
                    for ip in all_ips
                }
                for future in as_completed(futures):
                    result = future.result()
                    if result is not None:
                        found.append(result)
                    completed += 1
                    if on_progress:
                        on_progress(completed, total)

            # 按 IP 排序
            found.sort(key=lambda c: ipaddress.IPv4Address(c.ip))
            self._last_results = found

            if on_complete:
                on_complete(found)
        finally:
            with self._lock:
                self._scanning = False
