# 相机刷新和断开检测修复

## 问题描述

当相机被物理拔掉后，刷新相机列表时仍然显示已断开的相机。

**现象**：
- 拔掉 `192.168.11.136` 的相机
- 点击"刷新"按钮
- 下拉框中仍然显示 `S1049704 (192.168.11.136)`

## 根本原因

1. **Ping 发现逻辑**：代码中使用 `ping` 命令来"发现"相机的IP地址
2. **网络缓存**：即使相机已拔掉，短时间内 ping 可能仍然返回成功（ARP缓存）
3. **旧结果未清空**：扫描时没有清空上次的扫描结果

## 解决方案

### 1. 移除 Ping 发现逻辑

**文件**: `camera/sapera_camera_discovery.py`

**修改内容**：
- 移除所有通过 `ping` 命令发现IP的代码
- 只依赖 Sapera SDK 的 `GevCurrentIPAddress` 特征
- 如果无法获取IP地址，跳过该相机（不显示在列表中）

**修改前**：
```python
# 对于已知的相机尝试ping常见IP
if not ip_address and server_name == "Genie_M1600_1":
    known_ips = ["192.168.11.136", "192.168.11.110", ...]
    for test_ip in known_ips:
        result = subprocess.run(['ping', '-n', '1', '-w', '1000', test_ip], ...)
        if result.returncode == 0:
            ip_address = test_ip
            break
```

**修改后**：
```python
# 如果没有IP地址，跳过这个相机（可能已断开连接）
if not ip_address:
    print(f"[Sapera] 跳过无IP地址的相机: {server_name}")
    continue
```

### 2. 扫描时清空旧结果

**文件**: `camera/sapera_camera_discovery.py`

**修改内容**：
- 在 `_do_scan` 方法开始时清空 `_last_results`
- 确保每次扫描都是全新的结果

```python
def _do_scan(self, ...):
    """执行实际的扫描操作"""
    try:
        found_cameras = []
        
        # ★★★ 清空上次的扫描结果，避免显示已断开的相机 ★★★
        self._last_results = []
        
        # ... 后续扫描逻辑
```

### 3. UI 刷新时清空列表

**文件**: `ui/CameraStatusBar.py`

**修改内容**：
- 在 `_on_refresh_click` 方法中清空 `_camera_list`
- 确保刷新时不会保留旧的相机信息

```python
def _on_refresh_click(self):
    """点击刷新按钮：触发重新扫描"""
    # ★★★ 清空当前列表，避免显示已断开的相机 ★★★
    self._camera_list = []
    self._combo["values"] = ["扫描中…"]
    self._combo_var.set("扫描中…")
    
    # ... 启动扫描
```

## 工作原理

### 扫描流程

1. **用户点击刷新**
   - 清空 `_camera_list`
   - 显示"扫描中…"

2. **Sapera SDK 扫描**
   - 清空 `_last_results`
   - 调用 `SapManager.GetServerCount()` 获取服务器数量
   - 遍历每个服务器

3. **相机信息获取**
   - 尝试创建 `SapAcqDevice` 对象
   - 读取 `GevCurrentIPAddress` 特征获取IP
   - **如果无法获取IP，跳过该相机**

4. **结果返回**
   - 只返回有IP地址的相机
   - UI 更新下拉框

### 相机断开检测

- **物理断开**：`SapManager.GetServerCount()` 不再返回该服务器
- **设备占用**：`SapAcqDevice.Create()` 失败，无法获取IP
- **网络断开**：`GevCurrentIPAddress` 特征读取失败

以上任何情况，相机都不会出现在扫描结果中。

## 测试场景

### 场景 1：正常扫描
1. 启动程序
2. 扫描发现相机：`S1024035 (192.168.11.110)`
3. 下拉框显示该相机

### 场景 2：拔掉相机后刷新
1. 拔掉相机的网线或电源
2. 点击"刷新"按钮
3. 扫描完成后，下拉框中**不再显示**该相机
4. 如果没有其他相机，显示"无可用相机"

### 场景 3：插入新相机后刷新
1. 插入新相机
2. 点击"刷新"按钮
3. 扫描完成后，下拉框中显示新相机

### 场景 4：多相机环境
1. 连接多台相机
2. 拔掉其中一台
3. 点击"刷新"按钮
4. 下拉框中只显示仍然连接的相机

## 注意事项

1. **IP 地址获取**：
   - 只依赖 Sapera SDK 的 `GevCurrentIPAddress` 特征
   - 不使用 ping、网络扫描等外部方法
   - 确保显示的都是真实连接的相机

2. **设备占用**：
   - 如果相机被 CamExpert 占用，可能无法获取IP
   - 建议关闭 CamExpert 后再使用本程序

3. **刷新频率**：
   - 不要频繁点击刷新按钮
   - 每次扫描需要几秒钟时间

4. **网络延迟**：
   - 拔掉相机后，可能需要等待几秒钟
   - Sapera SDK 需要时间检测设备断开

## 相关文件

- `camera/sapera_camera_discovery.py` - 相机发现逻辑
- `ui/CameraStatusBar.py` - 相机状态栏UI
- `CAMERA_REFRESH_FIX.md` - 本文档

## 版本历史

- **2024-05-11**: 初始版本，修复相机刷新和断开检测问题
