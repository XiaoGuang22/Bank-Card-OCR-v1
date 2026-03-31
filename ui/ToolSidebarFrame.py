"""
工具按钮侧边栏界面模块

该模块实现Card-OCR系统的工具按钮侧边栏，提供设置模板、选择工具、说明、区域等功能。
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
import cv2
import numpy as np
import os
import datetime
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 导入异常处理工具
try:
    from utils.exception_utils import ErrorHandler, safe_call, safe_execute
except ImportError:
    # 如果异常处理工具不可用，使用简单的装饰器
    def ErrorHandler():
        class _ErrorHandler:
            @staticmethod
            def handle_ui_error(func):
                return func
            @staticmethod
            def handle_file_error(func):
                return func
        return _ErrorHandler()
    ErrorHandler = ErrorHandler()
    safe_call = lambda func, *args, **kwargs: func(*args, **kwargs)
    safe_execute = lambda **kwargs: lambda func: func


class ToolSidebarFrame:
    """
    工具按钮侧边栏类
    
    提供设置模板、选择工具、说明、区域等功能按钮。
    """
    
    def __init__(self, parent, camera_controller, on_back_callback, main_window=None):
        """
        初始化工具侧边栏
        
        参数:
            parent: 父窗口（侧边栏）
            camera_controller: 相机控制器实例
            on_back_callback: 返回主菜单的回调函数
            main_window: 主窗口实例（用于调用主窗口的方法）
        """
        self.parent = parent
        self.camera_controller = camera_controller
        self.on_back_callback = on_back_callback
        self.main_window = main_window  # 保存主窗口引用
        
        # 创建侧边栏界面
        self._create_sidebar_ui()
    
    
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
            text="设置工具",
            font=("Microsoft YaHei UI", 11, "bold"),
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
        self._create_scrollable_container()
        
        # 创建各个功能区域
        self._create_template_section()
        self._create_tool_section()
        self._create_description_section()
        self._create_region_section()
    
    @ErrorHandler.handle_ui_error
    def _create_scrollable_container(self):
        """创建可滚动容器"""
        canvas = tk.Canvas(self.parent, bg="white", highlightthickness=0)
        scrollbar = tk.Scrollbar(self.parent, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg="white")
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def _create_template_section(self):
        """创建设置模板区域"""
        # 第一步：创建固定大小的外框（宽度380，高度700）
        self.template_frame = tk.LabelFrame(
            self.scrollable_frame,
            text="设置模板",
            font=("Microsoft YaHei UI", 11, "bold"),
            bg="white",
            relief=tk.GROOVE,
            bd=1,
            width=365,
            height=80
        )
        self.template_frame.pack(padx=(5, 5), pady=3)
        self.template_frame.pack_propagate(False)  # 禁止子组件改变框架大小
        
        # 第二步：在外框里面放置按钮
        button_container = tk.Frame(self.template_frame, bg="white")
        button_container.pack(anchor=tk.W, padx=10, pady=5)  # anchor=tk.W 向左靠齐
        
        # 按钮配置
        buttons = [
            ("拍照", self._on_take_photo),
            ("保存图像", self._on_save_image),
            ("加载图像", self._on_load_image)
        ]
        
        # 创建按钮（横向排列）
        for text, callback in buttons:
            # 创建一个固定大小的Frame来容纳按钮
            btn_frame = tk.Frame(button_container, width=58, height=58, bg="white")
            btn_frame.pack(side=tk.LEFT, padx=2)
            btn_frame.pack_propagate(False)  # 禁止子组件改变Frame大小
            
            btn = tk.Button(
                btn_frame,
                text=text,
                font=("Microsoft YaHei UI", 8),
                bg="#F0F0F0",
                relief=tk.RAISED,
                bd=1,
                cursor="hand2",
                command=callback
            )
            btn.pack(fill=tk.BOTH, expand=True)  # 填充整个Frame
    
    def _create_tool_section(self):
        """创建选择工具区域"""
        # 第一步：创建固定大小的外框（宽度380，高度700）
        self.tool_frame = tk.LabelFrame(
            self.scrollable_frame,
            text="选择工具",
            font=("Microsoft YaHei UI", 11, "bold"),
            bg="white",
            relief=tk.GROOVE,
            bd=1,
            width=365,
            heigh=400
        )
        self.tool_frame.pack(padx=(5, 5), pady=3)
        self.tool_frame.pack_propagate(False)  # 禁止子组件改变框架大小
        
        # 第二步：在外框里面放置 OCR 按钮
        button_container = tk.Frame(self.tool_frame, bg="white")
        button_container.pack(anchor=tk.W, padx=10, pady=5)  # anchor=tk.W 向左靠齐
        
        # OCR 按钮
        # 创建一个固定大小的Frame来容纳按钮
        btn_frame = tk.Frame(button_container, width=58, height=58, bg="white")
        btn_frame.pack()
        btn_frame.pack_propagate(False)  # 禁止子组件改变Frame大小
        
        ocr_btn = tk.Button(
            btn_frame,
            text="OCR",
            font=("Microsoft YaHei UI", 9, "bold"),
            bg="#4CAF50",
            fg="white",
            relief=tk.RAISED,
            bd=1,
            cursor="hand2",
            command=self._on_ocr_tool
        )
        ocr_btn.pack(fill=tk.BOTH, expand=True)  # 填充整个Frame
    
    def _create_description_section(self):
        """创建说明区域"""
        # 第一步：创建固定大小的外框（宽度380，高度700）
        self.desc_frame = tk.LabelFrame(
            self.scrollable_frame,
            text="说明",
            font=("Microsoft YaHei UI", 11, "bold"),
            bg="white",
            relief=tk.GROOVE,
            bd=1,
            width=365,
            height=150
        )
        self.desc_frame.pack(padx=(5, 5), pady=3)
        self.desc_frame.pack_propagate(False)  # 禁止子组件改变框架大小
        
        # 第二步：在外框里面放置说明文本
        desc_text = tk.Text(
            self.desc_frame,
            font=("Microsoft YaHei UI", 8),
            bg="white",
            relief=tk.FLAT,
            height=3,
            wrap=tk.WORD
        )
        desc_text.pack(fill=tk.BOTH, padx=5, pady=5)
        desc_text.insert("1.0", "点击鼠标开始新工具...\n如果文本转换使用折线")
        desc_text.config(state=tk.DISABLED)
    
    def _create_region_section(self):
        """创建区域区域"""
        # 第一步：创建固定大小的外框（宽度380，高度700）
        self.region_frame = tk.LabelFrame(
            self.scrollable_frame,
            text="区域",
            font=("Microsoft YaHei UI", 11, "bold"),
            bg="white",
            relief=tk.GROOVE,
            bd=1,
            width=365,
            height=80
        )
        self.region_frame.pack(padx=(5, 5), pady=3)
        self.region_frame.pack_propagate(False)  # 禁止子组件改变框架大小
        
        # 第二步：在外框里面放置区域工具按钮
        button_container = tk.Frame(self.region_frame, bg="white")
        button_container.pack(anchor=tk.W, padx=10, pady=5)  # anchor=tk.W 向左靠齐
        
        # 区域工具按钮（横向排列）
        region_tools = [
            ("矩形", self._on_rectangle_tool),
            ("圆形", self._on_circle_tool),
        ]
        
        for text, callback in region_tools:
            # 创建一个固定大小的Frame来容纳按钮
            btn_frame = tk.Frame(button_container, width=58, height=58, bg="white")
            btn_frame.pack(side=tk.LEFT, padx=2)
            btn_frame.pack_propagate(False)  # 禁止子组件改变Frame大小
            
            btn = tk.Button(
                btn_frame,
                text=text,
                font=("Microsoft YaHei UI", 8),
                bg="#F0F0F0",
                relief=tk.RAISED,
                bd=1,
                cursor="hand2",
                command=callback
            )
            btn.pack(fill=tk.BOTH, expand=True)  # 填充整个Frame
    
    # ========== 回调函数 ==========
    
    def _on_back_button_click(self):
        """返回按钮点击事件"""
        if self.on_back_callback:
            self.on_back_callback()
    
    @ErrorHandler.handle_ui_error
    def _on_take_photo(self):
        """拍照按钮回调 - 从相机捕获图像并显示在主窗口画布"""
        if not self.main_window:
            raise ValueError("主窗口引用不可用")
        
        if not self.camera_controller:
            raise ValueError("相机控制器不可用")
        
        # 1. 停止视频循环（关键修复）
        if hasattr(self.main_window, '_stop_video_loop'):
            safe_call(self.main_window._stop_video_loop)
            pass  # print removed
        
        # 2. 根据触发模式获取图像
        captured_image = self._capture_image_by_trigger_mode()
        
        if captured_image is None:
            raise RuntimeError("无法获取相机图像")
        
        # 3. 验证图像有效性
        if captured_image.size == 0:
            raise RuntimeError("相机返回空图像")
        
        # 4. 检查是否是"NO SIGNAL"画面
        self._check_signal_quality(captured_image)
        
        # 5. 更新 OCR 状态中的图片（保留字段布局）
        if hasattr(self.main_window, 'update_ocr_state_image'):
            safe_call(self.main_window.update_ocr_state_image, captured_image, image_path=None)
        
        # 6. 在主窗口画布显示图像
        self._display_image_on_canvas(captured_image)
        
        # 7. 根据触发模式显示不同的成功消息
        self._show_capture_success_message()
        
        pass  # print removed
    
    def _check_signal_quality(self, image):
        """检查信号质量"""
        mean_val = np.mean(image)
        std_val = np.std(image)
        
        if mean_val < 30 and std_val < 10:
            messagebox.showwarning(
                "警告",
                "相机可能未连接或无信号！\n请检查相机连接状态。"
            )
    
    def _show_capture_success_message(self):
        """显示拍照成功消息"""
        trigger_mode = safe_call(
            self.camera_controller.get_trigger_mode, 
            default="internal"
        ) if self.camera_controller else "internal"
        
        if trigger_mode == "software":
            messagebox.showinfo("拍照成功", "软件触发拍照完成！\n新图像已捕获并显示在画布上")
        else:
            messagebox.showinfo("拍照成功", "图像已捕获并显示在画布上")
    
    @safe_execute(default_return=None, log_error=True, error_message="根据触发模式获取图像失败")
    def _capture_image_by_trigger_mode(self):
        """
        根据触发模式获取图像
        
        返回:
            numpy.ndarray: 捕获的图像，失败返回None
        """
        # 获取当前触发模式
        trigger_mode = self.camera_controller.get_trigger_mode() if self.camera_controller else "internal"
        print(f"🔍 当前触发模式: {trigger_mode}")
        
        if trigger_mode == "software":
            return self._handle_software_trigger()
        elif trigger_mode == "hardware":
            return self._handle_hardware_trigger()
        else:
            return self._handle_internal_trigger()
    
    def _handle_software_trigger(self):
        """处理软件触发模式"""
        print("📸 软件触发模式：执行软件触发...")
        
        # 执行软件触发
        trigger_success = safe_call(self.camera_controller.execute_software_trigger, default=False)
        if not trigger_success:
            print("❌ 软件触发执行失败")
            messagebox.showwarning("警告", "软件触发执行失败，将返回缓存图像")
            return safe_call(self.camera_controller.get_image)
        
        print("✅ 软件触发执行成功")
        
        # 等待新帧
        self._wait_for_new_frame()
        
        # 获取触发后的新图像
        captured_image = safe_call(self.camera_controller.get_image)
        print(f"📷 获取触发后图像: {captured_image.shape if captured_image is not None else 'None'}")
        
        return captured_image
    
    def _wait_for_new_frame(self):
        """等待新帧"""
        # 使用事件等待新帧（更可靠的方式）
        if (hasattr(self.camera_controller, 'frame_updated_event') and 
            hasattr(self.camera_controller, 'waiting_for_trigger')):
            print("⏳ 等待新帧事件...")
            
            # 设置等待标志
            self.camera_controller.waiting_for_trigger = True
            
            # 等待新帧事件，最多等待500ms
            import threading
            event_received = safe_call(
                self.camera_controller.frame_updated_event.wait, 
                timeout=0.5, 
                default=False
            )
            
            # 清除等待标志
            self.camera_controller.waiting_for_trigger = False
            safe_call(self.camera_controller.frame_updated_event.clear)
            
            if event_received:
                print("✅ 收到新帧事件")
            else:
                print("⚠️ 等待新帧超时，继续获取图像")
        else:
            # 备用方案：简单延时等待
            print("⏳ 使用延时等待新帧...")
            import time
            time.sleep(0.1)  # 等待100ms
    
    def _handle_hardware_trigger(self):
        """处理硬件触发模式"""
        print("📸 硬件触发模式：获取当前帧")
        return safe_call(self.camera_controller.get_image)
    
    def _handle_internal_trigger(self):
        """处理内部时钟模式"""
        print("📸 内部时钟模式：获取当前帧")
        return safe_call(self.camera_controller.get_image)
    
    @ErrorHandler.handle_file_error
    def _on_save_image(self):
        """保存图像按钮回调 - 保存画布上的图像（优先保存已拍照的图像）"""
        if not self.main_window:
            messagebox.showwarning("警告", "主窗口引用不可用")
            return
        
        # 1. 优先保存画布上已拍照的图像
        image = None
        
        # 检查是否有已拍照的图像
        if hasattr(self.main_window, 'captured_image') and self.main_window.captured_image is not None:
            image = self.main_window.captured_image
        # 如果没有拍照图像，从相机获取实时图像
        elif self.camera_controller:
            image = self.camera_controller.get_image()
        else:
            messagebox.showwarning("警告", "没有可保存的图像")
            return
        
        if image is None:
            messagebox.showerror("错误", "无法获取图像")
            return
        
        # 2. 弹出文件保存对话框
        # 生成默认文件名（带时间戳）
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"captured_{timestamp}.bmp"
        
        file_path = filedialog.asksaveasfilename(
            title="保存图像",
            defaultextension=".bmp",
            initialfile=default_filename,
            filetypes=[
                ("BMP文件", "*.bmp"),
                ("JPEG文件", "*.jpg"),
                ("PNG文件", "*.png"),
                ("所有文件", "*.*")
            ]
        )
        
        # 用户取消保存
        if not file_path:
            return
        
        # 3. 确保目标目录存在
        target_dir = os.path.dirname(file_path)
        if target_dir and not os.path.exists(target_dir):
            os.makedirs(target_dir)
        
        # 4. 保存图像到文件
        success = cv2.imwrite(file_path, image)
        
        if success:
            messagebox.showinfo("成功", f"图像已保存到:\n{file_path}")
            logger.info(f"图像保存成功: {file_path}")
        else:
            messagebox.showerror("错误", "保存图像失败")
            logger.error(f"图像保存失败: {file_path}")
    
    @ErrorHandler.handle_file_error
    def _on_load_image(self):
        """加载图像按钮回调 - 从文件加载图像并显示在主窗口画布"""
        if not self.main_window:
            messagebox.showwarning("警告", "主窗口引用不可用")
            return
        
        # 1. 弹出文件选择对话框
        file_path = filedialog.askopenfilename(
            title="选择图像文件",
            filetypes=[
                ("图像文件", "*.bmp *.jpg *.jpeg *.png"),
                ("BMP文件", "*.bmp"),
                ("JPEG文件", "*.jpg *.jpeg"),
                ("PNG文件", "*.png"),
                ("所有文件", "*.*")
            ]
        )
        
        # 用户取消选择
        if not file_path:
            return
        
        # 验证文件存在性
        if not os.path.exists(file_path):
            messagebox.showerror("错误", "选择的文件不存在")
            return
        
        # 2. 停止视频循环（关键修复）
        if hasattr(self.main_window, '_stop_video_loop'):
            self.main_window._stop_video_loop()
            pass  # print removed
            
        # 3. 读取图像文件（支持中文路径）
        loaded_image = self._cv2_imread_chinese(file_path)
        
        if loaded_image is None:
            messagebox.showerror("错误", f"无法读取图像文件:\n{file_path}")
            return
        
        # ★★★ 关键改进：统一到相机硬件尺寸 ★★★
        loaded_image = self._resize_to_camera_size(loaded_image)
        
        # 4. 更新 OCR 状态中的图片（保留字段布局）
        if hasattr(self.main_window, 'update_ocr_state_image'):
            self.main_window.update_ocr_state_image(loaded_image, image_path=file_path)
        
        # 5. 在主窗口画布显示图像
        self._display_image_on_canvas(loaded_image)
        
        messagebox.showinfo("成功", f"图像已加载:\n{os.path.basename(file_path)}")
        logger.info(f"图像加载成功: {file_path}")
    
    @safe_execute(default_return=None, log_error=True, error_message="读取图像文件失败")
    def _cv2_imread_chinese(self, file_path):
        """
        读取图像文件（支持中文路径）
        
        参数:
            file_path: 图像文件路径
        
        返回:
            numpy数组（灰度图像）或 None
        """
        # 使用numpy读取文件，然后用cv2解码（支持中文路径）
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # 将字节数据转换为numpy数组
        file_array = np.frombuffer(file_data, dtype=np.uint8)
        
        # 使用cv2解码图像
        image = cv2.imdecode(file_array, cv2.IMREAD_GRAYSCALE)
        
        if image is None:
            logger.warning(f"图像解码失败: {file_path}")
        
        return image
    
    def _resize_to_camera_size(self, image):
        """
        将图像resize到相机硬件尺寸（等比例缩放+填充黑边）
        
        参数:
            image: 输入图像（numpy数组）
        
        返回:
            resize后的图像（与相机尺寸一致，保持宽高比）
        """
        if image is None:
            return None
        
        # 获取相机硬件尺寸
        if not self.camera_controller:
            return image
        
        camera_width = self.camera_controller.width
        camera_height = self.camera_controller.height
        
        # 如果相机尺寸无效，使用默认值 1600x1200
        if camera_width <= 0 or camera_height <= 0:
            camera_width = 1600
            camera_height = 1200
        
        # 获取当前图像尺寸
        current_h, current_w = image.shape[:2]
        
        # 如果尺寸已经一致，直接返回
        if current_w == camera_width and current_h == camera_height:
            return image
        
        # 需要resize
        # ★★★ 等比例缩放 + 填充黑边（避免变形）★★★
        # 计算缩放比例（取较小值，确保图像完全放入目标尺寸）
        scale = min(camera_width / current_w, camera_height / current_h)
        
        # 计算缩放后的尺寸
        new_w = int(current_w * scale)
        new_h = int(current_h * scale)
        
        # 执行等比例缩放
        resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        
        # 创建目标尺寸的黑色画布
        canvas = np.zeros((camera_height, camera_width), dtype=np.uint8)
        
        # 计算居中位置
        x_offset = (camera_width - new_w) // 2
        y_offset = (camera_height - new_h) // 2
        
        # 将缩放后的图像放到画布中心
        canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
        
        return canvas
    
    @ErrorHandler.handle_ui_error
    def _display_image_on_canvas(self, image):
        """
        在主窗口画布上显示图像
        
        参数:
            image: numpy数组，灰度图像
        """
        if not self.main_window or not hasattr(self.main_window, 'canvas'):
            logger.warning("主窗口或画布不可用")
            return
        
        canvas = self.main_window.canvas
        
        # 0. ★★★ 关键修复：工具页面使用独立的图像存储 ★★★
        # 不要更新主界面的captured_image，避免影响主界面状态
        # 工具页面的图像只在工具页面和OCR页面使用
        if not hasattr(self.main_window, 'tool_captured_image'):
            self.main_window.tool_captured_image = None
        self.main_window.tool_captured_image = image.copy()
        pass  # print removed
        
        # 0.1 初始化缩放比例（如果不存在）
        if not hasattr(self.main_window, 'tool_image_zoom_scale'):
            self.main_window.tool_image_zoom_scale = None
        
        # 1. 清空画布
        canvas.delete("all")
        
        # 2. 获取画布尺寸
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()
        
        if canvas_width <= 1 or canvas_height <= 1:
            # 画布尚未渲染，使用默认尺寸
            canvas_width = 800
            canvas_height = 600
        
        # 3. 计算缩放比例
        img_height, img_width = image.shape[:2]
        
        # ★★★ 关键修复：每次显示新图像时，重置缩放比例为默认的90%高度 ★★★
        # 这样可以避免使用之前的缩放比例导致显示异常
        scale = (canvas_height * 0.9) / img_height
        self.main_window.tool_image_zoom_scale = scale
        
        # 更新缩放比例显示
        if hasattr(self.main_window, 'zoom_label'):
            zoom_percent = int(scale * 100)
            self.main_window.zoom_label.config(text=f"{zoom_percent}%")
        
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        
        # 4. 调整图像大小
        resized_image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
        
        # 5. 转换为RGB格式（如果是灰度图）
        if len(resized_image.shape) == 2:
            resized_image = cv2.cvtColor(resized_image, cv2.COLOR_GRAY2RGB)
        else:
            resized_image = cv2.cvtColor(resized_image, cv2.COLOR_BGR2RGB)
        
        # 6. 转换为PIL Image
        pil_image = Image.fromarray(resized_image)
        
        # 7. 转换为Tkinter PhotoImage
        tk_image = ImageTk.PhotoImage(pil_image)
        
        # 8. 保存引用（防止被垃圾回收）
        self.main_window._captured_tk_image = tk_image
        
        # 9. 在画布上居中显示图像
        cx = canvas_width // 2
        cy = canvas_height // 2
        
        canvas.create_image(cx, cy, image=tk_image, tags="captured_image")
        
        # 10. 如果有保存的字段布局，绘制字段框
        if hasattr(self.main_window, 'saved_ocr_state') and self.main_window.saved_ocr_state['has_state']:
            roi_layout = self.main_window.saved_ocr_state.get('roi_layout', {})
            temp_layout = self.main_window.saved_ocr_state.get('temp_layout', {})
            
            if roi_layout or temp_layout:
                self._draw_roi_boxes(canvas, roi_layout, temp_layout, scale, cx, cy, img_width, img_height)
    
    def _draw_roi_boxes(self, canvas, roi_layout, temp_layout, zoom_scale, cx, cy, img_width, img_height):
        """在画布上绘制ROI框"""
        # 计算图片左上角
        img_w = int(img_width * zoom_scale)
        img_h = int(img_height * zoom_scale)
        img_left = cx - img_w // 2
        img_top = cy - img_h // 2
        
        # 颜色映射
        color_map = {
            "CardNumber": "#ff0000",
            "Name": "#0000ff",
            "Date": "#008000",
            "FirstDigitAnchor": "#ff00ff"
        }
        
        # 绘制已保存的ROI框
        for field, data in roi_layout.items():
            if isinstance(data, dict):
                coords = data.get("search_area", data.get("roi"))
            else:
                coords = data
            
            if not coords or len(coords) != 4:
                continue
            
            x, y, w_roi, h_roi = coords
            color = color_map.get(field, "#000000")
            
            # 转换为画布坐标
            sx = img_left + x * zoom_scale
            sy = img_top + y * zoom_scale
            sw = w_roi * zoom_scale
            sh = h_roi * zoom_scale
            
            # 绘制矩形框
            canvas.create_rectangle(
                sx, sy, sx + sw, sy + sh,
                outline=color,
                width=2,
                tags="tool_canvas_roi"
            )
            
            # 绘制标签
            canvas.create_text(
                sx, sy - 15,
                text=f"[已保存] {field}",
                fill=color,
                anchor="sw",
                font=("Arial", 9, "bold"),
                tags="tool_canvas_roi"
            )
        
        # 绘制临时ROI框
        for field, data in temp_layout.items():
            if isinstance(data, dict):
                coords = data.get("search_area", data.get("roi"))
            else:
                coords = data
            
            if not coords or len(coords) != 4:
                continue
            
            x, y, w_roi, h_roi = coords
            color = color_map.get(field, "#000000")
            
            # 转换为画布坐标
            sx = img_left + x * zoom_scale
            sy = img_top + y * zoom_scale
            sw = w_roi * zoom_scale
            sh = h_roi * zoom_scale
            
            # 绘制矩形框（虚线）
            canvas.create_rectangle(
                sx, sy, sx + sw, sy + sh,
                outline=color,
                width=3,
                dash=(4, 4),
                tags="tool_canvas_roi"
            )
            
            # 绘制标签
            canvas.create_text(
                sx, sy - 15,
                text=f"[临时] {field}",
                fill=color,
                anchor="sw",
                font=("Arial", 9, "bold"),
                tags="tool_canvas_roi"
            )
    
    def _on_ocr_tool(self):
        """OCR工具按钮回调 - 打开解决方案制作面板"""
        if self.main_window and hasattr(self.main_window, 'show_solution_maker'):
            # 调用主窗口的 show_solution_maker 方法
            self.main_window.show_solution_maker()
        else:
            messagebox.showwarning("提示", "无法打开解决方案制作面板")
    
    def _on_rectangle_tool(self):
        """矩形工具按钮回调"""
        messagebox.showinfo("提示", "矩形工具功能")
    
    def _on_circle_tool(self):
        """圆形工具按钮回调"""
        messagebox.showinfo("提示", "圆形工具功能")

    def _on_tcp_settings(self):
        """通信设置按钮回调（需求 12.2）。"""
        if self.main_window and hasattr(self.main_window, 'show_tcp_settings'):
            self.main_window.show_tcp_settings()
        else:
            messagebox.showwarning("提示", "无法打开通信设置面板")

    def _on_script_editor(self):
        """脚本编辑按钮回调（需求 12.4）。"""
        if self.main_window and hasattr(self.main_window, 'show_script_editor'):
            self.main_window.show_script_editor()
        else:
            messagebox.showwarning("提示", "无法打开脚本编辑面板")
