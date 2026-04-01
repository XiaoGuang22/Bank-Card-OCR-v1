
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
        super().__init__(parent, bg="white")
        
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
        """设置UI布局 - 左右两列，高度自适应内容"""
        main_container = tk.Frame(self, bg="white", relief=tk.RIDGE, bd=1)
        main_container.pack(fill=tk.X, padx=3, pady=3)

        # 标题
        title_frame = tk.Frame(main_container, bg="#D0D0D0", height=22)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        tk.Label(title_frame, text="解决方案管理", font=("微软雅黑", 9, "bold"),
                 bg="#D0D0D0", fg="#333").pack(pady=2)

        content = tk.Frame(main_container, bg="white", padx=8, pady=8)
        content.pack(anchor="w")  # 不撑满，靠左紧凑

        # 两列不拉伸，紧凑排列
        # ── 左列：新建解决方案 ──
        new_frame = tk.LabelFrame(content, text="新建解决方案", font=("微软雅黑", 9),
                                  bg="white", fg="#555", padx=8, pady=6)
        new_frame.grid(row=0, column=0, sticky="nw", padx=(0, 12))

        tk.Label(new_frame, text="名称:", bg="white", font=("微软雅黑", 10)).grid(
            row=0, column=0, sticky="w", pady=4)
        self.var_new_name = tk.StringVar()
        tk.Entry(new_frame, textvariable=self.var_new_name, font=("微软雅黑", 10), width=26
                 ).grid(row=0, column=1, columnspan=2, sticky="w", padx=(6, 0), pady=4)

        tk.Label(new_frame, text="描述:", bg="white", font=("微软雅黑", 10)).grid(
            row=1, column=0, sticky="nw", pady=4)
        self.txt_new_desc = tk.Text(new_frame, font=("微软雅黑", 10), width=24, height=4,
                                    relief=tk.SOLID, bd=1)
        self.txt_new_desc.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=4)

        btn_row = tk.Frame(new_frame, bg="white")
        btn_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        tk.Button(btn_row, text="新建", font=("微软雅黑", 10, "bold"),
                  bg="#5CB85C", fg="white", relief=tk.RAISED, padx=20, pady=5,
                  cursor="hand2", command=self.create_new_solution
                  ).pack(anchor="center")

        # ── 右列：解决方案列表 + 按钮 ──
        right_frame = tk.LabelFrame(content, text="库中解决方案", font=("微软雅黑", 10),
                                    bg="white", fg="#555", padx=10, pady=8)
        right_frame.grid(row=0, column=1, sticky="nw", padx=(0, 0))

        # 下拉列表
        self.var_solution_name = tk.StringVar()
        self.combo_solution = ttk.Combobox(right_frame, textvariable=self.var_solution_name,
                                           state="readonly", font=("微软雅黑", 10), width=22)
        self.combo_solution.pack(fill=tk.X, pady=(0, 8))
        self.combo_solution.bind("<<ComboboxSelected>>", self._on_solution_selected)

        # 三个按钮
        tk.Button(right_frame, text="加载", font=("微软雅黑", 10, "bold"),
                  bg="#4A90E2", fg="white", relief=tk.RAISED, pady=5,
                  cursor="hand2", command=self.load_solution
                  ).pack(fill=tk.X, pady=(0, 4))

        tk.Button(right_frame, text="删除", font=("微软雅黑", 10, "bold"),
                  bg="#E74C3C", fg="white", relief=tk.RAISED, pady=5,
                  cursor="hand2", command=self._delete_solution
                  ).pack(fill=tk.X, pady=(0, 4))

        tk.Button(right_frame, text="导入", font=("微软雅黑", 10, "bold"),
                  bg="#9B59B6", fg="white", relief=tk.RAISED, pady=5,
                  cursor="hand2", command=self.import_solution
                  ).pack(fill=tk.X)

    def _delete_solution(self):
        """删除选中的解决方案"""
        solution_name = self.var_solution_name.get()
        if not solution_name:
            messagebox.showwarning("警告", "请先选择要删除的方案！")
            return
        if not messagebox.askyesno("确认删除", f"确定要删除方案 '{solution_name}' 吗？\n此操作不可恢复！", icon='warning'):
            return
        try:
            shutil.rmtree(os.path.join(self.solutions_root, solution_name))
            self.var_solution_name.set("")
            self.current_solution_name = None
            self.refresh_solution_list()
            messagebox.showinfo("成功", f"方案 '{solution_name}' 已删除")
        except Exception as e:
            messagebox.showerror("错误", f"删除失败:\n{str(e)}")

    def refresh_solution_list(self):
        """刷新方案列表"""
        try:
            if not os.path.exists(self.solutions_root):
                os.makedirs(self.solutions_root)
                solution_names = []
            else:
                solution_names = sorted([
                    name for name in os.listdir(self.solutions_root)
                    if os.path.isdir(os.path.join(self.solutions_root, name))
                ])

            # 更新 listbox
            if hasattr(self, 'solution_listbox'):
                self.solution_listbox.delete(0, tk.END)
                for name in solution_names:
                    self.solution_listbox.insert(tk.END, name)

            # 兼容旧 combo_solution
            if hasattr(self, 'combo_solution'):
                self.combo_solution['values'] = solution_names

        except Exception:
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
        solution_name = self.var_new_name.get().strip() if hasattr(self, 'var_new_name') else ""
        if not solution_name:
            solution_name = simpledialog.askstring("创建新方案", "请输入方案名称:", parent=self)
        if not solution_name:
            return
        solution_name = solution_name.strip()
        if not solution_name:
            messagebox.showwarning("警告", "方案名称不能为空！")
            return

        invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
        if any(c in solution_name for c in invalid_chars):
            messagebox.showwarning("警告", f"方案名称不能包含: {' '.join(invalid_chars)}")
            return

        solution_path = os.path.join(self.solutions_root, solution_name)
        if os.path.exists(solution_path):
            messagebox.showwarning("警告", f"方案 '{solution_name}' 已存在！")
            return

        try:
            os.makedirs(solution_path)
            for field_type in ["CardNumber", "Name", "Date"]:
                os.makedirs(os.path.join(solution_path, field_type))

            # 保存描述到 readme
            desc = self.txt_new_desc.get("1.0", tk.END).strip() if hasattr(self, 'txt_new_desc') else \
                   (self.var_new_desc.get().strip() if hasattr(self, 'var_new_desc') else "")
            if desc:
                with open(os.path.join(solution_path, "description.txt"), "w", encoding="utf-8") as f:
                    f.write(desc)

            # 清空输入框
            if hasattr(self, 'var_new_name'):
                self.var_new_name.set("")
            if hasattr(self, 'txt_new_desc'):
                self.txt_new_desc.delete("1.0", tk.END)
            elif hasattr(self, 'var_new_desc'):
                self.var_new_desc.set("")

            self.refresh_solution_list()
            self.var_solution_name.set(solution_name)
            self.current_solution_name = solution_name
            self._on_solution_selected()
            messagebox.showinfo("成功", f"方案 '{solution_name}' 创建成功！")

        except Exception as e:
            messagebox.showerror("错误", f"创建方案失败:\n{str(e)}")
    
    def load_solution(self):
        """加载方案"""
        # 优先从 listbox 取选中项
        solution_name = None
        if hasattr(self, 'solution_listbox'):
            sel = self.solution_listbox.curselection()
            if sel:
                solution_name = self.solution_listbox.get(sel[0])
        if not solution_name:
            solution_name = self.var_solution_name.get()

        if not solution_name:
            messagebox.showwarning("警告", "请先在列表中选择要加载的方案！")
            return

        solution_path = os.path.join(self.solutions_root, solution_name)
        if not os.path.exists(solution_path):
            messagebox.showwarning("警告", f"方案 '{solution_name}' 不存在！")
            return

        self.current_solution_name = solution_name
        self.var_solution_name.set(solution_name)

        if self.on_solution_selected_callback:
            self.on_solution_selected_callback(solution_name)
            messagebox.showinfo("成功", f"方案 '{solution_name}' 已加载！")
        else:
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
