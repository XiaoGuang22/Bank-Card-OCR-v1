"""
控制按钮面板

提供运行时设置按钮（选择解决方案、编辑容忍度等）
"""

import tkinter as tk
from tkinter import ttk

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


class ControlButtonsPanel(tk.Frame):
    """控制按钮面板类
    
    提供运行时设置按钮，包括选择解决方案、编辑容忍度、设置显示、
    历史数据回顾、重置检测、重置统计数据、手动触发和开始按钮。
    
    验证需求: 5.1-5.9
    """
    
    def __init__(self, parent, callbacks=None):
        """初始化控制按钮面板
        
        参数:
            parent: 父窗口
            callbacks: 按钮回调函数字典，键为按钮名称，值为回调函数
                      支持的按钮名称：
                      - "select_solution": 选择解决方案
                      - "edit_tolerance": 编辑容忍度
                      - "display_settings": 设置显示
                      - "history_review": 历史数据回顾
                      - "reset_detection": 重置检测
                      - "reset_statistics": 重置统计数据
                      - "manual_trigger": 手动触发
                      - "start": 开始
        """
        super().__init__(parent, bg="white")
        
        # 回调函数字典
        self._callbacks = callbacks or {}
        
        # 按钮引用字典
        self._buttons = {}
        
        # 开始按钮引用
        self._start_button = None
        
        self._init_ui()
    
    def _init_ui(self):
        """初始化UI布局"""
        # 按钮容器
        buttons_container = tk.Frame(self, bg="white")
        buttons_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 创建按钮（2行4列布局，按照参考图片排列）
        # 第一行：选择解决方案、编辑容忍度、设置显示、历史数据回顾
        # 第二行：重置检测、重置统计数据、手动触发、开始
        button_configs = [
            # 第一行（原第二行）
            [
                ("reset_detection", "打开图片"),
                ("reset_statistics", "重置\n统计数据"),
                ("manual_trigger", "手动触发"),
                ("start", "▶ 开始"),
            ]
        ]
        
        # 创建按钮
        for row_idx, row_buttons in enumerate(button_configs):
            for col_idx, (key, text) in enumerate(row_buttons):
                # 开始按钮使用特殊样式（绿色）
                if key == "start":
                    btn = tk.Button(
                        buttons_container,
                        text=text,
                        font=("Microsoft YaHei UI", 10, "bold"),  # 增大字体
                        bg="#4CAF50",  # 绿色
                        fg="white",
                        relief=tk.RAISED,
                        bd=1,
                        padx=8,
                        pady=15,  # 增加高度
                        cursor="hand2",
                        command=lambda k=key: self._on_button_click(k)
                    )
                else:
                    btn = tk.Button(
                        buttons_container,
                        text=text,
                        font=("Microsoft YaHei UI", 9),  # 增大字体
                        bg="#f5f5f5",
                        fg="#333",
                        relief=tk.RAISED,
                        bd=1,
                        padx=8,
                        pady=15,  # 增加高度
                        cursor="hand2",
                        command=lambda k=key: self._on_button_click(k)
                    )
                
                btn.grid(row=row_idx, column=col_idx, padx=4, pady=4, sticky="nsew")
                self._buttons[key] = btn
                
                # 保存开始按钮的引用
                if key == "start":
                    self._start_button = btn
        
        # 配置列权重（使按钮均匀分布）
        for i in range(4):
            buttons_container.grid_columnconfigure(i, weight=1)
        
        # 配置行权重
        for i in range(1):
            buttons_container.grid_rowconfigure(i, weight=1)
    
    def _on_button_click(self, button_key):
        """按钮点击事件处理
        
        参数:
            button_key: 按钮键名
        """
        try:
            callback = self._callbacks.get(button_key)
            if callback and callable(callback):
                callback()
        except Exception as e:
            print(f"按钮回调执行失败 [{button_key}]: {e}")
    
    @ErrorHandler.handle_ui_error
    def set_callback(self, button_key, callback):
        """设置按钮回调函数
        
        参数:
            button_key: 按钮键名
            callback: 回调函数
        """
        if callback is not None and not callable(callback):
            print(f"警告: 回调函数不可调用 [{button_key}]: {callback}")
            return
        
        self._callbacks[button_key] = callback
    
    def enable_start_button(self, enabled):
        """启用/禁用开始按钮
        
        参数:
            enabled: True为启用，False为禁用
        """
        try:
            if self._start_button:
                if enabled:
                    self._start_button.config(
                        state=tk.NORMAL,
                        bg="#4CAF50",
                        text="▶ 开始"
                    )
                else:
                    self._start_button.config(
                        state=tk.DISABLED,
                        bg="#cccccc",
                        text="■ 停止"
                    )
        except Exception as e:
            print(f"设置开始按钮状态失败: {e}")
    
    @ErrorHandler.handle_ui_error
    def set_button_state(self, button_name, enabled):
        """设置按钮状态
        
        参数:
            button_name: 按钮名称
            enabled: True为启用，False为禁用
        """
        try:
            if button_name in self._buttons:
                button = self._buttons[button_name]
                if button:
                    state = tk.NORMAL if enabled else tk.DISABLED
                    button.config(state=state)
        except Exception as e:
            print(f"设置按钮状态失败 [{button_name}]: {e}")
    
    @ErrorHandler.handle_ui_error
    def set_start_button_text(self, text):
        """设置开始按钮文本
        
        参数:
            text: 按钮文本
        """
        try:
            if self._start_button and text:
                self._start_button.config(text=text)
        except Exception as e:
            print(f"设置开始按钮文本失败: {e}")
    
    @ErrorHandler.handle_ui_error
    def toggle_start_button(self, is_running):
        """切换开始/停止按钮状态
        
        参数:
            is_running: True表示正在运行，False表示已停止
        """
        try:
            if self._start_button:
                if is_running:
                    self._start_button.config(
                        text="■ 停止",
                        bg="#F44336"  # 红色
                    )
                else:
                    self._start_button.config(
                        text="▶ 开始",
                        bg="#4CAF50"  # 绿色
                    )
        except Exception as e:
            print(f"切换开始按钮状态失败: {e}")


# 测试代码
if __name__ == "__main__":
    root = tk.Tk()
    root.title("控制按钮面板测试")
    root.geometry("400x600")
    
    def on_button_click(name):
        print(f"按钮点击: {name}")
    
    callbacks = {
        "select_solution": lambda: on_button_click("选择解决方案"),
        "edit_tolerance": lambda: on_button_click("编辑容忍度"),
        "display_settings": lambda: on_button_click("设置显示"),
        "history_review": lambda: on_button_click("历史数据回顾"),
        "reset_detection": lambda: on_button_click("重置检测"),
        "reset_statistics": lambda: on_button_click("重置统计数据"),
        "manual_trigger": lambda: on_button_click("手动触发"),
        "start": lambda: on_button_click("开始"),
    }
    
    panel = ControlButtonsPanel(root, callbacks)
    panel.pack(fill=tk.BOTH, expand=True)
    
    # 测试按钮
    test_frame = tk.Frame(root)
    test_frame.pack(pady=10)
    
    is_running = False
    
    def toggle_running():
        global is_running
        is_running = not is_running
        panel.toggle_start_button(is_running)
    
    tk.Button(test_frame, text="切换运行状态", command=toggle_running).pack(padx=5)
    
    root.mainloop()
