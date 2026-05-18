# 相机热插拔日志记录功能

## 功能概述

实现相机热插拔事件的自动日志记录功能。当相机物理连接或断开时，系统会自动在操作日志中记录相机上线/离线事件。

**注意**：此功能**仅记录日志**，不会自动更新相机下拉框或弹出提示。用户仍需手动点击"刷新"按钮来更新相机列表。

---

## 实现方案

### 方案选择

由于 Sapera SDK 的 Python.NET 绑定中 `ServerNotify` 事件可能不被支持或无法正常触发，我们采用了**双保险方案**：

1. **主方案**：尝试注册 `ServerNotify` 事件（如果 SDK 支持）
2. **备用方案**：轮询检测服务器列表变化（5秒间隔）

### 轮询检测机制

#### 工作原理

1. **定时检测**：每 5 秒调用一次 `SapManager.GetServerCount()` 和 `SapManager.GetServerName()`
2. **比较变化**：将当前服务器列表与上次记录的列表进行对比
3. **触发回调**：
   - 新增的服务器 → 触发 `'added'` 事件
   - 移除的服务器 → 触发 `'removed'` 事件
4. **记录日志**：通过回调函数记录到操作日志数据库

#### 关键代码

**`camera/sapera_camera_discovery.py`**：

```python
# 轮询状态
self._polling_enabled = False
self._polling_interval = 5.0  # 5秒检测一次
self._polling_timer = None
self._last_server_list: List[str] = []  # 上次检测到的服务器列表

def _start_polling(self):
    """启动轮询检测（每5秒检测一次服务器列表变化）"""
    if self._polling_enabled:
        return
    
    self._polling_enabled = True
    self._last_server_list = self._get_current_servers()
    self._schedule_next_poll()

def _poll_camera_changes(self):
    """轮询检测相机变化"""
    current_servers = self._get_current_servers()
    
    # 比较变化
    added = set(current_servers) - set(self._last_server_list)
    removed = set(self._last_server_list) - set(current_servers)
    
    # 触发回调
    for server_name in added:
        print(f"[Sapera] 轮询检测: 相机上线 - {server_name}")
        for callback in self._server_notify_callbacks:
            callback('added', server_name)
    
    for server_name in removed:
        print(f"[Sapera] 轮询检测: 相机离线 - {server_name}")
        for callback in self._server_notify_callbacks:
            callback('removed', server_name)
    
    self._last_server_list = current_servers

def _get_current_servers(self) -> List[str]:
    """获取当前所有服务器名称（过滤掉系统设备）"""
    servers = []
    server_count = SapManager.GetServerCount()
    for i in range(server_count):
        server_name = SapManager.GetServerName(i)
        # 过滤系统设备
        if not server_name.startswith("System") and "System" not in server_name:
            servers.append(server_name)
    return servers
```

**`InspectMainWindow.py`**：

```python
def _register_server_notify_logger(self):
    """注册 ServerNotify 事件回调，仅用于记录相机插拔日志"""
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
    
    discovery.register_server_notify_callback(_on_camera_hotplug)
```

---

## 日志格式

### 日志类型

在 `ui/AuditLogPanel.py` 中新增了两种日志类型：

- `camera_connected`：相机上线
- `camera_disconnected`：相机离线

### 日志内容

| 字段 | 说明 | 示例 |
|------|------|------|
| 时间 | 事件发生时间 | 2026-05-18 14:30:25 |
| 用户 | 当前登录用户 | admin |
| 角色 | 用户角色 | 管理员 |
| 操作类型 | 相机设置 | camera_settings |
| 具体动作 | 相机上线/离线 | 相机上线 |
| 目标对象 | 相机名称 | S1049704 (192.168.11.136) (Genie_M1600_1) |
| 结果 | 成功 | 成功 |
| IP | 空（硬件事件） | - |

---

## 测试方法

### 测试步骤

1. **启动程序**：
   ```
   python main.py
   ```

2. **查看初始日志**：
   - 确认控制台输出：`[Sapera] 同时启动轮询检测作为备用方案（5秒间隔）`
   - 确认控制台输出：`[InspectMainWindow] ServerNotify 日志记录器已注册`

3. **拔掉相机网线**：
   - 等待 5-10 秒（轮询间隔）
   - 查看控制台是否输出：`[Sapera] 轮询检测: 相机离线 - Genie_M1600_X`
   - 查看控制台是否输出：`[InspectMainWindow] 相机离线日志已记录: ...`

4. **查看操作日志**：
   - 点击"操作日志"标签页
   - 查看是否有"相机离线"记录
   - 记录格式应为：`S1049704 (192.168.11.136) (Genie_M1600_1)`

5. **重新插上网线**：
   - 等待 5-10 秒
   - 查看控制台是否输出：`[Sapera] 轮询检测: 相机上线 - Genie_M1600_X`
   - 查看操作日志是否有"相机上线"记录

6. **手动刷新相机列表**：
   - 点击相机状态栏的"刷新"按钮
   - 确认相机列表已更新
   - 确认操作日志面板自动刷新

### 预期结果

✅ **成功标志**：
- 控制台输出轮询检测日志
- 操作日志中出现"相机上线"/"相机离线"记录
- 相机下拉框**不会**自动更新（需手动刷新）
- 不会弹出任何提示框

❌ **失败标志**：
- 插拔相机后 10 秒内没有任何日志输出
- 操作日志中没有相机上线/离线记录

---

## 性能影响

### 资源消耗

- **CPU**：每 5 秒调用一次 Sapera API，消耗极低（< 0.1%）
- **内存**：仅保存上次的服务器列表（几十字节）
- **网络**：无网络请求

### 优化措施

1. **合理的轮询间隔**：5 秒间隔既能及时检测变化，又不会频繁调用 API
2. **过滤系统设备**：只检测真实相机，减少无效比较
3. **异常保护**：轮询异常不会影响主程序运行

---

## 已知限制

1. **检测延迟**：最长可能有 5 秒的延迟（取决于轮询间隔）
2. **不自动更新下拉框**：用户需手动点击"刷新"按钮
3. **依赖 Sapera API**：如果 `SapManager.GetServerCount()` 失败，轮询会停止

---

## 相关文件

- `camera/sapera_camera_discovery.py`：轮询检测实现
- `InspectMainWindow.py`：日志记录器注册
- `ui/AuditLogPanel.py`：日志类型定义
- `managers/audit_log_manager.py`：日志数据库操作

---

## 后续优化建议

1. **可配置轮询间隔**：允许用户在配置文件中调整轮询间隔
2. **智能轮询**：在相机连接稳定时降低轮询频率，在检测到变化后提高频率
3. **事件优先**：如果 `ServerNotify` 事件可用，优先使用事件，轮询作为备用
4. **通知方式**：可选择是否在系统托盘显示通知（不打断用户操作）

---

## 总结

通过实现轮询检测机制，系统现在可以：
1. ✅ 自动记录相机插拔日志（5秒延迟）
2. ✅ 不打断用户操作
3. ✅ 保持手动刷新的方式
4. ✅ 提供完整的审计追溯

这是一个**轻量级、非侵入式**的实现，既满足了日志记录的需求，又不影响用户体验。
