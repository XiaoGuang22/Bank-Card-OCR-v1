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

集成增强的相机发现和切换功能，支持 Sapera SDK 和网络相机。
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading


# 延迟导入，避免循环依赖
def _get_camera_managers():
    from managers.camera_manager import EnhancedCameraManager
    from camera.sapera_camera_discovery import get_sapera_discovery
    from camera.sapera_camera_manager import get_sapera_camera_manager
    from camera.camera_info_model import CameraConnectionStatus
    return EnhancedCameraManager(), get_sapera_discovery(), get_sapera_camera_manager(), CameraConnectionStatus


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

        # 当前下拉框选项列表（相机信息对象）
        self._camera_list = []

        # 获取管理器实例
        self._manager, self._discovery, self._sapera_manager, self._ConnectionStatus = _get_camera_managers()

        # 构建 UI
        self._build_ui()

        # 注册回调
        self._manager.on_state_change(self._on_state_change)
        self._manager.on_scan_complete(self._on_scan_complete)
        
        # 注册 Sapera 管理器回调
        self._sapera_manager.add_state_callback(self._on_sapera_state_change)

        # 根据当前状态初始化显示
        current_camera = self._manager.current_camera or self._sapera_manager.current_camera
        if current_camera:
            self._refresh_display(self._ConnectionStatus.CONNECTED, current_camera)
        else:
            self._refresh_display(self._ConnectionStatus.DISCONNECTED, None)

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
        if self._manager.is_scanning or self._discovery.is_scanning:
            return
        
        # ★★★ 清空当前列表，避免显示已断开的相机 ★★★
        self._camera_list = []
        self._combo["values"] = ["扫描中…"]
        self._combo_var.set("扫描中…")
        
        # 设置扫描状态
        self._refresh_display(self._ConnectionStatus.SCANNING, None)
        
        # 启动扫描
        self._manager.start_scan(force_refresh=True)

    def _on_switch_click(self):
        """点击切换连接按钮"""
        selected = self._combo_var.get()
        if not selected or selected in ("无可用相机", "扫描中…"):
            messagebox.showwarning("切换相机", "请先选择一台可用相机", parent=self)
            return

        # 找到对应的相机信息
        target = None
        for camera in self._camera_list:
            # 支持 Sapera 相机和网络相机的显示名称匹配
            display_name = getattr(camera, 'formatted_display_name', None) or getattr(camera, 'display_name', str(camera))
            if display_name == selected:
                target = camera
                break
        
        if target is None:
            messagebox.showwarning("切换相机", "未找到所选相机信息", parent=self)
            return

        # 若目标与当前相同，忽略
        current = self._manager.current_camera or self._sapera_manager.current_camera
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
        self._execute_camera_switch(target)
    
    def _execute_camera_switch(self, target):
        """执行相机切换"""
        # 判断是 Sapera 相机还是网络相机
        if hasattr(target, 'server_name') and target.server_name:
            # Sapera 相机切换
            threading.Thread(
                target=self._switch_sapera_camera,
                args=(target,),
                daemon=True
            ).start()
        else:
            # 网络相机切换
            self._manager.switch_camera(
                target=target,
                user_name=self.username,
                user_role=self.role,
                on_result=self._on_switch_result,
            )
    
    def _switch_sapera_camera(self, target):
        """切换 Sapera 相机（在后台线程中执行）"""
        try:
            success, message = self._sapera_manager.switch_camera(target)
            # 线程安全的回调
            def callback():
                self._on_switch_result(success, message, self.role)
            
            try:
                self.after_idle(callback)
            except RuntimeError:
                import threading
                if threading.current_thread() is threading.main_thread():
                    callback()
                else:
                    def delayed_callback():
                        try:
                            self.after_idle(callback)
                        except:
                            pass
                    threading.Timer(0.1, delayed_callback).start()
                    
        except Exception as e:
            # 线程安全的错误回调
            def error_callback():
                self._on_switch_result(False, f"切换异常: {e}", self.role)
            
            try:
                self.after_idle(error_callback)
            except RuntimeError:
                import threading
                if threading.current_thread() is threading.main_thread():
                    error_callback()
                else:
                    def delayed_error_callback():
                        try:
                            self.after_idle(error_callback)
                        except:
                            pass
                    threading.Timer(0.1, delayed_error_callback).start()

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

    def _on_switch_result(self, success: bool, message: str, user_role: str = ""):
        """切换完成回调（在后台线程中调用，需要线程安全的UI更新）"""
        def _show():
            if self._destroyed:
                return
            if success:
                # 切换成功后提示用户确认旧图像，防止误用
                self._notify_stale_image()
            else:
                messagebox.showerror(
                    "切换相机失败",
                    f"{message}\n\n已自动恢复到上一次成功的连接。",
                    parent=self,
                )
        
        if self._destroyed:
            return
        
        # 线程安全的UI更新
        try:
            self.after_idle(_show)
        except RuntimeError:
            import threading
            if threading.current_thread() is threading.main_thread():
                _show()
            else:
                def delayed_update():
                    try:
                        self.after_idle(_show)
                    except:
                        pass
                threading.Timer(0.1, delayed_update).start()

    def _notify_stale_image(self):
        """
        FC-17：相机切换成功后，清除主窗口当前显示的旧图像，
        并提示用户重新拍照或确认。
        """
        try:
            root = self.winfo_toplevel()
            app = getattr(root, '_app_instance', None)

            # 尝试清除运行界面的当前帧，避免误用旧图像
            run_interface = getattr(root, '_app_run_interface', None)
            if run_interface is None and app:
                run_interface = getattr(app, 'run_interface', None)
            if run_interface and hasattr(run_interface, 'clear_current_frame'):
                run_interface.clear_current_frame()

            # 获取当前相机名称
            current_camera = self._manager.current_camera or self._sapera_manager.current_camera
            camera_name = "新相机"
            if current_camera:
                if hasattr(current_camera, 'formatted_display_name'):
                    camera_name = current_camera.formatted_display_name
                elif hasattr(current_camera, 'display_name'):
                    camera_name = current_camera.display_name
                else:
                    camera_name = str(current_camera)

            # 弹出提示（非阻塞）
            messagebox.showinfo(
                "相机已切换",
                f"相机已切换至 {camera_name}。\n\n"
                "当前图像已清除，请重新拍照或确认后再继续检测。",
                parent=self,
            )
        except Exception as e:
            print(f"[CameraStatusBar] 旧图像提示失败: {e}")

    # ------------------------------------------------------------------
    # 回调处理（后台线程调用，需 after 回到主线程）
    # ------------------------------------------------------------------

    def _on_state_change(self, state: str, camera):
        """连接状态变化回调（来自 EnhancedCameraManager）"""
        if self._destroyed:
            return
        # 检查是否在主线程中
        try:
            self.after_idle(lambda: self._safe_refresh_display(state, camera))
        except RuntimeError:
            # 如果不在主线程，使用线程安全的方式
            import threading
            if threading.current_thread() is threading.main_thread():
                self._safe_refresh_display(state, camera)
            else:
                # 在后台线程中，延迟执行
                def delayed_update():
                    try:
                        self.after_idle(lambda: self._safe_refresh_display(state, camera))
                    except:
                        pass
                threading.Timer(0.1, delayed_update).start()
    
    def _on_sapera_state_change(self, status, camera):
        """Sapera 相机状态变化回调"""
        if self._destroyed:
            return
        # 将 CameraConnectionStatus 转换为字符串状态
        state_map = {
            self._ConnectionStatus.CONNECTED: "connected",
            self._ConnectionStatus.CONNECTING: "connecting", 
            self._ConnectionStatus.SCANNING: "scanning",
            self._ConnectionStatus.DISCONNECTED: "disconnected",
            self._ConnectionStatus.ERROR: "failed"
        }
        state_str = state_map.get(status, "disconnected")
        
        # 线程安全的UI更新
        try:
            self.after_idle(lambda: self._safe_refresh_display(state_str, camera))
        except RuntimeError:
            import threading
            if threading.current_thread() is threading.main_thread():
                self._safe_refresh_display(state_str, camera)
            else:
                def delayed_update():
                    try:
                        self.after_idle(lambda: self._safe_refresh_display(state_str, camera))
                    except:
                        pass
                threading.Timer(0.1, delayed_update).start()

    def _on_scan_complete(self, sapera_cameras: list, network_cameras: list):
        """扫描完成回调（来自 EnhancedCameraManager）"""
        if self._destroyed:
            return
        # 合并两种类型的相机
        all_cameras = list(sapera_cameras) + list(network_cameras)
        
        # 线程安全的UI更新
        try:
            self.after_idle(lambda: self._safe_update_camera_list(all_cameras))
        except RuntimeError:
            import threading
            if threading.current_thread() is threading.main_thread():
                self._safe_update_camera_list(all_cameras)
            else:
                def delayed_update():
                    try:
                        self.after_idle(lambda: self._safe_update_camera_list(all_cameras))
                    except:
                        pass
                threading.Timer(0.1, delayed_update).start()

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
        """根据状态更新状态灯和信息文本（不修改下拉框列表）"""
        # 停止之前的闪烁
        self._stop_blink()

        if state == "connected" and camera:
            self._set_led(self._COLOR_CONNECTED)

            # 获取相机显示名称
            display_name = self._get_camera_display_name(camera)

            self._info_var.set(f"当前相机：{display_name}")

            # 只更新选中项，不往列表里追加
            # 注意：不在这里修改下拉框的 values，只修改当前选中项
            vals = list(self._combo["values"])
            if vals and vals != ["无可用相机"] and vals != ["扫描中…"]:
                # 如果列表中有这个相机，选中它
                if display_name in vals:
                    self._combo_var.set(display_name)
                # 如果列表中没有这个相机，不做任何操作（等待扫描完成后更新）
            else:
                # 如果列表为空或显示占位符，暂时不更新
                # 等待扫描完成后由 _update_camera_list 统一处理
                pass

        elif state in ("connecting", "scanning"):
            self._start_blink()
            self._info_var.set("连接中…" if state == "connecting" else "扫描中…")

        elif state == "failed":
            self._set_led(self._COLOR_DISCONNECTED)
            self._info_var.set("连接失败")

        else:  # disconnected
            self._set_led(self._COLOR_DISCONNECTED)
            self._info_var.set("未连接")

    def _update_camera_list(self, cameras: list):
        """
        扫描完成后用新列表完整替换下拉框，智能去重和合并
        
        逻辑：
        1. 遍历新扫描的相机列表
        2. 对于每个相机，检查是否已经在列表中（基于相等性比较）
        3. 如果存在旧版本，用新版本替换（新版本通常有更完整的信息，如IP地址）
        4. 如果不存在，添加到列表
        5. ★★★ 注意：不自动添加当前连接的相机，只使用扫描结果 ★★★
        """
        # 创建一个字典，用于快速查找和去重（基于 server_name）
        camera_dict = {}
        
        # ★★★ 修改：不自动添加当前连接的相机，只使用扫描结果 ★★★
        # 这样可以确保拔掉相机后，刷新时会清空列表
        
        # 添加新扫描的相机
        if cameras:
            for camera in cameras:
                key = self._get_camera_key(camera)
                if key:
                    # 如果已存在，比较哪个版本更完整
                    if key in camera_dict:
                        existing = camera_dict[key]
                        # 如果新相机有IP而旧相机没有，用新相机替换
                        if self._is_camera_more_complete(camera, existing):
                            camera_dict[key] = camera
                    else:
                        camera_dict[key] = camera
        
        # 转换为列表
        self._camera_list = list(camera_dict.values())
        
        # 获取当前连接的相机（用于判断选中项）
        current = self._manager.current_camera or self._sapera_manager.current_camera
        
        # 构建显示名称列表（已经去重）
        if self._camera_list:
            names = []
            for camera in self._camera_list:
                name = self._get_camera_display_name(camera)
                names.append(name)
            
            # 完整替换列表
            self._combo["values"] = names
            
            # 设置当前选中项
            if current:
                current_name = self._get_camera_display_name(current)
                # 只有当前相机在扫描结果中时，才选中它
                if current_name in names:
                    self._combo_var.set(current_name)
                else:
                    # 当前相机不在扫描结果中（可能已断开），选中第一个
                    self._combo_var.set(names[0])
            else:
                self._combo_var.set(names[0])
        else:
            # ★★★ 扫描结果为空，显示"无可用相机" ★★★
            self._combo["values"] = ["无可用相机"]
            self._combo_var.set("无可用相机")
        
        # 更新状态灯和文字
        # ★★★ 如果扫描结果为空，设置为断开状态 ★★★
        if self._camera_list:
            # ★★★ 优先使用扫描结果中的相机信息，而不是当前连接的相机 ★★★
            # 因为当前连接的相机可能是旧的，扫描结果才是最新的
            if current and current in self._camera_list:
                # 当前相机在扫描结果中，使用当前相机
                display_camera = current
            elif self._camera_list:
                # 当前相机不在扫描结果中，使用扫描结果中的第一个
                display_camera = self._camera_list[0]
            else:
                display_camera = current
            
            current_state = "connected" if display_camera else "disconnected"
            self._refresh_display(current_state, display_camera)
        else:
            # 扫描结果为空，设置为断开状态
            self._refresh_display("disconnected", None)
    
    def _get_camera_key(self, camera) -> str:
        """
        获取相机的唯一标识键
        
        优先使用 server_name（Sapera相机），其次使用 IP+端口（网络相机）
        """
        if hasattr(camera, 'server_name') and camera.server_name:
            return f"sapera:{camera.server_name}"
        elif hasattr(camera, 'ip') and camera.ip:
            port = getattr(camera, 'port', 5024)
            return f"network:{camera.ip}:{port}"
        return None
    
    def _is_camera_more_complete(self, new_camera, existing_camera) -> bool:
        """
        判断新相机信息是否比现有相机更完整
        
        主要比较是否有IP地址信息
        """
        # 对于 Sapera 相机，检查 device_info 中的 ip_address
        if hasattr(new_camera, 'device_info') and hasattr(existing_camera, 'device_info'):
            new_ip = (new_camera.device_info or {}).get('ip_address', '').strip()
            existing_ip = (existing_camera.device_info or {}).get('ip_address', '').strip()
            
            # 如果新相机有IP而旧相机没有，新相机更完整
            if new_ip and not existing_ip:
                return True
            # 如果两者都有IP或都没有IP，保持现有的
            return False
        
        # 对于网络相机，默认保持现有的
        return False
    
    def _get_camera_display_name(self, camera) -> str:
        """获取相机的显示名称"""
        if hasattr(camera, 'formatted_display_name'):
            return camera.formatted_display_name
        elif hasattr(camera, 'display_name'):
            return camera.display_name
        else:
            return str(camera)

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
        
        # 设置扫描状态
        self._refresh_display("scanning", None)
        
        # 启动扫描
        self._manager.start_scan(force_refresh=True)

    def destroy(self):
        """销毁时停止闪烁定时器，标记已销毁"""
        self._destroyed = True
        self._stop_blink()
        super().destroy()
