
"""
解决方案管理面板 (SolutionManagementPanel)
显示在画布下方，用于管理解决方案
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import os
import shutil


class SolutionManagementPanel(tk.Frame):
    """
    解决方案管理面板
    
    功能：
    - 方案下拉选择
    - 创建新方案
    - 加载方案
    - 保存方案
    - 导入方案
    """
    
    def __init__(self, parent, solutions_root=None, on_solution_selected=None):
        """
        初始化解决方案管理面板
        
        参数:
            parent: 父容器
            solutions_root: 方案根目录路径
            on_solution_selected: 方案选择回调函数 callback(solution_name)
        """
        super().__init__(parent, bg="#f0f0f0")
        
        # 保存参数
        self.solutions_root = solutions_root or self._get_default_solutions_root()
        self.on_solution_selected_callback = on_solution_selected
        self.current_solution_name = None
        
        # 确保方案目录存在
        if not os.path.exists(self.solutions_root):
            os.makedirs(self.solutions_root)
        
        # 创建UI
        self._setup_ui()
        
        # 刷新方案列表
        self.refresh_solution_list()
    
    def _get_default_solutions_root(self):
        """获取默认方案根目录"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        return os.path.join(parent_dir, "solutions")
    
    def _setup_ui(self):
        """设置UI布局 - 优化版本，避免压缩"""
        # 创建最外层容器（浅灰色背景）
        main_container = tk.Frame(self, bg="#E8E8E8", relief=tk.RIDGE, bd=1)
        main_container.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)
        
        # 标题区域
        title_frame = tk.Frame(main_container, bg="#D0D0D0", height=22)
        title_frame.pack(fill=tk.X, side=tk.TOP)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="选择解决方案",
            font=("微软雅黑", 9, "bold"),
            bg="#D0D0D0",
            fg="#333333"
        )
        title_label.pack(pady=2)
        
        # 内容区域（白色背景）
        content_frame = tk.Frame(main_container, bg="white", padx=10, pady=6)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # 第一行：方案选择区域
        row1_frame = tk.Frame(content_frame, bg="white")
        row1_frame.pack(fill=tk.X, pady=(0, 6))
        
        # 左侧：方案ID选择
        solution_frame = tk.LabelFrame(
            row1_frame,
            text="解决方案ID",
            font=("微软雅黑", 8),
            bg="white",
            fg="#555555",
            padx=8,
            pady=3
        )
        solution_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        
        self.var_solution_name = tk.StringVar()
        self.combo_solution = ttk.Combobox(
            solution_frame,
            textvariable=self.var_solution_name,
            state="readonly",
            width=35,
            font=("微软雅黑", 9),
            height=8
        )
        self.combo_solution.pack(fill=tk.X, pady=1)
        self.combo_solution.bind("<<ComboboxSelected>>", self._on_solution_selected)
        
        # 右侧：加载解决方案按钮
        btn_load = tk.Button(
            row1_frame,
            text="加载解决方案",
            font=("微软雅黑", 9, "bold"),
            bg="#4A90E2",
            fg="white",
            relief=tk.RAISED,
            bd=2,
            padx=15,
            pady=6,
            cursor="hand2",
            command=self.load_solution
        )
        btn_load.pack(side=tk.LEFT, padx=3)
        
        # 第二行：其他操作按钮
        row2_frame = tk.Frame(content_frame, bg="white")
        row2_frame.pack(fill=tk.X)
        
        # 按钮容器（确保按钮在同一行）
        buttons_container = tk.Frame(row2_frame, bg="white")
        buttons_container.pack(fill=tk.X)
        
        # 开始新解决方案按钮
        btn_new = tk.Button(
            buttons_container,
            text="开始新解决方案",
            font=("微软雅黑", 9, "bold"),
            bg="#5CB85C",
            fg="white",
            relief=tk.RAISED,
            bd=2,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self.create_new_solution
        )
        btn_new.pack(side=tk.LEFT, padx=(0, 5))
        
        # 加载解决方案按钮（第二个，与第一行的不同）
        btn_load2 = tk.Button(
            buttons_container,
            text="生成报告",
            font=("微软雅黑", 9, "bold"),
            bg="#3498DB",
            fg="white",
            relief=tk.RAISED,
            bd=2,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self.save_solution
        )
        btn_load2.pack(side=tk.LEFT, padx=5)
        
        # 保存解决方案按钮
        btn_save = tk.Button(
            buttons_container,
            text="保存解决方案",
            font=("微软雅黑", 9, "bold"),
            bg="#F39C12",
            fg="white",
            relief=tk.RAISED,
            bd=2,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self.save_solution
        )
        btn_save.pack(side=tk.LEFT, padx=5)
        
        # 导入解决方案按钮
        btn_import = tk.Button(
            buttons_container,
            text="导入解决方案",
            font=("微软雅黑", 9, "bold"),
            bg="#9B59B6",
            fg="white",
            relief=tk.RAISED,
            bd=2,
            padx=12,
            pady=6,
            cursor="hand2",
            command=self.import_solution
        )
        btn_import.pack(side=tk.LEFT, padx=5)
    
    def refresh_solution_list(self):
        """刷新方案列表"""
        try:
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
            
        except Exception as e:
            pass
    
    def _on_solution_selected(self, event=None):
        """方案选择事件处理"""
        solution_name = self.var_solution_name.get()
        
        print(f"🔍 [SolutionPanel] _on_solution_selected 被调用")
        print(f"   方案名称: {solution_name}")
        
        if not solution_name:
            print(f"   ⚠️ 方案名称为空，退出")
            return
        
        # 验证方案目录是否存在
        solution_path = os.path.join(self.solutions_root, solution_name)
        print(f"   方案路径: {solution_path}")
        print(f"   路径存在: {os.path.exists(solution_path)}")
        
        if not os.path.exists(solution_path):
            messagebox.showwarning(
                "警告",
                f"方案 '{solution_name}' 的目录不存在！\n请刷新方案列表。"
            )
            return
        
        # 更新当前方案名
        self.current_solution_name = solution_name
        
        # 调用回调函数
        print(f"   回调函数存在: {self.on_solution_selected_callback is not None}")
        if self.on_solution_selected_callback:
            print(f"   ✅ 调用回调函数: {self.on_solution_selected_callback}")
            self.on_solution_selected_callback(solution_name)
        else:
            print(f"   ❌ 回调函数为 None")
    
    def create_new_solution(self):
        """创建新方案"""
        # 弹出输入对话框
        solution_name = simpledialog.askstring(
            "创建新方案",
            "请输入方案名称:",
            parent=self
        )
        
        # 用户取消输入
        if solution_name is None:
            return
        
        # 验证方案名
        solution_name = solution_name.strip()
        
        # 检查是否为空
        if not solution_name:
            messagebox.showwarning("警告", "方案名称不能为空！")
            return
        
        # 检查是否包含非法字符
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
        
        # 创建方案目录
        try:
            os.makedirs(solution_path)
            
            # 创建默认字段目录
            default_fields = ["CardNumber", "Name", "Date"]
            for field_type in default_fields:
                field_dir = os.path.join(solution_path, field_type)
                os.makedirs(field_dir)
            
            # 刷新方案列表
            self.refresh_solution_list()
            
            # 选中新创建的方案
            self.var_solution_name.set(solution_name)
            self.current_solution_name = solution_name
            self._on_solution_selected()
            
            messagebox.showinfo("成功", f"方案 '{solution_name}' 创建成功！")
            
        except Exception as e:
            messagebox.showerror("错误", f"创建方案失败:\n{str(e)}")
    
    def load_solution(self):
        """加载方案"""
        solution_name = self.var_solution_name.get()
        
        print(f"🔍 [SolutionPanel] load_solution 被调用")
        print(f"   方案名称: {solution_name}")
        
        if not solution_name:
            messagebox.showwarning("警告", "请先选择要加载的方案！")
            return
        
        # 验证方案目录是否存在
        solution_path = os.path.join(self.solutions_root, solution_name)
        print(f"   方案路径: {solution_path}")
        print(f"   路径存在: {os.path.exists(solution_path)}")
        
        if not os.path.exists(solution_path):
            messagebox.showwarning("警告", f"方案 '{solution_name}' 不存在！")
            return
        
        # 调用回调函数加载方案
        print(f"   回调函数存在: {self.on_solution_selected_callback is not None}")
        if self.on_solution_selected_callback:
            print(f"   ✅ 调用回调函数")
            self.on_solution_selected_callback(solution_name)
            messagebox.showinfo("成功", f"方案 '{solution_name}' 已加载！")
        else:
            print(f"   ❌ 回调函数为 None")
            messagebox.showwarning("警告", "无法加载方案：未设置回调函数")
    
    def save_solution(self):
        """保存方案"""
        if not self.current_solution_name:
            messagebox.showwarning("警告", "请先选择或创建一个方案！")
            return
        
        # 这里应该调用实际的保存逻辑
        # 目前只是显示提示信息
        messagebox.showinfo(
            "保存方案",
            f"方案 '{self.current_solution_name}' 保存功能待实现。\n\n"
            f"此功能将保存当前的布局配置和字符模板。"
        )
        print(f"💾 保存方案: {self.current_solution_name}")
    
    def import_solution(self):
        """导入方案"""
        # 选择要导入的方案目录
        import_path = filedialog.askdirectory(
            title="选择要导入的方案目录",
            parent=self
        )
        
        if not import_path:
            return
        
        # 获取方案名称（目录名）
        solution_name = os.path.basename(import_path)
        
        # 检查方案是否已存在
        target_path = os.path.join(self.solutions_root, solution_name)
        if os.path.exists(target_path):
            # 询问是否覆盖
            confirm = messagebox.askyesno(
                "确认覆盖",
                f"方案 '{solution_name}' 已存在。\n\n是否覆盖？",
                icon='warning'
            )
            if not confirm:
                return
            
            # 删除现有方案
            try:
                shutil.rmtree(target_path)
            except Exception as e:
                messagebox.showerror("错误", f"删除现有方案失败:\n{str(e)}")
                return
        
        # 复制方案目录
        try:
            shutil.copytree(import_path, target_path)
            
            # 刷新方案列表
            self.refresh_solution_list()
            
            # 选中导入的方案
            self.var_solution_name.set(solution_name)
            self.current_solution_name = solution_name
            
            messagebox.showinfo("成功", f"方案 '{solution_name}' 导入成功！")
            
        except Exception as e:
            messagebox.showerror("错误", f"导入方案失败:\n{str(e)}")
    
    def get_current_solution(self):
        """获取当前选中的方案名称"""
        return self.current_solution_name
    
    def set_current_solution(self, solution_name):
        """设置当前方案"""
        if solution_name:
            self.var_solution_name.set(solution_name)
            self.current_solution_name = solution_name
            self._on_solution_selected()
