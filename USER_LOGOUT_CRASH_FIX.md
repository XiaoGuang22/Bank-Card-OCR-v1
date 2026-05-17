# 用户切换登录崩溃问题修复总结

## 问题描述

当用户退出登录并重新登录时，程序会崩溃并显示以下错误：

1. **Tkinter 回调错误**：
   ```
   invalid command name "2847127322432_load_recent"
   while executing
   "2847127322432_load_recent"
   ("after" script)
   ```

2. **Sapera 对象访问错误**：
   ```
   DALSA.SaperaLT.SapClassBasic.SapNativePointerException: 
   Invalid native class pointer. The Dispose method may already have been called.
   ```

## 根本原因

1. **日志面板回调未停止**：旧窗口的 `AuditLogPanel` 被销毁后，后台线程仍在尝试调用 `frame.after()` 回调
2. **相机对象被过早释放**：Sapera 相机对象已被 `Dispose()`，但帧回调函数仍在访问它
3. **清理顺序错误**：`_audit("login", "logout")` 会触发日志面板刷新，但此时面板应该已经被销毁

## 修复方案

### 1. 修改 `InspectMainWindow.logout()` 方法

**关键修复**：在记录退出日志**之前**先销毁日志面板

```python
def logout(self):
    """退出登录，销毁当前窗口并重新弹出登录界面"""
    try:
        # ★★★ 关键修复：先清理日志面板，再记录退出日志 ★★★
        # 因为 _audit() 会触发日志面板刷新，必须先销毁面板
        if hasattr(self, 'audit_log_panel') and self.audit_log_panel:
            self.audit_log_panel.destroy()
            self.audit_log_panel = None  # 防止 _audit 访问已销毁的面板
        
        # 记录退出日志（此时日志面板已销毁，不会触发刷新）
        self._audit("login", "logout")
        
        # ... 其他清理代码
```

**修改文件**：`InspectMainWindow.py` (第 3005 行)

### 2. 修改 `InspectMainWindow._audit()` 方法

**关键修复**：检查日志面板是否已被销毁

```python
def _audit(self, ...):
    """向操作日志面板写入一条记录（线程安全）"""
    try:
        # ... 添加相机信息的代码
        
        # ★★★ 检查日志面板是否存在且未被销毁 ★★★
        if self.audit_log_panel is not None and not getattr(self.audit_log_panel, '_destroyed', False):
            self.audit_log_panel.append_log(...)
        elif AuditLogManager is not None:
            # 日志面板不存在或已销毁，直接写入数据库
            AuditLogManager().log(...)
```

**修改文件**：`InspectMainWindow.py` (第 2732 行)

### 3. 修改 `AuditLogPanel.append_log()` 方法

**关键修复**：在调用 `after()` 之前检查 `_destroyed` 标志

```python
def append_log(self, ...):
    """写入数据库并实时追加到表格顶部"""
    # ★★★ 检查是否已销毁 ★★★
    if self._destroyed:
        return
        
    # 写库
    self._manager.log(...)
    
    # 刷新表格（回主线程）
    # ★★★ 再次检查是否已销毁，避免调度 after 回调 ★★★
    if not self._destroyed:
        try:
            self.frame.after(0, self._load_recent)
        except tk.TclError:
            # 窗口已被销毁，忽略
            pass
```

**修改文件**：`ui/AuditLogPanel.py` (第 180 行)

### 4. 同样修改 `_do_close()` 和 `close_application()` 方法

在这两个方法中也添加了日志面板清理代码：

```python
# ★★★ 清理日志面板（停止所有回调） ★★★
if hasattr(self, 'audit_log_panel') and self.audit_log_panel:
    self.audit_log_panel.destroy()
```

**修改文件**：`InspectMainWindow.py` (第 2877 行和第 2995 行)

## 修复效果

### 修复前
- 用户退出登录 → 程序崩溃
- 错误：`invalid command name` 和 `Invalid native class pointer`

### 修复后
- 用户退出登录 → 正常返回登录界面
- 重新登录 → 正常进入主界面
- 不再有 Tkinter 回调错误
- 不再有 Sapera 对象访问错误

## 测试场景

请测试以下场景确认修复有效：

1. ✅ 用账号 A 登录 → 退出登录 → 用账号 B 登录
2. ✅ 用账号 A 登录 → 切换相机 → 退出登录 → 用账号 B 登录
3. ✅ 用账号 A 登录 → 查看日志 → 退出登录 → 用账号 B 登录
4. ✅ 用账号 A 登录 → 直接关闭主窗口（点击 X 按钮）
5. ✅ 用账号 A 登录 → 进行多次操作（生成日志）→ 退出登录 → 用账号 B 登录

## 技术要点

### 1. 销毁顺序很重要
- **错误顺序**：记录日志 → 销毁面板 → 清理相机
- **正确顺序**：销毁面板 → 记录日志 → 清理相机

### 2. 多层防护
- 第一层：`logout()` 中先销毁面板
- 第二层：`_audit()` 中检查 `_destroyed` 标志
- 第三层：`append_log()` 中检查 `_destroyed` 标志
- 第四层：`_load_recent()` 中检查 `_destroyed` 标志

### 3. 线程安全
- 使用 `_destroyed` 标志阻止后台线程继续执行
- 使用 `try-except` 捕获 `tk.TclError` 异常
- 在调用 `after()` 前检查窗口是否仍然存在

## 相关文件

- `InspectMainWindow.py` - 主窗口类（logout、_audit、_do_close、close_application 方法）
- `ui/AuditLogPanel.py` - 日志面板类（append_log、_load_recent、destroy 方法）
- `ui/CameraStatusBar.py` - 相机状态栏（_refresh_audit_log 方法已有保护）

## 日期

2024-01-XX

## 状态

✅ 已修复 - 等待测试确认
