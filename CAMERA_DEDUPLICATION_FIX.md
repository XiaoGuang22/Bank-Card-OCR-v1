# 相机去重修复文档

## 问题描述

在相机扫描和显示过程中，下拉框出现了重复的相机条目：
- `S1049704 (Genie_M1600_1)` ← 错误的，使用服务器名而非IP
- `S1049704 (192.168.11.136)` ← 正确的

## 根本原因

1. **初始化时创建的相机对象**：使用服务器名作为"IP"，因为此时还未获取到真实IP地址
2. **扫描后的相机对象**：包含真实的IP地址
3. **相等性比较问题**：原来的 `__eq__` 方法优先比较序列号，但初始化时序列号可能为空，导致两个对象被认为是不同的相机
4. **显示名称问题**：`formatted_display_name` 在没有IP时会使用服务器名，导致显示为 `S1049704 (Genie_M1600_1)`

## 解决方案

### 1. 修复 `SaperaCameraInfo.__eq__` 方法

**文件**: `camera/sapera_camera_discovery.py`

**修改内容**：
- 优先比较 `server_name`（最可靠的标识）
- 其次比较序列号
- 确保同一台相机的不同版本（有IP/无IP）被识别为同一个对象

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

### 2. 修复 `SaperaCameraInfo.__hash__` 方法

**修改内容**：
- 优先使用 `server_name` 作为哈希值

```python
def __hash__(self):
    # 优先使用服务器名作为哈希值（最可靠的标识）
    if self.server_name:
        return hash(self.server_name)
    
    device_info = self.device_info or {}
    serial = device_info.get('serial', '')
    return hash(serial) if serial else hash(self.server_name)
```

### 3. 修复 `formatted_display_name` 属性

**修改内容**：
- 只有在有真实IP地址时才使用 `名称 (IP)` 格式
- 如果没有IP，显示 `名称 (未知IP)` 而不是 `名称 (服务器名)`
- 添加IP地址格式检查，避免将服务器名误认为是IP

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
    
    # 确定相机名称（优先级：Device User ID > 型号 > display_name > 服务器名）
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

### 4. 优化 `CameraStatusBar._update_camera_list` 方法

**文件**: `ui/CameraStatusBar.py`

**修改内容**：
- 使用字典进行智能去重
- 基于 `server_name` 作为唯一键
- 当发现同一相机的新旧版本时，用新版本（有IP的）替换旧版本（没有IP的）

```python
def _update_camera_list(self, cameras: list):
    """扫描完成后用新列表完整替换下拉框，智能去重和合并"""
    # 创建字典用于去重
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
    
    # 转换为列表并更新UI
    self._camera_list = list(camera_dict.values())
    # ... 后续UI更新逻辑
```

### 5. 添加辅助方法

**新增方法**：
- `_get_camera_key(camera)`: 获取相机的唯一标识键
- `_is_camera_more_complete(new_camera, existing_camera)`: 判断新相机信息是否比现有相机更完整
- `_get_camera_display_name(camera)`: 获取相机的显示名称

### 6. 优化 `_refresh_display` 方法

**修改内容**：
- 不在此方法中修改下拉框的 `values`
- 只更新当前选中项
- 等待扫描完成后由 `_update_camera_list` 统一处理列表更新

### 7. 修复缩进错误

**文件**: `camera/sapera_camera_discovery.py`

**修改内容**：
- 修复 `_get_device_info` 方法中的缩进错误
- 移除重复的 `except:` 语句
- 确保所有代码块的缩进一致

## 测试结果

运行 `test_camera_fix.py` 测试脚本，所有测试通过：

✅ **测试 1**: 相机相等性比较
- 相同 `server_name` 的相机被正确识别为同一台

✅ **测试 2**: 格式化显示名称
- 有IP的相机显示为 `S1049704 (192.168.11.136)`
- 没有IP的相机显示为 `S1049704 (未知IP)`

✅ **测试 3**: 相机去重逻辑
- 重复相机已去重
- 保留了有IP的版本

## 预期效果

修复后：
1. ✅ 下拉框只显示一条记录：`S1049704 (192.168.11.136)`
2. ✅ 初始化时不会创建"半成品"相机对象
3. ✅ 扫描完成后，列表中的相机信息都是完整的（包含IP地址）
4. ✅ 相同相机的不同版本会被正确识别并合并

## 使用说明

1. **启动程序**：程序会自动触发相机扫描
2. **查看下拉框**：应该只显示一条记录，格式为 `相机名称 (IP地址)`
3. **刷新相机**：点击"刷新"按钮，列表会更新但不会出现重复
4. **切换相机**：选择相机并点击"切换连接"，功能正常

## 注意事项

1. **IP地址获取**：如果相机被其他程序（如 CamExpert）占用，可能无法获取IP地址，此时会显示"未知IP"
2. **设备占用**：建议在使用本程序前关闭 CamExpert 等占用相机的程序
3. **扫描时间**：首次扫描可能需要几秒钟，请耐心等待

## 相关文件

- `camera/sapera_camera_discovery.py` - 相机发现和信息模型
- `ui/CameraStatusBar.py` - 相机状态栏UI组件
- `test_camera_fix.py` - 测试脚本
- `CAMERA_DEDUPLICATION_FIX.md` - 本文档

## 版本历史

- **2024-05-11**: 初始版本，修复相机去重问题
