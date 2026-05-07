import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageDraw
import cv2
import numpy as np
import threading
import time
import os
import sys
import ctypes
import clr
import json
from System import IntPtr, Int64
from System.Runtime.InteropServices import Marshal

# 导入配置
from config import CAMERA_DEFAULT_PARAMS

# ★★★ 导入传感器设置面板类 ★★★
try:
    from ui.SensorSettingsFrame import SensorSettingsFrame
except ImportError:
    from SensorSettingsFrame import SensorSettingsFrame

# ★★★ 导入解决方案制作面板类 ★★★
try:
    from ui.SolutionMakerFrame import SolutionMakerFrame
except ImportError:
    from SolutionMakerFrame import SolutionMakerFrame

# ★★★ 导入操作日志面板 ★★★
try:
    from ui.AuditLogPanel import AuditLogPanel
    from managers.audit_log_manager import AuditLogManager
except ImportError:
    AuditLogPanel = None
    AuditLogManager = None

# ★★★ 导入 TCP 服务和脚本引擎 ★★★
try:
    from services.tcp_service import TcpService
    from core.script_engine import ScriptEngine
    from ui.TcpSettingsFrame import TcpSettingsFrame
    from ui.ScriptEditorFrame import ScriptEditorFrame
except ImportError:
    # 如果导入失败，设置为 None（向后兼容）
    TcpService = None
    ScriptEngine = None
    TcpSettingsFrame = None
    ScriptEditorFrame = None

# ★★★ 导入异常处理工具 ★★★
try:
    from utils.exception_utils import ErrorHandler, safe_call, safe_execute, suppress_errors
except ImportError:
    # 如果异常处理工具不可用，使用简单的装饰器
    class _ErrorHandler:
        @staticmethod
        def handle_ui_error(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"UI错误: {e}")
                    return None
            return wrapper
        
        @staticmethod
        def handle_file_error(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"文件错误: {e}")
                    return None
            return wrapper
        
        @staticmethod
        def handle_camera_error(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"相机错误: {e}")
                    return False
            return wrapper
        
        @staticmethod
        def handle_system_error(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print(f"系统错误: {e}")
                    return False
            return wrapper
    
    # 创建ErrorHandler实例
    ErrorHandler = _ErrorHandler()
    
    def safe_call(func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"安全调用错误: {e}")
            return None
    
    def safe_execute(default_return=None, log_error=True, error_message="操作失败"):
        def decorator(func):
            def wrapper(*args, **kwargs):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if log_error:
                        print(f"{error_message}: {e}")
                    return default_return
            return wrapper
        return decorator
    
    def suppress_errors(*args, **kwargs):
        def decorator(func):
            def wrapper(*func_args, **func_kwargs):
                try:
                    return func(*func_args, **func_kwargs)
                except:
                    pass
            return wrapper
        return decorator

# ==============================================================================
# 1. 全局配置与初始化
# ==============================================================================
# Sapera SDK 配置
SAPERA_DLL_PATH = r"C:\Program Files\Teledyne DALSA\Sapera\Components\NET\Bin\DALSA.SaperaLT.SapClassBasic.dll"
SERVER_NAME = "Genie_M1600_1" 
RESOURCE_INDEX = 0

# 全局状态标记
SAPERA_AVAILABLE = False
# 全局 Sapera 类变量
SapLocation = None
SapAcqDevice = None
SapBuffer = None
SapBufferWithTrash = None
SapAcqDeviceToBuf = None
SapXferPair = None
SapTransfer = None

# 初始化 Sapera SDK
@ErrorHandler.handle_system_error
def init_sapera_sdk():
    """初始化 Sapera SDK"""
    global SAPERA_AVAILABLE, SapLocation, SapAcqDevice, SapBuffer, SapBufferWithTrash, SapAcqDeviceToBuf, SapXferPair, SapTransfer
    if not os.path.exists(SAPERA_DLL_PATH):
        return False
    
    clr.AddReference(SAPERA_DLL_PATH)
    from DALSA.SaperaLT.SapClassBasic import (
        SapLocation as _SapLocation, 
        SapAcqDevice as _SapAcqDevice, 
        SapBuffer as _SapBuffer, 
        SapBufferWithTrash as _SapBufferWithTrash, 
        SapAcqDeviceToBuf as _SapAcqDeviceToBuf, 
        SapXferPair as _SapXferPair, 
        SapTransfer as _SapTransfer,
    )
    SapLocation = _SapLocation
    SapAcqDevice = _SapAcqDevice
    SapBuffer = _SapBuffer
    SapBufferWithTrash = _SapBufferWithTrash
    SapAcqDeviceToBuf = _SapAcqDeviceToBuf
    SapXferPair = _SapXferPair
    SapTransfer = _SapTransfer
    
    SAPERA_AVAILABLE = True
    return True

# 通用工具函数
@safe_execute(default_return=False, log_error=True, error_message="Sapera对象创建失败")
def sapera_create_check(obj, create_func, obj_name):
    """通用 Sapera 对象创建检查函数"""
    success = create_func()
    if success:
        return True
    else:
        return False

@safe_execute(default_return=None, log_error=False, error_message="资源释放失败")
def safe_release(obj, release_func, obj_name):
    """通用资源释放函数"""
    if obj:
        release_func(obj)

# ==============================================================================
# 2. 相机控制器（优化版，改用Lock/Unlock读取图像）
# ==============================================================================
class CameraController:
    """单例模式相机控制器 - Sapera SDK 版本"""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """规范单例实现"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CameraController, cls).__new__(cls)
                cls._instance._init_attrs()
        return cls._instance

    def _init_attrs(self):
        """初始化属性"""
        self.is_running = False
        self.latest_frame = None
        self.lock = threading.Lock()
        
        # 新增：帧更新事件（用于软件触发后的即时刷新）
        self.frame_updated_event = threading.Event()
        self.waiting_for_trigger = False  # 标记是否正在等待触发帧
        
        # Sapera 对象初始化
        self.location = None
        self.acq_device = None
        self.buffers = None
        self.xfer = None
        self.width = 0
        self.height = 0
        self.pixel_depth = 8  # 工业相机默认8位灰度
        self.pitch = 0        # 行间距
        # 触发模式状态（内存中保存）
        self.current_trigger_mode = "internal"
        from config import SERVER_NAME as _CFG_SN
        self._current_server_name = _CFG_SN
        self._switch_lock = threading.Lock()
    
    @ErrorHandler.handle_camera_error
    def _stop_acquisition(self, silent=False):
        """
        停止采集（用于修改参数）
        
        参数:
            silent: 是否静默模式（不输出日志）
        
        返回:
            bool: 之前是否在运行
        """
        if not self.xfer:
            return False
        
        was_running = self.is_running
        if was_running:
            self.xfer.Freeze()
            self.xfer.Wait(5000)  # 等待最多5秒
            self.is_running = False
            if not silent:
                pass  # print(f"   ⏸️ 采集已停止")
                pass
        
        return was_running
    
    @safe_execute(default_return=None, log_error=True, error_message="清理部分连接资源失败")
    def _cleanup_partial_connection(self):
        """清理部分连接的资源"""
        if self.xfer:
            safe_call(self.xfer.Destroy)
            self.xfer = None
        
        if self.buffers:
            safe_call(self.buffers.Destroy)
            self.buffers = None
        
        if self.acq_device:
            safe_call(self.acq_device.Destroy)
            self.acq_device = None
    
    @ErrorHandler.handle_camera_error
    def _restart_acquisition(self, silent=False):
        """
        重新启动采集
        
        参数:
            silent: 是否静默模式（不输出日志）
        
        返回:
            bool: 是否成功启动
        """
        if not self.xfer:
            return False
        
        if self.xfer.Grab():
            self.is_running = True
            if not silent:
                pass
            return True
        else:
            if not silent:
                pass
            return False

    @ErrorHandler.handle_camera_error
    def connect(self, server_name=None):
        """连接相机硬件"""
        if server_name:
            self._current_server_name = server_name
        if self.acq_device is not None:
            if server_name and server_name != getattr(self, '_last_connected_name', ''):
                pass
            else:
                return True
        if not init_sapera_sdk():
            return False
        return self._execute_camera_connection()

    @ErrorHandler.handle_camera_error
    def disconnect(self):
        """断开相机连接"""
        self._stop_acquisition(silent=True)
        if self.xfer:
            try: self.xfer.XferNotify -= self._on_frame_callback
            except Exception: pass
            safe_call(self.xfer.Destroy)
            self.xfer = None
        if self.buffers:
            safe_call(self.buffers.Destroy)
            self.buffers = None
        if self.acq_device:
            safe_call(self.acq_device.Destroy)
            self.acq_device = None
        self.location = None
        self.is_running = False
        with self.lock:
            self.latest_frame = None

    @ErrorHandler.handle_camera_error
    def switch_to(self, server_name):
        """切换到指定相机"""
        with self._switch_lock:
            if server_name == self._current_server_name and self.acq_device is not None:
                return True
            self.disconnect()
            self._current_server_name = server_name
            if self.connect(server_name):
                self._last_connected_name = server_name
                return True
            return False

    @property
    def current_server_name(self):
        return self._current_server_name

    @ErrorHandler.handle_camera_error
    def _execute_camera_connection(self):
        """执行相机连接操作"""
        # 1. 定位设备
        self.location = SapLocation(self._current_server_name, RESOURCE_INDEX)
        
        # 2. 创建采集设备（修复分辨率获取）
        if not self._create_acq_device():
            return False
        
        # 3. 创建缓冲区（标准配置）
        if not self._create_buffers():
            return False
        
        # 4. 创建传输对象并启动采集（先绑定回调）
        if not self._create_and_start_transfer():
            return False
        
        # 5. 【关键修复】强制设置为内部时钟模式（避免上次关闭时的触发模式影响）
        safe_call(self.set_trigger_mode, "internal", interval_ms=100)

        return True

    @ErrorHandler.handle_camera_error
    def _create_acq_device(self):
        """创建采集设备"""
        # 直接使用默认配置创建
        self.acq_device = SapAcqDevice(self.location, False)
        
        if not sapera_create_check(self.acq_device, self.acq_device.Create, "采集设备"):
            return False
        
        # 获取相机分辨率（兼容多种方式）
        self._get_camera_resolution()
        
        # 如果仍然没有获取到，使用默认值
        if self.width == 0 or self.height == 0:
            self.width = 1600
            self.height = 1200
        
        return True

    @safe_execute(default_return=None, log_error=False, error_message="获取相机分辨率失败")
    def _get_camera_resolution(self):
        """获取相机分辨率"""
        from System import String
        
        width_str = None
        height_str = None
        
        # 方法1：尝试使用 StrongBox（新版本 pythonnet）
        width_str, height_str = self._try_strongbox_resolution()
        
        # 方法2：尝试使用 Reference（旧版本 pythonnet）
        if width_str is None or height_str is None:
            width_str, height_str = self._try_reference_resolution()
        
        # 转换为整数（处理空字符串）
        if width_str and width_str.strip():
            self.width = int(width_str)
        if height_str and height_str.strip():
            self.height = int(height_str)
        
        # 如果获取失败，尝试从缓冲区获取
        if self.width == 0 or self.height == 0:
            # 稍后从缓冲区获取
            self.width = 0
            self.height = 0

    @safe_execute(default_return=(None, None), log_error=False, error_message="StrongBox分辨率获取失败")
    def _try_strongbox_resolution(self):
        """尝试使用StrongBox获取分辨率"""
        from clr import StrongBox
        from System import String
        
        width_ref = StrongBox[String]()
        height_ref = StrongBox[String]()
        
        width_str = None
        height_str = None
        
        if self.acq_device.GetFeatureValue("Width", width_ref):
            width_str = str(width_ref.Value) if width_ref.Value else None
        if self.acq_device.GetFeatureValue("Height", height_ref):
            height_str = str(height_ref.Value) if height_ref.Value else None
            
        return width_str, height_str

    @safe_execute(default_return=(None, None), log_error=False, error_message="Reference分辨率获取失败")
    def _try_reference_resolution(self):
        """尝试使用Reference获取分辨率"""
        import clr
        from System import String
        
        width_ref = clr.Reference[String]()
        height_ref = clr.Reference[String]()
        
        width_str = None
        height_str = None
        
        if self.acq_device.GetFeatureValue("Width", width_ref):
            width_str = str(width_ref.Value) if width_ref.Value else None
        if self.acq_device.GetFeatureValue("Height", height_ref):
            height_str = str(height_ref.Value) if height_ref.Value else None
            
        return width_str, height_str

    @ErrorHandler.handle_camera_error
    def _create_buffers(self):
        """创建缓冲区（移除SapView，仅保留核心逻辑）"""
        buffer_types = [
            SapBuffer.MemoryType.ScatterGather,
            SapBuffer.MemoryType.ScatterGatherPhysical
        ]
        
        for mem_type in buffer_types:
            self.buffers = SapBufferWithTrash(2, self.acq_device, mem_type)
            self.buffers.PixelDepth = self.pixel_depth
            if sapera_create_check(self.buffers, self.buffers.Create, f"缓冲区({mem_type})"):
                self.pitch = self.buffers.Pitch
                pass  # print removed
                # 如果之前没有获取到分辨率，从缓冲区获取
                if self.width == 0 or self.height == 0:
                    safe_call(self._get_resolution_from_buffer)
                
                return True
        
        return False

    @safe_execute(default_return=None, log_error=False, error_message="从缓冲区获取分辨率失败")
    def _get_resolution_from_buffer(self):
        """从缓冲区获取分辨率"""
        self.width = self.buffers.Width
        self.height = self.buffers.Height
        pass  # print removed
        pass

    @ErrorHandler.handle_camera_error
    def _create_and_start_transfer(self):
        """创建传输对象并启动采集（先绑定回调）"""
        # 创建传输对象
        self.xfer = SapAcqDeviceToBuf(self.acq_device, self.buffers)
        self.xfer.Pairs[0].EventType = SapXferPair.XferEventType.EndOfFrame
        self.xfer.Pairs[0].Cycle = SapXferPair.CycleMode.NextWithTrash
        
        if not sapera_create_check(self.xfer, self.xfer.Create, "传输对象"):
            return False

        # 先绑定回调（核心修复）
        pass  # print removed
        self.xfer.XferNotify += self._on_frame_callback

        # 启动采集
        pass  # print removed
        if not self.xfer.Grab():
            return False
        
        self.is_running = True
        pass  # print removed
        # 等待系统稳定
        time.sleep(0.5)
        return True

    def _on_frame_callback(self, sender, args):
        """帧回调函数（使用临时文件方法，参考GenieCameraTriggerOptimized.py）"""
        if args.Trash:
            return

        # 执行帧处理
        self._process_frame_callback()

    @ErrorHandler.handle_camera_error
    def _process_frame_callback(self):
        """处理帧回调的核心逻辑"""
        # 使用 Sapera 的 Save 方法保存到临时文件，避免直接访问内存
        if not self.buffers:
            return

        import tempfile
        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix='.bmp', delete=False) as temp_file:
            temp_path = temp_file.name
        
        # 使用 Sapera 的 Save 方法
        if self.buffers.Save(temp_path, "-format bmp"):
            # 读取图像
            img_np = cv2.imread(temp_path, cv2.IMREAD_GRAYSCALE)
            
            # 删除临时文件
            safe_call(os.unlink, temp_path)
            
            if img_np is not None:
                # 线程安全更新最新帧
                with self.lock:
                    self.latest_frame = img_np.copy()
                
                # 如果正在等待触发帧，设置事件通知
                if self.waiting_for_trigger:
                    self.frame_updated_event.set()

    def get_image(self):
        """获取最新图像（优先返回有效帧）"""
        with self.lock:
            if self.latest_frame is not None:
                frame = self.latest_frame.copy()
                
                # 应用软件对比度调整（如果配置为 software 方案）
                frame = self._apply_software_contrast_if_needed(frame)
                
                return frame
        
        # 仅当无有效帧时返回无信号画面
        return self._generate_no_signal_image()

    @safe_execute(default_return=None, log_error=False, error_message="软件对比度调整失败")
    def _apply_software_contrast_if_needed(self, frame):
        """如果需要，应用软件对比度调整"""
        from config import CONTRAST_METHOD, SOFTWARE_CONTRAST_VALUE
        if CONTRAST_METHOD == 'software' and SOFTWARE_CONTRAST_VALUE != 50:
            return self._apply_software_contrast(frame, SOFTWARE_CONTRAST_VALUE)
        return frame

    def _generate_no_signal_image(self):
        """生成无信号画面"""
        img = np.zeros((self.height if self.height > 0 else 600, 
                        self.width if self.width > 0 else 800), dtype=np.uint8)
        img.fill(50)
        cv2.putText(img, "NO SIGNAL", (50, 300), cv2.FONT_HERSHEY_SIMPLEX, 2, (255), 3)
        t = time.time()
        x = int((np.sin(t) + 1) * 300) + 100
        cv2.rectangle(img, (x, 500), (x+50, 550), (200), -1)
        return img
    
    def _apply_software_contrast(self, image, contrast_value):
        """
        软件层面应用对比度调整
        
        参数:
            image: 输入图像（numpy数组）
            contrast_value: 对比度值（0-100）
        
        返回:
            调整后的图像
        """
        # 计算对比度因子
        # 0% -> 0.0, 50% -> 1.0, 100% -> 2.0
        contrast_factor = contrast_value / 50.0
        
        # 转换为浮点数进行计算
        img_float = image.astype(np.float32)
        
        # 应用对比度调整：output = 128 + (input - 128) * factor
        img_adjusted = 128 + (img_float - 128) * contrast_factor
        
        # 限制范围并转回 uint8
        img_adjusted = np.clip(img_adjusted, 0, 255).astype(np.uint8)
        
        return img_adjusted

    @ErrorHandler.handle_camera_error
    def set_exposure(self, value_ms):
        """
        设置曝光时间（毫秒）
        
        注意：曝光时间可以在采集时实时修改，无需停止采集
        """
        if not self.acq_device:
            return False
        
        return self._execute_exposure_setting(value_ms)

    @ErrorHandler.handle_camera_error
    def _execute_exposure_setting(self, value_ms):
        """执行曝光时间设置"""
        # 曝光时间可以实时修改，无需停止采集
        value_us = int(value_ms * 1000)  # 转换为微秒
        success = False
        
        # 尝试不同的特性名称
        for feature_name in ["ExposureTimeRaw", "ExposureTime", "ExposureTimeAbs"]:
            if self.acq_device.IsFeatureAvailable(feature_name):
                # 获取曝光时间的有效范围并限制值
                value_us = self._get_constrained_exposure_value(feature_name, value_us)
                
                # 设置曝光时间
                if self.acq_device.SetFeatureValue(feature_name, value_us):
                    success = True
                    break
        
        return success

    @safe_execute(default_return=None, log_error=False, error_message="获取曝光范围失败")
    def _get_constrained_exposure_value(self, feature_name, value_us):
        """获取限制后的曝光值"""
        from System import String
        
        # 尝试获取最小值和最大值
        min_val, max_val = self._get_exposure_range(feature_name)
        
        # 如果获取到了范围，进行限制
        if min_val is not None and max_val is not None:
            if value_us < min_val:
                value_us = int(min_val)
            elif value_us > max_val:
                value_us = int(max_val)
            
            pass  # print removed
            pass
        else:
            # 如果无法获取范围，使用常见的安全范围
            if value_us > 51100:  # 根据CSV文件，最大值约为51.10ms
                value_us = 51100
            elif value_us < 50:  # 最小值约为0.05ms
                value_us = 50
        
        return value_us

    @safe_execute(default_return=(None, None), log_error=False, error_message="获取曝光范围失败")
    def _get_exposure_range(self, feature_name):
        """获取曝光时间范围"""
        from System import String
        
        # 方法1：StrongBox（新版本）
        min_val, max_val = self._try_strongbox_exposure_range(feature_name)
        
        # 方法2：Reference（旧版本）
        if min_val is None or max_val is None:
            min_val, max_val = self._try_reference_exposure_range(feature_name)
        
        return min_val, max_val

    @safe_execute(default_return=(None, None), log_error=False, error_message="StrongBox曝光范围获取失败")
    def _try_strongbox_exposure_range(self, feature_name):
        """使用StrongBox获取曝光范围"""
        from clr import StrongBox
        from System import String
        
        min_ref = StrongBox[String]()
        max_ref = StrongBox[String]()
        
        min_feature = feature_name + "Min"
        max_feature = feature_name + "Max"
        
        min_val = None
        max_val = None
        
        if self.acq_device.GetFeatureValue(min_feature, min_ref):
            min_val = float(min_ref.Value) if min_ref.Value else None
        if self.acq_device.GetFeatureValue(max_feature, max_ref):
            max_val = float(max_ref.Value) if max_ref.Value else None
            
        return min_val, max_val

    @safe_execute(default_return=(None, None), log_error=False, error_message="Reference曝光范围获取失败")
    def _try_reference_exposure_range(self, feature_name):
        """使用Reference获取曝光范围"""
        import clr
        from System import String
        
        min_ref = clr.Reference[String]()
        max_ref = clr.Reference[String]()
        
        min_feature = feature_name + "Min"
        max_feature = feature_name + "Max"
        
        min_val = None
        max_val = None
        
        if self.acq_device.GetFeatureValue(min_feature, min_ref):
            min_val = float(min_ref.Value) if min_ref.Value else None
        if self.acq_device.GetFeatureValue(max_feature, max_ref):
            max_val = float(max_ref.Value) if max_ref.Value else None
            
        return min_val, max_val
    
    @ErrorHandler.handle_camera_error
    def set_gain(self, value):
        """
        设置增益（用于亮度调整）
        
        注意：增益可以在采集时实时修改，无需停止采集
        增益范围：0-120（Teledyne DALSA Genie M1600 相机）
        """
        if not self.acq_device:
            return False
        
        # 限制增益值在有效范围内（0-120）
        value = max(0, min(120, int(value)))
        
        # 增益可以实时修改，无需停止采集
        success = False
        
        # 尝试不同的特性名称
        for feature_name in ["GainRaw", "Gain"]:
            if self.acq_device.IsFeatureAvailable(feature_name):
                if self.acq_device.SetFeatureValue(feature_name, value):
                    pass  # print removed
                    success = True
                    break
        
        return success
    
    @ErrorHandler.handle_camera_error
    def set_gamma(self, value):
        """
        设置伽马值（用于对比度调整）
        
        注意：伽马值可以在采集时实时修改，无需停止采集
        由于相机不支持 Gamma，使用 LUT 来调整对比度
        """
        if not self.acq_device:
            return False
        
        # 检查相机是否支持 Gamma 参数
        if self.acq_device.IsFeatureAvailable("Gamma"):
            return self._set_gamma_direct(value)
        
        # 如果不支持 Gamma，根据配置选择对比度调整方案
        from config import CONTRAST_METHOD
        
        if CONTRAST_METHOD == 'lut':
            return self._set_gamma_via_lut(value)
        else:
            # 使用软件方案，保存到配置中
            return self._set_gamma_software(value)

    @ErrorHandler.handle_camera_error
    def _set_gamma_direct(self, value):
        """直接设置Gamma值"""
        # 伽马值可以实时修改，无需停止采集
        gamma_value = 0.5 + (value / 100.0) * 2.0  # 将0-100映射到0.5-2.5
        
        if self.acq_device.SetFeatureValue("Gamma", gamma_value):
            return True
        else:
            return False

    def _set_gamma_via_lut(self, value):
        """通过LUT设置Gamma值"""
        return self.set_contrast_with_lut_no_enable(value)

    def _set_gamma_software(self, value):
        """通过软件方式设置Gamma值"""
        # 保存对比度值到配置，在图像处理时应用
        import config
        config.SOFTWARE_CONTRAST_VALUE = value
        return True
    
    @ErrorHandler.handle_camera_error
    def set_contrast_with_lut_no_enable(self, contrast_value):
        """
        使用 LUT 调整对比度（使用属性赋值方式启用 LUT）
        
        参考官方示例代码，使用 acqDevice.LutEnable 属性而不是 SetFeatureValue()
        这可能可以避免 SDK 的类型转换警告
        """
        if not self.acq_device:
            return False
        
        # 记录当前采集状态并停止采集（静默模式）
        was_running = self._stop_acquisition(silent=True)
        
        return self._execute_lut_contrast_setting(contrast_value, was_running)

    @ErrorHandler.handle_camera_error
    def _execute_lut_contrast_setting(self, contrast_value, was_running):
        """执行LUT对比度设置"""
        # 检查 LUTIndex 和 LUTValue 是否可用
        if not self.acq_device.IsFeatureAvailable("LUTIndex") or \
           not self.acq_device.IsFeatureAvailable("LUTValue"):
            if was_running:
                self._restart_acquisition()
            return self.set_black_level(contrast_value)
        
        pass  # print removed
        # ★★★ 启用 LUT ★★★
        lut_enabled = self._enable_lut()
        
        # 设置 LUT Selector（如果可用）
        safe_call(self._set_lut_selector)
        
        # 计算对比度因子
        contrast_factor = contrast_value / 50.0
        
        # 设置 LUT 映射表
        success_count = self._set_lut_mapping_table(contrast_factor)
        
        if success_count == 256:
            # ★★★ 重要：在恢复采集前再次确认 LUT 已启用 ★★★
            self._force_enable_lut()
            
            # 恢复采集（静默模式）
            if was_running:
                self._restart_acquisition(silent=True)
            
            return True
        else:
            if was_running:
                self._restart_acquisition()
            return self.set_black_level(contrast_value)

    @safe_execute(default_return=False, log_error=False, error_message="启用LUT失败")
    def _enable_lut(self):
        """启用LUT"""
        lut_enabled = False
        if hasattr(self.acq_device, 'LutEnable'):
            self.acq_device.LutEnable = True
            lut_enabled = True
        
        # 如果属性赋值失败，尝试使用 SetFeatureValue
        if not lut_enabled:
            for value in ["1", "true", "True", "On", 1]:
                if safe_call(self.acq_device.SetFeatureValue, "LUTEnable", value):
                    lut_enabled = True
                    break
        
        return lut_enabled

    @safe_execute(default_return=None, log_error=False, error_message="设置LUT选择器失败")
    def _set_lut_selector(self):
        """设置LUT选择器"""
        if self.acq_device.IsFeatureAvailable("LUTSelector"):
            self.acq_device.SetFeatureValue("LUTSelector", "Luminance")

    @safe_execute(default_return=0, log_error=False, error_message="设置LUT映射表失败")
    def _set_lut_mapping_table(self, contrast_factor):
        """设置LUT映射表"""
        success_count = 0
        for i in range(256):
            output = 128 + (i - 128) * contrast_factor
            output = max(0, min(255, int(output)))
            
            # 设置索引
            if self.acq_device.SetFeatureValue("LUTIndex", i):
                # 设置值
                if self.acq_device.SetFeatureValue("LUTValue", output):
                    success_count += 1
                else:
                    break
            else:
                break
        
        return success_count

    @safe_execute(default_return=None, log_error=False, error_message="强制启用LUT失败")
    def _force_enable_lut(self):
        """强制启用LUT"""
        for value in ["1", "true", "True", "On", 1]:
            if safe_call(self.acq_device.SetFeatureValue, "LUTEnable", value):
                break
    
    @ErrorHandler.handle_camera_error
    def set_black_level(self, contrast_value):
        """
        通过黑电平调整对比度（降级方案）
        
        对比度值范围：0-100
        - 0%: 黑电平最高（降低对比度，图像偏灰）
        - 50%: 黑电平中等（正常对比度）
        - 100%: 黑电平最低（增强对比度，黑色更深）
        """
        if not self.acq_device:
            return False
        
        # 检查是否支持 BlackLevel 或 BlackLevelRaw
        feature_name = None
        if self.acq_device.IsFeatureAvailable("BlackLevelRaw"):
            feature_name = "BlackLevelRaw"
        elif self.acq_device.IsFeatureAvailable("BlackLevel"):
            feature_name = "BlackLevel"
        
        if not feature_name:
            return False
        
        # 将对比度值（0-100）映射到黑电平
        # 对比度越高，黑电平越低（黑色更深）
        # 假设黑电平范围是 0-255（需要根据实际相机调整）
        # 对比度 50% → 黑电平 0（默认）
        # 对比度 0% → 黑电平 50（降低对比度）
        # 对比度 100% → 黑电平 -50（增强对比度，但不能为负，所以保持为0）
        
        if contrast_value >= 50:
            # 对比度 50-100%：黑电平保持在 0
            black_level = 0
        else:
            # 对比度 0-50%：黑电平从 50 到 0
            black_level = int((50 - contrast_value) * 1.0)
        
        if self.acq_device.SetFeatureValue(feature_name, black_level):
            return True
        else:
            return False
    
    def get_exposure(self):
        """获取当前曝光时间（毫秒）"""
        if not self.acq_device:
            return 25.0  # 返回默认值
        
        return self._get_camera_parameter_value(
            ["ExposureTimeRaw", "ExposureTime"], 
            25.0, 
            lambda x: x / 1000.0  # 转换微秒到毫秒
        )
    
    def get_gain(self):
        """获取当前增益"""
        if not self.acq_device:
            return 100.0  # 返回默认值
        
        return self._get_camera_parameter_value(
            ["GainRaw", "Gain"], 
            100.0, 
            lambda x: x  # 直接返回
        )

    @safe_execute(default_return=None, log_error=False, error_message="获取相机参数失败")
    def _get_camera_parameter_value(self, feature_names, default_value, converter=None):
        """获取相机参数值的通用方法"""
        from System import String
        
        # 尝试多种方法获取值
        for feature_name in feature_names:
            # 方法1：StrongBox（新版本）
            value = self._try_strongbox_parameter(feature_name)
            if value is not None:
                return converter(value) if converter else value
            
            # 方法2：Reference（旧版本）
            value = self._try_reference_parameter(feature_name)
            if value is not None:
                return converter(value) if converter else value
        
        return default_value  # 所有方法都失败，返回默认值

    @safe_execute(default_return=None, log_error=False, error_message="StrongBox参数获取失败")
    def _try_strongbox_parameter(self, feature_name):
        """使用StrongBox获取参数值"""
        from clr import StrongBox
        from System import String
        
        value_ref = StrongBox[String]()
        if self.acq_device.GetFeatureValue(feature_name, value_ref):
            return float(value_ref.Value)
        return None

    @safe_execute(default_return=None, log_error=False, error_message="Reference参数获取失败")
    def _try_reference_parameter(self, feature_name):
        """使用Reference获取参数值"""
        import clr
        from System import String
        
        value_ref = clr.Reference[String]()
        if self.acq_device.GetFeatureValue(feature_name, value_ref):
            return float(value_ref.Value)
        return None
    
    # ====================================================================
    # 触发模式配置方法
    # ====================================================================
    
    @ErrorHandler.handle_camera_error
    def set_trigger_mode(self, mode, interval_ms=100, delay_ms=0):
        """
        设置触发模式
        
        注意：必须先停止采集才能修改参数
        
        参数:
            mode: 触发模式
                - "internal": 内部定时（自由运行）
                - "hardware": 检测触发（外部硬件触发）
                - "software": 软件触发
            interval_ms: 触发间隔（毫秒），仅用于内部定时模式
            delay_ms: 触发延时（毫秒），仅用于检测触发模式
        
        返回:
            bool: 设置是否成功
        """
        if not self.acq_device or not self.xfer:
            return False
        
        try:
            pass  # print removed
            # 1. 停止采集（释放参数锁定）
            was_running = self._stop_acquisition()
            
            # 2. 设置参数
            success = False
            
            if mode == "internal":
                # 内部定时模式（自由运行）
                pass  # print removed
                pass  # print removed
                # 关闭触发模式（自由运行）
                if self._set_feature("TriggerMode", "Off"):
                    success = True
                
                # 设置帧率
                frame_rate_hz = 1000.0 / interval_ms
                frame_rate_raw = int(frame_rate_hz * 1000)  # 转换为 mHz（毫赫兹）
                
                # 优先使用 Raw 参数（单位：mHz），如果失败则尝试 Hz 参数
                if not self._set_feature("AcquisitionFrameRateRaw", frame_rate_raw):
                    # 如果 Raw 参数不可用，尝试 Hz 参数
                    for feature_name in ["AcquisitionFrameRate", "AcquisitionFrameRateAbs", "FrameRate"]:
                        if self._set_feature(feature_name, frame_rate_hz):
                            break
                
                pass  # print removed
            elif mode == "hardware":
                # 检测触发模式（外部硬件触发）
                pass  # print removed
                pass  # print removed
                # 启用触发模式
                if not self._set_feature("TriggerMode", "On"):
                    success = False
                else:
                    success = True
                    
                    # 设置触发源
                    trigger_sources = ["Line0", "Line1", "ExternalTrigger", "Hardware"]
                    for source in trigger_sources:
                        if self._set_feature("TriggerSource", source):
                            break
                    
                    # 设置触发延时
                    if delay_ms > 0:
                        delay_us = int(delay_ms * 1000)
                        self._set_feature("TriggerDelay", delay_us)
                    
                    pass  # print removed
            elif mode == "software":
                # 软件触发模式
                pass  # print removed
                # 启用触发模式
                if not self._set_feature("TriggerMode", "On"):
                    print(f"   ❌ 无法启用软件触发模式")
                    success = False
                else:
                    # 设置触发源为软件
                    if self._set_feature("TriggerSource", "Software"):
                        pass  # print removed
                        success = True
                    else:
                        print(f"   ❌ 无法设置软件触发源")
                        success = False
            
            else:
                print(f"❌ 未知的触发模式: {mode}")
                success = False
            
            # 3. 重新启动采集
            if was_running:
                if not self._restart_acquisition():
                    success = False
            
            # 4. 保存触发模式到内存和 config（无论相机是否成功，都保存用户的意图）
            if success:
                self.current_trigger_mode = mode
                try:
                    import config
                    config.USER_SENSOR_SETTINGS['trigger_mode'] = mode
                except Exception:
                    pass
            
            return success
        
        except Exception as e:
            print(f"❌ 设置触发模式失败: {e}")
            import traceback
            traceback.print_exc()
            
            # 尝试恢复采集
            if was_running:
                self._restart_acquisition()
            
            return False
    
    @ErrorHandler.handle_camera_error
    def execute_software_trigger(self):
        """
        执行软件触发
        
        仅在软件触发模式下有效
        
        返回:
            bool: 触发是否成功
        """
        if not self.acq_device:
            return False
        
        try:
            # 执行软件触发命令
            if self.acq_device.IsFeatureAvailable("TriggerSoftware"):
                # 方法1: 使用 TriggerSoftware 命令
                if self.acq_device.SetFeatureValue("TriggerSoftware", 1):
                    pass  # print removed
                    return True
            
            # 方法2: 使用 SoftwareTrigger 命令（备用）
            if self.acq_device.IsFeatureAvailable("SoftwareTrigger"):
                if self.acq_device.SetFeatureValue("SoftwareTrigger", 1):
                    pass  # print removed
                    return True
            
            return False
        
        except Exception as e:
            return False
    
    def _set_feature(self, feature_name, value):
        """
        设置相机特性参数（内部辅助方法）
        
        参数:
            feature_name: 特性名称
            value: 特性值
        
        返回:
            bool: 设置是否成功
        """
        if not self.acq_device:
            return False
        
        # 检查特性是否可用
        if not self.acq_device.IsFeatureAvailable(feature_name):
            return False
        
        # 检查特性是否可写
        try:
            # 某些版本的 Sapera SDK 有 IsFeatureWritable 方法
            if hasattr(self.acq_device, 'IsFeatureWritable'):
                if not self.acq_device.IsFeatureWritable(feature_name):
                    return False
        except:
            pass
        
        try:
            # 根据值的类型选择合适的设置方法
            if isinstance(value, str):
                success = self.acq_device.SetFeatureValue(feature_name, value)
            elif isinstance(value, (int, float)):
                success = self.acq_device.SetFeatureValue(feature_name, value)
            else:
                success = self.acq_device.SetFeatureValue(feature_name, str(value))
            
            if success:
                pass  # print removed
                return True
            else:
                return False
        
        except Exception as e:
            return False
    
    def get_trigger_mode(self):
        """
        获取当前触发模式。
        优先从 config.USER_SENSOR_SETTINGS 读取，确保与用户设置一致。
        有相机时同步到硬件，无相机时也能正常返回。
        """
        try:
            import config
            return config.get_user_sensor_settings().get('trigger_mode', 'internal')
        except Exception:
            pass
        # 降级：从内存缓存读
        if hasattr(self, 'current_trigger_mode'):
            return self.current_trigger_mode
        return 'internal'

    def get_gamma(self):
        """获取当前伽马值"""
        if not self.acq_device:
            return 1.0  # 返回默认值
        
        # 检查相机是否支持 Gamma 参数
        if not self.acq_device.IsFeatureAvailable("Gamma"):
            return 1.0  # 返回默认值
        
        try:
            from System import String
            
            # 方法1：StrongBox（新版本）
            try:
                from clr import StrongBox
                value_ref = StrongBox[String]()
                if self.acq_device.GetFeatureValue("Gamma", value_ref):
                    return float(value_ref.Value)
            except (ImportError, AttributeError):
                pass
            
            # 方法2：Reference（旧版本）
            try:
                import clr
                value_ref = clr.Reference[String]()
                if self.acq_device.GetFeatureValue("Gamma", value_ref):
                    return float(value_ref.Value)
            except:
                pass
            
            return 1.0  # 所有方法都失败，返回默认值
        except:
            return 1.0

    def cleanup(self):
        """资源释放"""
        pass  # print removed
        # 1. 先停止采集（优化顺序，避免 CorXferAbort 错误）
        try:
            if self.xfer and self.is_running:
                # 先 Freeze（暂停），等待当前帧完成
                self.xfer.Freeze()
                # 等待一小段时间，让当前帧完成
                import time
                time.sleep(0.05)  # 50ms
                # 再 Abort（中止）
                self.xfer.Abort()
                self.is_running = False
                pass  # print removed
                pass
        except Exception as e:
            # 忽略清理过程中的错误
            pass
        
        # 2. 恢复相机为默认设置（方便下次使用）
        try:
            if self.acq_device:
                pass  # print removed
                # 2.1 关闭触发模式（恢复为自由运行）
                trigger_mode = CAMERA_DEFAULT_PARAMS.get('trigger_mode', 'Off')
                if self.acq_device.IsFeatureAvailable("TriggerMode"):
                    if self.acq_device.SetFeatureValue("TriggerMode", trigger_mode):
                        pass  # print removed
                        pass
                    else:
                        pass
                
                # 2.2 设置帧率
                frame_rate_hz = CAMERA_DEFAULT_PARAMS.get('frame_rate_hz', 6.0)
                frame_rate_raw = int(frame_rate_hz * 1000)  # 转换为 mHz
                
                if self._set_feature("AcquisitionFrameRateRaw", frame_rate_raw):
                    pass  # print removed
                    pass
                elif self._set_feature("AcquisitionFrameRate", frame_rate_hz):
                    pass  # print removed
                    pass
                else:
                    pass
                
                # 2.3 设置曝光时间
                exposure_us = CAMERA_DEFAULT_PARAMS.get('exposure_time_us', 66500)
                
                if self._set_feature("ExposureTimeRaw", exposure_us):
                    pass
                elif self._set_feature("ExposureTime", exposure_us):
                    pass
                else:
                    pass
                
                # 2.4 恢复对比度为默认值（50% = 不增强）
                try:
                    pass  # print removed
                    # 先禁用 LUT
                    lut_disabled = False
                    if hasattr(self.acq_device, 'LutEnable'):
                        self.acq_device.LutEnable = False
                        lut_disabled = True
                    else:
                        # 尝试使用 SetFeatureValue
                        for value in ["0", "false", "False", "Off", 0]:
                            try:
                                if self.acq_device.SetFeatureValue("LUTEnable", value):
                                    lut_disabled = True
                                    break
                            except:
                                continue
                    
                    if lut_disabled:
                        pass  # print(f"   ✅ LUT 已禁用")
                    
                    # 恢复 LUT 映射表为线性映射（50% 对比度）
                    try:
                        if self.acq_device.IsFeatureAvailable("LUTSelector"):
                            self.acq_device.SetFeatureValue("LUTSelector", "Luminance")
                        
                        # 设置线性映射：output = input
                        for i in range(256):
                            self.acq_device.SetFeatureValue("LUTIndex", i)
                            self.acq_device.SetFeatureValue("LUTValue", i)
                        
                        pass  # print removed
                        pass
                    except Exception as e:
                        pass
                    
                except Exception as e:
                    pass
                
                pass  # print removed
        except Exception as e:
            pass
        
        # 3. 释放传输对象
        if self.xfer:
            try:
                self.xfer.Dispose()
                pass  # print removed
                pass
            except Exception as e:
                pass
            finally:
                self.xfer = None
        
        # 4. 释放缓冲区
        if self.buffers:
            try:
                self.buffers.Destroy()
                self.buffers.Dispose()
                pass  # print removed
                pass
            except Exception as e:
                pass
            finally:
                self.buffers = None
        
        # 5. 释放采集设备
        if self.acq_device:
            try:
                self.acq_device.Destroy()
                self.acq_device.Dispose()
                pass  # print removed
                pass
            except Exception as e:
                pass
            finally:
                self.acq_device = None
        
        pass  # print removed
# ==============================================================================
# 3. 主界面（保持不变）
# ==============================================================================
class InspectMainWindow:
    def __init__(self, root, username="admin", role="管理员"):
        self.root = root
        self.username = username
        self.role = role
        self.root.title(f"MINGSEN Express - {username} ({role})")
        self.root.geometry("1280x800")
        
        # 配置样式
        self.style = ttk.Style()
        self.style.configure("White.TLabelframe", background="white")
        self.style.configure("White.TLabelframe.Label", background="white", font=("Microsoft YaHei UI", 9))
        
        # 初始化相机
        self.cam = CameraController()
        self.cam.connect()
        
        # 资源初始化
        self.icons = {}
        self.tk_img_ref = None
        self._init_resources()
        
        # 视频循环控制
        self.video_loop_running = False
        self.video_loop_id = None
        
        # 图像状态（用于在不同界面间传递捕获的图像）
        self.captured_image = None  # 存储当前画布上的静态图像（numpy数组）
        
        # 解决方案制作面板引用
        self.solution_maker_frame = None
        
        # 运行界面引用
        self.run_interface = None

        # 运行统计持久化（程序生命周期内保持）
        self.persistent_stats = {
            "pass": 0,
            "reject": 0,
            "recycle": 0,
            "image_detection_count": 0
        }
        # 最近一次 OCR 识别结果（供控制界面 AppVar 树显示）
        self.ocr_last_results = {}

        # OCR 字段信息（从 SolutionMakerFrame 同步过来）
        self.ocr_field_types = []        # 用户定义的字段名列表
        self.ocr_last_results = {}       # 最近一次识别结果 {field_name: {value, result, confidence}}
        
        # 保存进入工具界面前的画布状态
        self.before_tool_canvas_state = {
            'image': None,              # 画布上显示的图像（numpy数组）
            'trigger_mode': None,       # 触发模式（internal/hardware/software）
            'video_was_running': False, # 视频流是否在运行
            'has_state': False          # 是否有保存的状态
        }
        
        # 记录用户最后选择的方案（仅在本次程序运行期间有效）
        self.last_selected_solution = None
        self._current_workspace_name = None
        
        # OCR 工作状态保存（仅在本次程序运行期间有效）
        self.saved_ocr_state = {
            'image': None,           # 原始图片（numpy数组）
            'image_path': None,      # 图片文件路径（如果是加载的）
            'roi_layout': {},        # 已保存的字段布局
            'temp_layout': {},       # 临时字段布局
            'char_widgets': {},      # 字符模板数据
            'solution_name': None,   # 当前方案名称
            'zoom_scale': 1.0,       # 缩放比例
            'has_state': False       # 是否有保存的状态
        }

        # 操作日志面板引用（在 _create_layout 中创建）
        self.audit_log_panel = None

        # 创建布局
        self._create_layout()

        # 记录登录日志
        self._audit("login", "login_success", operation_result="成功")

        # ★★★ 初始化 TCP 服务和脚本引擎单例 ★★★
        if TcpService is not None and ScriptEngine is not None:
            self.tcp_service = TcpService()
            self.script_engine = ScriptEngine(self.tcp_service)
        else:
            self.tcp_service = None
            self.script_engine = None
        self._tcp_settings_frame = None
        self._script_editor_frame = None

        # 初始化 WorkspaceManager
        from managers.workspace_manager import WorkspaceManager
        import os as _os
        self.workspace_manager = WorkspaceManager(
            workspaces_root=_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "workspaces")
        )

        # 是否有未保存的变更标志
        self._is_dirty = False
        
        # 绑定窗口状态改变事件（监听最大化/还原）
        self.root.bind("<Configure>", self._on_window_configure)
        
        # 设置垂直分割位置（延迟执行，确保窗口已显示）
        self.root.after(100, self._set_initial_sash_position)
        
        # 启动视频循环
        self._start_video_loop()

        # 绑定主窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self._on_main_window_close)

        # ★★★ 软件启动后自动触发一次相机扫描（第二块：UI 层）★★★
        if hasattr(self, 'camera_status_bar') and self.camera_status_bar:
            self.root.after(500, self.camera_status_bar.trigger_initial_scan)

        # 注册 Sapera 连接器
        self._register_sapera_connector()

        self.root._app_instance = self

    def _register_sapera_connector(self):
        """桥接 CameraManager 与 CameraController"""
        from managers.camera_manager import CameraManager
        from camera.camera_discovery import CameraInfo, _find_camera_subnet_ip
        mgr = CameraManager()

        def _connect(server_name):
            if not server_name: return False
            if self.cam.current_server_name == server_name and self.cam.acq_device is not None:
                return True
            return self.cam.switch_to(server_name)

        def _disconnect():
            self.cam.disconnect()

        mgr.set_sapera_connector(_connect, _disconnect)

        # 同步当前相机状态
        if self.cam.acq_device is not None:
            ip = self._get_camera_ip_from_device()
            if not ip:
                ip = _find_camera_subnet_ip()
            cam_info = CameraInfo(ip=ip or "0.0.0.0", port=5024, name="",
                                  server_name=self.cam.current_server_name)
            mgr.set_initial_camera(cam_info)

        def _on_first_scan(cameras):
            sn = self.cam.current_server_name
            if sn:
                for cam in cameras:
                    if cam.server_name == sn:
                        mgr.set_initial_camera(cam)
                        break
            if not cameras and mgr.current_camera:
                for cb in getattr(mgr, '_scan_callbacks', []):
                    if cb is not _on_first_scan:
                        try: cb([mgr.current_camera])
                        except Exception: pass
            try: mgr._scan_callbacks.remove(_on_first_scan)
            except ValueError: pass
        mgr.on_scan_complete(_on_first_scan)

    def _get_camera_ip_from_device(self):
        """从 Sapera 设备获取相机 IP"""
        try:
            dev = self.cam.acq_device
            if not dev: return ""
            for feat in ["GevDeviceIPAddress","GevCurrentIPAddress","DeviceIPAddress"]:
                try:
                    if not dev.IsFeatureAvailable(feat): continue
                    from clr import StrongBox
                    from System import String
                    ref = StrongBox[String]()
                    if dev.GetFeatureValue(feat, ref) and ref.Value:
                        ip = str(ref.Value).strip()
                        if ip and ip != "0.0.0.0": return ip
                except Exception: pass
                try:
                    import clr
                    from System import String
                    ref = clr.Reference[String]()
                    if dev.GetFeatureValue(feat, ref) and ref.Value:
                        ip = str(ref.Value).strip()
                        if ip and ip != "0.0.0.0": return ip
                except Exception: pass
        except Exception: pass
        return self._get_ip_from_arp()

    def _get_ip_from_arp(self):
        """通过 ARP 表获取相机 IP（相机通电就一定有，不依赖端口/协议/SDK）"""
        try:
            import subprocess, ipaddress
            from camera.camera_discovery import _find_camera_subnet_ip
            subnet = _find_camera_subnet_ip()
            if not subnet:
                return ""
            nic_ip = subnet.rsplit(".", 1)[0] + ".1"
            for attempt in range(2):
                if attempt == 1:
                    # fallback: try .12 (known camera NIC)
                    nic_ip = subnet.rsplit(".", 1)[0] + ".12"
                try:
                    r = subprocess.run(["arp", "-a", "-N", nic_ip],
                                       capture_output=True, text=True, timeout=3)
                    for line in r.stdout.split("\n"):
                        if "动态" in line or "dynamic" in line.lower():
                            parts = line.split()
                            for p in parts:
                                p = p.strip()
                                if p.count(".") == 3:
                                    try: ipaddress.IPv4Address(p); return p
                                    except Exception: pass
                except Exception:
                    continue
        except Exception:
            pass
        return ""

    def _on_window_configure(self, event):
        """
        窗口配置改变事件处理（包括最大化/还原）
        """
        # 只处理窗口本身的事件，不处理子控件的事件
        if event.widget == self.root:
            pass  # print removed
            # 如果有捕获的图像，立即停止视频循环并触发画布重绘
            if hasattr(self, 'solution_maker_frame') and self.solution_maker_frame:
                if hasattr(self.solution_maker_frame, 'original_image') and self.solution_maker_frame.original_image is not None:
                    pass  # print removed
                    # 【关键修复】立即停止视频循环，不等待延迟
                    if self.video_loop_running:
                        self.video_loop_running = False
                        pass  # print removed
                    # 取消所有待执行的视频循环回调
                    if hasattr(self, 'video_loop_id') and self.video_loop_id:
                        try:
                            self.root.after_cancel(self.video_loop_id)
                            self.video_loop_id = None
                            pass  # print removed
                            pass
                        except:
                            pass
                    
                    # 清除视频帧
                    self.preview_canvas.delete("video_frame")
                    
                    # 延迟一小段时间，等待窗口完全调整好大小后再重绘
                    self.root.after(50, self._handle_window_resize_with_image)
    
    def _handle_window_resize_with_image(self):
        """
        处理窗口大小改变时的图像重绘
        """
        if hasattr(self, 'solution_maker_frame') and self.solution_maker_frame:
            if hasattr(self.solution_maker_frame, 'original_image') and self.solution_maker_frame.original_image is not None:
                pass  # print removed
                # 停止视频循环
                if self.video_loop_running:
                    self.video_loop_running = False
                    pass  # print removed
                # 取消视频循环回调
                if hasattr(self, 'video_loop_id') and self.video_loop_id:
                    try:
                        self.root.after_cancel(self.video_loop_id)
                        self.video_loop_id = None
                        pass  # print removed
                        pass
                    except:
                        pass
                
                # 清除视频帧
                self.preview_canvas.delete("video_frame")
                
                # 重新计算缩放比例
                old_scale = self.solution_maker_frame.zoom_scale
                self.solution_maker_frame.zoom_scale = self.solution_maker_frame._get_90_percent_scale()
                pass  # print removed
                # 刷新显示
                self.solution_maker_frame._refresh_canvas_image()
                
                pass  # print removed
    def _set_initial_sash_position(self):
        """设置初始分割位置，让预览区域占据更大空间"""
        try:
            # 获取垂直分割窗口的总高度
            total_height = self.vertical_paned.winfo_height()
            if total_height > 100:
                # 预览区域占65%，日志面板占35%
                sash0 = int(total_height * 0.65)
                self.vertical_paned.sash_place(0, 0, sash0)
        except Exception as e:
            pass

    def _init_resources(self):
        """初始化图标资源"""
        self.icon_size = (40, 40)
        # 预加载图标
        icon_config = {
            'folder': ("folder.png", "#999999", "?"),
            'run': ("run.png", "#999999", "?"),
            'sensor': ("sensor.png", "#999999", "?"),
            'tools': ("tool.png", "#999999", "?"),
            'control': ("control.png", "#999999", "?"),
            'user': ("user.png", "#999999", "?"),
            'close': ("close.png", "#B22222", "✖")
        }
        
        for key, (filename, fallback_color, fallback_char) in icon_config.items():
            self.icons[key] = self._load_icon(filename, self.icon_size, fallback_color, fallback_char)

    def _load_icon(self, filename, size, fallback_color, fallback_char):
        """加载图标"""
        base_path = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_path, "icon", filename)
        
        try:
            pil_img = Image.open(icon_path)
            pil_img = pil_img.resize(size, Image.LANCZOS)
            return ImageTk.PhotoImage(pil_img)
        except (FileNotFoundError, IOError):
            return self._create_icon_fallback(fallback_color, fallback_char)

    def _create_icon_fallback(self, color, char):
        """创建备用图标"""
        img = Image.new('RGB', (32, 32), color=color)
        draw = ImageDraw.Draw(img)
        draw.text((8, 8), char, fill="white")
        return ImageTk.PhotoImage(img)

    def _create_layout(self):
        """创建布局"""
        self.paned_window = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashwidth=4, bg="#E0E0E0")
        self.paned_window.pack(fill=tk.BOTH, expand=True)

        # 左侧边栏（保持400px宽度）
        self.sidebar_frame = tk.Frame(self.paned_window, bg="white", padx=0, pady=0, width=400)
        self.paned_window.add(self.sidebar_frame, minsize=340, width=400, stretch="never")
        self.show_main_menu()

        # 右侧显示区
        display_frame = tk.Frame(self.paned_window, bg="#808080")
        self.paned_window.add(display_frame, stretch="always")

        # 顶部状态栏
        top_bar = tk.Frame(display_frame, bg="#808080", height=32)
        top_bar.pack(fill=tk.X)
        top_bar.pack_propagate(False)

        # ★★★ 相机状态栏（第二块：UI 层）★★★
        try:
            from ui.CameraStatusBar import CameraStatusBar
            self.camera_status_bar = CameraStatusBar(
                top_bar,
                username=self.username,
                role=self.role,
                bg="#808080",
            )
            self.camera_status_bar.pack(side=tk.LEFT, fill=tk.Y)
        except Exception as _e:
            print(f"[CameraStatusBar] 加载失败: {_e}")
            self.camera_status_bar = None

        tk.Label(top_bar, text="(228, 445): 0   Running...", fg="white", bg="#808080", font=("Consolas", 9)).pack(side=tk.LEFT, padx=5)

        # 创建垂直分割的PanedWindow（上下分割）
        self.vertical_paned = tk.PanedWindow(display_frame, orient=tk.VERTICAL, sashwidth=4, bg="#E0E0E0")
        self.vertical_paned.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # 上方：实时预览画布（红色框区域）
        preview_frame = tk.Frame(self.vertical_paned, bg="#808080")
        self.vertical_paned.add(preview_frame, minsize=400, stretch="always")
        
        # 在 preview_frame 内部创建垂直 PanedWindow（用于画布和解决方案面板）
        self.preview_paned = tk.PanedWindow(preview_frame, orient=tk.VERTICAL, sashwidth=4, bg="#E0E0E0", sashrelief=tk.FLAT)
        self.preview_paned.pack(fill=tk.BOTH, expand=True)
        
        # 画布容器（上方）
        canvas_main_frame = tk.Frame(self.preview_paned, bg="#808080")
        self.preview_paned.add(canvas_main_frame, minsize=300, stretch="always")
        
        # 解决方案管理面板容器（下方，初始隐藏）
        self.solution_panel_container = tk.Frame(self.preview_paned, bg="#f0f0f0")
        # 初始不添加到 PanedWindow，等用户点击"解决方案"按钮时再添加
        self.solution_panel = None  # 解决方案管理面板实例
        self.solution_panel_visible = False  # 面板是否可见
        
        # 预览区域底部工具栏（缩放控制）- 先创建工具栏
        preview_toolbar = tk.Frame(canvas_main_frame, bg="#E0E0E0", height=12)
        preview_toolbar.pack(fill=tk.X, side=tk.BOTTOM)
        preview_toolbar.pack_propagate(False)  # 固定高度
        
        # 按钮通用样式
        btn_style = {
            "font": ("Arial", 7),
            "bg": "#F5F5F5",
            "relief": tk.FLAT,
            "bd": 1,
            "cursor": "hand2",
            "height": 1
        }
        
        # 快速放大按钮 (1.3倍)
        btn_zoom_in_fast = tk.Button(
            preview_toolbar, 
            text="++", 
            **btn_style,
            command=lambda: self._zoom_image(1.3)
        )
        btn_zoom_in_fast.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=1, pady=1)
        self._add_tooltip(btn_zoom_in_fast, "快速放大 (1.3x)")
        
        # 慢速放大按钮 (1.1倍)
        btn_zoom_in = tk.Button(
            preview_toolbar, 
            text="+", 
            **btn_style,
            command=lambda: self._zoom_image(1.1)
        )
        btn_zoom_in.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=1, pady=1)
        self._add_tooltip(btn_zoom_in, "慢速放大 (1.1x)")
        
        # 分隔线
        tk.Frame(preview_toolbar, width=1, bg="#AAAAAA").pack(side=tk.LEFT, fill=tk.Y, pady=2)
        
        # 原始大小按钮（高度90%适配，居中显示）
        btn_zoom_100 = tk.Button(
            preview_toolbar, 
            text="1:1", 
            **btn_style,
            command=lambda: self._zoom_image(0, fit_mode="actual")
        )
        btn_zoom_100.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=1, pady=1)
        self._add_tooltip(btn_zoom_100, "原始大小（高度90%）")
        
        # 填充窗口按钮（高度填充，宽度按比例）
        def test_button_click():
            pass  # print removed
            pass  # print removed
            pass  # print removed
            self._zoom_image(0, fit_mode="fit")
        
        btn_zoom_fit = tk.Button(
            preview_toolbar, 
            text="⊡", 
            font=("Arial", 8),
            bg="#F5F5F5",
            relief=tk.FLAT,
            bd=1,
            cursor="hand2",
            height=1,
            command=test_button_click
        )
        btn_zoom_fit.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=1, pady=1)
        self._add_tooltip(btn_zoom_fit, "填充窗口（高度填充）")
        
        # 分隔线
        tk.Frame(preview_toolbar, width=1, bg="#AAAAAA").pack(side=tk.LEFT, fill=tk.Y, pady=2)
        
        # 慢速缩小按钮 (1/1.1倍)
        btn_zoom_out = tk.Button(
            preview_toolbar, 
            text="-", 
            **btn_style,
            command=lambda: self._zoom_image(1/1.1)
        )
        btn_zoom_out.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=1, pady=1)
        self._add_tooltip(btn_zoom_out, "慢速缩小 (1/1.1x)")
        
        # 快速缩小按钮 (1/1.3倍)
        btn_zoom_out_fast = tk.Button(
            preview_toolbar, 
            text="--", 
            **btn_style,
            command=lambda: self._zoom_image(1/1.3)
        )
        btn_zoom_out_fast.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=1, pady=1)
        self._add_tooltip(btn_zoom_out_fast, "快速缩小 (1/1.3x)")
        
        # 分隔线
        tk.Frame(preview_toolbar, width=1, bg="#AAAAAA").pack(side=tk.LEFT, fill=tk.Y, pady=2)
        
        # 右侧：缩放比例显示
        zoom_info_frame = tk.Frame(preview_toolbar, bg="#E0E0E0", width=60)
        zoom_info_frame.pack(side=tk.LEFT, fill=tk.Y, padx=2)
        zoom_info_frame.pack_propagate(False)
        
        self.zoom_label = tk.Label(
            zoom_info_frame,
            text="100%",
            font=("Arial", 7),
            bg="#E0E0E0",
            fg="#333333"
        )
        self.zoom_label.pack(expand=True)
        
        # 创建带滚动条的画布容器
        canvas_container = tk.Frame(canvas_main_frame, bg="#808080")
        canvas_container.pack(fill=tk.BOTH, expand=True)
        
        # 水平滚动条
        h_scrollbar = tk.Scrollbar(canvas_container, orient=tk.HORIZONTAL)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 垂直滚动条
        v_scrollbar = tk.Scrollbar(canvas_container, orient=tk.VERTICAL)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 画布
        self.preview_canvas = tk.Canvas(
            canvas_container, 
            bg="#A9A9A9", 
            highlightthickness=0,
            xscrollcommand=h_scrollbar.set,
            yscrollcommand=v_scrollbar.set
        )
        self.preview_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 配置滚动条
        h_scrollbar.config(command=self.preview_canvas.xview)
        v_scrollbar.config(command=self.preview_canvas.yview)
        
        # 初始化视频缩放比例（默认为宽高适配模式）
        self.video_zoom_scale = -1.0  # -1.0表示宽高适配模式（原始大小）
        self.fit_window_scale = None  # 保存填充窗口时的缩放比例
        
        # 保存当前缩放比例
        self.current_zoom_scale = 1.0
        
        # 保存用户滚动位置（避免视频循环重置滚动）
        self.user_scroll_x = None
        self.user_scroll_y = None
        self.scroll_initialized = False
        self.is_user_scrolling = False  # 标记是否是用户主动滚动
        
        # 拖动画面相关变量
        self.is_dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.drag_scroll_start_x = 0
        self.drag_scroll_start_y = 0
        
        # 绑定滚动条拖动事件，记录用户滚动位置
        def on_h_scroll(*args):
            # 标记为用户主动滚动
            self.is_user_scrolling = True
            # 立即记录滚动位置（不延迟）
            try:
                self.user_scroll_x = self.preview_canvas.xview()[0]
            except:
                pass
        
        def on_v_scroll(*args):
            # 标记为用户主动滚动
            self.is_user_scrolling = True
            # 立即记录滚动位置（不延迟）
            try:
                self.user_scroll_y = self.preview_canvas.yview()[0]
            except:
                pass
        
        # 配置滚动条命令（先执行Canvas的滚动，再记录位置）
        def h_scroll_command(*args):
            self.preview_canvas.xview(*args)
            on_h_scroll(*args)
        
        def v_scroll_command(*args):
            self.preview_canvas.yview(*args)
            on_v_scroll(*args)
        
        h_scrollbar.config(command=h_scroll_command)
        v_scrollbar.config(command=v_scroll_command)
        
        # 绑定鼠标滚轮事件
        def on_mousewheel(event):
            self.is_user_scrolling = True
            # 立即记录滚动位置（不延迟）
            try:
                self.user_scroll_x = self.preview_canvas.xview()[0]
                self.user_scroll_y = self.preview_canvas.yview()[0]
            except:
                pass
        
        self.preview_canvas.bind("<MouseWheel>", on_mousewheel, add="+")
        self.preview_canvas.bind("<Button-4>", on_mousewheel, add="+")  # Linux
        self.preview_canvas.bind("<Button-5>", on_mousewheel, add="+")  # Linux
        
        # 绑定Ctrl+鼠标左键拖动事件
        def on_drag_start(event):
            # 检查是否按下Ctrl键
            if event.state & 0x0004:  # Ctrl键的状态码
                self.is_dragging = True
                self.drag_start_x = event.x
                self.drag_start_y = event.y
                # 记录当前滚动位置
                try:
                    scroll_x = self.preview_canvas.xview()
                    scroll_y = self.preview_canvas.yview()
                    self.drag_scroll_start_x = scroll_x[0]
                    self.drag_scroll_start_y = scroll_y[0]
                except:
                    self.drag_scroll_start_x = 0
                    self.drag_scroll_start_y = 0
                # 改变鼠标光标为手型
                self.preview_canvas.config(cursor="fleur")
        
        def on_drag_motion(event):
            if self.is_dragging:
                # 计算鼠标移动的距离
                dx = event.x - self.drag_start_x
                dy = event.y - self.drag_start_y
                
                # 获取滚动区域信息
                try:
                    scrollregion = self.preview_canvas.cget("scrollregion")
                    if scrollregion:
                        x1, y1, x2, y2 = map(float, scrollregion.split())
                        scroll_width = x2 - x1
                        scroll_height = y2 - y1
                        
                        # 获取Canvas可见区域大小
                        canvas_width = self.preview_canvas.winfo_width()
                        canvas_height = self.preview_canvas.winfo_height()
                        
                        # 计算新的滚动位置（注意：拖动方向与滚动方向相反）
                        if scroll_width > canvas_width:
                            # 将像素移动转换为滚动比例
                            scroll_dx = -dx / scroll_width
                            new_scroll_x = self.drag_scroll_start_x + scroll_dx
                            new_scroll_x = max(0.0, min(1.0, new_scroll_x))
                            self.preview_canvas.xview_moveto(new_scroll_x)
                            # 标记为用户滚动
                            self.is_user_scrolling = True
                            self.user_scroll_x = new_scroll_x
                        
                        if scroll_height > canvas_height:
                            # 将像素移动转换为滚动比例
                            scroll_dy = -dy / scroll_height
                            new_scroll_y = self.drag_scroll_start_y + scroll_dy
                            new_scroll_y = max(0.0, min(1.0, new_scroll_y))
                            self.preview_canvas.yview_moveto(new_scroll_y)
                            # 标记为用户滚动
                            self.is_user_scrolling = True
                            self.user_scroll_y = new_scroll_y
                except:
                    pass
        
        def on_drag_end(event):
            if self.is_dragging:
                self.is_dragging = False
                # 恢复默认鼠标光标
                self.preview_canvas.config(cursor="")
        
        # 绑定鼠标事件
        self.preview_canvas.bind("<ButtonPress-1>", on_drag_start)
        self.preview_canvas.bind("<B1-Motion>", on_drag_motion)
        self.preview_canvas.bind("<ButtonRelease-1>", on_drag_end)
        
        # 处理Ctrl键释放的情况（取消拖动）
        def on_key_release(event):
            if self.is_dragging and event.keysym == "Control_L" or event.keysym == "Control_R":
                self.is_dragging = False
                self.preview_canvas.config(cursor="")
        
        self.preview_canvas.bind("<KeyRelease>", on_key_release)
        # 确保Canvas可以接收键盘事件
        self.preview_canvas.focus_set()
        
        # 绑定画布大小改变事件（关键修复：自动缩放捕获的图像）
        self.preview_canvas.bind("<Configure>", self._on_preview_canvas_resize)

        # 下方：字符模板画布（蓝色框区域）+ 脚本面板（TCP设置时显示）
        self.template_frame = tk.Frame(self.vertical_paned, bg="#808080")
        self.vertical_paned.add(self.template_frame, minsize=150, stretch="never")

        # 脚本面板容器（初始隐藏，show_tcp_settings 时显示）
        self.script_bottom_frame = tk.Frame(self.template_frame, bg="white")
        # 初始不 pack，等 show_tcp_settings 调用时再显示
        
        # 创建字符模板滚动区域
        self.template_canvas = tk.Canvas(self.template_frame, bg="white", highlightthickness=0)
        template_scrollbar = tk.Scrollbar(self.template_frame, orient=tk.VERTICAL, command=self.template_canvas.yview)
        self.template_canvas.configure(yscrollcommand=template_scrollbar.set)
        self._template_scrollbar_ref = template_scrollbar  # 保存引用，供恢复时使用

        template_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.template_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 创建模板内容容器
        self.template_scroll_frame = tk.Frame(self.template_canvas, bg="white")
        self.template_scroll_window = self.template_canvas.create_window(
            (0, 0),
            window=self.template_scroll_frame,
            anchor="nw"
        )
        
        # 绑定配置事件
        self.template_scroll_frame.bind(
            "<Configure>",
            lambda e: self.template_canvas.configure(scrollregion=self.template_canvas.bbox("all"))
        )
        self.template_canvas.bind(
            "<Configure>",
            lambda e: self.template_canvas.itemconfig(self.template_scroll_window, width=e.width)
        )
        
        # 绑定鼠标滚轮事件（支持滚动）
        def _on_mousewheel(event):
            self.template_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        self.template_canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.template_scroll_frame.bind_all("<MouseWheel>", _on_mousewheel)

        # 默认隐藏字符模板画布（日志面板会占满此区域；工具界面使用时再显示）
        template_scrollbar.pack_forget()
        self.template_canvas.pack_forget()

        # 保留原有的canvas引用（用于ROI标注）
        self.canvas = self.preview_canvas

        # 操作日志面板：直接放入 template_frame，占满摄像头下方整块区域
        if AuditLogPanel is not None:
            self.audit_log_panel = AuditLogPanel(
                self.template_frame,
                viewer_name=self.username,
                viewer_role=self.role,
            )
            self.audit_log_panel.frame.pack(fill=tk.BOTH, expand=True)
    
    def _add_tooltip(self, widget, text):
        """添加工具提示"""
        def on_enter(event):
            # 创建提示窗口
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            label = tk.Label(
                tooltip, 
                text=text, 
                background="#FFFFCC", 
                relief=tk.SOLID, 
                borderwidth=1,
                font=("Arial", 8)
            )
            label.pack()
            widget.tooltip = tooltip
        
        def on_leave(event):
            if hasattr(widget, 'tooltip'):
                widget.tooltip.destroy()
                del widget.tooltip
        
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
    
    def _zoom_image(self, scale_factor, fit_mode=None):
        """
        缩放图像
        
        参数:
            scale_factor: 缩放倍数（相对于当前大小）
            fit_mode: 特殊模式 - "actual"=原始大小（高度90%）, "fit"=填充窗口（高度100%）
        """
        pass  # print removed
        
        # 优先级1: 检查是否在解决方案制作面板且有捕获的图像
        if self.solution_maker_frame and hasattr(self.solution_maker_frame, 'original_image'):
            pass  # print removed
            if self.solution_maker_frame.original_image is not None:
                pass  # print removed
                pass  # print removed
                # 关键修复：立即停止视频循环，防止它清空画布
                if self.video_loop_running:
                    self.video_loop_running = False
                    pass  # print removed
                # 取消所有待执行的视频循环回调
                if hasattr(self, 'video_loop_id') and self.video_loop_id:
                    try:
                        self.root.after_cancel(self.video_loop_id)
                        self.video_loop_id = None
                        pass  # print removed
                        pass
                    except:
                        pass
                
                # 清除画布上的视频帧
                self.preview_canvas.delete("video_frame")
                
                # 有捕获的图像，调用解决方案面板的缩放方法
                if fit_mode == "actual":
                    # 原始大小 = 高度90%
                    self.solution_maker_frame.zoom_scale = self.solution_maker_frame._get_90_percent_scale()
                    pass  # print removed
                    pass
                elif fit_mode == "fit":
                    # 填充窗口 = 高度100%
                    self.solution_maker_frame.zoom_scale = self.solution_maker_frame._get_height_fit_scale()
                    pass  # print removed
                    pass
                else:
                    # 相对缩放
                    old_scale = self.solution_maker_frame.zoom_scale
                    self.solution_maker_frame.zoom_scale *= scale_factor
                    # 限制缩放范围
                    self.solution_maker_frame.zoom_scale = max(0.1, min(10.0, self.solution_maker_frame.zoom_scale))
                    pass  # print removed
                # 刷新显示
                pass  # print removed
                self.solution_maker_frame._refresh_canvas_image()
                
                # 更新缩放比例显示
                zoom_percent = int(self.solution_maker_frame.zoom_scale * 100)
                self.zoom_label.config(text=f"{zoom_percent}%")
                
                pass  # print removed
                return
            else:
                pass
        else:
            pass
        
        # 优先级2: 检查是否在工具界面且有捕获的图像
        if hasattr(self, 'captured_image') and self.captured_image is not None:
            # 停止视频循环
            if self.video_loop_running:
                self.video_loop_running = False
            if hasattr(self, 'video_loop_id') and self.video_loop_id:
                try:
                    self.root.after_cancel(self.video_loop_id)
                    self.video_loop_id = None
                except:
                    pass
            
            # 清除画布上的视频帧
            self.canvas.delete("video_frame")
            
            # 获取画布尺寸
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width = 800
                canvas_height = 600
            
            # 获取原始图像尺寸
            img_height, img_width = self.captured_image.shape[:2]
            
            # 计算新的缩放比例
            if fit_mode == "actual":
                # 原始大小 = 高度90%
                new_scale = (canvas_height * 0.9) / img_height
            elif fit_mode == "fit":
                # 填充窗口 = 高度100%
                new_scale = canvas_height / img_height
            else:
                # 相对缩放
                if not hasattr(self, 'tool_image_zoom_scale') or self.tool_image_zoom_scale is None:
                    # 如果没有缩放比例，使用默认的90%高度
                    self.tool_image_zoom_scale = (canvas_height * 0.9) / img_height
                
                new_scale = self.tool_image_zoom_scale * scale_factor
                # 限制缩放范围
                new_scale = max(0.1, min(10.0, new_scale))
            
            # 保存新的缩放比例
            self.tool_image_zoom_scale = new_scale
            
            # 重新显示图像（使用新的缩放比例）
            self._redraw_tool_canvas_image()
            
            # 更新缩放比例显示
            zoom_percent = int(new_scale * 100)
            self.zoom_label.config(text=f"{zoom_percent}%")
            
            return
        
        # 优先级3: 没有捕获的图像，控制实时视频流的缩放
        if fit_mode == "actual":
            # 原始大小 = 高度90%
            # 使用特殊标记值 -1.0 表示高度90%模式
            self.video_zoom_scale = -1.0
            # 重置滚动标记，让画面重新居中
            self.scroll_initialized = False
            self.is_user_scrolling = False
            self.user_scroll_x = None
            self.user_scroll_y = None
        elif fit_mode == "fit":
            # 填充窗口 = 高度100%
            self.video_zoom_scale = None  # 使用None触发高度100%计算
            # 重置滚动标记，让画面重新居中
            self.scroll_initialized = False
            self.is_user_scrolling = False
            self.user_scroll_x = None
            self.user_scroll_y = None
        else:
            # 相对缩放
            if self.video_zoom_scale is None or self.video_zoom_scale == -1.0:
                # 如果当前是自适应模式，先获取当前实际缩放比例
                # 从视频循环中获取
                self.video_zoom_scale = self.current_zoom_scale
            
            self.video_zoom_scale *= scale_factor
            # 限制缩放范围
            self.video_zoom_scale = max(0.1, min(10.0, self.video_zoom_scale))
            # 缩放改变时，重置滚动标记，让画面重新居中
            self.scroll_initialized = False
            self.is_user_scrolling = False
            self.user_scroll_x = None
            self.user_scroll_y = None
        
        # 更新缩放比例显示
        if self.video_zoom_scale is None:
            # 填充窗口模式显示为100%
            zoom_percent = 100
        elif self.video_zoom_scale == -1.0:
            # 原始大小模式显示为90%
            zoom_percent = 90
        elif self.video_zoom_scale > 0:
            # 用户自定义缩放，计算相对于Canvas高度的百分比
            # 获取原始图像高度（从相机获取）
            try:
                h = self.cam.height if self.cam.height > 0 else 1200
                ch = self.canvas.winfo_height()
                if ch > 1:
                    zoom_percent = int((self.video_zoom_scale * h / ch) * 100)
                else:
                    zoom_percent = int(self.video_zoom_scale * 100)
            except:
                zoom_percent = int(self.video_zoom_scale * 100)
        else:
            # 兜底：按实际比例显示
            zoom_percent = int(self.current_zoom_scale * 100)
        self.zoom_label.config(text=f"{zoom_percent}%")
        
        pass  # print removed
    @ErrorHandler.handle_ui_error
    def clear_sidebar(self):
        """清空侧边栏"""
        # 【关键修复】在清空侧边栏之前，只停止视频循环，不清空 run_interface 引用
        # 这样从其他界面返回运行界面时，run_interface 实例和检测线程仍然存活
        if hasattr(self, 'run_interface') and self.run_interface is not None:
            if hasattr(self.run_interface, '_stop_video_loop'):
                self.run_interface._stop_video_loop()
            # 注意：不清空 run_interface = None，保留实例以便复用

        # 切换到子界面时隐藏日志面板
        if hasattr(self, 'audit_log_panel') and self.audit_log_panel is not None:
            self.audit_log_panel.frame.pack_forget()

        # 切换界面时恢复字符模板画布，隐藏脚本面板
        self._restore_template_canvas()

        # 销毁所有侧边栏 widgets
        for widget in self.sidebar_frame.winfo_children():
            widget.destroy()

    def _restore_template_canvas(self):
        """隐藏脚本面板（切换到非控制界面时调用）。"""
        if hasattr(self, 'script_bottom_frame'):
            self.script_bottom_frame.pack_forget()

    @ErrorHandler.handle_ui_error
    def show_main_menu(self):
        """显示主菜单"""
        self.clear_sidebar()

        # 主界面：隐藏字符模板画布，恢复日志面板
        if hasattr(self, 'template_canvas'):
            self.template_canvas.pack_forget()
        if hasattr(self, '_template_scrollbar_ref'):
            self._template_scrollbar_ref.pack_forget()
        if hasattr(self, 'audit_log_panel') and self.audit_log_panel is not None:
            self.template_frame.config(bg="#808080")
            self.audit_log_panel.frame.pack(fill=tk.BOTH, expand=True)

        content = tk.Frame(self.sidebar_frame, bg="white", padx=10, pady=10)
        content.pack(fill=tk.BOTH, expand=True)

        # Logo
        tk.Label(content, text="MINGSEN\nOCR", font=("Arial", 16, "bold"), fg="#0055A4", bg="white", justify=tk.LEFT).pack(anchor="w", pady=(0, 20))

        # 双列容器 → 单一组件，四个按钮 2×2 网格
        btn_frame = ttk.LabelFrame(content, text="功能选择", style="White.TLabelframe")
        btn_frame.pack(fill=tk.X, pady=10)
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        # 第一行：解决方案、传感器（管理员/技术员）
        sol_btn = self._create_img_btn(btn_frame, "解决方案", self.icons['folder'], command=self._show_solution_disabled_message, return_btn=True)
        if sol_btn:
            sol_btn.grid(row=0, column=0, sticky="nsew", padx=3, pady=3)

        if self.role in ["管理员", "技术员"]:
            sensor_btn = self._create_img_btn(btn_frame, "传感器", self.icons['sensor'], command=self.show_sensor_settings, return_btn=True)
            if sensor_btn:
                sensor_btn.grid(row=0, column=1, sticky="nsew", padx=3, pady=3)

            # 第二行：工具、控制
            tool_btn = self._create_img_btn(btn_frame, "工具", self.icons['tools'], command=self.show_tool_interface, return_btn=True)
            if tool_btn:
                tool_btn.grid(row=1, column=0, sticky="nsew", padx=3, pady=3)

            ctrl_btn = self._create_img_btn(btn_frame, "控制", self.icons['control'], command=self.show_tcp_settings, return_btn=True)
            if ctrl_btn:
                ctrl_btn.grid(row=1, column=1, sticky="nsew", padx=3, pady=3)

        # 第三行：运行
        run_btn = self._create_img_btn(btn_frame, "运行", self.icons['run'], command=self.show_run_interface, return_btn=True)
        if run_btn:
            run_btn.grid(row=2, column=0, sticky="nsew", padx=3, pady=3)

        # 底部按钮
        tk.Frame(content, height=30, bg="white").pack()
        # 仅管理员显示用户管理
        if self.role == "管理员":
            self._create_img_btn(content, "用户管理", self.icons['user'], side=tk.TOP, command=self.show_user_management)
        self._create_img_btn(content, "退出登录", None, side=tk.TOP, command=self.logout)
        self._create_img_btn(content, "关闭", self.icons['close'], side=tk.BOTTOM, command=self.close_application)

    # ------------------------------------------------------------------
    # 操作日志辅助方法
    # ------------------------------------------------------------------
    def _audit(
        self,
        operation_type: str,
        operation_action: str,
        target_object: str = "",
        old_value: str = "",
        new_value: str = "",
        operation_result: str = "成功",
    ):
        """向操作日志面板写入一条记录（线程安全）"""
        try:
            if self.audit_log_panel is not None:
                self.audit_log_panel.append_log(
                    user_name=self.username,
                    user_role=self.role,
                    operation_type=operation_type,
                    operation_action=operation_action,
                    target_object=target_object,
                    old_value=old_value,
                    new_value=new_value,
                    operation_result=operation_result,
                )
            elif AuditLogManager is not None:
                AuditLogManager().log(
                    user_name=self.username,
                    user_role=self.role,
                    operation_type=operation_type,
                    operation_action=operation_action,
                    target_object=target_object,
                    old_value=old_value,
                    new_value=new_value,
                    operation_result=operation_result,
                )
        except Exception:
            pass

    def _camera_target_object(self, suffix: str = "") -> str:
        """
        日志字段规范：返回携带当前相机名和 IP 的 target_object 字符串。
        格式：'CAM-B@192.168.10.22' 或 'CAM-B@192.168.10.22 > 传感器设置面板'
        若无相机连接则只返回 suffix。
        """
        try:
            from managers.camera_manager import CameraManager
            cam = CameraManager().current_camera
            if cam:
                label = cam.name if cam.name else cam.ip
                cam_str = f"{label}@{cam.ip}"
                return f"{cam_str} > {suffix}" if suffix else cam_str
        except Exception:
            pass
        return suffix

    def close_application(self):
        """关闭应用程序（正确清理资源）"""
        pass  # print removed
        try:
            # 停止视频循环
            self.video_loop_running = False
            if self.video_loop_id:
                self.root.after_cancel(self.video_loop_id)
            pass  # print removed
            # 停止 TCP 服务和脚本引擎
            if hasattr(self, 'tcp_service') and self.tcp_service:
                self.tcp_service.stop()
            if hasattr(self, 'script_engine') and self.script_engine:
                self.script_engine.stop_periodic()
            # 清理相机资源
            if self.cam:
                self.cam.cleanup()
                pass  # print removed
                pass
        except Exception as e:
            pass
        finally:
            # 关闭窗口
            self.root.quit()
            pass  # print removed

    def _mark_dirty(self):
        """标记有未保存的变更"""
        self._is_dirty = True

    def _has_unsaved_changes(self) -> bool:
        """检查是否有未保存的配置变更"""
        return self._is_dirty

    def _on_main_window_close(self):
        """
        主窗口关闭事件处理：
        - 若无未保存变更，直接关闭
        - 否则弹出三选一对话框（保存/不保存/取消）
        """
        from tkinter import messagebox, simpledialog

        if not self._has_unsaved_changes():
            self._do_close()
            return

        # 弹出三选一对话框
        result = messagebox.askyesnocancel(
            "保存解决方案",
            "当前有未保存的配置，是否保存为解决方案后再退出？\n\n"
            "是：保存后退出\n否：直接退出\n取消：返回程序"
        )

        if result is None:
            # 取消：不执行任何操作
            return
        elif result is False:
            # 不保存：直接关闭
            self._do_close()
        else:
            # 保存：弹出输入框，预填自动生成的名称
            from datetime import datetime
            default_name = datetime.now().strftime("解决方案_%Y%m%d_%H%M%S")
            name = simpledialog.askstring(
                "保存解决方案",
                "请输入解决方案名称：",
                initialvalue=default_name,
                parent=self.root
            )
            if name is None:
                # 用户取消了输入，不关闭
                return
            name = name.strip()
            if not name:
                messagebox.showwarning("警告", "解决方案名称不能为空")
                return

            # 执行保存
            try:
                solution_name = self.saved_ocr_state.get('solution_name')
                if not solution_name:
                    messagebox.showwarning("警告", "请先在工具界面选择一个字体库方案")
                    return

                font_solution_path = os.path.join("solutions", solution_name)
                sensor_settings = self._get_current_sensor_settings()
                script_settings = self._get_current_script_settings()
                tcp_settings = self._get_current_tcp_settings()

                overwrite = False
                if self.workspace_manager.workspace_exists(name):
                    overwrite = messagebox.askyesno("确认覆盖", f"解决方案 '{name}' 已存在，是否覆盖？")
                    if not overwrite:
                        return

                self.workspace_manager.save_workspace(
                    name=name,
                    font_solution_path=font_solution_path,
                    sensor_settings=sensor_settings,
                    script_settings=script_settings,
                    tcp_settings=tcp_settings,
                    overwrite=overwrite,
                    preview_image=self.saved_ocr_state.get('image'),
                )
                self._is_dirty = False
            except Exception as e:
                messagebox.showerror("保存失败", f"保存解决方案时出错：{e}")
                return

            self._do_close()

    def _do_close(self):
        """执行实际的关闭操作（停止服务并销毁窗口）"""
        try:
            self.video_loop_running = False
            if self.video_loop_id:
                self.root.after_cancel(self.video_loop_id)
            if hasattr(self, 'tcp_service') and self.tcp_service:
                self.tcp_service.stop()
            if hasattr(self, 'script_engine') and self.script_engine:
                self.script_engine.stop_periodic()
            if self.cam:
                self.cam.cleanup()
        except Exception:
            pass
        finally:
            self.root.destroy()

    def logout(self):
        """退出登录，销毁当前窗口并重新弹出登录界面"""
        try:
            # 记录退出日志
            self._audit("login", "logout")
            self.video_loop_running = False
            if self.video_loop_id:
                self.root.after_cancel(self.video_loop_id)
            if hasattr(self, 'tcp_service') and self.tcp_service:
                self.tcp_service.stop()
            if hasattr(self, 'script_engine') and self.script_engine:
                self.script_engine.stop_periodic()
            if self.cam:
                self.cam.cleanup()
        except Exception:
            pass
        finally:
            self.root.destroy()
            import tkinter as tk
            from ui.LoginWindow import LoginWindow

            def on_login_success(username, role):
                from InspectMainWindow import InspectMainWindow
                new_root = tk.Tk()
                app = InspectMainWindow(new_root, username, role)

                def on_closing():
                    try:
                        if hasattr(app, 'video_loop_running'):
                            app.video_loop_running = False
                        if hasattr(app, 'cam') and app.cam:
                            app.cam.cleanup()
                    except Exception:
                        pass
                    finally:
                        new_root.destroy()

                new_root.protocol("WM_DELETE_WINDOW", on_closing)
                new_root.mainloop()

            login_root = tk.Tk()
            LoginWindow(login_root, on_login_success)
            login_root.mainloop()

    def show_user_management(self):
        """显示用户管理窗口（仅管理员可访问）"""
        # 如果窗口已打开，直接置顶
        if hasattr(self, 'user_management_window') and self.user_management_window:
            try:
                self.user_management_window.window.lift()
                self.user_management_window.window.focus_force()
                return
            except Exception:
                self.user_management_window = None

        from ui.UserManagementWindow import UserManagementWindow

        def on_close():
            self.user_management_window = None

        self.user_management_window = UserManagementWindow(self.root, self.username, self.role, on_close)
        self._audit("user_management", "open_user_management", target_object="用户管理面板")

    @ErrorHandler.handle_ui_error
    def show_sensor_settings(self):
        """显示传感器设置面板（管理员和技术员可访问）"""
        if self.role == "操作员":
            from tkinter import messagebox
            messagebox.showinfo("提示", "操作员无权访问传感器设置")
            return

        self._audit(
            "camera_settings", "modify_trigger_source",
            target_object=self._camera_target_object("传感器设置面板"),
        )
        # 0. 先清除解决方案管理面板（如果存在）
        if self.solution_panel is not None:
            pass  # print removed
            self._hide_solution_panel()
        
        # 1. 清空 template_frame（显示白色背景）
        self.template_frame.config(bg="white")
        if hasattr(self, 'template_scroll_frame'):
            for widget in self.template_scroll_frame.winfo_children():
                widget.pack_forget()
        # 2. 清空侧边栏
        self.clear_sidebar()
        
        # 3. 在侧边栏容器中实例化 SensorSettingsFrame
        # 传入 self.cam (控制器) 和 self.show_main_menu (返回回调)
        settings_panel = SensorSettingsFrame(
            self.sidebar_frame, 
            self.cam, 
            on_back_callback=self.on_sensor_settings_back,
            camera_controller=self.cam,
            on_trigger_callback=self.on_software_trigger_executed,
            on_settings_changed=self._mark_dirty,
        )
        # 使用 pack 填满整个侧边栏，并增加一点内部 padding
        settings_panel.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def on_sensor_settings_back(self):
        """从传感器设置返回主菜单"""
        pass  # print removed
        # 1. 字符模板区域已经是白色背景，无需额外操作
        # （如果需要恢复字符模板内容，可以在这里添加代码）
        
        # 2. 恢复主菜单
        self.show_main_menu()
        
        # 3. 根据触发模式决定是否启动视频循环
        trigger_mode = self.cam.get_trigger_mode() if self.cam else "internal"
        if trigger_mode == "internal":
            # 内部时钟模式：启动视频循环
            if not self.video_loop_running:
                self._start_video_loop()
        else:
            # 硬件/软件触发模式：显示当前帧并停止循环
            if self.video_loop_running:
                self.video_loop_running = False
            # 获取并显示当前帧
            raw_img = self.cam.get_image()
            self._display_static_frame(raw_img)
        
        pass  # print removed
    
    @ErrorHandler.handle_ui_error
    def show_tcp_settings(self):
        """显示 TCP 通信设置面板（左侧）+ 脚本编辑面板（右侧下方）"""
        if not TcpSettingsFrame or not self.tcp_service:
            return
        if self.solution_panel is not None:
            self._hide_solution_panel()
        # clear_sidebar 内部会调用 _restore_template_canvas，
        # 但这里我们要显示脚本面板，所以 clear 之后再切换
        self.clear_sidebar()

        # 左侧：TCP 配置（端口/启停/客户端列表）每次重新创建，避免父窗口被销毁后路径失效
        self._tcp_settings_frame = TcpSettingsFrame(
            self.sidebar_frame, self.tcp_service, self.script_engine,
            save_callback=self._save_scripts_to_solution,
            back_callback=self._on_tcp_settings_back,
            main_window=self
        )
        self._tcp_settings_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        # 刷新 OCR 节点（可能已有识别结果）
        self._tcp_settings_frame._rebuild_ocr_nodes()

        # 右侧下方：脚本编辑面板（管理等式执行顺序）
        self._show_script_bottom_panel()

    def _on_tcp_settings_back(self):
        """从通信设置返回主界面：隐藏管理执行顺序面板，恢复主菜单。"""
        self._restore_template_canvas()
        self.show_main_menu()

    def _show_script_bottom_panel(self):
        """在相机画面下方显示脚本编辑面板，隐藏字符模板画布。"""
        if hasattr(self, '_template_scrollbar_ref'):
            self._template_scrollbar_ref.pack_forget()
        if hasattr(self, 'template_canvas'):
            self.template_canvas.pack_forget()

        if not hasattr(self, '_script_bottom_panel') or self._script_bottom_panel is None:
            self._build_script_bottom_panel()

        self.script_bottom_frame.pack(fill=tk.BOTH, expand=True)

    def _build_script_bottom_panel(self):
        """构建'管理等式执行顺序'脚本面板（参考图风格）。"""
        parent = self.script_bottom_frame

        lf = tk.LabelFrame(parent, text="管理等式执行顺序",
                            font=("Microsoft YaHei UI", 9, "bold"),
                            bg="white", padx=6, pady=4)
        lf.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        # 触发点选择行
        top_bar = tk.Frame(lf, bg="white")
        top_bar.pack(fill=tk.X, pady=(0, 4))
        tk.Label(top_bar, text="触发点：", bg="white",
                 font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT)
        self._script_trigger_var = tk.StringVar(value="post_image_process")
        combo = ttk.Combobox(top_bar, textvariable=self._script_trigger_var,
                             values=["solution_initialize", "pre_image_process",
                                     "post_image_process", "periodic"],
                             state="readonly", width=20,
                             font=("Microsoft YaHei UI", 9))
        combo.pack(side=tk.LEFT, padx=(0, 10))
        combo.bind("<<ComboboxSelected>>", self._on_script_trigger_change)

        # periodic 间隔输入框（仅选中 periodic 时启用）
        tk.Label(top_bar, text="间隔(ms)：", bg="white",
                 font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT)
        self._periodic_interval_var = tk.StringVar(value="100")
        self._periodic_interval_entry = tk.Entry(
            top_bar, textvariable=self._periodic_interval_var,
            width=6, font=("Microsoft YaHei UI", 9), state=tk.DISABLED)
        self._periodic_interval_entry.pack(side=tk.LEFT, padx=(0, 6))

        # 应用间隔按钮（仅 periodic 时有效）
        self._btn_apply_interval = tk.Button(
            top_bar, text="应用", font=("Microsoft YaHei UI", 8),
            bg="#F0F0F0", relief="raised", cursor="hand2",
            state=tk.DISABLED,
            command=self._on_apply_periodic_interval)
        self._btn_apply_interval.pack(side=tk.LEFT)

        # 主体：列表框 + 右侧按钮
        body = tk.Frame(lf, bg="white")
        body.pack(fill=tk.BOTH, expand=True)

        list_frame = tk.Frame(body, bg="white")
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_sb = tk.Scrollbar(list_frame)
        list_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._script_listbox = tk.Listbox(list_frame, yscrollcommand=list_sb.set,
                                          font=("Courier New", 9), bg="white",
                                          selectmode=tk.SINGLE, activestyle="dotbox")
        self._script_listbox.pack(fill=tk.BOTH, expand=True)
        list_sb.config(command=self._script_listbox.yview)
        self._script_listbox.bind("<Double-1>", self._on_script_line_edit)

        right_btns = tk.Frame(body, bg="white")
        right_btns.pack(side=tk.LEFT, fill=tk.Y, padx=(4, 0))
        btn_kw = dict(font=("Microsoft YaHei UI", 8), width=5,
                      relief="raised", cursor="hand2", bg="#F0F0F0")
        tk.Button(right_btns, text="编辑", command=self._on_script_line_edit, **btn_kw).pack(pady=(0, 2))
        tk.Button(right_btns, text="▲", command=self._on_script_line_up, **btn_kw).pack(pady=2)
        tk.Button(right_btns, text="▼", command=self._on_script_line_down, **btn_kw).pack(pady=2)
        tk.Button(right_btns, text="删除", command=self._on_script_line_delete, **btn_kw).pack(pady=2)

        # 底部按钮行
        bot_bar = tk.Frame(lf, bg="white")
        bot_bar.pack(fill=tk.X, pady=(4, 0))
        bot_kw = dict(font=("Microsoft YaHei UI", 9), relief="raised",
                      cursor="hand2", bg="#F0F0F0", padx=10, pady=3)
        tk.Button(bot_bar, text="导出", command=self._on_script_export, **bot_kw).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(bot_bar, text="导入", command=self._on_script_import, **bot_kw).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(bot_bar, text="插入等式",
                  bg="#5B9BD5", fg="white",
                  font=("Microsoft YaHei UI", 9), relief="raised",
                  cursor="hand2", padx=10, pady=3,
                  command=self._on_script_free_edit).pack(side=tk.LEFT)

        self._script_bottom_panel = lf
        self._reload_script_listbox()

    # ── 脚本底部面板回调 ──────────────────────────────────────────────

    def _reload_script_listbox(self):
        if not hasattr(self, '_script_listbox'):
            return
        self._script_listbox.delete(0, tk.END)
        if not self.script_engine:
            return
        trigger = self._script_trigger_var.get()
        code = self.script_engine.get_scripts().get(trigger, "")
        for line in code.splitlines():
            self._script_listbox.insert(tk.END, line)

    def _on_script_trigger_change(self, event=None):
        self._reload_script_listbox()
        # 仅 periodic 触发点时启用间隔输入框和应用按钮
        is_periodic = self._script_trigger_var.get() == "periodic"
        state = tk.NORMAL if is_periodic else tk.DISABLED
        if hasattr(self, '_periodic_interval_entry'):
            self._periodic_interval_entry.config(state=state)
        if hasattr(self, '_btn_apply_interval'):
            self._btn_apply_interval.config(state=state)

    def _on_script_line_edit(self, event=None):
        """弹出完整多行脚本编辑窗口（替代单行编辑）。"""
        trigger = self._script_trigger_var.get()
        # 取当前 Listbox 全部内容作为初始脚本
        current_code = "\n".join(self._script_listbox.get(0, tk.END))

        win = tk.Toplevel(self.root)
        win.title(f"脚本编辑 — {trigger}")
        win.geometry("700x600")
        win.minsize(700, 600)
        win.grab_set()
        win.configure(bg="white")

        # 顶部：内置函数快速参考
        ref_frame = tk.LabelFrame(win, text="内置函数参考", bg="white",
                                  font=("Microsoft YaHei UI", 8, "bold"))
        ref_frame.pack(fill=tk.X, padx=8, pady=(8, 0))
        ref_text = (
            "tcp_recv() → 从队列取一条命令(dict)，空时返回None  │  "
            "tcp_send(data) → 广播dict给所有客户端  │  "
            "trigger_capture() → 触发拍照  │  "
            "log(msg) → 写日志  │  "
            "reset_stats() → 重置统计"
        )
        tk.Label(ref_frame, text=ref_text, bg="white", fg="#555",
                 font=("Consolas", 8), wraplength=660, justify=tk.LEFT).pack(
            anchor="w", padx=4, pady=2)

        # 中间：脚本编辑区
        edit_frame = tk.Frame(win, bg="white")
        edit_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        vsb = tk.Scrollbar(edit_frame)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb = tk.Scrollbar(edit_frame, orient=tk.HORIZONTAL)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)

        txt = tk.Text(edit_frame, font=("Courier New", 11), undo=True,
                      wrap=tk.NONE, bg="#1e1e1e", fg="#d4d4d4",
                      insertbackground="white", selectbackground="#264f78",
                      yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.config(command=txt.yview)
        hsb.config(command=txt.xview)
        txt.insert("1.0", current_code)
        txt.focus_set()

        # 底部：语法检查结果 + 按钮
        bot = tk.Frame(win, bg="white")
        bot.pack(fill=tk.X, padx=8, pady=(0, 8))

        result_var = tk.StringVar(value="")
        result_label = tk.Label(bot, textvariable=result_var, bg="white",
                                fg="#4CAF50", font=("Microsoft YaHei UI", 9),
                                anchor="w")
        result_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        def _check():
            code = txt.get("1.0", tk.END).rstrip("\n")
            if self.script_engine:
                ok, msg = self.script_engine.check_syntax(code)
                if ok:
                    result_var.set("✓ 语法正确")
                    result_label.config(fg="#4CAF50")
                else:
                    result_var.set(f"✗ {msg}")
                    result_label.config(fg="#F44336")

        def _apply():
            new_code = txt.get("1.0", tk.END).rstrip("\n")
            self._script_listbox.delete(0, tk.END)
            for line in new_code.splitlines():
                self._script_listbox.insert(tk.END, line)
            self._sync_listbox_to_engine()
            win.destroy()

        tk.Button(bot, text="检查语法", font=("Microsoft YaHei UI", 9),
                  bg="#5B9BD5", fg="white", relief="raised", cursor="hand2",
                  command=_check).pack(side=tk.RIGHT, padx=(4, 0))
        tk.Button(bot, text="取消", font=("Microsoft YaHei UI", 9),
                  bg="#F0F0F0", relief="raised", cursor="hand2",
                  command=win.destroy).pack(side=tk.RIGHT, padx=(4, 0))
        tk.Button(bot, text="确定", font=("Microsoft YaHei UI", 9),
                  bg="#4CAF50", fg="white", relief="raised", cursor="hand2",
                  command=_apply).pack(side=tk.RIGHT)

    def _on_script_line_up(self):
        sel = self._script_listbox.curselection()
        if not sel or sel[0] == 0:
            return
        idx = sel[0]
        line = self._script_listbox.get(idx)
        self._script_listbox.delete(idx)
        self._script_listbox.insert(idx - 1, line)
        self._script_listbox.selection_set(idx - 1)
        self._sync_listbox_to_engine()

    def _on_script_line_down(self):
        sel = self._script_listbox.curselection()
        if not sel or sel[0] >= self._script_listbox.size() - 1:
            return
        idx = sel[0]
        line = self._script_listbox.get(idx)
        self._script_listbox.delete(idx)
        self._script_listbox.insert(idx + 1, line)
        self._script_listbox.selection_set(idx + 1)
        self._sync_listbox_to_engine()

    def _on_script_line_delete(self):
        sel = self._script_listbox.curselection()
        if not sel:
            return
        self._script_listbox.delete(sel[0])
        self._sync_listbox_to_engine()

    def _on_script_export(self):
        import tkinter.filedialog as fd
        trigger = self._script_trigger_var.get()
        path = fd.asksaveasfilename(title="导出脚本", defaultextension=".py",
                                    initialfile=f"{trigger}.py",
                                    filetypes=[("Python 脚本", "*.py"), ("所有文件", "*.*")])
        if not path:
            return
        code = "\n".join(self._script_listbox.get(0, tk.END))
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(code)
        except OSError as e:
            import tkinter.messagebox as mb
            mb.showerror("导出失败", str(e))

    def _on_script_import(self):
        import tkinter.filedialog as fd
        path = fd.askopenfilename(title="导入脚本",
                                  filetypes=[("Python 脚本", "*.py"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                code = f.read()
        except OSError as e:
            import tkinter.messagebox as mb
            mb.showerror("导入失败", str(e))
            return
        self._script_listbox.delete(0, tk.END)
        for line in code.splitlines():
            self._script_listbox.insert(tk.END, line)
        self._sync_listbox_to_engine()

    def _on_script_free_edit(self):
        """插入等式对话框：双击左侧 AppVar 大树插入变量名"""
        win = tk.Toplevel(self.root)
        win.title("插入等式")
        win.resizable(False, False)
        win.transient(self.root)
        win.configure(bg="white")

        x = self.root.winfo_x() + (self.root.winfo_width() - 420) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 220) // 2
        win.geometry(f"420x420+{x}+{y}")

        bg = "white"

        # 获取大树引用（稍后绑定/禁用）
        big_tree = None
        if hasattr(self, '_tcp_settings_frame') and self._tcp_settings_frame:
            big_tree = self._tcp_settings_frame._var_tree

        lf = tk.LabelFrame(win, text="等式赋值", font=("Microsoft YaHei UI", 9, "bold"),
                           bg=bg, padx=10, pady=8)
        lf.pack(fill=tk.X, padx=10, pady=(10, 6))

        # If 条件行
        cond_row = tk.Frame(lf, bg=bg)
        cond_row.pack(fill=tk.X, pady=(0, 6))
        tk.Label(cond_row, text="If (", bg=bg, font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT)
        var_cond = tk.StringVar()
        entry_cond = tk.Entry(cond_row, textvariable=var_cond, font=("Courier New", 9), width=28)
        entry_cond.pack(side=tk.LEFT, padx=4)
        tk.Label(cond_row, text=")", bg=bg, font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT)
        tk.Button(cond_row, text="清除", font=("Microsoft YaHei UI", 8), bg="#F0F0F0",
                  relief=tk.RAISED, cursor="hand2",
                  command=lambda: var_cond.set("")).pack(side=tk.LEFT, padx=(6, 0))

        # 变量名 = 值 行
        assign_row = tk.Frame(lf, bg=bg)
        assign_row.pack(fill=tk.X, pady=(0, 6))
        var_name = tk.StringVar()
        var_value = tk.StringVar()
        entry_name = tk.Entry(assign_row, textvariable=var_name, font=("Courier New", 9), width=16)
        entry_name.pack(side=tk.LEFT)
        tk.Label(assign_row, text=" = ", bg=bg, font=("Courier New", 9)).pack(side=tk.LEFT)
        entry_value = tk.Entry(assign_row, textvariable=var_value, font=("Courier New", 9), width=16)
        entry_value.pack(side=tk.LEFT)

        # 预览行
        preview_var = tk.StringVar(value="")
        tk.Label(lf, textvariable=preview_var, bg="#F8F8F8", fg="#333",
                 font=("Courier New", 9), anchor="w", relief=tk.SUNKEN, padx=4
                 ).pack(fill=tk.X)

        tk.Button(lf, text="添加到脚本", font=("Microsoft YaHei UI", 8, "bold"),
                  bg="#4CAF50", fg="white", relief=tk.RAISED, cursor="hand2",
                  command=lambda: _insert()
                  ).pack(anchor="e", pady=(4, 0))

        def _update_preview(*_):
            cond = var_cond.get().strip()
            name = var_name.get().strip()
            val = var_value.get().strip()
            if cond and name:
                preview_var.set(f"if ({cond}): {name} = {val}")
            elif name:
                preview_var.set(f"{name} = {val}")
            else:
                preview_var.set("")

        var_cond.trace_add("write", _update_preview)
        var_name.trace_add("write", _update_preview)
        var_value.trace_add("write", _update_preview)

        # 记录当前焦点输入框
        last_focused = [entry_name]
        entry_cond.bind("<FocusIn>", lambda e: last_focused.__setitem__(0, entry_cond))
        entry_name.bind("<FocusIn>", lambda e: last_focused.__setitem__(0, entry_name))
        entry_value.bind("<FocusIn>", lambda e: last_focused.__setitem__(0, entry_value))

        # 提示标签
        tk.Label(win, text="← 双击左侧 AppVar 树中的变量，插入到当前输入框",
                 bg=bg, fg="#888", font=("Microsoft YaHei UI", 8)
                 ).pack(anchor="w", padx=12, pady=(0, 6))

        # ── 字符串格式化 ──
        str_lf = tk.LabelFrame(win, text="字符串格式化", font=("Microsoft YaHei UI", 9),
                               bg=bg, padx=10, pady=6)
        str_lf.pack(fill=tk.X, padx=10, pady=(0, 6))

        # ── 字符串格式化 ──
        str_counter = [1]

        str_lf = tk.LabelFrame(win, text="字符串格式化", font=("Microsoft YaHei UI", 9),
                               bg=bg, padx=10, pady=6)
        str_lf.pack(fill=tk.X, padx=10, pady=(0, 6))

        str_top = tk.Frame(str_lf, bg=bg)
        str_top.pack(fill=tk.X, pady=(0, 4))
        tk.Button(str_top, text="清除", font=("Microsoft YaHei UI", 8), bg="#F0F0F0",
                  relief=tk.RAISED, cursor="hand2",
                  command=lambda: var_str_format.set("")
                  ).pack(side=tk.RIGHT)

        str_row = tk.Frame(str_lf, bg=bg)
        str_row.pack(fill=tk.X, pady=(0, 4))
        var_str_name = tk.StringVar(value="str1")
        tk.Entry(str_row, textvariable=var_str_name, font=("Courier New", 9), width=6,
                 state="readonly", readonlybackground="#F0F0F0"
                 ).pack(side=tk.LEFT)
        tk.Label(str_row, text=" = ", bg=bg, font=("Courier New", 9)).pack(side=tk.LEFT)
        var_str_format = tk.StringVar()
        entry_str_fmt = tk.Entry(str_row, textvariable=var_str_format,
                                 font=("Courier New", 9), width=34)
        entry_str_fmt.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entry_str_fmt.bind("<FocusIn>", lambda e: last_focused.__setitem__(0, entry_str_fmt))

        str_preview_var = tk.StringVar(value='str1 = ""')
        tk.Label(str_lf, textvariable=str_preview_var, bg="#F8F8F8", fg="#333",
                 font=("Courier New", 9), anchor="w", relief=tk.SUNKEN, padx=4
                 ).pack(fill=tk.X, pady=(0, 4))

        def _update_str_preview(*_):
            f = var_str_format.get()
            str_preview_var.set(f'{var_str_name.get()} = f"{f}"')
        var_str_format.trace_add("write", _update_str_preview)

        last_added_str = [None]  # 记录最后一次添加的字符串变量名

        def _add_str():
            n = var_str_name.get()
            f = entry_str_fmt.get()
            # 生成合法 f-string
            self._script_listbox.insert(tk.END, f'{n} = f"{f}"')
            self._sync_listbox_to_engine()
            last_added_str[0] = n  # 记录刚添加的变量名
            str_counter[0] += 1
            var_str_name.set(f"str{str_counter[0]}")
            entry_str_fmt.delete(0, tk.END)

        tk.Button(str_lf, text="添加到脚本", font=("Microsoft YaHei UI", 8, "bold"),
                  bg="#5B9BD5", fg="white", relief=tk.RAISED, cursor="hand2",
                  command=_add_str).pack(anchor="e")

        entry_str_fmt.bind("<FocusIn>", lambda e: last_focused.__setitem__(0, entry_str_fmt))

        # ── 发送到端口 ──
        send_lf = tk.LabelFrame(win, text="发送到端口", font=("Microsoft YaHei UI", 9),
                                bg=bg, padx=10, pady=6)
        send_lf.pack(fill=tk.X, padx=10, pady=(0, 6))

        send_row = tk.Frame(send_lf, bg=bg)
        send_row.pack(fill=tk.X)

        running_ports = []
        if self.tcp_service:
            try:
                running_ports = [str(p) for p in sorted(self.tcp_service._listeners.keys())
                                 if self.tcp_service.is_running(p)]
            except Exception:
                pass

        var_port = tk.StringVar()
        combo_port = ttk.Combobox(send_row, textvariable=var_port, values=running_ports,
                                  state="readonly", font=("Microsoft YaHei UI", 9), width=16)
        combo_port.pack(side=tk.LEFT, padx=(0, 6))
        if running_ports:
            combo_port.current(0)
        else:
            combo_port.set("（无运行中端口）")

        # 默认发送上面字符串变量
        tk.Button(send_row, text="添加", font=("Microsoft YaHei UI", 8, "bold"),
                  bg="#4CAF50", fg="white", relief=tk.RAISED, cursor="hand2",
                  command=lambda: (
                      self._script_listbox.insert(tk.END,
                          f"tcp_send({var_port.get()}, {last_added_str[0] or var_str_name.get()})"),
                      self._sync_listbox_to_engine()
                  )).pack(side=tk.LEFT)

        def _get_full_var_path(tree, item_id):
            """从叶节点往上遍历，拼出完整变量路径，如 OCR.CardNumber.Result"""
            skip_roots = {"AppVar", "Global", "TCP 端口", "用户变量", "OCR", "系统变量", ""}
            parts = []
            cur = item_id
            while cur:
                raw = tree.item(cur, "text").strip()
                # 去掉装饰符号，取等号左边部分
                clean = raw.lstrip("◆ 📁📡🟢⚫").split("(")[0].split("=")[0].strip()
                if clean and clean not in skip_roots:
                    parts.insert(0, clean)
                cur = tree.parent(cur)
            return ".".join(parts)

        def _on_tree_dbl(event):
            if not big_tree:
                return
            sel = big_tree.selection()
            if not sel:
                return
            var_text = _get_full_var_path(big_tree, sel[0])
            if not var_text:
                return
            entry = last_focused[0]
            # 如果焦点在格式输入框，插入 {变量名} f-string 格式；否则插入纯变量名
            if entry is entry_str_fmt:
                entry.insert(tk.INSERT, "{" + var_text + "}")
            else:
                entry.insert(tk.INSERT, var_text)
            win.lift()

        if big_tree:
            big_tree.bind("<Double-Button-1>", _on_tree_dbl)

        def _on_close():
            if big_tree:
                try:
                    big_tree.unbind("<Double-Button-1>")
                except Exception:
                    pass
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _on_close)

        # 底部按钮
        btn_row = tk.Frame(win, bg=bg)
        btn_row.pack(fill=tk.X, padx=10, pady=(4, 10))

        def _insert():
            line = preview_var.get().strip()
            if not line:
                return
            self._script_listbox.insert(tk.END, line)
            self._sync_listbox_to_engine()
            var_cond.set("")
            var_name.set("")
            var_value.set("")

        tk.Button(btn_row, text="关闭", font=("Microsoft YaHei UI", 9),
                  bg="#F0F0F0", relief=tk.RAISED, padx=16, pady=4,
                  cursor="hand2", command=_on_close).pack(side=tk.RIGHT)

    def _sync_listbox_to_engine(self):
        if not self.script_engine:
            return
        trigger = self._script_trigger_var.get()
        code = "\n".join(self._script_listbox.get(0, tk.END))
        current = self.script_engine.get_scripts()
        current[trigger] = code
        self.script_engine.set_scripts(current)

    def _on_apply_periodic_interval(self):
        """应用 periodic 间隔：重启定时器。"""
        if not self.script_engine:
            return
        try:
            interval = int(self._periodic_interval_var.get())
            if interval < 10:
                interval = 10
                self._periodic_interval_var.set("10")
        except ValueError:
            interval = 100
            self._periodic_interval_var.set("100")
        # 重启 periodic 定时器（仅在 TCP 服务运行时生效）
        if self.tcp_service and self.tcp_service.is_running:
            self.script_engine.stop_periodic()
            self.script_engine.start_periodic(interval)

    @ErrorHandler.handle_ui_error
    def show_script_editor(self):
        """显示脚本编辑面板"""
        if not ScriptEditorFrame or not self.script_engine:
            return
        # 清除解决方案管理面板（如果存在）
        if self.solution_panel is not None:
            self._hide_solution_panel()
        # 清空侧边栏
        self.clear_sidebar()
        # 懒加载 ScriptEditorFrame
        if self._script_editor_frame is None:
            self._script_editor_frame = ScriptEditorFrame(
                self.sidebar_frame, self.script_engine,
                save_callback=self._save_scripts_to_solution
            )
        self._script_editor_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _save_scripts_to_solution(self, scripts_dict):
        """将脚本字典写入当前 Solution 的 layout_config.json"""
        solution_name = self.saved_ocr_state.get('solution_name')
        if not solution_name:
            return
        config_file = os.path.join("solutions", solution_name, "layout_config.json")
        if not os.path.exists(config_file):
            return
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            config['scripts'] = scripts_dict
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def on_software_trigger_executed(self):
        """
        软件触发执行后的回调
        
        使用事件通知机制，实现最快速的帧刷新
        """
        # 清除之前的事件
        self.cam.frame_updated_event.clear()
        
        # 标记正在等待触发帧
        self.cam.waiting_for_trigger = True
        
        # 在后台线程中等待新帧
        def wait_and_refresh():
            # 等待新帧事件，最多等待200ms
            if self.cam.frame_updated_event.wait(timeout=0.2):
                # 收到新帧，立即刷新UI（在主线程中执行）
                self.root.after(0, self._refresh_triggered_frame)
            else:
                # 超时，仍然尝试刷新（可能相机回调有延迟）
                self.root.after(0, self._refresh_triggered_frame)
            
            # 重置等待标志
            self.cam.waiting_for_trigger = False
        
        # 启动后台线程
        threading.Thread(target=wait_and_refresh, daemon=True).start()
    
    def _refresh_triggered_frame_with_retry(self, max_retries=10, retry_interval=10, current_retry=0):
        """
        带重试机制的帧刷新（保留作为备用方案）
        
        参数:
            max_retries: 最大重试次数
            retry_interval: 重试间隔（毫秒）
            current_retry: 当前重试次数
        """
        if not self.cam:
            return
        
        # 获取当前帧
        raw_img = self.cam.get_image()
        if raw_img is None:
            return
        
        # 检查是否是新帧
        current_frame_id = id(self.cam.latest_frame) if hasattr(self.cam, 'latest_frame') else None
        is_new_frame = (current_frame_id != self._trigger_frame_id)
        
        # 刷新画布
        self._display_static_frame(raw_img)
        
        # 如果还不是新帧且还有重试次数，继续重试
        if not is_new_frame and current_retry < max_retries:
            self.root.after(
                retry_interval, 
                lambda: self._refresh_triggered_frame_with_retry(max_retries, retry_interval, current_retry + 1)
            )
    
    def _refresh_triggered_frame(self):
        """刷新触发后的帧到画布（简化版本，保留用于其他地方调用）"""
        if self.cam:
            raw_img = self.cam.get_image()
            if raw_img is not None:
                self._display_static_frame(raw_img)
    @ErrorHandler.handle_ui_error
    def show_tool_interface(self):
        """显示工具界面（管理员和技术员可访问）"""
        if self.role == "操作员":
            from tkinter import messagebox
            messagebox.showinfo("提示", "操作员无权访问工具配置")
            return

        self._audit(
            "tool_settings", "modify_ocr_region",
            target_object=self._camera_target_object("工具配置面板"),
        )
        # ★★★ 步骤1: 保存当前画布状态（拍快照）★★★
        # 获取当前画布上的图像（优先获取主界面的真实状态）
        current_image = None
        
        # 优先从视频流获取主界面的真实图像，而不是使用captured_image
        # 这样可以避免工具页面的拍照结果影响主界面状态
        try:
            current_image = self.cam.get_image()
        except:
            # 如果无法从相机获取，再考虑使用captured_image作为备用
            if hasattr(self, 'captured_image') and self.captured_image is not None:
                current_image = self.captured_image.copy()
        
        # 获取触发模式
        trigger_mode = self.cam.get_trigger_mode() if self.cam else 'internal'
        
        # 检查视频流是否在运行
        video_running = False
        if self.run_interface is not None and hasattr(self.run_interface, 'video_loop_running'):
            video_running = self.run_interface.video_loop_running
        elif self.video_loop_running:
            video_running = True
        
        # 保存状态
        self.before_tool_canvas_state = {
            'image': current_image,
            'trigger_mode': trigger_mode,
            'video_was_running': video_running,
            'has_state': True
        }
        
        # ★★★ 步骤2: 停止所有视频流 ★★★
        # 禁用 RunInterface 的全局视频标志
        from ui.RunInterface import RunInterface
        RunInterface._global_video_enabled = False
        
        # 停止主窗口视频循环
        self._stop_video_loop()
        
        # 停止运行界面视频循环
        if self.run_interface is not None and hasattr(self.run_interface, '_stop_video_loop'):
            self.run_interface._stop_video_loop()
        
        # ★★★ 步骤3: 清空画布 ★★★
        self.canvas.delete("all")
        self.preview_canvas.delete("all")
        
        # 清除解决方案管理面板（如果存在）
        if self.solution_panel is not None:
            self._hide_solution_panel()
        
        # 清空 template_frame（显示白色背景）
        if hasattr(self, 'template_scroll_frame'):
            for widget in self.template_scroll_frame.winfo_children():
                widget.pack_forget()

        # 隐藏日志面板，显示字符模板画布（工具界面需要使用）
        if self.audit_log_panel is not None:
            self.audit_log_panel.frame.pack_forget()
        self.template_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 清空侧边栏
        self.clear_sidebar()
        
        # 导入ToolSidebarFrame类
        try:
            from ui.ToolSidebarFrame import ToolSidebarFrame
        except ImportError:
            from ToolSidebarFrame import ToolSidebarFrame
        
        # 创建ToolSidebarFrame实例
        try:
            self.tool_interface = ToolSidebarFrame(
                parent=self.sidebar_frame,
                camera_controller=self.cam,
                on_back_callback=self.on_tool_interface_back,
                main_window=self
            )
        except Exception as e:
            pass
            self.show_main_menu()
            return
        
        # ★★★ 步骤4: 检查工具界面是否有保存的图片 ★★★
        if self.saved_ocr_state['has_state'] and self.saved_ocr_state['image'] is not None:
            self._restore_tool_canvas_state()

    
    def on_tool_interface_back(self):
        """从工具界面返回"""
        # 恢复 RunInterface 的全局视频标志
        from ui.RunInterface import RunInterface
        RunInterface._global_video_enabled = True
        
        # 清理工具界面
        if hasattr(self, 'tool_interface') and self.tool_interface:
            try:
                for widget in self.sidebar_frame.winfo_children():
                    widget.destroy()
            except:
                pass
            self.tool_interface = None
        
        # 清空 canvas
        self.canvas.delete("all")
        
        # ★★★ 关键修复：清除工具页面的独立图像缓存 ★★★
        if hasattr(self, 'tool_captured_image'):
            self.tool_captured_image = None
        
        # 不要清除主界面的captured_image，保持主界面状态独立
        # self.captured_image = None  # 注释掉这行
        
        # ★★★ 根据保存的画布状态恢复 ★★★
        if self.before_tool_canvas_state['has_state']:
            # 恢复画布上的图像（使用进入工具页面前保存的状态）
            if self.before_tool_canvas_state['image'] is not None:
                self._display_saved_canvas_image(self.before_tool_canvas_state['image'])
            
            # 根据触发模式决定是否恢复视频流
            if self.before_tool_canvas_state['trigger_mode'] == 'internal' and self.before_tool_canvas_state['video_was_running']:
                if not self.video_loop_running:
                    self._start_video_loop()
        else:
            if not self.video_loop_running:
                self._start_video_loop()
        
        # 恢复主菜单
        self.show_main_menu()

        # 退出工具界面后恢复日志面板，隐藏字符模板画布
        self.template_canvas.pack_forget()
        if self.audit_log_panel is not None:
            self.audit_log_panel.frame.pack(fill=tk.BOTH, expand=True)

        # 重置状态
        self.before_tool_canvas_state = {
            'image': None,
            'trigger_mode': None,
            'video_was_running': False,
            'has_state': False
        }
    
    def _display_saved_canvas_image(self, image):
        """在画布上显示保存的图像"""
        if image is None:
            return
        
        try:
            from PIL import Image, ImageTk
            import cv2
            
            # 获取Canvas尺寸
            cw = self.canvas.winfo_width()
            ch = self.canvas.winfo_height()
            
            if cw <= 1 or ch <= 1:
                cw = 800
                ch = 600
            
            h, w = image.shape[:2]
            
            # 计算缩放比例（高度90%）
            scale = (ch * 0.90) / h
            nw, nh = int(w*scale), int(h*scale)
            
            # 缩放图像
            resized = cv2.resize(image, (nw, nh))
            pil_img = Image.fromarray(resized)
            self.tk_img_ref = ImageTk.PhotoImage(pil_img)
            
            # 清空画布
            self.canvas.delete("all")
            
            # 居中显示
            cx, cy = cw//2, ch//2
            self.canvas.create_image(cx, cy, image=self.tk_img_ref)
        except Exception as e:
            pass
        
        pass  # print removed
    def _show_solution_disabled_message(self):
        """显示/隐藏解决方案管理面板（在 template_frame 位置，采用覆盖形式）"""
        # 切换面板显示状态
        if self.solution_panel is None:
            # 创建并显示面板
            self._show_solution_panel()
        else:
            # 隐藏面板，恢复字符模板区域
            self._hide_solution_panel()

    def _show_solution_panel(self):
        """显示解决方案管理面板（覆盖 template_frame 内容）"""
        if self.solution_panel is not None:
            return  # 已经显示
        
        pass  # print removed
        # 导入面板类
        try:
            from ui.SolutionManagementPanel import SolutionManagementPanel
        except ImportError:
            from SolutionManagementPanel import SolutionManagementPanel
        
        # 1. 隐藏日志面板和字符模板区域
        if self.audit_log_panel is not None:
            self.audit_log_panel.frame.pack_forget()
        self.template_canvas.pack_forget()

        # template_frame 背景改为白色
        self.template_frame.config(bg="white")

        # 2. 在 template_frame 中创建解决方案管理面板（覆盖显示）
        self.solution_panel = SolutionManagementPanel(
            parent=self.template_frame,
            workspace_manager_or_root=self.workspace_manager,
            main_window_or_callback=self
        )
        self.solution_panel.pack(fill=tk.BOTH, expand=True)
        self.template_frame.update_idletasks()
        
        pass  # print removed

    def _get_current_sensor_settings(self) -> dict:
        """从 config.USER_SENSOR_SETTINGS 读取当前传感器参数"""
        import config
        return config.get_user_sensor_settings()

    def _get_current_script_settings(self) -> dict:
        """优先从 ScriptEditorFrame.get_scripts() 读取，否则返回空脚本字典"""
        if self._script_editor_frame is not None:
            try:
                return self._script_editor_frame.get_scripts()
            except Exception:
                pass
        # 从 script_engine 读取
        if self.script_engine is not None:
            try:
                scripts = self.script_engine.get_scripts()
                return scripts
            except Exception:
                pass
        return {
            "solution_initialize": "",
            "pre_image_process": "",
            "post_image_process": "",
            "periodic": "",
            "periodic_interval_ms": 100,
        }

    def _get_current_tcp_settings(self) -> dict:
        """从 TcpSettingsFrame 和 TcpService 读取当前 TCP 设置"""
        ports = []
        auto_start_ports = []

        # 从 TcpSettingsFrame 读取端口列表
        if self._tcp_settings_frame is not None:
            try:
                ports = list(self._tcp_settings_frame._port_frames.keys())
            except Exception:
                pass

        # 从 TcpService 读取当前运行中的端口（作为 auto_start_ports）
        if self.tcp_service is not None:
            try:
                auto_start_ports = list(self.tcp_service.running_ports)
            except Exception:
                pass

        # 若 TcpSettingsFrame 不存在，从 tcp_config.json 读取
        if not ports:
            try:
                import json
                tcp_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tcp_config.json")
                if os.path.exists(tcp_config_path):
                    with open(tcp_config_path, "r", encoding="utf-8") as f:
                        tcp_data = json.load(f)
                    ports = tcp_data.get("ports", [])
            except Exception:
                pass

        return {
            "ports": ports,
            "auto_start_ports": auto_start_ports,
        }

    def _hide_solution_panel(self):
        """隐藏解决方案管理面板，恢复字符模板区域（覆盖模式）"""
        if self.solution_panel is None:
            return  # 已经隐藏
        
        pass  # print removed
        # 1. 销毁解决方案面板
        self.solution_panel.destroy()
        self.solution_panel = None
        
        # 2. 恢复日志面板（不恢复 template_canvas，日志面板占满此区域）
        if self.audit_log_panel is not None:
            self.template_frame.config(bg="#808080")
            self.audit_log_panel.frame.pack(fill=tk.BOTH, expand=True)
        
        pass  # print removed
    def _on_solution_panel_selected(self, solution_name):
        """解决方案面板选择回调"""
        print(f"🔄 [DEBUG] _on_solution_panel_selected 被调用: {solution_name}")
        self._audit("template_operation", "load_solution", target_object=solution_name)
        
        # 1. 加载方案的布局配置
        solution_path = os.path.join("solutions", solution_name)
        config_file = os.path.join(solution_path, "layout_config.json")
        
        print(f"   📂 方案路径: {solution_path}")
        print(f"   📄 配置文件: {config_file}")
        print(f"   📄 文件存在: {os.path.exists(config_file)}")
        
        if not os.path.exists(config_file):
            print(f"   ❌ 配置文件不存在，退出")
            return
        
        try:
            # 2. 读取布局配置
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            print(f"   ✅ 成功读取配置文件")
            print(f"   📊 配置数据: {config_data.keys()}")
            
            # 3. 转换为roi_layout格式
            new_roi_layout = {}
            
            # 加载锚点信息
            if config_data.get("strategy") == "anchor_based":
                new_roi_layout["FirstDigitAnchor"] = {
                    "roi": config_data["anchor_rect"],
                    "search_area": config_data.get("anchor_search_area", config_data["anchor_rect"]),
                    "is_anchor": True
                }
                print(f"   🎯 添加锚点: FirstDigitAnchor")
            
            # 加载其他字段
            if "fields" in config_data:
                for field_name, field_coords in config_data["fields"].items():
                    new_roi_layout[field_name] = {
                        "roi": field_coords,
                        "search_area": field_coords,
                        "is_anchor": False
                    }
                print(f"   📦 添加字段: {field_name} -> {field_coords}")
            
            print(f"   ✅ 总共加载了 {len(new_roi_layout)} 个字段")
            
            # 4. 更新saved_ocr_state中的roi_layout
            self.saved_ocr_state['roi_layout'] = new_roi_layout
            self.saved_ocr_state['has_state'] = True
            
            print(f"   ✅ 已更新 saved_ocr_state:")
            print(f"      - has_state: {self.saved_ocr_state['has_state']}")
            print(f"      - roi_layout 字段数: {len(self.saved_ocr_state['roi_layout'])}")
            
            # 5. 如果当前在OCR界面（solution_maker_frame存在），刷新显示
            if hasattr(self, 'solution_maker_frame') and self.solution_maker_frame:
                # 更新solution_maker_frame的roi_layout_config
                self.solution_maker_frame.roi_layout_config = new_roi_layout.copy()
                self.solution_maker_frame.current_solution_name = solution_name
                
                # 刷新画布显示（重新绘制ROI框）
                if hasattr(self.solution_maker_frame, '_refresh_canvas_image'):
                    self.solution_maker_frame._refresh_canvas_image()
            
            # 6. 如果当前在工具界面（tool_interface存在且有captured_image），刷新显示
            if hasattr(self, 'tool_interface') and self.tool_interface and hasattr(self, 'captured_image') and self.captured_image is not None:
                # 重新绘制工具界面的图像和ROI框
                self._redraw_tool_canvas_image()
            
        except Exception as e:
            pass
            import traceback
            traceback.print_exc()

    @ErrorHandler.handle_ui_error
    def show_solution_maker(self):
        """显示解决方案制作面板"""
        print("=" * 60)
        print("🔧 进入 show_solution_maker()")
        print("=" * 60)
        
        # ★★★ 关键修复：停止所有视频循环，不显示实时视频 ★★★
        print("🛑 步骤1: 停止主窗口视频循环")
        self._stop_video_loop()
        
        # 【新增】如果运行界面存在，也停止它的视频循环
        print(f"🔍 步骤2: 检查 run_interface 是否存在: {hasattr(self, 'run_interface')}")
        if hasattr(self, 'run_interface'):
            print(f"   run_interface 值: {self.run_interface}")
            if self.run_interface is not None:
                print(f"   run_interface 有 _stop_video_loop: {hasattr(self.run_interface, '_stop_video_loop')}")
                if hasattr(self.run_interface, '_stop_video_loop'):
                    print("🛑 停止运行界面的视频循环")
                    self.run_interface._stop_video_loop()
                    print(f"   运行界面 video_loop_running: {self.run_interface.video_loop_running}")
        
        # 清空画布（显示灰色背景）
        print("🧹 步骤3: 清空画布")
        self.canvas.delete("all")
        self.preview_canvas.delete("all")
        print("=" * 60)
        
        # 0. 先清除解决方案管理面板（如果存在）
        if self.solution_panel is not None:
            pass  # print removed
            self._hide_solution_panel()
        
        # 1. 检查是否有保存的 OCR 状态
        has_saved_state = self.saved_ocr_state['has_state'] and self.saved_ocr_state['image'] is not None
        
        # 2. 清空侧边栏
        self.clear_sidebar()

        # 确保字符模板画布可见（OCR界面需要使用）
        if hasattr(self, '_template_scrollbar_ref'):
            self._template_scrollbar_ref.pack(side=tk.RIGHT, fill=tk.Y)
        self.template_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 3. 决定传递的初始图像
        initial_image = None
        
        if has_saved_state:
            print("✅ OCR界面：有保存的图片，将恢复显示")
            # 如果有保存的状态，不传递initial_image，避免过早刷新画布
            initial_image = None
        else:
            print("ℹ️ OCR界面：没有保存的图片，显示灰色背景")
            initial_image = None
        
        # 4. 创建 SolutionMakerFrame 实例
        pass  # print removed
        self.solution_maker_frame = SolutionMakerFrame(
            parent=self.sidebar_frame,
            camera_controller=self.cam,
            canvas_widget=self.canvas,
            on_back_callback=self.on_solution_maker_back,
            preview_canvas=self.preview_canvas,
            template_canvas=self.template_scroll_frame,
            initial_image=initial_image,
            main_window=self  # 传递主窗口引用
        )
        
        # 5. 传递真正的Canvas引用（用于滚动控制）
        self.solution_maker_frame.template_canvas_widget = self.template_canvas
        
        # 6. 将面板添加到侧边栏（必须在恢复状态之前，确保UI已创建）
        self.solution_maker_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 7. 无论是否有图片，只要有方案名就恢复下拉框
        solution_name = self.saved_ocr_state.get('solution_name')
        if solution_name:
            if hasattr(self.solution_maker_frame, '_refresh_solution_list'):
                self.solution_maker_frame._refresh_solution_list()
            self.solution_maker_frame.current_solution_name = solution_name
            if hasattr(self.solution_maker_frame, 'var_solution_name'):
                self.solution_maker_frame.var_solution_name.set(solution_name)
            # 如果有图片，提前赋值，让 on_solution_selected 执行时已有图片
            if self.saved_ocr_state.get('image') is not None:
                self.solution_maker_frame.original_image = self.saved_ocr_state['image'].copy()
                # 重新按当前画布尺寸计算缩放比例，不使用保存的旧值
                if hasattr(self.solution_maker_frame, '_get_90_percent_scale'):
                    self.solution_maker_frame.zoom_scale = self.solution_maker_frame._get_90_percent_scale()
            # 延迟触发，确保 template_canvas_widget 已赋值且 __init__ 的延迟调用已完成
            self.root.after(100, self.solution_maker_frame.on_solution_selected)

        # 8. 如果有保存的图片状态，恢复完整显示（延迟到 on_solution_selected 之后）
        if has_saved_state:
            self.root.after(300, self._restore_ocr_state_immediate)
        
        # 9. 绑定Canvas大小改变事件,自动重新布局
        def on_canvas_resize(event):
            if self.solution_maker_frame and hasattr(self.solution_maker_frame, '_reflow_grid'):
                # 延迟调用,避免频繁重新布局
                self.root.after(100, self.solution_maker_frame._reflow_grid)
        
        self.template_canvas.bind("<Configure>", on_canvas_resize, add="+")
        
        # 10. 视频循环会自动检测 solution_maker_frame.original_image 并停止刷新
        pass  # print removed
        pass  # print removed
        pass  # print removed
    def on_solution_maker_back(self):
        """从解决方案制作返回"""
        # 返回前先保存当前状态（图片、布局等）
        if self.solution_maker_frame:
            try:
                self.save_ocr_state()
            except Exception:
                pass

        # 清理解决方案制作面板
        if self.solution_maker_frame:
            # 调用 cleanup 方法（如果存在）
            if hasattr(self.solution_maker_frame, 'cleanup'):
                self.solution_maker_frame.cleanup()
            self.solution_maker_frame.destroy()
            self.solution_maker_frame = None
        
        # 清空 canvas
        self.canvas.delete("all")
        
        # ★★★ 关键修复：检查是否应该返回工具页面 ★★★
        # 如果有工具页面的独立图像缓存，说明是从工具页面进入的OCR页面
        # 应该返回工具页面，而不是直接返回主界面
        if hasattr(self, 'tool_captured_image') and self.tool_captured_image is not None:
            print("🔄 从OCR页面返回工具页面")
            
            # 重新创建工具界面
            try:
                from ui.ToolSidebarFrame import ToolSidebarFrame
                self.tool_interface = ToolSidebarFrame(
                    parent=self.sidebar_frame,
                    camera_controller=self.cam,
                    on_back_callback=self.on_tool_interface_back,
                    main_window=self
                )
                
                # ★★★ 关键修复：使用工具页面的显示方法来显示图像和ROI框 ★★★
                # 这样可以确保字段框也会被显示
                self.tool_interface._display_image_on_canvas(self.tool_captured_image)
                
            except Exception as e:
                print(f"❌ 重新创建工具界面失败: {e}")
                # 如果创建失败，清除工具图像缓存并返回主界面
                self.tool_captured_image = None
                self._return_to_main_interface()
        else:
            print("🔄 从OCR页面返回主界面")
            self._return_to_main_interface()
    
    def _return_to_main_interface(self):
        """返回主界面的通用逻辑"""
        # 清除捕获的图像缓存（只在直接返回主界面时清除）
        self.captured_image = None
        pass  # print removed
        # 重新启动视频循环
        if not self.video_loop_running:
            self._start_video_loop()
        
        # 恢复主菜单
        self.show_main_menu()
        
        # 视频循环已经在运行，无需重启
    
    def save_ocr_state(self):
        """
        保存 OCR 工作状态到内存
        
        由 SolutionMakerFrame 的"保存全部"按钮调用
        
        ★★★ 只保存图片和字段布局，不保存字符模板 ★★★
        """
        pass  # print removed
        pass  # print removed
        pass  # print removed
        if not self.solution_maker_frame:
            print("⚠️ solution_maker_frame 不存在，无法保存状态")
            return
        
        try:
            # 1. 保存图片
            if self.solution_maker_frame.original_image is not None:
                self.saved_ocr_state['image'] = self.solution_maker_frame.original_image.copy()
                pass  # print removed
                pass
            else:
                self.saved_ocr_state['image'] = None
                print("⚠️ 没有图片可保存")
            
            self.saved_ocr_state['image_path'] = self.solution_maker_frame.image_path
            if self.saved_ocr_state['image_path']:
                pass  # print(f"✅ 保存图片路径: {self.saved_ocr_state['image_path']}")
            
            # 2. 保存布局配置
            self.saved_ocr_state['roi_layout'] = self.solution_maker_frame.roi_layout_config.copy()
            self.saved_ocr_state['temp_layout'] = self.solution_maker_frame.temp_layout_config.copy()
            pass  # print removed
            # print(f"   - 已保存字段: {len(self.saved_ocr_state['roi_layout'])}")
            # print(f"   - 临时字段: {len(self.saved_ocr_state['temp_layout'])}")
            
            # 3. 保存解决方案名称
            self.saved_ocr_state['solution_name'] = self.solution_maker_frame.current_solution_name
            if self.saved_ocr_state['solution_name']:
                pass  # print(f"✅ 保存解决方案名称: {self.saved_ocr_state['solution_name']}")
            else:
                print("⚠️ 没有选择解决方案")
            
            # 4. 保存缩放比例
            self.saved_ocr_state['zoom_scale'] = self.solution_maker_frame.zoom_scale
            pass  # print removed
            # 5. 标记为有状态
            self.saved_ocr_state['has_state'] = True
            
            pass  # print removed
            pass  # print removed
            pass  # print removed
        except Exception as e:
            print(f"❌ 保存 OCR 状态失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _restore_tool_canvas_state(self):
        """
        恢复工具界面的画布状态（图片+字段框）
        
        在 show_tool_interface 中调用
        """
        if not self.saved_ocr_state['has_state']:
            return
        
        try:
            # 1. 停止视频循环
            if self.video_loop_running:
                self.video_loop_running = False
            
            # 2. 清空画布上的视频帧
            self.canvas.delete("video_frame")
            self.preview_canvas.delete("video_frame")
            
            # 3. 获取保存的图片
            image = self.saved_ocr_state['image']
            if image is None:
                print("⚠️ 没有保存的图片")
                return
            
            # 设置captured_image，使缩放功能可用
            self.captured_image = image.copy()
            
            # 4. 计算缩放比例（默认90%高度）
            canvas_height = self.canvas.winfo_height()
            if canvas_height <= 1:
                self.canvas.update_idletasks()
                canvas_height = self.canvas.winfo_height()
            
            if canvas_height > 1:
                img_height = image.shape[0]
                zoom_scale = (canvas_height * 0.9) / img_height
            else:
                zoom_scale = 0.8
            
            # 设置tool_image_zoom_scale，使缩放功能可用
            self.tool_image_zoom_scale = zoom_scale
            
            # 5. 显示图片到画布（使用_redraw_tool_canvas_image方法）
            self._redraw_tool_canvas_image()
            
            # 6. 更新缩放比例显示
            if hasattr(self, 'zoom_label'):
                zoom_percent = int(zoom_scale * 100)
                self.zoom_label.config(text=f"{zoom_percent}%")
            
        except Exception as e:
            print(f"❌ 恢复画布状态失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _display_image_on_canvas(self, image, zoom_scale):
        """在画布上显示图片"""
        # 获取画布尺寸
        cw = self.preview_canvas.winfo_width()
        ch = self.preview_canvas.winfo_height()
        
        if cw <= 1 or ch <= 1:
            self.preview_canvas.update_idletasks()
            cw = self.preview_canvas.winfo_width()
            ch = self.preview_canvas.winfo_height()
        
        # 缩放图片
        h, w = image.shape[:2]
        new_w = int(w * zoom_scale)
        new_h = int(h * zoom_scale)
        
        img_resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        
        # 转换为RGB
        if len(img_resized.shape) == 2:
            img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_GRAY2RGB)
        else:
            img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        
        # 转换为PhotoImage
        pil_image = Image.fromarray(img_rgb)
        self.tk_img_ref = ImageTk.PhotoImage(pil_image)
        
        # 居中显示
        cx, cy = cw//2, ch//2
        
        # 添加白色边框
        self.preview_canvas.create_rectangle(
            cx-new_w//2-10, cy-new_h//2-10,
            cx+new_w//2+10, cy+new_h//2+10,
            fill="white", outline="",
            tags="tool_canvas_image"
        )
        
        # 绘制图像
        self.preview_canvas.create_image(
            cx, cy,
            image=self.tk_img_ref,
            tags="tool_canvas_image"
        )
        
        pass  # print removed
    def _draw_roi_boxes_on_canvas(self, roi_layout, temp_layout, zoom_scale):
        """在画布上绘制ROI框"""
        # 获取画布尺寸
        cw = self.preview_canvas.winfo_width()
        ch = self.preview_canvas.winfo_height()
        cx, cy = cw//2, ch//2
        
        # 获取图片尺寸
        if self.saved_ocr_state['image'] is None:
            return
        
        h, w = self.saved_ocr_state['image'].shape[:2]
        img_w = int(w * zoom_scale)
        img_h = int(h * zoom_scale)
        
        # 计算图片左上角
        img_left = cx - img_w // 2
        img_top = cy - img_h // 2
        
        # 颜色映射
        color_map = {
            "CardNumber": "#ff0000",
            "Name": "#0000ff",
            "Date": "#008000",
            "FirstDigitAnchor": "#ff00ff"
        }
        
        # 绘制已保存的ROI框
        for field, data in roi_layout.items():
            if isinstance(data, dict):
                coords = data.get("search_area", data.get("roi"))
            else:
                coords = data
            
            if not coords or len(coords) != 4:
                continue
            
            x, y, w_roi, h_roi = coords
            color = color_map.get(field, "#000000")
            
            # 转换为画布坐标
            sx = img_left + x * zoom_scale
            sy = img_top + y * zoom_scale
            sw = w_roi * zoom_scale
            sh = h_roi * zoom_scale
            
            # 绘制矩形框
            self.preview_canvas.create_rectangle(
                sx, sy, sx + sw, sy + sh,
                outline=color,
                width=2,
                tags="tool_canvas_roi"
            )
            
            # 绘制标签
            self.preview_canvas.create_text(
                sx, sy - 15,
                text=f"[已保存] {field}",
                fill=color,
                anchor="sw",
                font=("Arial", 9, "bold"),
                tags="tool_canvas_roi"
            )
        
        # 绘制临时ROI框
        for field, data in temp_layout.items():
            if isinstance(data, dict):
                coords = data.get("search_area", data.get("roi"))
            else:
                coords = data
            
            if not coords or len(coords) != 4:
                continue
            
            x, y, w_roi, h_roi = coords
            color = color_map.get(field, "#000000")
            
            # 转换为画布坐标
            sx = img_left + x * zoom_scale
            sy = img_top + y * zoom_scale
            sw = w_roi * zoom_scale
            sh = h_roi * zoom_scale
            
            # 绘制矩形框（虚线）
            self.preview_canvas.create_rectangle(
                sx, sy, sx + sw, sy + sh,
                outline=color,
                width=3,
                dash=(4, 4),
                tags="tool_canvas_roi"
            )
            
            # 绘制标签
            self.preview_canvas.create_text(
                sx, sy - 15,
                text=f"[临时] {field}",
                fill=color,
                anchor="sw",
                font=("Arial", 9, "bold"),
                tags="tool_canvas_roi"
            )
        
        # print(f"✅ 已绘制 {len(roi_layout)} 个已保存字段, {len(temp_layout)} 个临时字段")
    
    def _restore_ocr_state(self):
        """
        恢复 OCR 工作状态（静默恢复）- 延迟版本
        
        在 show_solution_maker 中调用（已废弃，使用_restore_ocr_state_immediate）
        """
        pass  # print removed
        pass  # print removed
        pass  # print removed
        if not self.saved_ocr_state['has_state']:
            pass  # print removed
            return
        
        if not self.solution_maker_frame:
            print("⚠️ solution_maker_frame 不存在，无法恢复状态")
            return
        
        try:
            # 1. 恢复图片路径
            if self.saved_ocr_state['image_path']:
                self.solution_maker_frame.image_path = self.saved_ocr_state['image_path']
                pass  # print removed
            # 2. 恢复布局配置
            self.solution_maker_frame.roi_layout_config = self.saved_ocr_state['roi_layout'].copy()
            self.solution_maker_frame.temp_layout_config = self.saved_ocr_state['temp_layout'].copy()
            pass  # print removed
            # print(f"   - 已保存字段: {len(self.saved_ocr_state['roi_layout'])}")
            # print(f"   - 临时字段: {len(self.saved_ocr_state['temp_layout'])}")
            
            # 3. 恢复字符模板数据
            import copy
            self.solution_maker_frame.char_widgets = copy.deepcopy(self.saved_ocr_state['char_widgets'])
            total_chars = sum(len(data.get('existing', [])) + len(data.get('new', [])) 
                            for data in self.solution_maker_frame.char_widgets.values())
            pass  # print removed
            # 4. 恢复方案名称
            if self.saved_ocr_state['solution_name']:
                self.solution_maker_frame.current_solution_name = self.saved_ocr_state['solution_name']
                if hasattr(self.solution_maker_frame, '_refresh_solution_list'):
                    self.solution_maker_frame._refresh_solution_list()
                if hasattr(self.solution_maker_frame, 'var_solution_name'):
                    self.solution_maker_frame.var_solution_name.set(self.saved_ocr_state['solution_name'])
                pass  # print removed
            # 5. 恢复缩放比例
            self.solution_maker_frame.zoom_scale = self.saved_ocr_state['zoom_scale']
            pass  # print removed
            # 6. 延迟刷新显示（等待界面完全加载）
            pass  # print removed
            self.root.after(300, self._delayed_restore_display)
            
            pass  # print removed
            pass  # print removed
            pass  # print removed
        except Exception as e:
            print(f"❌ 恢复 OCR 状态失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _restore_ocr_state_immediate(self):
        """
        立即恢复 OCR 工作状态（静默恢复）- 新版本
        
        在 show_solution_maker 中调用，先恢复数据再刷新显示
        """
        pass  # print removed
        pass  # print removed
        pass  # print removed
        if not self.saved_ocr_state['has_state']:
            pass  # print removed
            return
        
        if not self.solution_maker_frame:
            print("⚠️ solution_maker_frame 不存在，无法恢复状态")
            return
        
        try:
            # ★★★ 关键修复：先清空画布上的视频帧 ★★★
            pass  # print removed
            self.canvas.delete("video_frame")
            self.preview_canvas.delete("video_frame")
            pass  # print removed
            # 1. 恢复图片（必须先恢复，因为_refresh_canvas_image需要它）
            if self.saved_ocr_state['image'] is not None:
                self.solution_maker_frame.original_image = self.saved_ocr_state['image'].copy()
                pass  # print removed
            # 2. 恢复图片路径
            if self.saved_ocr_state['image_path']:
                self.solution_maker_frame.image_path = self.saved_ocr_state['image_path']
                pass  # print removed
            # 3. 恢复布局配置（必须在刷新画布之前恢复，这样才能绘制ROI框）
            self.solution_maker_frame.roi_layout_config = self.saved_ocr_state['roi_layout'].copy()
            self.solution_maker_frame.temp_layout_config = self.saved_ocr_state['temp_layout'].copy()
            pass  # print removed
            # print(f"   - 已保存字段: {len(self.saved_ocr_state['roi_layout'])}")
            # print(f"   - 临时字段: {len(self.saved_ocr_state['temp_layout'])}")
            
            # 4. 恢复字符模板数据（重新创建UI组件）
            # ★★★ 关键修复：从保存的数据重新创建UI组件 ★★★
            char_data = self.saved_ocr_state['char_widgets']
            total_chars = 0
            
            for field_type, widgets in char_data.items():
                # 确保字段类型已注册
                if field_type not in self.solution_maker_frame.char_widgets:
                    self.solution_maker_frame._register_field(field_type, create_ui=True)
                
                # 恢复existing字符
                for item_data in widgets.get('existing', []):
                    if item_data.get('image') is not None:
                        self.solution_maker_frame._add_char_grid_item(
                            cv2_img=item_data['image'],
                            section_type=field_type,
                            label_text=item_data.get('label', ''),
                            is_new=False
                        )
                        total_chars += 1
                
                # 恢复new字符
                for item_data in widgets.get('new', []):
                    if item_data.get('image') is not None:
                        self.solution_maker_frame._add_char_grid_item(
                            cv2_img=item_data['image'],
                            section_type=field_type,
                            label_text=item_data.get('label', ''),
                            is_new=True
                        )
                        total_chars += 1
            
            pass  # print removed
            # 5. 恢复方案名称
            if self.saved_ocr_state['solution_name']:
                self.solution_maker_frame.current_solution_name = self.saved_ocr_state['solution_name']
                # 先刷新下拉框列表，再设置选中值
                if hasattr(self.solution_maker_frame, '_refresh_solution_list'):
                    self.solution_maker_frame._refresh_solution_list()
                if hasattr(self.solution_maker_frame, 'var_solution_name'):
                    self.solution_maker_frame.var_solution_name.set(self.saved_ocr_state['solution_name'])
                pass  # print removed
            # 6. 重新按当前画布尺寸计算缩放比例（不使用保存的旧值，避免放大）
            if hasattr(self.solution_maker_frame, '_get_90_percent_scale'):
                self.solution_maker_frame.zoom_scale = self.solution_maker_frame._get_90_percent_scale()
            elif self.saved_ocr_state['zoom_scale']:
                self.solution_maker_frame.zoom_scale = self.saved_ocr_state['zoom_scale']
            pass  # print removed
            # 7. 延迟刷新显示（等待UI完全初始化，但时间更短）
            pass  # print removed
            self.root.after(150, self._delayed_restore_display)
            
            pass  # print removed
            pass  # print removed
            pass  # print removed
        except Exception as e:
            print(f"❌ 恢复 OCR 状态失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _delayed_restore_display(self):
        """延迟恢复显示（刷新画布和字符模板）"""
        pass  # print removed
        pass  # print removed
        pass  # print removed
        if not self.solution_maker_frame:
            print("⚠️ solution_maker_frame 不存在")
            return
        
        try:
            # 1. 刷新画布显示（重新绘制图片和ROI框）
            if hasattr(self.solution_maker_frame, '_refresh_canvas_image'):
                pass  # print removed
                self.solution_maker_frame._refresh_canvas_image()
                pass  # print removed
                pass
            else:
                print("⚠️ _refresh_canvas_image 方法不存在")
            
            # 2. 刷新字符模板网格
            if hasattr(self.solution_maker_frame, '_reflow_grid'):
                pass  # print removed
                self.solution_maker_frame._reflow_grid()
                pass  # print removed
                pass
            else:
                print("⚠️ _reflow_grid 方法不存在")
            
            pass  # print removed
            pass  # print removed
            pass  # print removed
        except Exception as e:
            print(f"⚠️ 刷新显示失败: {e}")
            import traceback
            traceback.print_exc()
    
    def update_ocr_state_image(self, new_image, image_path=None):
        """
        更新 OCR 状态中的图片（保留字段布局）
        
        由"拍照"和"加载图像"按钮调用
        
        参数:
            new_image: 新图片（numpy数组）
            image_path: 图片路径（可选）
        """
        if new_image is not None:
            self.saved_ocr_state['image'] = new_image.copy()
            self.saved_ocr_state['image_path'] = image_path
            
            # ★★★ 关键修复：重新计算缩放比例，不使用工具界面的缩放比例 ★★★
            # 计算适合OCR工具画布的缩放比例（90%填充）
            if hasattr(self, 'preview_canvas'):
                self.preview_canvas.update_idletasks()
                canvas_w = self.preview_canvas.winfo_width()
                canvas_h = self.preview_canvas.winfo_height()
                
                if canvas_w > 1 and canvas_h > 1:
                    h, w = new_image.shape[:2]
                    scale_w = (canvas_w * 0.9) / w
                    scale_h = (canvas_h * 0.9) / h
                    zoom_scale = min(scale_w, scale_h)
                    self.saved_ocr_state['zoom_scale'] = zoom_scale
                    pass  # print removed
                    pass
                else:
                    # 使用默认缩放比例
                    self.saved_ocr_state['zoom_scale'] = 0.5
                    pass  # print removed
                    pass
            else:
                # 使用默认缩放比例
                self.saved_ocr_state['zoom_scale'] = 0.5
                pass  # print removed
            # 如果之前没有状态，现在标记为有状态
            if not self.saved_ocr_state['has_state']:
                self.saved_ocr_state['has_state'] = True
            
            pass  # print removed
            if image_path:
                pass  # print removed
                pass
        else:
            print("⚠️ 新图片为None，无法更新")
    
    def clear_ocr_state_layout(self):
        """
        清空 OCR 状态中的字段布局
        
        由"新建解决方案"按钮调用
        """
        if self.saved_ocr_state['has_state']:
            self.saved_ocr_state['roi_layout'] = {}
            self.saved_ocr_state['temp_layout'] = {}
            self.saved_ocr_state['char_widgets'] = {}
            pass  # print removed
    @ErrorHandler.handle_ui_error
    def show_run_interface(self):
        """显示运行界面"""
        # 0. 先清除解决方案管理面板（如果存在）
        if self.solution_panel is not None:
            self._hide_solution_panel()
        
        # 停止主窗口视频循环（运行界面会自己管理画布）
        self._stop_video_loop()

        # 清空侧边栏
        self.clear_sidebar()
        self.template_frame.config(bg="white")

        # 导入RunInterface类
        try:
            from ui.RunInterface import RunInterface
        except ImportError:
            from RunInterface import RunInterface

        RunInterface._global_video_enabled = True

        # ★ 单例：只在第一次创建，之后复用
        if not hasattr(self, 'run_interface') or self.run_interface is None:
            try:
                self.run_interface = RunInterface(
                    parent=self.sidebar_frame,
                    camera_controller=self.cam,
                    on_back_callback=self.on_run_interface_back,
                    main_window=self,
                    script_engine=self.script_engine if hasattr(self, 'script_engine') else None
                )
                self._audit("inspection_control", "enter_run_interface")
            except Exception as e:
                print(f"RunInterface 创建失败: {e}")
                self._audit("inspection_control", "enter_run_interface", operation_result="失败")
                self.show_main_menu()
                return
        else:
            # 已有实例：重建侧边栏 UI（父容器已被 clear_sidebar 清空）
            self.run_interface.parent = self.sidebar_frame
            self.run_interface._create_sidebar_ui()
            # _create_sidebar_ui 末尾已调用 _init_display_on_enter，无需重复调用

            # ★ 关键：如果检测还在后台运行，立即恢复视频循环和数据刷新
            if self.run_interface.is_running:
                trigger_mode = self.cam.get_trigger_mode()
                if trigger_mode == "internal":
                    if not self.run_interface.video_loop_running:
                        self.run_interface._start_video_loop()
                print("✅ 重新进入运行界面，检测仍在运行，视频循环已恢复")

    def on_run_interface_back(self):
        """从运行界面返回主菜单（检测继续在后台运行）"""
        self._audit("inspection_control", "leave_run_interface")

        if hasattr(self, 'run_interface') and self.run_interface:
            # 只保存统计数据，不停止检测
            if hasattr(self.run_interface, '_save_stats'):
                self.run_interface._save_stats()
            # 停止视频循环（画布刷新），检测线程继续跑
            if hasattr(self.run_interface, '_stop_video_loop'):
                self.run_interface._stop_video_loop()
            from ui.RunInterface import RunInterface
            RunInterface._global_video_enabled = False

        # 清空侧边栏 UI（不销毁 run_interface 实例）
        try:
            for widget in self.sidebar_frame.winfo_children():
                widget.destroy()
        except Exception:
            pass

        # 恢复主窗口视频循环
        if not self.video_loop_running:
            self._start_video_loop()

        self.show_main_menu()

    def _stop_video_loop(self):
        """停止视频循环"""
        self.video_loop_running = False
        if self.video_loop_id:
            self.root.after_cancel(self.video_loop_id)
            self.video_loop_id = None
        pass  # print removed
    def _create_img_btn(self, parent, text, image, command=None, side=tk.TOP, return_btn=False):
        """创建带图标的按钮"""
        frame = tk.Frame(parent, bg="white", pady=5)
        btn = tk.Button(
            frame, text=text, image=image, compound=tk.LEFT,
            bg="white", relief="raised", anchor="w",
            padx=10, pady=8, font=("Microsoft YaHei UI", 10, "bold"),
            command=command
        )
        btn.pack(fill=tk.X)
        if return_btn:
            return frame
        frame.pack(side=side, fill=tk.X, padx=2)
        return btn

    def _start_video_loop(self):
        """视频刷新循环（参考C#的ImageBox显示逻辑）"""
        # 如果已经在运行，不重复启动
        if self.video_loop_running:
            return
        
        self.video_loop_running = True
        pass  # print removed
        self._video_loop_iteration()
    
    def _video_loop_iteration(self):
        """视频循环的单次迭代"""
        # 【关键修复1】如果在解决方案制作界面，不显示实时视频
        if self.solution_maker_frame is not None:
            # 在解决方案制作界面，停止视频刷新
            self.video_loop_running = False
            pass  # print removed
            return
        
        # 【关键修复2】检查是否有捕获的图像
        if hasattr(self, 'captured_image') and self.captured_image is not None:
            # 有捕获的图像，停止视频刷新
            self.video_loop_running = False
            pass  # print removed
            return
        
        # 【新增】检查触发模式，如果是硬件/软件触发，停止视频循环
        trigger_mode = self.cam.get_trigger_mode() if self.cam else "internal"
        if trigger_mode in ["hardware", "software"]:
            # 硬件/软件触发模式：获取当前帧并固定显示，然后停止循环
            self.video_loop_running = False
            # 获取并显示当前帧
            raw_img = self.cam.get_image()
            self._display_static_frame(raw_img)
            return
        
        # 检查是否应该继续循环
        if not self.video_loop_running:
            return
        
        # 获取最新帧
        raw_img = self.cam.get_image()
        
        # 获取Canvas尺寸
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        
        if cw > 1 and ch > 1:
            h, w = raw_img.shape[:2]
            
            # 计算缩放比例
            if self.video_zoom_scale is None:
                # None = 高度100%填充模式（填充窗口）
                scale = ch / h
                # 填充窗口模式显示为100%
                display_zoom_percent = 100
            elif self.video_zoom_scale == -1.0:
                # -1.0 = 高度90%模式（原始大小）
                scale = (ch * 0.90) / h
                # 原始大小模式显示为90%
                display_zoom_percent = 90
            else:
                # 使用用户设置的缩放比例
                scale = self.video_zoom_scale
                # 计算相对于Canvas高度的百分比
                # scale = 实际高度 / 原始高度
                # 相对于Canvas高度的百分比 = (实际高度 / Canvas高度) * 100
                display_zoom_percent = int((scale * h / ch) * 100)
            
            # 保存当前实际缩放比例
            self.current_zoom_scale = scale
            
            nw, nh = int(w*scale), int(h*scale)
            
            # 缩放图像
            resized = cv2.resize(raw_img, (nw, nh))
            pil_img = Image.fromarray(resized)
            self.tk_img_ref = ImageTk.PhotoImage(pil_img)
            
            # 清空画布
            self.canvas.delete("all")
            
            # ★★★ 确保清除运行界面的 ROI 框 ★★★
            self.canvas.delete("run_roi_box")
            self.canvas.delete("run_video_frame")
            
            # 始终居中显示（无论图像大小）
            cx, cy = cw//2, ch//2
            
            # 添加白色边框效果（使用标签，方便删除）
            self.canvas.create_rectangle(
                cx-nw//2-10, cy-nh//2-10, 
                cx+nw//2+10, cy+nh//2+10, 
                fill="white", outline="",
                tags="video_frame"
            )
            
            # 绘制图像（居中，使用标签）
            self.canvas.create_image(cx, cy, image=self.tk_img_ref, tags="video_frame")
            
            # 如果图像大于画布，设置滚动区域
            if nw > cw or nh > ch:
                # 重要：只在需要滚动的维度上设置滚动区域
                # 如果某个维度不需要滚动，使用Canvas的实际大小
                
                if nw > cw:
                    # 图像宽度大于Canvas，需要水平滚动
                    scroll_left = cx - nw//2
                    scroll_right = cx + nw//2
                else:
                    # 图像宽度小于等于Canvas，不需要水平滚动
                    # 使用Canvas的宽度作为滚动区域
                    scroll_left = 0
                    scroll_right = cw
                
                if nh > ch:
                    # 图像高度大于Canvas，需要垂直滚动
                    scroll_top = cy - nh//2
                    scroll_bottom = cy + nh//2
                else:
                    # 图像高度小于等于Canvas，不需要垂直滚动
                    # 使用Canvas的高度作为滚动区域
                    scroll_top = 0
                    scroll_bottom = ch
                
                self.canvas.config(scrollregion=(scroll_left, scroll_top, scroll_right, scroll_bottom))
                
                # 计算中心位置
                scroll_width = scroll_right - scroll_left
                scroll_height = scroll_bottom - scroll_top
                
                # 视口左上角在Canvas坐标系中的目标位置
                viewport_x = cx - cw//2
                viewport_y = cy - ch//2
                
                # 转换为滚动区域的比例（0-1）
                if nw > cw and scroll_width > 0:
                    # 图像宽度大于Canvas，需要水平滚动
                    center_x = (viewport_x - scroll_left) / scroll_width
                    center_x = max(0.0, min(1.0, center_x))
                else:
                    # 图像宽度小于等于Canvas，不需要水平滚动
                    center_x = 0.0
                
                if nh > ch and scroll_height > 0:
                    # 图像高度大于Canvas，需要垂直滚动
                    center_y = (viewport_y - scroll_top) / scroll_height
                    center_y = max(0.0, min(1.0, center_y))
                else:
                    # 图像高度小于等于Canvas，不需要垂直滚动
                    center_y = 0.0
                
                # 判断是否需要重新居中
                if not self.scroll_initialized:
                    # 首次初始化或缩放后，滚动到中心位置
                    self.canvas.xview_moveto(center_x)
                    self.canvas.yview_moveto(center_y)
                    self.scroll_initialized = True
                    # 记录初始居中位置
                    self.user_scroll_x = center_x
                    self.user_scroll_y = center_y
                elif self.is_user_scrolling:
                    # 用户已经主动滚动过，保持用户的滚动位置
                    if self.user_scroll_x is not None:
                        valid_x = max(0, min(1, self.user_scroll_x))
                        self.canvas.xview_moveto(valid_x)
                    if self.user_scroll_y is not None:
                        valid_y = max(0, min(1, self.user_scroll_y))
                        self.canvas.yview_moveto(valid_y)
                else:
                    # 既不是首次初始化，用户也没有滚动，保持居中
                    self.canvas.xview_moveto(center_x)
                    self.canvas.yview_moveto(center_y)
            else:
                # 图像较小，重置滚动区域和标记
                self.canvas.config(scrollregion=(0, 0, cw, ch))
                self.scroll_initialized = False
                self.is_user_scrolling = False
                self.user_scroll_x = None
                self.user_scroll_y = None
            
            # 更新缩放比例显示
            self.zoom_label.config(text=f"{display_zoom_percent}%")
        
        # 循环刷新（参考C#的实时显示）
        # 【关键修复3】只有在 video_loop_running 为 True 时才继续循环
        if self.video_loop_running:
            self.video_loop_id = self.root.after(50, self._video_loop_iteration)
    
    def _display_static_frame(self, raw_img):
        """
        显示静态帧（用于硬件/软件触发模式）
        
        参数:
            raw_img: 原始图像（numpy数组）
        """
        if raw_img is None:
            return
        
        # 获取Canvas尺寸
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        
        if cw > 1 and ch > 1:
            h, w = raw_img.shape[:2]
            
            # 计算缩放比例
            if self.video_zoom_scale is None:
                # None = 高度100%填充模式（填充窗口）
                scale = ch / h
                display_zoom_percent = 100
            elif self.video_zoom_scale == -1.0:
                # -1.0 = 高度90%模式（原始大小）
                scale = (ch * 0.90) / h
                display_zoom_percent = 90
            else:
                # 使用用户设置的缩放比例
                scale = self.video_zoom_scale
                display_zoom_percent = int((scale * h / ch) * 100)
            
            # 保存当前实际缩放比例
            self.current_zoom_scale = scale
            
            nw, nh = int(w*scale), int(h*scale)
            
            # 缩放图像
            resized = cv2.resize(raw_img, (nw, nh))
            pil_img = Image.fromarray(resized)
            self.tk_img_ref = ImageTk.PhotoImage(pil_img)
            
            # 清空画布
            self.canvas.delete("all")
            
            # 居中显示
            cx, cy = cw//2, ch//2
            
            # 添加白色边框
            self.canvas.create_rectangle(
                cx-nw//2-10, cy-nh//2-10, 
                cx+nw//2+10, cy+nh//2+10, 
                fill="white", outline="",
                tags="static_frame"
            )
            
            # 绘制图像
            self.canvas.create_image(cx, cy, image=self.tk_img_ref, tags="static_frame")
            
            # 设置滚动区域（如果需要）
            if nw > cw or nh > ch:
                if nw > cw:
                    scroll_left = cx - nw//2
                    scroll_right = cx + nw//2
                else:
                    scroll_left = 0
                    scroll_right = cw
                
                if nh > ch:
                    scroll_top = cy - nh//2
                    scroll_bottom = cy + nh//2
                else:
                    scroll_top = 0
                    scroll_bottom = ch
                
                self.canvas.config(scrollregion=(scroll_left, scroll_top, scroll_right, scroll_bottom))
                
                # 居中滚动
                scroll_width = scroll_right - scroll_left
                scroll_height = scroll_bottom - scroll_top
                
                viewport_x = cx - cw//2
                viewport_y = cy - ch//2
                
                if nw > cw and scroll_width > 0:
                    center_x = (viewport_x - scroll_left) / scroll_width
                    center_x = max(0.0, min(1.0, center_x))
                    self.canvas.xview_moveto(center_x)
                
                if nh > ch and scroll_height > 0:
                    center_y = (viewport_y - scroll_top) / scroll_height
                    center_y = max(0.0, min(1.0, center_y))
                    self.canvas.yview_moveto(center_y)
            else:
                self.canvas.config(scrollregion=(0, 0, cw, ch))
            
            # 更新缩放比例显示
            self.zoom_label.config(text=f"{display_zoom_percent}%")
    
    def _on_preview_canvas_resize(self, event):
        """
        画布大小改变事件处理
        
        当用户拖动分割线或窗口最大化时，自动重新绘制捕获的图像
        """
        pass  # print removed
        # 检查是否在SolutionMakerFrame中
        if hasattr(self, 'solution_maker_frame') and self.solution_maker_frame:
            pass  # print removed
            # 如果SolutionMakerFrame存在且有图像，调用它的resize处理
            if hasattr(self.solution_maker_frame, 'original_image') and self.solution_maker_frame.original_image is not None:
                pass  # print removed
                # 立即停止视频循环（防止视频循环清空画布）
                if self.video_loop_running:
                    self.video_loop_running = False
                    pass  # print removed
                # 取消所有待执行的视频循环回调（关键修复）
                if hasattr(self, 'video_loop_id') and self.video_loop_id:
                    try:
                        self.root.after_cancel(self.video_loop_id)
                        self.video_loop_id = None
                        pass  # print removed
                        pass
                    except:
                        pass
                
                # 立即删除视频帧，避免重影
                self.preview_canvas.delete("video_frame")
                
                # 取消之前的定时器（如果有）
                if hasattr(self, '_canvas_resize_timer'):
                    self.root.after_cancel(self._canvas_resize_timer)
                
                # 立即重绘（不延迟），确保图像不会被清空
                pass  # print removed
                self._do_solution_maker_canvas_resize()
                return
            else:
                pass  # print(f"   ⚠️ original_image不存在或为None")
        else:
            pass  # print(f"   ⚠️ solution_maker_frame不存在")
        
        # 否则，检查是否有捕获的图像（工具栏模式）
        if not hasattr(self, 'captured_image') or self.captured_image is None:
            pass  # print(f"   ⚠️ captured_image不存在或为None，跳过重绘")
            return
        
        pass  # print removed
        # 取消之前的定时器（如果有）
        if hasattr(self, '_canvas_resize_timer'):
            self.root.after_cancel(self._canvas_resize_timer)
        
        # 延迟100ms后再重绘（缩短延迟时间）
        self._canvas_resize_timer = self.root.after(100, self._do_preview_canvas_resize)
    
    def _do_solution_maker_canvas_resize(self):
        """
        SolutionMakerFrame中的画布大小改变处理
        """
        pass  # print removed
        # 确保视频循环已停止
        if self.video_loop_running:
            self.video_loop_running = False
            pass  # print removed
        # 清除视频帧
        self.preview_canvas.delete("video_frame")
        
        if hasattr(self, 'solution_maker_frame') and self.solution_maker_frame:
            # 验证图像是否存在
            if not hasattr(self.solution_maker_frame, 'original_image') or self.solution_maker_frame.original_image is None:
                print(f"   ❌ original_image不存在，无法重绘")
                return
            
            pass  # print removed
            # 重新计算缩放比例
            if hasattr(self.solution_maker_frame, '_get_90_percent_scale'):
                old_scale = self.solution_maker_frame.zoom_scale
                self.solution_maker_frame.zoom_scale = self.solution_maker_frame._get_90_percent_scale()
                pass  # print removed
            # 调用刷新方法
            if hasattr(self.solution_maker_frame, '_refresh_canvas_image'):
                pass  # print removed
                self.solution_maker_frame._refresh_canvas_image()
                pass  # print removed
                pass
            else:
                pass  # print(f"   ❌ 没有找到_refresh_canvas_image方法")
        else:
            pass  # print(f"   ❌ solution_maker_frame不存在")
    
    def _do_preview_canvas_resize(self):
        """
        实际执行画布大小改变后的重绘操作
        """
        if not hasattr(self, 'captured_image') or self.captured_image is None:
            return
        
        # 重新绘制捕获的图像
        self._redraw_captured_image()
    
    def _redraw_captured_image(self):
        """
        重新绘制捕获的图像（按新的画布大小缩放）
        """
        if not hasattr(self, 'captured_image') or self.captured_image is None:
            return
        
        try:
            from PIL import Image, ImageTk
            import cv2
            
            canvas = self.preview_canvas
            
            # 1. 清空画布（删除所有旧图像）
            canvas.delete("captured_image")
            canvas.delete("video_frame")
            
            # 2. 获取画布尺寸
            canvas_width = canvas.winfo_width()
            canvas_height = canvas.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:
                return
            
            # 3. 计算缩放比例（保持宽高比，适应画布）
            img_height, img_width = self.captured_image.shape[:2]
            scale_w = canvas_width / img_width
            scale_h = canvas_height / img_height
            scale = min(scale_w, scale_h) * 0.9  # 留10%边距
            
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            
            # 4. 调整图像大小
            resized_image = cv2.resize(self.captured_image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
            
            # 5. 转换为RGB格式（如果是灰度图）
            if len(resized_image.shape) == 2:
                resized_image = cv2.cvtColor(resized_image, cv2.COLOR_GRAY2RGB)
            else:
                resized_image = cv2.cvtColor(resized_image, cv2.COLOR_BGR2RGB)
            
            # 6. 转换为PIL Image
            pil_image = Image.fromarray(resized_image)
            
            # 7. 转换为Tkinter PhotoImage
            tk_image = ImageTk.PhotoImage(pil_image)
            
            # 8. 保存引用（防止被垃圾回收）
            self._captured_tk_image = tk_image
            
            # 9. 在画布上居中显示图像
            cx = canvas_width // 2
            cy = canvas_height // 2
            
            canvas.create_image(cx, cy, image=tk_image, tags="captured_image")
            
            # print(f"🔄 画布大小改变，重新绘制图像: 原始尺寸={self.captured_image.shape}, 显示尺寸=({new_width}, {new_height})")
            
        except Exception as e:
            print(f"❌ 重新绘制图像异常: {e}")
            import traceback
            traceback.print_exc()
    
    def _redraw_tool_canvas_image(self):
        """
        重新绘制工具界面的图像（使用保存的缩放比例）
        """
        if not hasattr(self, 'captured_image') or self.captured_image is None:
            return
        
        try:
            from PIL import Image, ImageTk
            import cv2
            
            canvas = self.canvas
            
            # 1. 清空画布
            canvas.delete("all")
            
            # 2. 获取画布尺寸
            canvas_width = canvas.winfo_width()
            canvas_height = canvas.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width = 800
                canvas_height = 600
            
            # 3. 获取原始图像尺寸
            img_height, img_width = self.captured_image.shape[:2]
            
            # 4. 使用保存的缩放比例
            if not hasattr(self, 'tool_image_zoom_scale') or self.tool_image_zoom_scale is None:
                # 如果没有缩放比例，使用默认的90%高度
                self.tool_image_zoom_scale = (canvas_height * 0.9) / img_height
            
            scale = self.tool_image_zoom_scale
            
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            
            # 5. 调整图像大小
            resized_image = cv2.resize(self.captured_image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
            
            # 6. 转换为RGB格式（如果是灰度图）
            if len(resized_image.shape) == 2:
                resized_image = cv2.cvtColor(resized_image, cv2.COLOR_GRAY2RGB)
            else:
                resized_image = cv2.cvtColor(resized_image, cv2.COLOR_BGR2RGB)
            
            # 7. 转换为PIL Image
            pil_image = Image.fromarray(resized_image)
            
            # 8. 转换为Tkinter PhotoImage
            tk_image = ImageTk.PhotoImage(pil_image)
            
            # 9. 保存引用（防止被垃圾回收）
            self._captured_tk_image = tk_image
            
            # 10. 在画布上居中显示图像
            cx = canvas_width // 2
            cy = canvas_height // 2
            
            canvas.create_image(cx, cy, image=tk_image, tags="captured_image")
            
            # 11. 如果有保存的ROI框，重新绘制
            if hasattr(self, 'saved_ocr_state') and self.saved_ocr_state['has_state']:
                roi_layout = self.saved_ocr_state.get('roi_layout', {})
                temp_layout = self.saved_ocr_state.get('temp_layout', {})
                
                if roi_layout or temp_layout:
                    # 调用ToolSidebarFrame的_draw_roi_boxes方法（如果存在）
                    if hasattr(self, 'tool_interface') and self.tool_interface:
                        self.tool_interface._draw_roi_boxes(canvas, roi_layout, temp_layout, scale, cx, cy, img_width, img_height)
                    else:
                        # 否则调用本地的_draw_tool_roi_boxes方法
                        self._draw_tool_roi_boxes(canvas, roi_layout, temp_layout, scale, cx, cy, img_width, img_height)
            
        except Exception as e:
            print(f"❌ 重新绘制工具图像异常: {e}")
            import traceback
            traceback.print_exc()
    
    def _draw_tool_roi_boxes(self, canvas, roi_layout, temp_layout, zoom_scale, cx, cy, img_width, img_height):
        """在工具界面画布上绘制ROI框"""
        # 计算图片左上角
        img_w = int(img_width * zoom_scale)
        img_h = int(img_height * zoom_scale)
        img_left = cx - img_w // 2
        img_top = cy - img_h // 2
        
        # 颜色映射
        color_map = {
            "CardNumber": "#ff0000",
            "Name": "#0000ff",
            "Date": "#008000",
            "FirstDigitAnchor": "#ff00ff"
        }
        
        # 绘制已保存的ROI框
        for field, data in roi_layout.items():
            if isinstance(data, dict):
                coords = data.get("search_area", data.get("roi"))
            else:
                coords = data
            
            if not coords or len(coords) != 4:
                continue
            
            x, y, w_roi, h_roi = coords
            color = color_map.get(field, "#000000")
            
            # 转换为画布坐标
            sx = img_left + x * zoom_scale
            sy = img_top + y * zoom_scale
            sw = w_roi * zoom_scale
            sh = h_roi * zoom_scale
            
            # 绘制矩形框
            canvas.create_rectangle(
                sx, sy, sx + sw, sy + sh,
                outline=color,
                width=2,
                tags="tool_canvas_roi"
            )
            
            # 绘制标签
            canvas.create_text(
                sx, sy - 15,
                text=f"[已保存] {field}",
                fill=color,
                anchor="sw",
                font=("Arial", 9, "bold"),
                tags="tool_canvas_roi"
            )
        
        # 绘制临时ROI框
        for field, data in temp_layout.items():
            if isinstance(data, dict):
                coords = data.get("search_area", data.get("roi"))
            else:
                coords = data
            
            if not coords or len(coords) != 4:
                continue
            
            x, y, w_roi, h_roi = coords
            color = color_map.get(field, "#000000")
            
            # 转换为画布坐标
            sx = img_left + x * zoom_scale
            sy = img_top + y * zoom_scale
            sw = w_roi * zoom_scale
            sh = h_roi * zoom_scale
            
            # 绘制矩形框（虚线）
            canvas.create_rectangle(
                sx, sy, sx + sw, sy + sh,
                outline=color,
                width=3,
                dash=(4, 4),
                tags="tool_canvas_roi"
            )
            
            # 绘制标签
            canvas.create_text(
                sx, sy - 15,
                text=f"[临时] {field}",
                fill=color,
                anchor="sw",
                font=("Arial", 9, "bold"),
                tags="tool_canvas_roi"
            )


# ==============================================================================
# 4. 主程序入口
# ==============================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = InspectMainWindow(root)
    root.mainloop()