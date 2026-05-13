# 两台相机画面展示方式对比

## 概述

系统中有两台 Sapera 相机：
- **S1049704 (192.168.11.136)** - Genie_M1600_1
- **S1024035 (192.168.12.110)** - Genie_M1600_2

两台相机使用**完全相同**的画面展示方式，都是通过 `CameraController` 类来管理和显示。

## 画面展示流程

### 1. 相机连接和初始化

**位置**: `InspectMainWindow.py` - `CameraController` 类

```python
def _execute_camera_connection(self):
    # 1. 定位设备
    self.location = SapLocation(self._current_server_name, RESOURCE_INDEX)
    
    # 2. 创建采集设备
    self.acq_device = SapAcqDevice(self.location, False)
    
    # 3. 创建缓冲区（双缓冲）
    self.buffers = SapBufferWithTrash(2, self.acq_device, mem_type)
    
    # 4. 创建传输对象
    self.xfer = SapAcqDeviceToBuf(self.acq_device, self.buffers)
    
    # 5. 绑定帧回调
    self.xfer.XferNotify += self._on_frame_callback
    
    # 6. 启动采集
    self.xfer.Grab()
```

### 2. 图像采集方式

**方式**: **连续采集 + 帧回调**

- **连续采集**: `self.xfer.Grab()` 启动后，相机持续采集图像
- **帧回调**: 每采集一帧，自动调用 `_on_frame_callback`
- **双缓冲**: 使用 2 个缓冲区，一个采集，一个处理

```python
def _on_frame_callback(self, sender, args):
    """每采集一帧自动调用"""
    if args.Trash:
        return
    self._process_frame_callback()
```

### 3. 图像处理流程

**位置**: `InspectMainWindow.py` - `_process_frame_callback` 方法

**关键步骤**:

1. **保存到临时文件**:
   ```python
   # 使用 Sapera 的 Save 方法保存为 BMP
   self.buffers.Save(temp_path, "-format bmp")
   ```

2. **读取为 NumPy 数组**:
   ```python
   # 方法1: 使用 fromfile + imdecode（推荐）
   file_data = np.fromfile(temp_path, dtype=np.uint8)
   img_np = cv2.imdecode(file_data, cv2.IMREAD_GRAYSCALE)
   
   # 方法2: 直接使用 imread（兼容）
   img_np = cv2.imread(temp_path, cv2.IMREAD_GRAYSCALE)
   ```

3. **更新最新帧**:
   ```python
   with self.lock:
       self.latest_frame = img_np.copy()
   ```

4. **清理临时文件**:
   ```python
   os.unlink(temp_path)
   ```

### 4. 图像显示方式

**位置**: `InspectMainWindow.py` - `get_image` 方法

```python
def get_image(self):
    """获取最新图像"""
    with self.lock:
        if self.latest_frame is not None:
            frame = self.latest_frame.copy()
            
            # 应用软件对比度调整（如果配置）
            frame = self._apply_software_contrast_if_needed(frame)
            
            return frame
    
    # 无有效帧时返回"无信号"画面
    return self._generate_no_signal_image()
```

**显示特点**:
- **线程安全**: 使用 `self.lock` 保护 `latest_frame`
- **拷贝返回**: 返回 `copy()`，避免外部修改
- **对比度调整**: 支持软件对比度调整
- **无信号画面**: 无图像时显示 "NO SIGNAL"

## 两台相机的区别

### 唯一的区别：`server_name`

```python
# 704 相机
self._current_server_name = "Genie_M1600_1"

# 035 相机
self._current_server_name = "Genie_M1600_2"
```

### 切换相机时的操作

**位置**: `InspectMainWindow.py` - `switch_to` 方法

```python
def switch_to(self, server_name):
    """切换到指定相机"""
    with self._switch_lock:
        if server_name == self._current_server_name and self.acq_device is not None:
            return True  # 已是当前相机
        
        # 1. 断开当前相机
        self.disconnect()
        
        # 2. 更新服务器名称
        self._current_server_name = server_name
        
        # 3. 连接新相机
        if self.connect(server_name):
            self._last_connected_name = server_name
            return True
        
        return False
```

**切换流程**:
1. 停止当前采集
2. 销毁当前 Sapera 对象（`acq_device`, `buffers`, `xfer`）
3. 使用新的 `server_name` 重新创建 Sapera 对象
4. 重新启动采集

## 对比：GenieCameraTriggerOptimized.py

系统中还有一个 `GenieCameraTriggerOptimized.py` 文件，它也实现了相机控制，但**不是主程序使用的**。

### 主要区别

| 特性 | CameraController (主程序) | GenieCameraTriggerOptimized |
|------|---------------------------|----------------------------|
| **使用场景** | 主程序的相机控制 | 独立的演示/测试程序 |
| **显示方式** | 自定义 UI（Tkinter） | Sapera SDK 自带窗口 (`SapView`) |
| **图像获取** | 临时文件 + OpenCV | 临时文件 + OpenCV |
| **采集模式** | 连续采集 | 连续采集 / 单帧采集 |
| **多相机支持** | ✅ 支持切换 | ❌ 单相机 |
| **集成度** | 完全集成到主程序 | 独立运行 |

### GenieCameraTriggerOptimized 的显示方式

```python
# 创建 Sapera SDK 自带的显示窗口
self.view = SapView(self.buffers)
self.view.Create()

# 显示窗口
self.view.Show()

# 每帧回调时刷新
def on_frame_callback(self, sender, args):
    if self.view:
        self.view.Show()
```

**特点**:
- 使用 Sapera SDK 自带的 `SapView` 窗口
- 不需要手动处理图像数据
- 适合快速测试和演示

## 总结

### 两台相机的画面展示方式

✅ **完全相同**

- 都使用 `CameraController` 类
- 都使用**连续采集 + 帧回调**模式
- 都使用**临时文件 + OpenCV**读取图像
- 都显示在主程序的 Tkinter UI 中

### 唯一的区别

- **server_name** 不同：
  - 704 相机: `Genie_M1600_1`
  - 035 相机: `Genie_M1600_2`

### 切换相机时

1. 断开当前相机（销毁 Sapera 对象）
2. 更新 `server_name`
3. 重新连接新相机（创建新的 Sapera 对象）
4. 重新启动采集

### 画面展示的技术细节

1. **采集**: Sapera SDK 连续采集
2. **回调**: 每帧自动触发 `_on_frame_callback`
3. **保存**: 使用 `buffers.Save()` 保存为临时 BMP 文件
4. **读取**: 使用 OpenCV 读取为 NumPy 数组
5. **存储**: 更新 `self.latest_frame`
6. **显示**: UI 调用 `get_image()` 获取最新帧
7. **清理**: 删除临时文件

### 为什么使用临时文件？

**原因**: 避免直接访问 Sapera 缓冲区内存

- Sapera 缓冲区是 C++ 管理的内存
- 直接访问可能导致内存错误或崩溃
- 使用临时文件是最稳定的方式

**优点**:
- ✅ 稳定可靠
- ✅ 避免内存问题
- ✅ 兼容性好

**缺点**:
- ❌ 性能略低（需要文件 I/O）
- ❌ 需要清理临时文件

但对于工业相机应用，稳定性比性能更重要，所以这是合理的选择。

## 修改日期

2026-05-13
