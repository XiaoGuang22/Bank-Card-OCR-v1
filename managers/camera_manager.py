"""
相机连接管理器（单例）

负责：
- 维护当前连接的相机信息
- 执行手动/自动切换
- 失败时自动回退到上一次成功的连接
- 将切换操作写入审计日志
"""

import threading
from typing import Optional, Callable, TYPE_CHECKING

from camera.camera_discovery import CameraInfo, CameraDiscovery, DEFAULT_CAMERA_PORT
from managers.audit_log_manager import AuditLogManager

if TYPE_CHECKING:
    pass


# 连接状态枚举
class ConnectionState:
    DISCONNECTED = "disconnected"   # 未连接
    CONNECTING   = "connecting"     # 连接中
    CONNECTED    = "connected"      # 已连接
    FAILED       = "failed"         # 连接失败


class CameraManager:
    """
    相机连接管理器（单例）。

    外部通过 CameraManager() 获取同一实例。
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

        # 当前连接的相机
        self._current: Optional[CameraInfo] = None
        # 上一次成功连接的相机（用于失败回退）
        self._last_successful: Optional[CameraInfo] = None
        # 连接状态
        self._state: str = ConnectionState.DISCONNECTED

        # 扫描器
        self._discovery = CameraDiscovery()

        # 日志管理器
        self._log = AuditLogManager()

        # 状态变化回调列表：fn(state: str, camera: Optional[CameraInfo])
        self._state_callbacks: list = []
        # 扫描完成回调列表：fn(cameras: list)
        self._scan_callbacks: list = []

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def current_camera(self) -> Optional[CameraInfo]:
        return self._current

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED

    @property
    def available_cameras(self):
        return self._discovery.last_results

    @property
    def is_scanning(self) -> bool:
        return self._discovery.is_scanning

    # ------------------------------------------------------------------
    # 回调注册
    # ------------------------------------------------------------------

    def on_state_change(self, callback: Callable[[str, Optional[CameraInfo]], None]):
        """注册连接状态变化回调。callback(state, camera_info)"""
        self._state_callbacks.append(callback)

    def on_scan_complete(self, callback: Callable[[list], None]):
        """注册扫描完成回调。callback(camera_list)"""
        self._scan_callbacks.append(callback)

    def _notify_state(self, state: str, camera: Optional[CameraInfo]):
        self._state = state
        for cb in self._state_callbacks:
            try:
                cb(state, camera)
            except Exception as e:
                print(f"[CameraManager] 状态回调异常: {e}")

    def _notify_scan(self, cameras: list):
        for cb in self._scan_callbacks:
            try:
                cb(cameras)
            except Exception as e:
                print(f"[CameraManager] 扫描回调异常: {e}")

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------

    def start_scan(self, blocking: bool = False):
        """
        启动局域网相机扫描。
        扫描完成后触发 on_scan_complete 回调。
        """
        self._notify_state(ConnectionState.CONNECTING, self._current)
        self._discovery.scan(
            on_complete=self._on_scan_done,
            blocking=blocking,
        )

    def _on_scan_done(self, cameras: list):
        # 扫描完成后恢复之前的连接状态
        self._notify_state(self._state if self._state != ConnectionState.CONNECTING
                           else (ConnectionState.CONNECTED if self._current else ConnectionState.DISCONNECTED),
                           self._current)
        self._notify_scan(cameras)

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
                    # 超时无响应：不是相机服务
                    return False, f"握手超时，对端不是相机服务：{camera.ip}:{camera.port}"
                except Exception:
                    # 连接后立即断开：不是相机服务
                    return False, f"握手失败，对端不是相机服务：{camera.ip}:{camera.port}"

        except _socket.timeout:
            return False, f"连接超时：{camera.ip}:{camera.port}"
        except ConnectionRefusedError:
            return False, f"连接被拒绝：{camera.ip}:{camera.port}"
        except Exception as e:
            return False, f"连接失败：{e}"

    # ------------------------------------------------------------------
    # 断开连接
    # ------------------------------------------------------------------

    def disconnect(self):
        """断开当前连接"""
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
