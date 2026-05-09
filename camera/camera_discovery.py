"""
相机自动发现模块

扫描局域网内可用的相机，通过 TCP 探测指定端口（默认 5024）以及 Sapera SDK。
支持手动刷新和启动时自动扫描。
"""

import socket
import ipaddress
import threading
import struct
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Optional, Callable


# 默认扫描端口（与 config.py 中 TCP_SETTINGS 保持一致）
DEFAULT_CAMERA_PORT = 5024
# 每个 IP 的连接超时（毫秒）
PROBE_TIMEOUT_MS = 200
# 并发探测线程数
MAX_WORKERS = 64

# Sapera SDK DLL 路径
SAPERA_DLL_PATH = r"C:\Program Files\Teledyne DALSA\Sapera\Components\NET\Bin\DALSA.SaperaLT.SapClassBasic.dll"


@dataclass
class CameraInfo:
    """描述一台发现的相机"""
    ip: str
    port: int
    name: str = ""          # 相机自定义名称（从设备读取，读不到则留空）
    serial: str = ""        # 序列号
    model: str = ""         # 型号
    server_name: str = ""   # Sapera 服务器名称（仅 Sapera 相机有效）
    source: str = "tcp"     # 发现来源: "tcp" 或 "sapera"

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


# Sapera 相机缓存（由主线程 init_sapera_sdk 填充，避免后台线程 CLR 调用失败）
_sapera_camera_cache: List[CameraInfo] = []
_sapera_cache_initialized = False


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
            # --- TCP 扫描 ---
            ranges = _get_local_network_ranges()
            tcp_found: List[CameraInfo] = []

            if ranges:
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
                completed = 0

                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = {
                        executor.submit(_probe_camera, ip, self.port, self.timeout_ms): ip
                        for ip in all_ips
                    }
                    for future in as_completed(futures):
                        result = future.result()
                        if result is not None:
                            tcp_found.append(result)
                        completed += 1
                        if on_progress:
                            on_progress(completed, total)

            # --- Sapera SDK 枚举 ---
            print("[CameraDiscovery] 开始 Sapera SDK 枚举...")
            sapera_found = _discover_sapera_cameras()
            print(f"[CameraDiscovery] Sapera枚举结果: {len(sapera_found)} 台")

            # 合并结果（去重：Sapera 优先，TCP 补充）
            found = _merge_camera_lists(sapera_found, tcp_found)

            # 按 IP 排序
            found.sort(key=lambda c: ipaddress.IPv4Address(c.ip))
            self._last_results = found

            if on_complete:
                on_complete(found)
        finally:
            with self._lock:
                self._scanning = False


# ==============================================================================
# Sapera SDK 相机枚举
# ==============================================================================

def _is_sapera_available() -> bool:
    """检查 Sapera SDK 是否可用"""
    return os.path.exists(SAPERA_DLL_PATH)


def _parse_sapera_ip(raw_value) -> str:
    """
    解析 Sapera SDK 返回的 IP 地址值。
    
    Sapera 可能返回多种格式：
    - 整数（如 3232238446 = 192.168.11.110）
    - 字符串（如 "192.168.11.110"）
    - 元组（如 (True, 3232238446)）
    """
    # 处理元组
    if isinstance(raw_value, tuple):
        # 取最后一个数值元素
        for item in reversed(raw_value):
            if isinstance(item, (int, float)):
                raw_value = item
                break
        else:
            return str(raw_value)
    
    # 处理整数（转换为 IP 地址）
    if isinstance(raw_value, (int, float)):
        raw_value = int(raw_value)
        # 32位无符号整数 → IP 地址
        return "{}.{}.{}.{}".format(
            (raw_value >> 24) & 0xFF,
            (raw_value >> 16) & 0xFF,
            (raw_value >> 8) & 0xFF,
            raw_value & 0xFF,
        )
    
    # 字符串直接返回
    return str(raw_value).strip()


def _parse_sapera_feature_value(raw_value) -> str:
    """
    通用 Sapera 特征值解析。
    处理 pythonnet 可能返回的元组包装格式。
    """
    if isinstance(raw_value, tuple):
        # 提取第一个字符串类型的值
        for item in raw_value:
            s = str(item).strip()
            if s and s != "True" and s != "False":
                return s
        return str(raw_value[0]).strip() if raw_value else ""
    return str(raw_value).strip()


def _discover_sapera_cameras() -> List[CameraInfo]:
    """
    通过 Sapera SDK 枚举 Genie / GigE Vision 相机。
    
    由于 pythonnet CLR 对象必须在主线程操作，此函数优先使用缓存。
    缓存由 initialize_sapera_cache() 在主线程填充。
    """
    global _sapera_cache_initialized
    if _sapera_cache_initialized:
        return list(_sapera_camera_cache)

    if not _is_sapera_available():
        return []

    # 备用：直接枚举（仅在主线程调用时可用）
    return _do_sapera_enumeration()


def initialize_sapera_cache():
    """
    在主线程初始化时调用，枚举所有 Sapera 相机并缓存。
    必须在 Sapera SDK 已加载（init_sapera_sdk）之后调用。
    """
    global _sapera_camera_cache, _sapera_cache_initialized
    if _sapera_cache_initialized:
        return _sapera_camera_cache

    if not _is_sapera_available():
        _sapera_cache_initialized = True
        return []

    _sapera_camera_cache = _do_sapera_enumeration()
    _sapera_cache_initialized = True
    print(f"[CameraDiscovery] Sapera缓存初始化完成，共 {len(_sapera_camera_cache)} 台相机")
    return _sapera_camera_cache


def set_sapera_cache(cameras: List[CameraInfo]):
    """
    由外部（InspectMainWindow.init_sapera_sdk）直接设置缓存。
    用于避免 pythonnet 类型重复导入问题。
    """
    global _sapera_camera_cache, _sapera_cache_initialized
    _sapera_camera_cache = list(cameras)
    _sapera_cache_initialized = True
    print(f"[CameraDiscovery] Sapera缓存已设置，共 {len(_sapera_camera_cache)} 台相机")


def _do_sapera_enumeration() -> List[CameraInfo]:
    """
    实际执行 Sapera SDK 相机枚举（必须在主线程调用）。
    """
    if not _is_sapera_available():
        return []

    try:
        import clr
        try:
            clr.AddReference(SAPERA_DLL_PATH)
        except Exception:
            pass

        from DALSA.SaperaLT.SapClassBasic import SapLocation, SapAcqDevice, SapManager

        cameras = []
        server_count = 0
        try:
            server_count = SapManager.GetServerCount()
            print(f"[CameraDiscovery] Sapera 服务器数量: {server_count}")
        except Exception as e:
            print(f"[CameraDiscovery] 获取服务器列表失败: {e}")
            return []

        for i in range(server_count):
            server_name = SapManager.GetServerName(i)
            print(f"[CameraDiscovery]   服务器[{i}]: {server_name}")

            if server_name.startswith("System_"):
                continue

            try:
                loc = SapLocation(server_name, 0)
                dev = SapAcqDevice(loc, False)
                if not dev.Create():
                    print(f"[CameraDiscovery]   {server_name}: Create() 返回 False")
                    try:
                        dev.Destroy()
                    except Exception:
                        pass
                    continue

                ip = ""
                try:
                    if dev.IsFeatureAvailable("GevCurrentIPAddress"):
                        raw = dev.GetFeatureValue("GevCurrentIPAddress")
                        ip = _parse_sapera_ip(raw)
                except Exception as ex:
                    print(f"[CameraDiscovery]   {server_name}: 获取IP失败 - {ex}")

                model = ""
                try:
                    if dev.IsFeatureAvailable("DeviceModelName"):
                        model = _parse_sapera_feature_value(dev.GetFeatureValue("DeviceModelName"))
                except Exception:
                    pass

                serial = ""
                try:
                    if dev.IsFeatureAvailable("DeviceSerialNumber"):
                        serial = _parse_sapera_feature_value(dev.GetFeatureValue("DeviceSerialNumber"))
                except Exception:
                    pass

                dev.Destroy()

                print(f"[CameraDiscovery]   ✅ 发现: {server_name} @ {ip}")

                cameras.append(CameraInfo(
                    ip=ip if ip else server_name,
                    port=DEFAULT_CAMERA_PORT,
                    name=server_name,
                    serial=serial,
                    model=model,
                    server_name=server_name,
                    source="sapera",
                ))

            except Exception as ex:
                print(f"[CameraDiscovery]   {server_name}: 枚举失败 - {ex}")
                continue

        print(f"[CameraDiscovery] Sapera枚举完成，共发现 {len(cameras)} 台相机")
        return cameras

    except Exception as e:
        print(f"[CameraDiscovery] Sapera枚举异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return []


def _merge_camera_lists(
    sapera_cameras: List[CameraInfo],
    tcp_cameras: List[CameraInfo],
) -> List[CameraInfo]:
    """
    合并 Sapera 和 TCP 发现的相机列表。
    规则：以 IP 为 key 去重，Sapera 相机优先（保留更丰富的信息），
    TCP 发现的相机作为补充。
    """
    merged = {c.ip: c for c in sapera_cameras}

    for cam in tcp_cameras:
        if cam.ip not in merged:
            merged[cam.ip] = cam
        # 如果 IP 已存在但 TCP 的相机有名称而 Sapera 没有，补充名称
        elif cam.name and not merged[cam.ip].name:
            merged[cam.ip].name = cam.name

    return list(merged.values())
