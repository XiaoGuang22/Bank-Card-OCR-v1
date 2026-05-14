# 相机缓存验证修复：ping → IsServerAccessible

## 问题

相机物理断开后，软件仍显示该相机为"在线"状态。

### 根因

`sapera_camera_discovery.py` 中 `_get_device_info_cached()` 使用 `ping` 验证缓存中的相机是否仍在
线。`ping` 在相机物理断开后可能因 Windows ARP 缓存或网卡代答而误报可达，导致已拔线的相机
仍出现在下拉框中。

```python
# 改前：ping 验证（不可靠）
ip_address = cached_info.get('ip_address', '').strip()
if ip_address and self._verify_ip_reachable(ip_address):  # ping
    return cached_info  # ← 相机已拔线但 ping 仍成功，误返回缓存
```

## 修改内容

### 文件：camera/sapera_camera_discovery.py

| 改动 | 说明 |
|:---|:---|
| `_get_device_info_cached` 缓存验证 | ping → `SapManager.IsServerAccessible(server_index)` |
| `_verify_ip_reachable()` 方法 | 整体删除（ping 不再使用） |
| `IsServerAccessible` 异常保护 | try/except 包裹，调用失败时走缓存清除逻辑 |

### 新逻辑

```
扫描时查询已缓存相机:
  ├─ 缓存命中 → SapManager.IsServerAccessible(server_index)?
  │     ├─ True  → 返回缓存（相机确实在线）
  │     └─ False → 清除缓存 → _get_device_info 重新读取
  │                 └─ 相机已拔线 → 创建临时设备失败
  │                 └─ 无 IP → 跳过此相机 → 下拉框不显示 ✓
  └─ 缓存未命中 → _get_device_info 读取 → 成功则缓存
```

## 为什么 IsServerAccessible 更可靠

- `ping`：ICMP 协议，仅检测 IP 层可达。Windows ARP 缓存可能保留已断开设备的 MAC 地址，
  导致 ping 误报成功。
- `SapManager.IsServerAccessible(server_index)`：Sapera SDK 通过 GigE Vision 协议直接
  检查相机服务器的控制通道状态，相机断开后立即反映。

---

## 关联修改（前序提交）

前序提交已完成的清理工作：

### managers/camera_manager.py
- 删除 `CameraDiscovery` 导入（旧 TCP 网络扫描器）
- 删除 `DiscoveryMode` 类（NETWORK_ONLY、HYBRID）
- 删除 `_network_discovery` 实例及相关属性
- 删除 `_scan_network_only()`、`_scan_hybrid()` 方法
- 删除 `set_discovery_mode()` 方法
- 简化 `start_scan()` 为仅 Sapera 扫描
- 简化回调签名：`(sapera_cameras, network_cameras)` → `(sapera_cameras)`

### ui/CameraStatusBar.py
- 删除 `_on_scan_complete` 中 sapera + network 合并逻辑
- 删除 `_get_camera_key` 中 `network:ip:port` 分支
- 更新 `_is_camera_more_complete` 注释

### InspectMainWindow.py
- 删除 `_on_first_scan` 的 `network_cameras` 兼容逻辑
- 函数内 `cameras` → `sapera_cameras`
