# 相机切换管理器状态判断问题修复

## 问题描述

在使用 Sapera 相机时，切换相机出现状态判断错误：
- 启动时连接 704 相机 ✓
- 切换到 035 相机 ✓
- 切换回 704 相机 ✗ 显示"已是当前连接的相机，无需切换"

## 问题分析

### 症状
```
[启动] 连接 704 → 成功
[切换] 704 → 035 → 成功
[切换] 035 → 704 → 失败（显示已是当前相机）
```

### 根本原因

在 `CameraStatusBar._on_switch_click()` 方法中，获取当前相机的逻辑有问题：

```python
# ❌ 错误的逻辑
current = self._manager.current_camera or self._sapera_manager.current_camera
```

**问题**：
1. `self._manager` 是 `EnhancedCameraManager`（网络相机管理器）
2. `self._sapera_manager` 是 `SaperaCameraManager`（Sapera相机管理器）
3. 使用 `or` 逻辑时，如果 `self._manager.current_camera` 不为 None，就会使用它
4. 但是在使用 Sapera 相机时，应该使用 `self._sapera_manager.current_camera`

### 详细流程分析

#### 启动时（连接 704）
```python
# SaperaCameraManager
_current_camera = SaperaCameraInfo(server_name='Genie_M1600_1', ...)

# EnhancedCameraManager
_current_camera = None  # 或者可能是旧值
```

#### 第一次切换（704 → 035）
```python
# 切换前
current = self._manager.current_camera or self._sapera_manager.current_camera
# 如果 _manager.current_camera 是 704，就会使用它
# 导致判断：704 != 035，允许切换

# 切换后
# SaperaCameraManager._current_camera 更新为 035
# 但 EnhancedCameraManager._current_camera 可能还是 704
```

#### 第二次切换（035 → 704）
```python
# 切换前
current = self._manager.current_camera or self._sapera_manager.current_camera
# 如果 _manager.current_camera 还是 704（旧值）
# 判断：704 == 704，拒绝切换！❌
```

## 解决方案

### 修复策略

**根据目标相机类型选择正确的管理器**：
- 如果目标是 Sapera 相机，使用 `self._sapera_manager.current_camera`
- 如果目标是网络相机，使用 `self._manager.current_camera`

### 修改的代码

**文件**：`ui/CameraStatusBar.py`

**方法**：`_on_switch_click()`

#### 修改前
```python
# 若目标与当前相同，忽略
current = self._manager.current_camera or self._sapera_manager.current_camera

if current and current == target:
    messagebox.showinfo("切换相机", "已是当前连接的相机，无需切换", parent=self)
    return
```

#### 修改后
```python
# ★★★ 修复：根据目标相机类型选择正确的管理器 ★★★
# 判断目标是 Sapera 相机还是网络相机
is_sapera_target = hasattr(target, 'server_name') and target.server_name

# 获取当前相机（从正确的管理器）
if is_sapera_target:
    current = self._sapera_manager.current_camera
else:
    current = self._manager.current_camera

if current and current == target:
    messagebox.showinfo("切换相机", "已是当前连接的相机，无需切换", parent=self)
    return
```

## 工作原理

### 判断逻辑

1. **识别目标相机类型**：
   ```python
   is_sapera_target = hasattr(target, 'server_name') and target.server_name
   ```
   - Sapera 相机有 `server_name` 属性
   - 网络相机没有 `server_name` 属性

2. **选择正确的管理器**：
   ```python
   if is_sapera_target:
       current = self._sapera_manager.current_camera
   else:
       current = self._manager.current_camera
   ```

3. **比较相机**：
   ```python
   if current and current == target:
       # 已是当前相机，拒绝切换
   ```

### 优势

- **类型安全**：根据目标相机类型选择管理器，避免混淆
- **状态准确**：总是从正确的管理器获取当前相机状态
- **逻辑清晰**：明确区分 Sapera 相机和网络相机

## 测试验证

### 测试场景

1. **启动并连接 704**：
   - 应该成功连接
   - `_sapera_manager.current_camera` = 704

2. **切换到 035**：
   - 目标是 Sapera 相机
   - 从 `_sapera_manager` 获取当前相机（704）
   - 704 != 035，允许切换
   - 切换成功后 `_sapera_manager.current_camera` = 035

3. **切换回 704**：
   - 目标是 Sapera 相机
   - 从 `_sapera_manager` 获取当前相机（035）
   - 035 != 704，允许切换 ✓
   - 切换成功后 `_sapera_manager.current_camera` = 704

4. **再次尝试切换到 704**：
   - 目标是 Sapera 相机
   - 从 `_sapera_manager` 获取当前相机（704）
   - 704 == 704，拒绝切换（正确行为）

### 预期日志

```
[CameraStatusBar] 切换相机检查:
  当前相机: SaperaCameraInfo(server_name='Genie_M1600_2', ...)
  目标相机: SaperaCameraInfo(server_name='Genie_M1600_1', ...)
  当前相机 server_name: Genie_M1600_2
  目标相机 server_name: Genie_M1600_1
  相等性检查: False  ← 允许切换
```

## 相关文件

- `ui/CameraStatusBar.py` - 主要修改文件
- `camera/sapera_camera_manager.py` - Sapera 相机管理器
- `managers/camera_manager.py` - 网络相机管理器

## 注意事项

1. **管理器独立性**：两个管理器（Sapera 和网络）应该独立维护各自的状态
2. **类型识别**：通过 `server_name` 属性区分相机类型
3. **状态同步**：确保管理器的 `current_camera` 在切换后正确更新

## 总结

通过根据目标相机类型选择正确的管理器来获取当前相机状态，成功解决了相机切换时的状态判断错误问题。核心思路是：
- **Sapera 相机** → 使用 `_sapera_manager.current_camera`
- **网络相机** → 使用 `_manager.current_camera`

这样确保了状态判断的准确性，避免了管理器之间的状态混淆。
