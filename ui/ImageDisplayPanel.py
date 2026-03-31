"""
图像显示面板

显示实时图像和识别结果
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import numpy as np

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


class ImageDisplayPanel(tk.Frame):
    """图像显示面板类
    
    使用Canvas显示实时图像，支持缩放和滚动功能，
    并在图像上绘制识别结果覆盖层。
    
    验证需求: 7.1, 7.2, 7.3
    """
    
    @ErrorHandler.handle_ui_error
    def __init__(self, parent):
        """初始化图像显示面板
        
        参数:
            parent: 父窗口
        """
        super().__init__(parent, bg="black")
        
        # 图像数据
        self._current_image = None  # PIL Image对象
        self._photo_image = None    # PhotoImage对象（用于Canvas显示）
        self._zoom_scale = 1.0      # 缩放比例
        
        # 识别结果数据
        self._result = None
        
        # Canvas图像ID
        self._canvas_image_id = None
        
        self._init_ui()
    
    @ErrorHandler.handle_ui_error
    def _init_ui(self):
        """初始化UI布局"""
        # 工具栏
        self._create_toolbar()
        
        # Canvas容器（带滚动条）
        self._create_canvas_container()
    
    @ErrorHandler.handle_ui_error
    def _create_toolbar(self):
        """创建工具栏"""
        toolbar = tk.Frame(self, bg="#2c2c2c", height=40)
        toolbar.pack(fill=tk.X, side=tk.TOP)
        
        # 缩放按钮
        zoom_frame = tk.Frame(toolbar, bg="#2c2c2c")
        zoom_frame.pack(side=tk.LEFT, padx=10)
        
        tk.Label(
            zoom_frame,
            text="缩放:",
            font=("Microsoft YaHei UI", 9),
            bg="#2c2c2c",
            fg="white"
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self._zoom_in_btn = tk.Button(
            zoom_frame,
            text="放大 +",
            font=("Microsoft YaHei UI", 8),
            bg="#444",
            fg="white",
            relief=tk.FLAT,
            padx=8,
            pady=4,
            cursor="hand2",
            command=self._zoom_in
        )
        self._zoom_in_btn.pack(side=tk.LEFT, padx=2)
        
        self._zoom_out_btn = tk.Button(
            zoom_frame,
            text="缩小 -",
            font=("Microsoft YaHei UI", 8),
            bg="#444",
            fg="white",
            relief=tk.FLAT,
            padx=8,
            pady=4,
            cursor="hand2",
            command=self._zoom_out
        )
        self._zoom_out_btn.pack(side=tk.LEFT, padx=2)
        
        self._fit_btn = tk.Button(
            zoom_frame,
            text="适应窗口",
            font=("Microsoft YaHei UI", 8),
            bg="#444",
            fg="white",
            relief=tk.FLAT,
            padx=8,
            pady=4,
            cursor="hand2",
            command=self._fit_to_window
        )
        self._fit_btn.pack(side=tk.LEFT, padx=2)
        
        # 缩放比例显示
        self._zoom_label = tk.Label(
            toolbar,
            text="100%",
            font=("Microsoft YaHei UI", 9),
            bg="#2c2c2c",
            fg="white"
        )
        self._zoom_label.pack(side=tk.LEFT, padx=10)
    
    @ErrorHandler.handle_ui_error
    def _create_canvas_container(self):
        """创建Canvas容器"""
        canvas_container = tk.Frame(self, bg="black")
        canvas_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建Canvas
        self._canvas = tk.Canvas(
            canvas_container,
            bg="black",
            highlightthickness=0
        )
        
        # 创建滚动条
        h_scrollbar = ttk.Scrollbar(
            canvas_container,
            orient=tk.HORIZONTAL,
            command=self._canvas.xview
        )
        v_scrollbar = ttk.Scrollbar(
            canvas_container,
            orient=tk.VERTICAL,
            command=self._canvas.yview
        )
        
        self._canvas.configure(
            xscrollcommand=h_scrollbar.set,
            yscrollcommand=v_scrollbar.set
        )
        
        # 布局
        self._canvas.grid(row=0, column=0, sticky="nsew")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        
        canvas_container.grid_rowconfigure(0, weight=1)
        canvas_container.grid_columnconfigure(0, weight=1)
    
    @safe_execute(default_return=None, error_message="显示图像失败")
    def display_image(self, image):
        """显示图像
        
        参数:
            image: numpy数组或PIL Image对象
        """
        # 转换numpy数组为PIL Image
        if isinstance(image, np.ndarray):
            # 假设图像是BGR格式（OpenCV默认格式）
            if len(image.shape) == 3 and image.shape[2] == 3:
                # BGR转RGB
                image = Image.fromarray(image[:, :, ::-1])
            else:
                image = Image.fromarray(image)
        
        self._current_image = image
        self._update_canvas()
    
    @safe_execute(default_return=None, error_message="更新Canvas失败")
    def _update_canvas(self):
        """更新Canvas显示"""
        if self._current_image is None:
            return
        
        # 应用缩放
        scaled_width = int(self._current_image.width * self._zoom_scale)
        scaled_height = int(self._current_image.height * self._zoom_scale)
        
        scaled_image = self._current_image.resize(
            (scaled_width, scaled_height),
            Image.Resampling.LANCZOS
        )
        
        # 如果有识别结果，绘制覆盖层
        if self._result is not None:
            scaled_image = self._draw_overlay(scaled_image)
        
        # 转换为PhotoImage
        self._photo_image = ImageTk.PhotoImage(scaled_image)
        
        # 更新Canvas
        if self._canvas_image_id is None:
            self._canvas_image_id = self._canvas.create_image(
                0, 0,
                anchor=tk.NW,
                image=self._photo_image
            )
        else:
            self._canvas.itemconfig(
                self._canvas_image_id,
                image=self._photo_image
            )
        
        # 更新滚动区域
        self._canvas.configure(scrollregion=self._canvas.bbox(tk.ALL))
        
        # 更新缩放比例显示
        self._zoom_label.config(text=f"{int(self._zoom_scale * 100)}%")
    
    @safe_execute(default_return=None, error_message="绘制覆盖层失败")
    def _draw_overlay(self, image):
        """绘制识别结果覆盖层
        
        参数:
            image: PIL Image对象
        
        返回:
            PIL Image: 绘制了覆盖层的图像
        """
        # 创建副本以避免修改原图
        overlay_image = image.copy()
        draw = ImageDraw.Draw(overlay_image)
        
        # 获取识别结果状态
        status = self._result.get("status", "UNKNOWN")
        
        # 根据状态选择颜色
        if status == "PASS":
            color = "#4CAF50"  # 绿色
            text = "PASS"
        elif status == "FAIL":
            color = "#F44336"  # 红色
            text = "FAIL"
        else:
            color = "#FFC107"  # 黄色
            text = "UNKNOWN"
        
        # 绘制大的状态标识框（在图像右上角）
        box_width = int(image.width * 0.2)
        box_height = int(image.height * 0.1)
        box_x = image.width - box_width - 20
        box_y = 20
        
        # 绘制半透明背景
        draw.rectangle(
            [box_x, box_y, box_x + box_width, box_y + box_height],
            fill=color,
            outline=color,
            width=3
        )
        
        # 绘制文字（尝试使用系统字体，如果失败则使用默认字体）
        try:
            font_size = int(box_height * 0.5)
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        # 计算文字位置（居中）
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        text_x = box_x + (box_width - text_width) // 2
        text_y = box_y + (box_height - text_height) // 2
        
        draw.text((text_x, text_y), text, fill="white", font=font)
        
        # 绘制检测信息列表（在图像左下角）
        detection_info = self._result.get("detection_info", [])
        if detection_info:
            info_y = image.height - 20 - len(detection_info) * 25
            
            try:
                info_font = ImageFont.truetype("msyh.ttc", 14)  # 微软雅黑
            except:
                info_font = ImageFont.load_default()
            
            for i, info in enumerate(detection_info):
                y_pos = info_y + i * 25
                draw.text((20, y_pos), str(info), fill="white", font=info_font)
        
        return overlay_image
    
    @safe_execute(default_return=None, error_message="绘制结果覆盖层失败")
    def draw_result_overlay(self, result):
        """绘制识别结果覆盖层
        
        参数:
            result: 识别结果对象（字典），包含以下键：
                - status: 识别状态（"PASS"或"FAIL"）
                - detection_info: 检测信息列表
                - fields: 识别字段字典（可选）
                - confidence_scores: 置信度分数字典（可选）
        """
        self._result = result
        self._update_canvas()
    
    @safe_execute(default_return=None, error_message="清除覆盖层失败")
    def clear_overlay(self):
        """清除识别结果覆盖层"""
        self._result = None
        self._update_canvas()
    
    @safe_execute(default_return=None, error_message="设置缩放比例失败")
    def set_zoom_scale(self, scale):
        """设置缩放比例
        
        参数:
            scale: 缩放比例（1.0表示100%）
        """
        if scale <= 0:
            raise ValueError("缩放比例必须大于0")
        
        self._zoom_scale = scale
        self._update_canvas()
    
    @safe_execute(default_return=None, error_message="放大图像失败")
    def _zoom_in(self):
        """放大图像"""
        self._zoom_scale = min(self._zoom_scale * 1.2, 5.0)  # 最大500%
        self._update_canvas()
    
    @safe_execute(default_return=None, error_message="缩小图像失败")
    def _zoom_out(self):
        """缩小图像"""
        self._zoom_scale = max(self._zoom_scale / 1.2, 0.1)  # 最小10%
        self._update_canvas()
    
    @safe_execute(default_return=None, error_message="适应窗口失败")
    def _fit_to_window(self):
        """适应窗口大小"""
        if self._current_image is None:
            return
        
        # 获取Canvas大小
        canvas_width = self._canvas.winfo_width()
        canvas_height = self._canvas.winfo_height()
        
        if canvas_width <= 1 or canvas_height <= 1:
            # Canvas尚未显示，使用默认缩放
            self._zoom_scale = 1.0
            return
        
        # 计算缩放比例
        width_scale = canvas_width / self._current_image.width
        height_scale = canvas_height / self._current_image.height
        
        # 使用较小的缩放比例以确保图像完全显示
        self._zoom_scale = min(width_scale, height_scale, 1.0)
        self._update_canvas()
    
    @safe_execute(default_return=None, error_message="清空图像显示失败")
    def clear(self):
        """清空图像显示"""
        self._current_image = None
        self._result = None
        self._photo_image = None
        
        if self._canvas_image_id is not None:
            self._canvas.delete(self._canvas_image_id)
            self._canvas_image_id = None


# 测试代码
if __name__ == "__main__":
    root = tk.Tk()
    root.title("图像显示面板测试")
    root.geometry("800x600")
    
    panel = ImageDisplayPanel(root)
    panel.pack(fill=tk.BOTH, expand=True)
    
    # 创建测试图像
    test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    
    # 显示图像
    panel.display_image(test_image)
    
    # 测试识别结果覆盖层
    test_result = {
        "status": "PASS",
        "detection_info": [
            "问题",
            "数字",
            "用户名称",
            "解决方案图片计数: ID 0",
            "组织",
            "暂时（通过）"
        ]
    }
    
    def toggle_overlay():
        if panel._result is None:
            panel.draw_result_overlay(test_result)
        else:
            panel.clear_overlay()
    
    # 测试按钮
    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=10)
    
    tk.Button(btn_frame, text="切换覆盖层", command=toggle_overlay).pack(side=tk.LEFT, padx=5)
    
    root.mainloop()
