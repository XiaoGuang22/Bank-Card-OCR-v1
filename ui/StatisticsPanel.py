"""
统计面板

显示实时统计信息（Pass/Reject/Recycle 数量和百分比）
"""

import tkinter as tk
from tkinter import ttk
import logging

# 导入异常处理工具
try:
    from utils.exception_utils import ErrorHandler, safe_execute
except ImportError:
    # 如果异常处理工具不可用，使用简单的装饰器
    def ErrorHandler():
        class _ErrorHandler:
            @staticmethod
            def handle_ui_error(func):
                return func
        return _ErrorHandler()
    ErrorHandler = ErrorHandler()
    safe_execute = lambda **kwargs: lambda func: func

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StatisticsPanel(tk.Frame):
    """统计面板类
    
    显示Pass/Reject/Recycle的数量和百分比，使用颜色编码区分不同类型。
    
    验证需求: 2.1, 2.2, 2.3, 2.4
    """
    
    def __init__(self, parent):
        """初始化统计面板
        
        参数:
            parent: 父窗口
        """
        super().__init__(parent, bg="white")
        
        # 统计数据
        self._pass_count = 0
        self._reject_count = 0
        self._recycle_count = 0
        
        # 颜色配置
        self.PASS_COLOR = "#4CAF50"      # 绿色
        self.REJECT_COLOR = "#F44336"    # 红色
        self.RECYCLE_COLOR = "#FFC107"   # 黄色
        
        self._init_ui()
    
    @ErrorHandler.handle_ui_error
    def _init_ui(self):
        """初始化UI布局"""
        # 标题
        title_label = tk.Label(
            self,
            text="统计信息",
            font=("Microsoft YaHei UI", 12, "bold"),
            bg="white",
            fg="#333"
        )
        title_label.pack(pady=(10, 15))
        
        # Pass 统计
        self._pass_frame = self._create_stat_item(
            "Pass",
            self.PASS_COLOR
        )
        self._pass_frame.pack(fill=tk.X, padx=15, pady=5)
        
        # Reject 统计
        self._reject_frame = self._create_stat_item(
            "Reject",
            self.REJECT_COLOR
        )
        self._reject_frame.pack(fill=tk.X, padx=15, pady=5)
        
        # Recycle 统计
        self._recycle_frame = self._create_stat_item(
            "Recycle",
            self.RECYCLE_COLOR
        )
        self._recycle_frame.pack(fill=tk.X, padx=15, pady=5)
        
        # 分隔线
        separator = tk.Frame(self, height=2, bg="#e0e0e0")
        separator.pack(fill=tk.X, padx=15, pady=10)
        
        # 总计
        total_frame = tk.Frame(self, bg="white")
        total_frame.pack(fill=tk.X, padx=15, pady=5)
        
        tk.Label(
            total_frame,
            text="总计:",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg="white",
            fg="#333"
        ).pack(side=tk.LEFT)
        
        self._total_label = tk.Label(
            total_frame,
            text="0",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg="white",
            fg="#333"
        )
        self._total_label.pack(side=tk.RIGHT)
    
    @safe_execute(default_return=None, log_error=True, error_message="创建统计项失败")
    def _create_stat_item(self, label_text, color):
        """创建统计项
        
        参数:
            label_text: 标签文本（Pass/Reject/Recycle）
            color: 颜色代码
        
        返回:
            tk.Frame: 统计项容器
        """
        # 容器
        container = tk.Frame(self, bg="white")
        
        # 标签和数值行
        top_row = tk.Frame(container, bg="white")
        top_row.pack(fill=tk.X)
        
        # 标签（带颜色）
        label = tk.Label(
            top_row,
            text=f"{label_text}:",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg="white",
            fg=color
        )
        label.pack(side=tk.LEFT)
        
        # 数值标签
        count_label = tk.Label(
            top_row,
            text="0",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg="white",
            fg=color
        )
        count_label.pack(side=tk.RIGHT)
        
        # 百分比行
        percent_row = tk.Frame(container, bg="white")
        percent_row.pack(fill=tk.X, pady=(2, 0))
        
        # 百分比标签
        percent_label = tk.Label(
            percent_row,
            text="0.0%",
            font=("Microsoft YaHei UI", 9),
            bg="white",
            fg="#666"
        )
        percent_label.pack(side=tk.RIGHT)
        
        # 保存标签引用
        container.count_label = count_label
        container.percent_label = percent_label
        
        return container
    
    @ErrorHandler.handle_ui_error
    def update_statistics(self, pass_count, reject_count, recycle_count):
        """更新统计数据
        
        参数:
            pass_count: Pass 数量
            reject_count: Reject 数量
            recycle_count: Recycle 数量
        """
        # 验证输入
        if pass_count < 0 or reject_count < 0 or recycle_count < 0:
            raise ValueError("统计数据不能为负数")
        
        # 更新内部数据
        self._pass_count = pass_count
        self._reject_count = reject_count
        self._recycle_count = recycle_count
        
        # 计算总数
        total = pass_count + reject_count + recycle_count
        
        # 计算百分比
        pass_rate = (pass_count / total * 100) if total > 0 else 0.0
        reject_rate = (reject_count / total * 100) if total > 0 else 0.0
        recycle_rate = (recycle_count / total * 100) if total > 0 else 0.0
        
        # 更新 Pass 显示
        self._pass_frame.count_label.config(text=str(pass_count))
        self._pass_frame.percent_label.config(text=f"{pass_rate:.1f}%")
        
        # 更新 Reject 显示
        self._reject_frame.count_label.config(text=str(reject_count))
        self._reject_frame.percent_label.config(text=f"{reject_rate:.1f}%")
        
        # 更新 Recycle 显示
        self._recycle_frame.count_label.config(text=str(recycle_count))
        self._recycle_frame.percent_label.config(text=f"{recycle_rate:.1f}%")
        
        # 更新总计
        self._total_label.config(text=str(total))
    
    @ErrorHandler.handle_ui_error
    def reset(self):
        """重置统计数据
        
        将Pass、Reject、Recycle计数全部清零。
        """
        self.update_statistics(0, 0, 0)
    
    @safe_execute(default_return={"pass": 0, "reject": 0, "recycle": 0, "total": 0}, log_error=True)
    def get_statistics(self):
        """获取当前统计数据
        
        返回:
            dict: 统计数据字典，包含以下键：
                - pass: Pass数量 (int)
                - reject: Reject数量 (int)
                - recycle: Recycle数量 (int)
                - total: 总处理数量 (int)
        """
        total = self._pass_count + self._reject_count + self._recycle_count
        return {
            "pass": self._pass_count,
            "reject": self._reject_count,
            "recycle": self._recycle_count,
            "total": total
        }


# 测试代码
if __name__ == "__main__":
    root = tk.Tk()
    root.title("统计面板测试")
    root.geometry("300x400")
    
    panel = StatisticsPanel(root)
    panel.pack(fill=tk.BOTH, expand=True)
    
    # 测试按钮
    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=10)
    
    def test_update():
        panel.update_statistics(10, 5, 2)
    
    def test_reset():
        panel.reset()
    
    tk.Button(btn_frame, text="更新统计", command=test_update).pack(side=tk.LEFT, padx=5)
    tk.Button(btn_frame, text="重置", command=test_reset).pack(side=tk.LEFT, padx=5)
    
    root.mainloop()
