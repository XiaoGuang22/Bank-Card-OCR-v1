import tkinter as tk
from tkinter import ttk
from config import get_user_sensor_settings, save_user_sensor_settings

# 导入异常处理工具
try:
    from utils.exception_utils import ErrorHandler, safe_call, safe_execute, suppress_errors
except ImportError:
    # 如果异常处理工具不可用，使用简单的装饰器
    def ErrorHandler():
        class _ErrorHandler:
            @staticmethod
            def handle_ui_error(func):
                return func
            @staticmethod
            def handle_camera_error(func):
                return func
        return _ErrorHandler()
    ErrorHandler = ErrorHandler()
    safe_call = lambda func, *args, **kwargs: func(*args, **kwargs)
    safe_execute = lambda **kwargs: lambda func: func
    suppress_errors = lambda *args, **kwargs: lambda: None

class SensorSettingsFrame(tk.Frame):
    """
    传感器设置面板：点击主界面'传感器'按钮后加载到侧边栏
    """
    def __init__(self, parent, controller, on_back_callback, camera_controller=None, on_trigger_callback=None):
        super().__init__(parent, bg="white")
        self.controller = controller
        self.on_back = on_back_callback
        self.camera = camera_controller  # 保存相机控制器引用
        self.on_trigger = on_trigger_callback  # 保存触发回调函数
        
        # === 样式配置 ===
        self.style = ttk.Style()
        self.style.configure("White.TLabelframe", background="white")
        self.style.configure("White.TLabelframe.Label", background="white", font=("Microsoft YaHei UI", 11, "bold"))
        self.style.configure("White.TRadiobutton", background="white", font=("Microsoft YaHei UI", 11))
        self.style.configure("White.TCheckbutton", background="white")
        
        self._init_ui()

    def _init_ui(self):
        # === 顶部 Header（与工具界面风格一致）===
        header = tk.Frame(self, bg="white")
        header.pack(fill=tk.X, padx=(10, 5), pady=5)

        tk.Label(
            header,
            text="设置相机",
            font=("Microsoft YaHei UI", 11, "bold"),
            bg="white",
            fg="#0055A4"
        ).pack(side=tk.LEFT)

        tk.Button(
            header,
            text="← 返回",
            font=("Microsoft YaHei UI", 8),
            bg="#F0F0F0",
            relief=tk.FLAT,
            cursor="hand2",
            command=self.on_back
        ).pack(side=tk.RIGHT)

        # 分隔线
        tk.Frame(self, height=1, bg="#E0E0E0").pack(fill=tk.X, padx=(10, 5), pady=(0, 10))

        # === 通用间距配置 ===
        SECTION_PADY = 8

        # === 触发源 ===
        lf_trig = ttk.LabelFrame(self, text="传感器触发", style="White.TLabelframe")
        lf_trig.pack(fill=tk.X, pady=SECTION_PADY)
        
        # 说明文字
        help_text = tk.Label(
            lf_trig, 
            text="选择应用拍一幅图像（拍一张照片）的触发源",
            bg="white", 
            fg="#666666",
            font=("Microsoft YaHei UI", 8),
            wraplength=300,
            justify=tk.LEFT
        )
        help_text.pack(anchor="w", pady=(5, 10), padx=5)
        
        f_trig_opts = tk.Frame(lf_trig, bg="white")
        f_trig_opts.pack(fill=tk.X, pady=5)
        
        self.var_trig = tk.StringVar(value="internal")
        
        # 绑定点击事件，刷新状态
        ttk.Radiobutton(f_trig_opts, text="内部定时", variable=self.var_trig, value="internal", 
                        style="White.TRadiobutton", command=self._refresh_states).pack(side=tk.LEFT)
        # ttk.Radiobutton(f_trig_opts, text="检测触发", variable=self.var_trig, value="hardware",
        #                 style="White.TRadiobutton", command=self._refresh_states).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(f_trig_opts, text="软件触发", variable=self.var_trig, value="software", 
                        style="White.TRadiobutton", command=self._refresh_states).pack(side=tk.LEFT)
        
        # 内部定时间隔滑杆（带说明）
        interval_frame = tk.Frame(lf_trig, bg="white")
        interval_frame.pack(fill=tk.X, pady=(5, 0))
        
        interval_label = tk.Label(
            interval_frame,
            text="时间间隔（拍摄频率）",
            bg="white",
            fg="#333333",
            font=("Microsoft YaHei UI", 9)
        )
        interval_label.pack(anchor="w", padx=5)
        
        # 根据相机实际帧率范围：0.2-15.18 Hz
        # 时间间隔 = 1000 / 帧率
        # 最小间隔 = 1000 / 15.18 ≈ 66 ms
        # 最大间隔 = 1000 / 0.2 = 5000 ms
        self.slider_interval = self._create_slider(lf_trig, 66, 5000, unit="毫秒", precision=0, resolution=1)
        

        # === 3. 检测触发延时（已移除）===
        # lf_delay = ttk.LabelFrame(self, text="检测触发延时", style="White.TLabelframe")
        # lf_delay.pack(fill=tk.X, pady=SECTION_PADY)
        # self.var_delay_check = tk.IntVar(value=0)
        # self.cb_delay = ttk.Checkbutton(lf_delay, variable=self.var_delay_check, style="White.TCheckbutton")
        # self.cb_delay.place(relx=1.0, x=-10, y=-22, anchor="ne")
        # self.slider_delay = self._create_slider(lf_delay, 0, 1500, unit="毫秒", precision=0, resolution=1)

        # === 4. 频闪/输出脉冲（已移除）===
        # lf_strobe = ttk.LabelFrame(self, text="频闪/输出脉冲", style="White.TLabelframe")
        # lf_strobe.pack(fill=tk.X, pady=SECTION_PADY)

        # === 5. 传感器曝光 ===
        lf_exp = ttk.LabelFrame(self, text="传感器曝光", style="White.TLabelframe")
        lf_exp.pack(fill=tk.X, pady=SECTION_PADY)
        # 曝光时间范围：35-65776 μs (0.035-65.776 ms)
        # 为了UI友好，设置为 0.05-51.10 ms（常用范围）
        self.slider_exposure = self._create_slider(lf_exp, 0.05, 51.10, unit="毫秒", precision=2, resolution=0.05)

        # === 6. 亮度 & 对比度 ===
        f_img = tk.Frame(self, bg="white")
        f_img.pack(fill=tk.X, pady=SECTION_PADY)
        f_img.grid_columnconfigure(0, weight=1)
        f_img.grid_columnconfigure(1, weight=1)
        
        lf_bright = ttk.LabelFrame(f_img, text="亮度", style="White.TLabelframe")
        lf_bright.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.slider_bright = self._create_slider(lf_bright, 0, 100, unit="%", precision=0, resolution=1, compact=True)
        
        lf_cont = ttk.LabelFrame(f_img, text="对比度", style="White.TLabelframe")
        lf_cont.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self.slider_cont = self._create_slider(lf_cont, 0, 100, unit="%", precision=0, resolution=1, compact=True)

        # === 7. 设置标定按钮（已移除）===
        # btn_calib = tk.Button(self, text="设置标定", bg="#E0E0E0", relief="raised", 
        #                       font=("Microsoft YaHei UI", 11, "bold"))
        # btn_calib.pack(fill=tk.X, pady=20, ipady=5)
        
        # === 底部区域 ===
        tk.Frame(self, bg="white").pack(fill=tk.BOTH, expand=True)

        f_btm = tk.Frame(self, bg="white", pady=10)
        f_btm.pack(fill=tk.X, side=tk.BOTTOM)

        tk.Button(f_btm, text="确定",
                  font=("Microsoft YaHei UI", 9),
                  bg="#F0F0F0", fg="#333333",
                  relief=tk.RAISED, cursor="hand2",
                  padx=20, pady=4,
                  command=self.apply_settings
                  ).pack(side=tk.RIGHT, padx=(0, 5))

        # 加载用户上次设置的参数
        self._load_user_settings()
        
        # 初始化状态
        self._refresh_states()
        
        # 加载当前相机设置（如果需要覆盖用户设置）
        # self._load_current_settings()

    # ==========================================================
    # ★★★ 状态控制与视觉逻辑 ★★★
    # ==========================================================
    
    @ErrorHandler.handle_ui_error
    def _load_user_settings(self):
        """加载用户上次设置的参数"""
        settings = get_user_sensor_settings()
        
        # 加载各项设置
        self._apply_user_settings(settings)
        
        print(f"✅ 已加载用户上次设置的参数")
        print(f"   触发模式: {settings.get('trigger_mode', 'internal')}")
        print(f"   时间间隔: {settings.get('interval_ms', 1084)} ms")
        print(f"   曝光时间: {settings.get('exposure_ms', 25.0)} ms")
    
    def _apply_user_settings(self, settings: dict):
        """应用用户设置到界面控件"""
        # 加载触发模式
        safe_call(self.var_trig.set, settings.get('trigger_mode', 'internal'))
        
        # 加载时间间隔
        safe_call(self.slider_interval.set, settings.get('interval_ms', 1084))
        
        # 加载延时设置（已移除UI，跳过）
        # safe_call(self.var_delay_check.set, ...)
        # safe_call(self.slider_delay.set, ...)
        
        # 加载频闪设置（已移除UI，跳过）
        # safe_call(self.var_strobe_check.set, ...)
        # safe_call(self.slider_strobe_dur.set, ...)
        # safe_call(self.slider_strobe_off.set, ...)
        
        # 加载曝光时间
        safe_call(self.slider_exposure.set, settings.get('exposure_ms', 25.0))
        
        # 加载亮度和对比度
        safe_call(self.slider_bright.set, settings.get('brightness', 50))
        safe_call(self.slider_cont.set, settings.get('contrast', 50))
    
    @ErrorHandler.handle_ui_error
    def _save_user_settings(self):
        """保存用户当前设置的参数（对比度不保存，每次启动恢复为50%）"""
        settings = {
            'trigger_mode': self.var_trig.get(),
            'interval_ms': self.slider_interval.get(),
            'exposure_ms': self.slider_exposure.get(),
            'brightness': self.slider_bright.get(),
            'contrast': 50,
        }
        
        save_user_sensor_settings(settings)
    
    @ErrorHandler.handle_camera_error
    def _load_current_settings(self):
        """从相机加载当前设置"""
        if not self.camera:
            raise ValueError("相机控制器未初始化")
        
        # 检查触发模式是否可写
        trigger_mode_writable = self._check_trigger_mode_writable()
        
        if not trigger_mode_writable:
            # 禁用触发模式选择
            for child in self.winfo_children():
                if isinstance(child, ttk.LabelFrame):
                    if "触发源" in child.cget("text"):
                        # 禁用触发源面板中的所有单选按钮
                        for widget in child.winfo_children():
                            if isinstance(widget, tk.Frame):
                                for rb in widget.winfo_children():
                                    if isinstance(rb, ttk.Radiobutton):
                                        rb.config(state="disabled")
        
        # 加载触发模式
        trigger_mode = self.camera.get_trigger_mode()
        if trigger_mode == "internal":
            self.var_trig.set("internal")
        elif trigger_mode == "hardware":
            self.var_trig.set("hardware")
        elif trigger_mode == "software":
            self.var_trig.set("software")
        else:
            # 未知模式，默认为内部定时
            self.var_trig.set("internal")
        
        # 加载曝光时间
        exposure_ms = self.camera.get_exposure()
        if exposure_ms is not None:
            self.slider_exposure.set(exposure_ms)
        
        # 加载增益（映射到亮度）
        gain = self.camera.get_gain()
        if gain is not None:
            # 将增益值（0-120）映射到亮度百分比（0-100）
            brightness = (gain / 120.0) * 100.0
            self.slider_bright.set(brightness)
    
    def _check_trigger_mode_writable(self) -> bool:
        """检查触发模式是否可写"""
        with suppress_errors(Exception, log_error=False):
            if hasattr(self.camera.acq_device, 'IsFeatureWritable'):
                return self.camera.acq_device.IsFeatureWritable("TriggerMode")
        return False
    
    @ErrorHandler.handle_ui_error
    def _test_software_trigger(self):
        """测试软件触发"""
        if not self.camera:
            raise ValueError("相机控制器未初始化")
        
        # 检查当前是否为软件触发模式
        current_mode = self.camera.get_trigger_mode()
        if current_mode != "software":
            print("⚠️ 当前不是软件触发模式，自动切换...")
            self._switch_to_software_trigger()
        
        # 执行软件触发
        if self.camera.execute_software_trigger():
            self._provide_trigger_feedback()
            # 调用回调函数，通知主窗口刷新画布
            if self.on_trigger:
                safe_call(self.on_trigger)
        else:
            raise RuntimeError("软件触发执行失败")
    
    @ErrorHandler.handle_camera_error
    def _switch_to_software_trigger(self):
        """切换到软件触发模式"""
        if self.camera.set_trigger_mode("software"):
            print("✅ 已自动切换到软件触发模式")
            # 同步 UI 状态
            safe_call(self.var_trig.set, "software")
        else:
            raise RuntimeError("切换到软件触发模式失败")
    
    def _provide_trigger_feedback(self):
        """提供触发反馈"""
    
    @ErrorHandler.handle_ui_error
    def apply_settings(self):
        """应用设置到相机"""
        if not self.camera:
            raise ValueError("相机控制器未初始化")
        
        # 保存用户设置
        self._save_user_settings()
        
        print("\n" + "="*60)
        print("应用传感器设置")
        print("="*60)
        
        # 应用所有设置
        self._apply_all_settings()
        
        print("\n✅ 传感器设置应用完成")
        print("="*60)
        
        # 返回主界面
        if self.on_back:
            safe_call(self.on_back)
    
    @safe_execute(default_return=None, log_error=True, error_message="应用所有设置失败")
    def _apply_all_settings(self):
        """应用所有传感器设置"""
        # 1. 应用触发模式
        trigger_mode = self.var_trig.get()
        interval_ms = self.slider_interval.get()
        delay_ms = 0  # 检测触发延时已移除

        print(f"\n📋 触发模式配置:")
        print(f"   模式: {trigger_mode}")
        if trigger_mode == "internal":
            print(f"   时间间隔: {interval_ms} ms")
            print(f"   拍摄频率: {1000.0/interval_ms:.2f} 帧/秒")
        elif trigger_mode == "hardware":
            print(f"   触发延时: {delay_ms} ms")
        
        if self.camera.set_trigger_mode(trigger_mode, interval_ms, delay_ms):
            print(f"✅ 触发模式已应用")
        else:
            print(f"❌ 触发模式应用失败")
        
        # 2. 应用曝光时间
        exposure_ms = self.slider_exposure.get()
        if self.camera.set_exposure(exposure_ms):
            print(f"✅ 曝光时间已应用: {exposure_ms:.2f} ms")
        else:
            print(f"❌ 曝光时间应用失败")
        
        # 3. 应用亮度（映射到增益）
        brightness = self.slider_bright.get()
        gain = int((brightness / 100.0) * 120.0)
        if self.camera.set_gain(gain):
            print(f"✅ 亮度已应用: {brightness}% (增益: {gain})")
        else:
            print(f"❌ 亮度应用失败")
        
        # 4. 应用对比度
        contrast = self.slider_cont.get()
        self._apply_contrast_settings(contrast)
        
        # 5. 显示成功提示
        self._show_success_message(trigger_mode)
    
    def _apply_contrast_settings(self, contrast):
        """应用对比度设置"""
        from config import CONTRAST_METHOD
        
        if self.camera.set_gamma(contrast):
            if CONTRAST_METHOD == 'lut':
                print(f"✅ 对比度已应用: {contrast}% (LUT 方案)")
            elif CONTRAST_METHOD == 'software':
                print(f"✅ 对比度已应用: {contrast}% (软件方案，实时处理)")
            else:  # black_level
                if contrast <= 50:
                    print(f"✅ 对比度已应用: {contrast}% (黑电平方案)")
                else:
                    print(f"✅ 对比度已应用: {contrast}% (注意：黑电平方案无法增强对比度，50%以上效果相同)")
        else:
            print(f"⚠️ 对比度应用失败")
    
    def _show_success_message(self, trigger_mode):
        """显示成功消息"""
        print("="*60)
        print("✅ 设置应用完成")
        print("="*60 + "\n")

    def _refresh_states(self):
        """刷新所有滑块的状态"""
        mode = self.var_trig.get()

        if mode == "internal":
            self._enable_slider(self.slider_interval)
        else:  # software
            self._disable_slider(self.slider_interval)

        # 始终启用的滑块
        always_active = [
            self.slider_exposure, self.slider_bright, self.slider_cont
        ]
        for s in always_active:
            self._enable_slider(s)

    def _enable_slider(self, slider):
        """启用: 紫色背景，可操作"""
        slider.config(state="normal", bg="#8A2BE2", troughcolor="#eee", activebackground="#9370DB")

    def _disable_slider(self, slider):
        """禁用: 灰色背景，不可操作"""
        slider.config(state="disabled", bg="#F0F0F0", troughcolor="#eee", activebackground="gray")

    def _update_label(self, val, label_widget, unit, precision):
        """更新标签文本"""
        val_float = safe_call(float, val, default=0.0)
        fmt = f"{{:.{precision}f}} {{}}"
        text_str = fmt.format(val_float, unit)
        safe_call(label_widget.config, text=text_str)

    def _set_focus(self, event, widget):
        if str(widget['state']) != 'disabled':
            widget.focus_set()

    def _create_slider(self, parent, min_v, max_v, unit="", precision=0, resolution=1, compact=False, default_val=None):
        f = tk.Frame(parent, bg="white")
        pady_val = 2 if compact else 8
        f.pack(fill=tk.X, pady=pady_val)
        
        lbl_val = tk.Label(f, text="", bg="white", font=("Microsoft YaHei UI", 9), width=10, anchor="e")
        lbl_val.pack(side=tk.RIGHT)
        
        # 使用提供的默认值，如果没有则使用中间值
        init_val = default_val if default_val is not None else (min_v + (max_v - min_v) / 2)
        
        s = tk.Scale(f, from_=min_v, to=max_v, orient=tk.HORIZONTAL, 
                     showvalue=0, bd=0, 
                     width=15,
                     resolution=resolution,          
                     takefocus=1,
                     
                     # 初始颜色
                     bg="#8A2BE2",           
                     troughcolor="#eee",     
                     activebackground="#9370DB",
                     
                     highlightthickness=1,           
                     highlightcolor="#8A2BE2",       
                     highlightbackground="white",    
                     
                     command=lambda v: self._update_label(v, lbl_val, unit, precision))
        
        s.bind("<Button-1>", lambda event: self._set_focus(event, s))
        s.pack(side=tk.LEFT, fill=tk.X, expand=True)
        s.set(init_val)
        return s

    def _create_mini_slider(self, parent, min_v, max_v, unit="", precision=0, resolution=1, default_val=None):
        f = tk.Frame(parent, bg="white")
        f.pack(fill=tk.X, pady=2)
        
        lbl_val = tk.Label(f, text="", bg="white", font=("Microsoft YaHei UI", 9), width=10, anchor="e")
        lbl_val.pack(side=tk.RIGHT)
        
        # 使用提供的默认值，如果没有则使用中间值
        init_val = default_val if default_val is not None else (min_v + (max_v - min_v) / 2)
        
        s = tk.Scale(f, from_=min_v, to=max_v, orient=tk.HORIZONTAL, 
                     showvalue=0, bd=0, 
                     width=15,
                     resolution=resolution,
                     takefocus=1,
                     
                     # 初始颜色
                     bg="#8A2BE2",
                     troughcolor="#eee",
                     activebackground="#9370DB",
                     
                     highlightthickness=1,
                     highlightcolor="#8A2BE2",
                     highlightbackground="white",
                     
                     command=lambda v: self._update_label(v, lbl_val, unit, precision))
        
        s.bind("<Button-1>", lambda event: self._set_focus(event, s))
        s.pack(side=tk.LEFT, fill=tk.X, expand=True)
        s.set(init_val)
        return s