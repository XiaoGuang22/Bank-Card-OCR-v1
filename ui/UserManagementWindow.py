import tkinter as tk
from tkinter import ttk, messagebox
import os

try:
    from managers.audit_log_manager import AuditLogManager as _AuditLogManager
except ImportError:
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from managers.audit_log_manager import AuditLogManager as _AuditLogManager
    except ImportError:
        _AuditLogManager = None

try:
    from managers.user_manager import UserManager as _UserManager
except ImportError:
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from managers.user_manager import UserManager as _UserManager
    except ImportError:
        _UserManager = None

class UserManagementWindow:
    def __init__(self, root, current_username, current_role, on_close):
        """初始化用户管理窗口
        
        Args:
            root: 父窗口
            current_username: 当前登录的用户名
            current_role: 当前用户角色
            on_close: 关闭窗口的回调函数
        """
        self.root = root
        self.current_username = current_username
        self.current_role = current_role
        self.on_close = on_close
        
        # 初始化用户管理器
        if _UserManager:
            self.user_manager = _UserManager()
        else:
            self.user_manager = None
        
        # 创建用户管理窗口
        self.window = tk.Toplevel(root)
        self.window.title("用户管理")
        self.window.geometry("600x400")
        self.window.resizable(False, False)
        
        # 窗口居中
        self._center_window()
        
        # 创建界面
        self._create_ui()
        
        # 加载用户数据
        self._load_users()
    
    def _center_window(self):
        """使窗口居中显示"""
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        
        window_width = 600
        window_height = 400
        
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        
        self.window.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    def _show_error_and_lift(self, title, message):
        """显示错误弹窗并在关闭后置顶窗口"""
        messagebox.showerror(title, message, parent=self.window)
        self.window.lift()
        self.window.focus_force()
    
    def _show_info_and_lift(self, title, message):
        """显示信息弹窗并在关闭后置顶窗口"""
        messagebox.showinfo(title, message, parent=self.window)
        self.window.lift()
        self.window.focus_force()
    
    def _create_ui(self):
        """创建用户管理界面"""
        main_frame = ttk.Frame(self.window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        title_label = ttk.Label(main_frame, text="用户管理", font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 20))
        
        list_frame = ttk.LabelFrame(main_frame, text="用户列表")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        self.tree = ttk.Treeview(list_frame, columns=("username", "role"), show="headings")
        self.tree.heading("username", text="用户名")
        self.tree.heading("role", text="角色")
        self.tree.column("username", width=200)
        self.tree.column("role", width=150)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        add_button = ttk.Button(button_frame, text="新增用户", command=self._add_user)
        add_button.pack(side=tk.LEFT, padx=5)
        
        edit_button = ttk.Button(button_frame, text="修改用户", command=self._edit_user)
        edit_button.pack(side=tk.LEFT, padx=5)
        
        delete_button = ttk.Button(button_frame, text="删除用户", command=self._delete_user)
        delete_button.pack(side=tk.LEFT, padx=5)
        
        refresh_button = ttk.Button(button_frame, text="刷新", command=self._load_users)
        refresh_button.pack(side=tk.LEFT, padx=5)
        
        close_button = ttk.Button(button_frame, text="关闭", command=self._close_window)
        close_button.pack(side=tk.RIGHT, padx=5)
    
    def _load_users(self):
        """加载用户数据到列表"""
        if not self.user_manager:
            self._show_error_and_lift("错误", "用户管理器初始化失败")
            return
        
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        try:
            users = self.user_manager.get_all_users()
            for user in users:
                self.tree.insert("", tk.END, values=(user["username"], user["role"]))
        except Exception as e:
            self._show_error_and_lift("错误", f"读取用户数据失败: {e}")
    
    def _add_user(self):
        """新增用户"""
        add_window = tk.Toplevel(self.window)
        add_window.title("新增用户")
        add_window.resizable(False, False)
        
        screen_width = add_window.winfo_screenwidth()
        screen_height = add_window.winfo_screenheight()
        
        window_width = 400
        window_height = 300
        
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        
        add_window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        frame = ttk.Frame(add_window, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="用户名:").pack(anchor="w", pady=(0, 5))
        username_var = tk.StringVar()
        ttk.Entry(frame, textvariable=username_var).pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(frame, text="密码:").pack(anchor="w", pady=(0, 5))
        password_var = tk.StringVar()
        ttk.Entry(frame, textvariable=password_var, show="*").pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(frame, text="角色:").pack(anchor="w", pady=(0, 5))
        role_var = tk.StringVar()
        role_combobox = ttk.Combobox(frame, textvariable=role_var, values=["管理员", "技术员", "操作员"])
        role_combobox.current(2)
        role_combobox.pack(fill=tk.X, pady=(0, 20))
        
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X)
        
        def save_user():
            username = username_var.get().strip()
            password = password_var.get()
            role = role_var.get()
            
            if not username or not password:
                self._show_error_and_lift("错误", "请输入用户名和密码")
                return
            
            success, message = self.user_manager.add_user(username, password, role)
            if success:
                self._show_info_and_lift("成功", message)
                self._audit("add_user", target=username, new_value=role)
                add_window.destroy()
                self._load_users()
            else:
                self._show_error_and_lift("错误", message)
        
        save_button = ttk.Button(button_frame, text="保存", command=save_user)
        save_button.pack(side=tk.LEFT, padx=5)
        
        cancel_button = ttk.Button(button_frame, text="取消", command=add_window.destroy)
        cancel_button.pack(side=tk.RIGHT, padx=5)
    
    def _edit_user(self):
        """修改用户"""
        selected_item = self.tree.selection()
        if not selected_item:
            self._show_info_and_lift("提示", "请选择要修改的用户")
            return
        
        item = selected_item[0]
        username = self.tree.item(item, "values")[0]
        
        edit_window = tk.Toplevel(self.window)
        edit_window.title("修改用户")
        edit_window.resizable(False, False)
        
        screen_width = edit_window.winfo_screenwidth()
        screen_height = edit_window.winfo_screenheight()
        
        window_width = 400
        window_height = 300
        
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        
        edit_window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        frame = ttk.Frame(edit_window, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="用户名:").pack(anchor="w", pady=(0, 5))
        username_var = tk.StringVar(value=username)
        ttk.Entry(frame, textvariable=username_var, state="readonly").pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(frame, text="新密码:").pack(anchor="w", pady=(0, 5))
        password_var = tk.StringVar()
        ttk.Entry(frame, textvariable=password_var, show="*").pack(fill=tk.X, pady=(0, 15))
        ttk.Label(frame, text="（留空表示不修改密码）", font=("Arial", 8, "italic")).pack(anchor="w")
        
        ttk.Label(frame, text="角色:").pack(anchor="w", pady=(0, 5))
        user = self.user_manager.get_user(username)
        role_var = tk.StringVar(value=user["role"] if user else "")
        role_combobox = ttk.Combobox(frame, textvariable=role_var, values=["管理员", "技术员", "操作员"])
        role_combobox.pack(fill=tk.X, pady=(0, 20))
        
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X)
        
        def save_changes():
            password = password_var.get()
            role = role_var.get()
            
            if not password and role == user["role"]:
                self._show_error_and_lift("错误", "至少需要修改一项")
                return
            
            success, message = self.user_manager.update_user(username, password if password else None, role)
            if success:
                self._show_info_and_lift("成功", message)
                if role != user["role"]:
                    self._audit("modify_role", target=username, old_value=user["role"], new_value=role)
                if password:
                    self._audit("modify_password", target=username)
                edit_window.destroy()
                self._load_users()
            else:
                self._show_error_and_lift("错误", message)
        
        save_button = ttk.Button(button_frame, text="保存", command=save_changes)
        save_button.pack(side=tk.LEFT, padx=5)
        
        cancel_button = ttk.Button(button_frame, text="取消", command=edit_window.destroy)
        cancel_button.pack(side=tk.RIGHT, padx=5)
    
    def _delete_user(self):
        """删除用户"""
        selected_item = self.tree.selection()
        if not selected_item:
            self._show_info_and_lift("提示", "请选择要删除的用户")
            return
        
        item = selected_item[0]
        username = self.tree.item(item, "values")[0]
        
        if username == self.current_username and self.current_role == "管理员":
            self._show_error_and_lift("错误", "不能删除当前登录的管理员账号")
            return
        
        if messagebox.askyesno("确认", f"确定要删除用户 '{username}' 吗？", parent=self.window):
            success, message = self.user_manager.delete_user(username)
            if success:
                self._show_info_and_lift("成功", message)
                self._audit("delete_user", target=username)
                self._load_users()
            else:
                self._show_error_and_lift("错误", message)
            
            self.window.lift()
            self.window.focus_force()
    
    def _close_window(self):
        """关闭窗口"""
        self.window.destroy()
        if self.on_close:
            self.on_close()

    def _audit(self, action, target="", old_value="", new_value="", result="成功"):
        """写入用户管理操作日志"""
        if _AuditLogManager:
            try:
                _AuditLogManager().log(
                    user_name=self.current_username,
                    user_role=self.current_role,
                    operation_type="user_management",
                    operation_action=action,
                    target_object=target,
                    old_value=old_value,
                    new_value=new_value,
                    operation_result=result,
                )
            except Exception:
                pass
