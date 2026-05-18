# FC-10 实现状态报告

## 需求回顾

FC-10 要求的相机切换流程：

1. 停止图像采集（`SapTransfer.Freeze` + `Wait`）
2. 销毁当前 `SapTransfer` 和 `SapAcqDevice` 对象
3. 为目标相机新建 `SapAcqDevice`，调用 `Create()` 建立控制通道
4. 重新创建 `SapAcqDeviceToBuf`（或 `SapTransfer`）对象并连接
5. 开始采集（`Grab`）
6. 成功：状态灯变绿，更新信息
7. **失败：状态灯变红，提示错误，尝试恢复至上一个成功的相机连接（重建其对象）**
8. **所有异常通过 `SapManager.Error` 事件统一捕获**

---

## 实现状态

### ✅ 已实现的部分

#### 1. 基本切换流程（步骤 1-6）
**文件**: `camera/sapera_camera_manager.py`

- ✅ **步骤 1**: 停止图像采集
  ```python
  # _disconnect_internal() 方法（第318-323行）
  if self._transfer:
      self._transfer.Freeze()
      self._transfer.Wait(5000)
  ```

- ✅ **步骤 2**: 销毁对象
  ```python
  # _cleanup_objects() 方法（第336-358行）
  # 销毁 Transfer, Buffers, AcqDevice
  ```

- ✅ **步骤 3**: 创建新设备
  ```python
  # _execute_connection() 方法（第217-223行）
  location = SapLocation(camera_info.server_name, 0)
  self._acq_device = SapAcqDevice(location, False)
  if not self._acq_device.Create():
      return False, f"无法创建设备: {camera_info.server_name}"
  ```

- ✅ **步骤 4**: 创建传输对象
  ```python
  # _create_buffers_and_transfer() 方法（第242-279行）
  self._buffers = SapBufferWithTrash(2, self._acq_device, mem_type)
  self._transfer = SapAcqDeviceToBuf(self._acq_device, self._buffers)
  ```

- ✅ **步骤 5**: 开始采集
  ```python
  # _start_acquisition() 方法（第281-296行）
  if not self._transfer.Grab():
      return False, "无法开始采集"
  ```

- ✅ **步骤 6**: 成功时更新状态
  ```python
  # switch_camera() 方法（第390-400行）
  self._notify_state_change(CameraConnectionStatus.CONNECTED, target_camera)
  ```

---

### ✅ 新增实现的部分（本次修复）

#### 2. 完善的错误恢复机制（步骤 7）
**修改**: `camera/sapera_camera_manager.py` 第 402-455 行

**改进内容**：

1. **三层回退逻辑**：
   ```python
   if success:
       # 切换成功
   else:
       # 第1层：尝试回退到上次成功的相机
       if self._last_successful_camera:
           fallback_success = cam_ctrl.switch_to(...)
           
           if fallback_success:
               # 第2层：回退成功，恢复连接
               self._notify_state_change(CONNECTED)
               return False, "切换失败，已自动恢复到..."
           else:
               # 第3层：回退也失败，设置错误状态
               self._notify_state_change(ERROR)
               return False, "切换失败且无法恢复连接"
   ```

2. **状态灯逻辑清晰**：
   - 切换成功 → 绿灯（`CONNECTED`）
   - 回退成功 → 绿灯（`CONNECTED`）+ 错误提示
   - 回退失败 → 红灯（`ERROR`）+ 错误提示

3. **异常处理完整**：
   - 捕获回退过程中的异常
   - 所有失败路径都设置正确的状态

---

### ⚠️ 部分实现的部分

#### 3. SapManager.Error 事件统一捕获（步骤 8）
**修改**: `camera/sapera_camera_manager.py` 第 144-177 行

**当前状态**：
- ✅ 已添加多种事件注册方式（方法1、2、3）
- ⚠️ **但事件可能仍然无法注册**（取决于 Sapera SDK 版本和 Python.NET 绑定）

**实现代码**：
```python
try:
    # 方法1：直接绑定
    SapManager.Error += _on_sapera_error
except:
    try:
        # 方法2：使用 add_ 前缀
        SapManager.add_Error(_on_sapera_error)
    except:
        try:
            # 方法3：使用 SetErrorHandler
            SapManager.SetErrorHandler(_on_sapera_error)
        except:
            print("[Sapera] Error 事件注册失败（所有方法都失败）")
            print("[Sapera] 将使用 Python try/except 代替事件捕获")
```

**备用方案**：
- 如果事件注册失败，使用 Python 的 `try/except` 捕获异常
- 所有关键操作都已包裹在 `try/except` 中

---

## 测试建议

### 测试场景 1：正常切换
1. 连接相机 A
2. 切换到相机 B
3. **预期**：成功切换，状态灯变绿

### 测试场景 2：切换失败 + 回退成功
1. 连接相机 A
2. 拔掉相机 B 的网线
3. 尝试切换到相机 B
4. **预期**：
   - 切换失败
   - 自动回退到相机 A
   - 状态灯保持绿色
   - 提示"切换失败，已自动恢复到 CAM-A"

### 测试场景 3：切换失败 + 回退失败
1. 连接相机 A
2. 拔掉相机 A 和相机 B 的网线
3. 尝试切换到相机 B
4. **预期**：
   - 切换失败
   - 回退也失败
   - 状态灯变红
   - 提示"切换失败且无法恢复连接，请手动选择相机"

### 测试场景 4：SapManager.Error 事件
1. 启动软件
2. 查看控制台输出
3. **预期**：
   - 看到 `[Sapera] Error 事件已注册（FC-10）- 方法X`
   - 或看到 `[Sapera] 将使用 Python try/except 代替事件捕获`

---

## 已知限制

### 1. SapManager.Error 事件可能无法注册
**原因**：
- Sapera SDK 的 Python.NET 绑定可能不支持事件
- 不同版本的 SDK 行为不一致

**影响**：
- 无法通过事件统一捕获 SDK 内部错误
- 但不影响功能，因为已使用 `try/except` 作为备用方案

**解决方案**：
- 继续使用 Python 的 `try/except`
- 或联系 Teledyne DALSA 技术支持确认事件支持情况

### 2. 回退机制依赖 CameraController
**当前实现**：
```python
from InspectMainWindow import CameraController
cam_ctrl = CameraController()
fallback_success = cam_ctrl.switch_to(self._last_successful_camera.server_name)
```

**限制**：
- 依赖主程序的 `CameraController`
- 如果 `CameraController` 有问题，回退也会失败

**建议**：
- 确保 `CameraController.switch_to()` 方法稳定可靠
- 考虑在 `SaperaCameraManager` 中直接管理 Sapera 对象（避免依赖外部）

---

## 总结

### FC-10 实现完成度：**90%**

| 需求项 | 状态 | 完成度 |
|:---|:---:|:---:|
| 1. 停止图像采集 | ✅ | 100% |
| 2. 销毁对象 | ✅ | 100% |
| 3. 创建新设备 | ✅ | 100% |
| 4. 创建传输对象 | ✅ | 100% |
| 5. 开始采集 | ✅ | 100% |
| 6. 成功时更新状态 | ✅ | 100% |
| 7. 失败时恢复机制 | ✅ | 100% |
| 8. SapManager.Error 事件 | ⚠️ | 50% |

### 下一步行动

1. **测试回退机制**：按照上述测试场景验证
2. **确认 Error 事件**：查看启动日志，确认事件是否注册成功
3. **如果事件注册失败**：
   - 联系 Teledyne DALSA 技术支持
   - 或接受使用 `try/except` 作为替代方案
4. **考虑重构**：将 Sapera 对象管理完全移入 `SaperaCameraManager`，减少对外部依赖

---

## 修改文件清单

1. `camera/sapera_camera_manager.py`
   - 第 144-177 行：增强 Error 事件注册（多种方式）
   - 第 402-455 行：完善切换失败后的恢复机制

2. `FC10_IMPLEMENTATION_STATUS.md`（本文件）
   - 详细记录 FC-10 的实现状态和测试建议
