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
from typing import Optional, Callable, TYPE_CHECKING, List

from camera.sapera_camera_discovery import (
    SaperaCameraDiscovery, SaperaCameraController, SaperaCameraInfo,
    get_sapera_discovery, get_sapera_controller
)
from camera.sapera_camera_manager import get_sapera_camera_manager
from managers.audit_log_manager import AuditLogManager

# 默认端口常量（用于方案文件兼容）
DEFAULT_CAMERA_PORT = 5024

if TYPE_CHECKING:
    pass


# 连接状态枚举
class ConnectionState:
    DISCONNECTED = "disconnected"   # 未连接
    CONNECTING   = "connecting"     # 连接中
    CONNECTED    = "connected"      # 已连接
    FAILED       = "failed"         # 连接失败


class EnhancedCameraManager:
    """
    相机连接管理器（单例）。

    基于 Sapera SDK 原生发现，适用于 GigE Vision 和 Camera Link 相机。

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

        # 当前连接的Sapera相机
        self._current_camera: Optional[SaperaCameraInfo] = None
        # 上一次成功连接的Sapera相机（用于失败回退）
        self._last_successful: Optional[SaperaCameraInfo] = None
        # 连接状态
        self._state: str = ConnectionState.DISCONNECTED

        # Sapera 扫描器、控制器与切换管理器
        self._sapera_discovery = get_sapera_discovery()
        self._sapera_controller = get_sapera_controller()
        self._sapera_manager = get_sapera_camera_manager()

        # 日志管理器
        self._log = AuditLogManager()

        # 状态变化回调列表：fn(state: str, camera: Optional[SaperaCameraInfo])
        self._state_callbacks: list = []
        # 扫描完成回调列表：fn(sapera_cameras: List[SaperaCameraInfo])
        self._scan_callbacks: list = []

        # Sapera 连接/断开回调（兼容旧接口）
        self._sapera_connector = None
        self._sapera_disconnector = None

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def current_camera(self) -> Optional[SaperaCameraInfo]:
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
    def all_available_cameras(self) -> List[SaperaCameraInfo]:
        """获取所有可用相机列表"""
        return list(self._sapera_discovery.last_results)

    @property
    def is_scanning(self) -> bool:
        return self._sapera_discovery.is_scanning

    @property
    def sapera_available(self) -> bool:
        """检查Sapera SDK是否可用"""
        return self._sapera_discovery.is_available

    # ------------------------------------------------------------------
    # 回调注册和配置
    # ------------------------------------------------------------------

    def on_state_change(self, callback: Callable[[str, Optional[SaperaCameraInfo]], None]):
        """注册连接状态变化回调。callback(state, camera_info)"""
        self._state_callbacks.append(callback)

    def on_scan_complete(self, callback: Callable[[List[SaperaCameraInfo]], None]):
        """注册扫描完成回调。callback(sapera_cameras)"""
        self._scan_callbacks.append(callback)

    def set_sapera_connector(self, connect_fn, disconnect_fn):
        """注册 Sapera 连接/断开回调（兼容旧接口）"""
        self._sapera_connector = connect_fn
        self._sapera_disconnector = disconnect_fn

    def set_initial_camera(self, camera: SaperaCameraInfo):
        """设置初始已连接的相机"""
        if self._state == ConnectionState.DISCONNECTED and camera:
            self._current_camera = camera
            self._last_successful = camera
            self._notify_state(ConnectionState.CONNECTED, camera)

    def _notify_state(self, state: str, camera: Optional[SaperaCameraInfo]):
        self._state = state
        for cb in self._state_callbacks:
            try:
                cb(state, camera)
            except Exception as e:
                print(f"[EnhancedCameraManager] 状态回调异常: {e}")

    def _notify_scan(self, sapera_cameras: List[SaperaCameraInfo]):
        for cb in self._scan_callbacks:
            try:
                cb(sapera_cameras)
            except Exception as e:
                print(f"[EnhancedCameraManager] 扫描回调异常: {e}")

    # ------------------------------------------------------------------
    # 扫描功能
    # ------------------------------------------------------------------

    def start_scan(self, blocking: bool = False, force_refresh: bool = False):
        """
        启动 Sapera 相机扫描。
        扫描完成后触发 on_scan_complete 回调。

        Args:
            blocking: 是否阻塞执行
            force_refresh: 是否强制刷新（检测新上线的服务器）
        """
        self._notify_state(ConnectionState.CONNECTING, self._current_camera)

        def on_complete(sapera_cameras):
            self._restore_connection_state()
            self._notify_scan(sapera_cameras)

        self._sapera_discovery.scan(
            on_complete=on_complete,
            blocking=blocking,
            detect_new_servers=force_refresh
        )

    def _restore_connection_state(self):
        """恢复扫描前的连接状态"""
        if self._state == ConnectionState.CONNECTING:
            if self._current_camera:
                self._notify_state(ConnectionState.CONNECTED, self._current_camera)
            else:
                self._notify_state(ConnectionState.DISCONNECTED, None)

    def refresh_cameras(self, on_complete: Optional[Callable] = None):
        """刷新相机列表（强制重新扫描）"""
        def wrapped_callback(sapera_cameras):
            if on_complete:
                on_complete(sapera_cameras)

        self.start_scan(blocking=False, force_refresh=True)

    # ------------------------------------------------------------------
    # 切换相机（手动，管理员/技术员）
    # ------------------------------------------------------------------

    def switch_camera(
        self,
        target: SaperaCameraInfo,
        user_name: str,
        user_role: str,
        on_result: Optional[Callable[[bool, str, str], None]] = None,
    ):
        """
        手动切换到目标相机（异步执行）。

        Args:
            target: 目标Sapera相机
            user_name / user_role: 操作人信息
            on_result: 完成回调 fn(success, message, user_role)
        """
        if self._current_camera and self._current_camera == target:
            if on_result:
                try:
                    on_result(True, "已是当前相机，无需切换", user_role)
                except TypeError:
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
        target: SaperaCameraInfo,
        user_name: str,
        user_role: str,
        on_result: Optional[Callable[[bool, str, str], None]] = None,
    ):
        """
        加载方案时系统自动切换相机（异步执行）。
        与手动切换逻辑相同，仅日志 action 不同。

        Args:
            target: 目标Sapera相机
        """
        if self._current_camera and self._current_camera == target:
            if on_result:
                try:
                    on_result(True, "已是当前相机，无需切换", user_role)
                except TypeError:
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
        target: SaperaCameraInfo,
        user_name: str,
        user_role: str,
        action: str,
        on_result: Optional[Callable],
    ):
        """
        核心切换逻辑：
        1. 委托 SaperaCameraManager.switch_camera() 执行硬件切换
        2. 失败时回退到上一次成功的连接
        3. 写审计日志，回调传递 user_role（供 UI 区分操作员/管理员行为）
        """
        old_camera = self._current_camera
        old_ip = ""
        old_display = "无"
        if old_camera:
            old_ip = (old_camera.device_info or {}).get("ip_address", "")
            old_display = old_camera.formatted_display_name

        self._notify_state(ConnectionState.CONNECTING, old_camera)

        # ── 执行硬件切换 ──
        success, message = self._sapera_manager.switch_camera(target)

        if success:
            self._last_successful = self._current_camera
            self._current_camera = target
            self._notify_state(ConnectionState.CONNECTED, target)

            self._log.log(
                user_name=user_name, user_role=user_role,
                operation_type="control_settings", operation_action=action,
                target_object=f"{old_display} → {target.formatted_display_name}",
                old_value=old_ip,
                new_value=(target.device_info or {}).get("ip_address", ""),
                operation_result="成功",
            )
        else:
            # ── 失败回退 ──
            fallback = self._last_successful
            if fallback and fallback != old_camera:
                fb_ok, _ = self._sapera_manager.switch_camera(fallback)
                if fb_ok:
                    self._current_camera = fallback
                    self._notify_state(ConnectionState.CONNECTED, fallback)
                else:
                    self._current_camera = None
                    self._notify_state(ConnectionState.FAILED, None)
            else:
                self._current_camera = old_camera
                self._notify_state(
                    ConnectionState.CONNECTED if old_camera else ConnectionState.FAILED,
                    old_camera,
                )

            self._log.log(
                user_name=user_name, user_role=user_role,
                operation_type="control_settings", operation_action=action,
                target_object=f"{old_display} → {target.formatted_display_name}",
                old_value=old_ip,
                new_value=(target.device_info or {}).get("ip_address", ""),
                operation_result="失败",
            )

        if on_result:
            try:
                on_result(success, message, user_role)
            except TypeError:
                on_result(success, message)

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
        self._current_camera = None
        self._notify_state(ConnectionState.DISCONNECTED, None)

    # ------------------------------------------------------------------
    # 从方案文件解析相机信息
    # ------------------------------------------------------------------

    @staticmethod
    def parse_camera_from_layout(layout: dict) -> Optional[dict]:
        """
        从方案文件的 connected_camera 节点解析相机信息。

        返回包含相机标识信息的字典，用于后续匹配 Sapera 相机。

        期望格式：
        {
            "connected_camera": {
                "serial":      "SN-00123",
                "name":        "CAM-A",
                "ip":          "192.168.10.11",
                "port":        5024,
                "server_name": "Genie_M1600_1"
            }
        }

        返回格式：
        {
            "serial": "SN-00123",
            "name": "CAM-A",
            "ip": "192.168.10.11",
            "server_name": "Genie_M1600_1"
        }
        """
        node = layout.get("connected_camera")
        if not node or not isinstance(node, dict):
            return None

        # 至少需要 server_name 或 IP 才能匹配相机
        server_name = node.get("server_name", "").strip()
        ip = node.get("ip", "").strip()
        if not server_name and not ip:
            return None

        return {
            "serial": node.get("serial", ""),
            "name": node.get("name", ""),
            "ip": ip,
            "server_name": server_name,
        }

    def find_matching_sapera_camera(self, camera_info: dict) -> Optional[SaperaCameraInfo]:
        """
        在当前 Sapera 扫描结果中按优先级匹配目标相机。

        Args:
            camera_info: 包含相机标识信息的字典（来自 parse_camera_from_layout）

        优先级：
          1. server_name 精确匹配（最可靠）
          2. 序列号精确匹配
          3. 用户名 + IP 同时匹配
          4. 仅 IP 匹配（兜底）

        返回匹配到的 SaperaCameraInfo，或 None。
        """
        candidates = self._sapera_discovery.last_results
        if not candidates:
            return None

        server_name = camera_info.get("server_name", "").strip()
        serial = camera_info.get("serial", "").strip()
        name = camera_info.get("name", "").strip()
        ip = camera_info.get("ip", "").strip()

        # ── 优先级 1：server_name 匹配（最可靠）──
        if server_name:
            for cam in candidates:
                if cam.server_name == server_name:
                    return cam

        # ── 优先级 2：序列号匹配 ──
        if serial:
            for cam in candidates:
                cam_serial = (cam.device_info or {}).get("serial", "").strip()
                if cam_serial and cam_serial == serial:
                    return cam

        # ── 优先级 3：用户名 + IP 同时匹配 ──
        if name and ip:
            for cam in candidates:
                info = cam.device_info or {}
                cam_ip = info.get("ip_address", "").strip()
                cam_name = info.get("user_id", "").strip()
                if cam_ip == ip and cam_name == name:
                    return cam

        # ── 优先级 4：仅 IP 匹配（兜底）──
        if ip:
            for cam in candidates:
                cam_ip = (cam.device_info or {}).get("ip_address", "").strip()
                if cam_ip == ip:
                    return cam

        return None

    @staticmethod
    def inject_camera_to_layout(layout: dict, camera: SaperaCameraInfo) -> dict:
        """
        将当前Sapera相机信息写入 layout dict（保存方案时调用）。

        写入字段：serial、name（用户名/DeviceUserID）、ip、server_name。
        返回修改后的 layout dict（原地修改并返回）。
        """
        info = camera.device_info or {}
        node = {
            "serial":      info.get("serial", ""),
            "name":        info.get("user_id", "") or camera.display_name,
            "ip":          info.get("ip_address", ""),
            "port":        DEFAULT_CAMERA_PORT,
            "server_name": camera.server_name,
        }

        layout["connected_camera"] = node
        return layout


# 向后兼容别名（旧代码 `from managers.camera_manager import CameraManager` 仍可用）
CameraManager = EnhancedCameraManager
