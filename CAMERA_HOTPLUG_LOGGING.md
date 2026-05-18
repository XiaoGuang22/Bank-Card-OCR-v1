# 相机热插拔日志记录功能

## 功能描述

实现 ServerNotify 事件监听，自动记录相机插拔日志，但**不自动更新下拉框**，保持手动刷新的方式。

### 设计原则
- ✅ **仅记录日志**：相机上线/离线时自动记录到操作日志
- ✅ **不打断用户**：不弹窗、不自动刷新下拉框
- ✅ **保持手动刷新**：用户需要点击【刷新】按钮才能更新相机列表

---

## 实现方案

### 1. 事件注册（sapera_camera_discovery.py）

#### 添加回调列表
```python
def __init__(self):
    # ...
    # ★★★ ServerNotify 事件回调列表（仅用于日志记录）★★★
    self._server_notify_callbacks: List[Callable[[str, str], None]] = []
    self._server_notify_registered = False
```

#### 注册方法
```python
def register_server_notify_callback(self, callback: Callable[[str, str], None]):
    """
    注册 ServerNotify 事件回调（仅用于日志记录）
    
    Args:
        callback: 回调函数，接收 (event_type, server_name)
                 event_type: 'added' 或 'removed'
                 server_name: 服务器名称
    """
    self._server_notify_callbacks.append(callback)
    
    if not self._server_notify_registered and SAPERA_AVAILABLE:
        self._register_server_notify_event()
```

#### 事件处理
```python
def _register_server_notify_event(self):
    """注册 Sapera ServerNotify 事件（仅用于日志记录）"""
    def _on_server_notify(sender, args):
        # 获取服务器名称和事件类型
        server_name = ...
        event_type = 'added' or 'removed'
        
        # 过滤系统设备
        if server_name.startswith("System"):
            return
        
        # 触发所有注册的回调
        for callback in self._server_notify_callbacks:
            callback(event_type, server_name)
    
    # 注册事件
    SapManager.ServerNotify += _on_server_notify
```

---

### 2. 日志记录（InspectMainWindow.py）

#### 注册日志记录器
```python
def __init__(self, root, username="admin", role="管理员"):
    # ...
    # ★★★ 注册 ServerNotify 事件回调（仅用于日志记录）★★★
    self._register_server_notify_logger()
```

#### 日志记录器实现
```python
def _register_server_notify_logger(self):
    """
    注册 ServerNotify 事件回调，仅用于记录相机插拔日志
    不自动更新下拉框，保持手动刷新的方式
    """
    from camera.sapera_camera_discovery import get_sapera_discovery
    discovery = get_sapera_discovery()
    
    def _on_camera_hotplug(event_type: str, server_name: str):
        # 获取相机显示名称
        camera_display = server_name
        for cam in discovery.last_results:
            if getattr(cam, 'server_name', '') == server_name:
                camera_display = cam.formatted_display_name
                break
        
        # 记录日志
        operation_action = "camera_connected" if event_type == "added" else "camera_disconnected"
        
        self._audit(
            operation_action=operation_action,
            target_object=f"{camera_display} ({server_name})",
            operation_result="成功"
        )
    
    # 注册回调
    discovery.register_server_notify_callback(_on_camera_hotplug)
```

---

### 3. 日志类型定义（AuditLogPanel.py）

```python
_ACTION_ZH = {
    # ...
    "camera_connected":     "相机上线",
    "camera_disconnected":  "相机离线",
}
```

---

## 日志格式

### 相机上线日志
```
时间: 2026-05-17 15:30:45
用户: system
角色: 系统
操作类型: 硬件事件
操作动作: 相机上线
目标对象: S1024035 (192.168.12.220) (Genie_M1600_1)
操作结果: 成功
```

### 相机离线日志
```
时间: 2026-05-17 15:35:20
用户: system
角色: 系统
操作类型: 硬件事件
操作动作: 相机离线
目标对象: S1024035 (192.168.12.220) (Genie_M1600_1)
操作结果: 成功
```

---

## 使用场景

### 场景1：相机意外断电
```
[用户正在使用相机 A]
1. 相机 A 断电
2. ServerNotify 事件触发
3. 自动记录日志：相机离线
4. 用户界面不变，继续显示当前状态
5. 用户点击【刷新】后，下拉框更新
```

### 场景2：新相机接入
```
[系统运行中]
1. 新相机 B 接入网络
2. ServerNotify 事件触发
3. 自动记录日志：相机上线
4. 用户界面不变
5. 用户点击【刷新】后，下拉框显示新相机
```

### 场景3：相机网络故障
```
[相机 A 正在使用]
1. 网线松动，相机离线
2. 自动记录日志：相机离线
3. 网线重新插好，相机上线
4. 自动记录日志：相机上线
5. 用户点击【刷新】后恢复连接
```

---

## 优势

### 1. 不打断用户操作
- ❌ 不弹窗提示
- ❌ 不自动刷新下拉框
- ❌ 不自动切换相机
- ✅ 仅静默记录日志

### 2. 完整的审计追溯
- ✅ 记录所有相机插拔事件
- ✅ 包含时间戳、相机标识
- ✅ 可用于故障排查

### 3. 保持用户习惯
- ✅ 保留手动刷新按钮
- ✅ 用户主动控制何时更新
- ✅ 避免意外的界面变化

---

## 与 ServerNotify 回退版本的区别

| 功能 | 回退版本 | 当前版本 |
|:---|:---:|:---:|
| ServerNotify 事件注册 | ❌ 已移除 | ✅ 已实现 |
| 自动更新下拉框 | ❌ 无 | ❌ 不实现 |
| 状态栏提示 | ❌ 无 | ❌ 不实现 |
| 日志记录 | ❌ 无 | ✅ **已实现** |
| 手动刷新按钮 | ✅ 保留 | ✅ 保留 |

---

## 测试验证

### 测试步骤
1. **启动软件**：
   - 观察控制台输出
   - 确认 `[InspectMainWindow] ServerNotify 日志记录器已注册`

2. **拔掉相机网线**：
   - 等待几秒
   - 打开操作日志面板
   - 查看是否有"相机离线"记录

3. **重新插上网线**：
   - 等待几秒
   - 刷新操作日志
   - 查看是否有"相机上线"记录

4. **验证不打断用户**：
   - 相机插拔时，界面不应有任何变化
   - 下拉框不应自动更新
   - 不应弹出任何提示

---

## 注意事项

### 1. 事件可能不触发
- 某些 Sapera SDK 版本可能不支持 ServerNotify 事件
- 如果事件不触发，不影响其他功能
- 控制台会显示注册失败的提示

### 2. 日志用户为 system
- 相机插拔是硬件事件，不是用户操作
- 日志中的用户名为当前登录用户
- 但操作类型标记为"硬件事件"

### 3. 延迟问题
- ServerNotify 事件可能有延迟（几秒到几十秒）
- 不适合实时监控
- 仅用于事后审计追溯

---

## 相关文件

- `camera/sapera_camera_discovery.py` - 事件注册和回调管理
- `InspectMainWindow.py` - 日志记录器实现
- `ui/AuditLogPanel.py` - 日志类型定义
- `managers/audit_log_manager.py` - 日志存储

---

## 总结

通过实现 ServerNotify 事件监听，系统现在可以：
1. ✅ 自动记录相机插拔日志
2. ✅ 不打断用户操作
3. ✅ 保持手动刷新的方式
4. ✅ 提供完整的审计追溯

这是一个**轻量级、非侵入式**的实现，既满足了日志记录的需求，又不影响用户体验。
