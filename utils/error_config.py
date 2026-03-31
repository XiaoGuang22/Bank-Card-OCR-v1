"""
异常处理配置模块
集中管理异常处理的行为和策略
"""

import logging
from enum import Enum
from typing import Dict, Any, Optional


class ErrorLevel(Enum):
    """错误级别枚举"""
    SILENT = "silent"           # 静默处理，不显示给用户
    LOG_ONLY = "log_only"       # 只记录日志
    NOTIFY_USER = "notify_user" # 通知用户
    CRITICAL = "critical"       # 关键错误，需要立即处理


class ErrorCategory(Enum):
    """错误类别枚举"""
    CAMERA = "camera"           # 相机相关错误
    FILE_IO = "file_io"         # 文件操作错误
    UI = "ui"                   # 界面操作错误
    NETWORK = "network"         # 网络相关错误
    SYSTEM = "system"           # 系统级错误
    BUSINESS = "business"       # 业务逻辑错误


class ErrorHandlingConfig:
    """异常处理配置类"""
    
    # 默认配置
    DEFAULT_CONFIG = {
        ErrorCategory.CAMERA: {
            'level': ErrorLevel.LOG_ONLY,
            'show_user_message': False,
            'log_level': logging.WARNING,
            'retry_attempts': 2,
            'retry_delay': 0.1
        },
        ErrorCategory.FILE_IO: {
            'level': ErrorLevel.NOTIFY_USER,
            'show_user_message': True,
            'log_level': logging.ERROR,
            'retry_attempts': 1,
            'retry_delay': 0.0
        },
        ErrorCategory.UI: {
            'level': ErrorLevel.NOTIFY_USER,
            'show_user_message': True,
            'log_level': logging.ERROR,
            'retry_attempts': 0,
            'retry_delay': 0.0
        },
        ErrorCategory.NETWORK: {
            'level': ErrorLevel.LOG_ONLY,
            'show_user_message': False,
            'log_level': logging.WARNING,
            'retry_attempts': 3,
            'retry_delay': 1.0
        },
        ErrorCategory.SYSTEM: {
            'level': ErrorLevel.CRITICAL,
            'show_user_message': True,
            'log_level': logging.CRITICAL,
            'retry_attempts': 0,
            'retry_delay': 0.0
        },
        ErrorCategory.BUSINESS: {
            'level': ErrorLevel.NOTIFY_USER,
            'show_user_message': True,
            'log_level': logging.ERROR,
            'retry_attempts': 0,
            'retry_delay': 0.0
        }
    }
    
    def __init__(self, config: Optional[Dict] = None):
        """
        初始化配置
        
        Args:
            config: 自定义配置字典，会覆盖默认配置
        """
        self.config = self.DEFAULT_CONFIG.copy()
        if config:
            self._merge_config(config)
    
    def _merge_config(self, custom_config: Dict):
        """合并自定义配置"""
        for category, settings in custom_config.items():
            if category in self.config:
                self.config[category].update(settings)
            else:
                self.config[category] = settings
    
    def get_config(self, category: ErrorCategory) -> Dict[str, Any]:
        """获取指定类别的配置"""
        return self.config.get(category, self.DEFAULT_CONFIG[ErrorCategory.BUSINESS])
    
    def should_show_user_message(self, category: ErrorCategory) -> bool:
        """是否应该显示用户消息"""
        return self.get_config(category).get('show_user_message', True)
    
    def get_log_level(self, category: ErrorCategory) -> int:
        """获取日志级别"""
        return self.get_config(category).get('log_level', logging.ERROR)
    
    def get_retry_config(self, category: ErrorCategory) -> tuple:
        """获取重试配置 (attempts, delay)"""
        config = self.get_config(category)
        return config.get('retry_attempts', 0), config.get('retry_delay', 0.0)


# 全局配置实例
error_config = ErrorHandlingConfig()


# 预定义的错误消息模板
ERROR_MESSAGES = {
    ErrorCategory.CAMERA: {
        'connection_failed': '相机连接失败，请检查相机是否正确连接',
        'capture_failed': '图像捕获失败，请重试',
        'setting_failed': '相机参数设置失败',
        'trigger_failed': '触发模式设置失败'
    },
    ErrorCategory.FILE_IO: {
        'read_failed': '文件读取失败，请检查文件是否存在且有读取权限',
        'write_failed': '文件写入失败，请检查磁盘空间和写入权限',
        'path_not_found': '指定的路径不存在',
        'permission_denied': '没有足够的权限访问文件'
    },
    ErrorCategory.UI: {
        'widget_creation_failed': '界面组件创建失败',
        'event_binding_failed': '事件绑定失败',
        'display_update_failed': '界面更新失败'
    },
    ErrorCategory.NETWORK: {
        'connection_timeout': '网络连接超时',
        'request_failed': '网络请求失败',
        'server_error': '服务器错误'
    },
    ErrorCategory.SYSTEM: {
        'memory_error': '内存不足',
        'resource_exhausted': '系统资源耗尽',
        'permission_error': '系统权限错误'
    },
    ErrorCategory.BUSINESS: {
        'validation_failed': '数据验证失败',
        'operation_not_allowed': '当前状态下不允许此操作',
        'resource_not_found': '请求的资源不存在'
    }
}


def get_error_message(category: ErrorCategory, error_type: str, default: str = "操作失败") -> str:
    """
    获取错误消息
    
    Args:
        category: 错误类别
        error_type: 错误类型
        default: 默认消息
    
    Returns:
        错误消息字符串
    """
    return ERROR_MESSAGES.get(category, {}).get(error_type, default)


# 常用的异常类型映射
EXCEPTION_CATEGORY_MAP = {
    # 文件相关异常
    FileNotFoundError: ErrorCategory.FILE_IO,
    PermissionError: ErrorCategory.FILE_IO,
    IOError: ErrorCategory.FILE_IO,
    OSError: ErrorCategory.FILE_IO,
    
    # 系统相关异常
    MemoryError: ErrorCategory.SYSTEM,
    SystemError: ErrorCategory.SYSTEM,
    
    # 网络相关异常
    ConnectionError: ErrorCategory.NETWORK,
    TimeoutError: ErrorCategory.NETWORK,
    
    # UI相关异常（tkinter）
    'tkinter.TclError': ErrorCategory.UI,
    
    # 业务逻辑异常
    ValueError: ErrorCategory.BUSINESS,
    TypeError: ErrorCategory.BUSINESS,
    AttributeError: ErrorCategory.BUSINESS,
}


def get_error_category(exception: Exception) -> ErrorCategory:
    """
    根据异常类型获取错误类别
    
    Args:
        exception: 异常实例
    
    Returns:
        错误类别
    """
    exception_type = type(exception)
    exception_name = f"{exception_type.__module__}.{exception_type.__name__}"
    
    # 首先尝试完整名称匹配
    if exception_name in EXCEPTION_CATEGORY_MAP:
        return EXCEPTION_CATEGORY_MAP[exception_name]
    
    # 然后尝试类型匹配
    if exception_type in EXCEPTION_CATEGORY_MAP:
        return EXCEPTION_CATEGORY_MAP[exception_type]
    
    # 默认返回业务逻辑错误
    return ErrorCategory.BUSINESS