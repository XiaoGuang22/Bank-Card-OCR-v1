"""
IP地址发现辅助工具

当 Sapera SDK 无法获取相机IP地址时，通过网络扫描来发现相机IP
"""

import socket
import ipaddress
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional


def get_local_network_ranges() -> List[str]:
    """获取本机所在的网络段"""
    networks = []
    
    try:
        # 获取本机IP地址
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        
        # 根据本机IP推断网络段
        ip_obj = ipaddress.IPv4Address(local_ip)
        
        # 常见的网络段
        common_networks = [
            "192.168.1.0/24",
            "192.168.0.0/24", 
            "192.168.11.0/24",
            "10.0.0.0/24",
            "172.16.0.0/24"
        ]
        
        # 添加本机所在网段
        for prefix_len in [24, 16]:
            try:
                network = ipaddress.IPv4Network(f"{local_ip}/{prefix_len}", strict=False)
                networks.append(str(network))
                break
            except:
                continue
        
        # 添加常见网段
        networks.extend(common_networks)
        
        # 去重
        networks = list(set(networks))
        
    except Exception as e:
        print(f"获取网络段失败: {e}")
        # 使用默认网段
        networks = ["192.168.1.0/24", "192.168.0.0/24", "192.168.11.0/24"]
    
    return networks


def probe_camera_ip(ip: str, port: int = 5024, timeout: float = 0.2) -> bool:
    """探测指定IP是否有相机服务"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            result = s.connect_ex((ip, port))
            return result == 0
    except:
        return False


def scan_network_for_cameras(network: str, port: int = 5024, max_workers: int = 50) -> List[str]:
    """扫描网络段寻找相机"""
    camera_ips = []
    
    try:
        net = ipaddress.IPv4Network(network, strict=False)
        
        # 限制扫描范围，避免扫描过多IP
        hosts = list(net.hosts())
        if len(hosts) > 254:
            hosts = hosts[:254]  # 限制最多扫描254个IP
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有扫描任务
            future_to_ip = {
                executor.submit(probe_camera_ip, str(ip), port): str(ip) 
                for ip in hosts
            }
            
            # 收集结果
            for future in as_completed(future_to_ip, timeout=10):
                ip = future_to_ip[future]
                try:
                    if future.result():
                        camera_ips.append(ip)
                except:
                    pass
    
    except Exception as e:
        print(f"扫描网络 {network} 失败: {e}")
    
    return camera_ips


def discover_camera_ips(port: int = 5024) -> List[str]:
    """发现网络中的相机IP地址"""
    print("🔍 开始网络扫描寻找相机...")
    
    all_camera_ips = []
    networks = get_local_network_ranges()
    
    print(f"扫描网络段: {networks}")
    
    for network in networks:
        try:
            print(f"扫描 {network}...")
            camera_ips = scan_network_for_cameras(network, port)
            if camera_ips:
                print(f"在 {network} 中发现相机: {camera_ips}")
                all_camera_ips.extend(camera_ips)
        except Exception as e:
            print(f"扫描 {network} 失败: {e}")
    
    # 去重并排序
    all_camera_ips = sorted(list(set(all_camera_ips)))
    
    print(f"总共发现 {len(all_camera_ips)} 个相机IP: {all_camera_ips}")
    
    return all_camera_ips


def match_sapera_camera_to_ip(server_name: str, camera_ips: List[str]) -> Optional[str]:
    """将 Sapera 相机服务器名匹配到IP地址"""
    
    # 简单的匹配策略：
    # 1. 如果只有一个相机IP，直接匹配
    # 2. 如果有多个，根据服务器名称的数字后缀匹配
    
    if not camera_ips:
        return None
    
    if len(camera_ips) == 1:
        return camera_ips[0]
    
    # 尝试从服务器名称中提取数字
    import re
    match = re.search(r'(\d+)', server_name)
    if match:
        camera_index = int(match.group(1)) - 1  # 转换为0基索引
        if 0 <= camera_index < len(camera_ips):
            return camera_ips[camera_index]
    
    # 如果无法匹配，返回第一个
    return camera_ips[0]


# 缓存扫描结果，避免重复扫描
_cached_camera_ips = None
_cache_lock = threading.Lock()


def get_cached_camera_ips() -> List[str]:
    """获取缓存的相机IP列表"""
    global _cached_camera_ips
    
    with _cache_lock:
        if _cached_camera_ips is None:
            _cached_camera_ips = discover_camera_ips()
        return _cached_camera_ips.copy()


def clear_ip_cache():
    """清除IP缓存"""
    global _cached_camera_ips
    
    with _cache_lock:
        _cached_camera_ips = None


if __name__ == "__main__":
    # 测试IP发现功能
    camera_ips = discover_camera_ips()
    print(f"\n发现的相机IP: {camera_ips}")
    
    # 测试匹配功能
    test_servers = ["Genie_M1600_1", "Genie_M1600_2", "System_P1"]
    for server in test_servers:
        matched_ip = match_sapera_camera_to_ip(server, camera_ips)
        print(f"{server} -> {matched_ip}")