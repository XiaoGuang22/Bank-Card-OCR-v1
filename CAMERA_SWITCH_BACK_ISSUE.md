# 相机切换回原相机失败问题调查

## 问题描述

用户报告：
1. 电脑同时接了两台相机：
   - **S1049704 (192.168.11.136)** - Genie_M1600_1
   - **S1024035 (192.168.12.110)** - Genie_M1600_2

2. 运行软件时默认是 704 相机
3. 切换到 035 相机 → **成功** ✅
4. 尝试切换回 704 相机 → **失败** ❌，提示"已是当前连接的相机，无需切换"

## 日志分析

从启动日志可以看出：

```
[Sapera] 无法创建设备 Genie_M1600_1（可能被占用）
[Sapera] 使用配置名称: S1049704 for Genie_M1600_1
[Sapera] 通过ping发现 Genie_M1600_1 的IP: 192.168.11.136

[Sapera] 设备 Genie_M1600_2 信息:
用户名: S1024035
IP地址: 192.168.12.110
[Sapera] 使用相机 Device User ID: S1024035 for Genie_M1600_2

[SaperaCameraManager] 开始切换相机: None -> S1024035 (192.168.12.110)
```

**关键发现：**
1. **S1049704 (Genie_M1600_1) 启动时无法创建设备**（可能被占用）
2. **实际连接的是 S1024035 (Genie_M1600_2)**
3. 日志显示 `None -> S1024035`，说明启动时没有成功连接到 S1049704

## 问题根源推测

### 可能原因 1：状态不一致

`SaperaCameraManager._current_camera` 的状态可能与实际连接状态不一致：

- **实际情况**：启动时连接的是 S1024035
- **可能的状态**：`_current_camera` 被错误地设置为 S1049704（或者为 None）

当用户尝试切换回 S1049704 时：
1. 代码检查 `current == target`
2. 由于某种原因，认为当前相机就是 S1049704
3. 返回"已是当前相机，无需切换"

### 可能原因 2：相机对象比较问题

`SaperaCameraInfo.__eq__` 方法主要通过 `server_name` 比较：

```python
def __eq__(self, other):
    if not isinstance(other, SaperaCameraInfo):
        return False
    
    # 优先比较服务器名（最可靠的标识）
    if self.server_name and other.server_name:
        if self.server_name == other.server_name:
            return True
    
    # 其次比较序列号
    ...
```

如果两个 `SaperaCameraInfo` 对象的 `server_name` 都是 `Genie_M1600_1`，即使一个是旧的（未连接）、一个是新的（扫描结果），它们也会被认为相等。

### 可能原因 3：扫描结果包含未连接的相机

相机扫描可能会返回所有检测到的相机，包括那些无法连接的相机。当用户选择 S1049704 时：
- 下拉框中的 S1049704 来自扫描结果
- 但实际上这台相机无法连接（被占用）
- `_current_camera` 可能保存着旧的 S1049704 信息

## 调试方案

我已经在以下位置添加了调试信息：

### 1. `ui/CameraStatusBar.py` - `_on_switch_click` 方法

```python
# 添加调试信息
print(f"[CameraStatusBar] 切换相机检查:")
print(f"  当前相机: {current}")
print(f"  目标相机: {target}")
if current:
    print(f"  当前相机 server_name: {getattr(current, 'server_name', 'N/A')}")
    print(f"  当前相机 display_name: {getattr(current, 'display_name', 'N/A')}")
    print(f"  当前相机 formatted_display_name: {getattr(current, 'formatted_display_name', 'N/A')}")
if target:
    print(f"  目标相机 server_name: {getattr(target, 'server_name', 'N/A')}")
    print(f"  目标相机 display_name: {getattr(target, 'display_name', 'N/A')}")
    print(f"  目标相机 formatted_display_name: {getattr(target, 'formatted_display_name', 'N/A')}")
print(f"  相等性检查: {current == target if current else 'current is None'}")
```

### 2. `camera/sapera_camera_manager.py` - `switch_camera` 方法

```python
print(f"[SaperaCameraManager] switch_camera 检查:")
print(f"  当前相机: {self._current_camera}")
print(f"  目标相机: {target_camera}")
if self._current_camera:
    print(f"  当前相机 server_name: {self._current_camera.server_name}")
    print(f"  当前相机 formatted_display_name: {self._current_camera.formatted_display_name}")
print(f"  目标相机 server_name: {target_camera.server_name}")
print(f"  目标相机 formatted_display_name: {target_camera.formatted_display_name}")
print(f"  相等性检查: {self._current_camera == target_camera if self._current_camera else 'current is None'}")
```

## 下一步操作

请重新运行程序，并执行以下操作：

1. **启动程序** - 观察启动日志，确认实际连接的相机
2. **切换到 035** - 观察调试信息
3. **尝试切换回 704** - 观察调试信息，特别关注：
   - `current` 和 `target` 的值
   - 它们的 `server_name`
   - 相等性检查的结果

将完整的日志发给我，我会根据调试信息确定问题的根本原因并提供修复方案。

## 可能的修复方案

根据调试结果，可能的修复方案包括：

### 方案 1：改进相机状态同步

确保 `_current_camera` 始终反映实际连接的相机：
- 连接成功后才设置 `_current_camera`
- 连接失败时清除 `_current_camera`

### 方案 2：改进相机可用性检查

在切换前检查目标相机是否真的可用：
- 尝试创建 `SapAcqDevice` 测试连接
- 如果无法连接，提示用户相机不可用

### 方案 3：改进相等性判断

不仅比较 `server_name`，还要考虑连接状态：
- 只有当前真正连接的相机才算"当前相机"
- 扫描结果中的相机不算"当前相机"

## 修改文件

- `ui/CameraStatusBar.py` - 添加调试信息
- `camera/sapera_camera_manager.py` - 添加调试信息

## 修改日期

2026-05-13
