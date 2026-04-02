"""
系统配置文件

包含所有可配置的参数，方便统一管理和修改。
"""

import os

# ==============================================================================
# 相机配置
# ==============================================================================

# Sapera SDK DLL 路径
SAPERA_DLL_PATH = r"C:\Program Files\Teledyne DALSA\Sapera\Components\NET\Bin\DALSA.SaperaLT.SapClassBasic.dll"

# 相机服务器名称（必须与 Sapera CamExpert 中显示的名称一致）
# 注意：需要在 Sapera CamExpert 中查看实际的服务器名称
SERVER_NAME = "Genie_M1600_1"  # 或者 "Genie_M1600_1"，需要确认

# 资源索引（通常第一个相机为 0）
RESOURCE_INDEX = 0

# 相机默认参数（程序关闭时恢复为这些值）
CAMERA_DEFAULT_PARAMS = {
    'frame_rate_hz': 6.0,           # 默认帧率（Hz）
    'exposure_time_us': 66500,      # 默认曝光时间（微秒）= 66.5 ms
    'trigger_mode': 'Off',          # 默认触发模式（Off = 自由运行）
}

# 用户传感器设置（程序启动时的默认值，每次启动都重置为此）
DEFAULT_SENSOR_SETTINGS = {
    'trigger_mode': 'internal',     # 触发模式: internal/software
    'interval_ms': 66,              # 内部定时间隔（毫秒）
    'exposure_ms': 25.0,            # 曝光时间（毫秒）
    'brightness': 50,               # 亮度（0-100%）
    'contrast': 50,                 # 对比度（0-100%）
}

# 运行时传感器设置（程序启动时从 DEFAULT_SENSOR_SETTINGS 初始化）
USER_SENSOR_SETTINGS = DEFAULT_SENSOR_SETTINGS.copy()

# 对比度调整方案配置
CONTRAST_METHOD = 'lut'  # 'lut' 或 'black_level' 或 'software'
# 'lut': 使用 LUT 实现完整对比度控制（0-100%），但会弹出 SDK 警告对话框
# 'black_level': 使用黑电平，只能降低对比度（0-50%），不会弹出警告
# 'software': 使用软件处理，完整对比度控制（0-100%），不会弹出警告，但会增加 CPU 负担

# 软件对比度调整参数（仅当 CONTRAST_METHOD = 'software' 时生效）
SOFTWARE_CONTRAST_VALUE = 50  # 0-100，由 UI 动态更新

# ==============================================================================
# 图像处理配置
# ==============================================================================

# 模板标准化尺寸 (宽, 高)
TEMPLATE_NORM_SIZE = (64, 96)

# 图像预处理参数
IMAGE_PREPROCESSING = {
    'gaussian_blur_ksize': (5, 5),      # 高斯模糊核大小
    'bilateral_filter_d': 9,            # 双边滤波直径
    'bilateral_filter_sigma': 75,       # 双边滤波 sigma
    'adaptive_threshold_block': 11,     # 自适应阈值块大小
    'adaptive_threshold_c': 2,          # 自适应阈值常数
}

# 模板匹配参数
TEMPLATE_MATCHING = {
    'method': 'cv2.TM_CCOEFF_NORMED',   # 匹配方法
    'threshold': 0.7,                    # 匹配阈值
    'max_candidates': 5,                 # 最大候选数量
}

# ==============================================================================
# UI 配置
# ==============================================================================

# 主窗口配置
MAIN_WINDOW = {
    'title': 'iNspect Express - Bank Card OCR System',
    'geometry': '1280x800',
    'min_width': 1024,
    'min_height': 768,
}

# 侧边栏配置
SIDEBAR = {
    'width': 340,
    'min_width': 300,
    'bg_color': 'white',
}

# 图标配置
ICON = {
    'size': (40, 40),
    'path': 'icon',
}

# ==============================================================================
# 路径配置
# ==============================================================================

# 获取项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 解决方案存储路径
SOLUTIONS_PATH = os.path.join(PROJECT_ROOT, 'solutions')

# 图标资源路径
ICON_PATH = os.path.join(PROJECT_ROOT, 'icon')

# 临时文件路径
TEMP_PATH = os.path.join(PROJECT_ROOT, 'temp')

# ==============================================================================
# 日志配置
# ==============================================================================

# 是否启用详细日志
VERBOSE_LOGGING = True

# 日志级别 ('DEBUG', 'INFO', 'WARNING', 'ERROR')
LOG_LEVEL = 'INFO'

# ==============================================================================
# 性能配置
# ==============================================================================

# 视频刷新间隔（毫秒）
VIDEO_REFRESH_INTERVAL = 40  # 约 25 FPS

# 缓冲区数量
BUFFER_COUNT = 2

# 线程池大小
THREAD_POOL_SIZE = 4

# ==============================================================================
# 辅助函数
# ==============================================================================

def save_user_sensor_settings(settings):
    """保存用户传感器设置到配置文件"""
    global USER_SENSOR_SETTINGS
    USER_SENSOR_SETTINGS.update(settings)
    # 这里可以扩展为保存到文件，目前保存在内存中

def get_user_sensor_settings():
    """获取用户传感器设置"""
    return USER_SENSOR_SETTINGS.copy()

def ensure_directories():
    """确保必要的目录存在"""
    directories = [SOLUTIONS_PATH, TEMP_PATH]
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"✅ 创建目录: {directory}")

def get_icon_path(icon_name):
    """获取图标完整路径"""
    return os.path.join(ICON_PATH, icon_name)

def validate_config():
    """验证配置是否有效"""
    errors = []
    
    # 检查 Sapera DLL 是否存在
    if not os.path.exists(SAPERA_DLL_PATH):
        errors.append(f"❌ Sapera DLL 不存在: {SAPERA_DLL_PATH}")
    
    # 检查图标目录是否存在
    if not os.path.exists(ICON_PATH):
        errors.append(f"⚠️ 图标目录不存在: {ICON_PATH}")
    
    if errors:
        print("\n配置验证失败:")
        for error in errors:
            print(error)
        return False
    
    print("✅ 配置验证通过")
    return True


# 初始化时自动创建必要目录
if __name__ != "__main__":
    ensure_directories()

# ==============================================================================
# TCP 通信配置
# ==============================================================================

TCP_SETTINGS = {
    'port': 5024,
    'auto_start': False,
}
