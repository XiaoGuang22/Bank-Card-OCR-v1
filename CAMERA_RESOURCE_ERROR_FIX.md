# 相机资源占用错误修复指南

## 错误信息
```
Error in "CorAcqDeviceGetHandle" <Acquisition Device module>
Resource in use ()
```

## 原因
相机资源正在被其他程序或进程占用，无法获取设备句柄。

## 解决方案

### 方案1：关闭占用相机的程序（推荐）

1. **关闭 CamExpert**
   - 如果 Teledyne DALSA CamExpert 正在运行，请完全关闭它
   - 确保在系统托盘中也没有运行

2. **关闭其他相机程序**
   - 检查任务管理器中是否有其他使用相机的程序
   - 关闭所有可能访问相机的应用程序

3. **重启程序**
   - 关闭当前的 Bank-Card-OCR 程序
   - 等待几秒钟
   - 重新启动程序

### 方案2：使用任务管理器强制结束进程

如果程序无法正常关闭：

1. 按 `Ctrl + Shift + Esc` 打开任务管理器
2. 查找以下进程并结束：
   - `CamExpert.exe`
   - `python.exe`（如果有多个，结束与相机相关的）
   - 任何 Sapera 相关的进程
3. 重新启动程序

### 方案3：重启相机

如果软件方法无效：

1. 断开相机电源或网线
2. 等待 10 秒
3. 重新连接相机
4. 等待相机初始化完成（约 30 秒）
5. 启动程序

### 方案4：修改代码（已实现）

我们已经在代码中实现了以下改进：

1. **非独占模式创建设备**
   ```python
   acq_device = SapAcqDevice(location, False)  # False = 非独占
   ```

2. **确保资源释放**
   - 在 `finally` 块中确保 `Destroy()` 和 `Dispose()` 被调用
   - 添加了多层异常处理

3. **抑制错误对话框**
   - 设置 `DisplayStatusMode` 为 Log 模式
   - 错误信息只记录到日志，不弹出对话框

## 预防措施

### 1. 程序退出时正确释放资源

确保程序关闭时调用：
```python
camera_manager.disconnect()
```

### 2. 避免同时运行多个相机程序

- 使用相机时，不要同时打开 CamExpert
- 一次只运行一个使用相机的程序

### 3. 使用非独占模式

在创建 `SapAcqDevice` 时使用非独占模式：
```python
acq_device = SapAcqDevice(location, False)  # 非独占模式
```

## 常见问题

### Q: 为什么会出现这个错误？
A: Sapera SDK 的设备句柄是独占的，一次只能被一个程序使用。如果另一个程序正在使用相机，就会出现这个错误。

### Q: 关闭 CamExpert 后还是报错怎么办？
A: 可能是进程没有完全退出，请使用任务管理器强制结束进程，或者重启相机。

### Q: 如何避免这个错误？
A: 
1. 使用相机前确保没有其他程序在使用
2. 程序退出时正确释放资源
3. 使用非独占模式创建设备

### Q: 错误对话框太烦人，能关闭吗？
A: 我们已经在代码中设置了 Log 模式，错误信息会记录到日志而不是弹出对话框。如果还是弹出，可能需要在 Sapera SDK 配置中关闭。

## 技术细节

### 资源占用的原因

1. **设备句柄独占**：Sapera SDK 的 `SapAcqDevice` 默认是独占模式
2. **未正确释放**：程序异常退出时可能没有调用 `Destroy()` 和 `Dispose()`
3. **多实例冲突**：同一程序的多个实例尝试访问同一相机

### 正确的资源管理

```python
acq_device = None
try:
    location = SapLocation(server_name, 0)
    acq_device = SapAcqDevice(location, False)  # 非独占模式
    
    if acq_device.Create():
        # 使用设备...
        pass
finally:
    # 确保资源释放
    if acq_device:
        try:
            acq_device.Destroy()
        except:
            pass
        try:
            acq_device.Dispose()
        except:
            pass
```

## 联系支持

如果以上方法都无法解决问题，可能是：
- Sapera SDK 安装问题
- 相机固件问题
- 网络配置问题

请检查：
1. Sapera SDK 是否正确安装
2. 相机固件是否最新
3. 网络连接是否正常
4. 防火墙是否阻止了相机通信