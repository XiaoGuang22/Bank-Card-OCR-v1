# 导入必要的库
import tkinter as tk  # 导入tkinter库，用于创建图形用户界面
from tkinter import ttk, messagebox  # 导入ttk组件和消息框功能
import os  # 导入os库，用于文件路径操作

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

# 定义登录窗口类
class LoginWindow:
    # 初始化函数，创建登录窗口时会自动调用
    def __init__(self, root, on_login_success):
        # 保存根窗口的引用
        self.root = root
        # 保存登录成功后的回调函数
        self.on_login_success = on_login_success
        # 设置窗口标题
        self.root.title("用户登录")
        # 设置窗口大小为400x350像素
        self.root.geometry("400x350")
        # 禁止调整窗口大小
        self.root.resizable(False, False)
        
        # 调用窗口居中方法
        self._center_window()
        
        # 初始化用户管理器
        if _UserManager:
            self.user_manager = _UserManager()
            self.user_manager.init_default_users()
        else:
            self.user_manager = None
        
        # 创建登录界面
        self._create_login_ui()
    
    # 使窗口在屏幕中央显示的方法
    def _center_window(self):
        """使窗口在屏幕中央显示"""
        # 获取屏幕宽度和高度
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # 窗口宽度和高度
        window_width = 400
        window_height = 350
        
        # 计算窗口在屏幕上的X坐标（屏幕宽度的一半减去窗口宽度的一半）
        x = (screen_width // 2) - (window_width // 2)
        # 计算窗口在屏幕上的Y坐标（屏幕高度的一半减去窗口高度的一半）
        y = (screen_height // 2) - (window_height // 2)
        
        # 直接设置窗口的位置和大小，避免先显示在左上角
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    # 创建登录界面的方法
    def _create_login_ui(self):
        """创建登录界面的各个组件"""
        # 创建主框架，设置内边距为40像素
        main_frame = ttk.Frame(self.root, padding="40")
        # 将主框架填充整个窗口
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建标题标签
        title_label = ttk.Label(main_frame, text="银行卡识别系统", font=('Arial', 16, 'bold'))
        # 显示标题，设置下边距为30像素
        title_label.pack(pady=(0, 30))
        
        # 创建表单框架
        form_frame = ttk.Frame(main_frame)
        # 将表单框架填充水平方向
        form_frame.pack(fill=tk.X)
        
        # 创建用户名标签
        ttk.Label(form_frame, text="用户名:").pack(anchor="w", pady=(0, 5))
        # 创建存储用户名的字符串变量
        self.username_var = tk.StringVar()
        # 创建用户名输入框
        username_entry = ttk.Entry(form_frame, textvariable=self.username_var, width=30)
        # 显示输入框，设置下边距为15像素
        username_entry.pack(fill=tk.X, pady=(0, 15))
        
        # 创建密码标签
        ttk.Label(form_frame, text="密码:").pack(anchor="w", pady=(0, 5))
        # 创建存储密码的字符串变量
        self.password_var = tk.StringVar()
        # 创建密码输入框，show="*"表示输入的内容显示为*
        password_entry = ttk.Entry(form_frame, textvariable=self.password_var, show="*", width=30)
        # 显示输入框，设置下边距为20像素
        password_entry.pack(fill=tk.X, pady=(0, 20))
        
        # 创建登录按钮，点击时调用_login方法
        login_button = ttk.Button(form_frame, text="登录", command=self._login)
        # 显示按钮，设置下边距为10像素
        login_button.pack(fill=tk.X, pady=(0, 10))
        
        # 绑定回车键，按下回车键时触发登录
        self.root.bind('<Return>', lambda event: self._login())
    
    # 登录验证的方法
    def _login(self):
        """验证用户登录信息"""
        # 获取输入的用户名并去除首尾空格
        username = self.username_var.get().strip()
        # 获取输入的密码
        password = self.password_var.get()
        
        # 检查用户名和密码是否为空
        if not username or not password:
            # 显示错误消息
            messagebox.showerror("错误", "请输入用户名和密码")
            # 终止登录流程
            return
        
        # 使用用户管理器验证
        if not self.user_manager:
            messagebox.showerror("错误", "用户管理器初始化失败")
            return
        
        # 验证用户名是否存在
        user = self.user_manager.get_user(username)
        if not user:
            # 记录登录失败日志
            if _AuditLogManager:
                try:
                    _AuditLogManager().log(username, "未知", "login", "login_failed",
                                           target_object="用户名不存在", operation_result="失败")
                except Exception:
                    pass
            # 显示错误消息
            messagebox.showerror("错误", "用户名不存在")
            # 终止登录流程
            return
        
        # 验证密码
        if not self.user_manager.verify_password(username, password):
            # 记录登录失败日志
            if _AuditLogManager:
                try:
                    _AuditLogManager().log(username, user["role"], "login", "login_failed",
                                           target_object="密码错误", operation_result="失败")
                except Exception:
                    pass
            # 显示错误消息
            messagebox.showerror("错误", "密码错误")
            # 终止登录流程
            return
        
        # 登录成功，获取用户角色
        user_role = user["role"]
        # 记录登录成功日志
        if _AuditLogManager:
            try:
                _AuditLogManager().log(username, user_role, "login", "login_success",
                                       operation_result="成功")
            except Exception:
                pass
        # 关闭登录窗口
        self.root.destroy()
        # 调用登录成功回调函数，传递用户名和角色
        self.on_login_success(username, user_role)