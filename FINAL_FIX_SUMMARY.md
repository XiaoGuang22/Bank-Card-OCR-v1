# 相机去重和IP显示最终修复总结

## 修复的问题

1. ✅ **相机重复显示问题**：下拉框显示两条相同的相机记录
2. ✅ **IP地址显示问题**：显示服务器名而不是IP地址
3. ✅ **相机断开检测问题**：拔掉相机后仍然显示

## 最终解决方案

### 1. 相机相等性比较（去重的基础）

**文件**: `camera/sapera_camera_discovery.py`

**修改**: `SaperaCameraInfo.__eq__` 方法

```python
def __eq__(self, other):
    if not isinstance(other, SaperaCameraInfo):
        return False
    
    # 优先比较服务器名（最可靠的标识）
    if self.server_name and other.server_name:
        if self.server_name == other.server_name:
            return True
    
    # 其次比较序列号
    device_info = self.device_info or {}
    other_device_info = other.device_info or {}
    
    self_serial = device_info.get('serial', '')
    other_serial = other_device_info.get('serial', '')
    
    if self_serial and other_serial:
        return self_serial == other_serial
    
    return False
```

**原理**: 确保同一台相机的不同版本（有IP/无IP）被识别为同一个对象。

### 2. IP地址获取（多层后备方案）

**文件**: `camera/sapera_camera_discovery.py`

**修改**: `_do_scan` 方法中的IP获取逻辑

```python
# 优先级顺序：
# 1. 从 Sapera SDK 读取 GevCurrentIPAddress
# 2. 从主程序的 CameraController 获取（如果是当前连接的相机）
# 3. 通过 ping 已知IP段发现
# 4. 通过网络扫描匹配
# 5. 使用服务器名作为标识
```

**关键代码**:
```python
# 方法1：从设备读取
ip_address = device_info_dict.get('ip_address', '').strip()

# 方法2：从主程序获取
if not ip_address:
    from InspectMainWindow import CameraController
    cam_ctrl = CameraController()
    if cam_ctrl.current_server_name == server_name:
        # 从已连接的设备获取IP
        ...

# 方法3：ping 发现
if not ip_address:
    known_ips = ["192.168.11.136", "192.168.11.110", ...]
    for test_ip in known_ips:
        result = subprocess.run(['ping', '-n', '1', '-w', '1000', test_ip], ...)
        if result.returncode == 0:
            ip_address = test_ip
            break

# 方法4：网络扫描
if not ip_address:
    from camera.ip_discovery_helper import get_cached_camera_ips
    ...
```

### 3. 智能去重逻辑

**文件**: `ui/CameraStatusBar.py`

**修改**: `_update_camera_list` 方法

```python
def _update_camera_list(self, cameras: list):
    # 使用字典进行去重，key 为 server_name
    camera_dict = {}
    
    # 首先添加当前连接的相机
    current = self._manager.current_camera or self._sapera_manager.current_camera
    if current:
        key = self._get_camera_key(current)
        if key:
            camera_dict[key] = current
    
    # 然后添加新扫描的相机，如果已存在则替换（新版本优先）
    if cameras:
        for camera in cameras:
            key = self._get_camera_key(camera)
            if key:
                if key in camera_dict:
                    existing = camera_dict[key]
                    # 如果新相机有IP而旧相机没有，用新相机替换
                    if self._is_camera_more_complete(camera, existing):
                        camera_dict[key] = camera
                else:
                    camera_dict[key] = camera
    
    self._camera_list = list(camera_dict.values())
    # ... 更新UI
```

### 4. 扫描时清空旧结果

**文件**: `camera/sapera_camera_discovery.py`

**修改**: `_do_scan` 方法开始时清空

```python
def _do_scan(self, ...):
    try:
        found_cameras = []
        
        # ★★★ 清空上次的扫描结果，避免显示已断开的相机 ★★★
        self._last_results = []
        
        # ... 后续扫描逻辑
```

### 5. 格式化显示名称

**文件**: `camera/sapera_camera_discovery.py`

**修改**: `formatted_display_name` 属性

```python
@property
def formatted_display_name(self) -> str:
    # 检查是否已经格式化且包含真实IP
    if self.display_name and '(' in self.display_name and ')' in self.display_name:
        import re
        ip_pattern = r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'
        if re.search(ip_pattern, self.display_name):
            return self.display_name
    
    # 获取设备信息
    device_info = self.device_info or {}
    ip_address = device_info.get('ip_address', '').strip()
    
    # 确定相机名称
    user_id = device_info.get('user_id', '').strip()
    model = device_info.get('model', '').strip()
    
    if user_id and not user_id.isdigit() and len(user_id) < 20:
        name = user_id
    elif model and not model.isdigit() and len(model) < 20:
        name = model
    else:
        if self.display_name and self.display_name != self.server_name:
            name = self.display_name
        else:
            name = self.server_name
    
    # 格式化显示
    if ip_address:
        return f"{name} ({ip_address})"
    else:
        return f"{name} (未知IP)"
```

### 6. 初始化优化

**文件**: `InspectMainWindow.py`

**修改**: 不在初始化时创建不完整的相机对象

```python
# 注释掉初始化时创建相机对象的代码
# cam_info = CameraInfo(
#     ip=ip or self.cam.current_server_name,
#     port=5024,
#     name=name or self.cam.current_server_name,
#     server_name=self.cam.current_server_name,
# )
# mgr.set_initial_camera(cam_info)

# 等待第一次扫描完成后，从扫描结果中设置当前相机
def _on_first_scan(sapera_cameras, network_cameras=None):
    # ... 合并相机列表
    sn = self.cam.current_server_name
    if sn:
        for cam in cameras:
            if getattr(cam, 'server_name', '') == sn:
                mgr.set_initial_camera(cam)
                break
```

## 工作流程

### 启动流程

1. **程序启动** → 连接相机（`CameraController`）
2. **初始化UI** → 不创建相机对象，等待扫描
3. **触发扫描** → `trigger_initial_scan()`
4. **扫描相机** → Sapera SDK 枚举服务器
5. **获取信息** → 尝试多种方法获取IP地址
6. **扫描完成** → 回调 `_on_first_scan`
7. **设置当前相机** → 从扫描结果中找到匹配的相机
8. **更新UI** → 下拉框显示相机列表

### 刷新流程

1. **点击刷新** → 清空 `_camera_list`
2. **显示"扫描中…"** → UI 提示
3. **清空旧结果** → `_last_results = []`
4. **重新扫描** → Sapera SDK 枚举服务器
5. **获取信息** → 多层后备方案获取IP
6. **去重合并** → 使用字典去重
7. **更新UI** → 下拉框显示最新列表

### 相机断开检测

1. **物理断开** → 拔掉网线或电源
2. **Sapera SDK** → `GetServerCount()` 不再返回该服务器
3. **扫描结果** → 不包含已断开的相机
4. **UI更新** → 下拉框中移除该相机

## 预期效果

✅ **下拉框只显示一条记录**：`S1049704 (192.168.11.136)`

✅ **不会出现重复**：相同相机的不同版本被正确合并

✅ **IP地址正确**：优先显示真实IP，而不是服务器名

✅ **断开检测**：拔掉相机后刷新，该相机不再显示

✅ **多相机支持**：可以正确显示多台相机

## 测试场景

### 场景 1：单相机正常启动
- 启动程序
- 自动扫描
- 显示：`S1049704 (192.168.11.136)`

### 场景 2：刷新相机列表
- 点击"刷新"按钮
- 显示"扫描中…"
- 扫描完成后显示：`S1049704 (192.168.11.136)`

### 场景 3：拔掉相机后刷新
- 拔掉相机
- 点击"刷新"按钮
- 扫描完成后显示："无可用相机"

### 场景 4：多相机环境
- 连接两台相机
- 扫描显示：
  - `S1049704 (192.168.11.136)`
  - `S1024035 (192.168.11.110)`

## 相关文件

- `camera/sapera_camera_discovery.py` - 相机发现和信息模型
- `ui/CameraStatusBar.py` - 相机状态栏UI组件
- `managers/camera_manager.py` - 相机管理器
- `InspectMainWindow.py` - 主窗口初始化
- `config.py` - 配置文件

## 注意事项

1. **设备占用**：如果相机被 CamExpert 占用，可能无法获取IP，会使用 ping 后备方案
2. **网络延迟**：拔掉相机后，可能需要等待几秒钟 Sapera SDK 才能检测到
3. **ARP缓存**：短时间内 ping 可能仍然成功，但 Sapera SDK 不会枚举到已断开的相机
4. **多相机**：确保每台相机有不同的IP地址

## 版本历史

- **2024-05-11**: 最终版本，修复所有相机去重和IP显示问题
