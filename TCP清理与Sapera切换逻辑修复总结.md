# TCP 清理与 Sapera 切换逻辑修复总结

## 修改概览

删除了项目中废弃的 TCP 网络扫描代码，修复了 `EnhancedCameraManager` 中因 `self._current` 属性名错误导致的潜在崩溃，将死代码中的 Sapera 重连逻辑整合进正常的切换流程。

## 涉及文件

| 文件 | 改动类型 |
|------|----------|
| `camera/camera_discovery.py` | 删除废弃代码 |
| `managers/camera_manager.py` | 删除 TCP + 修复 Sapera 逻辑 + 修复 Bug |
| `ui/CameraStatusBar.py` | 删除网络相机分支 |

---

## 一、camera/camera_discovery.py — 清理详情

### 删除内容

| 删除的代码 | 说明 |
|------------|------|
| `CameraDiscovery` 类 | TCP 局域网扫描器，已废弃，无任何文件引用 |
| `_probe_camera()` | 单 IP TCP 探测，仅被 CameraDiscovery 调用 |
| `_get_local_ips()` | 获取本机 IP，仅被 CameraDiscovery 调用 |
| `_get_local_network_ranges()` | 获取局域网段，仅被 CameraDiscovery 调用 |
| `PROBE_TIMEOUT_MS`、`MAX_WORKERS` | 废弃常量 |
| `ipaddress`、`struct`、`threading`、`concurrent.futures` 等 import | 仅废弃代码使用 |

### 保留内容

| 保留的代码 | 原因 |
|------------|------|
| `CameraInfo` 数据类 | `managers/camera_manager.py` 和 `InspectMainWindow.py` 引用 |
| `DEFAULT_CAMERA_PORT` | `managers/camera_manager.py` 引用 |
| `_find_camera_subnet_ip()` | `InspectMainWindow.py` 引用 |

---

## 二、managers/camera_manager.py — 清理修复详情

### 删除内容

| 删除的代码 | 说明 |
|------------|------|
| `_connect()` 方法 | TCP `IDENTIFY\r\n` 握手验证 + 永远不会执行到的 Sapera 重连死代码 |
| 旧版 `_do_switch()` | 先调 `_connect()` 做 TCP 验证再切换的旧流程 |

### 修复的 Bug

**Bug：`self._current` 属性不存在**

- `__init__` 中定义的是 `self._current_camera`
- 但 `switch_camera()`、`auto_switch_camera()`、`_do_switch()`、`disconnect()` 全部使用了不存在的 `self._current`
- 修复：6 处 `self._current` → `self._current_camera`

### 重写的切换流程

`_do_switch()` 的新逻辑（三步）：

```
1. _match_sapera_camera(target)
   ↓ 从最近一次 Sapera 扫描结果中按 IP 匹配目标相机
   ↓ 找到？
   ├── 否 → 返回失败 "未在扫描结果中找到目标相机 IP"
   └── 是 ↓
2. self._sapera_manager.switch_camera(sapera_target)
   ↓ 委托 SaperaCameraManager 执行硬件切换（Freeze→Destroy→Create→Grab）
   ↓ 成功？
   ├── 是 → 更新 _current_camera，写成功日志，通知状态
   └── 否 ↓
3. 回退到 _last_successful
   └── 再次调用 SaperaCameraManager.switch_camera(fallback)
```

### 新增方法

| 方法 | 说明 |
|------|------|
| `_match_sapera_camera(target)` | 在 `_sapera_discovery.last_results` 中逐条比对 `device_info['ip_address']`，找到 IP 匹配的 `SaperaCameraInfo` |
| `self._sapera_manager` | 引用 `SaperaCameraManager` 实例（从 `get_sapera_camera_manager()` 获取） |

---

## 三、ui/CameraStatusBar.py — 清理详情

| 删除的代码 | 说明 |
|------------|------|
| `_execute_camera_switch()` 中的 `else` 分支 | 网络相机切换路径（调用 `EnhancedCameraManager.switch_camera`），因为所有相机均走 Sapera 通道 |

简化前：
```python
if hasattr(target, 'server_name') and target.server_name:
    # Sapera 相机切换
    ...
else:
    # 网络相机切换 → 已删除
    self._manager.switch_camera(...)
```

简化后：
```python
def _execute_camera_switch(self, target):
    """执行相机切换（所有相机均为 Sapera 相机）"""
    threading.Thread(
        target=self._switch_sapera_camera,
        args=(target,),
        daemon=True
    ).start()
```

---

## 当前相机系统架构

```
UI: CameraStatusBar ──扫描──→ EnhancedCameraManager ──→ SaperaCameraDiscovery
    │                                                         │
    │                                                         ├── SapManager.GetServerCount()
    │                                                         ├── SapManager.GetServerName(i)
    │                                                         ├── IsServerAccessible(i)
    │                                                         └── _get_device_info() 读取 GenICam 特征
    │                                                              ├── DeviceUserID     → 名称
    │                                                              ├── DeviceSerialNumber → 序列号
    │                                                              ├── DeviceModelName   → 型号
    │                                                              └── GevCurrentIPAddress → IP
    │
    └──切换──→ SaperaCameraManager ──→ InspectMainWindow.CameraController
                    │                          │
                    │                          ├── SapAcqDevice (设备对象)
                    │                          ├── SapBufferWithTrash (图像缓冲)
                    │                          └── SapAcqDeviceToBuf (传输对象)
                    │
                    └── FC-10 标准切换流程:
                         1. Freeze()    停止采集
                         2. Destroy()   销毁旧设备
                         3. Create()    创建新设备
                         4. Create()    重建缓冲传输
                         5. Grab()      开始新采集
```

## 修改日期

2026-05-16
