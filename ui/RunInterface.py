"""
运行界面模块

该模块实现Card-OCR系统的运行界面，提供实时的卡片识别和处理功能。
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
from datetime import datetime
import cv2
import numpy as np
import os
import json

# ★★★ 导入异常处理工具 ★★★
try:
    from utils.exception_utils import ErrorHandler, safe_call, safe_execute, suppress_errors
except ImportError:
    # 如果异常处理工具不可用，使用简单的装饰器
    class ErrorHandler:
        @staticmethod
        def handle_ui_error(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"UI错误: {e}")
                    return None
            return wrapper
        
        @staticmethod
        def handle_file_error(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"文件错误: {e}")
                    return None
            return wrapper
        
        @staticmethod
        def handle_camera_error(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"相机错误: {e}")
                    return False
            return wrapper
        
        @staticmethod
        def handle_system_error(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"系统错误: {e}")
                    return False
            return wrapper
    
    def safe_call(func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"安全调用错误: {e}")
            return None
    
    def safe_execute(default_return=None, log_error=True, error_message="操作失败"):
        def decorator(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if log_error:
                        print(f"{error_message}: {e}")
                    return default_return
            return wrapper
        return decorator
    
    def suppress_errors(*args, **kwargs):
        def decorator(func):
            def wrapper(*func_args, **func_kwargs):
                try:
                    return func(*func_args, **func_kwargs)
                except:
                    pass
            return wrapper
        return decorator

# 导入UI组件
try:
    from ui.StatisticsPanel import StatisticsPanel
    from ui.TimeInfoPanel import TimeInfoPanel
    from ui.TreeViewPanel import TreeViewPanel
    from ui.ControlButtonsPanel import ControlButtonsPanel
    from ui.ImageDisplayPanel import ImageDisplayPanel
except ImportError:
    from StatisticsPanel import StatisticsPanel
    from TimeInfoPanel import TimeInfoPanel
    from TreeViewPanel import TreeViewPanel
    from ControlButtonsPanel import ControlButtonsPanel
    from ImageDisplayPanel import ImageDisplayPanel

# 导入管理器
try:
    from managers.stats_manager import StatsManager
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from managers.stats_manager import StatsManager

# 导入OCR引擎
try:
    from ocr.ocr_engine import OCREngine
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from ocr.ocr_engine import OCREngine

# 导入识别器
try:
    from recognizer.main_recognizer import BankCardRecognizer
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from recognizer.main_recognizer import BankCardRecognizer


class RunInterface:
    """
    运行界面类
    
    提供实时的卡片识别和处理界面，包含统计信息显示、运行状态控制、
    参数设置和实时图像显示等功能。
    """
    
    # 【关键修复】类变量：全局控制所有 RunInterface 实例的视频循环
    _global_video_enabled = True
    
    @ErrorHandler.handle_ui_error
    def __init__(self, parent, camera_controller, on_back_callback, main_window=None, script_engine=None):
        """
        初始化运行界面
        
        参数:
            parent: 父窗口（侧边栏）
            camera_controller: 相机控制器实例
            on_back_callback: 返回主菜单的回调函数
            main_window: 主窗口引用（用于访问画布）
            script_engine: 脚本引擎实例（可选）
        """
        self.parent = parent
        self.camera_controller = camera_controller
        self.on_back_callback = on_back_callback
        self.main_window = main_window
        self.script_engine = script_engine
        
        # 初始化统计管理器
        self.stats_manager = StatsManager()

        # 添加图片检测计数器
        self.image_detection_count = 0

        # 从主窗口恢复上次统计数据
        self._load_stats()
        
        # 初始化OCR引擎（模板在识别时按需加载）
        template_dir = ""
        self.ocr_engine = OCREngine(template_dir)
        
        # 初始化识别器（用于字符识别）
        self.recognizer = None
        self.current_solution_path = None
        
        # 运行状态
        self.is_running = False
        self.inspection_thread = None
        self.stop_event = threading.Event()
        self.status_label = None  # 状态栏已移除，保留引用避免报错
        # 软件/手动触发事件
        self.trigger_event = threading.Event()
        
        # 性能统计
        self.last_trigger_time = None
        self.trigger_frequency = 0.0
        
        # 视频显示相关
        self.video_loop_running = False
        self.video_loop_id = None
        self._current_tk_image = None
        
        # 静态图片显示相关
        self.static_image_mode = False  # 是否处于静态图片显示模式
        self.static_image = None  # 当前显示的静态图片
        
        # 调试标志（只输出一次）
        self._debug_roi_logged = False
        
        # 锚点检测相关
        self.current_anchor_offset = (0, 0)  # 当前检测到的偏移量
        self.anchor_detection_enabled = True  # 是否启用锚点检测
        self.anchor_detection_counter = 0  # 检测计数器（用于降低检测频率）
        self.anchor_detection_interval = 5  # 每5帧检测一次锚点
        
        # 手动校准相关
        self.manual_calibration_mode = False  # 是否处于手动校准模式
        self.manual_offset = (0, 0)  # 手动设置的偏移量
        self.use_manual_offset = False  # 是否使用手动偏移量
        
        # 创建侧边栏界面
        self._create_sidebar_ui()
        
        # 注入脚本引擎回调
        if self.script_engine:
            self.script_engine.set_trigger_capture_callback(self._on_manual_trigger)
            self.script_engine.set_reset_stats_callback(self.reset_statistics)
    
    @ErrorHandler.handle_ui_error
    def _create_sidebar_ui(self):
        """创建侧边栏UI（只在侧边栏显示，不创建新窗口）"""
        # 清空父窗口
        for widget in self.parent.winfo_children():
            widget.destroy()
        
        # 标题栏
        title_frame = tk.Frame(self.parent, bg="white")
        title_frame.pack(fill=tk.X, padx=(10, 5), pady=5)
        
        tk.Label(
            title_frame,
            text="运行界面",
            font=("Microsoft YaHei UI", 12, "bold"),
            bg="white",
            fg="#0055A4"
        ).pack(side=tk.LEFT)
        
        # 返回按钮
        tk.Button(
            title_frame,
            text="← 返回",
            font=("Microsoft YaHei UI", 8),
            bg="#F0F0F0",
            relief=tk.FLAT,
            cursor="hand2",
            command=self._on_back_button_click
        ).pack(side=tk.RIGHT)
        
        # 分隔线
        tk.Frame(self.parent, height=1, bg="#E0E0E0").pack(fill=tk.X, padx=(10, 5))
        
        # 创建滚动容器
        canvas = tk.Canvas(self.parent, bg="white", highlightthickness=0)
        scrollbar = tk.Scrollbar(self.parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="white")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # 让 scrollable_frame 宽度跟随 canvas 宽度自适应
        def _on_canvas_configure(event):
            canvas.itemconfig(canvas.find_withtag("all")[0], width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 1. 检测结果大框
        result_frame = tk.LabelFrame(
            scrollable_frame,
            text="检测结果",
            font=("Microsoft YaHei UI", 9, "bold"),
            bg="white",
            relief=tk.GROOVE,
            bd=2
        )
        result_frame.pack(fill=tk.X, padx=(10, 5), pady=3)
        
        # 创建检测结果内容面板
        self._create_detection_result_panel(result_frame)
        
        # 2. 系统变量面板
        tree_label_frame = tk.LabelFrame(
            scrollable_frame,
            text="系统变量",
            font=("Microsoft YaHei UI", 9, "bold"),
            bg="white",
            relief=tk.GROOVE,
            bd=2
        )
        tree_label_frame.pack(fill=tk.BOTH, expand=True, padx=(5, 5), pady=3)
        
        self.tree_view_panel = TreeViewPanel(tree_label_frame)
        self.tree_view_panel.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)
        
        # 3. 运行时设置面板
        control_label_frame = tk.LabelFrame(
            scrollable_frame,
            text="运行时设置",
            font=("Microsoft YaHei UI", 9, "bold"),
            bg="white",
            relief=tk.GROOVE,
            bd=2
        )
        control_label_frame.pack(fill=tk.X, padx=(5, 5), pady=3)
        
        # 锚点检测控制
        anchor_frame = tk.Frame(control_label_frame, bg="white")
        anchor_frame.pack(fill=tk.X, padx=5, pady=3)
        
        tk.Label(
            anchor_frame,
            text="锚点检测:",
            font=("Microsoft YaHei UI", 9),
            bg="white"
        ).pack(side=tk.LEFT)
        
        self.anchor_detection_var = tk.BooleanVar(value=True)
        anchor_checkbox = tk.Checkbutton(
            anchor_frame,
            text="启用锚点检测",
            variable=self.anchor_detection_var,
            command=self._toggle_anchor_detection,
            font=("Microsoft YaHei UI", 8),
            bg="white"
        )
        anchor_checkbox.pack(side=tk.LEFT, padx=(5, 0))
        
        # 第二行：按钮和偏移量显示
        anchor_frame2 = tk.Frame(control_label_frame, bg="white")
        anchor_frame2.pack(fill=tk.X, padx=5, pady=(0, 3))
        
        # 手动校准按钮
        self.calibrate_btn = tk.Button(
            anchor_frame2,
            text="手动校准",
            font=("Microsoft YaHei UI", 7),
            bg="#FFE4B5",
            relief=tk.FLAT,
            cursor="hand2",
            command=self._start_manual_calibration,
            width=8
        )
        self.calibrate_btn.pack(side=tk.LEFT, padx=(20, 5))
        
        # 重置按钮
        self.reset_btn = tk.Button(
            anchor_frame2,
            text="重置",
            font=("Microsoft YaHei UI", 7),
            bg="#F0F0F0",
            relief=tk.FLAT,
            cursor="hand2",
            command=self._reset_anchor_detection,
            width=5
        )
        self.reset_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 恢复视频按钮
        self.resume_video_btn = tk.Button(
            anchor_frame2,
            text="恢复视频",
            font=("Microsoft YaHei UI", 7),
            bg="#E6FFE6",
            relief=tk.FLAT,
            cursor="hand2",
            command=self._resume_video_stream,
            width=8
        )
        self.resume_video_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 偏移量显示
        self.offset_label = tk.Label(
            anchor_frame2,
            text="偏移: (0, 0)",
            font=("Microsoft YaHei UI", 8),
            bg="white",
            fg="#666666"
        )
        self.offset_label.pack(side=tk.RIGHT)
        
        # 定义按钮回调
        callbacks = {
            "select_solution": self._on_select_solution,
            "edit_tolerance": self._on_edit_tolerance,
            "display_settings": self._on_set_display,
            "history_review": self._on_review_history,
            "reset_detection": self._on_reset_detection,
            "reset_statistics": self.reset_statistics,
            "manual_trigger": self._on_manual_trigger,
            "start": self._on_start_button_click
        }
        
        self.control_buttons_panel = ControlButtonsPanel(
            control_label_frame,
            callbacks
        )
        self.control_buttons_panel.pack(fill=tk.X, padx=5, pady=5)

        # 立即同步按钮状态
        self.control_buttons_panel.toggle_start_button(self.is_running)

        # 5. 进入运行界面时，如果是内部时钟模式，自动显示视频流（不启动检测）
        self._init_display_on_enter()
    
    @ErrorHandler.handle_ui_error
    def _create_detection_result_panel(self, parent):
        """创建检测结果面板（整合所有信息）"""
        content = tk.Frame(parent, bg="white")
        content.pack(fill=tk.BOTH, padx=5, pady=5)
        
        # 左侧：检测的部件和略过的部件
        left_frame = tk.Frame(content, bg="white")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 5))
        
        # 检测的部件（带缩进）
        detected_container = tk.Frame(left_frame, bg="white")
        detected_container.pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(
            detected_container,
            text="  检测的部件:",
            font=("Microsoft YaHei UI", 10),  # 增大字体
            bg="white",
            anchor="w"
        ).pack(anchor="w")
        
        self.detected_parts_label = tk.Label(
            detected_container,
            text="  0",
            font=("Microsoft YaHei UI", 18, "bold"),
            bg="white",
            anchor="w"
        )
        self.detected_parts_label.pack(anchor="w", pady=(2, 0))
        
        # 略过的部件（带缩进）
        skipped_container = tk.Frame(left_frame, bg="white")
        skipped_container.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(
            skipped_container,
            text="  略过的部件:",
            font=("Microsoft YaHei UI", 10),  # 增大字体
            bg="white",
            anchor="w"
        ).pack(anchor="w")
        
        self.skipped_parts_label = tk.Label(
            skipped_container,
            text="  0",
            font=("Microsoft YaHei UI", 18, "bold"),  # 增大字体
            bg="white",
            anchor="w"
        )
        self.skipped_parts_label.pack(anchor="w", pady=(2, 0))
        
        # Pass/Reject/Recycle 统计（带颜色块和缩进）
        stats_container = tk.Frame(left_frame, bg="white")
        stats_container.pack(fill=tk.X, padx=(5, 0))
        
        # Pass（绿色）
        pass_frame = tk.Frame(stats_container, bg="white")
        pass_frame.pack(fill=tk.X, pady=4)
        
        tk.Canvas(
            pass_frame,
            width=35,
            height=32,
            bg="#4CAF50",
            highlightthickness=0
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        pass_info = tk.Frame(pass_frame, bg="white")
        pass_info.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        tk.Label(
            pass_info,
            text="Pass:",
            font=("Microsoft YaHei UI", 10),
            bg="white"
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        self.pass_count_label = tk.Label(
            pass_info,
            text="0",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg="white"
        )
        self.pass_count_label.pack(side=tk.LEFT, padx=(0, 12))
        
        self.pass_rate_label = tk.Label(
            pass_info,
            text="0.0 %",
            font=("Microsoft YaHei UI", 10),
            bg="white"
        )
        self.pass_rate_label.pack(side=tk.LEFT)
        
        # Reject（红色）
        reject_frame = tk.Frame(stats_container, bg="white")
        reject_frame.pack(fill=tk.X, pady=4)
        
        tk.Canvas(
            reject_frame,
            width=35,
            height=32,
            bg="#F44336",
            highlightthickness=0
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        reject_info = tk.Frame(reject_frame, bg="white")
        reject_info.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        tk.Label(
            reject_info,
            text="Reject:",
            font=("Microsoft YaHei UI", 10),
            bg="white"
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        self.reject_count_label = tk.Label(
            reject_info,
            text="0",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg="white"
        )
        self.reject_count_label.pack(side=tk.LEFT, padx=(0, 12))
        
        self.reject_rate_label = tk.Label(
            reject_info,
            text="0.0 %",
            font=("Microsoft YaHei UI", 10),
            bg="white"
        )
        self.reject_rate_label.pack(side=tk.LEFT)
        
        # Recycle（黄色）
        recycle_frame = tk.Frame(stats_container, bg="white")
        recycle_frame.pack(fill=tk.X, pady=4)
        
        tk.Canvas(
            recycle_frame,
            width=35,
            height=32,
            bg="#FFC107",
            highlightthickness=0
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        recycle_info = tk.Frame(recycle_frame, bg="white")
        recycle_info.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        tk.Label(
            recycle_info,
            text="Recycle:",
            font=("Microsoft YaHei UI", 10),
            bg="white"
        ).pack(side=tk.LEFT, padx=(0, 8))
        
        self.recycle_count_label = tk.Label(
            recycle_info,
            text="0",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg="white"
        )
        self.recycle_count_label.pack(side=tk.LEFT, padx=(0, 12))
        
        self.recycle_rate_label = tk.Label(
            recycle_info,
            text="0.0 %",
            font=("Microsoft YaHei UI", 10),
            bg="white"
        )
        self.recycle_rate_label.pack(side=tk.LEFT)
        
        # 右侧：时间戳、检测时间、触发频率（带边框，增加宽度）
        right_frame = tk.Frame(content, bg="white", relief=tk.SOLID, bd=1)
        right_frame.pack(side=tk.RIGHT, padx=(5, 5))
        
        # 时间戳
        timestamp_frame = tk.Frame(right_frame, bg="white")
        timestamp_frame.pack(fill=tk.X, padx=18, pady=8)
        
        tk.Label(
            timestamp_frame,
            text="时间戳",
            font=("Microsoft YaHei UI", 9),
            bg="white",
            fg="#666"
        ).pack()
        
        self.timestamp_label = tk.Label(
            timestamp_frame,
            text="--",
            font=("Microsoft YaHei UI", 10),
            bg="white",
            justify=tk.CENTER
        )
        self.timestamp_label.pack(pady=(3, 0))
        
        # 分隔线
        tk.Frame(right_frame, height=1, bg="#D0D0D0").pack(fill=tk.X, padx=10)
        
        # 检测时间
        detection_time_frame = tk.Frame(right_frame, bg="white")
        detection_time_frame.pack(fill=tk.X, padx=18, pady=8)
        
        tk.Label(
            detection_time_frame,
            text="检测时间",
            font=("Microsoft YaHei UI", 9),
            bg="white",
            fg="#666"
        ).pack()
        
        self.detection_time_label = tk.Label(
            detection_time_frame,
            text="-- ms",
            font=("Microsoft YaHei UI", 10),
            bg="white"
        )
        self.detection_time_label.pack(pady=(3, 0))
        
        # 分隔线
        tk.Frame(right_frame, height=1, bg="#D0D0D0").pack(fill=tk.X, padx=10)
        
        # 触发频率
        trigger_freq_frame = tk.Frame(right_frame, bg="white")
        trigger_freq_frame.pack(fill=tk.X, padx=18, pady=8)
        
        tk.Label(
            trigger_freq_frame,
            text="触发频率",
            font=("Microsoft YaHei UI", 9),
            bg="white",
            fg="#666"
        ).pack()
        
        self.trigger_freq_label = tk.Label(
            trigger_freq_frame,
            text="-- Hz",
            font=("Microsoft YaHei UI", 10),
            bg="white"
        )
        self.trigger_freq_label.pack(pady=(3, 0))
    
    @safe_execute(default_return=None, error_message="启动检测流程失败")
    def start_inspection(self):
        """启动检测流程"""
        if self.is_running:
            print("⚠️ 检测已在运行中")
            return

        # 前置检查：必须先选择解决方案
        solution_name = None
        if self.main_window and hasattr(self.main_window, 'saved_ocr_state'):
            solution_name = self.main_window.saved_ocr_state.get('solution_name')

        if not solution_name:
            messagebox.showwarning("未选择方案", "请先在 OCR 工具中选择一个字体库方案，再启动运行。")
            return

        # 前置检查：方案路径必须存在
        solutions_root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "solutions")
        solution_path = os.path.join(solutions_root, solution_name)
        if not os.path.exists(solution_path):
            messagebox.showerror("方案不存在", f"方案路径不存在：\n{solution_path}\n\n请重新在 OCR 工具中选择方案。")
            return

        print("🚀 启动检测流程...")

        self.ocr_engine.template_dir = solution_path
        if not self.ocr_engine.template_loaded:
            if not self.ocr_engine.load_templates():
                messagebox.showerror("错误", "无法加载OCR模板，请检查解决方案配置")
                return

        # 如果是从 workspace 加载的解决方案，用 workspace 里的 layout_config 覆盖
        try:
            workspace_manager = getattr(self.main_window, 'workspace_manager', None)
            ws_name = getattr(self.main_window, '_current_workspace_name', None)
            if workspace_manager and ws_name:
                import os as _os, json as _json
                lc_path = _os.path.join(workspace_manager.workspaces_root, ws_name, "layout_config.json")
                if _os.path.isfile(lc_path):
                    with open(lc_path, "r", encoding="utf-8") as f:
                        self.ocr_engine.recognizer.layout_config = _json.load(f)
        except Exception:
            pass
        
        # 设置运行状态（必须在启动视频循环之前）
        self.is_running = True
        self.stop_event.clear()

        # 应用 config 里的传感器设置到相机（确保加载解决方案后的设置生效）
        try:
            import config as _cfg
            _sensor = _cfg.get_user_sensor_settings()
            _mode = _sensor.get('trigger_mode', 'internal')
            _interval = _sensor.get('interval_ms', 1000)
            if self.camera_controller:
                self.camera_controller.set_trigger_mode(_mode, interval_ms=_interval)
        except Exception as e:
            print(f"⚠️ 应用传感器设置失败: {e}")

        # 获取当前触发模式：优先从 config 读，相机不可用时也能正常工作
        try:
            import config as _cfg
            trigger_mode = _cfg.get_user_sensor_settings().get('trigger_mode', 'internal')
        except Exception:
            trigger_mode = self.camera_controller.get_trigger_mode() if self.camera_controller else 'internal'
        
        # 根据触发模式决定显示方式
        if trigger_mode == "internal":
            # 内部时钟模式：启动连续视频流
            self._start_video_loop()
        else:
            # 硬件/软件触发模式：保持当前画布内容（显示上次的静止帧）
            # 不清空画布，让用户看到上次触发的帧
            pass
        
        # 更新按钮状态为红色"停止"
        self.control_buttons_panel.toggle_start_button(True)
        
        # 更新状态栏
        self.status_label and self.status_label.config(text="运行中...")
        
        # 启动检测线程
        self.inspection_thread = threading.Thread(
            target=self._inspection_loop,
            daemon=True
        )
        self.inspection_thread.start()
        
        print("✅ 检测流程已启动")
    
    @safe_execute(default_return=None, error_message="停止检测流程失败")
    def stop_inspection(self):
        """停止检测流程"""
        if not self.is_running:
            print("⚠️ 检测未在运行")
            return

        import traceback
        print("🛑 stop_inspection 被调用，调用栈:")
        traceback.print_stack(limit=6)
        
        # 停止视频循环（如果正在运行）
        self._stop_video_loop()
        
        # 设置停止标志
        self.is_running = False
        self.stop_event.set()

        # 非阻塞等待线程结束（避免卡住 UI 线程）
        if self.inspection_thread and self.inspection_thread.is_alive():
            threading.Thread(target=self.inspection_thread.join, kwargs={"timeout": 2.0}, daemon=True).start()
        
        # 更新按钮状态为绿色"开始"
        self.control_buttons_panel.toggle_start_button(False)
        
        # 更新状态栏
        self.status_label and self.status_label.config(text="已停止")
        
        print("✅ 检测流程已停止")
    
    @safe_execute(default_return=None, error_message="检测主循环异常")
    def _inspection_loop(self):
        """检测主循环（在独立线程中运行）"""
        # 获取触发模式：优先从 config 读，不依赖相机连接状态
        try:
            import config as _cfg
            trigger_mode = _cfg.get_user_sensor_settings().get('trigger_mode', 'internal')
        except Exception:
            trigger_mode = self.camera_controller.get_trigger_mode() if self.camera_controller else 'internal'

        # 获取内部时钟间隔（毫秒）
        interval_ms = 1000  # 默认1秒
        if self.main_window and hasattr(self.main_window, 'cam'):
            try:
                from config import get_user_sensor_settings
                settings = get_user_sensor_settings()
                interval_ms = settings.get('interval_ms', 1000)
            except Exception:
                pass
        interval_sec = max(interval_ms / 1000.0, 0.05)

        while self.is_running and not self.stop_event.is_set():
            try:
                if trigger_mode == "internal":
                    # 内部时钟模式：按间隔时间自动识别
                    pass  # 直接往下执行识别
                else:
                    # 软件触发 / 手动触发模式：等待触发事件
                    triggered = self.trigger_event.wait(timeout=0.2)
                    if not triggered:
                        continue  # 超时，继续等待
                    self.trigger_event.clear()
                    if not self.is_running:
                        break

                # 1. 采图前执行脚本
                if self.script_engine:
                    self.script_engine.execute("pre_image_process")

                # 2. 图像采集：软件触发模式先发指令让相机曝光新帧
                if trigger_mode == "software":
                    self.camera_controller.execute_software_trigger()
                    # 等待新帧到来（最多500ms）
                    if hasattr(self.camera_controller, 'frame_updated_event'):
                        self.camera_controller.frame_updated_event.clear()
                        self.camera_controller.waiting_for_trigger = True
                        self.camera_controller.frame_updated_event.wait(timeout=0.5)
                        self.camera_controller.waiting_for_trigger = False
                image = self.camera_controller.get_image()
                if image is None:
                    if trigger_mode == "internal":
                        time.sleep(interval_sec)
                    continue

                # 3. 图像采集后先显示（所有触发模式）
                if self.main_window:
                    try:
                        self.main_window.root.after(0, self._display_image_on_canvas, image)
                    except Exception:
                        pass

                # 4. 真实字符识别
                recognition_results = self._run_recognition_on_image(image)

                # 5. 把 OCR 字段结果注入脚本引擎用户变量，再执行 post_image_process
                if self.script_engine:
                    overall_pass = bool(recognition_results) and all(not r['is_abnormal'] for r in recognition_results)
                    result_code = 1 if overall_pass else 3
                    avg_conf = (sum(r['confidence'] for r in recognition_results) / len(recognition_results)) if recognition_results else 0.0
                    card_number = next((r['result'] for r in (recognition_results or []) if r['field_name'] == 'CardNumber'), "")
                    timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
                    self.script_engine.update_system_vars(
                        Result=result_code,
                        CardNumber=card_number,
                        Confidence=avg_conf,
                        Timestamp=timestamp_str,
                    )
                    # 把每个 OCR 字段的识别值和结果注入为用户变量（供脚本直接使用）
                    # 扁平键：CardNumber / Name / Date（向后兼容）
                    # 点号键：CardNumber.Result / OCR.CardNumber / OCR.CardNumber.Result
                    for r in (recognition_results or []):
                        field = r['field_name']
                        val = r['result']
                        res = "FAIL" if r['is_abnormal'] else "PASS"
                        # 扁平键（向后兼容）
                        self.script_engine._user_vars[field] = val
                        self.script_engine._user_vars[f"{field}_Result"] = res
                        # 点号键：CardNumber.Result（控制界面双击插入的格式）
                        self.script_engine._user_vars[f"{field}.Result"] = res
                        # OCR 前缀点号键
                        self.script_engine._user_vars[f"OCR.{field}"] = val
                        self.script_engine._user_vars[f"OCR.{field}.Result"] = res
                    self.script_engine.execute("post_image_process")

                # 6. 更新统计数据和显示
                try:
                    print(f"[检测线程] 准备调度UI更新, count将变为{self.image_detection_count+1}")
                    self.main_window.root.after(0, self._update_recognition_results, recognition_results or [])
                except Exception as e:
                    print(f"[检测线程] after调度失败: {e}")

                # 8. 计算触发频率
                current_time = time.time()
                if self.last_trigger_time is not None:
                    time_diff = current_time - self.last_trigger_time
                    if time_diff > 0:
                        self.trigger_frequency = 1.0 / time_diff
                self.last_trigger_time = current_time

                # 9. 内部模式按间隔等待
                if trigger_mode == "internal":
                    time.sleep(interval_sec)

            except Exception as e:
                print(f"[inspection_loop] 异常: {e}")
                time.sleep(0.1)

        print(f"[inspection_loop] 循环退出 — is_running={self.is_running}, stop_event={self.stop_event.is_set()}")
    
    @safe_execute(default_return=None, error_message="更新显示失败")
    def update_display(self, image, result):
        """
        更新显示（只更新侧边栏的统计信息）
        
        参数:
            image: numpy数组，相机捕获的图像（由主窗口显示）
            result: 识别结果对象
        """
        # 更新统计数据
        stats = self.stats_manager.get_statistics()
        
        # 更新检测的部件（总数）
        self.detected_parts_label.config(text=f"  {stats['total']}")
        
        # 更新略过的部件（暂时设为0）
        self.skipped_parts_label.config(text="  0")
        
        # 更新 Pass/Reject/Recycle
        self.pass_count_label.config(text=str(stats["pass"]))
        self.pass_rate_label.config(text=f"{stats['pass_rate']:.1f} %")
        
        self.reject_count_label.config(text=str(stats["reject"]))
        self.reject_rate_label.config(text=f"{stats['reject_rate']:.1f} %")
        
        self.recycle_count_label.config(text=str(stats["recycle"]))
        self.recycle_rate_label.config(text=f"{stats['recycle_rate']:.1f} %")

        # 持久化保存统计数据
        self._save_stats()

        # 触发频率
        self.trigger_freq_label.config(text=f"{self.trigger_frequency:.3f} Hz")
    
    @safe_execute(default_return=None, error_message="重置统计数据失败")
    def _save_stats(self):
        """把当前统计数据写回主窗口内存"""
        if not self.main_window or not hasattr(self.main_window, 'persistent_stats'):
            return
        stats = self.stats_manager.get_statistics()

        # 安全读取 UI 控件文本（控件销毁后用缓存值）
        def _safe_cget(widget, attr, default):
            try:
                if widget and widget.winfo_exists():
                    return widget.cget(attr)
            except Exception:
                pass
            return default

        self.main_window.persistent_stats = {
            "pass": stats["pass"],
            "reject": stats["reject"],
            "recycle": stats["recycle"],
            "image_detection_count": self.image_detection_count,
            "timestamp": _safe_cget(self.timestamp_label, "text", "--"),
            "detection_time": _safe_cget(self.detection_time_label, "text", "-- ms"),
            "trigger_freq": _safe_cget(self.trigger_freq_label, "text", "-- Hz"),
            "tree_vars": self._get_tree_vars()
        }

    def _get_tree_vars(self):
        """获取系统变量树的所有节点值"""
        result = {}
        try:
            for path, node_id in self.tree_view_panel._node_map.items():
                values = self.tree_view_panel._tree.item(node_id, "values")
                tags = self.tree_view_panel._tree.item(node_id, "tags")
                result[path] = {
                    "value": values[0] if values else "",
                    "tag": tags[0] if tags else ""
                }
        except Exception:
            pass
        return result

    def _load_stats(self):
        """从主窗口内存恢复统计数据"""
        if not self.main_window or not hasattr(self.main_window, 'persistent_stats'):
            return
        data = self.main_window.persistent_stats
        for _ in range(data.get("pass", 0)):
            self.stats_manager.increment_pass()
        for _ in range(data.get("reject", 0)):
            self.stats_manager.increment_reject()
        for _ in range(data.get("recycle", 0)):
            self.stats_manager.increment_recycle()
        self.image_detection_count = data.get("image_detection_count", 0)

    def reset_statistics(self):
        """重置统计数据"""
        # 重置统计管理器
        self.stats_manager.reset()
        self.image_detection_count = 0

        # 重置检测结果显示
        self.detected_parts_label.config(text="  0")
        self.skipped_parts_label.config(text="  0")
        self.pass_count_label.config(text="0")
        self.pass_rate_label.config(text="0.0 %")
        self.reject_count_label.config(text="0")
        self.reject_rate_label.config(text="0.0 %")
        self.recycle_count_label.config(text="0")
        self.recycle_rate_label.config(text="0.0 %")

        # 重置时间信息
        self.timestamp_label.config(text="--")
        self.detection_time_label.config(text="-- ms")
        self.trigger_freq_label.config(text="-- Hz")

        # 重置系统变量树
        self.tree_view_panel.clear_all()

        # 清除持久化数据
        self._save_stats()
    
    @safe_execute(default_return=None, error_message="返回按钮处理失败")
    def _on_back_button_click(self):
        """返回按钮点击事件（检测继续在后台运行）"""
        if self.on_back_callback:
            self.on_back_callback()
    
    @safe_execute(default_return=None, error_message="开始按钮处理失败")
    def _on_start_button_click(self):
        """开始按钮点击事件"""
        if self.is_running:
            # 已在运行：点击变为停止
            self.stop_inspection()
            self.control_buttons_panel.toggle_start_button(False)
        else:
            self.start_inspection()
            self.control_buttons_panel.toggle_start_button(True)
    
    @safe_execute(default_return=None, error_message="字符识别失败")
    def _perform_character_recognition(self, image):
        """执行字符识别"""
        # 初始化识别器（如果还没有初始化）
        if self.recognizer is None:
            self._initialize_recognizer()
        
        if self.recognizer is None:
            messagebox.showerror("错误", "识别器初始化失败，请检查解决方案配置")
            return
        
        # 检查是否有ROI配置
        if not self.main_window or not hasattr(self.main_window, 'saved_ocr_state'):
            messagebox.showwarning("提示", "请先在OCR工具中配置ROI区域")
            return
        
        saved_state = self.main_window.saved_ocr_state
        if not saved_state.get('has_state', False):
            messagebox.showwarning("提示", "请先在OCR工具中配置ROI区域")
            return
        
        roi_layout = saved_state.get('roi_layout', {})
        if not roi_layout:
            messagebox.showwarning("提示", "没有找到ROI配置，请先在OCR工具中配置识别区域")
            return
        
        print(f"🔍 开始字符识别，ROI区域数量: {len(roi_layout)}")
        print(f"📋 ROI字段: {list(roi_layout.keys())}")
        
        # 更新状态
        self.status_label and self.status_label.config(text="正在识别...")
        
        # 执行识别
        recognition_results = self._run_recognition_on_image(image)
        
        # 更新显示
        self._update_recognition_results(recognition_results)
        
        # 更新状态
        overall = "PASS" if all(not r['is_abnormal'] for r in results) else "FAIL"
        self.status_label and self.status_label.config(text=f"识别完成 - {overall}")
    
    @safe_execute(default_return=None, error_message="识别器初始化失败")
    def _initialize_recognizer(self):
        """初始化识别器（可从后台线程调用，不弹 messagebox）"""
        if not self.main_window or not hasattr(self.main_window, 'saved_ocr_state'):
            print("⚠️ 识别器初始化失败：请先在OCR工具中选择解决方案")
            return

        saved_state = self.main_window.saved_ocr_state
        if not saved_state.get('has_state', False):
            print("⚠️ 识别器初始化失败：请先在OCR工具中选择解决方案")
            return

        solution_name = saved_state.get('solution_name')
        if not solution_name:
            print("⚠️ 识别器初始化失败：OCR工具中没有选择解决方案")
            return

        solutions_root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "solutions")
        solution_path = os.path.join(solutions_root, solution_name)

        if not os.path.exists(solution_path):
            print(f"⚠️ 识别器初始化失败：解决方案路径不存在 {solution_path}")
            return

        self.recognizer = BankCardRecognizer()
        template_count = self.recognizer.load_templates(solution_path)
        self.current_solution_path = solution_path

        if template_count == 0:
            print(f"⚠️ 解决方案 '{solution_name}' 中没有找到模板文件")
        else:
            print(f"✅ 识别器初始化成功，使用OCR工具选择的解决方案: {solution_name}，加载了 {template_count} 个模板")
    
    @safe_execute(default_return=[], error_message="图像识别处理失败")
    def _run_recognition_on_image(self, image):
        """在图像上运行识别算法"""
        if not self.main_window or not hasattr(self.main_window, 'saved_ocr_state'):
            return []
        
        saved_state = self.main_window.saved_ocr_state
        roi_layout = saved_state.get('roi_layout', {})
        
        if not roi_layout:
            return []

        # 识别器懒初始化
        if self.recognizer is None:
            self._initialize_recognizer()
        if self.recognizer is None:
            return []
        
        results = []
        
        # 标准化图像尺寸（如果需要）
        working_image = image.copy()
        if self.recognizer.standard_image_size is not None:
            current_h, current_w = working_image.shape[:2]
            standard_w, standard_h = self.recognizer.standard_image_size
            
            if (current_w, current_h) != (standard_w, standard_h):
                working_image = cv2.resize(working_image, (standard_w, standard_h), interpolation=cv2.INTER_LINEAR)
        
        # 获取锚点偏移量
        offset_x, offset_y = 0, 0
        if self.anchor_detection_enabled:
            if self.use_manual_offset:
                offset_x, offset_y = self.manual_offset
            else:
                offset_x, offset_y = self.recognizer.locate_anchor_offset(working_image)
        
        # 对每个ROI区域进行识别
        for field_name, field_data in roi_layout.items():
            if field_name == "FirstDigitAnchor":
                continue  # 跳过锚点字段
            
            try:
                # 获取ROI坐标
                coords = field_data.get('roi', field_data.get('coords', []))
                if not coords or len(coords) != 4:
                    continue
                
                x, y, w, h = coords
                
                # 应用偏移量（如果启用锚点检测）
                if self.anchor_detection_enabled:
                    x += offset_x
                    y += offset_y
                
                # 边界检查
                img_h, img_w = working_image.shape[:2]
                x = max(0, min(x, img_w - 1))
                y = max(0, min(y, img_h - 1))
                x2 = max(x + 1, min(x + w, img_w))
                y2 = max(y + 1, min(y + h, img_h))
                
                # 提取ROI
                roi = working_image[y:y2, x:x2]
                if roi.size == 0:
                    continue
                
                # 执行字符识别
                result = self._recognize_roi(roi, field_name, (x, y, x2 - x, y2 - y))
                if result:
                    results.append(result)
                    
            except Exception as e:
                print(f"识别字段 {field_name} 时出错: {e}")
                continue
        
        return results
    
    @safe_execute(default_return=None, error_message="ROI识别失败")
    def _recognize_roi(self, roi_image, field_name, box_coords):
        """识别单个ROI区域"""
        import time
        
        t_start = time.perf_counter()
        
        # 图像预处理
        padding = 10
        roi_padded = cv2.copyMakeBorder(roi_image, padding, padding, padding, padding, cv2.BORDER_CONSTANT, value=(0,0,0))
        binary_detect, binary_template = self.recognizer.preprocess_image(roi_padded)
        
        # 字符分割
        cnts, _ = cv2.findContours(binary_detect, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        heights = []
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            if h < 8 or w < 3:  # 过滤太小的区域
                continue
            if w / h > 4.0:  # 过滤宽高比异常的区域
                continue
            candidates.append((x, y, w, h))
            heights.append(h)
        
        if not candidates:
            return None
        
        # 字符高度过滤
        if len(candidates) > 2:
            median_h = np.median(heights)
            valid_chars = []
            for (x, y, w, h) in candidates:
                if h < median_h * 0.5 or h > median_h * 1.8:
                    continue
                valid_chars.append((x, y, w, h))
        else:
            valid_chars = candidates
        
        # 字符排序（多行支持）
        valid_chars = self._sort_multiline_chars(valid_chars)
        
        # 字符识别
        result_str = ""
        total_conf = 0
        char_details = []
        
        for idx, (x, y, w, h) in enumerate(valid_chars):
            char_roi = binary_template[y:y+h, x:x+w]
            label, score, _ = self.recognizer.match_char(char_roi, field_type=field_name, idx=idx)
            result_str += label
            total_conf += score
            
            # 计算字符在原图中的坐标
            global_char_x = box_coords[0] + x - padding
            global_char_y = box_coords[1] + y - padding
            char_details.append({
                "char": label,
                "score": score,
                "box": (global_char_x, global_char_y, w, h)
            })
        
        t_end = time.perf_counter()
        field_time_ms = (t_end - t_start) * 1000
        
        # 计算平均置信度和最小置信度
        avg_conf = total_conf / len(valid_chars) if valid_chars else 0
        min_char_conf = min((d['score'] for d in char_details), default=0)
        
        # 推断字段类型
        final_type = self.recognizer.infer_field_type(result_str) if field_name == "Auto" else field_name
        
        # 异常检测（读取字段属性配置）
        is_abnormal = False
        notes = []

        # 从 layout_config 读取该字段的属性
        layout_cfg = self.recognizer.layout_config
        field_props = layout_cfg.get("field_props", {}).get(field_name, {})
        enabled = field_props.get("enabled", True)
        min_conf = field_props.get("min_confidence", 80) / 100.0
        expected_chars = field_props.get("expected_chars", 0)
        ignore_space = field_props.get("ignore_space", False)

        # 忽略空格
        if ignore_space:
            result_str = result_str.replace(" ", "")

        # 字段禁用
        if not enabled:
            notes.append("字段已禁用")
            return {
                "field_name": field_name,
                "result": "",
                "field_type": field_name,
                "confidence": 0.0,
                "time_ms": 0.0,
                "box": box_coords,
                "char_details": [],
                "is_abnormal": False,
                "notes": ["字段已禁用（跳过）"]
            }

        # 置信度检查：任意一个字符低于阈值则失败，并用 ? 替代该字符
        low_conf_chars = []
        for d in char_details:
            if d['score'] < min_conf:
                low_conf_chars.append(d['char'])
                d['char'] = '?'

        if low_conf_chars:
            is_abnormal = True
            notes.append(f"最低字符置信度 {min_char_conf:.0%} 低于阈值 {min_conf:.0%}")

        # 重新拼接结果（低置信度字符已替换为 ?）
        result_str = "".join(d['char'] for d in char_details)

        # 期望字符数检查
        if expected_chars > 0 and len(result_str) != expected_chars:
            is_abnormal = True
            notes.append(f"字符数 {len(result_str)} 不符合期望 {expected_chars}")
        
        return {
            "field_name": field_name,
            "result": result_str,
            "field_type": final_type,
            "confidence": float(round(avg_conf, 4)),
            "time_ms": float(round(field_time_ms, 2)),
            "box": box_coords,
            "char_details": char_details,
            "is_abnormal": is_abnormal,
            "notes": notes
        }
    
    @safe_execute(default_return=[], error_message="多行字符排序失败")
    def _sort_multiline_chars(self, chars_data):
        """多行字符排序"""
        if not chars_data:
            return []
        
        # 按Y坐标排序
        chars_data.sort(key=lambda b: b[1])
        
        lines = []
        current_line = [chars_data[0]]
        ref_h = chars_data[0][3]
        
        for i in range(1, len(chars_data)):
            curr = chars_data[i]
            prev = current_line[-1]
            
            # 如果Y坐标差异小于字符高度的60%，认为在同一行
            if abs(curr[1] - prev[1]) < ref_h * 0.6:
                current_line.append(curr)
            else:
                # 当前行按X坐标排序
                current_line.sort(key=lambda b: b[0])
                lines.append(current_line)
                current_line = [curr]
                ref_h = curr[3]
        
        # 处理最后一行
        current_line.sort(key=lambda b: b[0])
        lines.append(current_line)
        
        # 展平所有行
        return [item for sublist in lines for item in sublist]
    
    @safe_execute(default_return=None, error_message="更新识别结果失败")
    def _update_recognition_results(self, results):
        """更新识别结果显示"""
        print(f"[UI更新] _update_recognition_results 被调用, count={self.image_detection_count+1}")
        # 先做统计数据更新（无论 UI 是否存活）
        self.image_detection_count += 1
        if not results:
            self.stats_manager.increment_reject()
        else:
            reject_count = sum(1 for r in results if r['is_abnormal'])
            if reject_count == 0:
                self.stats_manager.increment_pass()
            else:
                self.stats_manager.increment_reject()
        self._save_stats()

        # UI 控件存活检查，返回主界面后跳过 UI 更新
        ui_alive = False
        try:
            ui_alive = self.detected_parts_label.winfo_exists()
        except Exception:
            pass
        if not ui_alive:
            return

        stats = self.stats_manager.get_statistics()
        self.detected_parts_label.config(text=f"  {self.image_detection_count}")
        self.pass_count_label.config(text=str(stats["pass"]))
        self.reject_count_label.config(text=str(stats["reject"]))
        self.recycle_count_label.config(text=str(stats["recycle"]))
        if stats['total'] > 0:
            self.pass_rate_label.config(text=f"{stats['pass_rate']:.1f} %")
            self.reject_rate_label.config(text=f"{stats['reject_rate']:.1f} %")
            self.recycle_rate_label.config(text=f"{stats['recycle_rate']:.1f} %")

        current_time = time.time()
        self.timestamp_label.config(text=time.strftime("%m/%d/%Y\n%H:%M:%S", time.localtime(current_time)))

        if not results:
            self.tree_view_panel.update_variable("AppVar.Result", "FAIL")
            self.tree_view_panel.update_variable("AppVar.Confidence", "0.00%")
            self.detection_time_label.config(text="0.000 ms")
            return

        total_fields = len(results)
        reject_count = sum(1 for r in results if r['is_abnormal'])
        total_time = sum(r['time_ms'] for r in results)
        avg_confidence = sum(r['confidence'] for r in results) / total_fields

        self.detection_time_label.config(text=f"{total_time:.3f} ms")

        overall_status = "PASS" if reject_count == 0 else "FAIL"
        self.tree_view_panel.update_variable("AppVar.Result", overall_status)
        self.tree_view_panel.update_variable("AppVar.Confidence", f"{avg_confidence:.2%}")
        
        # 添加识别结果到系统变量，每个字段包含识别值和通过/失败状态
        for result in results:
            var_name = f"OCR.{result['field_name']}"
            self.tree_view_panel.update_variable(var_name, result['result'])
            field_status = "FAIL" if result['is_abnormal'] else "PASS"
            self.tree_view_panel.update_variable(f"{var_name}.Result", field_status)
            # 字段名节点也染色
            color = "fail" if result['is_abnormal'] else "pass"
            self.tree_view_panel.set_node_color(var_name, color)
        
        # 展开OCR节点以显示识别结果
        self.tree_view_panel.expand_all()
        
        print("=== 识别结果 ===")
        for result in results:
            status = "异常" if result['is_abnormal'] else "正常"
            print(f"{result['field_name']}: {result['result']} (置信度: {result['confidence']:.2%}, {status})")
        print(f"总耗时: {total_time:.2f} ms")
    
    @safe_execute(default_return=None, error_message="选择解决方案失败")
    def _on_select_solution(self):
        """选择解决方案按钮回调"""
        messagebox.showinfo("提示", "选择解决方案功能待实现")
    
    def _load_solution_scripts(self, solution_data: dict):
        """
        加载方案中的脚本配置并触发 solution_initialize
        
        参数:
            solution_data: 方案数据字典（含 scripts 键）
        """
        if self.script_engine:
            scripts = solution_data.get("scripts", {})
            self.script_engine.set_scripts(scripts)
            self.script_engine.execute("solution_initialize")
    
    @safe_execute(default_return=None, error_message="编辑容忍度失败")
    def _on_edit_tolerance(self):
        """编辑容忍度按钮回调"""
        messagebox.showinfo("提示", "编辑容忍度功能待实现")
    
    @safe_execute(default_return=None, error_message="设置显示失败")
    def _on_set_display(self):
        """设置显示按钮回调"""
        messagebox.showinfo("提示", "设置显示功能待实现")
    
    @safe_execute(default_return=None, error_message="历史数据回顾失败")
    def _on_review_history(self):
        """历史数据回顾按钮回调"""
        messagebox.showinfo("提示", "历史数据回顾功能待实现")
    
    @safe_execute(default_return=None, error_message="打开图片失败")
    def _on_reset_detection(self):
        """打开图片按钮回调（原重置检测按钮）"""
        self._open_image_file()
    
    @safe_execute(default_return=None, error_message="手动触发失败")
    def _on_manual_trigger(self):
        """手动触发按钮/trigger_capture()：触发一次识别。

        只有用户已点击"开始"（is_running == True）时才生效。
        可能从 periodic 脚本线程调用，trigger_event.set() 本身是线程安全的。
        """
        if not self.is_running:
            return
        self.trigger_event.set()
    
    @safe_execute(default_return=None, error_message="初始化显示失败")
    def _init_display_on_enter(self):
        """进入运行界面时初始化显示"""
        # 恢复持久化的统计数据到 UI
        stats = self.stats_manager.get_statistics()
        self.detected_parts_label.config(text=f"  {self.image_detection_count}")
        self.pass_count_label.config(text=str(stats["pass"]))
        self.pass_rate_label.config(text=f"{stats['pass_rate']:.1f} %")
        self.reject_count_label.config(text=str(stats["reject"]))
        self.reject_rate_label.config(text=f"{stats['reject_rate']:.1f} %")
        self.recycle_count_label.config(text=str(stats["recycle"]))
        self.recycle_rate_label.config(text=f"{stats['recycle_rate']:.1f} %")

        # 恢复时间信息和系统变量
        if self.main_window and hasattr(self.main_window, 'persistent_stats'):
            data = self.main_window.persistent_stats
            self.timestamp_label.config(text=data.get("timestamp", "--"))
            self.detection_time_label.config(text=data.get("detection_time", "-- ms"))
            self.trigger_freq_label.config(text=data.get("trigger_freq", "-- Hz"))
            # 恢复系统变量树
            tree_vars = data.get("tree_vars", {})
            if tree_vars:
                for path, info in tree_vars.items():
                    self.tree_view_panel.update_variable(path, info.get("value", ""))
                    tag = info.get("tag", "")
                    if tag in ("pass", "fail"):
                        self.tree_view_panel.set_node_color(path, tag)
                self.tree_view_panel.expand_all()

        # 延迟100ms执行，确保UI完全初始化
        if self.main_window and hasattr(self.main_window, 'root'):
            self.main_window.root.after(100, self._init_display_on_enter_delayed)
        else:
            self.parent.after(100, self._init_display_on_enter_delayed)

        # 从 saved_ocr_state 读取字段信息，显示在 OCR 节点下
        self._populate_ocr_fields_from_state()
    
    @safe_execute(default_return=None, error_message="延迟初始化显示失败")
    def _populate_ocr_fields_from_state(self):
        """从 saved_ocr_state 读取字段定义，预填充到系统变量 OCR 节点下"""
        if not self.main_window or not hasattr(self.main_window, 'saved_ocr_state'):
            return
        state = self.main_window.saved_ocr_state
        roi_layout = state.get('roi_layout', {})
        if not roi_layout:
            return
        for field_name in roi_layout:
            if field_name == "FirstDigitAnchor":
                continue
            var_path = f"OCR.{field_name}"
            result_path = f"OCR.{field_name}.Result"
            # 只在节点不存在时添加（避免覆盖已有识别结果）
            if var_path not in self.tree_view_panel._node_map:
                self.tree_view_panel.update_variable(var_path, "--")
            if result_path not in self.tree_view_panel._node_map:
                self.tree_view_panel.update_variable(result_path, "--")
        self.tree_view_panel.expand_all()

    def _init_display_on_enter_delayed(self):
        """延迟执行的初始化显示"""
        # 获取当前触发模式
        trigger_mode = self.camera_controller.get_trigger_mode()
        
        if trigger_mode == "internal":
            # 内部时钟模式：确保视频循环在运行（无论是否正在检测）
            if not self.video_loop_running:
                self.video_loop_running = True
                self._video_loop_iteration()
        else:
            # 硬件/软件触发模式：显示当前静止帧
            if self.main_window:
                # 获取当前帧
                image = self.camera_controller.get_image()
                if image is not None:
                    # 显示静止帧（包含 ROI 框）
                    self._display_image_on_canvas(image)
                else:
                    # 如果无法获取图像，清空画布
                    self.main_window.canvas.delete("all")
                    self.main_window.preview_canvas.delete("all")

    @safe_execute(default_return=None, error_message="启动视频循环失败")
    def _start_video_loop(self):
        """启动视频循环（用于内部时钟模式）"""
        if self.video_loop_running:
            print("⚠️ 视频循环已在运行中")
            return
        
        if not self.main_window:
            print("⚠️ 主窗口引用不可用，无法启动视频循环")
            return
        
        print("🎬 启动视频循环...")
        self.video_loop_running = True
        self._video_loop_iteration()
        print("✅ 视频循环已启动")
    
    @safe_execute(default_return=None, error_message="停止视频循环失败")
    def _stop_video_loop(self):
        """停止视频循环"""
        if not self.video_loop_running:
            return
        
        self.video_loop_running = False
        
        # 取消待执行的回调
        if self.video_loop_id:
            try:
                if self.main_window and hasattr(self.main_window, 'root'):
                    self.main_window.root.after_cancel(self.video_loop_id)
                else:
                    self.parent.after_cancel(self.video_loop_id)
                self.video_loop_id = None
            except Exception as e:
                pass
    
    @safe_execute(default_return=None, error_message="视频循环迭代失败")
    def _video_loop_iteration(self):
        """视频循环的单次迭代"""
        
        # 【关键修复】首先检查全局标志
        if not RunInterface._global_video_enabled:
            self.video_loop_running = False
            return
        
        
        # 【关键修复】检查实例标志
        if not self.video_loop_running:
            return
        
        
        # 【关键修复】检查 parent 是否还存在（是否被销毁）
        try:
            if not self.parent.winfo_exists():
                self.video_loop_running = False
                return
        except Exception as e:
            self.video_loop_running = False
            return
        
        
        if not self.main_window:
            return

        
        # 【新增】如果处于静态图片模式，不更新视频帧
        if self.static_image_mode:
            # 调度下一次迭代，但不更新图像
            if self.video_loop_running:
                if self.main_window and hasattr(self.main_window, 'root'):
                    self.video_loop_id = self.main_window.root.after(50, self._video_loop_iteration)
                else:
                    self.video_loop_id = self.parent.after(50, self._video_loop_iteration)
            return
        
        try:
            # 获取图像
            image = self.camera_controller.get_image()
            
            if image is not None:
                # 显示到主窗口画布
                self._display_image_on_canvas(image)
            else:
                print(f"   ⚠️ 图像为 None")
        
        except Exception as e:
            print(f"   ❌ 异常: {e}")
            import traceback
            traceback.print_exc()
        
        # 调度下一次迭代
        if self.video_loop_running:
            # 【关键修复】使用主窗口的 root.after，而不是 parent.after
            # 这样即使 parent 被销毁，也能正确取消回调
            if self.main_window and hasattr(self.main_window, 'root'):
                self.video_loop_id = self.main_window.root.after(50, self._video_loop_iteration)
            else:
                self.video_loop_id = self.parent.after(50, self._video_loop_iteration)
    
    @safe_execute(default_return=None, error_message="画布图像显示失败")
    def _display_image_on_canvas(self, image):
        """在主窗口画布上显示图像"""
        if not self.main_window:
            return
        
        from PIL import Image, ImageTk
        import cv2
        
        canvas = self.main_window.canvas
        
        # 获取画布尺寸
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()
        
        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width = 800
            canvas_height = 600
        
        # 获取图像尺寸
        img_height, img_width = image.shape[:2]
        
        # 计算缩放比例（高度90%）
        scale = (canvas_height * 0.9) / img_height
        
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        
        # 调整图像大小
        resized_image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
        
        # 转换为RGB格式
        if len(resized_image.shape) == 2:
            resized_image = cv2.cvtColor(resized_image, cv2.COLOR_GRAY2RGB)
        else:
            resized_image = cv2.cvtColor(resized_image, cv2.COLOR_BGR2RGB)
        
        # 转换为PIL Image
        pil_image = Image.fromarray(resized_image)
        
        # 转换为Tkinter PhotoImage
        tk_image = ImageTk.PhotoImage(pil_image)
        
        # 保存引用（防止被垃圾回收）
        self._current_tk_image = tk_image
        
        # 完全清空画布，避免重叠显示
        canvas.delete("all")
        
        # 显示图像
        cx = canvas_width // 2
        cy = canvas_height // 2
        canvas.create_image(cx, cy, image=tk_image, tags="run_video_frame")
        
        # 绘制ROI框（如果有保存的布局配置）
        self._draw_roi_boxes(canvas, cx, cy, new_width, new_height, scale)
        
        # 更新偏移量显示
        self._update_offset_display()
    
    @safe_execute(default_return=None, error_message="绘制ROI框失败")
    def _draw_roi_boxes(self, canvas, cx, cy, img_width, img_height, scale):
        """
        在画布上绘制动态调整的ROI框
        
        参数:
            canvas: 画布对象
            cx, cy: 图像中心坐标
            img_width, img_height: 缩放后的图像尺寸
            scale: 缩放比例
        """
        if not self.main_window or not hasattr(self.main_window, 'saved_ocr_state'):
            if not self._debug_roi_logged:
                print("🔍 [ROI调试] main_window 或 saved_ocr_state 不存在")
                self._debug_roi_logged = True
            return
        
        # 获取保存的ROI布局
        saved_state = self.main_window.saved_ocr_state
        
        if not saved_state.get('has_state', False):
            if not self._debug_roi_logged:
                print(f"🔍 [ROI调试] has_state = False")
                self._debug_roi_logged = True
            return
        
        roi_layout = saved_state.get('roi_layout', {})
        
        if not roi_layout:
            if not self._debug_roi_logged:
                print(f"🔍 [ROI调试] roi_layout 为空")
                self._debug_roi_logged = True
            return
        
        # 获取当前偏移量
        if not self.anchor_detection_enabled:
            # 禁用锚点检测：使用绝对坐标（偏移量为0）
            offset_x, offset_y = 0, 0
        elif self.use_manual_offset:
            # 启用锚点检测且使用手动偏移量
            offset_x, offset_y = self.manual_offset
        else:
            # 启用锚点检测且使用自动检测偏移量（降低检测频率以提高性能）
            self.anchor_detection_counter += 1
            if self.anchor_detection_counter >= self.anchor_detection_interval:
                self.anchor_detection_counter = 0
                try:
                    # 根据当前模式选择图像源
                    if self.static_image_mode and self.static_image is not None:
                        # 静态图片模式：使用保存的静态图片
                        current_image = self.static_image
                    else:
                        # 视频模式：从相机获取当前图像
                        current_image = self.camera_controller.get_image()
                    
                    if current_image is not None:
                        self.current_anchor_offset = self._detect_anchor_offset(current_image)
                    else:
                        self.current_anchor_offset = (0, 0)
                except Exception as e:
                    self.current_anchor_offset = (0, 0)
            
            offset_x, offset_y = self.current_anchor_offset
        
        if not self._debug_roi_logged:
            print(f"✅ [ROI调试] 准备绘制 {len(roi_layout)} 个字段框，偏移量: ({offset_x}, {offset_y})")
            print(f"   字段列表: {list(roi_layout.keys())}")
            self._debug_roi_logged = True
        
        # 计算图像左上角坐标
        img_left = cx - img_width // 2
        img_top = cy - img_height // 2
        
        # 绘制每个ROI框
        for field_name, field_data in roi_layout.items():
            try:
                # 获取原始坐标
                coords = field_data.get('roi', field_data.get('coords', []))
                search_area = field_data.get('search_area', coords)
                is_anchor = field_data.get('is_anchor', False)
                
                if not coords or len(coords) != 4:
                    continue
                
                x, y, w, h = coords
                
                if field_name == "FirstDigitAnchor":
                    # 锚点特殊处理：只有在启用锚点检测时才显示锚点可视化
                    if self.anchor_detection_enabled:
                        self._draw_anchor_visualization(canvas, field_data, img_left, img_top, scale, offset_x, offset_y)
                else:
                    # 普通字段：根据锚点检测状态决定是否应用偏移量
                    if self.anchor_detection_enabled:
                        # 启用锚点检测：应用偏移量（相对坐标）
                        adjusted_x = x + offset_x
                        adjusted_y = y + offset_y
                        box_color = "#00FF00"  # 绿色（调整后的ROI）
                        label_suffix = f" [偏移:{offset_x},{offset_y}]" if offset_x != 0 or offset_y != 0 else ""
                    else:
                        # 禁用锚点检测：使用绝对坐标（不应用偏移量）
                        adjusted_x = x
                        adjusted_y = y
                        box_color = "#0080FF"  # 蓝色（绝对坐标）
                        label_suffix = " [绝对坐标]"
                    
                    # 应用缩放比例
                    scaled_x = int(adjusted_x * scale)
                    scaled_y = int(adjusted_y * scale)
                    scaled_w = int(w * scale)
                    scaled_h = int(h * scale)
                    
                    # 转换为画布坐标
                    canvas_x1 = img_left + scaled_x
                    canvas_y1 = img_top + scaled_y
                    canvas_x2 = canvas_x1 + scaled_w
                    canvas_y2 = canvas_y1 + scaled_h
                    
                    # 绘制ROI框
                    canvas.create_rectangle(
                        canvas_x1, canvas_y1, canvas_x2, canvas_y2,
                        outline=box_color,
                        width=2,
                        tags="run_roi_box"
                    )
                    
                    # 绘制字段名称标签
                    label_text = f"{field_name}{label_suffix}"
                    
                    # 绘制标签背景
                    canvas.create_rectangle(
                        canvas_x1, canvas_y1 - 20, canvas_x1 + len(label_text) * 7, canvas_y1,
                        fill=box_color,
                        outline="",
                        tags="run_roi_box"
                    )
                    
                    # 绘制标签文字
                    canvas.create_text(
                        canvas_x1 + 2, canvas_y1 - 10,
                        text=label_text,
                        anchor="w",
                        fill="white",
                        font=("Arial", 8, "bold"),
                        tags="run_roi_box"
                    )
                
            except Exception as e:
                # 跳过无效的ROI
                pass
    
    @safe_execute(default_return=None, error_message="绘制锚点可视化失败")
    def _draw_anchor_visualization(self, canvas, anchor_data, img_left, img_top, scale, offset_x, offset_y):
        """
        绘制锚点的完整可视化（搜索区域、基准位置、当前位置）
        
        参数:
            canvas: 画布对象
            anchor_data: 锚点数据
            img_left, img_top: 图像左上角坐标
            scale: 缩放比例
            offset_x, offset_y: 检测到的偏移量
        """
        anchor_rect = anchor_data.get('roi', [])  # 基准位置
        search_area = anchor_data.get('search_area', anchor_rect)  # 搜索区域
        
        if not anchor_rect or len(anchor_rect) != 4:
            return
        if not search_area or len(search_area) != 4:
            return
        
        # 1. 绘制搜索区域（大框，虚线，蓝色）
        sx, sy, sw, sh = search_area
        scaled_sx = int(sx * scale)
        scaled_sy = int(sy * scale)
        scaled_sw = int(sw * scale)
        scaled_sh = int(sh * scale)
        
        canvas_sx1 = img_left + scaled_sx
        canvas_sy1 = img_top + scaled_sy
        canvas_sx2 = canvas_sx1 + scaled_sw
        canvas_sy2 = canvas_sy1 + scaled_sh
        
        canvas.create_rectangle(
            canvas_sx1, canvas_sy1, canvas_sx2, canvas_sy2,
            outline="#0080FF",  # 蓝色
            width=2,
            dash=(8, 4),  # 虚线
            tags="run_roi_box"
        )
        
        canvas.create_text(
            canvas_sx1, canvas_sy1 - 5,
            text="锚点搜索区域",
            anchor="sw",
            fill="#0080FF",
            font=("Arial", 8, "bold"),
            tags="run_roi_box"
        )
        
        # 2. 绘制基准锚点位置（小框，实线，灰色）
        ax, ay, aw, ah = anchor_rect
        scaled_ax = int(ax * scale)
        scaled_ay = int(ay * scale)
        scaled_aw = int(aw * scale)
        scaled_ah = int(ah * scale)
        
        canvas_ax1 = img_left + scaled_ax
        canvas_ay1 = img_top + scaled_ay
        canvas_ax2 = canvas_ax1 + scaled_aw
        canvas_ay2 = canvas_ay1 + scaled_ah
        
        canvas.create_rectangle(
            canvas_ax1, canvas_ay1, canvas_ax2, canvas_ay2,
            outline="#808080",  # 灰色
            width=1,
            tags="run_roi_box"
        )
        
        canvas.create_text(
            canvas_ax1, canvas_ay1 - 15,
            text="基准位置",
            anchor="sw",
            fill="#808080",
            font=("Arial", 7),
            tags="run_roi_box"
        )
        
        # 3. 根据锚点检测状态决定是否绘制当前位置
        if self.anchor_detection_enabled and (offset_x != 0 or offset_y != 0):
            # 启用锚点检测且有偏移：绘制当前检测到的锚点位置（小框，实线，红色）
            current_ax = ax + offset_x
            current_ay = ay + offset_y
            
            scaled_current_ax = int(current_ax * scale)
            scaled_current_ay = int(current_ay * scale)
            
            canvas_current_ax1 = img_left + scaled_current_ax
            canvas_current_ay1 = img_top + scaled_current_ay
            canvas_current_ax2 = canvas_current_ax1 + scaled_aw
            canvas_current_ay2 = canvas_current_ay1 + scaled_ah
            
            canvas.create_rectangle(
                canvas_current_ax1, canvas_current_ay1, canvas_current_ax2, canvas_current_ay2,
                outline="#FF0000",  # 红色
                width=3,
                tags="run_roi_box"
            )
            
            # 显示偏移信息
            if self.use_manual_offset:
                offset_text = f"当前锚点 [手动偏移:{offset_x},{offset_y}]"
            else:
                offset_text = f"当前锚点 [自动偏移:{offset_x},{offset_y}]"
            
            canvas.create_text(
                canvas_current_ax1, canvas_current_ay1 - 5,
                text=offset_text,
                anchor="sw",
                fill="#FF0000",
                font=("Arial", 8, "bold"),
                tags="run_roi_box"
            )
            
            # 绘制偏移箭头
            center_ax = canvas_ax1 + scaled_aw // 2
            center_ay = canvas_ay1 + scaled_ah // 2
            center_current_ax = canvas_current_ax1 + scaled_aw // 2
            center_current_ay = canvas_current_ay1 + scaled_ah // 2
            
            canvas.create_line(
                center_ax, center_ay, center_current_ax, center_current_ay,
                fill="#FF8000",  # 橙色
                width=2,
                arrow=tk.LAST,
                tags="run_roi_box"
            )
        elif not self.anchor_detection_enabled:
            # 禁用锚点检测：显示禁用状态
            canvas.create_text(
                canvas_ax1, canvas_ay1 - 25,
                text="锚点检测已禁用",
                anchor="sw",
                fill="#999999",
                font=("Arial", 8),
                tags="run_roi_box"
            )
    
    @safe_execute(default_return=None, error_message="开始手动校准失败")
    def _start_manual_calibration(self):
        """开始手动校准锚点"""
        if not self.main_window or not hasattr(self.main_window, 'saved_ocr_state'):
            messagebox.showwarning("提示", "没有找到锚点配置信息")
            return
        
        saved_state = self.main_window.saved_ocr_state
        if not saved_state.get('has_state', False):
            messagebox.showwarning("提示", "没有加载解决方案配置")
            return
        
        roi_layout = saved_state.get('roi_layout', {})
        anchor_data = roi_layout.get('FirstDigitAnchor')
        if not anchor_data:
            messagebox.showwarning("提示", "当前解决方案没有配置锚点")
            return
        
        # 进入手动校准模式
        self.manual_calibration_mode = True
        
        # 显示校准提示
        messagebox.showinfo(
            "手动校准锚点", 
            "请在画面中点击当前锚点的实际位置\n"
            "（通常是卡号的第一个数字）\n\n"
            "点击后系统会自动计算偏移量"
        )
        
        # 绑定画布点击事件
        if hasattr(self.main_window, 'preview_canvas'):
            canvas = self.main_window.preview_canvas
        else:
            canvas = self.main_window.canvas
        
        # 保存原有的绑定（如果有）
        self.original_canvas_bindings = {}
        for event in ['<Button-1>', '<Motion>']:
            try:
                original_binding = canvas.bind(event)
                if original_binding:
                    self.original_canvas_bindings[event] = original_binding
            except:
                pass
        
        # 绑定新的事件处理
        canvas.bind('<Button-1>', self._on_manual_calibration_click)
        canvas.bind('<Motion>', self._on_calibration_mouse_move)
        
        # 改变鼠标光标
        canvas.config(cursor="crosshair")
        
        # 更新偏移量显示
        self.offset_label.config(text="偏移: 校准中...", fg="#FF6600")
    
    @safe_execute(default_return=None, error_message="校准鼠标移动处理失败")
    def _on_calibration_mouse_move(self, event):
        """校准模式下的鼠标移动事件"""
        if not self.manual_calibration_mode:
            return
        
        # 可以在这里添加实时预览功能，显示如果在此处点击会产生的偏移量
        pass
    
    @safe_execute(default_return=None, error_message="手动校准点击处理失败")
    def _on_manual_calibration_click(self, event):
        """处理手动校准的点击事件"""
        if not self.manual_calibration_mode:
            return
        
        # 获取点击位置（画布坐标）
        click_x = event.x
        click_y = event.y
        
        # 转换为图像坐标
        image_coords = self._canvas_to_image_coords(click_x, click_y)
        if not image_coords:
            messagebox.showerror("错误", "无法确定点击位置，请重试")
            self._cancel_manual_calibration()
            return
        
        img_x, img_y = image_coords
        
        # 获取基准锚点位置
        saved_state = self.main_window.saved_ocr_state
        roi_layout = saved_state.get('roi_layout', {})
        anchor_data = roi_layout.get('FirstDigitAnchor')
        anchor_rect = anchor_data.get('roi', [])
        
        if len(anchor_rect) != 4:
            messagebox.showerror("错误", "锚点配置数据异常")
            self._cancel_manual_calibration()
            return
        
        base_x, base_y, base_w, base_h = anchor_rect
        
        # 计算手动偏移量（点击位置 - 基准位置）
        manual_offset_x = img_x - base_x
        manual_offset_y = img_y - base_y
        
        # 保存手动偏移量
        self.manual_offset = (manual_offset_x, manual_offset_y)
        self.use_manual_offset = True
        
        # 退出校准模式
        self._finish_manual_calibration()
        
        # 显示校准结果
        messagebox.showinfo(
            "校准完成", 
            f"手动校准完成！\n"
            f"偏移量: X={manual_offset_x}, Y={manual_offset_y}\n\n"
            f"点击位置: ({img_x}, {img_y})\n"
            f"基准位置: ({base_x}, {base_y})"
        )
    
    @safe_execute(default_return=None, error_message="画布坐标转换失败")
    def _canvas_to_image_coords(self, canvas_x, canvas_y):
        """
        将画布坐标转换为图像坐标
        
        参数:
            canvas_x, canvas_y: 画布坐标
        
        返回:
            tuple: (img_x, img_y) 图像坐标，失败返回None
        """
        try:
            # 获取当前显示的图像信息
            if hasattr(self.main_window, 'preview_canvas'):
                canvas = self.main_window.preview_canvas
            else:
                canvas = self.main_window.canvas
            
            # 获取画布尺寸
            canvas_width = canvas.winfo_width()
            canvas_height = canvas.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:
                return None
            
            # 获取当前图像
            current_image = self.camera_controller.get_image()
            if current_image is None:
                return None
            
            img_height, img_width = current_image.shape[:2]
            
            # 计算当前的缩放比例和居中偏移
            # 这里需要与视频显示逻辑保持一致
            scale_w = canvas_width / img_width
            scale_h = canvas_height / img_height
            scale = min(scale_w, scale_h) * 0.9  # 假设使用90%填充
            
            display_width = int(img_width * scale)
            display_height = int(img_height * scale)
            
            # 计算图像在画布上的位置（居中）
            img_left = (canvas_width - display_width) // 2
            img_top = (canvas_height - display_height) // 2
            
            # 检查点击是否在图像区域内
            if (canvas_x < img_left or canvas_x > img_left + display_width or
                canvas_y < img_top or canvas_y > img_top + display_height):
                return None
            
            # 转换为图像坐标
            relative_x = canvas_x - img_left
            relative_y = canvas_y - img_top
            
            img_x = int(relative_x / scale)
            img_y = int(relative_y / scale)
            
            # 边界检查
            img_x = max(0, min(img_width - 1, img_x))
            img_y = max(0, min(img_height - 1, img_y))
            
            return (img_x, img_y)
            
        except Exception as e:
            return None
    
    @safe_execute(default_return=None, error_message="完成手动校准失败")
    def _finish_manual_calibration(self):
        """完成手动校准"""
        self.manual_calibration_mode = False
        
        # 恢复画布绑定和光标
        if hasattr(self.main_window, 'preview_canvas'):
            canvas = self.main_window.preview_canvas
        else:
            canvas = self.main_window.canvas
        
        # 恢复原有绑定
        for event, binding in self.original_canvas_bindings.items():
            try:
                canvas.bind(event, binding)
            except:
                canvas.unbind(event)
        
        # 恢复光标
        canvas.config(cursor="")
        
        # 更新偏移量显示
        self._update_offset_display()
        
        # 强制刷新ROI框显示
        self._force_refresh_roi_display()
    
    @safe_execute(default_return=None, error_message="取消手动校准失败")
    def _cancel_manual_calibration(self):
        """取消手动校准"""
        self.manual_calibration_mode = False
        self.use_manual_offset = False
        self._finish_manual_calibration()
    
    @safe_execute(default_return=None, error_message="切换锚点检测失败")
    def _toggle_anchor_detection(self):
        """切换锚点检测开关"""
        self.anchor_detection_enabled = self.anchor_detection_var.get()
        
        if not self.anchor_detection_enabled:
            # 禁用锚点检测
            self.current_anchor_offset = (0, 0)
            self.use_manual_offset = False
            self.manual_offset = (0, 0)
            self.offset_label.config(text="偏移: 已禁用 [绝对坐标]", fg="#999999")
            
            # 禁用相关按钮
            self.calibrate_btn.config(state="disabled")
            self.reset_btn.config(state="disabled")
            self.resume_video_btn.config(state="disabled")
        else:
            # 启用锚点检测
            self.offset_label.config(text="偏移: (0, 0) [相对坐标]", fg="#666666")
            
            # 启用相关按钮
            self.calibrate_btn.config(state="normal")
            self.reset_btn.config(state="normal")
            self.resume_video_btn.config(state="normal")
        
        # 强制刷新ROI框显示
        self._force_refresh_roi_display()
    
    @safe_execute(default_return=None, error_message="更新偏移量显示失败")
    def _update_offset_display(self):
        """更新偏移量显示"""
        try:
            if not self.offset_label.winfo_exists():
                return
        except Exception:
            return
        if not self.anchor_detection_enabled:
            self.offset_label.config(text="偏移: 已禁用 [绝对坐标]", fg="#999999")
        elif self.use_manual_offset:
            offset_x, offset_y = self.manual_offset
            self.offset_label.config(text=f"偏移: ({offset_x}, {offset_y}) [手动]", fg="#FF6600")
        else:
            offset_x, offset_y = self.current_anchor_offset
            self.offset_label.config(text=f"偏移: ({offset_x}, {offset_y}) [自动]", fg="#666666")
    
    @safe_execute(default_return=(0, 0), error_message="检测锚点偏移失败")
    def _detect_anchor_offset(self, image):
        """
        检测当前图像中的锚点偏移量
        
        参数:
            image: 当前图像（numpy数组）
        
        返回:
            tuple: (offset_x, offset_y) 偏移量
        """
        if not self.main_window or not hasattr(self.main_window, 'saved_ocr_state'):
            return (0, 0)
        
        saved_state = self.main_window.saved_ocr_state
        if not saved_state.get('has_state', False):
            return (0, 0)
        
        roi_layout = saved_state.get('roi_layout', {})
        
        # 检查是否有锚点配置
        anchor_data = roi_layout.get('FirstDigitAnchor')
        if not anchor_data:
            return (0, 0)
        
        try:
            # 获取基准锚点位置和搜索区域
            anchor_rect = anchor_data.get('roi', [])  # 基准位置 [x, y, w, h]
            search_area = anchor_data.get('search_area', anchor_rect)  # 搜索区域 [x, y, w, h]
            
            if not anchor_rect or len(anchor_rect) != 4:
                return (0, 0)
            if not search_area or len(search_area) != 4:
                return (0, 0)
            
            train_x, train_y, train_w, train_h = anchor_rect
            sx, sy, sw, sh = search_area
            
            # 边界检查
            h_img, w_img = image.shape[:2]
            sx = max(0, sx)
            sy = max(0, sy)
            ex = min(w_img, sx + sw)
            ey = min(h_img, sy + sh)
            
            if sx >= ex or sy >= ey:
                return (0, 0)
            
            # 提取搜索区域
            roi = image[sy:ey, sx:ex]
            if roi.size == 0:
                return (0, 0)
            
            # 转换为灰度图
            if len(roi.shape) == 3:
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            else:
                gray = roi
            
            # 图像增强
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
            
            # 二值化
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            
            # 形态学处理
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 4))
            eroded = cv2.erode(binary, kernel, iterations=1)
            
            # 轮廓检测
            cnts, _ = cv2.findContours(eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # 筛选有效的墨迹
            valid_blobs = []
            for c in cnts:
                bx, by, bw, bh = cv2.boundingRect(c)
                if bh < 8:  # 高度太小
                    continue
                if bw * bh < 25:  # 面积太小
                    continue
                ratio = bw / float(bh)
                if ratio > 2.5:  # 宽高比太大（可能是噪声）
                    continue
                valid_blobs.append((bx, by, bw, bh))
            
            if not valid_blobs:
                return (0, 0)
            
            # 选择最左边的墨迹作为锚点
            valid_blobs.sort(key=lambda b: b[0])
            ink_x, ink_y, ink_w, ink_h = valid_blobs[0]
            
            # 计算当前锚点的绝对坐标
            current_abs_x = sx + ink_x
            current_abs_y = sy + ink_y
            
            # 计算偏移量
            offset_x = current_abs_x - train_x
            offset_y = current_abs_y - train_y
            
            return (offset_x, offset_y)
            
        except Exception as e:
            return (0, 0)
    @safe_execute(default_return=None, error_message="强制刷新ROI显示失败")
    def _force_refresh_roi_display(self):
        """强制刷新ROI框显示"""
        if not self.main_window:
            return
        
        # 防止重复调用，添加延迟执行
        if hasattr(self, '_refresh_pending') and self._refresh_pending:
            return
        
        self._refresh_pending = True
        
        def delayed_refresh():
            try:
                # 根据当前模式选择图像源
                if self.static_image_mode and self.static_image is not None:
                    # 静态图片模式：使用保存的静态图片
                    current_image = self.static_image
                else:
                    # 视频模式：从相机获取当前图像
                    current_image = self.camera_controller.get_image()
                
                if current_image is not None:
                    # 立即更新显示
                    self._display_image_on_canvas(current_image)
            except Exception as e:
                pass
            finally:
                self._refresh_pending = False
        
        # 延迟50ms执行，避免与其他显示调用冲突
        if self.main_window and hasattr(self.main_window, 'root'):
            self.main_window.root.after(50, delayed_refresh)
        else:
            self.parent.after(50, delayed_refresh)
    
    @ErrorHandler.handle_file_error
    def _open_image_file(self):
        """打开图片文件并显示在画布上"""
        from tkinter import filedialog
        import cv2
        import os
        import numpy as np
        
        # 打开文件对话框
        file_types = [
            ("图片文件", "*.jpg *.jpeg *.png *.bmp *.tiff *.tif"),
            ("JPEG文件", "*.jpg *.jpeg"),
            ("PNG文件", "*.png"),
            ("BMP文件", "*.bmp"),
            ("TIFF文件", "*.tiff *.tif"),
            ("所有文件", "*.*")
        ]
        
        file_path = filedialog.askopenfilename(
            title="选择图片文件",
            filetypes=file_types,
            initialdir=os.getcwd()
        )
        
        if not file_path:
            return
        
        print(f"🖼️ 用户选择图片文件: {file_path}")
        
        try:
            # 使用支持中文路径和BMP格式的方式读取图片
            image = self._cv2_imread_unicode(file_path)
            if image is None:
                error_msg = (
                    f"无法读取图片文件：\n{os.path.basename(file_path)}\n\n"
                    f"可能的原因：\n"
                    f"• 文件格式不支持或已损坏\n"
                    f"• 文件路径包含特殊字符\n"
                    f"• 文件正在被其他程序使用\n\n"
                    f"建议：\n"
                    f"• 尝试将文件复制到英文路径\n"
                    f"• 检查文件是否完整\n"
                    f"• 尝试其他图片格式（PNG、JPG）"
                )
                messagebox.showerror("读取图片失败", error_msg)
                return
            
            print(f"✅ 图片读取成功，尺寸: {image.shape}")
            
            # 进入静态图片模式
            self.static_image_mode = True
            self.static_image = image.copy()
            
            # 显示图片到画布上（包含ROI框）
            self._display_image_on_canvas(image)
            
            # 如果启用了锚点检测，重新计算偏移量
            if self.anchor_detection_enabled and not self.use_manual_offset:
                try:
                    print("🔍 重新计算锚点偏移量...")
                    self.current_anchor_offset = self._detect_anchor_offset(image)
                    self._update_offset_display()
                    # 重新绘制以应用新的偏移量
                    self._display_image_on_canvas(image)
                    print(f"✅ 锚点偏移量: {self.current_anchor_offset}")
                except Exception as e:
                    print(f"⚠️ 锚点检测失败: {e}")
            
            success_msg = (
                f"图片已成功加载：\n{os.path.basename(file_path)}\n\n"
                f"图片信息：\n"
                f"• 尺寸: {image.shape[1]} × {image.shape[0]}\n"
                f"• 通道数: {image.shape[2] if len(image.shape) > 2 else 1}\n\n"
                f"提示：图片将保持显示，不会被视频流覆盖\n"
                f"点击\"恢复视频\"按钮可返回视频流模式"
            )
            messagebox.showinfo("加载成功", success_msg)
            
        except Exception as e:
            error_msg = (
                f"加载图片时发生错误：\n{str(e)}\n\n"
                f"文件路径：\n{file_path}\n\n"
                f"请检查：\n"
                f"• 文件是否存在且可访问\n"
                f"• 文件格式是否正确\n"
                f"• 是否有足够的内存"
            )
            messagebox.showerror("加载失败", error_msg)
            print(f"❌ 加载图片失败: {e}")
            import traceback
            traceback.print_exc()
    
    @ErrorHandler.handle_file_error
    def _cv2_imread_unicode(self, file_path, flags=cv2.IMREAD_COLOR):
        """
        支持中文路径和BMP格式的OpenCV图片读取函数
        
        参数:
            file_path: 图片文件路径
            flags: OpenCV读取标志
        
        返回:
            numpy.ndarray: 图片数组，失败返回None
        """
        print(f"🔍 尝试读取图片: {file_path}")
        
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                print(f"❌ 文件不存在: {file_path}")
                return None
            
            # 获取文件大小
            file_size = os.path.getsize(file_path)
            print(f"📁 文件大小: {file_size} bytes")
            
            # 方法1: 尝试直接读取（适用于纯英文路径）
            print("🔄 方法1: 直接使用cv2.imread读取...")
            image = cv2.imread(file_path, flags)
            if image is not None:
                print("✅ 方法1成功")
                return image
            else:
                print("⚠️ 方法1失败，可能是中文路径问题")
            
            # 方法2: 使用numpy fromfile处理中文路径和特殊格式
            print("🔄 方法2: 使用numpy.fromfile读取...")
            try:
                # 读取文件的原始字节数据
                img_data = np.fromfile(file_path, dtype=np.uint8)
                print(f"📊 读取到 {len(img_data)} 字节数据")
                
                # 尝试解码图片数据
                image = cv2.imdecode(img_data, flags)
                if image is not None:
                    print("✅ 方法2成功")
                    return image
                else:
                    print("⚠️ 方法2失败，cv2.imdecode无法解码")
            except Exception as e:
                print(f"⚠️ 方法2异常: {e}")
            
            # 方法3: 使用标准文件读取 + cv2.imdecode
            print("🔄 方法3: 使用标准文件读取...")
            try:
                with open(file_path, 'rb') as f:
                    img_data = np.frombuffer(f.read(), dtype=np.uint8)
                
                print(f"📊 读取到 {len(img_data)} 字节数据")
                
                # 解码图片数据
                image = cv2.imdecode(img_data, flags)
                if image is not None:
                    print("✅ 方法3成功")
                    return image
                else:
                    print("⚠️ 方法3失败，cv2.imdecode无法解码")
            except Exception as e:
                print(f"⚠️ 方法3异常: {e}")
            
            # 方法4: 尝试使用PIL读取然后转换（最兼容的方法）
            print("🔄 方法4: 使用PIL读取...")
            try:
                from PIL import Image
                pil_image = Image.open(file_path)
                print(f"📷 PIL读取成功，模式: {pil_image.mode}, 尺寸: {pil_image.size}")
                
                # 转换为RGB格式（确保兼容性）
                if pil_image.mode in ['RGBA', 'LA']:
                    # 有透明通道，转换为RGB并使用白色背景
                    rgb_image = Image.new('RGB', pil_image.size, (255, 255, 255))
                    if pil_image.mode == 'RGBA':
                        rgb_image.paste(pil_image, mask=pil_image.split()[-1])
                    else:
                        rgb_image.paste(pil_image)
                    pil_image = rgb_image
                elif pil_image.mode != 'RGB':
                    pil_image = pil_image.convert('RGB')
                
                # 转换为numpy数组
                image_array = np.array(pil_image)
                print(f"🔢 numpy数组形状: {image_array.shape}")
                
                # PIL使用RGB，OpenCV使用BGR，需要转换
                if len(image_array.shape) == 3 and image_array.shape[2] == 3:
                    image = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)
                    print("🔄 RGB转BGR完成")
                else:
                    image = image_array
                
                print("✅ 方法4成功")
                return image
                
            except ImportError:
                print("❌ PIL库未安装，无法使用PIL读取图片")
            except Exception as e:
                print(f"❌ PIL读取图片失败: {e}")
            
            print("❌ 所有方法都失败了")
            return None
            
        except Exception as e:
            print(f"❌ 读取图片时发生严重错误: {file_path} - {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @safe_execute(default_return=None, error_message="重置锚点检测失败")
    def _reset_anchor_detection(self):
        """重置锚点检测"""
        self.current_anchor_offset = (0, 0)
        self.manual_offset = (0, 0)
        self.use_manual_offset = False
        self._update_offset_display()
        
        # 强制重新检测
        if self.anchor_detection_enabled:
            try:
                # 根据当前模式选择图像源
                if self.static_image_mode and self.static_image is not None:
                    # 静态图片模式：使用保存的静态图片
                    current_image = self.static_image
                else:
                    # 视频模式：从相机获取当前图像
                    current_image = self.camera_controller.get_image()
                
                if current_image is not None:
                    self.current_anchor_offset = self._detect_anchor_offset(current_image)
                    self._update_offset_display()
            except Exception as e:
                pass
        
        # 强制刷新ROI框显示
        self._force_refresh_roi_display()
    @safe_execute(default_return=None, error_message="恢复视频流失败")
    def _resume_video_stream(self):
        """恢复视频流显示"""
        # 退出静态图片模式
        self.static_image_mode = False
        self.static_image = None
        
        # 获取当前触发模式
        trigger_mode = self.camera_controller.get_trigger_mode()
        
        if trigger_mode == "internal":
            # 内部时钟模式：如果视频循环没有运行，启动它
            if not self.video_loop_running:
                self._start_video_loop()
        else:
            # 硬件/软件触发模式：显示当前静止帧
            try:
                current_image = self.camera_controller.get_image()
                if current_image is not None:
                    self._display_image_on_canvas(current_image)
            except Exception as e:
                pass
        
        messagebox.showinfo("提示", "已恢复视频流显示")