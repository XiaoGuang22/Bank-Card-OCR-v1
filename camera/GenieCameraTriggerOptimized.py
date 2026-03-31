import clr
import sys
import time
import numpy as np
from datetime import datetime

# 导入异常处理工具
try:
    from utils.exception_utils import ErrorHandler, safe_call, safe_execute
except ImportError:
    # 如果异常处理工具不可用，使用简单的装饰器
    class ErrorHandler:
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

# ==============================================================================
# 1. 基础配置
# ==============================================================================
# 定义 Sapera LT .NET 组件 DLL 的绝对路径
# 该 DLL 提供了 Python 调用 Sapera SDK 所需的所有类
SAPERA_DLL_PATH = r"C:\Program Files\Teledyne DALSA\Sapera\Components\NET\Bin\DALSA.SaperaLT.SapClassBasic.dll"

# 相机服务器名称，必须与 Sapera CamExpert 中显示的名称完全一致
SERVER_NAME = "Genie_M1600_1"
# 资源索引，通常第一个相机接口为 0
RESOURCE_INDEX = 0

# ==============================================================================
# 2. 加载 .NET 组件库
# ==============================================================================
try:
    # 加载 C# DLL 到 Python 运行时环境
    clr.AddReference(SAPERA_DLL_PATH)
    # 导入 Sapera 的核心类
    from DALSA.SaperaLT.SapClassBasic import (
        SapLocation,        # 用于定位相机（物理连接）
        SapAcqDevice,       # 代表采集设备（相机本身）
        SapBuffer,          # 基础缓冲区类
        SapBufferWithTrash, # 带垃圾回收机制的缓冲区（防止丢帧导致的内存问题）
        SapAcqDeviceToBuf,  # 传输模块：将数据从设备传输到缓冲区
        SapView,            # SDK 自带的图像显示窗口类
        SapXferPair         # 传输对配置（定义源和目标）
    )
except Exception as e:
    sys.exit(1)

# ==============================================================================
# 3. 相机控制类封装
# ==============================================================================
class GenieLiveCamera:
    def __init__(self, server_name, resource_index):
        """
        构造函数：初始化对象状态，但不连接硬件
        """
        # SapLocation 对象用于描述“哪个服务器上的哪个资源”
        self.location = SapLocation(server_name, resource_index)
        
        # 初始化各组件变量为空，后续在 init_system 中创建
        self.acq_device = None  # 设备对象
        self.buffers = None     # 图像缓冲区
        self.xfer = None        # 传输对象
        self.view = None        # 显示窗口
        
        # 统计相关
        self.frame_count = 0    # 帧计数器
        self.last_print_time = time.time() # 上次打印FPS的时间

    @ErrorHandler.handle_system_error
    def init_system(self):
        """
        初始化系统：创建所有必要的 Sapera 对象并建立连接
        """
        # --- 1. 创建采集设备 (Acquisition Device) ---
        # 第二个参数 False 表示不使用配置文件，而是使用默认设置或后续代码配置
        self.acq_device = SapAcqDevice(self.location, False)
        if not self.acq_device.Create():
            raise Exception("创建设备失败!")
        
        # --- 2. 检查并设置像素格式 ---
        # PixelFormat 决定了图像是黑白还是彩色，以及位深（如 Mono8, BayerGR8）
        if self.acq_device.IsFeatureAvailable("PixelFormat"):
            try:
                current_format = self.acq_device.GetFeatureValue("PixelFormat")
                # 强制设置为 Mono8 (8位黑白)，这通常是机器视觉最通用的格式
                self.acq_device.SetFeatureValue("PixelFormat", "Mono8")
            except Exception as e:
                pass
        
        # --- 3. 设置网络包大小 (关键防黑屏设置) ---
        # GevSCPSPacketSize: GigE Vision 流通道包大小
        # 默认的巨型帧 (9000+) 可能被防火墙或网卡拦截，强制设为 1500 (标准以太网帧) 可保证稳定性
        if self.acq_device.IsFeatureAvailable("GevSCPSPacketSize"):
            self.acq_device.SetFeatureValue("GevSCPSPacketSize", 1500)
        
        # --- 4. 创建缓冲区 (Buffers) ---
        # count=2: 双缓冲模式，一个用于采集，一个用于处理/显示
        # MemoryType.ScatterGather: 分散/聚集 DMA 模式，性能最高
        self.buffers = SapBufferWithTrash(2, self.acq_device, SapBuffer.MemoryType.ScatterGather)
        if not self.buffers.Create():
            # 如果高性能模式失败，尝试回退到物理内存模式
            self.buffers = SapBufferWithTrash(2, self.acq_device, SapBuffer.MemoryType.ScatterGatherPhysical)
            if not self.buffers.Create():
                raise Exception("创建缓冲区失败!")
        
        # --- 5. 创建传输对象 (Transfer) ---
        # 负责将数据从 acq_device 搬运到 buffers
        self.xfer = SapAcqDeviceToBuf(self.acq_device, self.buffers)
        
        # 配置传输行为：
        # EndOfFrame: 每传输完一帧触发一次事件
        self.xfer.Pairs[0].EventType = SapXferPair.XferEventType.EndOfFrame
        # NextWithTrash: 循环使用缓冲区，如果处理不过来则丢弃旧帧（防止延迟累积）
        self.xfer.Pairs[0].Cycle = SapXferPair.CycleMode.NextWithTrash
        
        # 绑定 Python 回调函数，当收到图片时会调用 self.on_frame_callback
        self.xfer.XferNotify += self.on_frame_callback
        
        if not self.xfer.Create():
            raise Exception("创建传输对象失败!")
        
        # --- 6. 创建 SDK 自带显示窗口 (View) ---
        self.view = SapView(self.buffers)
        if not self.view.Create():
            raise Exception("创建窗口失败!")
    

    @ErrorHandler.handle_camera_error
    def config_camera(self, frame_rate=10.0, exposure_us=20000, gain_raw=100):
        """
        配置相机核心参数：帧率、曝光、增益
        包含安全检查逻辑
        """
        # --- 安全逻辑：计算最大曝光时间 ---
        # 曝光时间必须小于帧间隔，否则会导致帧率下降或丢帧
        # 例如 10fps = 100ms 周期，这里乘以 0.7 留出 30% 余量
        max_safe_exposure = int((1000000 / (frame_rate / 1000)) * 0.7)
        if exposure_us > max_safe_exposure:
            exposure_us = max_safe_exposure
        
        # 辅助内部函数：封装 SetFeatureValue，增加错误处理
        def set_param(name, value):
            if not self.acq_device.IsFeatureAvailable(name):
                return False
            try:
                if self.acq_device.SetFeatureValue(name, value):
                    return True
                else:
                    return False
            except Exception as e:
                return False
        
        # 1. 触发模式设置
        # "Off" 代表自由运行模式 (Free Run)，相机自动连续拍照
        set_param("TriggerMode", "Off")
        
        # 2. 帧率控制
        # 先开启帧率控制使能，再设置具体数值
        set_param("AcquisitionFrameRate", frame_rate)
        
        
        # 3. 曝光控制
        # 先关闭自动曝光
        # 设置具体曝光时间 (微秒)，优先使用 Raw 值以避免浮点数精度问题
        set_param("ExposureTimeRaw", int(exposure_us))
        
        # 4. 增益控制
        # 兼容性处理：不同固件可能使用 GainRaw 或 Gain
        if self.acq_device.IsFeatureAvailable("GainRaw"):
            set_param("GainRaw", int(gain_raw))
        
        # 5. 黑电平 (Black Level) - 调节暗部细节
        if self.acq_device.IsFeatureAvailable("BlackLevelRaw"):
            set_param("BlackLevelRaw", 0)

    def start_live(self):
        """启动实时采集和显示"""
        # 弹出/显示 SapView 窗口
        self.view.Show()
        
        # 开始抓取 (Grab)
        # 这会启动后台传输线程
        if self.xfer.Grab():
            return True
        else:
            return False

    def on_frame_callback(self, sender, args):
        """
        回调函数：每当传输完一帧图像时，SDK 会自动调用此函数
        """
        if args.Trash:
            return
        
        self.frame_count += 1
        current_time = time.time()
        
        # 每秒更新一次计时器
        if current_time - self.last_print_time >= 1.0:
            # 重置计时器
            self.last_print_time = current_time
        
        # 刷新视图窗口
        if self.view:
            self.view.Show()



    @ErrorHandler.handle_camera_error
    def capture_single_frame(self, timeout_ms=5000):
        """
        单帧采集功能
        
        参数:
            timeout_ms: 等待超时时间（毫秒），默认5秒
        
        返回:
            成功返回 True，失败返回 False
        """
        if not self.xfer:
            return False
        
        try:
            # 使用 Snap 进行单帧采集
            if not self.xfer.Snap():
                return False
            
            # 等待采集完成
            if not self.xfer.Wait(timeout_ms):
                return False
            
            # 如果有显示窗口，刷新显示
            if self.view:
                self.view.Show()
            
            self.frame_count += 1
            return True
            
        except Exception as e:
            return False
    
    @safe_execute(default_return=None, log_error=True, error_message="获取帧数据失败")
    def get_frame_as_numpy(self, buffer_index=0):
        """
        将缓冲区中的图像数据转换为 numpy 数组
        使用临时文件的方法避免内存访问问题
        
        参数:
            buffer_index: 缓冲区索引，默认为 0
        
        返回:
            numpy.ndarray: 图像数据，失败返回 None
        """
        if not self.buffers:
            return None
        
        try:
            import tempfile
            import os
            
            # 创建临时 BMP 文件
            temp_file = tempfile.NamedTemporaryFile(suffix='.bmp', delete=False)
            temp_path = temp_file.name
            temp_file.close()
            
            # 使用 Sapera 的 Save 方法保存到临时文件
            if not self.buffers.Save(temp_path, "-format bmp"):
                return None
            
            # 使用 opencv 或 PIL 读取
            try:
                import cv2
                image = cv2.imread(temp_path, cv2.IMREAD_GRAYSCALE)
            except ImportError:
                from PIL import Image
                img = Image.open(temp_path)
                image = np.array(img)
            
            # 删除临时文件
            try:
                os.unlink(temp_path)
            except:
                pass
            
            return image
            
        except Exception as e:
            return None
    
    @safe_execute(default_return=None, log_error=True, error_message="保存帧到文件失败")
    def save_frame_to_file(self, filename=None, buffer_index=0):
        """
        保存当前帧到文件
        使用 Sapera 自带的保存功能，避免内存访问问题
        
        参数:
            filename: 文件名，如果为 None 则自动生成（带时间戳）
            buffer_index: 缓冲区索引
        
        返回:
            成功返回文件路径，失败返回 None
        """
        if not self.buffers:
            return None
        
        # 生成文件名
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            filename = f"capture_{timestamp}.bmp"
        
        # 确保文件扩展名是 BMP（Sapera 支持的格式）
        if not filename.lower().endswith('.bmp'):
            filename = filename.rsplit('.', 1)[0] + '.bmp'
        
        try:
            # 使用 Sapera 的 Save 方法直接保存
            if self.buffers.Save(filename, "-format bmp"):
                # 如果需要 PNG 格式，转换一下
                if filename.lower().endswith('.png'):
                    try:
                        import cv2
                        img = cv2.imread(filename.replace('.png', '.bmp'), cv2.IMREAD_GRAYSCALE)
                        cv2.imwrite(filename, img)
                        import os
                        os.unlink(filename.replace('.png', '.bmp'))
                    except:
                        pass
                
                return filename
            else:
                return None
                
        except Exception as e:
            return None
    
    @safe_execute(default_return=None, log_error=True, error_message="资源清理失败")
    def stop_and_destroy(self):
        """资源清理函数：按特定顺序停止和销毁对象，防止崩溃"""
        # 1. 停止传输
        if self.xfer:
            self.xfer.Freeze() # 暂停
            self.xfer.Abort()  # 中止
            self.xfer.Dispose()# 释放内存
        # 2. 销毁视图
        if self.view:
            self.view.Destroy()
            self.view.Dispose()
        # 3. 销毁缓冲区
        if self.buffers:
            self.buffers.Destroy()
            self.buffers.Dispose()
        # 4. 销毁设备
        if self.acq_device:
            self.acq_device.Destroy()
            self.acq_device.Dispose()

# ==============================================================================
# 4. 主程序入口
# ==============================================================================
def demo_single_capture():
    """演示：单帧采集模式"""
    print("\n" + "="*60)
    print("模式 1: 单帧采集演示")
    print("="*60)
    
    camera = GenieLiveCamera(SERVER_NAME, RESOURCE_INDEX)
    
    try:
        # 初始化系统
        camera.init_system()
        
        # 配置参数（单帧采集时帧率不重要）
        camera.config_camera(
            frame_rate=10000,
            exposure_us=20000,
            gain_raw=100
        )
        
        # 执行单帧采集
        print("\n开始采集 3 张图像...")
        for i in range(3):
            print(f"\n--- 第 {i+1} 张 ---")
            if camera.capture_single_frame():
                # 保存图像（使用 BMP 格式更稳定）
                filename = f"single_capture_{i+1}.bmp"
                camera.save_frame_to_file(filename)
            time.sleep(0.5)  # 间隔 0.5 秒
        
        print("\n✅ 单帧采集完成！")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        camera.stop_and_destroy()

def demo_continuous_capture():
    """演示：连续采集模式"""
    print("\n" + "="*60)
    print("模式 2: 连续采集演示")
    print("="*60)
    
    camera = GenieLiveCamera(SERVER_NAME, RESOURCE_INDEX)
    
    try:
        # 初始化系统
        camera.init_system()
        
        # 配置参数
        camera.config_camera(
            frame_rate=10000,
            exposure_us=20000,
            gain_raw=100
        )
        
        # 开始连续采集
        if camera.start_live():
            print("\n" + "="*60)
            print("相机正在运行，Sapera 预览窗口应已弹出。")
            print("按回车键停止程序...")
            print("="*60 + "\n")
            input()
        
    except KeyboardInterrupt:
        print("\n⚠️ 用户强制中断 (Ctrl+C)")
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        camera.stop_and_destroy()

if __name__ == "__main__":
    print("\n" + "="*60)
    print("Genie 相机采集程序")
    print("="*60)
    print("\n请选择运行模式:")
    print("  1 - 单帧采集模式（采集 3 张图片并保存）")
    print("  2 - 连续采集模式（实时预览）")
    print("  0 - 退出")
    
    choice = input("\n请输入选项 (1/2/0): ")
    
    if choice == "1":
        demo_single_capture()
    elif choice == "2":
        demo_continuous_capture()
    elif choice == "0":
        print("\n👋 退出程序")
    else:
        print("\n❌ 无效选项")