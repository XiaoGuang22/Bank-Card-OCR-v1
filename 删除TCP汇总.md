# 改动汇总
## 文件 1：managers/camera_manager.py（改动最大）
删除项	说明
CameraDiscovery 导入	旧网络扫描器类
DiscoveryMode 类（NETWORK_ONLY, HYBRID）	三种扫描模式定位
self._network_discovery	不再需要网络扫描器实例
self._discovery_mode	不再需要模式切换
available_network_cameras 属性	不再有网络相机列表
set_discovery_mode() 方法	不再需要切换模式
_scan_network_only() 方法	仅 TCP 扫描
_scan_hybrid() 方法	并行两种扫描
all_available_cameras 合并逻辑	不再拼接两种列表
is_scanning 中的 _network_discovery.is_scanning	只看 Sapera
回调签名中的 network_cameras 参数	简化为仅 sapera_cameras
保留（虽然也用 CameraInfo，但属于方案文件 I/O，不是扫描）：

parse_camera_from_layout() / inject_camera_to_layout()
switch_camera() / auto_switch_camera() / _do_switch() / _connect()


## 文件 2：ui/CameraStatusBar.py
删除项	说明
_on_scan_complete 中 all_cameras = sapera + network 合并	直接使用 sapera_cameras
_get_camera_key 中的 network:ip:port 分支	只保留 server_name 去重
_is_camera_more_complete 中的"对于网络相机"注释	更新注释说明

#  文件 3：InspectMainWindow.py
删除项	说明
_on_first_scan 的 network_cameras=None 兼容逻辑	签名简化为 (sapera_cameras)
函数内 cameras → sapera_cameras	变量名直接使用参数名