"""
解决方案管理面板 (SolutionManagementPanel)

支持两种构造方式：
  新接口（推荐）：SolutionManagementPanel(parent, workspace_manager, main_window)
  旧接口（向后兼容）：SolutionManagementPanel(parent, solutions_root, on_solution_selected)
"""

import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess


def _ask_directory_safe(title="选择目录"):
    """
    用 PowerShell 弹出文件夹选择对话框，避免 tkinter filedialog 在 Windows 上崩溃。
    返回选中的路径字符串，取消则返回空字符串。
    """
    script = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
        f"$d.Description = '{title}';"
        "$d.ShowNewFolderButton = $true;"
        "$r = $d.ShowDialog();"
        "if ($r -eq 'OK') { Write-Output $d.SelectedPath }"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=60
        )
        path = result.stdout.strip()
        return path
    except Exception:
        # 降级回 tkinter（万一 PowerShell 不可用）
        return filedialog.askdirectory(title=title)



class SolutionManagementPanel(tk.Frame):
    """解决方案管理面板"""

    def __init__(self, parent, workspace_manager_or_root=None, main_window_or_callback=None):
        """
        支持两种调用方式：
          新接口：SolutionManagementPanel(parent, workspace_manager, main_window)
          旧接口：SolutionManagementPanel(parent, solutions_root, on_solution_selected)

        通过检测第二个参数类型来区分：
          - 若为字符串（路径），则使用旧接口
          - 否则使用新接口
        """
        super().__init__(parent, bg="white")

        # 判断使用哪种接口
        if isinstance(workspace_manager_or_root, str):
            # 旧接口：向后兼容
            self._legacy_mode = True
            self._solutions_root = workspace_manager_or_root
            self._on_solution_selected_callback = main_window_or_callback
            self.workspace_manager = None
            self.main_window = None
        else:
            # 新接口
            self._legacy_mode = False
            self.workspace_manager = workspace_manager_or_root
            self.main_window = main_window_or_callback
            self._solutions_root = None
            self._on_solution_selected_callback = None

        self._setup_ui()
        self.refresh_list()

    # ──────────────────────────────────────────────
    # UI 构建
    # ──────────────────────────────────────────────

    def _setup_ui(self):
        """两列铺满布局，消除空白"""
        self.configure(bg="white")

        # ── 标题 ──
        header = tk.Frame(self, bg="white")
        header.pack(fill=tk.X, padx=12, pady=(10, 4))
        tk.Label(header, text="解决方案管理",
                 font=("Microsoft YaHei UI", 11, "bold"),
                 bg="white", fg="#0055A4").pack(side=tk.LEFT)
        tk.Frame(self, height=1, bg="#E0E0E0").pack(fill=tk.X, padx=12, pady=(0, 10))

        _btn = dict(font=("Microsoft YaHei UI", 9), relief=tk.RAISED,
                    padx=10, pady=3, cursor="hand2")

        # ── 两列主体，fill=X 铺满宽度，columnconfigure weight=1 均分 ──
        body = tk.Frame(self, bg="white")
        body.pack(fill=tk.X, padx=12, pady=(0, 10))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        # ════ 左列：选择 & 操作 ════
        lf_left = tk.LabelFrame(body, text="选择解决方案",
                                font=("Microsoft YaHei UI", 9),
                                bg="white", fg="#555", padx=10, pady=10)
        lf_left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), ipady=4)
        lf_left.columnconfigure(1, weight=1)

        tk.Label(lf_left, text="方案：", bg="white",
                 font=("Microsoft YaHei UI", 9)).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self._combo_var = tk.StringVar()
        self._combo = ttk.Combobox(lf_left, textvariable=self._combo_var,
                                   state="readonly", font=("Microsoft YaHei UI", 9))
        self._combo.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=(0, 8))
        self._combo.bind("<<ComboboxSelected>>",
                         lambda e: self._name_var.set(self._combo_var.get()))
        tk.Button(lf_left, text="刷新", bg="#F0F0F0", fg="#333",
                  command=self.refresh_list, **_btn).grid(row=0, column=2, pady=(0, 8))

        btn_frame = tk.Frame(lf_left, bg="white")
        btn_frame.grid(row=1, column=0, columnspan=3, sticky="w")
        tk.Button(btn_frame, text="加载", bg="#4A90E2", fg="white",
                  command=self._on_load, **_btn).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btn_frame, text="删除", bg="#E74C3C", fg="white",
                  command=self._on_delete, **_btn).pack(side=tk.LEFT, padx=(0, 6))
        tk.Button(btn_frame, text="导出", bg="#16A085", fg="white",
                  command=self._on_export, **_btn).pack(side=tk.LEFT)

        # ════ 右列：保存 & 导入 ════
        lf_right = tk.LabelFrame(body, text="保存 / 导入",
                                 font=("Microsoft YaHei UI", 9),
                                 bg="white", fg="#555", padx=10, pady=10)
        lf_right.grid(row=0, column=1, sticky="nsew", ipady=4)
        lf_right.columnconfigure(1, weight=1)

        tk.Label(lf_right, text="名称：", bg="white",
                 font=("Microsoft YaHei UI", 9)).grid(row=0, column=0, sticky="w", pady=(0, 8))
        self._name_var = tk.StringVar()
        tk.Entry(lf_right, textvariable=self._name_var,
                 font=("Microsoft YaHei UI", 9)).grid(row=0, column=1, sticky="ew",
                                                       padx=(0, 6), pady=(0, 8))
        tk.Button(lf_right, text="保存", bg="#5CB85C", fg="white",
                  command=self._on_save, **_btn).grid(row=0, column=2, pady=(0, 8))

        tk.Label(lf_right, text="从外部目录导入：", bg="white",
                 font=("Microsoft YaHei UI", 9)).grid(row=1, column=0, columnspan=2,
                                                       sticky="w")
        tk.Button(lf_right, text="导入", bg="#8E44AD", fg="white",
                  command=self._on_import, **_btn).grid(row=1, column=2)

    # ──────────────────────────────────────────────
    # 核心方法
    # ──────────────────────────────────────────────

    def _on_save(self):
        """保存当前配置为解决方案"""
        if self._legacy_mode or self.workspace_manager is None:
            messagebox.showwarning("警告", "保存功能需要新接口（workspace_manager）")
            return

        name = self._name_var.get().strip()

        # 验证名称
        if not self.workspace_manager.validate_name(name):
            messagebox.showwarning("警告", "解决方案名称无效（不能为空，且不能包含 \\ / : * ? \" < > |）")
            return

        # 检查是否已选择字体库方案
        solution_name = self.main_window.saved_ocr_state.get('solution_name')
        if not solution_name:
            messagebox.showwarning("警告", "请先在工具界面选择一个字体库方案")
            return

        # 字体库方案路径（使用绝对路径，避免工作目录不一致导致找不到）
        from config import SOLUTIONS_PATH
        font_solution_path = os.path.join(SOLUTIONS_PATH, solution_name)

        # 若目录已存在，询问是否覆盖
        overwrite = False
        if self.workspace_manager.workspace_exists(name):
            overwrite = messagebox.askyesno("确认覆盖", f"解决方案 '{name}' 已存在，是否覆盖？")
            if not overwrite:
                return

        # 收集当前配置
        sensor_settings = {}
        if hasattr(self.main_window, '_get_current_sensor_settings'):
            sensor_settings = self.main_window._get_current_sensor_settings() or {}

        script_settings = {}
        if hasattr(self.main_window, '_get_current_script_settings'):
            script_settings = self.main_window._get_current_script_settings() or {}

        tcp_settings = {}
        if hasattr(self.main_window, '_get_current_tcp_settings'):
            tcp_settings = self.main_window._get_current_tcp_settings() or {}

        try:
            preview_image = None
            if self.main_window and hasattr(self.main_window, 'saved_ocr_state'):
                preview_image = self.main_window.saved_ocr_state.get('image')

            # ── 收集当前相机信息（serial / name / ip / port / server_name）──
            camera_info_dict = {}
            try:
                from managers.camera_manager import CameraManager
                from camera.sapera_camera_discovery import SaperaCameraInfo
                current_cam = CameraManager().current_camera
                if current_cam is not None:
                    if isinstance(current_cam, SaperaCameraInfo):
                        dev = current_cam.device_info or {}
                        camera_info_dict = {
                            "serial":      dev.get("serial", ""),
                            "name":        dev.get("user_id", "") or current_cam.display_name,
                            "ip":          dev.get("ip_address", ""),
                            "port":        5024,
                            "server_name": current_cam.server_name,
                        }
                    else:
                        # CameraInfo
                        camera_info_dict = {
                            "serial":      getattr(current_cam, "serial", ""),
                            "name":        getattr(current_cam, "name", ""),
                            "ip":          current_cam.ip,
                            "port":        current_cam.port,
                            "server_name": getattr(current_cam, "server_name", ""),
                        }
            except Exception as e:
                print(f"[SolutionManagementPanel] 获取相机信息失败: {e}")

            self.workspace_manager.save_workspace(
                name=name,
                font_solution_path=font_solution_path,
                sensor_settings=sensor_settings,
                script_settings=script_settings,
                tcp_settings=tcp_settings,
                overwrite=overwrite,
                preview_image=preview_image,
                camera_info=camera_info_dict if camera_info_dict else None,
            )
            self.refresh_list()
            messagebox.showinfo("成功", f"解决方案 '{name}' 保存成功")
            # 清除脏标志
            if self.main_window and hasattr(self.main_window, '_is_dirty'):
                self.main_window._is_dirty = False
        except Exception as e:
            messagebox.showerror("错误", f"保存失败：{e}")

    def _on_load(self):
        """加载选中的解决方案"""
        if self._legacy_mode or self.workspace_manager is None:
            messagebox.showwarning("警告", "加载功能需要新接口（workspace_manager）")
            return

        # 优先从 Combobox 取值，其次从 Listbox
        name = self._combo_var.get() if hasattr(self, '_combo') else ""
        if not name and hasattr(self, '_listbox'):
            sel = self._listbox.curselection()
            if sel:
                name = self._listbox.get(sel[0])
        if not name:
            messagebox.showwarning("警告", "请先选择要加载的解决方案")
            return

        try:
            data = self.workspace_manager.load_workspace(name)
        except Exception as e:
            messagebox.showerror("错误", f"加载失败：{e}")
            return

        # ── 加载方案前处理相机自动切换 ──
        # 优先从 workspace_config.json 的 connected_camera 节点读取，
        # 兼容旧方案（仅有 layout_config.json 中的 connected_camera）
        camera_node = (
            data.get('connected_camera')
            or data.get('layout_config', {}).get('connected_camera')
        )

        if camera_node and isinstance(camera_node, dict) and camera_node.get('ip'):
            self._do_load_with_camera_switch(name, data, camera_node)
        else:
            # 方案没有关联相机，直接加载
            self._finish_load(name, data)

    def _do_load_with_camera_switch(self, name: str, data: dict, camera_node: dict):
        """
        处理加载方案时的相机自动切换。

        流程：
        1. 在主线程中做优先级匹配（纯内存操作，不阻塞）
        2. 若目标与当前相机相同，直接加载
        3. 否则在后台线程执行硬件切换，完成后通过 after() 回主线程处理结果
        """
        try:
            from managers.camera_manager import CameraManager
            from camera.camera_discovery import CameraInfo
            cam_mgr = CameraManager()

            username = getattr(self.main_window, 'username', '') if self.main_window else ''
            role     = getattr(self.main_window, 'role', '')     if self.main_window else ''

            # ── 构造目标 CameraInfo（携带 serial / name / server_name）──
            target_info = CameraInfo(
                ip=camera_node.get("ip", ""),
                port=int(camera_node.get("port", 5024)),
                name=camera_node.get("name", ""),
                serial=camera_node.get("serial", ""),
                server_name=camera_node.get("server_name", ""),
            )

            # ── 三级优先级匹配（主线程，纯内存，不阻塞）──
            matched = cam_mgr.find_matching_sapera_camera(target_info)

            if matched is not None:
                effective_target = matched
            elif target_info.server_name:
                # 扫描结果为空或 device_info 不完整，但有 server_name：
                # 直接把 CameraInfo 传给 auto_switch_camera，
                # _do_switch 内部会用 server_name 兜底构造 SaperaCameraInfo
                effective_target = target_info
            else:
                # 既无扫描结果又无 server_name，无法切换，直接加载
                print("[SolutionManagementPanel] 无法匹配目标相机且无 server_name，直接加载")
                self._finish_load(name, data)
                return

            # 构造显示名（兼容两种类型）
            try:
                cam_display = effective_target.formatted_display_name
            except AttributeError:
                cam_display = getattr(effective_target, 'display_name',
                                      camera_node.get("name") or camera_node.get("ip", "未知相机"))

            # 若已是当前相机，直接加载（比较 server_name，兼容两种类型）
            current = cam_mgr.current_camera
            target_sn = (
                effective_target.server_name
                if hasattr(effective_target, 'server_name')
                else getattr(effective_target, 'server_name', '')
            )
            current_sn = getattr(current, 'server_name', '') if current else ''
            if target_sn and current_sn and target_sn == current_sn:
                self._finish_load(name, data)
                return

            # ── 禁用加载按钮，防止重复点击 ──
            self._set_load_button_state(False)

        except Exception as e:
            print(f"[SolutionManagementPanel] 相机匹配异常，直接加载: {e}")
            self._finish_load(name, data)
            return

        # ── 后台线程执行硬件切换，完成后回主线程 ──
        def _on_switch_done(success: bool, message: str, user_role: str = ""):
            """切换完成回调（在后台线程中调用）"""
            try:
                # 检查 widget 是否还存在，防止 panel 被销毁后 TclError
                if self.winfo_exists():
                    self.after(0, lambda: self._handle_switch_result(
                        success, message, cam_display, role, name, data
                    ))
            except Exception as ex:
                print(f"[SolutionManagementPanel] 切换回调异常: {ex}")

        cam_mgr.auto_switch_camera(
            target=effective_target,
            user_name=username,
            user_role=role,
            on_result=_on_switch_done,
        )

    def _handle_switch_result(
        self,
        success: bool,
        message: str,
        cam_display: str,
        role: str,
        name: str,
        data: dict,
    ):
        """
        在主线程中处理相机切换结果，然后决定是否继续加载方案。

        成功：提示已切换，继续加载。
        失败-操作员：提示不可用，中止加载。
        失败-管理员/技术员：询问是否继续，用户可选择继续或取消。
        """
        # 恢复加载按钮
        self._set_load_button_state(True)

        if success:
            # FC-13：自动切换成功，提示用户
            messagebox.showinfo(
                "相机已切换",
                f"已自动切换至方案关联相机：{cam_display}",
                parent=self,
            )
            self._finish_load(name, data)

        elif role == "操作员":
            # FC-14：操作员 → 中止加载，提示联系技术员
            messagebox.showerror(
                "相机不可用",
                f"方案关联相机 '{cam_display}' 不可用，请联系技术员。\n\n"
                f"加载已中止，当前连接不变。",
                parent=self,
            )
            # 不调用 _finish_load，中止加载

        else:
            # FC-15：管理员/技术员 → 不中止，询问是否继续
            proceed = messagebox.askyesno(
                "相机切换失败",
                f"方案关联相机 '{cam_display}' 不可用。\n\n"
                f"是否仍继续加载方案（使用当前相机）？",
                parent=self,
            )
            if proceed:
                self._finish_load(name, data)
            # 否则取消，不加载

    def _finish_load(self, name: str, data: dict):
        """应用方案数据并显示成功提示"""
        self._apply_loaded_workspace(data)
        if self.main_window:
            self.main_window._current_workspace_name = name
        messagebox.showinfo("成功", f"解决方案 '{name}' 加载成功")

    def _set_load_button_state(self, enabled: bool):
        """启用/禁用加载按钮，防止切换期间重复点击"""
        try:
            for widget in self.winfo_children():
                self._toggle_button_recursive(widget, "加载", enabled)
        except Exception:
            pass

    def _toggle_button_recursive(self, widget, text: str, enabled: bool):
        """递归查找并切换指定文本的按钮状态"""
        try:
            if isinstance(widget, tk.Button) and widget.cget("text") == text:
                widget.config(state=tk.NORMAL if enabled else tk.DISABLED)
            for child in widget.winfo_children():
                self._toggle_button_recursive(child, text, enabled)
        except Exception:
            pass

    def _apply_loaded_workspace(self, data: dict):
        """
        应用加载的解决方案配置到主窗口所有组件：
        1. 传感器参数：持久化 + 应用到 SensorSettingsFrame
        2. 脚本：应用到 ScriptEditorFrame 和 ScriptEngine
        3. ROI 布局：更新 saved_ocr_state
        4. TCP 端口：自动启动标记为 auto_start 的端口
        5. SolutionMakerFrame：同步 current_solution_name
        """
        if self.main_window is None:
            return

        # 1. 传感器参数应用
        sensor = data.get('sensor', {})
        if sensor:
            try:
                import config
                config.save_user_sensor_settings(sensor)
            except Exception:
                pass
            try:
                frame = getattr(self.main_window, '_sensor_settings_frame', None)
                if frame is not None:
                    frame._apply_user_settings(sensor)
            except Exception:
                pass
            # 直接应用触发模式到相机硬件
            try:
                cam = getattr(self.main_window, 'cam', None)
                if cam is not None:
                    trigger_mode = sensor.get('trigger_mode', 'internal')
                    interval_ms = sensor.get('interval_ms', 1000)
                    cam.set_trigger_mode(trigger_mode, interval_ms=interval_ms)
            except Exception:
                pass

        # 2. 脚本应用
        scripts = data.get('scripts', {})
        if scripts:
            try:
                script_editor = getattr(self.main_window, '_script_editor_frame', None)
                if script_editor is not None:
                    script_editor.load_scripts(scripts)
            except Exception:
                pass
            try:
                script_engine = getattr(self.main_window, 'script_engine', None)
                if script_engine is not None:
                    # set_scripts 只接受触发点脚本，过滤掉 periodic_interval_ms
                    trigger_scripts = {
                        k: v for k, v in scripts.items()
                        if k in ('solution_initialize', 'pre_image_process',
                                 'post_image_process', 'periodic')
                    }
                    script_engine.set_scripts(trigger_scripts)
                    # 执行 solution_initialize 脚本
                    try:
                        script_engine.execute('solution_initialize')
                    except Exception:
                        pass
                    # 刷新通讯界面的脚本列表显示
                    try:
                        if hasattr(self.main_window, '_reload_script_listbox'):
                            self.main_window._reload_script_listbox()
                    except Exception:
                        pass
            except Exception:
                pass

        # 3. ROI 布局应用
        try:
            layout_config = data.get('layout_config', {})
            if layout_config:
                roi_layout = _parse_layout_config(layout_config)
                self.main_window.saved_ocr_state['roi_layout'] = roi_layout
                self.main_window.saved_ocr_state['has_state'] = True
        except Exception:
            pass

        # 3b. 预览图片应用
        try:
            preview_image = data.get('preview_image')
            if preview_image is not None:
                self.main_window.saved_ocr_state['image'] = preview_image
                self.main_window.saved_ocr_state['has_state'] = True
        except Exception:
            pass

        # 4. TCP 端口应用
        try:
            tcp_service = getattr(self.main_window, 'tcp_service', None)
            if tcp_service is not None:
                for port in data.get('tcp', {}).get('auto_start_ports', []):
                    try:
                        tcp_service.start(port)
                    except Exception:
                        pass
        except Exception:
            pass

        # 4b. 启动 periodic 脚本定时线程
        try:
            script_engine = getattr(self.main_window, 'script_engine', None)
            if script_engine is not None:
                scripts = data.get('scripts', {})
                interval_ms = int(scripts.get('periodic_interval_ms', 100))
                periodic_code = scripts.get('periodic', '').strip()
                if periodic_code:
                    script_engine.start_periodic(interval_ms)
        except Exception:
            pass

        # 5. SolutionMakerFrame 同步
        try:
            font_solution_name = data.get('font_solution_name') or \
                (data.get('layout_config') or {}).get('font_solution_name')
            if font_solution_name and self.main_window is not None:
                # 更新 saved_ocr_state
                self.main_window.saved_ocr_state['solution_name'] = font_solution_name
                self.main_window.saved_ocr_state['has_state'] = True

                # 更新 SolutionMakerFrame 的下拉框和内部状态（如果已创建）
                solution_maker = getattr(self.main_window, 'solution_maker_frame', None)
                if solution_maker is not None:
                    # 先刷新列表确保 values 包含该方案名
                    if hasattr(solution_maker, '_refresh_solution_list'):
                        solution_maker._refresh_solution_list()
                    solution_maker.current_solution_name = font_solution_name
                    if hasattr(solution_maker, 'var_solution_name'):
                        solution_maker.var_solution_name.set(font_solution_name)
                    # 触发 on_solution_selected 加载字段布局等
                    if hasattr(solution_maker, 'on_solution_selected'):
                        solution_maker.on_solution_selected()
        except Exception:
            pass

    def _on_delete(self):
        """删除选中的解决方案"""
        if self._legacy_mode or self.workspace_manager is None:
            messagebox.showwarning("警告", "删除功能需要新接口（workspace_manager）")
            return

        name = self._combo_var.get() if hasattr(self, '_combo') else ""
        if not name and hasattr(self, '_listbox'):
            sel = self._listbox.curselection()
            if sel:
                name = self._listbox.get(sel[0])
        if not name:
            messagebox.showwarning("警告", "请先选择要删除的解决方案")
            return

        if not messagebox.askyesno("确认删除", f"确定要删除解决方案 '{name}' 吗？\n此操作不可恢复！",
                                   icon='warning'):
            return

        try:
            self.workspace_manager.delete_workspace(name)
            self.refresh_list()
        except Exception as e:
            messagebox.showerror("错误", f"删除失败：{e}")

    def _on_import(self):
        """从外部目录导入解决方案"""
        src = _ask_directory_safe("选择要导入的解决方案目录")
        if not src:
            return

        name = os.path.basename(src.rstrip("/\\"))
        if not name:
            messagebox.showwarning("警告", "无法识别目录名称")
            return

        if self.workspace_manager is not None:
            dest = os.path.join(self.workspace_manager.workspaces_root, name)
        else:
            messagebox.showwarning("警告", "导入功能需要新接口（workspace_manager）")
            return

        if os.path.exists(dest):
            if not messagebox.askyesno("确认覆盖", f"解决方案 '{name}' 已存在，是否覆盖？"):
                return
            try:
                shutil.rmtree(dest)
            except Exception as e:
                messagebox.showerror("错误", f"删除旧目录失败：{e}")
                return

        try:
            shutil.copytree(src, dest)
            self.refresh_list()
            messagebox.showinfo("成功", f"解决方案 '{name}' 导入成功")
        except Exception as e:
            messagebox.showerror("错误", f"导入失败：{e}")

    def _on_export(self):
        """将选中的解决方案导出到指定目录"""
        name = self._combo_var.get() if hasattr(self, '_combo') else ""
        if not name and hasattr(self, '_listbox'):
            sel = self._listbox.curselection()
            if sel:
                name = self._listbox.get(sel[0])
        if not name:
            messagebox.showwarning("警告", "请先选择要导出的解决方案")
            return

        if self.workspace_manager is not None:
            src = os.path.join(self.workspace_manager.workspaces_root, name)
        else:
            messagebox.showwarning("警告", "导出功能需要新接口（workspace_manager）")
            return

        dest_dir = _ask_directory_safe("选择导出目标目录")
        if not dest_dir:
            return

        dest = os.path.join(dest_dir, name)
        if os.path.exists(dest):
            if not messagebox.askyesno("确认覆盖", f"目标目录已存在 '{name}'，是否覆盖？"):
                return
            try:
                shutil.rmtree(dest)
            except Exception as e:
                messagebox.showerror("错误", f"删除目标目录失败：{e}")
                return

        try:
            shutil.copytree(src, dest)
            messagebox.showinfo("成功", f"解决方案 '{name}' 已导出到：\n{dest}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败：{e}")

    def refresh_list(self):
        """刷新解决方案列表（同时更新 Listbox 和 Combobox）"""
        names = []

        if self._legacy_mode or self.workspace_manager is None:
            if self._solutions_root and os.path.exists(self._solutions_root):
                names = sorted([
                    n for n in os.listdir(self._solutions_root)
                    if os.path.isdir(os.path.join(self._solutions_root, n))
                ])
        else:
            try:
                names = self.workspace_manager.list_workspaces()
            except Exception:
                pass

        # 更新 Listbox（若存在）
        if hasattr(self, '_listbox'):
            self._listbox.delete(0, tk.END)
            for n in names:
                self._listbox.insert(tk.END, n)

        # 更新 Combobox（若存在）
        if hasattr(self, '_combo'):
            self._combo['values'] = names
            if names and self._combo_var.get() not in names:
                self._combo_var.set(names[0])

    # ──────────────────────────────────────────────
    # 旧接口兼容方法（供旧代码调用）
    # ──────────────────────────────────────────────

    def refresh_solution_list(self):
        """向后兼容别名"""
        self.refresh_list()

    def get_current_solution(self):
        """获取当前选中的方案名称（旧接口兼容）"""
        if hasattr(self, '_combo'):
            return self._combo_var.get() or None
        if hasattr(self, '_listbox'):
            sel = self._listbox.curselection()
            if sel:
                return self._listbox.get(sel[0])
        return None

    def set_current_solution(self, solution_name):
        """设置当前方案（旧接口兼容）"""
        if not solution_name:
            return
        if hasattr(self, '_combo'):
            values = self._combo['values']
            if solution_name in values:
                self._combo_var.set(solution_name)
        if hasattr(self, '_listbox'):
            items = self._listbox.get(0, tk.END)
            if solution_name in items:
                idx = list(items).index(solution_name)
                self._listbox.selection_clear(0, tk.END)
                self._listbox.selection_set(idx)
                self._listbox.see(idx)


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────

def _parse_layout_config(config_data: dict) -> dict:
    """将 layout_config.json 内容转换为 roi_layout 格式"""
    roi_layout = {}

    # 锚点
    if config_data.get("strategy") == "anchor_based":
        roi_layout["FirstDigitAnchor"] = {
            "roi": config_data["anchor_rect"],
            "search_area": config_data.get("anchor_search_area", config_data["anchor_rect"]),
            "is_anchor": True,
        }

    # 字段
    for field_name, field_coords in config_data.get("fields", {}).items():
        roi_layout[field_name] = {
            "roi": field_coords,
            "search_area": field_coords,
            "is_anchor": False,
        }

    return roi_layout
