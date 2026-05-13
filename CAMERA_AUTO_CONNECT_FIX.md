# 相机自动连接问题修复 - 先扫描再连接

## 问题描述

用户反馈：
1. 704 相机总是显示"被主程序占用"
2. 想要实现：**先扫描可用相机，再选择连接**

## 问题根源

### 硬编码的相机连接

**位置 1**: `config.py`
```python
SERVER_NAME = "Genie_M1600_1"  # ← 硬编码了 704 相机
```

**位置 2**: `InspectMainWindow.py` - `__init__` 方法
```python
self.cam = CameraController()
self.cam.connect()  # ← 启动时立即连接，使用硬编码的 SERVER_NAME
```

### 问题流程

1. **程序启动**:
   ```
   InspectMainWindow.__init__()
   → self.cam = CameraController()
   → self.cam.connect()  # 使用 config.SERVER_NAME = "Genie_M1600_1"
   → 连接到 704 相机并占用设备
   ```

2. **扫描相机**:
   ```
   相机扫描开始
   → 尝试获取 704 相机的设备信息
   → 尝试创建 SapAcqDevice
   → 失败！因为设备已被 CameraController 占用
   → 返回空的 device_info
   ```

3. **结果**:
   - 704 相机被 `CameraController` 占用
   - 扫描时无法获取 704 相机的详细信息
   - 用户无法切换回 704 相机

## 修复方案

### 新的流程：先扫描，再连接

```
程序启动
→ 创建 CameraController（不连接）
→ 启动相机扫描
→ 扫描完成，获取所有可用相机列表
→ 自动连接到第一台有完整信息的相机
→ 用户可以在下拉框中切换到其他相机
```

### 修改 1: `InspectMainWindow.py` - 注释掉自动连接

**修改前**:
```python
self.cam = CameraController()
self.cam.connect()  # ← 立即连接
```

**修改后**:
```python
self.cam = CameraController()
# self.cam.connect()  # ← 注释掉，不自动连接
print("[InspectMainWindow] 相机控制器已创建，等待扫描完成后连接...")
```

### 修改 2: `_on_first_scan` - 扫描完成后自动连接

**新逻辑**:

```python
def _on_first_scan(sapera_cameras, network_cameras=None):
    # 合并相机列表
    cameras = list(sapera_cameras) + list(network_cameras or [])
    
    print(f"[InspectMainWindow] 扫描到 {len(cameras)} 台相机")
    
    if cameras:
        # 遍历所有相机，找到第一台有完整信息的
        for cam in cameras:
            server_name = getattr(cam, 'server_name', '')
            device_info = getattr(cam, 'device_info', {}) or {}
            
            # 检查信息是否完整
            has_info = bool(
                device_info.get('user_id') or 
                device_info.get('model') or 
                device_info.get('ip_address')
            )
            
            if has_info:
                # 尝试连接
                if self.cam.connect(server_name):
                    print(f"✓ 成功连接到: {cam.formatted_display_name}")
                    
                    # 设置为当前相机
                    mgr.set_initial_camera(cam)
                    
                    # 同步 Sapera 管理器状态
                    sapera_mgr._current_camera = cam
                    sapera_mgr._last_successful_camera = cam
                    sapera_mgr._connected = True
                    
                    break
```

### 关键改进

1. **不再硬编码连接**:
   - 启动时不自动连接到 `config.SERVER_NAME`
   - 等待扫描完成后再决定连接哪台相机

2. **智能选择相机**:
   - 优先连接有完整信息的相机（有 user_id、model 或 ip_address）
   - 跳过信息不完整的相机（可能被占用或不可用）

3. **状态同步**:
   - 连接成功后，同步 `EnhancedCameraManager` 和 `SaperaCameraManager` 的状态
   - 确保两个管理器的 `current_camera` 一致

4. **详细日志**:
   - 输出每台相机的检查过程
   - 输出连接成功/失败的信息
   - 方便调试和排查问题

## 预期效果

### 修复前

```
启动程序
→ 立即连接到 704 相机（硬编码）
→ 704 相机被占用
→ 扫描时无法获取 704 相机信息
→ 无法切换回 704 相机 ❌
```

### 修复后

```
启动程序
→ 不连接任何相机
→ 扫描所有可用相机
→ 自动连接到第一台可用相机（例如 035）
→ 用户可以在下拉框中切换到任何相机（包括 704）✅
```

## 测试步骤

1. **重新启动程序**，观察日志：
   ```
   [InspectMainWindow] 相机控制器已创建，等待扫描完成后连接...
   [InspectMainWindow] _on_first_scan: 扫描到 2 台相机
   [InspectMainWindow] 检查相机: Genie_M1600_1
     display_name: S1049704 (192.168.11.136)
     has_info: True/False
   [InspectMainWindow] 检查相机: Genie_M1600_2
     display_name: S1024035 (192.168.12.110)
     has_info: True
   [InspectMainWindow] 尝试连接到: S1024035 (192.168.12.110)
   [InspectMainWindow] ✓ 成功连接到: S1024035 (192.168.12.110)
   ```

2. **检查下拉框**：
   - 应该显示所有扫描到的相机
   - 当前相机应该是自动连接的那台

3. **尝试切换相机**：
   - 切换到 704 相机
   - 应该可以成功切换 ✅
   - 切换回 035 相机
   - 应该可以成功切换 ✅

## 进一步优化建议

### 1. 用户选择默认相机

可以在配置文件中添加：
```python
# 默认相机优先级（按顺序尝试连接）
DEFAULT_CAMERA_PRIORITY = [
    "Genie_M1600_2",  # 优先连接 035
    "Genie_M1600_1",  # 其次连接 704
]
```

### 2. 记住上次使用的相机

可以保存用户上次使用的相机，下次启动时优先连接：
```python
# 保存到配置文件或数据库
last_used_camera = "Genie_M1600_2"
```

### 3. 手动选择相机

可以在启动时弹出对话框，让用户选择要连接的相机：
```python
if len(cameras) > 1:
    # 弹出选择对话框
    selected_camera = show_camera_selection_dialog(cameras)
    self.cam.connect(selected_camera.server_name)
```

## 注意事项

1. **config.py 中的 SERVER_NAME**:
   - 现在不再使用这个配置
   - 可以保留作为备用，或者删除

2. **向后兼容**:
   - 如果扫描失败或没有可用相机，程序仍然可以运行
   - 只是无法显示相机画面

3. **性能影响**:
   - 启动时间可能略微增加（等待扫描完成）
   - 但用户体验更好（不会占用相机）

## 修改文件

- `InspectMainWindow.py` - `__init__` 方法和 `_on_first_scan` 回调

## 修改日期

2026-05-13
