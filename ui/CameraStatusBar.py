"""
相机状态栏组件

显示在主界面左上角（顶部状态栏右侧），包含：
- 状态指示灯（绿=已连接，黄闪烁=扫描/连接中，红=未连接/失败）
- 当前相机信息文本
- 相机选择下拉框
- 刷新按钮
- 切换连接按钮

权限控制：
- 管理员/技术员：所有控件可用
- 操作员：下拉框、刷新、切换按钮全部禁用，仅显示状态灯和信息文本
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading


# 延迟导入，避免循环依赖
def _get_camera_manager():
    from managers.camera_manager import CameraManager, ConnectionState
    return CameraManager(), ConnectionState


class CameraStatusBar(tk.Frame):
    """
    相机状态栏 Frame，可直接 pack/grid 到任意父容器。

    参数：
        parent      父容器
        username    当前登录用户名（用于写日志）
        role        当前用户角色（"管理员"/"技术员"/"操作员"）
        bg          背景色，默认与顶部状态栏一致 (#808080)
    """

    # 状态灯颜色
    _COLOR_CONNECTED    = "#00CC44"   # 绿
    _COLOR_SCANNING     = "#FFCC00"   # 黄
    _COLOR_DISCONNECTED = "#CC2200"   # 红

    def __init__(self, parent, username: str, role: str, bg: str = "#808080", **kwargs):
        super().__init__(parent, bg=bg, **kwargs)

        self.username = username
        self.role = role
        self._bg = bg

        # 销毁标志：控件销毁后阻止后台回调访问 UI
        self._destroyed = False

        # 状态灯闪烁控制
        self._blink_job = None
        self._blink_visible = True

        # 当前下拉框选项列表（CameraInfo 对象）
        self._camera_list = []

        # 获取 CameraManager 单例
        self._manager, self._ConnectionState = _get_camera_manager()

        # 构建 UI
        self._build_ui()

        # 注册回调
        self._manager.on_state_change(self._on_state_change)
        self._manager.on_scan_complete(self._on_scan_complete)

        # 根据当前状态初始化显示
        self._refresh_display(self._manager.state, self._manager.current_camera)

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self):
        """构建状态栏内所有控件"""
        is_operator = (self.role == "操作员")

        # ── 状态指示灯 ──
        self._led_canvas = tk.Canvas(
            self, width=14, height=14,
            bg=self._bg, highlightthickness=0
        )
        self._led_canvas.pack(side=tk.LEFT, padx=(6, 2), pady=4)
        self._led_oval = self._led_canvas.create_oval(
            2, 2, 12, 12,
            fill=self._COLOR_DISCONNECTED, outline=""
        )

        # ── 当前相机信息文本 ──
        self._info_var = tk.StringVar(value="未连接")
        tk.Label(
            self,
            textvariable=self._info_var,
            fg="white", bg=self._bg,
            font=("Microsoft YaHei UI", 9)
        ).pack(side=tk.LEFT, padx=(0, 8))

        # ── 分隔线 ──
        tk.Frame(self, width=1, bg="#AAAAAA").pack(side=tk.LEFT, fill=tk.Y, pady=3)

        # ── 相机选择下拉框 ──
        self._combo_var = tk.StringVar(value="无可用相机")
        self._combo = ttk.Combobox(
            self,
            textvariable=self._combo_var,
            state="disabled" if is_operator else "readonly",
            font=("Microsoft YaHei UI", 9),
            width=22,
        )
        self._combo["values"] = ["无可用相机"]
        self._combo.pack(side=tk.LEFT, padx=(8, 4), pady=3)

        # ── 刷新按钮 ──
        self._btn_refresh = tk.Button(
            self,
            text="刷新",
            font=("Microsoft YaHei UI", 8),
            bg="#5A5A5A" if not is_operator else "#3A3A3A",
            fg="white" if not is_operator else "#888888",
            relief=tk.FLAT,
            bd=1,
            padx=6,
            cursor="hand2" if not is_operator else "arrow",
            state=tk.DISABLED if is_operator else tk.NORMAL,
            command=self._on_refresh_click,
        )
        self._btn_refresh.pack(side=tk.LEFT, padx=(0, 4), pady=3)

        # ── 切换连接按钮 ──
        self._btn_switch = tk.Button(
            self,
            text="切换连接",
            font=("Microsoft YaHei UI", 8),
            bg="#2E6DA4" if not is_operator else "#3A3A3A",
            fg="white" if not is_operator else "#888888",
            relief=tk.FLAT,
            bd=1,
            padx=6,
            cursor="hand2" if not is_operator else "arrow",
            state=tk.DISABLED if is_operator else tk.NORMAL,
            command=self._on_switch_click,
        )
        self._btn_switch.pack(side=tk.LEFT, padx=(0, 6), pady=3)

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _on_refresh_click(self):
        """点击刷新按钮：触发重新扫描"""
        if self._manager.is_scanning:
            return
        # 清空列表，显示扫描中提示
        self._camera_list = []
        self._combo["values"] = ["扫描中…"]
        self._combo_var.set("扫描中…")
        self._manager.start_scan()

    def _on_switch_click(self):
        """点击切换连接按钮"""
        selected = self._combo_var.get()
        if not selected or selected in ("无可用相机", "扫描中…"):
            messagebox.showwarning("切换相机", "请先选择一台可用相机", parent=self)
            return

        # 找到对应的 CameraInfo
        target = next(
            (c for c in self._camera_list if c.display_name == selected),
            None
        )
        if target is None:
            messagebox.showwarning("切换相机", "未找到所选相机信息", parent=self)
            return

        # 若目标与当前相同，忽略
        current = self._manager.current_camera
        if current and current == target:
            messagebox.showinfo("切换相机", "已是当前连接的相机，无需切换", parent=self)
            return

        # 检查是否有检测正在运行
        if self._is_detection_running():
            confirm = messagebox.askyesno(
                "检测运行中",
                "当前检测正在运行，切换相机需要先停止检测。\n\n是否停止检测并切换？",
                parent=self,
            )
            if not confirm:
                return
            # 用户确认后停止检测
            self._stop_detection()

        # 执行切换（异步）
        self._manager.switch_camera(
            target=target,
            user_name=self.username,
            user_role=self.role,
            on_result=self._on_switch_result,
        )

    def _is_detection_running(self) -> bool:
        """判断当前是否有检测在运行"""
        try:
            # 通过 winfo_toplevel 找到主窗口，再访问 run_interface
            root = self.winfo_toplevel()
            run_interface = getattr(root, '_app_run_interface', None)
            if run_interface is None:
                # 尝试从主窗口实例获取
                app = getattr(root, '_app_instance', None)
                if app:
                    run_interface = getattr(app, 'run_interface', None)
            if run_interface and hasattr(run_interface, 'is_running'):
                return bool(run_interface.is_running)
        except Exception:
            pass
        return False

    def _stop_detection(self):
        """停止当前检测"""
        try:
            root = self.winfo_toplevel()
            run_interface = getattr(root, '_app_run_interface', None)
            if run_interface is None:
                app = getattr(root, '_app_instance', None)
                if app:
                    run_interface = getattr(app, 'run_interface', None)
            if run_interface and hasattr(run_interface, 'stop_inspection'):
                run_interface.stop_inspection()
        except Exception as e:
            print(f"[CameraStatusBar] 停止检测失败: {e}")

    def _on_switch_result(self, success: bool, message: str):
        """切换完成回调（在后台线程中调用，需 after 回到主线程）"""
        def _show():
            if not success:
                messagebox.showerror(
                    "切换相机失败",
                    f"{message}\n\n已自动恢复到上一次成功的连接。",
                    parent=self,
                )
        self.after(0, _show)

    # ------------------------------------------------------------------
    # CameraManager 回调（后台线程调用，需 after 回到主线程）
    # ------------------------------------------------------------------

    def _on_state_change(self, state: str, camera):
        """连接状态变化回调"""
        if self._destroyed:
            return
        self.after(0, lambda: self._safe_refresh_display(state, camera))

    def _on_scan_complete(self, cameras: list):
        """扫描完成回调"""
        if self._destroyed:
            return
        self.after(0, lambda: self._safe_update_camera_list(cameras))

    def _safe_refresh_display(self, state, camera):
        """带销毁检查的 _refresh_display"""
        if self._destroyed:
            return
        try:
            self._refresh_display(state, camera)
        except Exception:
            pass

    def _safe_update_camera_list(self, cameras):
        """带销毁检查的 _update_camera_list"""
        if self._destroyed:
            return
        try:
            self._update_camera_list(cameras)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI 刷新
    # ------------------------------------------------------------------

    def _refresh_display(self, state: str, camera):
        """根据状态更新状态灯和信息文本"""
        CS = self._ConnectionState

        # 停止之前的闪烁
        self._stop_blink()

        if state == CS.CONNECTED and camera:
            self._set_led(self._COLOR_CONNECTED)
            self._info_var.set(f"当前相机：{camera.display_name}")
            # 同步下拉框选中项
            if camera.display_name in self._combo["values"]:
                self._combo_var.set(camera.display_name)

        elif state == CS.CONNECTING:
            self._start_blink()
            self._info_var.set("连接中…")

        elif state == CS.FAILED:
            self._set_led(self._COLOR_DISCONNECTED)
            self._info_var.set("连接失败")

        else:  # DISCONNECTED
            self._set_led(self._COLOR_DISCONNECTED)
            self._info_var.set("未连接")

    def _update_camera_list(self, cameras: list):
        """扫描完成后更新下拉框"""
        self._camera_list = cameras

        if cameras:
            names = [c.display_name for c in cameras]
            self._combo["values"] = names
            # 如果当前连接的相机在列表中，保持选中；否则选第一个
            current = self._manager.current_camera
            if current and current.display_name in names:
                self._combo_var.set(current.display_name)
            else:
                self._combo_var.set(names[0])
        else:
            self._combo["values"] = ["无可用相机"]
            self._combo_var.set("无可用相机")

        # 恢复状态灯（扫描完成后回到连接状态）
        self._refresh_display(self._manager.state, self._manager.current_camera)

    # ------------------------------------------------------------------
    # 状态灯控制
    # ------------------------------------------------------------------

    def _set_led(self, color: str):
        """设置状态灯颜色（静态）"""
        self._led_canvas.itemconfig(self._led_oval, fill=color)

    def _start_blink(self):
        """开始黄色闪烁"""
        self._blink_visible = True
        self._set_led(self._COLOR_SCANNING)
        self._blink_job = self.after(400, self._blink_tick)

    def _blink_tick(self):
        """闪烁定时器"""
        self._blink_visible = not self._blink_visible
        color = self._COLOR_SCANNING if self._blink_visible else self._bg
        self._set_led(color)
        self._blink_job = self.after(400, self._blink_tick)

    def _stop_blink(self):
        """停止闪烁"""
        if self._blink_job is not None:
            self.after_cancel(self._blink_job)
            self._blink_job = None

    # ------------------------------------------------------------------
    # 公开接口（供主窗口调用）
    # ------------------------------------------------------------------

    def trigger_initial_scan(self):
        """
        触发启动时的自动扫描（由主窗口在初始化完成后调用）。
        """
        self._camera_list = []
        self._combo["values"] = ["扫描中…"]
        self._combo_var.set("扫描中…")
        self._manager.start_scan()

    def destroy(self):
        """销毁时停止闪烁定时器，标记已销毁"""
        self._destroyed = True
        self._stop_blink()
        super().destroy()
