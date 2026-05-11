"""
基于Sapera SDK的相机发现和管理模块

使用Sapera LT原生API实现相机的自动发现、枚举和管理，
支持GigE Vision和Camera Link相机的自动检测。
"""

import clr
import sys
import threading
import time
from typing import List, Optional, Callable, Dict
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

# 导入配置
from config import SAPERA_DLL_PATH, CAMERA_DISPLAY_NAMES

# 加载Sapera SDK
try:
    clr.AddReference(SAPERA_DLL_PATH)
    from DALSA.SaperaLT.SapClassBasic import (
        SapManager,
        SapLocation,
        SapAcqDevice,
        SapBuffer
    )
    SAPERA_AVAILABLE = True
except Exception as e:
    print(f"Sapera SDK加载失败: {e}")
    SAPERA_AVAILABLE = False


@dataclass
class SaperaCameraInfo:
    """Sapera相机信息"""
    server_name: str        # Sapera服务器名称
    server_index: int       # 服务器索引
    resource_count: int     # 资源数量
    display_name: str       # 显示名称
    is_accessible: bool     # 是否可访问
    device_info: Dict       # 设备详细信息
    
    @property
    def formatted_display_name(self) -> str:
        """
        格式化显示名称，按需求文档 FC-05 格式：
        "用户自定义名 (IP)" 或 "型号 (IP)"
        """
        # 如果 display_name 已经是格式化的（包含括号），直接返回
        if self.display_name and '(' in self.display_name and ')' in self.display_name:
            return self.display_name
        
        # 否则进行格式化
        device_info = self.device_info or {}
        ip_address = device_info.get('ip_address', '').strip()
        
        # 优先使用已设置的 display_name（来自配置文件或其他逻辑）
        if self.display_name and self.display_name != self.server_name:
            name = self.display_name
        else:
            # 如果没有设置 display_name，则从设备信息中获取
            user_id = device_info.get('user_id', '').strip()
            model = device_info.get('model', '').strip()
            # 过滤掉看起来像数字ID的名称
            if user_id and not user_id.isdigit() and len(user_id) < 20:
                name = user_id
            elif model and not model.isdigit() and len(model) < 20:
                name = model
            else:
                name = self.server_name
        
        # 确保使用实际的IP地址
        if ip_address:
            return f"{name} ({ip_address})"
        else:
            # 如果没有IP地址，显示服务器名
            return f"{name} ({self.server_name})"
    
    @property
    def unique_identifier(self) -> str:
        """唯一标识符，优先使用序列号"""
        device_info = self.device_info or {}
        return (device_info.get('serial', '') or 
                self.server_name or 
                device_info.get('ip_address', ''))
    
    @property
    def log_target_object(self) -> str:
        """日志记录格式：用户自定义名(序列号)@IP"""
        device_info = self.device_info or {}
        user_id = device_info.get('user_id', '').strip()
        model = device_info.get('model', '').strip()
        serial = device_info.get('serial', '').strip()
        ip_address = device_info.get('ip_address', '').strip()
        
        name = user_id or model or self.server_name
        serial_part = f"({serial})" if serial else ""
        ip = ip_address or "未知IP"
        
        return f"{name}{serial_part}@{ip}"
    
    def __eq__(self, other):
        if not isinstance(other, SaperaCameraInfo):
            return False
        # 优先比较序列号，其次比较服务器名
        device_info = self.device_info or {}
        other_device_info = other.device_info or {}
        
        self_serial = device_info.get('serial', '')
        other_serial = other_device_info.get('serial', '')
        
        if self_serial and other_serial:
            return self_serial == other_serial
        
        return self.server_name == other.server_name
    
    def __hash__(self):
        device_info = self.device_info or {}
        serial = device_info.get('serial', '')
        return hash(serial) if serial else hash(self.server_name)


class SaperaCameraDiscovery:
    """
    基于Sapera SDK的相机发现器
    
    使用Sapera原生API进行相机发现和管理，避免网络扫描的问题
    """
    
    def __init__(self):
        self._scanning = False
        self._lock = threading.Lock()
        self._last_results: List[SaperaCameraInfo] = []
        self._event_registered = False
        
    @property
    def is_scanning(self) -> bool:
        return self._scanning
    
    @property
    def last_results(self) -> List[SaperaCameraInfo]:
        return list(self._last_results)
    
    @property
    def is_available(self) -> bool:
        """检查Sapera SDK是否可用"""
        return SAPERA_AVAILABLE
    
    def scan(
        self,
        on_complete: Optional[Callable[[List[SaperaCameraInfo]], None]] = None,
        on_progress: Optional[Callable[[int, int], None]] = None,
        blocking: bool = False,
        detect_new_servers: bool = True
    ):
        """
        扫描Sapera相机
        
        Args:
            on_complete: 扫描完成回调
            on_progress: 进度回调
            blocking: 是否阻塞执行
            detect_new_servers: 是否检测新连接的服务器（用于Camera Link）
        """
        if not SAPERA_AVAILABLE:
            if on_complete:
                on_complete([])
            return
            
        with self._lock:
            if self._scanning:
                return
            self._scanning = True
        
        if blocking:
            self._do_scan(on_complete, on_progress, detect_new_servers)
        else:
            t = threading.Thread(
                target=self._do_scan,
                args=(on_complete, on_progress, detect_new_servers),
                daemon=True
            )
            t.start()
    
    def _do_scan(
        self,
        on_complete: Optional[Callable],
        on_progress: Optional[Callable],
        detect_new_servers: bool
    ):
        """执行实际的扫描操作"""
        try:
            found_cameras = []
            
            # 1. 对于Camera Link相机，先检测新服务器
            if detect_new_servers:
                self._detect_new_servers()
            
            # 2. 获取服务器数量
            server_count = SapManager.GetServerCount()
            
            if on_progress:
                on_progress(0, server_count)
            
            # 3. 遍历所有服务器
            for i in range(server_count):
                try:
                    # 获取服务器名称
                    server_name = SapManager.GetServerName(i)
                    
                    # 过滤掉系统设备和非真实相机
                    if server_name.startswith("System") or "System" in server_name:
                        print(f"跳过系统设备: {server_name}")
                        continue
                    
                    # 检查服务器是否可访问
                    is_accessible = True  # 默认为可访问，因为 IsServerAccessible 可能不可用
                    try:
                        is_accessible = SapManager.IsServerAccessible(i)
                    except Exception:
                        pass
                    
                    # 获取资源数量 - 修复方法调用
                    resource_count = 0
                    try:
                        # 尝试不同的方法调用方式
                        resource_count = SapManager.GetResourceCount(i)
                    except Exception as e1:
                        try:
                            # 如果失败，尝试其他方式
                            from DALSA.SaperaLT.SapClassBasic import ResourceType
                            resource_count = SapManager.GetResourceCount(server_name, ResourceType.AcqDevice)
                        except Exception as e2:
                            print(f"获取资源数量失败: {e1}, {e2}")
                            resource_count = 1  # 默认为1
                    
                    # 先获取设备详细信息
                    device_info = self._get_device_info(server_name, i)
                    
                    # 然后根据设备信息和配置计算显示名称
                    config_display_name = CAMERA_DISPLAY_NAMES.get(server_name, "")
                    device_info_dict = device_info or {}
                    
                    # 确定相机名称：Device User ID > 配置名称 > 型号 > 服务器名
                    user_id = device_info_dict.get('user_id', '').strip()
                    model = device_info_dict.get('model', '').strip()
                    config_display_name = CAMERA_DISPLAY_NAMES.get(server_name, "")
                    
                    # 优先使用相机自身的 Device User ID（如果不是纯数字且长度合理）
                    if user_id and not user_id.isdigit() and len(user_id) < 20:
                        camera_name = user_id
                        print(f"[Sapera] 使用相机 Device User ID: {camera_name} for {server_name}")
                    elif config_display_name:
                        camera_name = config_display_name
                        print(f"[Sapera] 使用配置名称: {camera_name} for {server_name}")
                    elif model and not model.isdigit() and len(model) < 20:
                        camera_name = model
                        print(f"[Sapera] 使用相机型号: {camera_name} for {server_name}")
                    else:
                        camera_name = server_name
                        print(f"[Sapera] 使用服务器名称: {camera_name} for {server_name}")
                    
                    # 获取IP地址用于显示
                    ip_address = device_info_dict.get('ip_address', '').strip()
                    
                    # 如果无法从设备获取IP地址，尝试通过网络扫描获取
                    if not ip_address and is_accessible:
                        # 对于GigE Vision相机，网络扫描可能不适用，先尝试ping已知IP
                        if server_name == "Genie_M1600_1":
                            known_ips = ["192.168.11.136", "192.168.11.110", "192.168.1.100", "192.168.0.100"]
                            for test_ip in known_ips:
                                try:
                                    import subprocess
                                    result = subprocess.run(['ping', '-n', '1', '-w', '1000', test_ip], 
                                                          capture_output=True, text=True, timeout=2)
                                    if result.returncode == 0:
                                        ip_address = test_ip
                                        print(f"[Sapera] 通过ping发现 {server_name} 的IP: {ip_address}")
                                        break
                                except Exception as e:
                                    continue
                        
                        # 如果ping也没找到，再尝试网络扫描
                        if not ip_address:
                            try:
                                from camera.ip_discovery_helper import get_cached_camera_ips, match_sapera_camera_to_ip
                                camera_ips = get_cached_camera_ips()
                                matched_ip = match_sapera_camera_to_ip(server_name, camera_ips)
                                if matched_ip:
                                    ip_address = matched_ip
                                    print(f"[Sapera] 通过网络扫描为 {server_name} 匹配到IP: {ip_address}")
                            except Exception as e:
                                print(f"[Sapera] 网络扫描匹配IP失败: {e}")
                    
                    # 如果还是没有IP，对于已知的相机尝试ping常见IP
                    if not ip_address and server_name == "Genie_M1600_1":
                        known_ips = ["192.168.11.136", "192.168.11.110", "192.168.1.100", "192.168.0.100"]
                        for test_ip in known_ips:
                            try:
                                import subprocess
                                result = subprocess.run(['ping', '-n', '1', '-w', '1000', test_ip], 
                                                      capture_output=True, text=True, timeout=2)
                                if result.returncode == 0:
                                    ip_address = test_ip
                                    print(f"[Sapera] 通过ping发现 {server_name} 的IP: {ip_address}")
                                    break
                            except Exception as e:
                                continue
                    
                    # 格式化显示名称：名称 (IP)
                    if ip_address:
                        display_name = f"{camera_name} ({ip_address})"
                    else:
                        display_name = f"{camera_name} (未知IP)"
                    
                    camera_info = SaperaCameraInfo(
                        server_name=server_name,
                        server_index=i,
                        resource_count=resource_count,
                        display_name=display_name,
                        is_accessible=is_accessible,
                        device_info=device_info
                    )
                    
                    found_cameras.append(camera_info)
                    
                    if on_progress:
                        on_progress(i + 1, server_count)
                        
                except Exception as e:
                    print(f"获取服务器 {i} 信息失败: {e}")
                    continue
            
            # 4. 按服务器名称排序
            found_cameras.sort(key=lambda x: x.server_name)
            self._last_results = found_cameras
            
            if on_complete:
                on_complete(found_cameras)
                
        except Exception as e:
            print(f"Sapera相机扫描失败: {e}")
            if on_complete:
                on_complete([])
        finally:
            with self._lock:
                self._scanning = False
    
    def _detect_new_servers(self):
        """检测新连接的GenCP Camera Link服务器"""
        try:
            # 注册服务器新增事件（如果还没注册）
            if not self._event_registered:
                # 这里应该注册ServerNew事件，但由于Python绑定限制，
                # 我们直接调用DetectAllServers
                self._event_registered = True
            
            # 检测所有服务器 - 修复方法调用
            try:
                # 尝试不带参数的调用
                SapManager.DetectAllServers()
            except Exception as e1:
                try:
                    # 如果失败，尝试带参数的调用
                    from DALSA.SaperaLT.SapClassBasic import DetectServerType
                    SapManager.DetectAllServers(DetectServerType.GenCP)
                except Exception as e2:
                    print(f"DetectAllServers 调用失败: {e1}, {e2}")
            
            # 等待一小段时间让检测完成
            time.sleep(0.1)
            
        except Exception as e:
            print(f"检测新服务器失败: {e}")
    
    def _get_device_info(self, server_name: str, server_index: int) -> Dict:
        """
        获取设备详细信息
        
        按需求文档 FC-05 要求，读取 GenICam 标准特征：
        - DeviceUserID (用户自定义名称)
        - DeviceSerialNumber (序列号)
        - DeviceModelName (型号)
        - GevCurrentIPAddress (当前IP地址)
        
        注意：创建设备后必须立即释放，避免资源占用
        """
        device_info = {
            'user_id': '',           # DeviceUserID
            'serial': '',            # DeviceSerialNumber
            'model': '',             # DeviceModelName
            'ip_address': '',        # GevCurrentIPAddress
            'vendor': '',            # DeviceVendorName
            'version': '',           # DeviceVersion
            'pixel_formats': [],
            'features': []
        }
        
        acq_device = None
        try:
            # 创建设备位置
            location = SapLocation(server_name, 0)  # 通常第一个资源
            
            # 创建设备对象（不独占模式）
            acq_device = SapAcqDevice(location, False)
            
            # 尝试创建设备，如果失败则直接返回空信息
            if not acq_device.Create():
                print(f"[Sapera] 无法创建设备 {server_name}（可能被占用）")
                return device_info
                try:
                    # 按需求文档 FC-05 读取 GenICam 标准特征
                    
                    # 用户自定义名称
                    if acq_device.IsFeatureAvailable("DeviceUserID"):
                        result = acq_device.GetFeatureValue("DeviceUserID")
                        if isinstance(result, tuple) and len(result) >= 2:
                            raw_value = result[1] if result[0] else ""
                            # 尝试将数字转换为字符串（可能是编码的字符串）
                            if isinstance(raw_value, (int, float)):
                                try:
                                    # 尝试将大整数转换为字符串
                                    hex_str = hex(int(raw_value))[2:]  # 去掉 0x 前缀
                                    if len(hex_str) % 2 == 1:
                                        hex_str = '0' + hex_str
                                    
                                    # 尝试解码为ASCII字符串
                                    decoded = bytes.fromhex(hex_str).decode('ascii', errors='ignore').strip('\x00')
                                    
                                    # 如果解码结果看起来是反向的，尝试反转
                                    if decoded and decoded.isprintable():
                                        # 检查是否需要反转（如果以数字开头但应该以S开头）
                                        if decoded[0].isdigit() and decoded[-1].upper() == 'S':
                                            decoded = decoded[::-1]  # 反转字符串
                                        device_info['user_id'] = decoded
                                    else:
                                        device_info['user_id'] = str(raw_value)
                                except:
                                    device_info['user_id'] = str(raw_value)
                            else:
                                device_info['user_id'] = str(raw_value)
                        else:
                            device_info['user_id'] = str(result)
                    
                    # 序列号（唯一标识）
                    if acq_device.IsFeatureAvailable("DeviceSerialNumber"):
                        result = acq_device.GetFeatureValue("DeviceSerialNumber")
                        if isinstance(result, tuple) and len(result) >= 2:
                            raw_value = result[1] if result[0] else ""
                            # 尝试解码序列号
                            if isinstance(raw_value, (int, float)):
                                try:
                                    hex_str = hex(int(raw_value))[2:]
                                    if len(hex_str) % 2 == 1:
                                        hex_str = '0' + hex_str
                                    decoded = bytes.fromhex(hex_str).decode('ascii', errors='ignore').strip('\x00')
                                    if decoded and decoded.isprintable():
                                        device_info['serial'] = decoded
                                    else:
                                        device_info['serial'] = str(raw_value)
                                except:
                                    device_info['serial'] = str(raw_value)
                            else:
                                device_info['serial'] = str(raw_value)
                        else:
                            device_info['serial'] = str(result)
                    
                    # 型号
                    if acq_device.IsFeatureAvailable("DeviceModelName"):
                        result = acq_device.GetFeatureValue("DeviceModelName")
                        if isinstance(result, tuple) and len(result) >= 2:
                            raw_value = result[1] if result[0] else ""
                            # 尝试解码型号
                            if isinstance(raw_value, (int, float)):
                                try:
                                    hex_str = hex(int(raw_value))[2:]
                                    if len(hex_str) % 2 == 1:
                                        hex_str = '0' + hex_str
                                    decoded = bytes.fromhex(hex_str).decode('ascii', errors='ignore').strip('\x00')
                                    if decoded and decoded.isprintable():
                                        device_info['model'] = decoded
                                    else:
                                        device_info['model'] = str(raw_value)
                                except:
                                    device_info['model'] = str(raw_value)
                            else:
                                device_info['model'] = str(raw_value)
                        else:
                            device_info['model'] = str(result)
                    
                    # 当前IP地址
                    if acq_device.IsFeatureAvailable("GevCurrentIPAddress"):
                        try:
                            result = acq_device.GetFeatureValue("GevCurrentIPAddress")
                            ip_value = result[1] if isinstance(result, tuple) and len(result) >= 2 else result
                            
                            if isinstance(ip_value, (int, float)):
                                # 将整数IP转换为点分十进制格式
                                ip_int = int(ip_value)
                                ip_str = f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"
                                device_info['ip_address'] = ip_str
                            else:
                                device_info['ip_address'] = str(ip_value)
                        except Exception as e:
                            print(f"获取IP地址失败: {e}")
                    
                    # 其他设备信息
                    if acq_device.IsFeatureAvailable("DeviceVendorName"):
                        result = acq_device.GetFeatureValue("DeviceVendorName")
                        if isinstance(result, tuple) and len(result) >= 2:
                            device_info['vendor'] = str(result[1]) if result[0] else ""
                        else:
                            device_info['vendor'] = str(result)
                    
                    if acq_device.IsFeatureAvailable("DeviceVersion"):
                        result = acq_device.GetFeatureValue("DeviceVersion")
                        if isinstance(result, tuple) and len(result) >= 2:
                            device_info['version'] = str(result[1]) if result[0] else ""
                        else:
                            device_info['version'] = str(result)
                    
                    # 获取支持的像素格式
                    if acq_device.IsFeatureAvailable("PixelFormat"):
                        try:
                            result = acq_device.GetFeatureValue("PixelFormat")
                            current_format = result[1] if isinstance(result, tuple) and len(result) >= 2 else result
                            device_info['pixel_formats'] = [str(current_format)]
                        except:
                            pass
                    
                    # 获取关键特性列表
                    key_features = [
                        "TriggerMode", "ExposureTime", "ExposureTimeRaw", "Gain", "GainRaw",
                        "Width", "Height", "AcquisitionFrameRate", "GevSCPSPacketSize",
                        "DeviceTemperature", "DeviceUptime"
                    ]
                    
                    available_features = []
                    for feature in key_features:
                        if acq_device.IsFeatureAvailable(feature):
                            available_features.append(feature)
                    
                    device_info['features'] = available_features
                    
                    # 调试输出
                    print(f"[Sapera] 设备 {server_name} 信息:")
                    print(f"  用户名: {device_info['user_id']}")
                    print(f"  序列号: {device_info['serial']}")
                    print(f"  型号: {device_info['model']}")
                    print(f"  IP地址: {device_info['ip_address']}")
                    print(f"  厂商: {device_info['vendor']}")
                    
                except Exception as e:
                    print(f"获取设备 {server_name} 详细信息失败: {e}")
                finally:
                    # 确保设备被正确销毁和释放
                    if acq_device:
                        try:
                            acq_device.Destroy()
                        except:
                            pass
                        try:
                            acq_device.Dispose()
                        except:
                            pass
        
        except Exception as e:
            print(f"创建设备 {server_name} 失败: {e}")
        finally:
            # 最终确保资源释放
            if acq_device:
                try:
                    if hasattr(acq_device, 'Destroy'):
                        acq_device.Destroy()
                except:
                    pass
                try:
                    if hasattr(acq_device, 'Dispose'):
                        acq_device.Dispose()
                except:
                    pass
        
        return device_info
    
    def get_camera_by_name(self, server_name: str) -> Optional[SaperaCameraInfo]:
        """根据服务器名称获取相机信息"""
        for camera in self._last_results:
            if camera.server_name == server_name:
                return camera
        return None
    
    def refresh(self, on_complete: Optional[Callable] = None):
        """刷新相机列表（强制重新扫描）"""
        self.scan(on_complete=on_complete, detect_new_servers=True)


class SaperaCameraController:
    """
    Sapera相机控制器
    
    提供相机连接、断开、参数设置等功能
    """
    
    def __init__(self):
        self._current_camera: Optional[SaperaCameraInfo] = None
        self._acq_device: Optional = None
        self._connected = False
        self._lock = threading.Lock()
    
    @property
    def current_camera(self) -> Optional[SaperaCameraInfo]:
        return self._current_camera
    
    @property
    def is_connected(self) -> bool:
        return self._connected
    
    def connect(self, camera_info: SaperaCameraInfo) -> tuple[bool, str]:
        """
        连接到指定相机
        
        Returns:
            (success, message)
        """
        if not SAPERA_AVAILABLE:
            return False, "Sapera SDK不可用"
        
        with self._lock:
            # 如果已连接到同一相机，直接返回成功
            if (self._connected and self._current_camera and 
                self._current_camera.server_name == camera_info.server_name):
                return True, "已连接到该相机"
            
            # 断开当前连接
            if self._connected:
                self._disconnect_internal()
            
            try:
                # 创建设备位置
                location = SapLocation(camera_info.server_name, 0)
                
                # 创建设备对象
                self._acq_device = SapAcqDevice(location, False)
                
                if not self._acq_device.Create():
                    return False, f"无法创建设备: {camera_info.server_name}"
                
                # 连接成功
                self._current_camera = camera_info
                self._connected = True
                
                return True, f"成功连接到 {camera_info.display_name}"
                
            except Exception as e:
                self._disconnect_internal()
                return False, f"连接失败: {e}"
    
    def disconnect(self):
        """断开当前连接"""
        with self._lock:
            self._disconnect_internal()
    
    def _disconnect_internal(self):
        """内部断开连接方法（不加锁）"""
        if self._acq_device:
            try:
                self._acq_device.Destroy()
                self._acq_device.Dispose()
            except:
                pass
            self._acq_device = None
        
        self._current_camera = None
        self._connected = False
    
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
_sapera_discovery = None
_sapera_controller = None

def get_sapera_discovery() -> SaperaCameraDiscovery:
    """获取Sapera相机发现器单例"""
    global _sapera_discovery
    if _sapera_discovery is None:
        _sapera_discovery = SaperaCameraDiscovery()
    return _sapera_discovery

def get_sapera_controller() -> SaperaCameraController:
    """获取Sapera相机控制器单例"""
    global _sapera_controller
    if _sapera_controller is None:
        _sapera_controller = SaperaCameraController()
    return _sapera_controller