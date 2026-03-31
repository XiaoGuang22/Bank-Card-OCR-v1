"""
异常处理工具模块
提供装饰器和上下文管理器来简化异常处理，提高代码可读性
"""

import functools
import logging
import traceback
from contextlib import contextmanager
from typing import Any, Callable, Optional, Type, Union, Tuple
import tkinter.messagebox as messagebox

# 导入配置模块
try:
    from .error_config import error_config, ErrorCategory, get_error_category, get_error_message
except ImportError:
    try:
        from error_config import error_config, ErrorCategory, get_error_category, get_error_message
    except ImportError:
        # 如果配置模块不可用，使用简单的默认配置
        error_config = None
        ErrorCategory = None
        get_error_category = lambda e: "business"
        get_error_message = lambda c, t, d: d

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def safe_execute(
    default_return: Any = None,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    log_error: bool = True,
    show_error: bool = False,
    error_message: str = "操作失败"
):
    """
    装饰器：安全执行函数，捕获异常并返回默认值
    
    Args:
        default_return: 异常时返回的默认值
        exceptions: 要捕获的异常类型
        log_error: 是否记录错误日志
        show_error: 是否显示错误对话框
        error_message: 错误消息前缀
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exceptions as e:
                if log_error:
                    logger.error(f"{error_message} - {func.__name__}: {str(e)}")
                    logger.debug(traceback.format_exc())
                
                if show_error:
                    messagebox.showerror("错误", f"{error_message}:\n{str(e)}")
                
                return default_return
        return wrapper
    return decorator


def retry_on_failure(
    max_attempts: int = 3,
    delay: float = 0.1,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    backoff_factor: float = 1.0
):
    """
    装饰器：失败时重试
    
    Args:
        max_attempts: 最大尝试次数
        delay: 重试间隔（秒）
        exceptions: 要重试的异常类型
        backoff_factor: 退避因子（每次重试延迟增加的倍数）
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import time
            
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:  # 不是最后一次尝试
                        logger.warning(f"{func.__name__} 第 {attempt + 1} 次尝试失败: {str(e)}")
                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        logger.error(f"{func.__name__} 所有 {max_attempts} 次尝试都失败了")
            
            # 所有尝试都失败，抛出最后一个异常
            raise last_exception
        return wrapper
    return decorator


@contextmanager
def safe_resource(resource, cleanup_func: Optional[Callable] = None, error_message: str = "资源操作失败"):
    """
    上下文管理器：安全的资源管理
    
    Args:
        resource: 要管理的资源
        cleanup_func: 清理函数，如果为None则尝试调用resource的Destroy方法
        error_message: 错误消息
    """
    try:
        yield resource
    except Exception as e:
        logger.error(f"{error_message}: {str(e)}")
        raise
    finally:
        try:
            if cleanup_func:
                cleanup_func(resource)
            elif hasattr(resource, 'Destroy'):
                resource.Destroy()
            elif hasattr(resource, 'close'):
                resource.close()
        except Exception as e:
            logger.warning(f"清理资源时出错: {str(e)}")


@contextmanager
def suppress_errors(*exceptions, log_error: bool = True, error_message: str = "操作中出现错误"):
    """
    上下文管理器：抑制指定的异常
    
    Args:
        exceptions: 要抑制的异常类型
        log_error: 是否记录错误
        error_message: 错误消息
    """
    try:
        yield
    except exceptions as e:
        if log_error:
            logger.warning(f"{error_message}: {str(e)}")


class SmartErrorHandler:
    """智能错误处理器 - 基于配置的异常处理"""
    
    @staticmethod
    def handle_with_category(category: 'ErrorCategory', error_type: str = None):
        """
        基于类别的错误处理装饰器
        
        Args:
            category: 错误类别
            error_type: 具体错误类型（用于获取错误消息）
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    return SmartErrorHandler._handle_exception(e, category, error_type, func.__name__)
            return wrapper
        return decorator
    
    @staticmethod
    def _handle_exception(exception: Exception, category: 'ErrorCategory', error_type: str, func_name: str):
        """处理异常的核心逻辑"""
        if not error_config:
            # 回退到简单处理
            logger.error(f"{func_name} 失败: {str(exception)}")
            return None
        
        config = error_config.get_config(category)
        
        # 记录日志
        log_level = config.get('log_level', logging.ERROR)
        logger.log(log_level, f"{func_name} 失败: {str(exception)}")
        logger.debug(traceback.format_exc())
        
        # 显示用户消息
        if config.get('show_user_message', False):
            error_msg = get_error_message(category, error_type, f"{func_name} 操作失败")
            messagebox.showerror("错误", f"{error_msg}:\n{str(exception)}")
        
        return None


class ErrorHandler:
    """统一的错误处理器 - 保持向后兼容"""
    
    @staticmethod
    def handle_camera_error(func: Callable) -> Callable:
        """相机操作错误处理装饰器"""
        if ErrorCategory:
            return SmartErrorHandler.handle_with_category(ErrorCategory.CAMERA, 'operation_failed')(func)
        else:
            return safe_execute(
                default_return=False,
                exceptions=(Exception,),
                log_error=True,
                show_error=False,
                error_message="相机操作失败"
            )(func)
    
    @staticmethod
    def handle_ui_error(func: Callable) -> Callable:
        """UI操作错误处理装饰器"""
        if ErrorCategory:
            return SmartErrorHandler.handle_with_category(ErrorCategory.UI, 'operation_failed')(func)
        else:
            return safe_execute(
                default_return=None,
                exceptions=(Exception,),
                log_error=True,
                show_error=True,
                error_message="界面操作失败"
            )(func)
    
    @staticmethod
    def handle_file_error(func: Callable) -> Callable:
        """文件操作错误处理装饰器"""
        if ErrorCategory:
            return SmartErrorHandler.handle_with_category(ErrorCategory.FILE_IO, 'operation_failed')(func)
        else:
            return safe_execute(
                default_return=None,
                exceptions=(IOError, OSError, FileNotFoundError),
                log_error=True,
                show_error=True,
                error_message="文件操作失败"
            )(func)
    
    @staticmethod
    def handle_system_error(func: Callable) -> Callable:
        """系统操作错误处理装饰器"""
        if ErrorCategory:
            return SmartErrorHandler.handle_with_category(ErrorCategory.SYSTEM, 'operation_failed')(func)
        else:
            return safe_execute(
                default_return=False,
                exceptions=(Exception,),
                log_error=True,
                show_error=False,
                error_message="系统操作失败"
            )(func)


# 便捷函数
def safe_call(func: Callable, *args, default=None, **kwargs):
    """安全调用函数，返回结果或默认值"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.warning(f"安全调用 {func.__name__} 失败: {str(e)}")
        return default


def safe_get_attribute(obj, attr_name: str, default=None):
    """安全获取对象属性"""
    try:
        return getattr(obj, attr_name, default)
    except Exception:
        return default


def safe_set_attribute(obj, attr_name: str, value, log_error: bool = True):
    """安全设置对象属性"""
    try:
        setattr(obj, attr_name, value)
        return True
    except Exception as e:
        if log_error:
            logger.warning(f"设置属性 {attr_name} 失败: {str(e)}")
        return False