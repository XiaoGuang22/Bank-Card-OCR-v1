# 相机切换回原相机失败问题 - 根本原因和修复

## 问题描述

用户报告：
1. 电脑同时接了两台相机：S1049704 (192.168.11.136) 和 S1024035 (192.168.12.110)
2. 切换到 035 相机 → **成功** ✅
3. 尝试切换回 704 相机 → **失败** ❌，提示"已是当前连接的相机，无需切换"

## 根本原因分析

通过调试日志发现了问题的根本原因：

### 调试日志关键信息

```
# 启动时
[Sapera] 无法创建设备 Genie_M1600_1（可能被占用）
[Sapera] 使用配置名称: S1049704 for Genie_M1600_1

# 第一次切换（035 → 成功）
[CameraStatusBar] 切换相机检查:
  当前相机: SaperaCameraInfo(server_name='Genie_M1600_1', ...)  # ❌ 错误！
  目标相机: SaperaCameraInfo(server_name='Genie_M1600_2', ...)
  相等性检查: False  # 所以可以切换

[SaperaCameraManager] switch_camera 检查:
  当前相机: None  # ✓ 正确！
  目标相机: SaperaCameraInfo(server_name='Genie_M1600_2', ...)

# 第二次切换（尝试切换回 704 → 失败）
[CameraStatusBar] 切换相机检查:
  当前相机: SaperaCameraInfo(server_name='Genie_M1600_1', ...)  # ❌ 错误！
  目标相机: SaperaCameraInfo(server_name='Genie_M1600_1', ...)
  相等性检查: True  # ❌ 认为是同一台相机，拒绝切换！
```

### 问题根源

**状态不一致**：
- `EnhancedCameraManager._current_camera` = **Genie_M1600_1** ❌（错误）
- `SaperaCameraManager._current_camera` = **None** ✓（正确）

**为什么会这样？**

1. **启动时**：
   - `CameraController.connect()` 尝试连接到 `Genie_M1600_1`（配置中的默认相机）
   - 连接成功，`CameraController` 创建了 `SapAcqDevice` 并占用了设备

2. **扫描时**：
   - `_get_device_info()` 尝试再次创建 `SapAcqDevice` 来获取设备信息
   - 因为设备已被 `CameraController` 占用，`Create()` 失败
   - 返回空的 `device_info`（没有 user_id、model、ip_address 等信息）
   - 但相机仍然被添加到扫描结果中

3. **`_on_first_scan` 回调**：
   ```python
   sn = self.cam.current_server_name  # Genie_M1600_1
   for cam in cameras:
       if getattr(cam, 'server_name', '') == sn:
           mgr.set_initial_camera(cam)  # ❌ 错误地设置为当前相机！
           break
   ```
   - 找到 `server_name` 匹配的相机（Genie_M1600_1）
   - **盲目地**将它设置为 `EnhancedCameraManager._current_camera`
   - 但实际上这个相机的 `device_info` 是空的（因为被占用）
   - `SaperaCameraManager._current_camera` 仍然是 `None`

4. **切换时**：
   - `CameraStatusBar` 从 `self._manager.current_camera` 获取当前相机
   - 得到 `Genie_M1600_1`（错误的状态）
   - 比较 `current == target`，认为是同一台相机
   - 拒绝切换！

## 修复方案

### 修改 1: `InspectMainWindow.py` - `_on_first_scan` 方法

**修复前**：盲目地根据 `server_name` 匹配设置当前相机

```python
sn = self.cam.current_server_name
if sn:
    for cam in cameras:
        if getattr(cam, 'server_name', '') == sn:
            mgr.set_initial_camera(cam)  # ❌ 盲目设置
            break
```

**修复后**：检查实际连接状态和设备信息完整性

```python
sn = self.cam.current_server_name
if sn:
    from camera.sapera_camera_manager import get_sapera_camera_manager
    sapera_mgr = get_sapera_camera_manager()
    
    # 优先使用 SaperaCameraManager 的状态（最可靠）
    if sapera_mgr.is_connected and sapera_mgr.current_camera:
        mgr.set_initial_camera(sapera_mgr.current_camera)
    else:
        # 如果 CameraController 已连接，从扫描结果中找到匹配的相机
        if self.cam.acq_device is not None:
            for cam in cameras:
                if getattr(cam, 'server_name', '') == sn:
                    # 检查设备信息是否完整（不是"被占用"的）
                    device_info = getattr(cam, 'device_info', {}) or {}
                    if device_info.get('user_id') or device_info.get('model') or device_info.get('ip_address'):
                        mgr.set_initial_camera(cam)  # ✓ 有完整信息才设置
                        break
                    else:
                        # 信息不完整，跳过
                        break
```

### 关键改进

1. **优先使用 `SaperaCameraManager` 的状态**：
   - `SaperaCameraManager` 是专门管理 Sapera 相机连接的
   - 它的 `is_connected` 和 `current_camera` 是最可靠的

2. **检查设备信息完整性**：
   - 如果相机被占用，`device_info` 会是空的
   - 只有当 `device_info` 包含 `user_id`、`model` 或 `ip_address` 时才认为是有效的

3. **添加详细的调试日志**：
   - 输出 `SaperaCameraManager` 的状态
   - 输出设置初始相机的决策过程

## 为什么 704 相机会"被占用"？

这是正常的行为：

1. **`CameraController` 在启动时连接到 704 相机**
   - 创建 `SapAcqDevice` 并开始采集
   - 设备被独占

2. **扫描时尝试再次创建设备**
   - `_get_device_info()` 尝试创建 `SapAcqDevice` 来读取设备信息
   - 因为设备已被占用，`Create()` 失败
   - 这是预期的行为，不是错误

3. **解决方案**
   - 不应该在扫描时尝试创建已连接的设备
   - 或者使用非独占模式（`SapAcqDevice(location, False)`）
   - 但最简单的方法是：不要盲目地设置当前相机，而是检查实际状态

## 测试建议

重新运行程序，观察以下日志：

1. **启动时**：
   ```
   [InspectMainWindow] _on_first_scan: CameraController.current_server_name = Genie_M1600_1
   [InspectMainWindow] SaperaCameraManager 状态:
     is_connected: False/True
     current_camera: None/SaperaCameraInfo(...)
   [InspectMainWindow] ✓/✗ 设置初始相机: ...
   ```

2. **切换时**：
   - 观察 `[CameraStatusBar] 切换相机检查` 的输出
   - 确认 `当前相机` 和 `目标相机` 的值是否正确

## 预期效果

修复后：
1. **启动时**：`EnhancedCameraManager._current_camera` 应该与实际连接的相机一致
2. **切换到 035**：成功 ✅
3. **切换回 704**：成功 ✅（不再提示"已是当前连接的相机"）

## 修改文件

- `InspectMainWindow.py` - `_on_first_scan` 方法
- `ui/CameraStatusBar.py` - 添加调试信息（已完成）
- `camera/sapera_camera_manager.py` - 添加调试信息（已完成）

## 修改日期

2026-05-13
