"""
解决方案制作面板 (SolutionMakerFrame)
集成自 ScrollableFrame.py 的 BankCardTrainerApp
用于嵌入到 InspectMainWindow 的侧边栏
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
from PIL import Image, ImageTk
import cv2
import numpy as np
import os
import shutil
import platform
import random
import time
import json

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
            def handle_file_error(func):
                return func
            @staticmethod
            def handle_camera_error(func):
                return func
        return _ErrorHandler()
    ErrorHandler = ErrorHandler()
    safe_call = lambda func, *args, **kwargs: func(*args, **kwargs)
    safe_execute = lambda **kwargs: lambda func: func
    suppress_errors = lambda *args, **kwargs: lambda: None


# ============================================================================
# 工具函数 (从 BankCardTrainerApp 迁移)
# ============================================================================

@safe_execute(default_return=None, log_error=True, error_message="图像读取失败")
def cv2_imread_chinese(file_path, flags=cv2.IMREAD_COLOR):
    """支持中文路径的图像读取"""
    img_data = np.fromfile(file_path, dtype=np.uint8)
    img = cv2.imdecode(img_data, flags)
    return img


def resize_with_padding(image, target_size):
    """等比例缩放并填充到目标尺寸"""
    h, w = image.shape[:2]
    target_w, target_h = target_size
    scale = min(target_w / w, target_h / h)
    new_w = int(w * scale)
    new_h = int(h * scale)
    resized = cv2.resize(image, (new_w, new_h))
    canvas = np.full((target_h, target_w), 255, dtype=np.uint8)
    x_offset = (target_w - new_w) // 2
    y_offset = (target_h - new_h) // 2
    canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
    return canvas


# ============================================================================
# SolutionMakerFrame 类定义
# ============================================================================

class SolutionMakerFrame(tk.Frame):
    """
    解决方案制作面板（嵌入式版本）
    
    功能：
    - 方案管理（创建/删除/切换）
    - 图像加载（文件/相机捕获）
    - ROI标注和字符提取
    - 锚点定位
    - 模板保存和加载
    """
    
    def __init__(self, parent, camera_controller, canvas_widget, on_back_callback, 
                 preview_canvas=None, template_canvas=None, initial_image=None, main_window=None):
        """
        初始化解决方案制作面板
        
        参数:
            parent: 父容器（侧边栏）
            camera_controller: 相机控制器实例
            canvas_widget: 主界面的画布对象（共享，用于ROI标注）
            on_back_callback: 返回主菜单的回调函数
            preview_canvas: 实时预览画布（红色框区域）
            template_canvas: 字符模板画布（蓝色框区域）- 实际是Frame容器
            initial_image: 初始图像（numpy数组，可选）- 从工具侧边栏传递的捕获图像
            main_window: 主窗口实例（用于保存/恢复用户选择的方案）
        """
        super().__init__(parent, bg="white")
        
        # 保存外部引用
        self.cam = camera_controller
        self.canvas = canvas_widget  # ROI标注画布
        self.preview_canvas = preview_canvas  # 实时预览画布
        self.template_canvas = template_canvas  # 字符模板容器（Frame）
        self.template_canvas_widget = None  # 真正的Canvas（用于滚动）
        self.on_back = on_back_callback
        self.main_window = main_window  # 保存主窗口引用
        
        # ====================================================================
        # 核心变量初始化（从 BankCardTrainerApp 迁移）
        # ====================================================================
        
        # 图像相关
        self.image_path = None
        self.original_image = None
        self.tk_image = None
        self.zoom_scale = 1.0
        
        # ROI框选相关
        self.rect_start = None
        self.rect_end = None
        self.current_rect_id = None
        
        # 支持多个临时框（用户可以连续框选多个区域）
        self.temp_rects = []  # 存储多个临时框：[{'start': (x,y), 'end': (x,y), 'canvas_id': id, 'field_type': str}, ...]
        
        # 布局配置
        self.roi_layout_config = {}  # 已保存的布局配置（从磁盘加载或已保存）
        self._pending_field_props = {}  # 临时存储字段属性，保存全部时才写入
        self.temp_layout_config = {}  # 临时布局配置（执行提取后，保存前）
        
        # 字段类型
        self.field_types = ["CardNumber", "Name", "Date", "FirstDigitAnchor"]
        
        # 字符模板存储
        self.char_widgets = {}
        self.section_frames = {}
        
        # 颜色映射
        self.color_map = {
            "CardNumber": "#ff0000",
            "Name": "#0000ff",
            "Date": "#008000",
            "FirstDigitAnchor": "#ff00ff"  # 紫色显示锚点
        }
        
        # 方案管理
        # 使用上级目录的solutions文件夹（与Card-OCR-v1同级）
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        self.solutions_root = os.path.join(parent_dir, "solutions")
        self.current_solution_name = None
        if not os.path.exists(self.solutions_root):
            os.makedirs(self.solutions_root)
        
        pass  # print removed
        # 归一化尺寸
        self.norm_width = 32
        self.norm_height = 48
        self.card_width = 60  # 字符卡片宽度
        self.card_spacing = 10  # 卡片间距（左右padx=5，共10）
        self.card_border = 5  # 卡片边框和内边距
        
        # UI变量（稍后在 _setup_ui 中创建）
        self.var_field_type = None
        self.var_is_anchor = None
        self.var_work_mode = None
        self.var_show_debug = None
        self.var_solution_name = None
        
        # 初始化UI
        self._setup_ui()
        
        # 刷新方案列表
        self.refresh_solution_list()
        
        # 恢复用户上次选择的方案（如果有）
        if self.main_window and hasattr(self.main_window, 'last_selected_solution'):
            last_solution = self.main_window.last_selected_solution
            if last_solution:
                # 检查该方案是否仍然存在
                solution_path = os.path.join(self.solutions_root, last_solution)
                if os.path.exists(solution_path):
                    pass  # print removed
                    self.var_solution_name.set(last_solution)
                    self.current_solution_name = last_solution
                    # 延迟加载，确保UI完全初始化
                    self.after(50, self.load_solution_data)
                else:
                    self.main_window.last_selected_solution = None
        
        # 绑定画布事件
        self._bind_canvas_events()
        
        # 如果提供了初始图像，加载并显示
        if initial_image is not None:
            pass  # print removed
            self.original_image = initial_image.copy()
            # 计算合适的缩放比例（90%画布大小）
            self.zoom_scale = self._get_90_percent_scale()
            # 延迟刷新画布，确保UI已完全初始化
            self.after(100, self._refresh_canvas_image)
        
        pass  # print removed
    # ====================================================================
    # UI布局方法
    # ====================================================================
    
    def _setup_ui(self):
        """设置完整的UI布局"""
        self.configure(bg="white")
        
        # 创建各个UI区域（移除_create_scroll_container）
        self._create_top_navbar()
        self._create_solution_management()
        self._create_field_selection()
        self._create_tool_buttons()
        self._create_mode_selection()
        
        # 如果有外部模板画布，初始化字段sections
        pass  # print removed
        if self.template_canvas:
            pass  # print removed
            for field_type in self.field_types:
                pass  # print removed
                self._create_field_section(field_type)
            pass
        else:
            pass
    
    def _create_top_navbar(self):
        """创建顶部导航栏（返回按钮 + 标题）"""
        navbar = tk.Frame(self, bg="white")
        navbar.pack(fill=tk.X, padx=(10, 5), pady=5)

        tk.Label(
            navbar,
            text="字体库方案制作工具",
            font=("Microsoft YaHei UI", 11, "bold"),
            bg="white",
            fg="#0055A4"
        ).pack(side=tk.LEFT)

        tk.Button(
            navbar,
            text="← 返回",
            font=("Microsoft YaHei UI", 8),
            bg="#F0F0F0",
            relief=tk.FLAT,
            cursor="hand2",
            command=self.on_back
        ).pack(side=tk.RIGHT)

        # 分隔线
        tk.Frame(self, height=1, bg="#E0E0E0").pack(fill=tk.X, padx=(10, 5))
    
    def _create_solution_management(self):
        """创建方案管理区域（下拉框 + 新建/删除/导入/导出按钮）"""
        frame = tk.LabelFrame(
            self,
            text="字体方案管理",
            font=("微软雅黑", 9, "bold"),
            bg="white",
            fg="#2c3e50",
            padx=10,
            pady=5
        )
        frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        # 第一行：标签 + 下拉框
        row1 = tk.Frame(frame, bg="white")
        row1.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(
            row1,
            text="当前方案:",
            font=("微软雅黑", 9),
            bg="white"
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self.var_solution_name = tk.StringVar()
        self.combo_solution = ttk.Combobox(
            row1,
            textvariable=self.var_solution_name,
            state="readonly",
            width=20,
            font=("微软雅黑", 9)
        )
        self.combo_solution.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.combo_solution.bind("<<ComboboxSelected>>", self.on_solution_selected)
        
        # 第二行：新建和删除按钮
        row2 = tk.Frame(frame, bg="white")
        row2.pack(fill=tk.X)
        
        btn_new = tk.Button(
            row2,
            text="➕ 新建方案",
            font=("微软雅黑", 9),
            bg="#27ae60",
            fg="white",
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.create_solution
        )
        btn_new.pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)
        
        btn_delete = tk.Button(
            row2,
            text="❌ 删除方案",
            font=("微软雅黑", 9),
            bg="#e74c3c",
            fg="white",
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.delete_solution
        )
        btn_delete.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 第三行：导入和导出按钮
        row3 = tk.Frame(frame, bg="white")
        row3.pack(fill=tk.X, pady=(5, 0))
        
        btn_import = tk.Button(
            row3,
            text="📥 导入方案",
            font=("微软雅黑", 9),
            bg="#8e44ad",
            fg="white",
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.import_solution
        )
        btn_import.pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)
        
        btn_export = tk.Button(
            row3,
            text="📤 导出方案",
            font=("微软雅黑", 9),
            bg="#16a085",
            fg="white",
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.export_solution
        )
        btn_export.pack(side=tk.LEFT, fill=tk.X, expand=True)
    
    @ErrorHandler.handle_file_error
    def create_solution(self):
        """
        创建新方案
        
        流程:
        1. 弹出对话框让用户输入方案名
        2. 验证方案名是否合法（非空、不包含特殊字符、不重复）
        3. 创建方案目录
        4. 刷新方案列表
        5. 切换到新创建的方案
        """
        # 0. 清空 OCR 状态中的字段布局（新增）
        if self.main_window and hasattr(self.main_window, 'clear_ocr_state_layout'):
            self.main_window.clear_ocr_state_layout()
        
        # 1. 弹出输入对话框
        solution_name = simpledialog.askstring(
            "创建新方案",
            "请输入方案名称:",
            parent=self
        )
        
        # 用户取消输入
        if solution_name is None:
            return
        
        # 2. 验证方案名
        solution_name = solution_name.strip()
        
        # 检查是否为空
        if not solution_name:
            messagebox.showwarning("警告", "方案名称不能为空！")
            return
        
        # 检查是否包含非法字符（Windows文件名限制）
        invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
        if any(char in solution_name for char in invalid_chars):
            messagebox.showwarning(
                "警告",
                f"方案名称不能包含以下字符:\n{' '.join(invalid_chars)}"
            )
            return
        
        # 检查方案是否已存在
        solution_path = os.path.join(self.solutions_root, solution_name)
        if os.path.exists(solution_path):
            messagebox.showwarning("警告", f"方案 '{solution_name}' 已存在！")
            return
        
        # 3. 创建方案目录
        self._create_solution_directories(solution_path)
        
        # 4. 刷新方案列表
        self.refresh_solution_list()
        
        # 5. 切换到新创建的方案
        self.var_solution_name.set(solution_name)
        self.current_solution_name = solution_name
        self.on_solution_selected()
        # 记录新建解决方案日志
        if self.main_window and hasattr(self.main_window, '_audit'):
            self.main_window._audit(
                "template_operation", "new_solution",
                target_object=solution_name
            )

    @ErrorHandler.handle_file_error
    def _create_solution_directories(self, solution_path):
        """创建方案目录结构"""
        os.makedirs(solution_path)
        
        # 为每个字段类型创建子目录（除了锚点）
        for field_type in self.field_types:
            if field_type != "FirstDigitAnchor":
                field_dir = os.path.join(solution_path, field_type)
                os.makedirs(field_dir)
        
        # 从路径中提取方案名称
        solution_name = os.path.basename(solution_path)
        
        messagebox.showinfo("成功", f"方案 '{solution_name}' 创建成功！")
    
    @ErrorHandler.handle_file_error
    def delete_solution(self):
        """
        删除方案
        
        流程:
        1. 检查是否选择了方案
        2. 弹出确认对话框
        3. 删除方案目录及其所有内容
        4. 刷新方案列表
        5. 清空编辑器
        """
        # 1. 检查是否选择了方案
        solution_name = self.var_solution_name.get()
        
        if not solution_name:
            messagebox.showwarning("警告", "请先选择要删除的方案！")
            return
        
        # 2. 弹出确认对话框
        confirm = messagebox.askyesno(
            "确认删除",
            f"确定要删除方案 '{solution_name}' 吗？\n\n"
            f"此操作将删除该方案的所有数据，且无法恢复！",
            icon='warning'
        )
        
        if not confirm:
            return
        
        # 3. 删除方案目录及其所有内容
        solution_path = os.path.join(self.solutions_root, solution_name)
        
        self._delete_solution_directory(solution_path, solution_name)
        
        # 4. 刷新方案列表
        self.refresh_solution_list()

    @ErrorHandler.handle_file_error
    def _delete_solution_directory(self, solution_path, solution_name):
        """删除方案目录"""
        if os.path.exists(solution_path):
            shutil.rmtree(solution_path)
            pass  # print removed
        else:
            messagebox.showwarning("警告", f"方案 '{solution_name}' 不存在！")
            return
        
        # 5. 清空编辑器
        self.current_solution_name = None
        self.var_solution_name.set("")
        self._clear_editor()
        
        messagebox.showinfo("成功", f"方案 '{solution_name}' 已删除！")
    
    def refresh_solution_list(self):
        """
        刷新方案列表
        
        扫描 solutions/ 目录，更新下拉框中的方案列表
        """
        self._scan_and_update_solution_list()
    
    @safe_execute(default_return=None, log_error=False, error_message="刷新方案列表失败")
    def _scan_and_update_solution_list(self):
        """扫描并更新方案列表"""
        # 获取所有方案目录
        if not os.path.exists(self.solutions_root):
            os.makedirs(self.solutions_root)
            solution_names = []
        else:
            solution_names = [
                name for name in os.listdir(self.solutions_root)
                if os.path.isdir(os.path.join(self.solutions_root, name))
            ]
        
        # 按字母顺序排序
        solution_names.sort()
        
        # 更新下拉框
        self.combo_solution['values'] = solution_names
        
        # 不自动选中任何方案（移除自动选中第一个方案的逻辑）
        # 用户需要手动选择方案，或者由show_solution_maker恢复上次选择
    
    def on_solution_selected(self, event=None):
        """
        方案选择事件处理
        
        当用户切换方案时，加载该方案的数据
        
        参数:
            event: 事件对象（可选，用于绑定到Combobox事件）
        
        流程:
        1. 获取选中的方案名
        2. 验证方案名是否有效
        3. 更新 current_solution_name
        4. 清空编辑器（只清除字符模板，保留捕获的画面）
        5. 加载方案数据（布局配置和已保存的字符模板）
        """
        # 1. 获取选中的方案名
        solution_name = self.var_solution_name.get()
        
        # 2. 验证方案名是否有效
        if not solution_name:
            return
        
        # 验证方案目录是否存在
        solution_path = os.path.join(self.solutions_root, solution_name)
        if not os.path.exists(solution_path):
            messagebox.showwarning(
                "警告",
                f"方案 '{solution_name}' 的目录不存在！\n请刷新方案列表。"
            )
            return
        
        # 3. 更新当前方案名
        self.current_solution_name = solution_name
        pass  # print removed
        # 保存用户选择到主窗口（关键修复：记录用户选择）
        if self.main_window and hasattr(self.main_window, 'last_selected_solution'):
            self.main_window.last_selected_solution = solution_name
            pass  # print removed
        # 4. 清空当前编辑器（保留捕获的画面）
        self._clear_editor(keep_captured_image=True)
        
        # 5. 加载方案数据
        self._load_solution_data_safe(solution_name)

    def _load_solution_data_safe(self, solution_name):
        """安全加载方案数据"""
        try:
            self.load_solution_data()
            pass  # print removed

            # 同步字段信息到主窗口
            if self.main_window and hasattr(self.main_window, 'ocr_field_types'):
                self.main_window.ocr_field_types = [
                    f for f in self.field_types if f != "FirstDigitAnchor"
                ]
            
            # ★★★ 关键修复：将加载的布局配置同步到主窗口的saved_ocr_state ★★★
            if self.main_window and hasattr(self.main_window, 'saved_ocr_state'):
                # 更新saved_ocr_state中的roi_layout和solution_name
                self.main_window.saved_ocr_state['roi_layout'] = self.roi_layout_config.copy()
                self.main_window.saved_ocr_state['solution_name'] = self.current_solution_name
                self.main_window.saved_ocr_state['has_state'] = True
        except Exception as e:
            messagebox.showerror(
                "加载失败",
                f"加载方案 '{solution_name}' 时出错:\n{str(e)}"
            )
            # 加载失败后清空当前方案名
            self.current_solution_name = None
    
    @ErrorHandler.handle_file_error
    def load_solution_data(self):
        """
        加载方案数据
        
        从方案目录加载：
        1. 自定义字段配置 (custom_fields.json)
        2. 布局配置文件 (layout_config.json)
        3. 已保存的字符模板图像
        
        注意：此方法在任务 4.5 中会进一步完善
        """
        if not self.current_solution_name:
            return
        
        solution_path = os.path.join(self.solutions_root, self.current_solution_name)
        
        # 0. 加载自定义字段配置（必须在加载布局配置之前）
        self._load_custom_fields_config()
        
        # 1. 加载布局配置文件
        config_file = os.path.join(solution_path, "layout_config.json")
        if os.path.exists(config_file):
            self._load_layout_config_from_file(config_file)
        else:
            pass  # print removed
        # 2. 加载已保存的字符模板图像
        # 遍历每个字段类型目录
        for field_type in self.field_types:
            if field_type == "FirstDigitAnchor":
                continue  # 锚点不需要加载字符模板
            
            field_dir = os.path.join(solution_path, field_type)
            pass  # print removed
            if not os.path.exists(field_dir):
                pass  # print removed
                continue
            
            # 获取该字段的所有PNG图像文件
            self._load_field_character_templates(field_dir, field_type)
        
        # 刷新网格布局，确保所有模板正确显示
        # 使用多次延迟调用,确保Canvas已经完成布局
        def delayed_reflow():
            """延迟重新布局"""
            if self.template_canvas_widget:
                self.template_canvas_widget.update_idletasks()
            
            # 打印详细的宽度信息
            pass  # print removed
            pass  # print removed
            pass  # print removed
            if self.template_canvas_widget:
                pass
                # print(f"Canvas宽度: {self.template_canvas_widget.winfo_width()}px")
            if self.template_canvas:
                pass  # print(f"Frame宽度: {self.template_canvas.winfo_width()}px")
            
            # 打印第一个grid的宽度
            for section in self.field_types:
                if section in self.section_frames:
                    grid = self.section_frames[section]['archived_grid']
                    if grid and grid.winfo_exists():
                        pass  # print(f"{section} archived_grid宽度: {grid.winfo_width()}px")
                        break
            pass  # print removed
            self._reflow_grid()
        
        # 第一次立即调用
        self._reflow_grid()
        
        # 第二次延迟100ms调用(Canvas可能还在初始化)
        if self.template_canvas_widget:
            self.template_canvas_widget.after(100, delayed_reflow)
        
        # 第三次延迟500ms调用(确保Canvas完全初始化)
        if self.template_canvas_widget:
            self.template_canvas_widget.after(500, delayed_reflow)
        
        # 第四次延迟1000ms调用(最终确保)
        if self.template_canvas_widget:
            self.template_canvas_widget.after(1000, delayed_reflow)
        
        # 重置滚动条到顶部（使用真正的Canvas）
        if self.template_canvas_widget:
            self.template_canvas_widget.yview_moveto(0)
        
        # 如果有捕获的图像，重新绘制（包括新加载的ROI框）
        if self.original_image is not None:
            pass  # print removed
            self._refresh_canvas_image()
        
        pass  # print removed

    @safe_execute(default_return=None, log_error=True, error_message="加载布局配置失败")
    def _load_layout_config_from_file(self, config_file):
        """从文件加载布局配置"""
        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
            
            # 重建 roi_layout_config（从嵌套结构转换为扁平结构）
            self.roi_layout_config = {}
            
            # 加载锚点信息
            if config_data.get("strategy") == "anchor_based":
                self.roi_layout_config["FirstDigitAnchor"] = {
                    "roi": config_data["anchor_rect"],
                    "search_area": config_data.get("anchor_search_area", config_data["anchor_rect"]),
                    "is_anchor": True
                }
                pass  # print removed
                # 确保 FirstDigitAnchor 被注册
                if "FirstDigitAnchor" not in self.field_types:
                    self._register_field("FirstDigitAnchor", create_ui=False)
            
            # 加载其他字段
            if "fields" in config_data:
                field_props_map = config_data.get("field_props", {})
                for field_name, field_coords in config_data["fields"].items():
                    self.roi_layout_config[field_name] = {
                        "roi": field_coords,
                        "search_area": field_coords,
                        "is_anchor": False,
                        "field_props": field_props_map.get(field_name, {}),
                    }
                    # 同步到 _pending_field_props，让置信度对话框能读到
                    if field_name in field_props_map:
                        self._pending_field_props[field_name] = field_props_map[field_name]
                    # 确保字段类型被注册
                    if field_name not in self.field_types:
                        self._register_field(field_name, create_ui=True)
            
            pass

    @safe_execute(default_return=None, log_error=False, error_message="加载字符模板失败")
    def _load_field_character_templates(self, field_dir, field_type):
        """加载字段的字符模板"""
        image_files = [
            f for f in os.listdir(field_dir)
            if f.lower().endswith('.png')
        ]
        
        # 按文件名排序
        image_files.sort()
        
        # 加载每个图像
        loaded_count = 0
        for img_file in image_files:
            img_path = os.path.join(field_dir, img_file)
            char_img = self._load_single_character_template(img_path, img_file, field_type)
            if char_img is not None:
                loaded_count += 1
        
        if loaded_count > 0:
            pass  # print removed
            # 验证模板是否正确添加到existing列表
            existing_count = len(self.char_widgets[field_type]['existing'])
            new_count = len(self.char_widgets[field_type]['new'])
            pass
            if existing_count != loaded_count:
                pass
        else:
            pass

    @safe_execute(default_return=None, log_error=False, error_message="加载单个字符模板失败")
    def _load_single_character_template(self, img_path, img_file, field_type):
        """加载单个字符模板"""
        # 读取图像（使用支持中文路径的函数）
        char_img = cv2_imread_chinese(img_path, cv2.IMREAD_GRAYSCALE)
        if char_img is not None:
            # 提取标签（文件名格式：label_index.png）
            label = img_file.split('_')[0] if '_' in img_file else ''
            
            # 反向转换特殊字符（与保存时的转换对应）
            label = label.replace("backslash", "\\").replace("slash", "/").replace("char_dot", ".")
            
            pass  # print removed
            # 使用_add_char_grid_item创建UI元素
            self._add_char_grid_item(char_img, field_type, label_text=label, is_new=False)
            return char_img
        return None
    
    def _clear_editor(self, keep_captured_image=False):
        """
        清空编辑器
        
        清除所有当前显示的内容，包括：
        1. 清空画布上的ROI框（但可选保留捕获的图像）
        2. 清空所有字符模板网格
        3. 销毁所有section容器
        4. 重置图像相关变量（可选保留original_image）
        5. 重置ROI布局配置
        
        参数:
            keep_captured_image: 是否保留捕获的图像（True=保留，False=清空恢复视频流）
        """
        # 1. 清空预览画布上的ROI框（但保留捕获的图像）
        if self.preview_canvas:
            # 只删除ROI框，不删除捕获的图像
            self.preview_canvas.delete("saved_roi_visual")
            if not keep_captured_image:
                # 如果不保留捕获的图像，清空整个画布
                self.preview_canvas.delete("all")
        elif self.canvas:
            self.canvas.delete("saved_roi_visual")
            if not keep_captured_image:
                self.canvas.delete("all")
        
        # 2. 清空所有字符模板网格
        for field_type in self.char_widgets:
            # 清空已归档模板
            for item in self.char_widgets[field_type]['existing']:
                if 'frame' in item and item['frame'].winfo_exists():
                    item['frame'].destroy()
            
            # 清空本次提取结果
            for item in self.char_widgets[field_type]['new']:
                if 'frame' in item and item['frame'].winfo_exists():
                    item['frame'].destroy()
            
            # 重置列表
            self.char_widgets[field_type]['existing'] = []
            self.char_widgets[field_type]['new'] = []
        
        # 3. 销毁所有section容器（关键修复！）
        for field_type in self.section_frames:
            if 'container' in self.section_frames[field_type]:
                container = self.section_frames[field_type]['container']
                if container and container.winfo_exists():
                    container.destroy()
        
        # 清空section_frames字典
        self.section_frames = {}
        
        # 重新创建所有字段的section（确保UI结构正确）
        for field_type in self.field_types:
            self._register_field(field_type, create_ui=True)
        
        # 4. 重置图像相关变量（可选保留original_image）
        if not keep_captured_image:
            # 完全清空，恢复视频流
            self.image_path = None
            self.original_image = None  # 清空后视频循环会恢复
            self.tk_image = None
            self.zoom_scale = 1.0
            pass  # print removed
            pass
        else:
            # 保留捕获的图像，只清空路径
            self.image_path = None
            # original_image保持不变
            # tk_image保持不变
            # zoom_scale保持不变
            pass  # print removed
        # 5. 重置ROI框选变量
        self.rect_start = None
        self.rect_end = None
        self.current_rect_id = None
        
        # 清空临时框列表
        self.temp_rects = []
        
        # 6. 重置ROI布局配置
        self.roi_layout_config = {}
        self.temp_layout_config = {}  # 同时清空临时布局
    
    def _create_field_selection(self):
        """创建字段选择区域（字段类型单选按钮 + 新建/删除按钮）"""
        frame = tk.LabelFrame(
            self,
            text="字段标注",
            font=("微软雅黑", 9, "bold"),
            bg="white",
            fg="#2c3e50",
            padx=10,
            pady=5
        )
        frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(
            frame,
            text="标注字段:",
            font=("微软雅黑", 11),
            bg="white",
            anchor="w"
        ).pack(fill=tk.X, pady=(0, 3))

        # 字段列表容器（grid 布局，每行4列，列宽均等）
        self.field_icon_frame = tk.Frame(frame, bg="white")
        self.field_icon_frame.pack(fill=tk.X, pady=(0, 5))
        for col in range(4):
            self.field_icon_frame.grid_columnconfigure(col, weight=1, uniform="field_col")

        # 创建单选按钮
        self.var_field_type = tk.StringVar(value=self.field_types[0])

        field_labels = {
            "CardNumber": "卡号",
            "Name": "姓名",
            "Date": "日期",
            "FirstDigitAnchor": "锚点"
        }

        self.field_buttons = {}
        for i, field_type in enumerate(self.field_types):
            label = field_labels.get(field_type, field_type)
            rb = tk.Radiobutton(
                self.field_icon_frame,
                text=label,
                variable=self.var_field_type,
                value=field_type,
                font=("微软雅黑", 10),
                bg="white",
                activebackground="white",
                selectcolor="white",
                cursor="hand2",
                anchor="w",
                command=lambda ft=field_type: self._select_field(ft)
            )
            rb.grid(row=i // 4, column=i % 4, sticky="w", padx=2, pady=2)
            self.field_buttons[field_type] = rb

        self.var_is_anchor = tk.BooleanVar(value=False)

        # 第二行：新建字段和删除字段按钮
        row3 = tk.Frame(frame, bg="white")
        row3.pack(fill=tk.X)

        btn_add_field = tk.Button(
            row3,
            text="➕ 新建字段",
            font=("微软雅黑", 9),
            bg="#3498db",
            fg="white",
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.add_custom_field
        )
        btn_add_field.pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)

        btn_delete_field = tk.Button(
            row3,
            text="🗑️ 删除字段",
            font=("微软雅黑", 9),
            bg="#e74c3c",
            fg="white",
            relief=tk.FLAT,
            padx=10,
            pady=3,
            cursor="hand2",
            command=self.delete_field
        )
        btn_delete_field.pack(side=tk.LEFT, fill=tk.X, expand=True)
    
    def _select_field(self, field_type):
        """
        选择字段类型
        
        参数:
            field_type: 字段类型
        """
        self.var_field_type.set(field_type)
        # 更新锚点复选框状态
        if field_type == "FirstDigitAnchor":
            self.var_is_anchor.set(True)
        else:
            self.var_is_anchor.set(False)
    
    def _on_anchor_toggled(self):
        """
        锚点复选框切换事件
        
        当用户勾选/取消锚点复选框时，自动切换字段类型
        """
        if self.var_is_anchor.get():
            # 勾选锚点，切换到FirstDigitAnchor
            # self.var_field_type.set("FirstDigitAnchor")  # 已注释，改用_select_field
            self._select_field("FirstDigitAnchor")
        else:
            # 取消锚点，恢复到第一个非锚点字段
            non_anchor_fields = [f for f in self.field_types if f != "FirstDigitAnchor"]
            if non_anchor_fields:
                # self.var_field_type.set(non_anchor_fields[0])  # 已注释，改用_select_field
                self._select_field(non_anchor_fields[0])
    
    def _create_tool_buttons(self):
        """创建工具按钮区域（打开图片、捕获画面、执行提取、保存全部、清空本次提取）"""
        frame = tk.LabelFrame(
            self,
            text="工具操作",
            font=("微软雅黑", 9, "bold"),
            bg="white",
            fg="#2c3e50",
            padx=10,
            pady=5
        )
        frame.pack(fill=tk.X, padx=10, pady=5)

        btn_cfg = dict(font=("微软雅黑", 9), fg="white", relief=tk.FLAT,
                       pady=5, cursor="hand2", width=1)

        # 第一行：打开图片 + 捕获画面
        row1 = tk.Frame(frame, bg="white")
        row1.pack(fill=tk.X, pady=(0, 5))

        tk.Button(row1, text="打开图片", bg="#3498db",
                  command=self.load_image_from_file, **btn_cfg
                  ).pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)

        tk.Button(row1, text="捕获画面", bg="#9b59b6",
                  command=self.capture_from_camera, **btn_cfg
                  ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 第二行：执行提取 + 保存全部
        row2 = tk.Frame(frame, bg="white")
        row2.pack(fill=tk.X)

        tk.Button(row2, text="执行提取", bg="#f39c12",
                  command=self.process_selection, **btn_cfg
                  ).pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)

        tk.Button(row2, text="保存全部", bg="#27ae60",
                  command=self.save_templates, **btn_cfg
                  ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 第三行：取消选中 + 清空本次提取
        row3 = tk.Frame(frame, bg="white")
        row3.pack(fill=tk.X, pady=(5, 0))

        tk.Button(row3, text="取消选中", bg="#e67e22",
                  command=self.clear_selected_state, **btn_cfg
                  ).pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)

        tk.Button(row3, text="清空本次提取", bg="#e74c3c",
                  command=self.clear_new_extraction, **btn_cfg
                  ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 第四行：批量删除（已注释，现在使用右键菜单进行批量删除）
        # row4 = tk.Frame(frame, bg="white")
        # row4.pack(fill=tk.X, pady=(5, 0))
        # 
        # btn_batch_delete = tk.Button(
        #     row4,
        #     text="🗑️ 批量删除模板",
        #     font=("微软雅黑", 9),
        #     bg="#e67e22",
        #     fg="white",
        #     relief=tk.FLAT,
        #     padx=10,
        #     pady=5,
        #     cursor="hand2",
        #     command=self.batch_delete_selected_templates
        # )
        # btn_batch_delete.pack(fill=tk.X)
    
    @ErrorHandler.handle_file_error
    def load_image_from_file(self):
        """
        从文件加载图像
        
        流程:
        1. 弹出文件选择对话框
        2. 使用支持中文路径的函数读取图像
        3. ★ 统一到相机硬件尺寸
        4. 计算适配缩放比例
        5. 刷新画布显示
        6. 启用处理按钮
        """
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
        
        # 2. 读取图像（支持中文路径）
        self._load_image_from_file(file_path)

        # 3. 强制更新画布尺寸，再计算适配缩放比例
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        display_canvas.update_idletasks()
        self.zoom_scale = self._get_90_percent_scale()

        # 4. 刷新显示
        self._refresh_canvas_image()

    @ErrorHandler.handle_file_error
    def _load_image_from_file(self, file_path):
        """从文件加载图像"""
        self.image_path = file_path
        self.original_image = cv2_imread_chinese(file_path)
        
        if self.original_image is None:
            raise ValueError("无法读取图片文件")
        
        # ★★★ 关键改进：统一到相机硬件尺寸 ★★★
        self.original_image = self._resize_to_camera_size(self.original_image)
        
        messagebox.showinfo("成功", f"图像加载成功！\n文件: {os.path.basename(file_path)}")
    
    @ErrorHandler.handle_camera_error
    def capture_from_camera(self):
        """
        从相机捕获图像
        
        流程:
        1. 检查相机控制器是否可用
        2. 从相机获取当前图像
        3. 验证图像有效性
        4. 保存图像（设置original_image后，视频循环会自动跳过刷新）
        5. 计算适配缩放比例
        6. 在预览画布显示截取的帧
        """
        # 1. 检查相机控制器是否可用
        if self.cam is None:
            messagebox.showwarning("警告", "相机控制器不可用！")
            return
        
        # 2. 从相机获取当前图像
        self._capture_camera_image()

    @ErrorHandler.handle_camera_error
    def _capture_camera_image(self):
        """从相机捕获图像"""
        captured_image = self.cam.get_image()
        
        if captured_image is None:
            raise ValueError("相机返回空图像")
        
        # 3. 验证图像有效性
        if captured_image.size == 0:
            raise ValueError("相机返回空数组")
        
        # 检查是否是"NO SIGNAL"画面
        # 更准确的判断：检查图像是否过暗且方差很小（表示画面均匀无内容）
        mean_val = np.mean(captured_image)
        std_val = np.std(captured_image)
        
        # 无信号画面特征：平均值很低且标准差很小（画面均匀暗）
        if mean_val < 30 and std_val < 10:
            messagebox.showwarning(
                "警告",
                "相机可能未连接或无信号！\n请检查相机连接状态。"
            )
            # 仍然加载，让用户看到画面
        else:
            pass  # print removed
        # 4. 保存图像（关键：设置后视频循环会自动停止刷新）
        self.original_image = captured_image
        self.image_path = None  # 清空文件路径（表示来自相机）
        
        pass  # print removed
        pass  # print removed
        # print(f"   图像类型: {'灰度' if len(self.original_image.shape) == 2 else '彩色'}")
        
        # 5. 计算适配缩放比例（高度90%）
        self.zoom_scale = self._get_90_percent_scale()
        pass  # print removed
        # 6. 在预览画布显示截取的帧
        self._refresh_canvas_image()
        
        messagebox.showinfo("成功", "已捕获当前画面！\n提示：画面已暂停，可以进行标注操作。")
    
    def _get_main_window(self):
        """获取主窗口实例（InspectMainWindow）"""
        # 向上遍历父组件，找到InspectMainWindow实例
        widget = self
        while widget:
            if hasattr(widget, 'video_loop_running'):
                return widget
            widget = widget.master
        return None
    
    def _get_fit_scale(self):
        """
        计算适配缩放比例（宽高都适配，取较小值）
        
        根据画布大小和图像大小，计算合适的缩放比例，
        使图像能够完整显示在画布中
        
        返回:
            float: 缩放比例（0.1 ~ 1.0）
        """
        if self.original_image is None:
            return 1.0
        
        # 获取图像尺寸
        h, w = self.original_image.shape[:2]
        
        # 使用preview_canvas的尺寸
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        
        # 获取画布尺寸（如果画布未显示，使用默认值）
        canvas_w = display_canvas.winfo_width() or 800
        canvas_h = display_canvas.winfo_height() or 600
        
        # 计算缩放比例（不放大，只缩小）
        scale = min(canvas_w / w, canvas_h / h, 1.0)
        
        return scale
    
    def _get_90_percent_scale(self):
        """
        计算90%缩放比例，同时适配宽高，确保图片完整显示在画布内
        """
        if self.original_image is None:
            return 1.0

        h, w = self.original_image.shape[:2]

        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        canvas_w = display_canvas.winfo_width() or 800
        canvas_h = display_canvas.winfo_height() or 600

        scale_h = (canvas_h * 0.90) / h
        scale_w = (canvas_w * 0.90) / w
        scale = min(scale_h, scale_w)
        return min(scale, 1.0)
    
    def _get_height_fit_scale(self):
        """
        计算高度填充缩放比例（填充窗口）
        
        高度填充整个预览区（100%），宽度按比例缩放
        
        返回:
            float: 缩放比例
        """
        if self.original_image is None:
            return 1.0
        
        # 获取图像尺寸
        h, w = self.original_image.shape[:2]
        
        # 使用preview_canvas的尺寸
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        
        # 强制更新画布尺寸
        display_canvas.update_idletasks()
        
        # 获取画布尺寸（如果画布未显示，使用默认值）
        canvas_h = display_canvas.winfo_height()
        
        pass  # print removed
        if canvas_h <= 1:
            canvas_h = 600
        
        # 计算缩放比例（高度100%填充）
        scale = canvas_h / h
        
        pass  # print removed
        return scale
    
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
        if not self.cam:
            return image
        
        camera_width = self.cam.width
        camera_height = self.cam.height
        
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
        print(f"📐 图像尺寸调整:")
        print(f"   原始: {current_w}x{current_h}")
        print(f"   目标: {camera_width}x{camera_height} (相机硬件)")
        
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
        
        print(f"   缩放后: {new_w}x{new_h}")
        print(f"   填充位置: ({x_offset}, {y_offset})")
        
        return canvas
    
    def _refresh_canvas_image(self):
        """
        刷新画布显示
        
        流程:
        1. 清空画布（删除图像和ROI框，保留用户正在绘制的临时框）
        2. 根据缩放比例调整图像大小
        3. 转换为RGB格式（OpenCV使用BGR）
        4. 转换为Tkinter可用的PhotoImage
        5. 在预览画布上居中显示图像（始终居中，无论大小）
        6. 更新画布滚动区域
        7. 绘制已保存的ROI框
        
        注意：设置original_image后，视频循环会自动跳过刷新
        """
        pass  # print removed
        if self.original_image is None:
            return
        
        pass  # print removed
        # 确保主窗口的视频循环已停止（关键修复：防止视频循环清空画布）
        if self.main_window and hasattr(self.main_window, 'video_loop_running'):
            if self.main_window.video_loop_running:
                self.main_window.video_loop_running = False
                pass  # print removed
        # 使用preview_canvas显示图像
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        
        pass  # print removed
        # 1. 清空画布（删除图像和已保存的ROI框，保留temp_rect标签的临时框）
        # 注意：不要使用delete("all")，否则会删除临时框
        display_canvas.delete("captured_img")  # SolutionMakerFrame内部创建的图像
        display_canvas.delete("captured_image")  # ToolSidebarFrame创建的图像（关键修复）
        display_canvas.delete("video_frame")  # 视频循环创建的图像（关键修复）
        display_canvas.delete("saved_roi_visual")
        
        pass  # print removed
        # 强制更新画布尺寸
        display_canvas.update_idletasks()
        
        # 获取画布尺寸
        cw = display_canvas.winfo_width()
        ch = display_canvas.winfo_height()
        
        pass  # print removed
        # 检查画布尺寸是否有效
        if cw <= 1 or ch <= 1:
            # 画布尺寸无效，延迟后重试
            self.after(100, self._refresh_canvas_image)
            return
        
        # 2. 根据缩放比例调整图像大小
        h, w = self.original_image.shape[:2]
        
        # 使用当前的zoom_scale（已经通过_get_90_percent_scale或其他方法计算好）
        scale = self.zoom_scale
        
        pass  # print removed
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        # 确保尺寸至少为1像素
        new_w = max(1, new_w)
        new_h = max(1, new_h)
        
        pass  # print removed
        img_resized = cv2.resize(
            self.original_image,
            (new_w, new_h),
            interpolation=cv2.INTER_LINEAR
        )
        
        pass  # print removed
        # 3. 转换为RGB格式
        # 检查图像是灰度还是彩色
        if len(img_resized.shape) == 2:
            # 灰度图，转换为RGB
            img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_GRAY2RGB)
        else:
            # 彩色图，BGR转RGB
            img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        
        pass  # print removed
        # 4. 转换为Tkinter可用的PhotoImage
        pil_image = Image.fromarray(img_rgb)
        self.tk_image = ImageTk.PhotoImage(pil_image)
        
        pass  # print removed
        # 5. 在预览画布上居中显示图像（始终居中，无论大小）
        cx, cy = cw//2, ch//2

        # 保存图像偏移量，供右键坐标计算使用
        self._img_offset_x = cx - new_w // 2
        self._img_offset_y = cy - new_h // 2
        
        # 添加白色边框效果（使用标签以便删除）
        display_canvas.create_rectangle(
            cx-new_w//2-10, cy-new_h//2-10,
            cx+new_w//2+10, cy+new_h//2+10,
            fill="white", outline="",
            tags="captured_img"
        )
        
        # 绘制图像（居中显示）
        display_canvas.create_image(
            cx, cy,
            image=self.tk_image,
            tags="captured_img"
        )
        
        pass  # print removed
        # 6. 更新画布滚动区域
        if new_w > cw or new_h > ch:
            # 图像大于画布，设置滚动区域
            scroll_left = cx - new_w//2
            scroll_top = cy - new_h//2
            scroll_right = cx + new_w//2
            scroll_bottom = cy + new_h//2
            
            display_canvas.config(scrollregion=(scroll_left, scroll_top, scroll_right, scroll_bottom))
            
            # 滚动到中心位置（捕获的图像不会自动刷新，所以每次都居中）
            display_canvas.xview_moveto(0.5 - (cw / (2 * new_w)))
            display_canvas.yview_moveto(0.5 - (ch / (2 * new_h)))
        else:
            # 图像较小，重置滚动区域
            display_canvas.config(scrollregion=(0, 0, cw, ch))
        
        # 7. 绘制已保存的ROI框（需要调整坐标以适应居中显示）
        self._draw_saved_rois_centered(cx, cy, new_w, new_h)

        # 8. 把用户绘制的临时框（temp_rect）提升到最顶层，防止被图片遮住
        display_canvas.tag_raise("temp_rect")
    def _draw_saved_rois(self):
        """
        绘制已保存的ROI框（左上角对齐模式，已废弃）
        
        在画布上绘制所有已保存的ROI区域，
        用不同颜色区分不同字段类型
        """
        # 使用preview_canvas显示ROI框
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        
        # 删除旧的ROI标记
        display_canvas.delete("saved_roi_visual")
        
        # 如果没有保存的ROI配置，直接返回
        if not self.roi_layout_config:
            return
        
        # 遍历所有已保存的ROI
        for field, data in self.roi_layout_config.items():
            # 兼容两种数据格式：
            # 1. 字典格式（新版，包含锚点信息）
            # 2. 列表格式（旧版，直接是坐标）
            if isinstance(data, dict):
                # 优先显示用户框选的大框（search_area）
                coords = data.get("search_area", data.get("roi"))
                is_anchor = data.get("is_anchor", False)
            else:
                coords = data
                is_anchor = False
            
            # 验证坐标有效性
            if not coords or len(coords) != 4:
                continue
            
            # 获取坐标（原始图像坐标）
            x, y, w, h = coords
            
            # 获取字段颜色
            color = self.color_map.get(field, "#000000")
            
            # 转换为画布坐标（考虑缩放）
            sx = x * self.zoom_scale
            sy = y * self.zoom_scale
            sw = w * self.zoom_scale
            sh = h * self.zoom_scale
            
            # 特殊显示锚点（更粗的线条，实线）
            line_width = 3 if is_anchor or field == "FirstDigitAnchor" else 2
            dash = None if is_anchor or field == "FirstDigitAnchor" else (4, 4)
            tag_text = f"★ {field}" if is_anchor else f"[布局] {field}"
            
            # 绘制矩形框
            display_canvas.create_rectangle(
                sx, sy, sx + sw, sy + sh,
                outline=color,
                width=line_width,
                dash=dash,
                tags="saved_roi_visual"
            )
            
            # 绘制标签文本
            display_canvas.create_text(
                sx, sy - 15,
                text=tag_text,
                fill=color,
                anchor="sw",
                font=("Arial", 9, "bold"),
                tags="saved_roi_visual"
            )
        
        pass

    def _on_roi_right_click(self, event):
        """右键点击画布，检测是否点中某个 ROI 框，弹出属性菜单"""
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        cx = display_canvas.canvasx(event.x)
        cy = display_canvas.canvasy(event.y)

        offset_x = getattr(self, '_img_offset_x', 0)
        offset_y = getattr(self, '_img_offset_y', 0)

        hit_field = None

        # 先检查临时框（temp_rects）
        for rect in self.temp_rects:
            ft = rect['field_type']
            if ft == "FirstDigitAnchor":
                continue
            x1 = min(rect['start'][0], rect['end'][0])
            y1 = min(rect['start'][1], rect['end'][1])
            x2 = max(rect['start'][0], rect['end'][0])
            y2 = max(rect['start'][1], rect['end'][1])
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                hit_field = ft
                break

        # 再检查已保存的 roi_layout_config
        if hit_field is None:
            for field, data in self.roi_layout_config.items():
                if field == "FirstDigitAnchor":
                    continue
                if isinstance(data, dict):
                    coords = data.get("search_area", data.get("roi"))
                else:
                    coords = data
                if not coords or len(coords) != 4:
                    continue
                x, y, w, h = coords
                sx = offset_x + x * self.zoom_scale
                sy = offset_y + y * self.zoom_scale
                sw = w * self.zoom_scale
                sh = h * self.zoom_scale
                if sx <= cx <= sx + sw and sy <= cy <= sy + sh:
                    hit_field = field
                    break

        if hit_field:
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label=f"字段属性：{hit_field}",
                             command=lambda f=hit_field, e=event: self._show_field_props_dialog(f, e.x_root, e.y_root))
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

    def _show_field_props_dialog(self, field_name, x_root=None, y_root=None):
        """弹出字段属性设置对话框（方案一：精简版）"""
        # 优先从临时属性读取，其次从 roi_layout_config 读取
        field_props = self._pending_field_props.get(field_name) or \
                      (self.roi_layout_config.get(field_name, {}).get("field_props", {})
                       if isinstance(self.roi_layout_config.get(field_name), dict) else {})

        dlg = tk.Toplevel(self)
        dlg.title(f"字段属性 - {field_name}")
        dlg.resizable(False, False)
        dlg.grab_set()

        # 定位到右键点击位置附近
        dlg.update_idletasks()
        if x_root is not None and y_root is not None:
            dlg.geometry(f"+{x_root + 10}+{y_root + 10}")
        else:
            # 默认居中于画布
            display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
            rx = display_canvas.winfo_rootx() + display_canvas.winfo_width() // 2
            ry = display_canvas.winfo_rooty() + display_canvas.winfo_height() // 2
            dlg.geometry(f"+{rx}+{ry}")

        bg = "white"
        dlg.configure(bg=bg)
        pad = dict(padx=12, pady=6)

        # 字段名（只读）
        tk.Label(dlg, text="字段名称:", bg=bg, font=("微软雅黑", 9)).grid(row=0, column=0, sticky="w", **pad)
        tk.Label(dlg, text=field_name, bg=bg, font=("微软雅黑", 9, "bold"), fg="#0055A4").grid(row=0, column=1, sticky="w", **pad)

        # 启用/禁用
        var_enabled = tk.BooleanVar(value=field_props.get("enabled", True))
        tk.Label(dlg, text="启用识别:", bg=bg, font=("微软雅黑", 9)).grid(row=1, column=0, sticky="w", **pad)
        tk.Checkbutton(dlg, variable=var_enabled, bg=bg, activebackground=bg).grid(row=1, column=1, sticky="w", **pad)

        # 最小置信度阈值
        var_conf = tk.StringVar(value=str(int(field_props.get("min_confidence", 75))))
        tk.Label(dlg, text="最小置信度 (0-100):", bg=bg, font=("微软雅黑", 9)).grid(row=2, column=0, sticky="w", **pad)
        conf_frame = tk.Frame(dlg, bg=bg)
        conf_frame.grid(row=2, column=1, sticky="w", **pad)
        tk.Scale(conf_frame, from_=0, to=100, orient=tk.HORIZONTAL, variable=var_conf,
                 length=150, showvalue=False
                 ).pack(side=tk.LEFT)
        tk.Entry(conf_frame, textvariable=var_conf, width=4,
                 font=("微软雅黑", 9), justify="center"
                 ).pack(side=tk.LEFT, padx=(4, 0))

        # 期望字符数
        var_char_count = tk.StringVar(value=str(field_props.get("expected_chars", 0)))
        tk.Label(dlg, text="期望字符数 (0=不限):", bg=bg, font=("微软雅黑", 9)).grid(row=3, column=0, sticky="w", **pad)
        tk.Entry(dlg, textvariable=var_char_count, width=6, font=("微软雅黑", 9)).grid(row=3, column=1, sticky="w", **pad)

        # 忽略空格
        var_ignore_space = tk.BooleanVar(value=field_props.get("ignore_space", False))
        tk.Label(dlg, text="忽略空格:", bg=bg, font=("微软雅黑", 9)).grid(row=4, column=0, sticky="w", **pad)
        tk.Checkbutton(dlg, variable=var_ignore_space, bg=bg, activebackground=bg).grid(row=4, column=1, sticky="w", **pad)

        # 分隔线
        tk.Frame(dlg, bg="#E0E0E0", height=1).grid(row=5, column=0, columnspan=2, sticky="ew", padx=12, pady=4)

        def on_save():
            try:
                conf_val = int(float(var_conf.get()))
                char_count = int(var_char_count.get())
            except ValueError:
                messagebox.showwarning("输入错误", "置信度和字符数必须为整数", parent=dlg)
                return
            conf_val = max(0, min(100, conf_val))
            char_count = max(0, char_count)

            new_props = {
                "enabled": var_enabled.get(),
                "min_confidence": conf_val,
                "expected_chars": char_count,
                "ignore_space": var_ignore_space.get()
            }
            # 只写入临时属性字典，不动 roi_layout_config（点"保存全部"时才合并）
            self._pending_field_props[field_name] = new_props
            # 标记该字段为"已修改未保存"，刷新画布让标签变回临时状态
            if field_name in self.roi_layout_config:
                if isinstance(self.roi_layout_config[field_name], dict):
                    self.roi_layout_config[field_name]['_modified'] = True
            self._refresh_canvas_image()
            dlg.destroy()

        btn_frame = tk.Frame(dlg, bg=bg)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=(0, 10))
        tk.Button(btn_frame, text="确定", font=("微软雅黑", 9), bg="#F0F0F0",
                  relief=tk.RAISED, padx=20, pady=3, cursor="hand2",
                  command=on_save).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="取消", font=("微软雅黑", 9), bg="#F0F0F0",
                  relief=tk.RAISED, padx=20, pady=3, cursor="hand2",
                  command=dlg.destroy).pack(side=tk.LEFT, padx=8)

    def _draw_saved_rois_centered(self, cx, cy, img_w, img_h):
        """
        绘制已保存的ROI框（居中显示模式）
        
        在画布上绘制所有已保存的ROI区域和临时ROI区域，
        用不同颜色区分不同字段类型，用线条样式区分已保存和临时
        
        参数:
            cx, cy: 图像中心点在画布上的坐标
            img_w, img_h: 缩放后的图像尺寸
        """
        # 使用preview_canvas显示ROI框
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        
        # 删除旧的ROI标记
        display_canvas.delete("saved_roi_visual")
        display_canvas.delete("temp_roi_visual")
        
        # 计算图像左上角在画布上的位置
        img_left = cx - img_w // 2
        img_top = cy - img_h // 2
        
        # 1. 绘制已保存的ROI（实线）
        if self.roi_layout_config:
            
            for field, data in self.roi_layout_config.items():
                # 兼容两种数据格式
                if isinstance(data, dict):
                    coords = data.get("search_area", data.get("roi"))
                    is_anchor = data.get("is_anchor", False)
                else:
                    coords = data
                    is_anchor = False
                
                # 验证坐标有效性
                if not coords or len(coords) != 4:
                    continue
                
                # 获取坐标（原始图像坐标）
                x, y, w, h = coords
                
                # 获取字段颜色
                color = self.color_map.get(field, "#000000")
                
                # 转换为画布坐标（考虑缩放和居中偏移）
                sx = img_left + x * self.zoom_scale
                sy = img_top + y * self.zoom_scale
                sw = w * self.zoom_scale
                sh = h * self.zoom_scale
                
                # 已保存的布局：实线，较细；若属性被修改则显示为临时
                is_modified = isinstance(data, dict) and data.get('_modified', False)
                line_width = 3 if is_anchor or field == "FirstDigitAnchor" else 2
                dash = (4, 4) if is_modified else None
                if is_anchor:
                    tag_text = f"★ {field}"
                elif is_modified:
                    tag_text = f"[临时] {field}"
                else:
                    tag_text = f"[已保存] {field}"
                
                # 绘制矩形框
                display_canvas.create_rectangle(
                    sx, sy, sx + sw, sy + sh,
                    outline=color,
                    width=line_width,
                    dash=dash,
                    tags="saved_roi_visual"
                )
                
                # 绘制标签文本
                display_canvas.create_text(
                    sx, sy - 15,
                    text=tag_text,
                    fill=color,
                    anchor="sw",
                    font=("Arial", 9, "bold"),
                    tags="saved_roi_visual"
                )
            
            pass
        
        # 2. 绘制临时ROI（虚线，更粗）
        if self.temp_layout_config:
            
            for field, data in self.temp_layout_config.items():
                # 兼容两种数据格式
                if isinstance(data, dict):
                    coords = data.get("search_area", data.get("roi"))
                    is_anchor = data.get("is_anchor", False)
                else:
                    coords = data
                    is_anchor = False
                
                # 验证坐标有效性
                if not coords or len(coords) != 4:
                    continue
                
                # 获取坐标（原始图像坐标）
                x, y, w, h = coords
                
                # 获取字段颜色（临时布局使用更亮的颜色）
                color = self.color_map.get(field, "#ff0000")
                
                # 转换为画布坐标（考虑缩放和居中偏移）
                sx = img_left + x * self.zoom_scale
                sy = img_top + y * self.zoom_scale
                sw = w * self.zoom_scale
                sh = h * self.zoom_scale
                
                # 临时布局：虚线，较粗
                line_width = 4 if is_anchor or field == "FirstDigitAnchor" else 3
                dash = (8, 4)  # 虚线
                tag_text = f"★ [临时] {field}" if is_anchor else f"[临时] {field}"
                
                # 绘制矩形框
                display_canvas.create_rectangle(
                    sx, sy, sx + sw, sy + sh,
                    outline=color,
                    width=line_width,
                    dash=dash,
                    tags="temp_roi_visual"
                )
                
                # 绘制标签文本
                display_canvas.create_text(
                    sx, sy - 30,  # 临时标签显示在更上方，避免与已保存标签重叠
                    text=tag_text,
                    fill=color,
                    anchor="sw",
                    font=("Arial", 9, "bold"),
                    tags="temp_roi_visual"
                )
            
            pass
    
    # ====================================================================
    # 画布交互方法 (Task 6)
    # ====================================================================
    
    def _bind_canvas_events(self):
        """绑定画布事件（激活时）"""
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        display_canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        display_canvas.bind("<B1-Motion>", self.on_mouse_drag)
        display_canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        display_canvas.bind("<Control-MouseWheel>", self.on_zoom)
        display_canvas.bind("<Configure>", self._on_canvas_resize)
        display_canvas.bind("<ButtonPress-3>", self._on_roi_right_click)
    def _on_canvas_resize(self, event):
        """
        画布大小改变事件处理
        
        当用户拖动分割线改变画布大小时，自动重新计算缩放比例并重绘图像
        """
        # 只有当有图像时才处理
        if self.original_image is None:
            return
        
        # 确保主窗口的视频循环已停止（关键修复：防止视频循环清空画布）
        if self.main_window and hasattr(self.main_window, 'video_loop_running'):
            if self.main_window.video_loop_running:
                self.main_window.video_loop_running = False
                pass  # print removed
        # 取消之前的定时器（如果有）
        if hasattr(self, '_resize_timer'):
            self.after_cancel(self._resize_timer)
        
        # 立即删除所有旧图像，避免重影
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        display_canvas.delete("captured_img")
        display_canvas.delete("captured_image")
        display_canvas.delete("video_frame")  # 视频循环创建的图像
        display_canvas.delete("saved_roi_visual")
        
        # 延迟100ms后再重绘（缩短延迟时间，提高响应速度）
        # 这样可以避免拖动过程中频繁重绘导致的重影问题
        self._resize_timer = self.after(100, self._do_canvas_resize)
    
    def _do_canvas_resize(self):
        """
        实际执行画布大小改变后的重绘操作
        """
        if self.original_image is None:
            return
        
        # 重新计算缩放比例（保持90%画布大小）
        new_scale = self._get_90_percent_scale()
        
        # 如果缩放比例变化超过1%，才重新绘制（避免频繁刷新）
        if abs(new_scale - self.zoom_scale) / self.zoom_scale > 0.01:
            self.zoom_scale = new_scale
            pass  # print removed
            # 重新绘制图像
            self._refresh_canvas_image()
    
    def _unbind_canvas_events(self):
        """解绑画布事件（返回主菜单时）"""
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        display_canvas.unbind("<ButtonPress-1>")
        display_canvas.unbind("<B1-Motion>")
        display_canvas.unbind("<ButtonRelease-1>")
        display_canvas.unbind("<Control-MouseWheel>")
        display_canvas.unbind("<Configure>")  # 解绑画布大小改变事件
        pass  # print removed
    @ErrorHandler.handle_ui_error
    def on_mouse_down(self, event):
        """
        鼠标按下事件
        
        开始框选ROI区域（支持连续框选多个区域）
        """
        # 检查是否有图像
        if self.original_image is None:
            return
        
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        
        # 记录起始点（画布坐标）
        self.rect_start = (event.x, event.y)
        self.rect_end = None
        
        # 删除当前正在绘制的临时矩形（如果有）
        if self.current_rect_id:
            display_canvas.delete(self.current_rect_id)
            self.current_rect_id = None
    
    @ErrorHandler.handle_ui_error
    def on_mouse_drag(self, event):
        """
        鼠标拖动事件
        
        实时显示框选矩形
        """
        # 检查是否有起始点
        if self.rect_start is None:
            return
        
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        
        # 更新结束点
        self.rect_end = (event.x, event.y)
        
        # 删除旧的临时矩形
        if self.current_rect_id:
            display_canvas.delete(self.current_rect_id)
        
        # 获取当前字段类型的颜色
        current_type = self.var_field_type.get()
        color = self.color_map.get(current_type, "#000000")
        
        # 绘制新的临时矩形
        self.current_rect_id = display_canvas.create_rectangle(
            self.rect_start[0], self.rect_start[1],
            self.rect_end[0], self.rect_end[1],
            outline=color,
            width=2,
            dash=(4, 4),
            tags="temp_rect"
        )
    
    @ErrorHandler.handle_ui_error
    def on_mouse_up(self, event):
        """
        鼠标释放事件
        
        完成框选，保留临时框直到用户执行提取
        每个字段只能画一个框
        """
        # 检查是否有起始点
        if self.rect_start is None:
            return
        
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        
        # 更新结束点
        self.rect_end = (event.x, event.y)
        
        # 验证框选区域是否有效（至少10x10像素）
        dx = abs(self.rect_end[0] - self.rect_start[0])
        dy = abs(self.rect_end[1] - self.rect_start[1])
        
        if dx < 10 or dy < 10:
            # 删除太小的框
            if self.current_rect_id:
                display_canvas.delete(self.current_rect_id)
                self.current_rect_id = None
            self.rect_start = None
            self.rect_end = None
            return
        
        # 获取当前字段类型
        current_type = self.var_field_type.get()
        
        # 检查该字段是否已经有框了
        existing_rect = None
        for i, rect in enumerate(self.temp_rects):
            if rect['field_type'] == current_type:
                existing_rect = i
                break
        
        # 如果该字段已经有框，删除旧框
        if existing_rect is not None:
            old_rect = self.temp_rects[existing_rect]
            # 删除旧框的 canvas 对象
            if old_rect['canvas_id']:
                display_canvas.delete(old_rect['canvas_id'])
            # 从列表中移除
            self.temp_rects.pop(existing_rect)
        
        # 保留临时矩形，不删除！让用户看到框选结果
        # 将临时框转换为实线显示，表示框选完成
        if self.current_rect_id:
            display_canvas.delete(self.current_rect_id)
            
            # 获取当前字段类型的颜色
            color = self.color_map.get(current_type, "#000000")
            
            # 重新绘制为实线框
            self.current_rect_id = display_canvas.create_rectangle(
                self.rect_start[0], self.rect_start[1],
                self.rect_end[0], self.rect_end[1],
                outline=color,
                width=2,
                tags="temp_rect"
            )
            
            # 将这个框添加到临时框列表中
            self.temp_rects.append({
                'start': self.rect_start,
                'end': self.rect_end,
                'canvas_id': self.current_rect_id,
                'field_type': current_type
            })
            
            pass
        
        # 重置当前框选状态，准备下一次框选
        self.rect_start = None
        self.rect_end = None
        self.current_rect_id = None

        # 框选完成后，若该字段还没有临时属性，初始化默认值（不写入 roi_layout_config）
        if current_type and current_type != "FirstDigitAnchor":
            if current_type not in self._pending_field_props:
                self._pending_field_props[current_type] = {
                    "enabled": True,
                    "min_confidence": 75,
                    "expected_chars": 0,
                    "ignore_space": False
                }
    
    def on_zoom(self, event):
        """
        缩放控制
        
        使用 Ctrl + 鼠标滚轮缩放图像
        """
        # 检查是否有图像
        if self.original_image is None:
            return
        
        # 获取滚轮方向（正数=向上滚动=放大，负数=向下滚动=缩小）
        delta = event.delta
        
        # 计算缩放因子
        if delta > 0:
            scale_factor = 1.1  # 放大10%
        else:
            scale_factor = 0.9  # 缩小10%
        
        # 更新缩放比例
        new_scale = self.zoom_scale * scale_factor
        
        # 限制缩放范围（0.1 ~ 5.0）
        new_scale = max(0.1, min(5.0, new_scale))
        
        # 如果缩放比例没有变化，直接返回
        if abs(new_scale - self.zoom_scale) < 0.001:
            return
        
        self.zoom_scale = new_scale
        
        # 刷新画布
        self._refresh_canvas_image()
        
        pass  # print removed
    def process_selection(self):
        """
        处理ROI选择（核心逻辑）
        
        流程:
        1. 获取所有用户框选的坐标
        2. 判断字段类型（锚点 vs 常规字段）
        3. 锚点特殊处理：检测墨迹位置，保存双重坐标
        4. 常规字段处理：提取字符，添加到网格
        """
        pass  # print removed
        pass  # print removed
        # print(f"   temp_rects数量: {len(self.temp_rects)}")
        pass  # print removed
        pass  # print removed
        pass  # print removed
        # print(f"   section_frames keys: {list(self.section_frames.keys())}")
        pass  # print removed
        # 检查是否有框选
        if not self.temp_rects:
            messagebox.showwarning("警告", "请先框选ROI区域！")
            return
        
        # 检查是否有图像
        if self.original_image is None:
            messagebox.showwarning("警告", "请先加载图像！")
            return
        
        # 检查是否选择了方案
        if not self.current_solution_name:
            messagebox.showwarning("警告", "请先选择或创建方案！")
            return
        
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        
        # 获取工作模式
        mode = self.var_work_mode.get()
        
        # 获取画布尺寸和图像位置信息（用于坐标转换）
        cw = display_canvas.winfo_width()
        ch = display_canvas.winfo_height()
        h, w = self.original_image.shape[:2]
        
        # 计算缩放后的图像尺寸
        new_w = int(w * self.zoom_scale)
        new_h = int(h * self.zoom_scale)
        
        # 计算图像中心点和左上角位置（与_refresh_canvas_image中的计算一致）
        cx, cy = cw // 2, ch // 2
        img_left = cx - new_w // 2
        img_top = cy - new_h // 2
        
        pass
        pass
        # 处理所有临时框
        processed_count = 0
        for rect_info in self.temp_rects:
            rect_start = rect_info['start']
            rect_end = rect_info['end']
            field_type = rect_info['field_type']
            canvas_id = rect_info['canvas_id']
            
            # 转换为原始图像坐标（先减去图像偏移，再除以缩放比例）
            x1 = (rect_start[0] - img_left) / self.zoom_scale
            y1 = (rect_start[1] - img_top) / self.zoom_scale
            x2 = (rect_end[0] - img_left) / self.zoom_scale
            y2 = (rect_end[1] - img_top) / self.zoom_scale
            
            x_start, x_end = sorted([int(x1), int(x2)])
            y_start, y_end = sorted([int(y1), int(y2)])
            
            # 边界检查
            h_img, w_img = self.original_image.shape[:2]
            x_start = max(0, x_start)
            y_start = max(0, y_start)
            x_end = min(w_img, x_end)
            y_end = min(h_img, y_end)
            
            # 验证框选区域大小
            if (x_end - x_start) < 5 or (y_end - y_start) < 5:
                continue
            
            # 用户的原始框（用于识别端的搜索范围）
            user_search_roi = [x_start, y_start, x_end - x_start, y_end - y_start]
            
            # 默认基准点也是这个框（如果没有找到墨迹）
            final_ref_roi = user_search_roi
            
            # 判断是否为锚点字段
            is_anchor_field = (field_type == "FirstDigitAnchor")
            
            # 锚点特殊处理
            if is_anchor_field:
                final_ref_roi = self._detect_anchor_ink(x_start, y_start, x_end, y_end)
                
                # 保存双重坐标到临时布局
                layout_data = {
                    "roi": final_ref_roi,
                    "search_area": user_search_roi,
                    "is_anchor": True
                }
                self.temp_layout_config[field_type] = layout_data
                
                pass  # print removed
                processed_count += 1
                continue
            
            # 根据工作模式决定是否保存布局
            if mode in ["Full Mode", "Layout Only"]:
                # 保存常规字段的ROI到临时布局（非锚点）
                layout_data = {
                    "roi": user_search_roi,
                    "search_area": user_search_roi,
                    "is_anchor": False
                }
                self.temp_layout_config[field_type] = layout_data
                pass  # print removed
            # 如果是仅布局模式，不提取字符，直接跳过
            if mode == "Layout Only":
                pass  # print removed
                processed_count += 1
                continue
            
            # 提取字符（Full Mode 或 Template Only）
            if mode in ["Full Mode", "Template Only"]:
                chars = self._extract_characters(x_start, y_start, x_end, y_end)
                
                if chars:
                    for char_img in chars:
                        self._add_char_grid_item(char_img, field_type, is_new=True)
                    
                    processed_count += 1
                else:
                    pass
        
        # 删除所有临时框
        for rect_info in self.temp_rects:
            canvas_id = rect_info['canvas_id']
            if canvas_id:
                display_canvas.delete(canvas_id)
        
        # 清空临时框列表
        self.temp_rects = []
        
        # 清除当前框选状态
        self.rect_start = None
        self.rect_end = None
        self.current_rect_id = None
        
        # 刷新画布显示ROI框
        self._refresh_canvas_image()
        
        # 刷新网格布局
        if mode in ["Full Mode", "Template Only"]:
            self._reflow_grid()
        
        # 显示处理结果
        if processed_count > 0:
            messagebox.showinfo("成功", f"成功处理 {processed_count} 个字段！")
        else:
            messagebox.showwarning("提示", "没有成功处理任何字段")

        # 将 temp_layout_config 合并到 roi_layout_config，使右键能命中已提取的字段框
        for field, layout_data in self.temp_layout_config.items():
            existing = self.roi_layout_config.get(field, {})
            existing_props = existing.get("field_props", {}) if isinstance(existing, dict) else \
                             self._pending_field_props.get(field, {})
            merged = dict(layout_data)
            merged["field_props"] = existing_props
            self.roi_layout_config[field] = merged
    
    def _get_roi_coords(self):
        """
        获取ROI坐标
        
        返回:
            tuple: (x_start, y_start, x_end, y_end) 原始图像坐标
        """
        if not self.rect_start or not self.rect_end:
            return None
        
        # 转换为原始图像坐标
        x1 = int(self.rect_start[0] / self.zoom_scale)
        y1 = int(self.rect_start[1] / self.zoom_scale)
        x2 = int(self.rect_end[0] / self.zoom_scale)
        y2 = int(self.rect_end[1] / self.zoom_scale)
        
        # 排序确保 start < end
        x_start, x_end = sorted([x1, x2])
        y_start, y_end = sorted([y1, y2])
        
        # 边界检查
        if self.original_image is not None:
            h_img, w_img = self.original_image.shape[:2]
            x_start = max(0, x_start)
            y_start = max(0, y_start)
            x_end = min(w_img, x_end)
            y_end = min(h_img, y_end)
        
        return (x_start, y_start, x_end, y_end)
    
    def _detect_anchor_ink(self, x_start, y_start, x_end, y_end):
        """
        检测锚点墨迹位置
        
        在用户框选的大框内，精确定位首字符的墨迹位置
        
        参数:
            x_start, y_start, x_end, y_end: 用户框选的区域坐标
        
        返回:
            list: [x, y, w, h] 墨迹的精确位置
        """
        # 提取ROI区域
        roi_img = self.original_image[y_start:y_end, x_start:x_end]
        
        # 转换为灰度图
        if len(roi_img.shape) == 3:
            gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = roi_img
        
        # 二值化
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        
        # 形态学处理（轻微腐蚀，去除噪点）
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 3))
        eroded = cv2.erode(binary, kernel, iterations=1)
        
        # 轮廓检测
        cnts, _ = cv2.findContours(eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # 筛选有效的墨迹
        valid_blobs = []
        for c in cnts:
            bx, by, bw, bh = cv2.boundingRect(c)
            
            # 过滤太小的噪点
            if bh < 6:
                continue
            if bw * bh < 20:
                continue
            
            valid_blobs.append((bx, by, bw, bh))
        
        # 如果找到墨迹，返回最左边的一个
        if valid_blobs:
            # 按X坐标排序，取最左边的
            valid_blobs.sort(key=lambda b: b[0])
            ink_x, ink_y, ink_w, ink_h = valid_blobs[0]
            
            # 计算墨迹的绝对坐标
            true_abs_x = x_start + ink_x
            true_abs_y = y_start + ink_y
            
            return [true_abs_x, true_abs_y, ink_w, ink_h]
        else:
            # 未找到墨迹，返回用户框选的区域
            messagebox.showwarning(
                "警告",
                "框内未检测到清晰字符！\n基准点将默认使用整个搜索框。"
            )
            return [x_start, y_start, x_end - x_start, y_end - y_start]
    
    def _extract_characters(self, x_start, y_start, x_end, y_end):
        """
        提取字符（保持原算法）
        
        参数:
            x_start, y_start, x_end, y_end: ROI区域坐标
        
        返回:
            list: 归一化后的字符图像列表
        """
        # 提取ROI区域
        roi = self.original_image[y_start:y_end, x_start:x_end]
        
        # 性能统计
        t_start = time.perf_counter()
        
        # 添加边界填充（避免边缘字符被截断）
        padding = 10
        roi_padded = cv2.copyMakeBorder(
            roi, padding, padding, padding, padding,
            cv2.BORDER_CONSTANT, value=(0, 0, 0)
        )
        
        # 转换为灰度图（检查通道数）
        if len(roi_padded.shape) == 3:
            # 彩色图像，转换为灰度
            gray = cv2.cvtColor(roi_padded, cv2.COLOR_BGR2GRAY)
        else:
            # 已经是灰度图，直接使用
            gray = roi_padded
        
        # CLAHE增强对比度
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        
        # 二值化（用于轮廓检测）
        _, binary_detect_raw = cv2.threshold(
            enhanced, 0, 255,
            cv2.THRESH_BINARY | cv2.THRESH_OTSU
        )
        
        # 形态学闭运算（连接断裂的字符）
        binary_detect = cv2.morphologyEx(
            binary_detect_raw,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (2, 3))
        )
        
        # 膨胀（增强字符边界）
        binary_detect = cv2.dilate(
            binary_detect,
            cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2)),
            iterations=1
        )
        
        # 反转图像（用于模板保存）
        img_inverted = 255 - gray
        img_template_gray = clahe.apply(img_inverted)
        _, binary_template = cv2.threshold(
            img_template_gray, 0, 255,
            cv2.THRESH_BINARY | cv2.THRESH_OTSU
        )
        
        t_end = time.perf_counter()
        cost_ms = (t_end - t_start) * 1000
        pass  # print removed
        # 显示调试图像（如果启用）
        if self.var_show_debug.get():
            debug_images = {
                "1. 原始区域": roi,
                "2. 灰度化": gray,
                "4. 定位二值化": binary_detect,
                "7. 最终模板": binary_template
            }
            self._display_debug_images(debug_images)
        
        # 轮廓检测
        cnts, _ = cv2.findContours(
            binary_detect,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )
        
        # 筛选候选字符
        current_type = self.var_field_type.get()
        candidates = []
        heights = []
        
        for c in cnts:
            (x, y, w, h) = cv2.boundingRect(c)
            
            # 最小高度阈值（Name字段更宽松）
            min_h = 4 if current_type == "Name" else 8
            if h < min_h or w < 3:
                continue
            
            # 过滤宽高比异常的（可能是横线）
            if w / h > 4.0:
                continue
            
            candidates.append((x, y, w, h))
            heights.append(h)
        
        if not candidates:
            return []
        
        # 高度过滤（去除异常大小的噪点）
        if len(candidates) <= 2:
            valid_chars = candidates
        else:
            median_h = np.median(heights)
            valid_chars = []
            
            for (x, y, w, h) in candidates:
                # 特殊处理：Name字段的点号
                is_dot = (current_type == "Name" and h > 3 and 0.5 < w/float(h) < 2.0)
                
                if not is_dot and h < median_h * 0.5:
                    continue
                if h > median_h * 1.8:
                    continue
                
                valid_chars.append((x, y, w, h))
        
        # 多行字符排序
        valid_chars = self._filter_and_sort_chars(valid_chars)
        
        # 提取并归一化字符
        normalized_chars = []
        for (x, y, w, h) in valid_chars:
            char_roi = binary_template[y:y+h, x:x+w]
            char_roi_resized = resize_with_padding(
                char_roi,
                (self.norm_width, self.norm_height)
            )
            normalized_chars.append(char_roi_resized)
        
        return normalized_chars
    
    def _filter_and_sort_chars(self, chars_data):
        """
        筛选和排序字符
        
        参数:
            chars_data: 字符边界框列表 [(x, y, w, h), ...]
        
        返回:
            list: 排序后的字符边界框列表
        """
        # 直接调用多行排序
        return self.sort_multiline_chars(chars_data)
    
    def sort_multiline_chars(self, chars_data):
        """
        多行字符排序
        
        先按Y坐标分行，再按X坐标排序每一行
        
        参数:
            chars_data: 字符边界框列表 [(x, y, w, h), ...]
        
        返回:
            list: 排序后的字符边界框列表
        """
        if not chars_data:
            return []
        
        # 先按Y坐标排序
        chars_data.sort(key=lambda b: b[1])
        
        lines = []
        current_line = [chars_data[0]]
        
        # 初始化参考高度（第一个字符的高度）
        ref_h = chars_data[0][3]
        
        # 分行
        for i in range(1, len(chars_data)):
            curr = chars_data[i]
            prev = current_line[-1]
            
            # 如果Y坐标差距小于参考高度的60%，认为是同一行
            if abs(curr[1] - prev[1]) < ref_h * 0.6:
                current_line.append(curr)
            else:
                # 当前行结束，按X坐标排序
                current_line.sort(key=lambda b: b[0])
                lines.append(current_line)
                
                # 开始新行
                current_line = [curr]
                ref_h = curr[3]  # 更新参考高度
        
        # 处理最后一行
        current_line.sort(key=lambda b: b[0])
        lines.append(current_line)
        
        # 展平所有行
        return [item for sublist in lines for item in sublist]
    
    def _display_debug_images(self, step_images):
        """
        显示调试图像
        
        在新窗口中显示图像处理的中间步骤
        
        参数:
            step_images: 字典 {标题: 图像数组}
        """
        win = tk.Toplevel(self)
        win.title("算法处理步骤可视化 (中间过程)")
        win.geometry("900x600")
        
        canvas = tk.Canvas(win, bg="white")
        scrollbar = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="white")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        row = 0
        col = 0
        MAX_COLS = 3
        
        for title, img_array in step_images.items():
            frame = tk.LabelFrame(
                scrollable_frame,
                text=title,
                font=("Arial", 10, "bold"),
                bg="white",
                padx=5,
                pady=5
            )
            frame.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
            
            # 转换为RGB格式
            if len(img_array.shape) == 2:
                img_rgb = cv2.cvtColor(img_array, cv2.COLOR_GRAY2RGB)
            else:
                img_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
            
            # 放大小图像以便查看
            h, w = img_rgb.shape[:2]
            if w < 150:
                scale = 3.0
                img_rgb = cv2.resize(
                    img_rgb,
                    (int(w*scale), int(h*scale)),
                    interpolation=cv2.INTER_NEAREST
                )
            
            # 转换为Tkinter图像
            pil_img = Image.fromarray(img_rgb)
            tk_img = ImageTk.PhotoImage(pil_img)
            
            lbl = tk.Label(frame, image=tk_img, bg="white")
            lbl.image = tk_img  # 保持引用
            lbl.pack()
            
            col += 1
            if col >= MAX_COLS:
                col = 0
                row += 1
    
    # ====================================================================
    # 字符网格显示方法 (Task 8)
    # ====================================================================
    
    def _register_field(self, field_type, create_ui=True):
        """
        注册字段类型
        
        为新的字段类型创建UI区域和数据结构
        
        参数:
            field_type: 字段类型名称
            create_ui: 是否创建UI（默认True）
        """
        # 添加到字段类型列表
        if field_type not in self.field_types:
            self.field_types.append(field_type)

            # 动态添加单选按钮
            if hasattr(self, 'field_icon_frame') and self.field_icon_frame.winfo_exists():
                i = len(self.field_types) - 1  # 当前是最后一个
                rb = tk.Radiobutton(
                    self.field_icon_frame,
                    text=field_type,
                    variable=self.var_field_type,
                    value=field_type,
                    font=("微软雅黑", 10),
                    bg="white",
                    activebackground="white",
                    selectcolor="white",
                    cursor="hand2",
                    anchor="w",
                    command=lambda ft=field_type: self._select_field(ft)
                )
                rb.grid(row=i // 4, column=i % 4, sticky="w", padx=2, pady=2)
                self.field_buttons[field_type] = rb
                self.field_icon_frame.update_idletasks()

            # 分配颜色（随机生成）
            if field_type not in self.color_map:
                self.color_map[field_type] = "#{:06x}".format(random.randint(0, 0xFFFFFF))
        
        # 初始化字符widgets列表（即使不创建UI也要初始化数据结构）
        if field_type not in self.char_widgets:
            self.char_widgets[field_type] = {
                'existing': [],
                'new': []
            }
        
        # 创建UI区域（如果尚未创建）
        if create_ui and field_type not in self.section_frames:
            self._create_field_section(field_type)
        
        pass  # print removed
    def _add_char_grid_item(self, cv2_img, section_type, label_text="", is_new=False):
        """
        添加字符网格项
        
        参数:
            cv2_img: OpenCV图像（灰度图）
            section_type: 字段类型
            label_text: 字符标签（可选）
            is_new: 是否为新提取的字符
        """
        # 调试信息
        pass  # print removed
        # 确保字段类型已注册
        if section_type not in self.char_widgets:
            self._register_field(section_type, create_ui=True)
        
        # 检查section_frames是否存在
        if section_type not in self.section_frames:
            pass
            self._create_field_section(section_type)
            if section_type not in self.section_frames:
                return
        
        # 确定目标列表和父容器
        target_key = 'new' if is_new else 'existing'
        target_list = self.char_widgets[section_type][target_key]
        
        # 调试信息
        # print(f"   → target_key={target_key}, 当前列表长度={len(target_list)}")
        
        # 获取父容器
        if target_key == 'new':
            parent_frame = self.section_frames[section_type]['new_grid']
            # print(f"   → 使用new_grid作为父容器, ID={id(parent_frame)}, exists={parent_frame.winfo_exists()}")
            pass
        else:
            parent_frame = self.section_frames[section_type]['archived_grid']
            # print(f"   → 使用archived_grid作为父容器, ID={id(parent_frame)}, exists={parent_frame.winfo_exists()}")
        
        # 验证父容器
        if parent_frame is None:
            return
        
        if not parent_frame.winfo_exists():
            return
        
        pass  # print removed
        # 创建字符卡片
        bg_color = "white"
        item_data = {
            'image': cv2_img,
            'type': section_type,
            'is_new': is_new,
            'selected': False
        }
        
        # 创建卡片Frame
        frame = tk.Frame(
            parent_frame,
            bd=0,
            bg=bg_color,
            highlightthickness=2,
            highlightbackground="#d0d0d0",
            width=self.card_width,
            height=80
        )
        item_data['frame'] = frame
        
        # 删除按钮（右上角）
        btn_del = tk.Button(
            frame,
            text="×",
            bg=bg_color,
            fg="#999",
            activebackground="#ffcdd2",
            activeforeground="#ff1744",
            font=("Arial", 10),
            bd=0,
            relief=tk.FLAT,
            cursor="hand2",
            command=lambda: self.delete_single_char(item_data)
        )
        btn_del.place(relx=1.0, x=0, y=0, anchor="ne", width=20, height=20)
        
        # 添加点击事件
        def on_frame_click(event):
            # 切换选中状态
            item_data['selected'] = not item_data['selected']
            # 更新视觉反馈
            if item_data['selected']:
                frame.config(highlightbackground="#3498db", highlightcolor="#3498db")
                frame.config(bg="#e3f2fd")
                btn_del.config(bg="#e3f2fd")
            else:
                frame.config(highlightbackground="#d0d0d0", highlightcolor="#d0d0d0")
                frame.config(bg="white")
                btn_del.config(bg="white")
        
        # 右键菜单
        def show_context_menu(event):
            # 创建右键菜单
            context_menu = tk.Menu(self, tearoff=0)
            
            # 添加删除选中项菜单
            context_menu.add_command(
                label="删除选中的模板",
                command=self.batch_delete_selected_templates
            )
            
            # 显示菜单
            try:
                context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                context_menu.grab_release()
        
        # 绑定点击事件
        frame.bind("<Button-1>", on_frame_click)
        # 绑定右键事件
        frame.bind("<Button-3>", show_context_menu)
        # 确保点击事件不会被其他组件拦截
        frame.bind_all("<Button-1>", lambda e: None, add="+")
        
        # 字符图像
        img_pil = Image.fromarray(cv2_img)
        img_tk = ImageTk.PhotoImage(img_pil)
        lbl_img = tk.Label(frame, bg=bg_color, image=img_tk)
        lbl_img.image = img_tk  # 保持引用
        lbl_img.pack(side=tk.TOP, pady=(15, 2), padx=5)
        
        # 标签输入框
        entry = tk.Entry(
            frame,
            font=("Arial", 14, "bold"),
            width=3,
            justify="center",
            bd=1,
            relief=tk.SOLID,
            highlightthickness=0
        )
        entry.pack(side=tk.BOTTOM, pady=(0, 10))
        
        # 限制输入一个字符并自动跳转到下一个输入框
        def on_key_press(event):
            # 只允许输入一个字符
            current_text = entry.get()
            # 检查是否是删除键（Backspace 或 Delete）
            if event.keysym in ('BackSpace', 'Delete'):
                # 允许删除操作
                return
            if len(current_text) >= 1 and event.char:
                # 输入了第二个字符，阻止输入
                return "break"
            elif len(current_text) == 0 and event.char:
                # 输入了第一个字符，延迟一小段时间后自动跳转
                def auto_focus():
                    if len(entry.get()) == 1:
                        self._focus_next(entry, section_type, target_key)
                # 使用after确保字符已经输入
                entry.after(100, auto_focus)
        
        entry.bind("<KeyPress>", on_key_press)
        entry.bind("<Return>", lambda e: self._focus_next(entry, section_type, target_key))
        
        if label_text:
            entry.insert(0, label_text)
        
        item_data['entry'] = entry
        
        # 添加到列表
        target_list.append(item_data)
        
        # 注意: 不在这里调用_reflow_grid(),由调用者统一调用
        # 这样可以避免在批量加载时多次重新布局,提升性能
        # self._reflow_grid()
    
    def _reflow_grid(self, container_width=None):
        """
        响应式网格布局
        
        根据容器宽度自动调整列数
        
        参数:
            container_width: 容器宽度（可选，默认自动获取）
        """
        # 先隐藏所有section
        for section in self.field_types:
            if section in self.section_frames:
                container = self.section_frames[section]['container']
                if container.winfo_ismapped():
                    container.pack_forget()
        
        # 获取容器宽度
        if container_width is None:
            actual_width = None
            
            # 方法1: 尝试从第一个grid容器获取实际宽度
            for section in self.field_types:
                if section in self.section_frames:
                    grid_frame = self.section_frames[section]['archived_grid']
                    if grid_frame and grid_frame.winfo_exists():
                        grid_frame.update_idletasks()
                        grid_width = grid_frame.winfo_width()
                        if grid_width > 10:  # 确保是有效宽度
                            actual_width = grid_width
                            pass  # print removed
                            break
            
            # 方法2: 如果grid宽度无效，从Canvas获取并减去各种padding
            if actual_width is None or actual_width <= 10:
                if self.template_canvas_widget:
                    self.template_canvas_widget.update_idletasks()
                    canvas_width = self.template_canvas_widget.winfo_width()
                    # Canvas宽度 - 滚动条(20px) - section的padx(10px) - grid的padx(10px)
                    actual_width = canvas_width - 40
                    pass  # print removed
                    pass
                elif self.template_canvas:
                    self.template_canvas.update_idletasks()
                    frame_width = self.template_canvas.winfo_width()
                    actual_width = frame_width - 40
                    pass  # print removed
                    pass
                else:
                    actual_width = 720  # 默认值
                    pass  # print removed
            # 最终验证
            if actual_width <= 10:
                actual_width = 720
            
            container_width = actual_width
        
        # 计算列数 - 使用实际测量值
        # 保持列数稳定：
        # - 891px 应该放15列 → 891/15 = 59.4px
        # - 1147px 应该放19列 → 1147/19 = 60.4px
        # 使用60px保持列数不变，通过padx调整视觉间距
        card_total = 60  # 固定值，保持列数稳定
        
        # 计算列数（向下取整）
        cols = int(container_width / card_total)
        
        # 检查剩余空间：如果剩余空间超过30px，可以再挤一列
        remaining = container_width - (cols * card_total)
        if remaining >= 30:  # 如果剩余空间 >= 30px
            cols += 1
        # 确保至少1列
        if cols < 1:
            cols = 1
        
        pass
        pass
        # 按照field_types的顺序重新pack有内容的section
        for section in self.field_types:
            if section not in self.section_frames:
                continue
            
            # 获取已归档模板列表
            widgets_e = self.char_widgets[section]['existing']
            frame_e = self.section_frames[section]['archived_grid']
            
            # 调试信息
            if widgets_e:
                pass
            
            # 布局已归档模板
            if widgets_e:
                frame_e.pack(fill=tk.X, expand=True, pady=(0, 5))
                # print(f"   → 开始布局 {len(widgets_e)} 个已归档模板，使用 {cols} 列")
                for index, item in enumerate(widgets_e):
                    row = index // cols
                    col = index % cols
                    # 确保widget的父容器正确
                    if item['frame'].master != frame_e:
                        pass
                        pass
                    item['frame'].grid(
                        row=row,
                        column=col,
                        padx=6,  # 水平间距：左右各6px，总共12px
                        pady=5,
                        sticky="n"
                    )
                    if index < 5 or index >= len(widgets_e) - 5:  # 打印前5个和后5个的位置
                        pass  # print removed
                        pass
            else:
                frame_e.pack_forget()
            
            # 获取本次提取结果列表
            widgets_n = self.char_widgets[section]['new']
            frame_n = self.section_frames[section]['new_grid']
            
            # 调试信息
            if widgets_n:
                pass
            
            # 布局本次提取结果
            if widgets_n:
                frame_n.pack(fill=tk.X, expand=True)
                for index, item in enumerate(widgets_n):
                    row = index // cols
                    col = index % cols
                    # 确保widget的父容器正确
                    if item['frame'].master != frame_n:
                        pass
                        pass
                    item['frame'].grid(
                        row=row,
                        column=col,
                        padx=6,  # 水平间距：左右各6px，总共12px
                        pady=5,
                        sticky="n"
                    )
            else:
                frame_n.pack_forget()
            
            # 如果该字段有内容，按顺序pack整个section
            has_content = (len(widgets_e) > 0 or len(widgets_n) > 0)
            if has_content:
                container = self.section_frames[section]['container']
                container.pack(
                    fill=tk.X,
                    expand=True,
                    padx=5,
                    pady=5
                )
    
    def delete_single_char(self, item_to_delete):
        """
        删除单个字符
        
        参数:
            item_to_delete: 要删除的字符项数据
        """
        section = item_to_delete['type']
        is_new = item_to_delete['is_new']
        target_key = 'new' if is_new else 'existing'
        target_list = self.char_widgets[section][target_key]
        
        # 查找要删除的项
        target_index = -1
        for i, item in enumerate(target_list):
            if item is item_to_delete:
                target_index = i
                break
        
        # 删除
        if target_index != -1:
            item_to_delete['frame'].destroy()
            target_list.pop(target_index)
            self._reflow_grid()
            pass  # print removed
    
    def batch_delete_selected_templates(self):
        """
        批量删除选中的模板
        
        删除用户在界面上选中的模板
        """
        # 收集所有选中的模板
        selected_templates = []
        for section in self.char_widgets:
            for item in self.char_widgets[section]['existing']:
                if 'selected' in item and item['selected']:
                    selected_templates.append((section, item))
            for item in self.char_widgets[section]['new']:
                if 'selected' in item and item['selected']:
                    selected_templates.append((section, item))
        
        if not selected_templates:
            messagebox.showinfo("提示", "请先在界面上选择要删除的模板")
            return
        
        # 确认删除
        confirm = messagebox.askyesno(
            "确认删除",
            f"确定要删除选中的 {len(selected_templates)} 个模板吗？\n\n此操作不可恢复！",
            icon='warning'
        )
        
        if not confirm:
            return
        
        # 执行删除
        deleted_count = 0
        for section, item in selected_templates:
            # 确定目标列表
            target_list = self.char_widgets[section]['existing'] if not item['is_new'] else self.char_widgets[section]['new']
            
            # 从列表中删除
            if item in target_list:
                item['frame'].destroy()
                target_list.remove(item)
                deleted_count += 1
        
        # 刷新布局
        self._reflow_grid()
        
        # 显示结果
        if deleted_count > 0:
            messagebox.showinfo("成功", f"成功删除 {deleted_count} 个模板！")
        else:
            messagebox.showinfo("提示", "没有删除任何模板")

    def clear_selected_state(self):
        """取消所有已选中模板的选中状态"""
        for section in self.field_types:
            for item in self.char_widgets[section]['existing'] + self.char_widgets[section]['new']:
                if item.get('selected'):
                    item['selected'] = False
                    item['frame'].config(highlightbackground="#d0d0d0", highlightcolor="#d0d0d0", bg="white")
                    if 'lbl_img' in item:
                        item['lbl_img'].config(bg="white")
                    for child in item['frame'].winfo_children():
                        if isinstance(child, tk.Button):
                            child.config(bg="white")

    # ============================================================================
    # 原来的批量删除模板方法（已注释，保留以供参考）
    # ============================================================================
    # def batch_delete_templates(self):
    #     """
    #     批量删除模板
    #     
    #     打开一个新窗口，显示所有已保存的模板，允许用户选择要删除的模板
    #     """
    #     # 收集所有已保存的模板
    #     all_templates = []
    #     for section in self.char_widgets:
    #         for item in self.char_widgets[section]['existing']:
    #             all_templates.append((section, item))
    #     
    #     if not all_templates:
    #         messagebox.showinfo("提示", "当前没有已保存的模板")
    #         return
    #     
    #     # 创建选择窗口
    #     select_window = tk.Toplevel(self)
    #     select_window.title("批量删除模板")
    #     select_window.geometry("600x400")
    #     select_window.resizable(True, True)
    #     
    #     # 创建滚动容器
    #     canvas = tk.Canvas(select_window, bg="white")
    #     scrollbar = tk.Scrollbar(select_window, orient="vertical", command=canvas.yview)
    #     scrollable_frame = tk.Frame(canvas, bg="white")
    #     
    #     scrollable_frame.bind(
    #         "<Configure>",
    #         lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    #     )
    #     
    #     canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    #     canvas.configure(yscrollcommand=scrollbar.set)
    #     
    #     canvas.pack(side="left", fill="both", expand=True)
    #     scrollbar.pack(side="right", fill="y")
    #     
    #     # 存储选择状态
    #     selected_items = []
    #     check_vars = []
    #     
    #     # 显示模板列表
    #     row = 0
    #     col = 0
    #     max_cols = 5
    #     
    #     for section, item in all_templates:
    #         # 创建复选框和模板预览
    #         frame = tk.Frame(scrollable_frame, bg="white", bd=1, relief=tk.SOLID, width=100, height=100)
    #         frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
    #         
    #         # 复选框
    #         var = tk.BooleanVar()
    #         check_vars.append((var, section, item))
    #         
    #         checkbox = tk.Checkbutton(frame, variable=var, bg="white")
    #         checkbox.place(x=5, y=5)
    #         
    #         # 模板图像
    #         cv2_img = item['image']
    #         img_pil = Image.fromarray(cv2_img)
    #         img_tk = ImageTk.PhotoImage(img_pil)
    #         lbl_img = tk.Label(frame, bg="white", image=img_tk)
    #         lbl_img.image = img_tk
    #         lbl_img.place(x=25, y=10, width=60, height=60)
    #         
    #         # 标签
    #         label = item['entry'].get() if 'entry' in item else ""
    #         lbl_text = tk.Label(frame, text=label, bg="white", font=("Arial", 10))
    #         lbl_text.place(x=5, y=75, width=90, anchor="n")
    #         
    #         # 字段类型
    #         lbl_section = tk.Label(frame, text=section, bg="white", font=("Arial", 8), fg="#666")
    #         lbl_section.place(x=5, y=90, width=90, anchor="n")
    #         
    #         col += 1
    #         if col >= max_cols:
    #             col = 0
    #             row += 1
    #     
    #     # 按钮区域
    #     button_frame = tk.Frame(select_window, bg="white")
    #     button_frame.pack(fill=tk.X, pady=10)
    #     
    #     def select_all():
    #         for var, _, _ in check_vars:
    #             var.set(True)
    #     
    #     def select_none():
    #         for var, _, _ in check_vars:
    #             var.set(False)
    #     
    #     def delete_selected():
    #         # 收集要删除的项
    #         to_delete = []
    #         for var, section, item in check_vars:
    #             if var.get():
    #                 to_delete.append((section, item))
    #         
    #         if not to_delete:
    #             messagebox.showinfo("提示", "请选择要删除的模板")
    #             return
    #         
    #         # 确认删除
    #         confirm = messagebox.askyesno(
    #             "确认删除",
    #             f"确定要删除选中的 {len(to_delete)} 个模板吗？\n\n此操作不可恢复！",
    #             icon='warning'
    #         )
    #         
    #         if not confirm:
    #             return
    #         
    #         # 执行删除
    #         deleted_count = 0
    #         for section, item in to_delete:
    #             # 从列表中删除
    #             if item in self.char_widgets[section]['existing']:
    #                 item['frame'].destroy()
    #                 self.char_widgets[section]['existing'].remove(item)
    #                 deleted_count += 1
    #         
    #         # 刷新布局
    #         self._reflow_grid()
    #         
    #         # 关闭窗口
    #         select_window.destroy()
    #         
    #         # 显示结果
    #         if deleted_count > 0:
    #             messagebox.showinfo("成功", f"成功删除 {deleted_count} 个模板！")
    #         else:
    #             messagebox.showinfo("提示", "没有删除任何模板")
    #     
    #     # 全选按钮
    #     btn_select_all = tk.Button(
    #         button_frame,
    #         text="全选",
    #         font=("微软雅黑", 9),
    #         bg="#3498db",
    #         fg="white",
    #         relief=tk.FLAT,
    #         padx=10,
    #         pady=5,
    #         cursor="hand2",
    #         command=select_all
    #     )
    #     btn_select_all.pack(side=tk.LEFT, padx=(10, 5))
    #     
    #     # 全不选按钮
    #     btn_select_none = tk.Button(
    #         button_frame,
    #         text="全不选",
    #         font=("微软雅黑", 9),
    #         bg="#95a5a6",
    #         fg="white",
    #         relief=tk.FLAT,
    #         padx=10,
    #         pady=5,
    #         cursor="hand2",
    #         command=select_none
    #     )
    #     btn_select_none.pack(side=tk.LEFT, padx=5)
    #     
    #     # 删除按钮
    #     btn_delete = tk.Button(
    #         button_frame,
    #         text="删除选中",
    #         font=("微软雅黑", 9),
    #         bg="#e74c3c",
    #         fg="white",
    #         relief=tk.FLAT,
    #         padx=10,
    #         pady=5,
    #         cursor="hand2",
    #         command=delete_selected
    #     )
    #     btn_delete.pack(side=tk.RIGHT, padx=10)
    #     
    #     # 取消按钮
    #     btn_cancel = tk.Button(
    #         button_frame,
    #         text="取消",
    #         font=("微软雅黑", 9),
    #         bg="#95a5a6",
    #         fg="white",
    #         relief=tk.FLAT,
    #         padx=10,
    #         pady=5,
    #         cursor="hand2",
    #         command=select_window.destroy
    #     )
    #     btn_cancel.pack(side=tk.RIGHT, padx=5)
    def reset_list(self):
        """
        还原列表
        
        放弃本次新提取的所有字符，恢复到加载方案时的状态
        """
        # 统计新提取的字符数量
        total_new = 0
        for s in self.char_widgets:
            total_new += len(self.char_widgets[s]['new'])
        
        # 如果没有新提取的内容，直接返回
        if total_new == 0:
            messagebox.showinfo("提示", "当前没有新提取的内容，无需还原。")
            return
        
        # 确认还原
        if not messagebox.askyesno("还原列表", "确定要放弃本次新提取的所有字符？"):
            return
        
        # 重新加载方案数据
        self.load_solution_data()
        
        pass  # print removed
    def _focus_next(self, current_entry, section, target_key):
        """
        焦点移动到下一个输入框
        
        按Enter键时，自动跳转到下一个字符的标签输入框
        
        参数:
            current_entry: 当前输入框
            section: 字段类型
            target_key: 'existing' 或 'new'
        """
        widgets = self.char_widgets[section][target_key]
        found = False
        
        for item in widgets:
            if found:
                item['entry'].focus_set()
                return
            if item['entry'] == current_entry:
                found = True
    
    # ====================================================================
    # 字段管理方法 (Task 9)
    # ====================================================================
    
    def add_custom_field(self):
        """
        添加自定义字段
        
        允许用户添加新的字段类型，并保存到当前方案中
        """
        # 1. 检查是否选择了方案
        if not self.current_solution_name:
            messagebox.showwarning(
                "警告",
                "请先选择或创建方案！\n\n"
                "自定义字段需要保存到具体的方案中。"
            )
            return
        
        # 2. 弹出输入对话框
        field_name = simpledialog.askstring(
            "添加自定义字段",
            f"当前方案: {self.current_solution_name}\n\n"
            f"请输入字段名称:",
            parent=self
        )
        
        # 用户取消输入
        if field_name is None:
            return
        
        # 3. 验证字段名
        field_name = field_name.strip()
        
        # 检查是否为空
        if not field_name:
            messagebox.showwarning("警告", "字段名称不能为空！")
            return
        
        # 检查是否已存在
        if field_name in self.field_types:
            messagebox.showwarning("警告", f"字段 '{field_name}' 已存在！")
            return
        
        # 4. 为新字段创建目录（在方案目录下）
        self._create_field_directory(field_name)
        
        # 5. 注册新字段
        self._register_field(field_name, create_ui=True)

        # 强制刷新布局，确保新单选按钮立即显示
        if hasattr(self, 'field_icon_frame'):
            self.field_icon_frame.update_idletasks()
        self.update_idletasks()
        
        # 6. 保存字段列表到方案配置
        safe_call(self._save_custom_fields_config)
        
        # 7. 切换到新字段
        self.var_field_type.set(field_name)
        
        messagebox.showinfo(
            "成功",
            f"字段 '{field_name}' 已添加到方案 '{self.current_solution_name}'！\n\n"
            f"提示：记得保存方案以保留字段配置。"
        )

    @ErrorHandler.handle_file_error
    def _create_field_directory(self, field_name):
        """创建字段目录"""
        solution_path = os.path.join(self.solutions_root, self.current_solution_name)
        field_dir = os.path.join(solution_path, field_name)
        
        if not os.path.exists(field_dir):
            os.makedirs(field_dir)
            pass  # print removed
    
    def delete_field(self):
        """
        删除字段
        
        允许用户删除自定义字段（不能删除默认字段）
        """
        # 获取当前选中的字段
        field_name = self.var_field_type.get()
        
        # 检查是否选择了字段
        if not field_name:
            messagebox.showwarning("警告", "请先选择要删除的字段！")
            return
        
        # 定义不可删除的默认字段
        protected_fields = ["CardNumber", "Name", "Date", "FirstDigitAnchor"]
        
        # 检查是否为默认字段
        if field_name in protected_fields:
            messagebox.showwarning(
                "警告",
                f"字段 '{field_name}' 是默认字段，不能删除！\n\n"
                f"只能删除自定义字段。"
            )
            return
        
        # 弹出确认对话框
        confirm = messagebox.askyesno(
            "确认删除",
            f"确定要删除字段 '{field_name}' 吗？\n\n"
            f"此操作将删除该字段的所有数据：\n"
            f"- UI section\n"
            f"- 字符模板数据\n"
            f"- ROI 配置\n"
            f"- 临时框\n\n"
            f"注意：此操作不会删除已保存到磁盘的模板文件。",
            icon='warning'
        )
        
        if not confirm:
            return
        
        # 执行删除
        self._execute_field_deletion(field_name)

    @ErrorHandler.handle_ui_error
    def _execute_field_deletion(self, field_name):
        """执行字段删除操作"""
        # 1. 从 field_types 列表中移除
        if field_name in self.field_types:
            self.field_types.remove(field_name)
            pass  # print removed
        # 2. 删除 UI section
        if field_name in self.section_frames:
            container = self.section_frames[field_name]['container']
            if container and container.winfo_exists():
                container.destroy()
            del self.section_frames[field_name]
            pass  # print removed
        # 3. 删除字符模板数据
        if field_name in self.char_widgets:
            # 销毁所有字符卡片
            for item in self.char_widgets[field_name]['existing']:
                if 'frame' in item and item['frame'].winfo_exists():
                    item['frame'].destroy()
            for item in self.char_widgets[field_name]['new']:
                if 'frame' in item and item['frame'].winfo_exists():
                    item['frame'].destroy()
            
            del self.char_widgets[field_name]
            pass  # print removed
        # 4. 删除 ROI 配置
        if field_name in self.roi_layout_config:
            del self.roi_layout_config[field_name]
            pass  # print removed
        if field_name in self.temp_layout_config:
            del self.temp_layout_config[field_name]
            pass  # print removed
        # 5. 删除临时框
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        temp_rects_to_remove = []
        for i, rect in enumerate(self.temp_rects):
            if rect['field_type'] == field_name:
                # 删除画布上的框
                if rect['canvas_id']:
                    display_canvas.delete(rect['canvas_id'])
                temp_rects_to_remove.append(i)
        
        # 从后往前删除，避免索引错乱
        for i in reversed(temp_rects_to_remove):
            self.temp_rects.pop(i)
        
        if temp_rects_to_remove:
            pass
        
        # 6. 删除颜色映射
        if field_name in self.color_map:
            del self.color_map[field_name]
            pass  # print removed
        # 7. 删除对应的单选按钮，并重新排列剩余按钮
        if field_name in self.field_buttons:
            self.field_buttons[field_name].destroy()
            del self.field_buttons[field_name]

        # 重新 grid 所有剩余按钮
        if hasattr(self, 'field_icon_frame') and self.field_icon_frame.winfo_exists():
            for i, ft in enumerate(self.field_types):
                if ft in self.field_buttons:
                    self.field_buttons[ft].grid(row=i // 4, column=i % 4, sticky="w", padx=2, pady=2)
            self.field_icon_frame.update_idletasks()

        # 8. 永久删除：移除磁盘目录并更新 custom_fields.json
        if self.current_solution_name:
            import shutil
            solution_path = os.path.join(self.solutions_root, self.current_solution_name)
            field_dir = os.path.join(solution_path, field_name)
            if os.path.exists(field_dir):
                shutil.rmtree(field_dir)
            safe_call(self._save_custom_fields_config)

        # 9. 切换到第一个字段
        if self.field_types:
            self.var_field_type.set(self.field_types[0])
            self._on_field_selected()
        else:
            self.var_field_type.set("")
        
        # 9. 刷新画布（重新绘制 ROI 框）
        if self.original_image is not None:
            self._refresh_canvas_image()
        
        messagebox.showinfo("成功", f"字段 '{field_name}' 已删除！")
        pass  # print removed
    
    def _on_field_selected(self):
        """
        字段选择事件
        
        当用户切换字段类型时触发
        """
        current_type = self.var_field_type.get()
        
        # 如果选择的是锚点字段，自动勾选锚点复选框
        if current_type == "FirstDigitAnchor":
            self.var_is_anchor.set(True)
        else:
            self.var_is_anchor.set(False)
        
        pass  # print removed
    def _save_custom_fields_config(self):
        """
        保存自定义字段配置
        
        将当前方案的字段列表保存到配置文件
        """
        if not self.current_solution_name:
            return
        
        solution_path = os.path.join(self.solutions_root, self.current_solution_name)
        config_file = os.path.join(solution_path, "custom_fields.json")
        
        # 获取自定义字段（排除默认字段）
        default_fields = ["CardNumber", "Name", "Date", "FirstDigitAnchor"]
        custom_fields = [f for f in self.field_types if f not in default_fields]
        
        # 保存到文件
        config_data = {
            "custom_fields": custom_fields,
            "all_fields": self.field_types
        }
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        
        pass  # print removed
    @safe_execute(default_return=None, log_error=False, error_message="加载自定义字段配置失败")
    def _load_custom_fields_config(self):
        """加载自定义字段配置，切换方案时先清除旧自定义字段再加载新方案字段"""
        default_fields = ["CardNumber", "Name", "Date", "FirstDigitAnchor"]

        # 1. 移除上一个方案的自定义字段（UI + 数据）
        old_custom = [f for f in self.field_types if f not in default_fields]
        for field_name in old_custom:
            self.field_types.remove(field_name)
            if field_name in self.field_buttons:
                self.field_buttons[field_name].destroy()
                del self.field_buttons[field_name]
            if field_name in self.char_widgets:
                del self.char_widgets[field_name]
            if field_name in self.section_frames:
                del self.section_frames[field_name]

        # 重新排列剩余按钮
        if hasattr(self, 'field_icon_frame') and self.field_icon_frame.winfo_exists():
            for i, ft in enumerate(self.field_types):
                if ft in self.field_buttons:
                    self.field_buttons[ft].grid(row=i // 4, column=i % 4, sticky="w", padx=2, pady=2)

        if not self.current_solution_name:
            return

        solution_path = os.path.join(self.solutions_root, self.current_solution_name)
        config_file = os.path.join(solution_path, "custom_fields.json")

        if not os.path.exists(config_file):
            return

        with open(config_file, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        custom_fields = config_data.get("custom_fields", [])

        # 2. 注册新方案的自定义字段
        for field_name in custom_fields:
            if field_name not in self.field_types:
                self._register_field(field_name, create_ui=True)
    
    def _on_mode_change(self):
        """
        工作模式切换事件
        
        当用户切换工作模式时触发
        """
        mode = self.var_work_mode.get()
        pass  # print removed
        # 可以根据模式调整UI状态
        # 例如：Layout Only模式下禁用某些功能
    
    # ====================================================================
    # 数据持久化方法 (Task 10)
    # ====================================================================
    
    @ErrorHandler.handle_file_error
    def save_templates(self):
        """
        保存模板
        
        将所有字符模板和布局配置保存到方案目录
        """
        # 1. 验证方案名
        if not self.current_solution_name:
            messagebox.showwarning("警告", "请先选择或创建方案！")
            return
        
        # 2. 统计要保存的内容
        total_chars = 0
        for s in self.char_widgets:
            total_chars += len(self.char_widgets[s]['existing']) + len(self.char_widgets[s]['new'])
        
        # 如果没有内容，直接返回
        if total_chars == 0 and not self.roi_layout_config:
            messagebox.showinfo("提示", "没有可保存的内容")
            return
        
        # 3. 确认保存
        if not messagebox.askokcancel(
            "同步保存",
            f"方案 '{self.current_solution_name}'\n"
            f"布局字段: {len(self.roi_layout_config)}\n"
            f"字符模板: {total_chars}\n\n"
            f"确定要保存吗？(旧文件将被覆盖)"
        ):
            return
        
        # 4. 执行保存
        self._execute_save_operation()

    @ErrorHandler.handle_file_error
    def _execute_save_operation(self):
        """执行保存操作"""
        base_dir = os.path.join(self.solutions_root, self.current_solution_name)
        
        # 合并临时布局到正式布局
        if self.temp_layout_config:
            for field, layout_data in self.temp_layout_config.items():
                self.roi_layout_config[field] = layout_data
                pass  # print removed
            self.temp_layout_config = {}

        # 清除所有 _modified 标记（保存后恢复为"已保存"状态）
        for field, data in self.roi_layout_config.items():
            if isinstance(data, dict) and data.get('_modified'):
                data.pop('_modified', None)
        
        # 保存布局配置
        self._save_layout_config(base_dir)
        
        # 保存自定义字段配置
        self._save_custom_fields_config()
        
        # 保存字符模板
        saved_count = self._save_char_templates(base_dir)
        
        # ★★★ 保存 OCR 工作状态到主窗口（新增）★★★
        if self.main_window and hasattr(self.main_window, 'save_ocr_state'):
            self.main_window.save_ocr_state()
            pass  # print removed
        # 记录保存解决方案日志
        if self.main_window and hasattr(self.main_window, '_audit'):
            self.main_window._audit(
                "template_operation", "save_solution",
                target_object=self.current_solution_name or ""
            )
        # 清空编辑器（保留捕获的图像）
        pass  # print removed
        self._clear_editor(keep_captured_image=True)
        
        # 重新加载方案数据（刷新UI）
        self.load_solution_data()
        
        # 获取策略类型
        strategy = "anchor_based" if "FirstDigitAnchor" in self.roi_layout_config else "absolute"
        
        messagebox.showinfo(
            "保存成功",
            f"方案 '{self.current_solution_name}' 已更新。\n"
            f"策略: {strategy}\n"
            f"保存了 {saved_count} 个字符模板"
        )
        
        pass  # print removed
    
    def _save_layout_config(self, base_dir):
        """
        保存布局配置
        
        将ROI布局配置保存为JSON文件
        
        参数:
            base_dir: 方案目录路径
        """
        layout_data = {}
        layout_data["fields"] = {}
        
        # ★★★ 关键改进：保存训练图像的尺寸 ★★★
        if self.original_image is not None:
            h, w = self.original_image.shape[:2]
            layout_data["image_size"] = {
                "width": int(w),
                "height": int(h)
            }
        else:
            pass
        
        # 1. 保存锚点信息
        if "FirstDigitAnchor" in self.roi_layout_config:
            anchor_data = self.roi_layout_config["FirstDigitAnchor"]
            
            layout_data["strategy"] = "anchor_based"
            # 保存用于计算偏移的基准点（墨迹）
            layout_data["anchor_rect"] = anchor_data["roi"]
            # 保存用于寻找锚点的搜索区（用户框）
            layout_data["anchor_search_area"] = anchor_data.get("search_area", anchor_data["roi"])
        else:
            layout_data["strategy"] = "absolute"
        
        # 2. 保存其他字段
        for field, config in self.roi_layout_config.items():
            if field == "FirstDigitAnchor":
                continue
            if isinstance(config, dict):
                r = config["roi"]
                # 优先用 _pending_field_props，其次用 roi_layout_config 里的
                field_props = self._pending_field_props.get(field) or config.get("field_props", {})
            else:
                r = config
                field_props = self._pending_field_props.get(field, {})
            layout_data["fields"][field] = r
            if field_props:
                if "field_props" not in layout_data:
                    layout_data["field_props"] = {}
                layout_data["field_props"][field] = field_props
        
        # 3. 保存到文件
        layout_path = os.path.join(base_dir, "layout_config.json")
        with open(layout_path, "w", encoding="utf-8") as f:
            json.dump(layout_data, f, indent=4, ensure_ascii=False)
        
        pass  # print removed
    def _save_char_templates(self, base_dir):
        """
        保存字符模板图像
        
        将所有字符模板保存为PNG文件
        
        参数:
            base_dir: 方案目录路径
        
        返回:
            int: 保存的字符数量
        """
        saved_count = 0
        
        # 遍历所有字段类型
        for section in self.field_types:
            if section not in self.char_widgets:
                continue
            
            # 合并已归档和新提取的字符
            all_widgets = (
                self.char_widgets[section]['existing'] +
                self.char_widgets[section]['new']
            )
            
            if not all_widgets:
                continue
            
            # 创建字段目录
            target_dir = os.path.join(base_dir, section)
            
            # 删除旧文件
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            os.makedirs(target_dir)
            
            # 标签计数器（用于处理重复标签）
            label_counters = {}
            
            # 保存每个字符
            for item in all_widgets:
                label = item['entry'].get().strip()
                
                # 跳过空标签或标记为skip的字符
                if not label or label.lower() == 'skip':
                    continue
                
                # 处理特殊字符（避免文件名冲突）
                safe_label = label.replace("\\", "backslash").replace("/", "slash").replace(".", "char_dot")
                
                # 处理重复标签
                if safe_label not in label_counters:
                    label_counters[safe_label] = 0
                
                filename = f"{safe_label}_{label_counters[safe_label]}.png"
                label_counters[safe_label] += 1
                
                # 保存图像（使用支持中文路径的方法）
                path = os.path.join(target_dir, filename)
                img = item['image']
                
                # 使用cv2.imencode + tofile支持中文路径
                is_success, im_buf = cv2.imencode(".png", img)
                if is_success:
                    im_buf.tofile(path)
                    saved_count += 1
        
        return saved_count
    
    def _load_layout_config(self):
        """
        加载布局配置
        
        从JSON文件加载ROI布局配置
        
        注意：此方法已在load_solution_data中实现
        """
        pass
    
    def _load_char_templates(self):
        """
        加载字符模板图像
        
        从PNG文件加载字符模板
        
        注意：此方法已在load_solution_data中实现
        """
        pass
    
    def clear_new_extraction(self):
        """
        清空本次提取结果
        
        删除所有"本次提取结果"的字符、画面中的临时框和临时布局
        """
        # 1. 统计要删除的内容
        total_new_chars = 0
        for section in self.char_widgets:
            total_new_chars += len(self.char_widgets[section]['new'])
        
        total_temp_rects = len(self.temp_rects)
        total_temp_layouts = len(self.temp_layout_config)
        
        if total_new_chars == 0 and total_temp_rects == 0 and total_temp_layouts == 0:
            messagebox.showinfo("提示", "没有本次提取的内容需要清空")
            return
        
        # 2. 确认删除
        if not messagebox.askokcancel(
            "确认清空",
            f"即将清空：\n"
            f"• 本次提取的字符: {total_new_chars} 个\n"
            f"• 画面中的临时框: {total_temp_rects} 个\n"
            f"• 临时布局配置: {total_temp_layouts} 个\n\n"
            f"此操作不可撤销，确定要清空吗？"
        ):
            return
        
        # 3. 删除所有"本次提取结果"的字符
        for section in self.char_widgets:
            for item in self.char_widgets[section]['new']:
                if 'frame' in item and item['frame'].winfo_exists():
                    item['frame'].destroy()
            
            # 清空new列表
            self.char_widgets[section]['new'] = []
        
        # 4. 删除画面中的所有临时框
        display_canvas = self.preview_canvas if self.preview_canvas else self.canvas
        for rect_info in self.temp_rects:
            canvas_id = rect_info['canvas_id']
            if canvas_id:
                display_canvas.delete(canvas_id)
        
        # 清空临时框列表
        self.temp_rects = []
        
        # 5. 清空临时布局配置
        if self.temp_layout_config:
            self.temp_layout_config = {}
        
        # 6. 清除当前框选状态
        self.rect_start = None
        self.rect_end = None
        if self.current_rect_id:
            display_canvas.delete(self.current_rect_id)
            self.current_rect_id = None
        
        # 7. 刷新画布（重新显示已保存的布局框，不显示临时布局）
        if self.original_image is not None:
            self._refresh_canvas_image()
        
        # 8. 刷新网格布局
        self._reflow_grid()
        
        pass  # print removed
        messagebox.showinfo("成功", f"已清空 {total_new_chars} 个字符、{total_temp_rects} 个临时框和 {total_temp_layouts} 个临时布局")
    
    @ErrorHandler.handle_file_error
    def export_solution(self):
        """
        导出方案到磁盘
        
        将整个方案文件夹打包导出到用户指定的位置
        """
        # 1. 检查是否选择了方案
        if not self.current_solution_name:
            messagebox.showwarning("警告", "请先选择一个方案！")
            return
        
        # 2. 检查方案目录是否存在
        solution_path = os.path.join(self.solutions_root, self.current_solution_name)
        if not os.path.exists(solution_path):
            messagebox.showerror("错误", f"方案目录不存在: {solution_path}")
            return
        
        # 3. 选择导出位置
        from tkinter import filedialog
        export_path = filedialog.asksaveasfilename(
            title="导出方案",
            defaultextension=".zip",
            initialfile=f"{self.current_solution_name}.zip",
            filetypes=[("ZIP压缩包", "*.zip"), ("所有文件", "*.*")]
        )
        
        if not export_path:
            return  # 用户取消
        
        # 4. 打包方案文件夹
        self._export_solution_to_zip(solution_path, export_path)

    @ErrorHandler.handle_file_error
    def _export_solution_to_zip(self, solution_path, export_path):
        """将方案导出为ZIP文件"""
        import zipfile
        
        with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 遍历方案目录中的所有文件
            for root, dirs, files in os.walk(solution_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    # 计算相对路径（保持目录结构）
                    arcname = os.path.relpath(file_path, solution_path)
                    zipf.write(file_path, arcname)
                    pass  # print removed
        messagebox.showinfo(
            "导出成功",
            f"方案 '{self.current_solution_name}' 已导出到:\n{export_path}"
        )
        pass  # print removed
    
    @ErrorHandler.handle_file_error
    def import_solution(self):
        """
        从磁盘导入方案
        
        解压用户选择的ZIP文件到solutions目录
        """
        # 1. 选择要导入的ZIP文件
        from tkinter import filedialog
        import_path = filedialog.askopenfilename(
            title="导入方案",
            filetypes=[("ZIP压缩包", "*.zip"), ("所有文件", "*.*")]
        )
        
        if not import_path:
            return  # 用户取消
        
        # 2. 提取方案名称（从文件名）
        import_filename = os.path.basename(import_path)
        solution_name = os.path.splitext(import_filename)[0]
        
        # 3. 检查方案是否已存在
        target_path = os.path.join(self.solutions_root, solution_name)
        if os.path.exists(target_path):
            if not messagebox.askokcancel(
                "方案已存在",
                f"方案 '{solution_name}' 已存在。\n\n"
                f"是否覆盖现有方案？"
            ):
                return
            
            # 删除旧方案
            shutil.rmtree(target_path)
            pass  # print removed
        # 4. 解压ZIP文件
        self._import_solution_from_zip(import_path, target_path, solution_name)

    @ErrorHandler.handle_file_error
    def _import_solution_from_zip(self, import_path, target_path, solution_name):
        """从ZIP文件导入方案"""
        import zipfile
        
        with zipfile.ZipFile(import_path, 'r') as zipf:
            zipf.extractall(target_path)
            pass  # print removed
        # 5. 刷新方案列表
        self._refresh_solution_list()
        
        # 6. 自动选择导入的方案
        self.var_solution_name.set(solution_name)
        self.on_solution_selected(None)
        
        messagebox.showinfo(
            "导入成功",
            f"方案 '{solution_name}' 已成功导入！\n\n"
            f"已自动加载该方案。"
        )
        pass  # print removed
    
    def _refresh_solution_list(self):
        """
        刷新方案列表
        
        重新扫描solutions目录，更新下拉框
        """
        if not os.path.exists(self.solutions_root):
            return
        
        # 扫描方案目录
        solution_names = [
            d for d in os.listdir(self.solutions_root)
            if os.path.isdir(os.path.join(self.solutions_root, d))
        ]
        solution_names.sort()
        
        # 更新下拉框
        if hasattr(self, 'combo_solution'):
            self.combo_solution['values'] = solution_names
            # 如果当前方案名在列表里，自动选中
            if self.current_solution_name and self.current_solution_name in solution_names:
                if hasattr(self, 'var_solution_name'):
                    self.var_solution_name.set(self.current_solution_name)
    
    # ====================================================================
    # 资源管理方法 (Task 11)
    # ====================================================================
    
    def cleanup(self):
        """
        清理资源
        
        在返回主菜单前清理所有资源
        """
        pass  # print removed
        # 1. 解绑画布事件
        self._unbind_canvas_events()
        
        # 2. 清空预览画布
        if self.preview_canvas:
            self.preview_canvas.delete("all")
        elif self.canvas:
            self.canvas.delete("all")
        
        # 3. 清空编辑器
        self._clear_editor()
        
        # 4. 释放图像资源
        self.original_image = None
        self.tk_image = None
        
        pass  # print removed
    def _check_save_state(self):
        """
        检查保存状态
        
        检查是否有未保存的内容，并更新UI状态
        
        注意：在当前实现中，保存按钮始终可用（如果有方案）
        """
        # 统计总字符数
        total = 0
        for s in self.char_widgets:
            total += len(self.char_widgets[s]['existing']) + len(self.char_widgets[s]['new'])
        
        # 如果有内容或有布局配置，且选择了方案，则可以保存
        has_content = (total > 0 or self.roi_layout_config)
        has_solution = (self.current_solution_name is not None)
        
        if has_content and has_solution:
            # print(f"💾 可保存状态: {total} 个字符, {len(self.roi_layout_config)} 个布局")
            pass
        else:
            pass  # print removed
    def _create_mode_selection(self):
        """创建模式选择区域（工作模式下拉框 + 调试复选框）"""
        frame = tk.LabelFrame(
            self,
            text="工作模式",
            font=("微软雅黑", 9, "bold"),
            bg="white",
            fg="#2c3e50",
            padx=10,
            pady=5
        )
        frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 第一行：工作模式下拉框
        row1 = tk.Frame(frame, bg="white")
        row1.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(
            row1,
            text="模式:",
            font=("微软雅黑", 9),
            bg="white"
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        self.var_work_mode = tk.StringVar(value="Full Mode")
        work_modes = ["Full Mode", "Template Only", "Layout Only"]
        combo_mode = ttk.Combobox(
            row1,
            textvariable=self.var_work_mode,
            values=work_modes,
            state="readonly",
            width=18,
            font=("微软雅黑", 9)
        )
        combo_mode.pack(side=tk.LEFT, fill=tk.X, expand=True)
        combo_mode.bind("<<ComboboxSelected>>", lambda e: self._on_mode_change())
        
        # 第二行：调试复选框
        row2 = tk.Frame(frame, bg="white")
        row2.pack(fill=tk.X)
        
        self.var_show_debug = tk.BooleanVar(value=False)
        chk_debug = tk.Checkbutton(
            row2,
            text="☑ 显示过程图（调试模式）",
            variable=self.var_show_debug,
            font=("微软雅黑", 9),
            bg="white",
            selectcolor="white",
            activebackground="white"
        )
        chk_debug.pack(side=tk.LEFT)
    
    def _create_scroll_container(self):
        """创建滚动容器（用于显示字符模板网格）"""
        # 创建标签框
        frame = tk.LabelFrame(
            self,
            text="字符模板",
            font=("微软雅黑", 9, "bold"),
            bg="white",
            fg="#2c3e50",
            padx=5,
            pady=5
        )
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 创建Canvas用于滚动
        self.scroll_canvas = tk.Canvas(
            frame,
            bg="white",
            highlightthickness=0
        )
        self.scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 创建垂直滚动条
        scrollbar = tk.Scrollbar(
            frame,
            orient=tk.VERTICAL,
            command=self.scroll_canvas.yview
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 配置Canvas滚动
        self.scroll_canvas.configure(yscrollcommand=scrollbar.set)
        
        # 创建内部Frame用于放置字符网格
        self.scroll_frame = tk.Frame(self.scroll_canvas, bg="white")
        self.scroll_window = self.scroll_canvas.create_window(
            (0, 0),
            window=self.scroll_frame,
            anchor="nw"
        )
        
        # 绑定配置事件以更新滚动区域
        self.scroll_frame.bind(
            "<Configure>",
            lambda e: self.scroll_canvas.configure(
                scrollregion=self.scroll_canvas.bbox("all")
            )
        )
        
        # 绑定Canvas大小变化事件以调整内部Frame宽度
        self.scroll_canvas.bind(
            "<Configure>",
            lambda e: self.scroll_canvas.itemconfig(
                self.scroll_window,
                width=e.width
            )
        )
        
        # 初始化字段类型的section frames
        for field_type in self.field_types:
            self._create_field_section(field_type)
    
    def _create_field_section(self, field_type):
        """为每个字段类型创建一个section区域"""
        pass  # print removed
        # 使用外部传入的template_canvas作为父容器
        parent_frame = self.template_canvas if self.template_canvas else self
        pass  # print removed
        # 创建section容器(不立即pack,由_reflow_grid统一管理)
        section_container = tk.Frame(parent_frame, bg="white")
        # 注释掉立即pack,改为在_reflow_grid中按顺序pack
        # section_container.pack(fill=tk.X, padx=5, pady=5)
        
        # Section标题
        title_frame = tk.Frame(section_container, bg="#ecf0f1", height=30)
        title_frame.pack(fill=tk.X, pady=(0, 5))
        title_frame.pack_propagate(False)
        
        color = self.color_map.get(field_type, "#000000")
        tk.Label(
            title_frame,
            text=f"▼ {field_type}",
            font=("微软雅黑", 9, "bold"),
            bg="#ecf0f1",
            fg=color,
            anchor="w"
        ).pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        
        # 已归档模板区域
        archived_label = tk.Label(
            section_container,
            text="📂 已归档模板",
            font=("微软雅黑", 8),
            bg="white",
            fg="#7f8c8d",
            anchor="w"
        )
        archived_label.pack(fill=tk.X, padx=5, pady=(5, 2))
        
        archived_grid = tk.Frame(section_container, bg="white")
        archived_grid.pack(fill=tk.X, padx=5, pady=(0, 10))
        
        # 本次提取结果区域
        new_label = tk.Label(
            section_container,
            text="🆕 本次提取结果",
            font=("微软雅黑", 8),
            bg="white",
            fg="#7f8c8d",
            anchor="w"
        )
        new_label.pack(fill=tk.X, padx=5, pady=(5, 2))
        
        new_grid = tk.Frame(section_container, bg="white")
        new_grid.pack(fill=tk.X, padx=5, pady=(0, 5))
        
        # 保存引用
        self.section_frames[field_type] = {
            'container': section_container,
            'archived_grid': archived_grid,
            'new_grid': new_grid
        }
        
        # 初始化字符widgets列表（仅在不存在时初始化，避免覆盖已有数据）
        if field_type not in self.char_widgets:
            self.char_widgets[field_type] = {
                'existing': [],
                'new': []
            }
        
        # 调试信息:打印Frame的ID
        pass  # print removed
        # print(f"      - archived_grid ID: {id(archived_grid)}")
        # print(f"      - new_grid ID: {id(new_grid)}")


# ============================================================================
# 模块测试代码
# ============================================================================

if __name__ == "__main__":
    # 简单测试：创建一个窗口并实例化 SolutionMakerFrame
    root = tk.Tk()
    root.title("SolutionMakerFrame 测试")
    root.geometry("400x600")
    
    # 模拟参数
    mock_camera = None
    mock_canvas = tk.Canvas(root, bg="gray")
    mock_canvas.pack(fill=tk.BOTH, expand=True)
    
    def mock_back():
        pass  # print removed
    # 创建实例
    frame = SolutionMakerFrame(root, mock_camera, mock_canvas, mock_back)
    frame.pack(fill=tk.BOTH, expand=True)
    
    pass  # print removed
    root.mainloop()