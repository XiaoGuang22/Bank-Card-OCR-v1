"""
时间信息面板

显示时间戳、检测时间和触发频率
"""

import tkinter as tk
from datetime import datetime
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


class TimeInfoPanel(tk.Frame):
    """时间信息面板类
    
    显示当前时间戳、单次检测时间和触发频率。
    
    验证需求: 3.1, 3.2, 3.3, 3.4
    """
    
    def __init__(self, parent):
        """初始化时间信息面板
        
        参数:
            parent: 父窗口
        """
        super().__init__(parent, bg="white")
        
        # 时间信息数据
        self._timestamp = None
        self._detection_time_ms = 0.0
        self._trigger_frequency_hz = 0.0
        
        self._init_ui()
    
    @ErrorHandler.handle_ui_error
    def _init_ui(self):
        """初始化UI布局"""
        # 标题
        title_label = tk.Label(
            self,
            text="时间信息",
            font=("Microsoft YaHei UI", 12, "bold"),
            bg="white",
            fg="#333"
        )
        title_label.pack(pady=(10, 15))
        
        # 时间戳
        self._timestamp_frame = self._create_info_item("时间戳", "--")
        self._timestamp_frame.pack(fill=tk.X, padx=15, pady=5)
        
        # 检测时间
        self._detection_time_frame = self._create_info_item("检测时间", "0.0 ms")
        self._detection_time_frame.pack(fill=tk.X, padx=15, pady=5)
        
        # 触发频率
        self._trigger_freq_frame = self._create_info_item("触发频率", "0.0 Hz")
        self._trigger_freq_frame.pack(fill=tk.X, padx=15, pady=5)
    
    @safe_execute(default_return=None, log_error=True, error_message="创建信息项失败")
    def _create_info_item(self, label_text, initial_value):
        """创建信息项
        
        参数:
            label_text: 标签文本
            initial_value: 初始值
        
        返回:
            tk.Frame: 信息项容器
        """
        # 容器
        container = tk.Frame(self, bg="white")
        
        # 标签
        label = tk.Label(
            container,
            text=f"{label_text}:",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg="white",
            fg="#333"
        )
        label.pack(anchor=tk.W)
        
        # 值标签
        value_label = tk.Label(
            container,
            text=initial_value,
            font=("Microsoft YaHei UI", 9),
            bg="white",
            fg="#666"
        )
        value_label.pack(anchor=tk.W, pady=(2, 0))
        
        # 保存值标签引用
        container.value_label = value_label
        
        return container
    
    @ErrorHandler.handle_ui_error
    def update_timestamp(self, timestamp=None):
        """更新时间戳
        
        参数:
            timestamp: datetime对象，如果为None则使用当前时间
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        self._timestamp = timestamp
        
        # 格式化为 MM/DD/YYYY HH:MM:SS.mmm
        formatted = timestamp.strftime("%m/%d/%Y %H:%M:%S.%f")[:-3]
        
        self._timestamp_frame.value_label.config(text=formatted)
    
    @ErrorHandler.handle_ui_error
    def update_detection_time(self, time_ms):
        """更新检测时间（毫秒）
        
        参数:
            time_ms: 检测时间（毫秒）
        """
        if time_ms < 0:
            raise ValueError("检测时间不能为负数")
        
        self._detection_time_ms = time_ms
        
        self._detection_time_frame.value_label.config(text=f"{time_ms:.1f} ms")
    
    @ErrorHandler.handle_ui_error
    def update_trigger_frequency(self, frequency_hz):
        """更新触发频率（Hz）
        
        参数:
            frequency_hz: 触发频率（Hz）
        """
        if frequency_hz < 0:
            raise ValueError("触发频率不能为负数")
        
        self._trigger_frequency_hz = frequency_hz
        
        self._trigger_freq_frame.value_label.config(text=f"{frequency_hz:.2f} Hz")
    
    @safe_execute(default_return={"timestamp": None, "detection_time_ms": 0.0, "trigger_frequency_hz": 0.0}, log_error=True)
    def get_time_info(self):
        """获取当前时间信息
        
        返回:
            dict: 时间信息字典，包含以下键：
                - timestamp: 时间戳 (datetime)
                - detection_time_ms: 检测时间（毫秒）(float)
                - trigger_frequency_hz: 触发频率（Hz）(float)
        """
        return {
            "timestamp": self._timestamp,
            "detection_time_ms": self._detection_time_ms,
            "trigger_frequency_hz": self._trigger_frequency_hz
        }


# 测试代码
if __name__ == "__main__":
    root = tk.Tk()
    root.title("时间信息面板测试")
    root.geometry("300x300")
    
    panel = TimeInfoPanel(root)
    panel.pack(fill=tk.BOTH, expand=True)
    
    # 测试按钮
    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=10)
    
    def test_update():
        panel.update_timestamp()
        panel.update_detection_time(85.5)
        panel.update_trigger_frequency(12.5)
    
    tk.Button(btn_frame, text="更新时间信息", command=test_update).pack(padx=5)
    
    root.mainloop()
