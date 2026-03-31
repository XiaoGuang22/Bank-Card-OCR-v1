import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import hashlib

try:
    from managers.audit_log_manager import AuditLogManager as _AuditLogManager
except ImportError:
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from managers.audit_log_manager import AuditLogManager as _AuditLogManager
    except ImportError:
        _AuditLogManager = None

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
        
        # 确保用户数据文件存在
        self._ensure_user_file_exists()
        
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
        # 获取屏幕宽度和高度
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        
        # 窗口宽度和高度
        window_width = 600
        window_height = 400
        
        # 计算窗口在屏幕上的X坐标（屏幕宽度的一半减去窗口宽度的一半）
        x = (screen_width // 2) - (window_width // 2)
        # 计算窗口在屏幕上的Y坐标（屏幕高度的一半减去窗口高度的一半）
        y = (screen_height // 2) - (window_height // 2)
        
        # 直接设置窗口的位置和大小，避免先显示在左上角
        self.window.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    def _ensure_user_file_exists(self):
        """确保用户数据文件存在"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.user_file = os.path.join(base_dir, "users.json")
        if not os.path.exists(self.user_file):
            default_users = {
                "admin": {
                    "password": self._hash_password("admin123456"),
                    "role": "管理员"
                }
            }
            with open(self.user_file, 'w', encoding='utf-8') as f:
                json.dump(default_users, f, ensure_ascii=False, indent=2)
    
    def _hash_password(self, password):
        """对密码进行哈希处理"""
        return hashlib.md5(password.encode()).hexdigest()
    
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
        # 主框架
        main_frame = ttk.Frame(self.window, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        title_label = ttk.Label(main_frame, text="用户管理", font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 20))
        
        # 用户列表框架
        list_frame = ttk.LabelFrame(main_frame, text="用户列表")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # 列表控件
        self.tree = ttk.Treeview(list_frame, columns=("username", "role"), show="headings")
        self.tree.heading("username", text="用户名")
        self.tree.heading("role", text="角色")
        self.tree.column("username", width=200)
        self.tree.column("role", width=150)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # 按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        # 新增用户按钮
        add_button = ttk.Button(button_frame, text="新增用户", command=self._add_user)
        add_button.pack(side=tk.LEFT, padx=5)
        
        # 修改用户按钮
        edit_button = ttk.Button(button_frame, text="修改用户", command=self._edit_user)
        edit_button.pack(side=tk.LEFT, padx=5)
        
        # 删除用户按钮
        delete_button = ttk.Button(button_frame, text="删除用户", command=self._delete_user)
        delete_button.pack(side=tk.LEFT, padx=5)
        
        # 刷新按钮
        refresh_button = ttk.Button(button_frame, text="刷新", command=self._load_users)
        refresh_button.pack(side=tk.LEFT, padx=5)
        
        # 关闭按钮
        close_button = ttk.Button(button_frame, text="关闭", command=self._close_window)
        close_button.pack(side=tk.RIGHT, padx=5)
    
    def _load_users(self):
        """加载用户数据到列表"""
        # 清空现有数据
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 读取用户数据
        try:
            with open(self.user_file, 'r', encoding='utf-8') as f:
                self.users = json.load(f)
            
            # 添加到列表
            for username, user_info in self.users.items():
                self.tree.insert("", tk.END, values=(username, user_info["role"]))
        except Exception as e:
            self._show_error_and_lift("错误", f"读取用户数据失败: {e}")
    
    def _add_user(self):
        """新增用户"""
        # 创建新增用户窗口
        add_window = tk.Toplevel(self.window)
        add_window.title("新增用户")
        add_window.resizable(False, False)
        
        # 居中显示
        # 获取屏幕宽度和高度
        screen_width = add_window.winfo_screenwidth()
        screen_height = add_window.winfo_screenheight()
        
        # 窗口宽度和高度
        window_width = 400
        window_height = 300
        
        # 计算窗口在屏幕上的X坐标（屏幕宽度的一半减去窗口宽度的一半）
        x = (screen_width // 2) - (window_width // 2)
        # 计算窗口在屏幕上的Y坐标（屏幕高度的一半减去窗口高度的一半）
        y = (screen_height // 2) - (window_height // 2)
        
        # 直接设置窗口的位置和大小，避免先显示在左上角
        add_window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # 框架
        frame = ttk.Frame(add_window, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # 用户名
        ttk.Label(frame, text="用户名:").pack(anchor="w", pady=(0, 5))
        username_var = tk.StringVar()
        ttk.Entry(frame, textvariable=username_var).pack(fill=tk.X, pady=(0, 15))
        
        # 密码
        ttk.Label(frame, text="密码:").pack(anchor="w", pady=(0, 5))
        password_var = tk.StringVar()
        ttk.Entry(frame, textvariable=password_var, show="*").pack(fill=tk.X, pady=(0, 15))
        
        # 角色
        ttk.Label(frame, text="角色:").pack(anchor="w", pady=(0, 5))
        role_var = tk.StringVar()
        role_combobox = ttk.Combobox(frame, textvariable=role_var, values=["管理员", "技术员", "操作员"])
        role_combobox.current(2)  # 默认选择操作员
        role_combobox.pack(fill=tk.X, pady=(0, 20))
        
        # 按钮框架
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X)
        
        def save_user():
            """保存新用户"""
            username = username_var.get().strip()
            password = password_var.get()
            role = role_var.get()
            
            if not username or not password:
                self._show_error_and_lift("错误", "请输入用户名和密码")
                return
            
            if username in self.users:
                self._show_error_and_lift("错误", "用户名已存在")
                return
            
            # 添加新用户
            self.users[username] = {
                "password": self._hash_password(password),
                "role": role
            }
            
            # 保存到文件
            try:
                with open(self.user_file, 'w', encoding='utf-8') as f:
                    json.dump(self.users, f, ensure_ascii=False, indent=2)
                self._show_info_and_lift("成功", "用户添加成功")
                self._audit("add_user", target=username, new_value=role)
                add_window.destroy()
                self._load_users()
            except Exception as e:
                self._show_error_and_lift("错误", f"保存用户数据失败: {e}")
        
        # 保存按钮
        save_button = ttk.Button(button_frame, text="保存", command=save_user)
        save_button.pack(side=tk.LEFT, padx=5)
        
        # 取消按钮
        cancel_button = ttk.Button(button_frame, text="取消", command=add_window.destroy)
        cancel_button.pack(side=tk.RIGHT, padx=5)
    
    def _edit_user(self):
        """修改用户"""
        # 获取选中的用户
        selected_item = self.tree.selection()
        if not selected_item:
            self._show_info_and_lift("提示", "请选择要修改的用户")
            return
        
        # 获取用户名
        item = selected_item[0]
        username = self.tree.item(item, "values")[0]
        
        # 创建修改用户窗口
        edit_window = tk.Toplevel(self.window)
        edit_window.title("修改用户")
        edit_window.resizable(False, False)
        
        # 居中显示
        # 获取屏幕宽度和高度
        screen_width = edit_window.winfo_screenwidth()
        screen_height = edit_window.winfo_screenheight()
        
        # 窗口宽度和高度
        window_width = 400
        window_height = 300
        
        # 计算窗口在屏幕上的X坐标（屏幕宽度的一半减去窗口宽度的一半）
        x = (screen_width // 2) - (window_width // 2)
        # 计算窗口在屏幕上的Y坐标（屏幕高度的一半减去窗口高度的一半）
        y = (screen_height // 2) - (window_height // 2)
        
        # 直接设置窗口的位置和大小，避免先显示在左上角
        edit_window.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        # 框架
        frame = ttk.Frame(edit_window, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # 用户名（可编辑）
        ttk.Label(frame, text="用户名:").pack(anchor="w", pady=(0, 5))
        username_var = tk.StringVar(value=username)
        ttk.Entry(frame, textvariable=username_var).pack(fill=tk.X, pady=(0, 15))
        
        # 密码（可选修改）
        ttk.Label(frame, text="新密码:").pack(anchor="w", pady=(0, 5))
        password_var = tk.StringVar()
        ttk.Entry(frame, textvariable=password_var, show="*").pack(fill=tk.X, pady=(0, 15))
        ttk.Label(frame, text="（留空表示不修改密码）", font=("Arial", 8, "italic")).pack(anchor="w")
        
        # 角色
        ttk.Label(frame, text="角色:").pack(anchor="w", pady=(0, 5))
        role_var = tk.StringVar(value=self.users[username]["role"])
        role_combobox = ttk.Combobox(frame, textvariable=role_var, values=["管理员", "技术员", "操作员"])
        role_combobox.pack(fill=tk.X, pady=(0, 20))
        
        # 按钮框架
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X)
        
        def save_changes():
            """保存修改"""
            new_username = username_var.get().strip()
            password = password_var.get()
            role = role_var.get()
            
            if not new_username:
                self._show_error_and_lift("错误", "用户名不能为空")
                return
            
            # 检查新用户名是否已存在（如果用户名发生变化）
            if new_username != username and new_username in self.users:
                self._show_error_and_lift("错误", "用户名已存在")
                return
            
            # 检查是否至少修改了一项（用户名、密码或角色）
            username_changed = (new_username != username)
            password_changed = bool(password)
            role_changed = (role != self.users[username]["role"])
            
            if not username_changed and not password_changed and not role_changed:
                self._show_error_and_lift("错误", "至少需要修改一项")
                return
            
            # 如果角色改为管理员，检查是否已存在其他管理员
            if role == "管理员":
                for uname, uinfo in self.users.items():
                    if uname != username and uinfo.get("role") == "管理员":
                        self._show_error_and_lift("错误", "管理员已存在")
                        return
            
            # 更新用户信息
            if new_username != username:
                # 用户名发生变化，需要删除旧用户并创建新用户
                user_info = self.users[username].copy()
                del self.users[username]
                if password:
                    user_info["password"] = self._hash_password(password)
                user_info["role"] = role
                self.users[new_username] = user_info
            else:
                # 用户名未变化，直接更新
                if password:
                    self.users[username]["password"] = self._hash_password(password)
                self.users[username]["role"] = role
            
            # 保存到文件
            try:
                with open(self.user_file, 'w', encoding='utf-8') as f:
                    json.dump(self.users, f, ensure_ascii=False, indent=2)
                self._show_info_and_lift("成功", "用户修改成功")
                # 记录修改日志
                if role_changed:
                    self._audit("modify_role", target=new_username,
                                old_value=self.users.get(username, {}).get("role", ""),
                                new_value=role)
                if password_changed:
                    self._audit("modify_password", target=new_username)
                edit_window.destroy()
                self._load_users()
            except Exception as e:
                self._show_error_and_lift("错误", f"保存用户数据失败: {e}")
        
        # 保存按钮
        save_button = ttk.Button(button_frame, text="保存", command=save_changes)
        save_button.pack(side=tk.LEFT, padx=5)
        
        # 取消按钮
        cancel_button = ttk.Button(button_frame, text="取消", command=edit_window.destroy)
        cancel_button.pack(side=tk.RIGHT, padx=5)
    
    def _delete_user(self):
        """删除用户"""
        # 获取选中的用户
        selected_item = self.tree.selection()
        if not selected_item:
            self._show_info_and_lift("提示", "请选择要删除的用户")
            return
        
        # 获取用户名
        item = selected_item[0]
        username = self.tree.item(item, "values")[0]
        
        # 检查是否是当前登录的管理员
        if username == self.current_username and self.current_role == "管理员":
            self._show_error_and_lift("错误", "不能删除当前登录的管理员账号")
            return
        
        # 确认删除
        if messagebox.askyesno("确认", f"确定要删除用户 '{username}' 吗？", parent=self.window):
            # 删除用户
            del self.users[username]
            
            # 保存到文件
            try:
                with open(self.user_file, 'w', encoding='utf-8') as f:
                    json.dump(self.users, f, ensure_ascii=False, indent=2)
                self._show_info_and_lift("成功", "用户删除成功")
                self._audit("delete_user", target=username)
                self._load_users()
            except Exception as e:
                self._show_error_and_lift("错误", f"保存用户数据失败: {e}")
            
            # 置顶窗口
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