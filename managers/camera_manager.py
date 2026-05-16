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
from typing import Optional, Callable, TYPE_CHECKING, List, Union

from camera.camera_discovery import CameraInfo, DEFAULT_CAMERA_PORT
from camera.sapera_camera_discovery import (
    SaperaCameraDiscovery, SaperaCameraController, SaperaCameraInfo,
    get_sapera_discovery, get_sapera_controller
)
from camera.sapera_camera_manager import get_sapera_camera_manager
from managers.audit_log_manager import AuditLogManager

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

        # 当前连接的相机（可能是Sapera或网络相机）
        self._current_camera: Optional[Union[SaperaCameraInfo, CameraInfo]] = None
        # 上一次成功连接的相机（用于失败回退）
        self._last_successful: Optional[Union[SaperaCameraInfo, CameraInfo]] = None
        # 连接状态
        self._state: str = ConnectionState.DISCONNECTED

        # Sapera 扫描器、控制器与切换管理器
        self._sapera_discovery = get_sapera_discovery()
        self._sapera_controller = get_sapera_controller()
        self._sapera_manager = get_sapera_camera_manager()

        # 日志管理器
        self._log = AuditLogManager()

        # 状态变化回调列表：fn(state: str, camera: Optional[Union[SaperaCameraInfo, CameraInfo]])
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

    def on_state_change(self, callback: Callable[[str, Optional[Union[SaperaCameraInfo, CameraInfo]]], None]):
        """注册连接状态变化回调。callback(state, camera_info)"""
        self._state_callbacks.append(callback)

    def on_scan_complete(self, callback: Callable[[List[SaperaCameraInfo]], None]):
        """注册扫描完成回调。callback(sapera_cameras)"""
        self._scan_callbacks.append(callback)

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
        target,
        user_name: str,
        user_role: str,
        on_result: Optional[Callable[[bool, str, str], None]] = None,
    ):
        """
        手动切换到目标相机（异步执行）。

        target 可以是：
          - SaperaCameraInfo：直接使用，跳过匹配步骤
          - CameraInfo：先用三级优先级在扫描结果中匹配，再切换

        Args:
            target: 目标相机
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
        target,
        user_name: str,
        user_role: str,
        on_result: Optional[Callable[[bool, str, str], None]] = None,
    ):
        """
        加载方案时系统自动切换相机（异步执行）。
        与手动切换逻辑相同，仅日志 action 不同。

        target 可以是 SaperaCameraInfo 或 CameraInfo。
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

    def _match_sapera_camera(self, target: CameraInfo) -> Optional[SaperaCameraInfo]:
        """
        从最近一次 Sapera 扫描结果中按三级优先级匹配目标相机。
        （内部使用，外部请调用 find_matching_sapera_camera）
        """
        return self.find_matching_sapera_camera(target)

    def _do_switch(
        self,
        target,
        user_name: str,
        user_role: str,
        action: str,
        on_result: Optional[Callable],
    ):
        """
        核心切换逻辑：
        1. 若 target 已是 SaperaCameraInfo，直接使用；
           否则用三级优先级在扫描结果中匹配，找不到则报失败。
        2. 委托 SaperaCameraManager.switch_camera() 执行硬件切换。
        3. 失败时回退到上一次成功的连接。
        4. 写审计日志，回调传递 user_role（供 UI 区分操作员/管理员行为）。
        """
        from camera.sapera_camera_discovery import SaperaCameraInfo as _SCI

        old_camera = self._current_camera
        old_ip = ""
        old_display = "无"
        if old_camera:
            if isinstance(old_camera, _SCI):
                old_ip = (old_camera.device_info or {}).get("ip_address", "")
                old_display = old_camera.formatted_display_name
            else:
                old_ip = getattr(old_camera, "ip", "")
                old_display = getattr(old_camera, "display_name", str(old_camera))

        self._notify_state(ConnectionState.CONNECTING, old_camera)

        # ── 步骤 1：解析出 SaperaCameraInfo ──
        if isinstance(target, _SCI):
            # 调用方已经做了匹配，直接使用
            sapera_target = target
        else:
            # CameraInfo → 三级优先级匹配（扫描结果中查找）
            sapera_target = self.find_matching_sapera_camera(target)

            if sapera_target is None:
                # 扫描结果为空或 device_info 不完整（设备被占用时常见）
                # 兜底：用 server_name 直接构造最小 SaperaCameraInfo，
                # 让 SaperaCameraManager.switch_camera → CameraController.switch_to
                # 凭 server_name 完成硬件切换，不依赖扫描结果
                server_name = getattr(target, "server_name", "").strip()
                if server_name:
                    sapera_target = _SCI(
                        server_name=server_name,
                        server_index=0,
                        resource_count=1,
                        display_name=getattr(target, "name", "") or server_name,
                        is_accessible=True,
                        device_info={
                            "ip_address": getattr(target, "ip", ""),
                            "serial":     getattr(target, "serial", ""),
                            "user_id":    getattr(target, "name", ""),
                        },
                    )
                    print(
                        f"[CameraManager] 扫描结果中未找到目标相机，"
                        f"降级为 server_name 直接切换: {server_name}"
                    )
                else:
                    # 连 server_name 都没有，真正无法切换
                    self._current_camera = old_camera
                    self._notify_state(
                        ConnectionState.CONNECTED if old_camera else ConnectionState.FAILED,
                        old_camera,
                    )
                    msg = (
                        f"无法切换相机：扫描结果为空且方案未记录 server_name"
                        f"（序列号={getattr(target, 'serial', '')}，"
                        f"IP={getattr(target, 'ip', '')}）"
                    )
                    self._log.log(
                        user_name=user_name, user_role=user_role,
                        operation_type="control_settings", operation_action=action,
                        target_object=f"{old_display} → {getattr(target, 'display_name', str(target))}",
                        old_value=old_ip, new_value=getattr(target, "ip", ""),
                        operation_result="失败",
                    )
                    if on_result:
                        try:
                            on_result(False, msg, user_role)
                        except TypeError:
                            on_result(False, msg)
                    return

        # ── 步骤 2：委托 SaperaCameraManager 执行硬件切换 ──
        success, message = self._sapera_manager.switch_camera(sapera_target)

        if success:
            self._last_successful = self._current_camera
            self._current_camera = sapera_target
            self._notify_state(ConnectionState.CONNECTED, sapera_target)

            self._log.log(
                user_name=user_name, user_role=user_role,
                operation_type="control_settings", operation_action=action,
                target_object=f"{old_display} → {sapera_target.formatted_display_name}",
                old_value=old_ip,
                new_value=(sapera_target.device_info or {}).get("ip_address", ""),
                operation_result="成功",
            )
        else:
            # ── 步骤 3：失败回退 ──
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
                target_object=f"{old_display} → {sapera_target.formatted_display_name}",
                old_value=old_ip,
                new_value=(sapera_target.device_info or {}).get("ip_address", ""),
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
    def parse_camera_from_layout(layout: dict) -> Optional[CameraInfo]:
        """
        从方案文件的 connected_camera 节点解析 CameraInfo。

        匹配优先级（需求文档 3.5.2）：
          1. 序列号（serial）—— 最可靠，硬件唯一
          2. 用户名（name）+ IP —— 次选
          3. 仅 IP —— 兜底

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
        """
        node = layout.get("connected_camera")
        if not node or not isinstance(node, dict):
            return None

        ip = node.get("ip", "").strip()
        # 至少需要 IP 才能构造 CameraInfo
        if not ip:
            return None

        return CameraInfo(
            ip=ip,
            port=int(node.get("port", DEFAULT_CAMERA_PORT)),
            name=node.get("name", ""),
            serial=node.get("serial", ""),
            server_name=node.get("server_name", ""),
        )

    def find_matching_sapera_camera(self, target: CameraInfo):
        """
        在当前 Sapera 扫描结果中按优先级匹配目标相机。

        优先级：
          1. 序列号精确匹配
          2. 用户名 + IP 同时匹配
          3. 仅 IP 匹配（兜底）

        返回匹配到的 SaperaCameraInfo，或 None。
        """
        candidates = self._sapera_discovery.last_results
        if not candidates:
            return None

        # ── 优先级 1：序列号匹配 ──
        if target.serial:
            for cam in candidates:
                cam_serial = (cam.device_info or {}).get("serial", "").strip()
                if cam_serial and cam_serial == target.serial:
                    return cam

        # ── 优先级 2：用户名 + IP 同时匹配 ──
        if target.name and target.ip:
            for cam in candidates:
                info = cam.device_info or {}
                cam_ip = info.get("ip_address", "").strip()
                cam_name = info.get("user_id", "").strip()
                if cam_ip == target.ip and cam_name == target.name:
                    return cam

        # ── 优先级 3：仅 IP 匹配（兜底）──
        if target.ip:
            for cam in candidates:
                cam_ip = (cam.device_info or {}).get("ip_address", "").strip()
                if cam_ip == target.ip:
                    return cam

        return None

    @staticmethod
    def inject_camera_to_layout(layout: dict, camera) -> dict:
        """
        将当前相机信息写入 layout dict（保存方案时调用）。

        支持 CameraInfo 和 SaperaCameraInfo 两种类型。
        写入四个字段：serial、name（用户名/DeviceUserID）、ip、server_name。
        返回修改后的 layout dict（原地修改并返回）。
        """
        from camera.sapera_camera_discovery import SaperaCameraInfo

        if isinstance(camera, SaperaCameraInfo):
            info = camera.device_info or {}
            node = {
                "serial":      info.get("serial", ""),
                "name":        info.get("user_id", "") or camera.display_name,
                "ip":          info.get("ip_address", ""),
                "port":        DEFAULT_CAMERA_PORT,
                "server_name": camera.server_name,
            }
        else:
            # CameraInfo
            node = {
                "serial":      getattr(camera, "serial", ""),
                "name":        getattr(camera, "name", ""),
                "ip":          camera.ip,
                "port":        camera.port,
                "server_name": getattr(camera, "server_name", ""),
            }

        layout["connected_camera"] = node
        return layout


# 向后兼容别名（旧代码 `from managers.camera_manager import CameraManager` 仍可用）
CameraManager = EnhancedCameraManager
