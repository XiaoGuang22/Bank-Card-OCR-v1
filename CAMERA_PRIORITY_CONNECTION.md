# 相机优先连接功能实现

## 功能描述

实现"重启时优先连接上次使用的相机"功能，提升用户体验。

### 需求
- 程序启动时扫描所有可用相机
- **优先尝试连接上次使用的相机**
- 如果上次的相机不可用，再连接第一台可用相机
- 切换相机后自动保存配置

## 实现方案

### 1. 配置文件存储

**文件位置**：`Logs/last_camera.json`

**存储内容**：
```json
{
  "server_name": "Genie_M1600_2",
  "display_name": "S1024035 (192.168.12.110)",
  "ip_address": "192.168.12.110",
  "camera_type": "sapera"
}
```

### 2. 配置管理函数

**文件**：`config.py`

#### 保存函数
```python
def save_last_connected_camera(camera_info):
    """
    保存上次连接的相机信息
    
    Args:
        camera_info: SaperaCameraInfo 或 CameraInfo 对象
    """
    # 提取相机信息
    camera_data = {
        'server_name': getattr(camera_info, 'server_name', ''),
        'display_name': getattr(camera_info, 'display_name', ''),
        'ip_address': '',
        'camera_type': 'sapera' if hasattr(camera_info, 'server_name') else 'network'
    }
    
    # 获取 IP 地址
    if hasattr(camera_info, 'device_info') and camera_info.device_info:
        camera_data['ip_address'] = camera_info.device_info.get('ip_address', '')
    elif hasattr(camera_info, 'ip'):
        camera_data['ip_address'] = camera_info.ip
    
    # 保存到 JSON 文件
    with open(LAST_CAMERA_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(camera_data, f, indent=2, ensure_ascii=False)
```

#### 读取函数
```python
def load_last_connected_camera():
    """
    读取上次连接的相机信息
    
    Returns:
        dict: 包含 server_name, display_name, ip_address, camera_type 的字典
        None: 如果没有保存的记录或读取失败
    """
    if not os.path.exists(LAST_CAMERA_CONFIG_FILE):
        return None
    
    with open(LAST_CAMERA_CONFIG_FILE, 'r', encoding='utf-8') as f:
        camera_data = json.load(f)
    
    return camera_data
```

### 3. 启动时优先连接逻辑

**文件**：`InspectMainWindow.py`

**方法**：`_on_first_scan()`

#### 流程图
```
启动扫描
    ↓
扫描到相机列表
    ↓
读取上次连接的相机配置
    ↓
在扫描结果中查找上次的相机
    ↓
找到了？
    ├─ 是 → 尝试连接上次的相机
    │       ├─ 成功 → 设置为当前相机 ✓
    │       └─ 失败 → 继续下一步
    │
    └─ 否 → 连接第一台可用相机
            ├─ 成功 → 设置为当前相机 ✓
            └─ 失败 → 显示未连接
```

#### 代码实现
```python
def _on_first_scan(sapera_cameras, network_cameras=None):
    # 合并相机列表
    cameras = list(sapera_cameras) + list(network_cameras or [])
    
    if cameras:
        # 读取上次连接的相机信息
        from config import load_last_connected_camera
        last_camera_data = load_last_connected_camera()
        
        connected = False
        
        # 步骤1：优先尝试连接上次的相机
        if last_camera_data:
            last_server_name = last_camera_data.get('server_name', '')
            
            # 在扫描结果中查找上次的相机
            for cam in cameras:
                if getattr(cam, 'server_name', '') == last_server_name:
                    # 找到了，尝试连接
                    if self.cam.connect(last_server_name):
                        print(f"✓ 成功连接到上次的相机")
                        mgr.set_initial_camera(cam)
                        save_last_connected_camera(cam)
                        connected = True
                        break
        
        # 步骤2：如果上次的相机连接失败，连接第一台可用相机
        if not connected:
            for cam in cameras:
                if has_complete_info(cam):
                    if self.cam.connect(cam.server_name):
                        print(f"✓ 成功连接到第一台可用相机")
                        mgr.set_initial_camera(cam)
                        save_last_connected_camera(cam)
                        connected = True
                        break
```

### 4. 切换时保存配置

**文件**：`camera/sapera_camera_manager.py`

**方法**：`switch_camera()`

```python
def switch_camera(self, target_camera):
    # ... 执行切换逻辑 ...
    
    if success:
        self._current_camera = target_camera
        self._last_successful_camera = target_camera
        self._connected = True
        
        # ★★★ 保存上次连接的相机信息 ★★★
        from config import save_last_connected_camera
        save_last_connected_camera(target_camera)
        
        return True, f"成功切换到 {target_camera.formatted_display_name}"
```

## 使用场景

### 场景1：正常重启
```
[第一次启动]
1. 扫描到相机：704, 035
2. 连接第一台：704
3. 保存配置：server_name = "Genie_M1600_1"

[用户切换到 035]
1. 切换成功
2. 保存配置：server_name = "Genie_M1600_2"

[第二次启动]
1. 扫描到相机：704, 035
2. 读取配置：server_name = "Genie_M1600_2"
3. 优先连接：035 ✓
```

### 场景2：上次的相机不可用
```
[上次连接的是 035]
配置文件：server_name = "Genie_M1600_2"

[本次启动，035 断开]
1. 扫描到相机：704
2. 读取配置：server_name = "Genie_M1600_2"
3. 查找 035：未找到
4. 连接第一台可用相机：704 ✓
5. 更新配置：server_name = "Genie_M1600_1"
```

### 场景3：首次启动（无配置文件）
```
[首次启动]
1. 扫描到相机：704, 035
2. 读取配置：无配置文件
3. 连接第一台可用相机：704 ✓
4. 创建配置：server_name = "Genie_M1600_1"
```

## 日志输出

### 成功连接上次的相机
```
[Config] 读取上次连接的相机: S1024035 (Genie_M1600_2)
[InspectMainWindow] 尝试优先连接上次的相机: Genie_M1600_2
[InspectMainWindow] 找到上次的相机: S1024035 (192.168.12.110)
[InspectMainWindow] 尝试连接到上次的相机: S1024035 (192.168.12.110)
[InspectMainWindow] ✓ 成功连接到上次的相机: S1024035 (192.168.12.110)
[Config] 已保存上次连接的相机: S1024035 (192.168.12.110) (Genie_M1600_2)
```

### 上次的相机不可用，连接第一台
```
[Config] 读取上次连接的相机: S1024035 (Genie_M1600_2)
[InspectMainWindow] 尝试优先连接上次的相机: Genie_M1600_2
[InspectMainWindow] ✗ 未找到上次的相机: Genie_M1600_2
[InspectMainWindow] 尝试连接第一台可用相机
[InspectMainWindow] 检查相机: Genie_M1600_1
[InspectMainWindow] 尝试连接到: S1049704 (192.168.11.136)
[InspectMainWindow] ✓ 成功连接到: S1049704 (192.168.11.136)
[Config] 已保存上次连接的相机: S1049704 (192.168.11.136) (Genie_M1600_1)
```

## 优势

1. **用户体验提升**：
   - 重启后自动连接常用相机
   - 减少手动切换操作

2. **智能回退**：
   - 上次的相机不可用时自动连接其他相机
   - 不会因为配置问题导致无法启动

3. **配置持久化**：
   - 使用 JSON 文件存储，易于查看和修改
   - 存储在 Logs 目录，与其他日志文件一起管理

4. **兼容性好**：
   - 支持 Sapera 相机和网络相机
   - 首次启动无配置文件时自动创建

## 注意事项

1. **配置文件位置**：`Logs/last_camera.json`
   - 确保 Logs 目录有写入权限
   - 配置文件损坏时会自动忽略并创建新的

2. **相机识别**：
   - 使用 `server_name` 作为唯一标识
   - 确保 `server_name` 在系统中唯一

3. **状态同步**：
   - 连接成功后同步 `SaperaCameraManager` 状态
   - 确保两个管理器状态一致

## 测试验证

### 测试步骤
1. **首次启动**：
   - 启动程序，观察连接到哪台相机
   - 检查 `Logs/last_camera.json` 是否创建

2. **切换相机**：
   - 切换到另一台相机
   - 检查配置文件是否更新

3. **重启验证**：
   - 关闭程序
   - 重新启动
   - 观察是否连接到上次的相机

4. **相机不可用**：
   - 断开上次连接的相机
   - 重新启动
   - 观察是否连接到其他可用相机

## 相关文件

- `config.py` - 配置管理函数
- `InspectMainWindow.py` - 启动时优先连接逻辑
- `camera/sapera_camera_manager.py` - 切换时保存配置
- `Logs/last_camera.json` - 配置文件（运行时生成）

## 总结

通过引入配置文件机制，成功实现了"重启时优先连接上次使用的相机"功能。核心思路是：
1. **保存**：切换相机成功后保存配置
2. **读取**：启动时读取配置
3. **优先**：优先尝试连接上次的相机
4. **回退**：失败时连接第一台可用相机

这样既提升了用户体验，又保证了系统的稳定性。
