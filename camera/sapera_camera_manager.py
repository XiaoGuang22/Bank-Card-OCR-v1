"""
Sapera 相机切换管理器

负责：
- 管理 Sapera 相机的连接和切换
- 处理 SapAcqDevice 和 SapTransfer 对象的生命周期
- 实现安全的相机切换流程
- 提供状态回调和错误处理
"""

import clr
import threading
import time
from typing import Optional, Callable, TYPE_CHECKING
from enum import Enum

# 导入配置
from config import SAPERA_DLL_PATH

# 加载Sapera SDK
try:
    clr.AddReference(SAPERA_DLL_PATH)
    from DALSA.SaperaLT.SapClassBasic import (
        SapManager,
        SapLocation,
        SapAcqDevice,
        SapBuffer,
        SapTransfer,
        SapAcqDeviceToBuf
    )
    SAPERA_AVAILABLE = True
except Exception as e:
    print(f"Sapera SDK加载失败: {e}")
    SAPERA_AVAILABLE = False

if TYPE_CHECKING:
    from camera.sapera_camera_discovery import SaperaCameraInfo
    from camera.camera_info_model import CameraConnectionStatus


class SaperaCameraManager:
    """
    Sapera 相机切换管理器
    
    实现需求文档 FC-10 中的切换流程：
    1. 停止图像采集（SapTransfer.Freeze + Wait）
    2. 销毁当前 SapTransfer 和 SapAcqDevice 对象
    3. 为目标相机新建 SapAcqDevice，调用 Create() 建立控制通道
    4. 重新创建 SapTransfer 对象并连接
    5. 开始采集（Grab）
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        
        # 当前连接的相机信息
        self._current_camera: Optional['SaperaCameraInfo'] = None
        self._last_successful_camera: Optional['SaperaCameraInfo'] = None
        
        # Sapera 对象
        self._acq_device: Optional = None
        self._buffers: Optional = None
        self._transfer: Optional = None
        
        # 连接状态
        self._connected = False
        self._connecting = False
        
        # 状态回调列表
        self._state_callbacks = []
        
        # 错误处理
        self._register_error_handler()
    
    @property
    def is_available(self) -> bool:
        """检查 Sapera SDK 是否可用"""
        return SAPERA_AVAILABLE
    
    @property
    def current_camera(self) -> Optional['SaperaCameraInfo']:
        """当前连接的相机"""
        return self._current_camera
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected
    
    @property
    def is_connecting(self) -> bool:
        """是否正在连接"""
        return self._connecting
    
    def add_state_callback(self, callback: Callable[['CameraConnectionStatus', Optional['SaperaCameraInfo']], None]):
        """添加状态变化回调"""
        self._state_callbacks.append(callback)
    
    def remove_state_callback(self, callback):
        """移除状态变化回调"""
        if callback in self._state_callbacks:
            self._state_callbacks.remove(callback)
    
    def _notify_state_change(self, status: 'CameraConnectionStatus', camera: Optional['SaperaCameraInfo'] = None):
        """通知状态变化"""
        for callback in self._state_callbacks:
            try:
                callback(status, camera or self._current_camera)
            except Exception as e:
                print(f"[SaperaCameraManager] 状态回调异常: {e}")
    
    def _register_error_handler(self):
        """注册 Sapera SDK 错误处理"""
        if not SAPERA_AVAILABLE:
            return
        
        try:
            # 设置错误事件处理 - 修复枚举转换问题
            from System import Enum
            # 使用正确的枚举值转换
            try:
                SapManager.DisplayStatusMode = Enum.ToObject(type(SapManager.DisplayStatusMode), 1)  # StatusMode.Event
            except:
                # 如果枚举转换失败，尝试直接设置为 Log 模式（不显示对话框）
                try:
                    SapManager.DisplayStatusMode = Enum.ToObject(type(SapManager.DisplayStatusMode), 2)  # StatusMode.Log
                except:
                    pass
            
            # 注意：Python 绑定可能不支持事件注册，这里仅设置模式
        except Exception as e:
            print(f"[SaperaCameraManager] 注册错误处理失败: {e}")
            # 如果枚举转换失败，尝试直接设置
            try:
                SapManager.DisplayStatusMode = 2  # Log模式，不显示对话框
            except:
                pass
    
    def connect(self, camera_info: 'SaperaCameraInfo') -> tuple[bool, str]:
        """
        连接到指定相机
        
        Args:
            camera_info: 目标相机信息
            
        Returns:
            (success, message)
        """
        if not SAPERA_AVAILABLE:
            return False, "Sapera SDK 不可用"
        
        with self._lock:
            # 如果已连接到同一相机，直接返回成功
            if (self._connected and self._current_camera and 
                self._current_camera == camera_info):
                return True, f"已连接到 {camera_info.formatted_display_name}"
            
            # 设置连接状态
            self._connecting = True
            from camera.camera_info_model import CameraConnectionStatus
            self._notify_state_change(CameraConnectionStatus.CONNECTING)
            
            try:
                # 断开当前连接
                if self._connected:
                    self._disconnect_internal()
                
                # 执行连接
                success, message = self._execute_connection(camera_info)
                
                if success:
                    self._current_camera = camera_info
                    self._last_successful_camera = camera_info
                    self._connected = True
                    self._notify_state_change(CameraConnectionStatus.CONNECTED, camera_info)
                else:
                    self._notify_state_change(CameraConnectionStatus.ERROR)
                
                return success, message
                
            except Exception as e:
                self._notify_state_change(CameraConnectionStatus.ERROR)
                return False, f"连接异常: {e}"
            finally:
                self._connecting = False
    
    def _execute_connection(self, camera_info: 'SaperaCameraInfo') -> tuple[bool, str]:
        """
        执行实际的连接操作
        
        按需求文档 FC-10 的步骤执行
        """
        try:
            # 步骤 3: 为目标相机新建 SapAcqDevice
            location = SapLocation(camera_info.server_name, 0)
            self._acq_device = SapAcqDevice(location, False)
            
            if not self._acq_device.Create():
                return False, f"无法创建设备: {camera_info.server_name}"
            
            print(f"[SaperaCameraManager] 成功创建设备: {camera_info.server_name}")
            
            # 步骤 4: 重新创建 SapTransfer 对象并连接
            success, message = self._create_buffers_and_transfer()
            if not success:
                self._cleanup_objects()
                return False, message
            
            # 步骤 5: 开始采集
            success, message = self._start_acquisition()
            if not success:
                self._cleanup_objects()
                return False, message
            
            return True, f"成功连接到 {camera_info.formatted_display_name}"
            
        except Exception as e:
            self._cleanup_objects()
            return False, f"连接失败: {e}"
    
    def _create_buffers_and_transfer(self) -> tuple[bool, str]:
        """创建缓冲区和传输对象"""
        try:
            # 创建缓冲区
            self._buffers = SapBuffer(2, self._acq_device)  # 双缓冲
            if not self._buffers.Create():
                return False, "无法创建缓冲区"
            
            print(f"[SaperaCameraManager] 成功创建缓冲区")
            
            # 创建传输对象
            self._transfer = SapAcqDeviceToBuf(self._acq_device, self._buffers)
            if not self._transfer.Create():
                return False, "无法创建传输对象"
            
            print(f"[SaperaCameraManager] 成功创建传输对象")
            
            return True, "缓冲区和传输对象创建成功"
            
        except Exception as e:
            return False, f"创建缓冲区和传输对象失败: {e}"
    
    def _start_acquisition(self) -> tuple[bool, str]:
        """开始图像采集"""
        try:
            if not self._transfer:
                return False, "传输对象未创建"
            
            # 开始采集
            if not self._transfer.Grab():
                return False, "无法开始采集"
            
            print(f"[SaperaCameraManager] 成功开始采集")
            
            return True, "图像采集已开始"
            
        except Exception as e:
            return False, f"开始采集失败: {e}"
    
    def disconnect(self):
        """断开当前连接"""
        with self._lock:
            self._disconnect_internal()
    
    def _disconnect_internal(self):
        """内部断开连接方法（不加锁）"""
        try:
            # 步骤 1: 停止图像采集
            if self._transfer:
                try:
                    self._transfer.Freeze()
                    self._transfer.Wait(5000)  # 等待5秒
                    print(f"[SaperaCameraManager] 成功停止采集")
                except Exception as e:
                    print(f"[SaperaCameraManager] 停止采集失败: {e}")
            
            # 步骤 2: 销毁对象
            self._cleanup_objects()
            
            # 更新状态
            self._current_camera = None
            self._connected = False
            
            from camera.camera_info_model import CameraConnectionStatus
            self._notify_state_change(CameraConnectionStatus.DISCONNECTED)
            
        except Exception as e:
            print(f"[SaperaCameraManager] 断开连接异常: {e}")
    
    def _cleanup_objects(self):
        """清理 Sapera 对象"""
        # 销毁传输对象
        if self._transfer:
            try:
                self._transfer.Destroy()
                self._transfer.Dispose()
            except Exception as e:
                print(f"[SaperaCameraManager] 销毁传输对象失败: {e}")
            self._transfer = None
        
        # 销毁缓冲区
        if self._buffers:
            try:
                self._buffers.Destroy()
                self._buffers.Dispose()
            except Exception as e:
                print(f"[SaperaCameraManager] 销毁缓冲区失败: {e}")
            self._buffers = None
        
        # 销毁设备对象
        if self._acq_device:
            try:
                self._acq_device.Destroy()
                self._acq_device.Dispose()
            except Exception as e:
                print(f"[SaperaCameraManager] 销毁设备对象失败: {e}")
            self._acq_device = None
    
    def switch_camera(self, target_camera: 'SaperaCameraInfo') -> tuple[bool, str]:
        """
        切换到目标相机
        
        实现需求文档 FC-09/FC-10 的完整切换流程
        """
        if not SAPERA_AVAILABLE:
            return False, "Sapera SDK 不可用"
        
        # 检查是否为同一相机
        if self._current_camera and self._current_camera == target_camera:
            return True, "已是当前相机，无需切换"
        
        print(f"[SaperaCameraManager] 开始切换相机: {self._current_camera} -> {target_camera.formatted_display_name}")
        
        # 执行切换
        success, message = self.connect(target_camera)
        
        if not success:
            # 切换失败，尝试回退到上一次成功的连接
            if self._last_successful_camera and self._last_successful_camera != target_camera:
                print(f"[SaperaCameraManager] 切换失败，尝试回退到: {self._last_successful_camera.formatted_display_name}")
                fallback_success, fallback_message = self.connect(self._last_successful_camera)
                if fallback_success:
                    message += f"\n已自动回退到上一次成功的连接: {self._last_successful_camera.formatted_display_name}"
                else:
                    message += f"\n回退也失败: {fallback_message}"
        
        return success, message
    
    def get_current_frame(self):
        """获取当前帧（如果有的话）"""
        if not self._connected or not self._buffers:
            return None
        
        try:
            # 这里可以实现帧获取逻辑
            # 具体实现取决于如何与现有的 CameraController 集成
            pass
        except Exception as e:
            print(f"[SaperaCameraManager] 获取当前帧失败: {e}")
            return None
    
    def set_parameter(self, param_name: str, value) -> tuple[bool, str]:
        """
        设置相机参数
        
        Args:
            param_name: 参数名称
            value: 参数值
            
        Returns:
            (success, message)
        """
        if not self._connected or not self._acq_device:
            return False, "相机未连接"
        
        try:
            if not self._acq_device.IsFeatureAvailable(param_name):
                return False, f"参数 {param_name} 不可用"
            
            if self._acq_device.SetFeatureValue(param_name, value):
                return True, f"参数 {param_name} 设置成功"
            else:
                return False, f"参数 {param_name} 设置失败"
                
        except Exception as e:
            return False, f"设置参数失败: {e}"
    
    def get_parameter(self, param_name: str) -> tuple[bool, str, any]:
        """
        获取相机参数
        
        Returns:
            (success, message, value)
        """
        if not self._connected or not self._acq_device:
            return False, "相机未连接", None
        
        try:
            if not self._acq_device.IsFeatureAvailable(param_name):
                return False, f"参数 {param_name} 不可用", None
            
            value = self._acq_device.GetFeatureValue(param_name)
            return True, "获取成功", value
            
        except Exception as e:
            return False, f"获取参数失败: {e}", None


# 全局单例实例
_sapera_camera_manager = None

def get_sapera_camera_manager() -> SaperaCameraManager:
    """获取 Sapera 相机管理器单例"""
    global _sapera_camera_manager
    if _sapera_camera_manager is None:
        _sapera_camera_manager = SaperaCameraManager()
    return _sapera_camera_manager