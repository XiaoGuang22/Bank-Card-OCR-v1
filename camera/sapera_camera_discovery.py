"""
基于Sapera SDK的相机发现和管理模块

【模块功能】
使用Sapera LT原生API实现相机的自动发现、枚举和管理，
支持GigE Vision和Camera Link相机的自动检测。

【主要类】
1. SaperaCameraInfo: 相机信息数据类，存储相机的所有属性
2. SaperaCameraDiscovery: 相机发现器，负责扫描和发现网络中的相机
3. SaperaCameraController: 相机控制器，负责连接和控制相机

【工作流程】
程序启动 → 扫描相机 → 获取相机信息 → 用户选择相机 → 连接相机 → 开始采集
"""

# ============================================================
# 导入必要的库
# ============================================================
import clr  # Python.NET库，用于调用.NET程序集（Sapera SDK是.NET库）
import sys
import threading  # 多线程库，用于后台扫描相机
import time
from typing import List, Optional, Callable, Dict  # 类型提示，让代码更清晰
from dataclasses import dataclass  # 数据类装饰器，简化类的定义
from concurrent.futures import ThreadPoolExecutor  # 线程池，用于并发执行任务

# ============================================================
# 导入项目配置
# ============================================================
from config import SAPERA_DLL_PATH, CAMERA_DISPLAY_NAMES

# ============================================================
# 加载Sapera SDK（相机驱动库）
# ============================================================
# Sapera SDK是DALSA公司提供的相机控制库
try:
    # 添加Sapera SDK的DLL引用
    clr.AddReference(SAPERA_DLL_PATH)
    # 导入Sapera SDK的核心类
    from DALSA.SaperaLT.SapClassBasic import (
        SapManager,    # 管理器：用于扫描和管理相机
        SapLocation,   # 位置：指定相机的位置（服务器名+资源索引）
        SapAcqDevice,  # 采集设备：代表一个相机设备
        SapBuffer      # 缓冲区：存储相机采集的图像
    )
    SAPERA_AVAILABLE = True  # 标记SDK加载成功
except Exception as e:
    # 如果加载失败（比如没有安装Sapera SDK），打印错误信息
    print(f"Sapera SDK加载失败: {e}")
    SAPERA_AVAILABLE = False  # 标记SDK不可用


# ============================================================
# 数据类：SaperaCameraInfo（相机信息）
# ============================================================
@dataclass
class SaperaCameraInfo:
    """
    【相机信息数据类】
    存储一个相机的所有信息，包括名称、IP、序列号等
    
    【属性说明】
    - server_name: Sapera服务器名称（如"Genie_M1600_1"），这是相机的唯一标识
    - server_index: 服务器索引（第几个服务器，从0开始）
    - resource_count: 资源数量（一个服务器可能有多个资源）
    - display_name: 显示名称（给用户看的名字，如"相机A (192.168.1.100)"）
    - is_accessible: 是否可访问（相机是否在线）
    - device_info: 设备详细信息（字典，包含IP、序列号、型号等）
    
    【使用示例】
    camera = SaperaCameraInfo(
        server_name="Genie_M1600_1",
        server_index=0,
        resource_count=1,
        display_name="相机A (192.168.1.100)",
        is_accessible=True,
        device_info={'ip_address': '192.168.1.100', 'serial': 'SN12345'}
    )
    """
    server_name: str        # Sapera服务器名称（相机的唯一标识）
    server_index: int       # 服务器索引（第几个相机）
    resource_count: int     # 资源数量
    display_name: str       # 显示名称（给用户看的）
    is_accessible: bool     # 是否可访问（是否在线）
    device_info: Dict       # 设备详细信息（字典类型）
    
    @property
    def formatted_display_name(self) -> str:
        """
        【格式化显示名称】
        返回格式："用户自定义名 (IP)" 或 "型号 (IP)"
        
        【示例】
        - "相机A (192.168.1.100)"
        - "Genie_M1600 (192.168.1.101)"
        
        【逻辑】
        1. 如果display_name已经包含IP地址，直接返回
        2. 否则，按优先级选择名称：用户自定义名 > 型号 > 服务器名
        3. 拼接成 "名称 (IP)" 的格式
        """
        # 如果 display_name 已经是格式化的（包含括号和IP地址），直接返回
        if self.display_name and '(' in self.display_name and ')' in self.display_name:
            # 检查括号里是否是IP地址格式（而不是服务器名）
            import re
            ip_pattern = r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'  # IP地址的正则表达式
            if re.search(ip_pattern, self.display_name):
                return self.display_name
        
        # 否则进行格式化
        device_info = self.device_info or {}  # 获取设备信息，如果为None则用空字典
        ip_address = device_info.get('ip_address', '').strip()  # 获取IP地址
        
        # 确定相机名称
        # 优先使用 Device User ID（用户自定义名），其次使用型号，最后使用服务器名
        user_id = device_info.get('user_id', '').strip()  # 用户自定义名
        model = device_info.get('model', '').strip()      # 型号
        
        # 过滤掉看起来像数字ID的名称（比如"280570380612"这种）
        if user_id and not user_id.isdigit() and len(user_id) < 20:
            name = user_id  # 使用用户自定义名
        elif model and not model.isdigit() and len(model) < 20:
            name = model    # 使用型号
        else:
            # 如果 display_name 已设置且不是服务器名，使用它
            if self.display_name and self.display_name != self.server_name:
                name = self.display_name
            else:
                name = self.server_name  # 使用服务器名
        
        # 确保使用实际的IP地址，而不是服务器名
        if ip_address:
            return f"{name} ({ip_address})"  # 返回 "名称 (IP)" 格式
        else:
            # 如果没有IP地址，显示"未知IP"而不是服务器名
            return f"{name} (未知IP)"
    
    @property
    def unique_identifier(self) -> str:
        """
        【唯一标识符】
        返回相机的唯一标识，优先使用序列号
        
        【优先级】
        序列号 > 服务器名 > IP地址
        """
        device_info = self.device_info or {}
        return (device_info.get('serial', '') or      # 优先使用序列号
                self.server_name or                    # 其次使用服务器名
                device_info.get('ip_address', ''))     # 最后使用IP地址
    
    @property
    def log_target_object(self) -> str:
        """
        【日志记录格式】
        返回用于日志记录的格式："用户自定义名(序列号)@IP"
        
        【示例】
        "相机A(SN12345)@192.168.1.100"
        """
        device_info = self.device_info or {}
        user_id = device_info.get('user_id', '').strip()
        model = device_info.get('model', '').strip()
        serial = device_info.get('serial', '').strip()
        ip_address = device_info.get('ip_address', '').strip()
        
        name = user_id or model or self.server_name  # 选择名称
        serial_part = f"({serial})" if serial else ""  # 如果有序列号，加上括号
        ip = ip_address or "未知IP"
        
        return f"{name}{serial_part}@{ip}"
    
    def __eq__(self, other):
        """
        【相等性判断】
        判断两个相机是否是同一个相机
        
        【判断逻辑】
        1. 优先比较服务器名（最可靠）
        2. 其次比较序列号
        """
        if not isinstance(other, SaperaCameraInfo):
            return False
        
        # 优先比较服务器名（最可靠的标识）
        # 因为同一台相机的 server_name 始终不变，而序列号可能在初始化时未获取到
        if self.server_name and other.server_name:
            if self.server_name == other.server_name:
                return True
        
        # 其次比较序列号
        device_info = self.device_info or {}
        other_device_info = other.device_info or {}
        
        self_serial = device_info.get('serial', '')
        other_serial = other_device_info.get('serial', '')
        
        if self_serial and other_serial:
            return self_serial == other_serial
        
        return False
    
    def __hash__(self):
        """
        【哈希值】
        用于将相机对象放入集合（set）或作为字典的键
        优先使用服务器名作为哈希值
        """
        # 优先使用服务器名作为哈希值（最可靠的标识）
        if self.server_name:
            return hash(self.server_name)
        
        device_info = self.device_info or {}
        serial = device_info.get('serial', '')
        return hash(serial) if serial else hash(self.server_name)



# ============================================================
# 类：SaperaCameraDiscovery（相机发现器）
# ============================================================
class SaperaCameraDiscovery:
    """
    【相机发现器类】
    负责扫描网络中的所有相机，获取相机的详细信息
    
    【主要功能】
    1. 扫描网络中的相机（scan方法）
    2. 获取相机的IP、名称、序列号等信息
    3. 缓存相机信息，避免重复扫描
    4. 支持后台扫描，不阻塞主程序
    
    【工作原理】
    使用Sapera SDK的原生API进行相机发现，不需要网络扫描
    Sapera SDK会自动发现连接到电脑的所有相机
    
    【使用示例】
    discovery = SaperaCameraDiscovery()
    discovery.scan(on_complete=lambda cameras: print(f"找到{len(cameras)}个相机"))
    """
    
    def __init__(self):
        """
        【初始化方法】
        创建相机发现器对象时自动调用
        """
        # 扫描状态标志（True=正在扫描，False=未扫描）
        self._scanning = False
        
        # 线程锁，防止多个线程同时扫描（多线程安全）
        self._lock = threading.Lock()
        
        # 上次扫描的结果（相机列表）
        self._last_results: List[SaperaCameraInfo] = []
        
        # 事件注册标志（是否已注册服务器新增事件）
        self._event_registered = False
        
        # ★★★ 设备信息缓存 ★★★
        # 作用：避免重复创建设备对象，提高性能
        # 格式：{'服务器名': {'ip_address': '192.168.1.100', 'serial': 'SN12345', ...}}
        self._device_info_cache: Dict[str, Dict] = {}
        
    @property
    def is_scanning(self) -> bool:
        """
        【属性：是否正在扫描】
        返回True表示正在扫描，False表示未扫描
        
        【使用示例】
        if discovery.is_scanning:
            print("正在扫描相机...")
        """
        return self._scanning
    
    @property
    def last_results(self) -> List[SaperaCameraInfo]:
        """
        【属性：上次扫描结果】
        返回上次扫描到的相机列表
        
        【使用示例】
        cameras = discovery.last_results
        for camera in cameras:
            print(camera.display_name)
        """
        return list(self._last_results)  # 返回列表的副本，防止外部修改
    
    @property
    def is_available(self) -> bool:
        """
        【属性：SDK是否可用】
        检查Sapera SDK是否成功加载
        返回True表示可用，False表示不可用
        """
        return SAPERA_AVAILABLE
    
    def scan(
        self,
        on_complete: Optional[Callable[[List[SaperaCameraInfo]], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
        blocking: bool = False,
        detect_new_servers: bool = True
    ):
        """
        【扫描相机方法】
        扫描网络中的所有相机，获取相机信息
        
        【参数说明】
        - on_complete: 扫描完成后的回调函数，参数是相机列表
                      示例：lambda cameras: print(f"找到{len(cameras)}个相机")
        - on_progress: 进度回调函数，参数是(当前进度, 总数)
                      示例：lambda current, total: print(f"进度: {current}/{total}")
        - blocking: 是否阻塞执行
                   True=等待扫描完成再返回（会卡住程序）
                   False=后台扫描，立即返回（推荐）
        - detect_new_servers: 是否检测新连接的服务器（用于Camera Link相机）
        
        【工作流程】
        1. 检查SDK是否可用
        2. 检查是否已在扫描（防止重复扫描）
        3. 设置扫描标志为True
        4. 在后台线程中执行扫描（如果blocking=False）
        5. 扫描完成后调用on_complete回调
        
        【使用示例】
        # 后台扫描（推荐）
        discovery.scan(on_complete=lambda cameras: print(f"找到{len(cameras)}个相机"))
        
        # 阻塞扫描（会卡住程序）
        discovery.scan(blocking=True)
        cameras = discovery.last_results
        """
        # 1. 检查SDK是否可用
        if not SAPERA_AVAILABLE:
            # SDK不可用，直接返回空列表
            if on_complete:
                on_complete([])
            return
        
        # 2. 检查是否已在扫描（使用线程锁保证线程安全）
        with self._lock:
            if self._scanning:
                # 已经在扫描了，直接返回
                return
            # 设置扫描标志为True
            self._scanning = True
        
        # 3. 执行扫描
        if blocking:
            # 阻塞模式：直接在当前线程执行（会卡住程序）
            self._do_scan(on_complete, on_progress, detect_new_servers)
        else:
            # 非阻塞模式：在后台线程执行（推荐）
            t = threading.Thread(
                target=self._do_scan,  # 要执行的函数
                args=(on_complete, on_progress, detect_new_servers),  # 函数参数
                daemon=True  # 守护线程，程序退出时自动结束
            )
            t.start()  # 启动线程
    
    def _do_scan(
        self,
        on_complete: Optional[Callable],
        on_progress: Optional[Callable],
        detect_new_servers: bool
    ):
        """
        【执行实际的扫描操作】
        这是扫描的核心方法，在后台线程中执行
        
        【工作流程】
        1. 清空上次的扫描结果
        2. 检测新连接的服务器（如果需要）
        3. 获取服务器数量
        4. 遍历每个服务器，获取相机信息
        5. 过滤掉系统设备和无IP的相机
        6. 排序并保存结果
        7. 调用完成回调
        
        【详细步骤】
        对于每个服务器：
        - 获取服务器名称（如"Genie_M1600_1"）
        - 检查是否是系统设备（跳过）
        - 获取设备详细信息（IP、序列号、型号等）
        - 确定显示名称（优先级：用户自定义名 > 配置名 > 型号 > 服务器名）
        - 创建SaperaCameraInfo对象
        - 添加到结果列表
        """
        try:
            # 存储找到的相机
            found_cameras = []
            
            # ★★★ 步骤1：清空上次的扫描结果 ★★★
            # 作用：避免显示已断开的相机
            self._last_results = []
            
            # ★★★ 步骤2：检测新连接的服务器 ★★★
            # 作用：对于Camera Link相机，需要先检测新服务器
            if detect_new_servers:
                self._detect_new_servers()
            
            # ★★★ 步骤3：获取服务器数量 ★★★
            # SapManager.GetServerCount() 返回连接到电脑的相机数量
            server_count = SapManager.GetServerCount()
            print(f"[Sapera] Found {server_count} server(s)")  # 打印找到的服务器数量
            
            # 调用进度回调（0/总数）
            if on_progress:
                on_progress(0, server_count)
            
            # ★★★ 步骤4：遍历所有服务器 ★★★
            for i in range(server_count):  # i从0到server_count-1
                try:
                    # ──────────────────────────────────────
                    # 4.1 获取服务器名称
                    # ──────────────────────────────────────
                    # SapManager.GetServerName(i) 返回第i个服务器的名称
                    # 例如："Genie_M1600_1", "Genie_M1600_2"
                    server_name = SapManager.GetServerName(i)
                    
                    # ──────────────────────────────────────
                    # 4.2 过滤掉系统设备
                    # ──────────────────────────────────────
                    # 系统设备不是真实的相机，需要跳过
                    if server_name.startswith("System") or "System" in server_name:
                        print(f"跳过系统设备: {server_name}")
                        continue  # 跳过本次循环，继续下一个
                    
                    # ──────────────────────────────────────
                    # 4.3 检查服务器是否可访问
                    # ──────────────────────────────────────
                    is_accessible = True  # 默认为可访问
                    try:
                        # 尝试调用IsServerAccessible检查
                        is_accessible = SapManager.IsServerAccessible(i)
                    except Exception:
                        # 如果方法不可用，保持默认值True
                        pass
                    
                    # ──────────────────────────────────────
                    # 4.4 获取资源数量
                    # ──────────────────────────────────────
                    # 一个服务器可能有多个资源（通常是1个）
                    resource_count = 0
                    try:
                        # 尝试第一种方法调用
                        resource_count = SapManager.GetResourceCount(i)
                    except Exception as e1:
                        try:
                            # 如果失败，尝试第二种方法（带ResourceType参数）
                            from DALSA.SaperaLT.SapClassBasic import ResourceType
                            resource_count = SapManager.GetResourceCount(server_name, ResourceType.AcqDevice)
                        except Exception as e2:
                            # 两种方法都失败，使用默认值1
                            print(f"获取资源数量失败: {e1}, {e2}")
                            resource_count = 1
                    
                    # ──────────────────────────────────────
                    # 4.5 获取设备详细信息（带缓存）
                    # ──────────────────────────────────────
                    # 这是最重要的一步，获取相机的IP、序列号、型号等信息
                    device_info = self._get_device_info_cached(server_name, i)
                    
                    # ──────────────────────────────────────
                    # 4.6 确定相机显示名称
                    # ──────────────────────────────────────
                    # 优先级：用户自定义名 > 配置名 > 型号 > 服务器名
                    device_info_dict = device_info or {}  # 如果为None，用空字典
                    
                    # 从设备信息中提取各种名称
                    user_id = device_info_dict.get('user_id', '').strip()  # 用户自定义名
                    model = device_info_dict.get('model', '').strip()      # 型号
                    config_display_name = CAMERA_DISPLAY_NAMES.get(server_name, "")  # 配置文件中的名称
                    
                    # 按优先级选择名称
                    if user_id and not user_id.isdigit() and len(user_id) < 20:
                        # 优先使用用户自定义名（如果不是纯数字且长度合理）
                        camera_name = user_id
                        print(f"[Sapera] 使用相机 Device User ID: {camera_name} for {server_name}")
                    elif config_display_name:
                        # 其次使用配置文件中的名称
                        camera_name = config_display_name
                        print(f"[Sapera] 使用配置名称: {camera_name} for {server_name}")
                    elif model and not model.isdigit() and len(model) < 20:
                        # 再次使用型号
                        camera_name = model
                        print(f"[Sapera] 使用相机型号: {camera_name} for {server_name}")
                    else:
                        # 最后使用服务器名
                        camera_name = server_name
                        print(f"[Sapera] 使用服务器名称: {camera_name} for {server_name}")
                    
                    # ──────────────────────────────────────
                    # 4.7 获取IP地址
                    # ──────────────────────────────────────
                    ip_address = device_info_dict.get('ip_address', '').strip()
                    
                    # 如果无法从设备获取IP地址，尝试其他方法
                    if not ip_address and is_accessible:
                        # 方法1：通过ping已知IP段发现
                        # 根据服务器名称尝试常见的IP地址
                        known_ips = []
                        if "Genie_M1600_1" in server_name:
                            known_ips = ["192.168.11.136", "192.168.11.110", "192.168.1.100", "192.168.0.100"]
                        elif "Genie_M1600_2" in server_name:
                            known_ips = ["192.168.12.110", "192.168.11.110", "192.168.11.136", "192.168.1.101", "192.168.0.101"]
                        else:
                            # 通用的常见IP段
                            known_ips = ["192.168.12.110", "192.168.11.136", "192.168.11.110", "192.168.1.100", "192.168.0.100"]
                        
                        # 尝试ping每个IP地址
                        for test_ip in known_ips:
                            try:
                                import subprocess
                                # 执行ping命令：ping -n 1 -w 500 IP地址
                                # -n 1: 只ping一次
                                # -w 500: 超时时间500毫秒
                                result = subprocess.run(['ping', '-n', '1', '-w', '500', test_ip], 
                                                      capture_output=True, text=True, timeout=1)
                                if result.returncode == 0:  # ping成功
                                    ip_address = test_ip
                                    print(f"[Sapera] 通过ping发现 {server_name} 的IP: {ip_address}")
                                    break  # 找到IP，退出循环
                            except Exception:
                                continue  # ping失败，尝试下一个IP
                        
                        # 方法2：尝试通过网络扫描获取
                        if not ip_address:
                            try:
                                from camera.ip_discovery_helper import get_cached_camera_ips, match_sapera_camera_to_ip
                                camera_ips = get_cached_camera_ips()
                                matched_ip = match_sapera_camera_to_ip(server_name, camera_ips)
                                if matched_ip:
                                    ip_address = matched_ip
                                    print(f"[Sapera] 通过网络扫描为 {server_name} 匹配到IP: {ip_address}")
                            except Exception as e:
                                print(f"[Sapera] 网络扫描匹配IP失败: {e}")
                    
                    # ──────────────────────────────────────
                    # 4.8 检查IP地址是否有效
                    # ──────────────────────────────────────
                    # ★★★ 如果无法获取IP地址，跳过该相机 ★★★
                    # 原因：没有IP地址的相机可能已断开连接或被其他程序占用
                    if not ip_address:
                        print(f"[Sapera] 跳过无IP地址的相机: {server_name}（可能已断开连接）")
                        continue  # 跳过本次循环
                    
                    # ──────────────────────────────────────
                    # 4.9 格式化显示名称
                    # ──────────────────────────────────────
                    # 格式："名称 (IP)"
                    # 例如："相机A (192.168.1.100)"
                    display_name = f"{camera_name} ({ip_address})"
                    
                    # ──────────────────────────────────────
                    # 4.10 创建相机信息对象
                    # ──────────────────────────────────────
                    camera_info = SaperaCameraInfo(
                        server_name=server_name,        # 服务器名称
                        server_index=i,                 # 服务器索引
                        resource_count=resource_count,  # 资源数量
                        display_name=display_name,      # 显示名称
                        is_accessible=is_accessible,    # 是否可访问
                        device_info=device_info         # 设备详细信息
                    )
                    
                    # ──────────────────────────────────────
                    # 4.11 添加到结果列表
                    # ──────────────────────────────────────
                    found_cameras.append(camera_info)
                    
                    # 调用进度回调
                    if on_progress:
                        on_progress(i + 1, server_count)
                        
                except Exception as e:
                    # 获取某个服务器信息失败，打印错误并继续下一个
                    print(f"获取服务器 {i} 信息失败: {e}")
                    continue
            
            # ★★★ 步骤5：按服务器名称排序 ★★★
            # 作用：让相机列表按字母顺序排列，方便查看
            found_cameras.sort(key=lambda x: x.server_name)
            
            # ★★★ 步骤6：保存扫描结果 ★★★
            self._last_results = found_cameras
            
            # ★★★ 步骤7：调用完成回调 ★★★
            if on_complete:
                on_complete(found_cameras)
                
        except Exception as e:
            # 扫描过程出错，打印错误信息
            print(f"Sapera相机扫描失败: {e}")
            if on_complete:
                on_complete([])  # 返回空列表
        finally:
            # ★★★ 步骤8：重置扫描标志 ★★★
            # 无论成功还是失败，都要重置扫描标志
            with self._lock:
                self._scanning = False
    
    def _detect_new_servers(self):
        """
        【检测新连接的服务器】
        用于Camera Link相机，检测新连接的GenCP服务器
        
        【工作原理】
        调用Sapera SDK的DetectAllServers方法，让SDK重新扫描所有服务器
        这样可以发现新连接的相机
        """
        try:
            # 注册服务器新增事件（如果还没注册）
            if not self._event_registered:
                # 这里应该注册ServerNew事件，但由于Python绑定限制，
                # 我们直接调用DetectAllServers
                self._event_registered = True
            
            # 检测所有服务器
            try:
                # 尝试不带参数的调用
                SapManager.DetectAllServers()
            except Exception as e1:
                try:
                    # 如果失败，尝试带参数的调用
                    from DALSA.SaperaLT.SapClassBasic import DetectServerType
                    SapManager.DetectAllServers(DetectServerType.GenCP)
                except Exception as e2:
                    print(f"DetectAllServers 调用失败: {e1}, {e2}")
            
            # 等待一小段时间让检测完成
            time.sleep(0.1)  # 等待100毫秒
            
        except Exception as e:
            print(f"检测新服务器失败: {e}")
    
    def _get_device_info_cached(self, server_name: str, server_index: int) -> Dict:
        """
        【获取设备详细信息（带缓存）】
        优先使用缓存的设备信息，避免重复创建设备对象
        
        【参数说明】
        - server_name: 服务器名称（如"Genie_M1600_1"）
        - server_index: 服务器索引（第几个服务器）
        
        【返回值】
        设备信息字典，包含：
        - ip_address: IP地址
        - serial: 序列号
        - user_id: 用户自定义名
        - model: 型号
        - vendor: 厂商
        等等
        
        【缓存机制】
        1. 如果缓存中有该服务器的信息，且服务器仍然可访问，直接返回缓存
        2. 如果服务器不可访问，清除缓存
        3. 如果缓存中没有，调用_get_device_info获取新信息并缓存
        
        【为什么要缓存？】
        - 创建设备对象需要时间（几百毫秒）
        - 如果相机被其他程序占用，创建会失败
        - 缓存可以避免重复创建，提高性能
        """
        # 检查缓存中是否有该服务器的信息
        if server_name in self._device_info_cache:
            cached_info = self._device_info_cache[server_name]
            try:
                # 检查服务器是否仍然可访问
                if SapManager.IsServerAccessible(server_index):
                    print(f"[Sapera] 使用缓存的设备信息: {server_name}")
                    return cached_info  # 返回缓存的信息
            except Exception:
                pass
            # 服务器不可达，清除缓存
            print(f"[Sapera] 服务器不可达，清除缓存: {server_name}")
            del self._device_info_cache[server_name]

        # 尝试获取新的设备信息
        device_info = self._get_device_info(server_name, server_index)

        # 如果成功获取到信息，缓存起来
        if device_info and device_info.get('ip_address'):
            self._device_info_cache[server_name] = device_info

        return device_info
    
    def _get_device_info(self, server_name: str, server_index: int) -> Dict:
        """
        获取设备详细信息
        
        按需求文档 FC-05 要求，读取 GenICam 标准特征：
        - DeviceUserID (用户自定义名称)
        - DeviceSerialNumber (序列号)
        - DeviceModelName (型号)
        - GevCurrentIPAddress (当前IP地址)
        
        注意：创建设备后必须立即释放，避免资源占用
        """
        device_info = {
            'user_id': '',           # DeviceUserID
            'serial': '',            # DeviceSerialNumber
            'model': '',             # DeviceModelName
            'ip_address': '',        # GevCurrentIPAddress
            'vendor': '',            # DeviceVendorName
            'version': '',           # DeviceVersion
            'pixel_formats': [],
            'features': []
        }
        
        acq_device = None
        try:
            # 创建设备位置
            location = SapLocation(server_name, 0)  # 通常第一个资源
            
            # 创建设备对象（不独占模式）
            acq_device = SapAcqDevice(location, False)
            
            # 尝试创建设备，如果失败则直接返回空信息
            if not acq_device.Create():
                print(f"[Sapera] 无法创建设备 {server_name}（可能被占用）")
                return device_info
            
            try:
                # 按需求文档 FC-05 读取 GenICam 标准特征
                
                # 用户自定义名称
                if acq_device.IsFeatureAvailable("DeviceUserID"):
                    result = acq_device.GetFeatureValue("DeviceUserID")
                    if isinstance(result, tuple) and len(result) >= 2:
                        raw_value = result[1] if result[0] else ""
                        # 尝试将数字转换为字符串（可能是编码的字符串）
                        if isinstance(raw_value, (int, float)):
                            try:
                                # 尝试将大整数转换为字符串
                                hex_str = hex(int(raw_value))[2:]  # 去掉 0x 前缀
                                if len(hex_str) % 2 == 1:
                                    hex_str = '0' + hex_str
                                
                                # 尝试解码为ASCII字符串
                                decoded = bytes.fromhex(hex_str).decode('ascii', errors='ignore').strip('\x00')
                                
                                # 如果解码结果看起来是反向的，尝试反转
                                if decoded and decoded.isprintable():
                                    # 检查是否需要反转（如果以数字开头但应该以S开头）
                                    if decoded[0].isdigit() and decoded[-1].upper() == 'S':
                                        decoded = decoded[::-1]  # 反转字符串
                                    device_info['user_id'] = decoded
                                else:
                                    device_info['user_id'] = str(raw_value)
                            except:
                                device_info['user_id'] = str(raw_value)
                        else:
                            device_info['user_id'] = str(raw_value)
                    else:
                        device_info['user_id'] = str(result)
                
                # 序列号（唯一标识）
                if acq_device.IsFeatureAvailable("DeviceSerialNumber"):
                    result = acq_device.GetFeatureValue("DeviceSerialNumber")
                    if isinstance(result, tuple) and len(result) >= 2:
                        raw_value = result[1] if result[0] else ""
                        # 尝试解码序列号
                        if isinstance(raw_value, (int, float)):
                            try:
                                hex_str = hex(int(raw_value))[2:]
                                if len(hex_str) % 2 == 1:
                                    hex_str = '0' + hex_str
                                decoded = bytes.fromhex(hex_str).decode('ascii', errors='ignore').strip('\x00')
                                if decoded and decoded.isprintable():
                                    device_info['serial'] = decoded
                                else:
                                    device_info['serial'] = str(raw_value)
                            except:
                                device_info['serial'] = str(raw_value)
                        else:
                            device_info['serial'] = str(raw_value)
                    else:
                        device_info['serial'] = str(result)
                
                # 型号
                if acq_device.IsFeatureAvailable("DeviceModelName"):
                    result = acq_device.GetFeatureValue("DeviceModelName")
                    if isinstance(result, tuple) and len(result) >= 2:
                        raw_value = result[1] if result[0] else ""
                        # 尝试解码型号
                        if isinstance(raw_value, (int, float)):
                            try:
                                hex_str = hex(int(raw_value))[2:]
                                if len(hex_str) % 2 == 1:
                                    hex_str = '0' + hex_str
                                decoded = bytes.fromhex(hex_str).decode('ascii', errors='ignore').strip('\x00')
                                if decoded and decoded.isprintable():
                                    device_info['model'] = decoded
                                else:
                                    device_info['model'] = str(raw_value)
                            except:
                                device_info['model'] = str(raw_value)
                        else:
                            device_info['model'] = str(raw_value)
                    else:
                        device_info['model'] = str(result)
                
                # 当前IP地址
                if acq_device.IsFeatureAvailable("GevCurrentIPAddress"):
                    try:
                        result = acq_device.GetFeatureValue("GevCurrentIPAddress")
                        ip_value = result[1] if isinstance(result, tuple) and len(result) >= 2 else result
                        
                        if isinstance(ip_value, (int, float)):
                            # 将整数IP转换为点分十进制格式
                            ip_int = int(ip_value)
                            ip_str = f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"
                            device_info['ip_address'] = ip_str
                        else:
                            device_info['ip_address'] = str(ip_value)
                    except Exception as e:
                        print(f"获取IP地址失败: {e}")
                
                # 其他设备信息
                if acq_device.IsFeatureAvailable("DeviceVendorName"):
                    result = acq_device.GetFeatureValue("DeviceVendorName")
                    if isinstance(result, tuple) and len(result) >= 2:
                        device_info['vendor'] = str(result[1]) if result[0] else ""
                    else:
                        device_info['vendor'] = str(result)
                
                if acq_device.IsFeatureAvailable("DeviceVersion"):
                    result = acq_device.GetFeatureValue("DeviceVersion")
                    if isinstance(result, tuple) and len(result) >= 2:
                        device_info['version'] = str(result[1]) if result[0] else ""
                    else:
                        device_info['version'] = str(result)
                
                # 获取支持的像素格式
                if acq_device.IsFeatureAvailable("PixelFormat"):
                    try:
                        result = acq_device.GetFeatureValue("PixelFormat")
                        current_format = result[1] if isinstance(result, tuple) and len(result) >= 2 else result
                        device_info['pixel_formats'] = [str(current_format)]
                    except:
                        pass
                
                # 获取关键特性列表
                key_features = [
                    "TriggerMode", "ExposureTime", "ExposureTimeRaw", "Gain", "GainRaw",
                    "Width", "Height", "AcquisitionFrameRate", "GevSCPSPacketSize",
                    "DeviceTemperature", "DeviceUptime"
                ]
                
                available_features = []
                for feature in key_features:
                    if acq_device.IsFeatureAvailable(feature):
                        available_features.append(feature)
                
                device_info['features'] = available_features
                
                # 调试输出
                print(f"[Sapera] 设备 {server_name} 信息:")
                print(f"  用户名: {device_info['user_id']}")
                print(f"  序列号: {device_info['serial']}")
                print(f"  型号: {device_info['model']}")
                print(f"  IP地址: {device_info['ip_address']}")
                print(f"  厂商: {device_info['vendor']}")
                
            except Exception as e:
                print(f"获取设备 {server_name} 详细信息失败: {e}")
            finally:
                # 确保设备被正确销毁和释放
                if acq_device:
                    try:
                        acq_device.Destroy()
                    except:
                        pass
                    try:
                        acq_device.Dispose()
                    except:
                        pass
        
        except Exception as e:
            print(f"创建设备 {server_name} 失败: {e}")
        finally:
            # 最终确保资源释放
            if acq_device:
                try:
                    if hasattr(acq_device, 'Destroy'):
                        acq_device.Destroy()
                except:
                    pass
                try:
                    if hasattr(acq_device, 'Dispose'):
                        acq_device.Dispose()
                except:
                    pass
        
        return device_info
    
    def get_camera_by_name(self, server_name: str) -> Optional[SaperaCameraInfo]:
        """根据服务器名称获取相机信息"""
        for camera in self._last_results:
            if camera.server_name == server_name:
                return camera
        return None
    
    def refresh(self, on_complete: Optional[Callable] = None):
        """刷新相机列表（强制重新扫描）"""
        self.scan(on_complete=on_complete, detect_new_servers=True)
    
    def clear_device_cache(self, server_name: Optional[str] = None):
        """
        清除设备信息缓存
        
        Args:
            server_name: 要清除的服务器名称，如果为None则清除所有缓存
        """
        if server_name:
            if server_name in self._device_info_cache:
                del self._device_info_cache[server_name]
                print(f"[Sapera] 已清除设备缓存: {server_name}")
        else:
            self._device_info_cache.clear()
            print(f"[Sapera] 已清除所有设备缓存")


class SaperaCameraController:
    """
    Sapera相机控制器
    
    提供相机连接、断开、参数设置等功能
    """
    
    def __init__(self):
        self._current_camera: Optional[SaperaCameraInfo] = None
        self._acq_device: Optional = None
        self._connected = False
        self._lock = threading.Lock()
    
    @property
    def current_camera(self) -> Optional[SaperaCameraInfo]:
        return self._current_camera
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    def connect(self, camera_info: SaperaCameraInfo) -> tuple[bool, str]:
        """
        连接到指定相机
        
        Returns:
            (success, message)
        """
        if not SAPERA_AVAILABLE:
            return False, "Sapera SDK不可用"
        
        with self._lock:
            # 如果已连接到同一相机，直接返回成功
            if (self._connected and self._current_camera and 
                self._current_camera.server_name == camera_info.server_name):
                return True, "已连接到该相机"
            
            # 断开当前连接
            if self._connected:
                self._disconnect_internal()
            
            try:
                # 创建设备位置
                location = SapLocation(camera_info.server_name, 0)
                
                # 创建设备对象
                self._acq_device = SapAcqDevice(location, False)
                
                if not self._acq_device.Create():
                    return False, f"无法创建设备: {camera_info.server_name}"
                
                # 连接成功
                self._current_camera = camera_info
                self._connected = True
                
                return True, f"成功连接到 {camera_info.display_name}"
                
            except Exception as e:
                self._disconnect_internal()
                return False, f"连接失败: {e}"
    
    def disconnect(self):
        """断开当前连接"""
        with self._lock:
            self._disconnect_internal()
    
    def _disconnect_internal(self):
        """内部断开连接方法（不加锁）"""
        if self._acq_device:
            try:
                self._acq_device.Destroy()
                self._acq_device.Dispose()
            except:
                pass
            self._acq_device = None
        
        self._current_camera = None
        self._connected = False
    
    def set_parameter(self, param_name: str, value) -> tuple[bool, str]:
        """
        设置相机参数
        
        Args:
            param_name: 参数名称
            value: 参数值
            
        Returns:
            (success, message)
        """
        if not self._connected or not self._acq_device:
            return False, "相机未连接"
        
        try:
            if not self._acq_device.IsFeatureAvailable(param_name):
                return False, f"参数 {param_name} 不可用"
            
            if self._acq_device.SetFeatureValue(param_name, value):
                return True, f"参数 {param_name} 设置成功"
            else:
                return False, f"参数 {param_name} 设置失败"
                
        except Exception as e:
            return False, f"设置参数失败: {e}"
    
    def get_parameter(self, param_name: str) -> tuple[bool, str, any]:
        """
        获取相机参数
        
        Returns:
            (success, message, value)
        """
        if not self._connected or not self._acq_device:
            return False, "相机未连接", None
        
        try:
            if not self._acq_device.IsFeatureAvailable(param_name):
                return False, f"参数 {param_name} 不可用", None
            
            value = self._acq_device.GetFeatureValue(param_name)
            return True, "获取成功", value
            
        except Exception as e:
            return False, f"获取参数失败: {e}", None


# 全局单例实例
_sapera_discovery = None
_sapera_controller = None

def get_sapera_discovery() -> SaperaCameraDiscovery:
    """获取Sapera相机发现器单例"""
    global _sapera_discovery
    if _sapera_discovery is None:
        _sapera_discovery = SaperaCameraDiscovery()
    return _sapera_discovery

def get_sapera_controller() -> SaperaCameraController:
    """获取Sapera相机控制器单例"""
    global _sapera_controller
    if _sapera_controller is None:
        _sapera_controller = SaperaCameraController()
    return _sapera_controller