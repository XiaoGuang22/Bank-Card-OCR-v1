"""
调试相机信息获取

详细查看相机信息获取过程，找出IP地址获取失败的原因
"""

def debug_camera_info():
    """调试相机信息获取"""
    print("🔍 调试相机信息获取过程")
    
    try:
        from camera.sapera_camera_discovery import get_sapera_discovery
        discovery = get_sapera_discovery()
        
        if not discovery.is_available:
            print("❌ Sapera SDK 不可用")
            return
        
        print("✅ Sapera SDK 可用")
        
        # 执行扫描并获取详细信息
        def on_complete(cameras):
            print(f"\n📋 发现 {len(cameras)} 台相机:")
            
            for i, camera in enumerate(cameras, 1):
                print(f"\n=== 相机 {i} 详细信息 ===")
                print(f"服务器名称: {camera.server_name}")
                print(f"服务器索引: {camera.server_index}")
                print(f"资源数量: {camera.resource_count}")
                print(f"是否可访问: {camera.is_accessible}")
                print(f"显示名称: {camera.display_name}")
                print(f"格式化显示名称: {camera.formatted_display_name}")
                
                device_info = camera.device_info or {}
                print(f"\n--- 设备信息 ---")
                for key, value in device_info.items():
                    print(f"{key}: {repr(value)}")
                
                print(f"\n--- 计算属性 ---")
                print(f"唯一标识: {camera.unique_identifier}")
                print(f"日志格式: {camera.log_target_object}")
        
        # 执行同步扫描
        discovery.scan(
            on_complete=on_complete,
            blocking=True,
            detect_new_servers=True
        )
        
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()


def test_manual_device_info():
    """手动测试设备信息获取"""
    print("\n🔧 手动测试设备信息获取")
    
    try:
        import clr
        from config import SAPERA_DLL_PATH
        
        clr.AddReference(SAPERA_DLL_PATH)
        from DALSA.SaperaLT.SapClassBasic import SapManager, SapLocation, SapAcqDevice
        
        # 获取服务器数量
        server_count = SapManager.GetServerCount()
        print(f"服务器数量: {server_count}")
        
        for i in range(server_count):
            try:
                server_name = SapManager.GetServerName(i)
                print(f"\n=== 服务器 {i}: {server_name} ===")
                
                # 创建设备
                location = SapLocation(server_name, 0)
                acq_device = SapAcqDevice(location, False)
                
                if acq_device.Create():
                    print("✅ 设备创建成功")
                    
                    # 测试各种特征
                    features_to_test = [
                        "DeviceUserID",
                        "DeviceSerialNumber", 
                        "DeviceModelName",
                        "GevCurrentIPAddress",
                        "DeviceVendorName",
                        "DeviceVersion"
                    ]
                    
                    for feature in features_to_test:
                        try:
                            if acq_device.IsFeatureAvailable(feature):
                                result = acq_device.GetFeatureValue(feature)
                                print(f"  {feature}: {repr(result)} (类型: {type(result)})")
                                
                                # 如果是元组，解析内容
                                if isinstance(result, tuple):
                                    print(f"    元组内容: success={result[0]}, value={repr(result[1]) if len(result) > 1 else 'N/A'}")
                            else:
                                print(f"  {feature}: 不可用")
                        except Exception as e:
                            print(f"  {feature}: 获取失败 - {e}")
                    
                    acq_device.Destroy()
                    acq_device.Dispose()
                else:
                    print("❌ 设备创建失败")
                    
            except Exception as e:
                print(f"处理服务器 {i} 失败: {e}")
        
    except Exception as e:
        print(f"❌ 手动测试失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数"""
    print("🚀 开始相机信息调试")
    
    # 调试相机发现
    debug_camera_info()
    
    # 手动测试设备信息
    test_manual_device_info()
    
    print("\n✅ 调试完成")


if __name__ == "__main__":
    main()