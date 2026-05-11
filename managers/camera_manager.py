"""
增强的相机连接管理器（单例）

负责：
- 维护当前连接的相机信息
- 执行手动/自动切换
- 失败时自动回退到上一次成功的连接
- 将切换操作写入审计日志
- 集成Sapera SDK原生发现功能
- 支持多种相机发现方式
"""

import threading
import time
from typing import Optional, Callable, TYPE_CHECKING, List, Union

from camera.camera_discovery import CameraInfo, CameraDiscovery, DEFAULT_CAMERA_PORT
from camera.sapera_camera_discovery import (
    SaperaCameraDiscovery, SaperaCameraController, SaperaCameraInfo,
    get_sapera_discovery, get_sapera_controller
)
from managers.audit_log_manager import AuditLogManager

if TYPE_CHECKING:
    pass


# 连接状态枚举
class ConnectionState:
    DISCONNECTED = "disconnected"   # 未连接
    CONNECTING   = "connecting"     # 连接中
    CONNECTED    = "connected"      # 已连接
    FAILED       = "failed"         # 连接失败


# 相机发现模式
class DiscoveryMode:
    SAPERA_ONLY = "sapera_only"     # 仅使用Sapera SDK发现
    NETWORK_ONLY = "network_only"   # 仅使用网络扫描
    HYBRID = "hybrid"               # 混合模式（推荐）


class EnhancedCameraManager:
    """
    增强的相机连接管理器（单例）。

    支持多种相机发现方式：
    1. Sapera SDK原生发现（推荐，适用于GigE Vision和Camera Link）
    2. 传统网络扫描（兼容性，适用于TCP相机服务）
    3. 混合模式（同时使用两种方式）
    
    外部通过 EnhancedCameraManager() 获取同一实例。
    UI 层通过注册回调感知状态变化，无需轮询。
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._state_lock = threading.Lock()

        # 当前连接的相机（可能是Sapera或网络相机）
        self._current_camera: Optional[Union[SaperaCameraInfo, CameraInfo]] = None
        # 上一次成功连接的相机（用于失败回退）
        self._last_successful: Optional[Union[SaperaCameraInfo, CameraInfo]] = None
        # 连接状态
        self._state: str = ConnectionState.DISCONNECTED
        
        # 发现模式
        self._discovery_mode = DiscoveryMode.HYBRID

        # 扫描器
        self._network_discovery = CameraDiscovery()
        self._sapera_discovery = get_sapera_discovery()
        self._sapera_controller = get_sapera_controller()

        # 日志管理器
        self._log = AuditLogManager()

        # 状态变化回调列表：fn(state: str, camera: Optional[Union[SaperaCameraInfo, CameraInfo]])
        self._state_callbacks: list = []
        # 扫描完成回调列表：fn(sapera_cameras: List[SaperaCameraInfo], network_cameras: List[CameraInfo])
        self._scan_callbacks: list = []

        # Sapera 连接/断开回调（兼容旧接口）
        self._sapera_connector = None
        self._sapera_disconnector = None

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def current_camera(self) -> Optional[Union[SaperaCameraInfo, CameraInfo]]:
        return self._current_camera

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def available_sapera_cameras(self) -> List[SaperaCameraInfo]:
        """获取可用的Sapera相机列表"""
        return self._sapera_discovery.last_results

    @property
    def available_network_cameras(self) -> List[CameraInfo]:
        """获取可用的网络相机列表"""
        return self._network_discovery.last_results
    
    @property
    def all_available_cameras(self) -> List[Union[SaperaCameraInfo, CameraInfo]]:
        """获取所有可用相机列表"""
        cameras = []
        cameras.extend(self._sapera_discovery.last_results)
        cameras.extend(self._network_discovery.last_results)
        return cameras

    @property
    def is_scanning(self) -> bool:
        return (self._network_discovery.is_scanning or 
                self._sapera_discovery.is_scanning)
    
    @property
    def discovery_mode(self) -> str:
        return self._discovery_mode
    
    @property
    def sapera_available(self) -> bool:
        """检查Sapera SDK是否可用"""
        return self._sapera_discovery.is_available

    # ------------------------------------------------------------------
    # 回调注册和配置
    # ------------------------------------------------------------------

    def on_state_change(self, callback: Callable[[str, Optional[Union[SaperaCameraInfo, CameraInfo]]], None]):
        """注册连接状态变化回调。callback(state, camera_info)"""
        self._state_callbacks.append(callback)

    def on_scan_complete(self, callback: Callable[[List[SaperaCameraInfo], List[CameraInfo]], None]):
        """注册扫描完成回调。callback(sapera_cameras, network_cameras)"""
        self._scan_callbacks.append(callback)

    def set_discovery_mode(self, mode: str):
        """
        设置相机发现模式
        
        Args:
            mode: DiscoveryMode中的一种模式
        """
        if mode in [DiscoveryMode.SAPERA_ONLY, DiscoveryMode.NETWORK_ONLY, DiscoveryMode.HYBRID]:
            self._discovery_mode = mode
        else:
            raise ValueError(f"无效的发现模式: {mode}")

    def set_sapera_connector(self, connect_fn, disconnect_fn):
        """注册 Sapera 连接/断开回调（兼容旧接口）"""
        self._sapera_connector = connect_fn
        self._sapera_disconnector = disconnect_fn

    def set_initial_camera(self, camera: Union[SaperaCameraInfo, CameraInfo]):
        """设置初始已连接的相机"""
        if self._state == ConnectionState.DISCONNECTED and camera:
            self._current_camera = camera
            self._last_successful = camera
            self._notify_state(ConnectionState.CONNECTED, camera)

    def _notify_state(self, state: str, camera: Optional[Union[SaperaCameraInfo, CameraInfo]]):
        self._state = state
        for cb in self._state_callbacks:
            try:
                cb(state, camera)
            except Exception as e:
                print(f"[EnhancedCameraManager] 状态回调异常: {e}")

    def _notify_scan(self, sapera_cameras: List[SaperaCameraInfo], network_cameras: List[CameraInfo]):
        for cb in self._scan_callbacks:
            try:
                cb(sapera_cameras, network_cameras)
            except Exception as e:
                print(f"[EnhancedCameraManager] 扫描回调异常: {e}")

    # ------------------------------------------------------------------
    # 扫描功能
    # ------------------------------------------------------------------

    def start_scan(self, blocking: bool = False, force_refresh: bool = False):
        """
        启动相机扫描。
        根据discovery_mode决定使用哪种扫描方式。
        扫描完成后触发 on_scan_complete 回调。
        
        Args:
            blocking: 是否阻塞执行
            force_refresh: 是否强制刷新（对Sapera相机检测新服务器）
        """
        self._notify_state(ConnectionState.CONNECTING, self._current_camera)
        
        if self._discovery_mode == DiscoveryMode.SAPERA_ONLY:
            self._scan_sapera_only(blocking, force_refresh)
        elif self._discovery_mode == DiscoveryMode.NETWORK_ONLY:
            self._scan_network_only(blocking)
        else:  # HYBRID
            self._scan_hybrid(blocking, force_refresh)

    def _scan_sapera_only(self, blocking: bool, force_refresh: bool):
        """仅扫描Sapera相机"""
        def on_complete(sapera_cameras):
            self._restore_connection_state()
            self._notify_scan(sapera_cameras, [])
        
        self._sapera_discovery.scan(
            on_complete=on_complete,
            blocking=blocking,
            detect_new_servers=force_refresh
        )

    def _scan_network_only(self, blocking: bool):
        """仅扫描网络相机"""
        def on_complete(network_cameras):
            self._restore_connection_state()
            self._notify_scan([], network_cameras)
        
        self._network_discovery.scan(
            on_complete=on_complete,
            blocking=blocking
        )

    def _scan_hybrid(self, blocking: bool, force_refresh: bool):
        """混合扫描（同时扫描Sapera和网络相机）"""
        results = {'sapera': [], 'network': []}
        completed = {'sapera': False, 'network': False}
        lock = threading.Lock()
        
        def check_completion():
            with lock:
                if completed['sapera'] and completed['network']:
                    self._restore_connection_state()
                    self._notify_scan(results['sapera'], results['network'])
        
        def on_sapera_complete(sapera_cameras):
            with lock:
                results['sapera'] = sapera_cameras
                completed['sapera'] = True
            check_completion()
        
        def on_network_complete(network_cameras):
            with lock:
                results['network'] = network_cameras
                completed['network'] = True
            check_completion()
        
        # 启动两种扫描
        self._sapera_discovery.scan(
            on_complete=on_sapera_complete,
            blocking=False,  # 混合模式下总是异步
            detect_new_servers=force_refresh
        )
        
        self._network_discovery.scan(
            on_complete=on_network_complete,
            blocking=False
        )
        
        # 如果需要阻塞，等待完成
        if blocking:
            while not (completed['sapera'] and completed['network']):
                time.sleep(0.1)

    def _restore_connection_state(self):
        """恢复扫描前的连接状态"""
        if self._state == ConnectionState.CONNECTING:
            if self._current_camera:
                self._notify_state(ConnectionState.CONNECTED, self._current_camera)
            else:
                self._notify_state(ConnectionState.DISCONNECTED, None)

    def refresh_cameras(self, on_complete: Optional[Callable] = None):
        """刷新相机列表（强制重新扫描）"""
        def wrapped_callback(sapera_cameras, network_cameras):
            if on_complete:
                on_complete(sapera_cameras, network_cameras)
        
        self.start_scan(blocking=False, force_refresh=True)

    # ------------------------------------------------------------------
    # 切换相机（手动，管理员/技术员）
    # ------------------------------------------------------------------

    def switch_camera(
        self,
        target: CameraInfo,
        user_name: str,
        user_role: str,
        on_result: Optional[Callable[[bool, str], None]] = None,
    ):
        """
        手动切换到目标相机（异步执行）。

        Args:
            target: 目标相机
            user_name / user_role: 操作人信息，用于写日志
            on_result: 完成回调 fn(success: bool, message: str)
        """
        if self._current and self._current == target:
            if on_result:
                on_result(True, "已是当前相机，无需切换")
            return

        threading.Thread(
            target=self._do_switch,
            args=(target, user_name, user_role, "switch_camera", on_result),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # 自动切换（加载方案时，系统触发）
    # ------------------------------------------------------------------

    def auto_switch_camera(
        self,
        target: CameraInfo,
        user_name: str,
        user_role: str,
        on_result: Optional[Callable[[bool, str], None]] = None,
    ):
        """
        加载方案时系统自动切换相机（异步执行）。
        与手动切换逻辑相同，但日志 action 不同。
        """
        if self._current and self._current == target:
            if on_result:
                on_result(True, "已是当前相机，无需切换")
            return

        threading.Thread(
            target=self._do_switch,
            args=(target, user_name, user_role, "auto_switch_camera", on_result),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # 核心切换逻辑
    # ------------------------------------------------------------------

    def _do_switch(
        self,
        target: CameraInfo,
        user_name: str,
        user_role: str,
        action: str,
        on_result: Optional[Callable],
    ):
        old_camera = self._current
        old_ip = old_camera.ip if old_camera else ""
        old_display = old_camera.display_name if old_camera else "无"

        self._notify_state(ConnectionState.CONNECTING, old_camera)

        success, message = self._connect(target)

        if success:
            self._last_successful = self._current  # 保存回退点（切换前的）
            self._current = target
            self._notify_state(ConnectionState.CONNECTED, target)

            # 写日志
            self._log.log(
                user_name=user_name,
                user_role=user_role,
                operation_type="control_settings",
                operation_action=action,
                target_object=f"{old_display} → {target.display_name}",
                old_value=old_ip,
                new_value=target.ip,
                operation_result="成功",
            )
        else:
            # 失败：回退到上一次成功的连接
            fallback = self._last_successful
            if fallback and fallback != old_camera:
                fb_ok, _ = self._connect(fallback)
                if fb_ok:
                    self._current = fallback
                    self._notify_state(ConnectionState.CONNECTED, fallback)
                else:
                    self._current = None
                    self._notify_state(ConnectionState.FAILED, None)
            else:
                # 保持原连接不变
                self._current = old_camera
                self._notify_state(
                    ConnectionState.CONNECTED if old_camera else ConnectionState.FAILED,
                    old_camera,
                )

            # 写失败日志
            self._log.log(
                user_name=user_name,
                user_role=user_role,
                operation_type="control_settings",
                operation_action=action,
                target_object=f"{old_display} → {target.display_name}",
                old_value=old_ip,
                new_value=target.ip,
                operation_result="失败",
            )

        if on_result:
            # 将用户角色一并传给回调，供调用方区分失败处理策略
            try:
                on_result(success, message, user_role)
            except TypeError:
                # 兼容只接受两个参数的旧回调
                on_result(success, message)

    def _connect(self, camera: CameraInfo) -> tuple[bool, str]:
        """
        验证目标 IP:port 是否为可用相机。
        先做 TCP 连通性探测，再发送 IDENTIFY 握手确认对端是相机服务。
        若对端无响应（普通 TCP 服务）则判定为非相机，返回失败。
        """
        import socket as _socket
        timeout_s = 2.0
        try:
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
                s.settimeout(timeout_s)
                s.connect((camera.ip, camera.port))

                # 发送握手指令，验证对端是相机服务
                try:
                    s.settimeout(0.5)
                    s.sendall(b"IDENTIFY\r\n")
                    resp = s.recv(256)
                    # 收到任何响应都认为是相机服务
                    # （真实相机会回复标识信息，非相机服务通常不响应或立即断开）
                    if resp:
                        return True, "连接成功"
                    else:
                        return False, f"对端无响应，可能不是相机：{camera.ip}:{camera.port}"
                except _socket.timeout:
                    return False, f"握手超时，对端不是相机服务：{camera.ip}:{camera.port}"
                except Exception:
                    return False, f"握手失败，对端不是相机服务：{camera.ip}:{camera.port}"

        except _socket.timeout:
            return False, f"连接超时：{camera.ip}:{camera.port}"
        except ConnectionRefusedError:
            return False, f"连接被拒绝：{camera.ip}:{camera.port}"
        except Exception as e:
            return False, f"连接失败：{e}"

        # 若有 Sapera 连接器，执行 Sapera 重连
        if camera.server_name and self._sapera_connector:
            try:
                if not self._sapera_connector(camera.server_name):
                    return False, f"Sapera连接失败：{camera.server_name}"
            except Exception as e:
                return False, f"Sapera连接异常：{e}"

    # ------------------------------------------------------------------
    # 断开连接
    # ------------------------------------------------------------------

    def disconnect(self):
        """断开当前连接（包括 Sapera）"""
        if self._sapera_disconnector:
            try:
                self._sapera_disconnector()
            except Exception:
                pass
        self._current = None
        self._notify_state(ConnectionState.DISCONNECTED, None)

    # ------------------------------------------------------------------
    # 从方案文件解析相机信息
    # ------------------------------------------------------------------

    @staticmethod
    def parse_camera_from_layout(layout: dict) -> Optional[CameraInfo]:
        """
        从 layout_config.json 的 connected_camera 节点解析 CameraInfo。

        期望格式：
        {
            "connected_camera": {
                "name": "CAM-A",
                "ip": "192.168.10.11",
                "port": 5024
            }
        }
        """
        node = layout.get("connected_camera")
        if not node or not isinstance(node, dict):
            return None
        ip = node.get("ip", "").strip()
        if not ip:
            return None
        return CameraInfo(
            ip=ip,
            port=int(node.get("port", DEFAULT_CAMERA_PORT)),
            name=node.get("name", ""),
        )

    @staticmethod
    def inject_camera_to_layout(layout: dict, camera: CameraInfo) -> dict:
        """
        将当前相机信息写入 layout dict（保存方案时调用）。
        返回修改后的 layout dict（原地修改并返回）。
        """
        layout["connected_camera"] = {
            "name": camera.name,
            "ip": camera.ip,
            "port": camera.port,
        }
        return layout
