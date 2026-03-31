# 导入必要的库
import tkinter as tk  # 导入tkinter库，用于创建图形用户界面
from tkinter import ttk, messagebox  # 导入ttk组件和消息框功能
import json  # 导入json库，用于读写JSON格式的文件
import os  # 导入os库，用于文件路径操作
import hashlib  # 导入hashlib库，用于对密码进行哈希处理

try:
    from managers.audit_log_manager import AuditLogManager as _AuditLogManager
except ImportError:
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from managers.audit_log_manager import AuditLogManager as _AuditLogManager
    except ImportError:
        _AuditLogManager = None

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
        
        # 确保用户数据文件存在
        self._ensure_user_file_exists()
        
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
    
    # 确保用户数据文件存在的方法
    def _ensure_user_file_exists(self):
        """确保用户数据文件存在，如果不存在则创建默认用户"""
        # 获取当前文件的目录路径，然后再获取上级目录
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 构建用户数据文件的完整路径
        self.user_file = os.path.join(base_dir, "users.json")
        
        # 检查用户数据文件是否存在
        if not os.path.exists(self.user_file):
            # 如果文件不存在，创建默认管理员用户
            default_users = {
                "admin": {
                    # 对默认密码进行哈希处理
                    "password": self._hash_password("admin123456"),
                    # 设置用户角色
                    "role": "管理员"
                }
            }
            
            # 打开文件并写入默认用户数据
            with open(self.user_file, 'w', encoding='utf-8') as f:
                # 使用json.dump将字典转换为JSON格式并写入文件
                json.dump(default_users, f, ensure_ascii=False, indent=2)
    
    # 对密码进行哈希处理的方法
    def _hash_password(self, password):
        """对密码进行哈希处理，增强安全性"""
        # 使用MD5算法对密码进行哈希处理
        # 1. 先将密码字符串转换为字节
        # 2. 使用md5()函数计算哈希值
        # 3. 使用hexdigest()方法获取十六进制格式的哈希值
        return hashlib.md5(password.encode()).hexdigest()
    
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
        
        # 读取用户数据
        try:
            # 打开用户数据文件
            with open(self.user_file, 'r', encoding='utf-8') as f:
                # 加载JSON数据到字典
                users = json.load(f)
        except Exception as e:
            # 显示错误消息
            messagebox.showerror("错误", f"读取用户数据失败: {e}")
            # 终止登录流程
            return
        
        # 验证用户名是否存在
        if username not in users:
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
        
        # 对输入的密码进行哈希处理
        hashed_password = self._hash_password(password)
        # 比较密码哈希值是否匹配
        if users[username]["password"] != hashed_password:
            # 记录登录失败日志
            if _AuditLogManager:
                try:
                    role = users[username].get("role", "未知")
                    _AuditLogManager().log(username, role, "login", "login_failed",
                                           target_object="密码错误", operation_result="失败")
                except Exception:
                    pass
            # 显示错误消息
            messagebox.showerror("错误", "密码错误")
            # 终止登录流程
            return
        
        # 登录成功，获取用户角色
        user_role = users[username]["role"]
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