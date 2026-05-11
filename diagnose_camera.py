"""
相机诊断脚本

检查相机连接状态和可访问性
"""

import clr
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import SAPERA_DLL_PATH, SERVER_NAME

print("=" * 60)
print("相机诊断工具")
print("=" * 60)
print()

# 1. 检查 Sapera SDK
print("1. 检查 Sapera SDK...")
if not os.path.exists(SAPERA_DLL_PATH):
    print(f"   ❌ Sapera SDK 不存在: {SAPERA_DLL_PATH}")
    sys.exit(1)
else:
    print(f"   ✅ Sapera SDK 存在")

# 2. 加载 Sapera SDK
print("\n2. 加载 Sapera SDK...")
try:
    clr.AddReference(SAPERA_DLL_PATH)
    from DALSA.SaperaLT.SapClassBasic import (
        SapManager,
        SapLocation,
        SapAcqDevice,
    )
    print("   ✅ Sapera SDK 加载成功")
except Exception as e:
    print(f"   ❌ Sapera SDK 加载失败: {e}")
    sys.exit(1)

# 3. 检查服务器数量
print("\n3. 检查服务器数量...")
try:
    server_count = SapManager.GetServerCount()
    print(f"   ✅ 发现 {server_count} 个服务器")
    
    for i in range(server_count):
        server_name = SapManager.GetServerName(i)
        print(f"      服务器 {i}: {server_name}")
except Exception as e:
    print(f"   ❌ 获取服务器数量失败: {e}")
    sys.exit(1)

# 4. 检查目标相机
print(f"\n4. 检查目标相机: {SERVER_NAME}...")
target_index = -1
for i in range(server_count):
    server_name = SapManager.GetServerName(i)
    if server_name == SERVER_NAME:
        target_index = i
        print(f"   ✅ 找到目标相机，索引: {i}")
        break

if target_index == -1:
    print(f"   ❌ 未找到目标相机: {SERVER_NAME}")
    sys.exit(1)

# 5. 检查相机是否可访问
print("\n5. 检查相机是否可访问...")
try:
    is_accessible = SapManager.IsServerAccessible(target_index)
    if is_accessible:
        print("   ✅ 相机可访问")
    else:
        print("   ⚠️ 相机不可访问（可能被占用）")
except Exception as e:
    print(f"   ⚠️ 无法检查可访问性: {e}")

# 6. 尝试创建设备（非独占模式）
print("\n6. 尝试创建设备（非独占模式）...")
acq_device = None
try:
    location = SapLocation(SERVER_NAME, 0)
    acq_device = SapAcqDevice(location, False)  # False = 非独占模式
    
    if acq_device.Create():
        print("   ✅ 设备创建成功（非独占模式）")
        
        # 7. 读取设备信息
        print("\n7. 读取设备信息...")
        try:
            # 读取 Device User ID
            if acq_device.IsFeatureAvailable("DeviceUserID"):
                result = acq_device.GetFeatureValue("DeviceUserID")
                user_id = result[1] if isinstance(result, tuple) else result
                print(f"   Device User ID: {user_id}")
            
            # 读取 IP 地址
            if acq_device.IsFeatureAvailable("GevCurrentIPAddress"):
                result = acq_device.GetFeatureValue("GevCurrentIPAddress")
                ip_value = result[1] if isinstance(result, tuple) else result
                if isinstance(ip_value, (int, float)):
                    ip_int = int(ip_value)
                    ip_str = f"{(ip_int >> 24) & 0xFF}.{(ip_int >> 16) & 0xFF}.{(ip_int >> 8) & 0xFF}.{ip_int & 0xFF}"
                    print(f"   IP 地址: {ip_str}")
                else:
                    print(f"   IP 地址: {ip_value}")
            
            # 读取分辨率
            if acq_device.IsFeatureAvailable("Width"):
                result = acq_device.GetFeatureValue("Width")
                width = result[1] if isinstance(result, tuple) else result
                print(f"   宽度: {width}")
            
            if acq_device.IsFeatureAvailable("Height"):
                result = acq_device.GetFeatureValue("Height")
                height = result[1] if isinstance(result, tuple) else result
                print(f"   高度: {height}")
            
            print("   ✅ 设备信息读取成功")
            
        except Exception as e:
            print(f"   ⚠️ 读取设备信息失败: {e}")
        
        # 清理
        acq_device.Destroy()
        print("\n   ✅ 设备已正常释放")
        
    else:
        print("   ❌ 设备创建失败（可能被其他程序占用）")
        print("\n   建议操作：")
        print("   1. 关闭 CamExpert")
        print("   2. 关闭其他使用相机的程序")
        print("   3. 重新运行本程序")
        
except Exception as e:
    print(f"   ❌ 创建设备时出错: {e}")
finally:
    if acq_device:
        try:
            acq_device.Destroy()
        except:
            pass

# 8. 网络连接测试
print("\n8. 测试网络连接...")
import subprocess
try:
    result = subprocess.run(['ping', '-n', '1', '-w', '1000', '192.168.11.136'], 
                          capture_output=True, text=True, timeout=2)
    if result.returncode == 0:
        print("   ✅ 网络连接正常（可以 ping 通 192.168.11.136）")
    else:
        print("   ❌ 网络连接失败（无法 ping 通 192.168.11.136）")
except Exception as e:
    print(f"   ⚠️ 网络测试失败: {e}")

print("\n" + "=" * 60)
print("诊断完成")
print("=" * 60)
