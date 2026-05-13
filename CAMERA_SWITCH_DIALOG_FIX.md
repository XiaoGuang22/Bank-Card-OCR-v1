# 相机切换弹窗显示固定内容问题修复

## 问题描述

用户报告：切换相机后，弹窗中显示的相机名称是固定的，不会随着选择的相机而变化。

例如：
- 当前相机：S1049704 (192.168.11.136)
- 用户选择切换到：S1024035 (192.168.12.110)
- 弹窗显示：**相机已切换至 S1049704 (192.168.11.136)** ❌（错误，应该显示 S1024035）

## 根本原因

在 `ui/CameraStatusBar.py` 文件中，`_notify_stale_image()` 方法负责显示相机切换成功的弹窗。

**问题代码流程：**

1. 用户选择相机 → 调用 `_execute_camera_switch(target)`
2. 切换完成 → 调用 `_on_switch_result(success, message, role)`
3. 切换成功 → 调用 `_notify_stale_image()`
4. `_notify_stale_image()` 从 `self._manager.current_camera` 或 `self._sapera_manager.current_camera` 获取当前相机

**问题所在：**
- `_notify_stale_image()` 没有接收目标相机作为参数
- 它依赖 manager 的 `current_camera` 属性
- 在某些情况下，manager 的状态可能还没有更新，或者获取的是旧的相机信息
- 导致弹窗显示的是旧相机的名称，而不是新切换的相机名称

## 修复方案

### 修改 1: `_execute_camera_switch` 方法

将目标相机对象传递给回调函数：

```python
# 修改前
self._manager.switch_camera(
    target=target,
    user_name=self.username,
    user_role=self.role,
    on_result=self._on_switch_result,
)

# 修改后
self._manager.switch_camera(
    target=target,
    user_name=self.username,
    user_role=self.role,
    on_result=lambda success, message: self._on_switch_result(success, message, self.role, target),
)
```

### 修改 2: `_switch_sapera_camera` 方法

在 Sapera 相机切换的回调中也传递目标相机：

```python
# 修改前
self._on_switch_result(success, message, self.role)

# 修改后
self._on_switch_result(success, message, self.role, target)
```

### 修改 3: `_on_switch_result` 方法

添加 `target_camera` 参数并传递给 `_notify_stale_image`：

```python
# 修改前
def _on_switch_result(self, success: bool, message: str, user_role: str = ""):
    ...
    self._notify_stale_image()

# 修改后
def _on_switch_result(self, success: bool, message: str, user_role: str = "", target_camera=None):
    ...
    self._notify_stale_image(target_camera)
```

### 修改 4: `_notify_stale_image` 方法

接收目标相机参数，优先使用传入的相机信息：

```python
def _notify_stale_image(self, target_camera=None):
    """
    FC-17：相机切换成功后，清除主窗口当前显示的旧图像，
    并提示用户重新拍照或确认。
    
    Args:
        target_camera: 目标相机对象，如果提供则使用该相机的名称，否则从manager获取
    """
    ...
    # 获取相机名称：优先使用传入的目标相机，否则从manager获取当前相机
    camera_name = "新相机"
    if target_camera:
        # 使用传入的目标相机
        if hasattr(target_camera, 'formatted_display_name'):
            camera_name = target_camera.formatted_display_name
        elif hasattr(target_camera, 'display_name'):
            camera_name = target_camera.display_name
        else:
            camera_name = str(target_camera)
    else:
        # 从manager获取当前相机（兼容旧代码）
        current_camera = self._manager.current_camera or self._sapera_manager.current_camera
        if current_camera:
            ...
```

## 修复效果

修复后，相机切换弹窗将正确显示：

- 用户选择切换到：S1024035 (192.168.12.110)
- 弹窗显示：**相机已切换至 S1024035 (192.168.12.110)** ✅（正确）

## 技术要点

1. **参数传递**：通过参数传递目标相机对象，而不是依赖全局状态
2. **向后兼容**：`target_camera` 参数设为可选，保持向后兼容性
3. **优先级**：优先使用传入的目标相机，如果没有则回退到从 manager 获取
4. **线程安全**：保持原有的线程安全机制不变

## 测试建议

1. 测试网络相机切换，验证弹窗显示正确的相机名称
2. 测试 Sapera 相机切换，验证弹窗显示正确的相机名称
3. 测试多次连续切换，确保每次都显示正确的相机名称
4. 测试切换失败的情况，确保错误提示正常

## 修改文件

- `ui/CameraStatusBar.py`

## 修改日期

2026-05-13
