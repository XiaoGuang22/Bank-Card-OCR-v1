# 相机刷新资源占用问题修复

## 问题描述

刷新相机列表时，原本能正常显示的相机变成"无法创建设备（可能被占用）"，导致无法获取相机信息。

### 症状
```
[启动时]
✓ 成功连接到: S1024035 (192.168.12.110)

[刷新后]
✗ 无法创建设备 Genie_M1600_1（可能被占用）
✗ 无法创建设备 Genie_M1600_2（可能被占用）
```

## 根本原因

### 问题分析

1. **启动时的流程**：
   - `SaperaCameraDiscovery._do_scan()` 调用 `_get_device_info()` 获取相机信息
   - `_get_device_info()` 创建临时设备对象（非独占模式）
   - 获取信息后立即销毁设备对象
   - 此时 `CameraController` 还未连接任何相机，所以能成功

2. **刷新时的流程**：
   - 用户点击刷新按钮
   - `SaperaCameraDiscovery._do_scan()` 再次调用 `_get_device_info()`
   - **问题**：`CameraController` 已经连接了 S1024035
   - 即使使用非独占模式，Sapera SDK 也不允许同时创建多个设备实例访问同一台相机
   - 导致 `acq_device.Create()` 失败，返回空的设备信息
   - 因为没有IP地址，相机被跳过

### 核心问题

**`_get_device_info()` 函数在每次扫描时都尝试创建新的设备实例，但已连接的相机无法再次创建设备实例。**

## 解决方案

### 实现缓存机制

1. **添加设备信息缓存**：
   ```python
   self._device_info_cache: Dict[str, Dict] = {}
   ```

2. **实现缓存查询方法** `_get_device_info_cached()`：
   - 优先使用缓存的设备信息
   - 通过 ping 验证缓存的IP是否仍然可达
   - 如果缓存无效或不存在，才调用 `_get_device_info()` 获取新信息
   - 成功获取后更新缓存

3. **添加缓存管理方法** `clear_device_cache()`：
   - 支持清除特定相机的缓存
   - 支持清除所有缓存

### 修改的文件

**camera/sapera_camera_discovery.py**

#### 1. 添加缓存字段
```python
def __init__(self):
    self._scanning = False
    self._lock = threading.Lock()
    self._last_results: List[SaperaCameraInfo] = []
    self._event_registered = False
    # ★★★ 新增：缓存已获取的设备信息，避免重复创建设备 ★★★
    self._device_info_cache: Dict[str, Dict] = {}
```

#### 2. 添加缓存查询方法
```python
def _get_device_info_cached(self, server_name: str, server_index: int) -> Dict:
    """
    获取设备详细信息（带缓存）
    
    优先使用缓存的设备信息，避免在相机已被占用时重复创建设备
    """
    # 如果缓存中有信息，直接返回
    if server_name in self._device_info_cache:
        cached_info = self._device_info_cache[server_name]
        # 验证缓存的IP地址是否仍然有效（通过ping）
        ip_address = cached_info.get('ip_address', '').strip()
        if ip_address and self._verify_ip_reachable(ip_address):
            print(f"[Sapera] 使用缓存的设备信息: {server_name}")
            return cached_info
        else:
            # IP不可达，清除缓存
            print(f"[Sapera] 缓存的IP不可达，清除缓存: {server_name}")
            del self._device_info_cache[server_name]
    
    # 尝试获取新的设备信息
    device_info = self._get_device_info(server_name, server_index)
    
    # 如果成功获取到信息，缓存起来
    if device_info and device_info.get('ip_address'):
        self._device_info_cache[server_name] = device_info
    
    return device_info
```

#### 3. 添加IP验证方法
```python
def _verify_ip_reachable(self, ip_address: str, timeout_ms: int = 500) -> bool:
    """
    验证IP地址是否可达（通过ping）
    
    Args:
        ip_address: IP地址
        timeout_ms: 超时时间（毫秒）
    
    Returns:
        bool: IP是否可达
    """
    try:
        import subprocess
        result = subprocess.run(
            ['ping', '-n', '1', '-w', str(timeout_ms), ip_address],
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000.0 + 0.5
        )
        return result.returncode == 0
    except Exception:
        return False
```

#### 4. 添加缓存管理方法
```python
def clear_device_cache(self, server_name: Optional[str] = None):
    """
    清除设备信息缓存
    
    Args:
        server_name: 要清除的服务器名称，如果为None则清除所有缓存
    """
    if server_name:
        if server_name in self._device_info_cache:
            del self._device_info_cache[server_name]
            print(f"[Sapera] 已清除设备缓存: {server_name}")
    else:
        self._device_info_cache.clear()
        print(f"[Sapera] 已清除所有设备缓存")
```

#### 5. 修改扫描逻辑
```python
# 在 _do_scan() 方法中
# 先获取设备详细信息（优先使用缓存）
device_info = self._get_device_info_cached(server_name, i)
```

## 工作原理

### 首次扫描（启动时）
1. 缓存为空
2. 调用 `_get_device_info()` 创建临时设备获取信息
3. 成功后将信息存入缓存
4. 销毁临时设备

### 后续刷新
1. 检查缓存中是否有该相机的信息
2. 如果有，验证IP是否可达（ping）
3. 如果IP可达，直接使用缓存信息，**避免创建设备**
4. 如果IP不可达或缓存不存在，才尝试创建设备获取新信息

### 优势
- **避免资源冲突**：已连接的相机使用缓存信息，不再尝试创建新设备
- **提高性能**：减少不必要的设备创建和销毁操作
- **保持准确性**：通过ping验证缓存有效性，确保信息准确

## 测试验证

### 测试场景
1. **启动应用**：
   - 应该能正常扫描并显示所有相机
   - 能成功连接到相机

2. **刷新相机列表**：
   - 已连接的相机应该使用缓存信息
   - 未连接的相机应该能正常获取信息
   - 所有相机都应该正常显示

3. **相机断开后刷新**：
   - 缓存的IP验证失败
   - 自动清除缓存
   - 相机从列表中消失

### 预期日志
```
[启动时]
[Sapera] 设备 Genie_M1600_1 信息:
  用户名: S1049704
  IP地址: 192.168.11.136
[Sapera] 设备 Genie_M1600_2 信息:
  用户名: S1024035
  IP地址: 192.168.12.110

[刷新时 - 已连接 S1024035]
[Sapera] 设备 Genie_M1600_1 信息:
  用户名: S1049704
  IP地址: 192.168.11.136
[Sapera] 使用缓存的设备信息: Genie_M1600_2
```

## 相关文件

- `camera/sapera_camera_discovery.py` - 主要修改文件
- `ui/CameraStatusBar.py` - 刷新按钮触发点
- `managers/camera_manager.py` - 相机管理器

## 注意事项

1. **缓存有效性**：通过ping验证IP可达性，确保缓存信息准确
2. **缓存清理**：相机断开连接时应该清除缓存（可选优化）
3. **线程安全**：缓存操作在扫描线程中进行，已有锁保护

## 总结

通过引入设备信息缓存机制，成功解决了刷新时的资源占用问题。核心思路是：
- **已连接的相机**：使用缓存信息，避免重复创建设备
- **未连接的相机**：正常创建临时设备获取信息
- **缓存验证**：通过ping确保缓存有效性

这样既避免了资源冲突，又保持了信息的准确性。
