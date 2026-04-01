"""
TCP 通信服务模块（多端口版本）

支持同时监听多个端口，每个端口独立管理客户端连接和命令队列。
帧格式：STX(0x02) + JSON字节 + ETX(0x03) + 换行符(0x0A)
"""

import json
import logging
import queue
import socket
import threading
from typing import Optional, List, Tuple, Callable, Dict

logger = logging.getLogger(__name__)

STX = 0x02
ETX = 0x03


class _PortListener:
    """单个端口的监听器，管理该端口的所有客户端连接和命令队列。"""

    def __init__(self, port: int, on_change_cb: Optional[Callable] = None):
        self.port = port
        self._clients: List[Tuple[socket.socket, tuple]] = []
        self._lock = threading.Lock()
        self._cmd_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._server_socket: Optional[socket.socket] = None
        self._listen_thread: Optional[threading.Thread] = None
        self._on_change_cb = on_change_cb  # 通知外部客户端列表变化

    def start(self) -> bool:
        self._stop_event.clear()
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind(('', self.port))
            self._server_socket.listen(5)
        except OSError as e:
            logger.error(f"端口 {self.port} 启动失败：{e}")
            self._server_socket = None
            return False
        self._listen_thread = threading.Thread(
            target=self._listen_loop, daemon=True,
            name=f"TcpListen-{self.port}")
        self._listen_thread.start()
        logger.info(f"TCP 服务已启动，监听端口 {self.port}")
        return True

    def stop(self):
        self._stop_event.set()
        if self._server_socket:
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None
        with self._lock:
            for sock, _ in self._clients:
                try:
                    sock.close()
                except OSError:
                    pass
            self._clients.clear()
        if self._listen_thread and self._listen_thread.is_alive():
            self._listen_thread.join(timeout=2.0)
        self._listen_thread = None
        logger.info(f"端口 {self.port} 已停止")

    @property
    def is_running(self) -> bool:
        return self._server_socket is not None and not self._stop_event.is_set()

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    @property
    def clients(self) -> list:
        with self._lock:
            return [addr for _, addr in self._clients]

    def broadcast(self, data):
        frame = TcpService._encode_frame(data)
        failed = []
        with self._lock:
            for sock, addr in self._clients:
                try:
                    sock.sendall(frame)
                except OSError as e:
                    logger.warning(f"端口 {self.port} 向 {addr} 发送失败：{e}")
                    failed.append((sock, addr))
            for item in failed:
                self._clients.remove(item)
        if failed:
            self._notify_change()

    def get_command(self) -> Optional[dict]:
        try:
            return self._cmd_queue.get_nowait()
        except queue.Empty:
            return None

    def _notify_change(self):
        if self._on_change_cb:
            try:
                self._on_change_cb(self.port, self.clients)
            except Exception as e:
                logger.warning(f"client_change_callback 异常：{e}")

    def _listen_loop(self):
        while not self._stop_event.is_set():
            try:
                client_sock, addr = self._server_socket.accept()
            except OSError:
                break
            logger.info(f"端口 {self.port} 新客户端：{addr}")
            with self._lock:
                self._clients.append((client_sock, addr))
            t = threading.Thread(
                target=self._recv_loop, args=(client_sock, addr),
                daemon=True, name=f"TcpRecv-{self.port}-{addr}")
            t.start()
            self._notify_change()

    def _recv_loop(self, sock: socket.socket, addr):
        buf = bytearray()
        while not self._stop_event.is_set():
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
                # 优先尝试帧格式解析（STX...ETX）
                while True:
                    try:
                        stx_idx = buf.index(STX)
                        etx_idx = buf.index(ETX, stx_idx + 1)
                    except ValueError:
                        # 没有完整帧，检查是否有换行结尾的裸文本
                        if b'\n' in buf:
                            line, buf = buf.split(b'\n', 1)
                            text = line.strip().decode('utf-8', errors='ignore')
                            if text:
                                self._cmd_queue.put({"data": text})
                        break
                    raw_frame = bytes(buf[stx_idx: etx_idx + 1])
                    buf = buf[etx_idx + 1:]
                    if buf and buf[0] == ord('\n'):
                        buf = buf[1:]
                    result = TcpService._decode_frame(raw_frame)
                    if result is not None:
                        self._cmd_queue.put(result)
                    else:
                        logger.warning(f"端口 {self.port} 收到非法帧，来自 {addr}，已丢弃")
            except OSError as e:
                logger.warning(f"端口 {self.port} 客户端 {addr} 网络异常：{e}")
                break
        with self._lock:
            self._clients = [(s, a) for s, a in self._clients if s is not sock]
        try:
            sock.close()
        except OSError:
            pass
        logger.info(f"端口 {self.port} 客户端断开：{addr}")
        self._notify_change()


class TcpService:
    """
    多端口 TCP 服务管理器。

    支持同时监听多个端口，每个端口独立管理客户端和命令队列。
    脚本通过 tcp_recv(port) / tcp_send(port, data) 操作指定端口。
    """

    def __init__(self):
        # port -> _PortListener
        self._listeners: Dict[int, _PortListener] = {}
        self._lock = threading.Lock()
        self._client_change_callback: Optional[Callable] = None

    # ------------------------------------------------------------------
    # 端口管理
    # ------------------------------------------------------------------

    def start(self, port: int) -> bool:
        """启动指定端口的监听。已在运行则直接返回 True。"""
        with self._lock:
            if port in self._listeners and self._listeners[port].is_running:
                return True
            listener = _PortListener(port, on_change_cb=self._on_port_change)
            if not listener.start():
                return False
            self._listeners[port] = listener
        return True

    def stop(self, port: Optional[int] = None):
        """停止指定端口；不传 port 则停止所有端口。"""
        with self._lock:
            if port is not None:
                if port in self._listeners:
                    self._listeners[port].stop()
                    del self._listeners[port]
            else:
                for listener in self._listeners.values():
                    listener.stop()
                self._listeners.clear()

    def is_running(self, port: int) -> bool:
        with self._lock:
            return port in self._listeners and self._listeners[port].is_running

    @property
    def running_ports(self) -> list:
        with self._lock:
            return [p for p, l in self._listeners.items() if l.is_running]

    @property
    def client_count(self) -> int:
        """所有端口的客户端总数。"""
        with self._lock:
            return sum(l.client_count for l in self._listeners.values())

    def client_count_on(self, port: int) -> int:
        with self._lock:
            return self._listeners[port].client_count if port in self._listeners else 0

    def all_clients(self) -> Dict[int, list]:
        """返回 {port: [addr, ...]} 的字典。"""
        with self._lock:
            return {p: l.clients for p, l in self._listeners.items()}

    # ------------------------------------------------------------------
    # 数据收发
    # ------------------------------------------------------------------

    def broadcast(self, data: dict, port: Optional[int] = None):
        """
        向指定端口广播；不传 port 则向所有端口广播。
        脚本中用 tcp_send(port, data) 或 tcp_send(data)。
        """
        with self._lock:
            targets = ([self._listeners[port]] if port and port in self._listeners
                       else list(self._listeners.values()))
        for listener in targets:
            listener.broadcast(data)

    def get_command(self, port: Optional[int] = None) -> Optional[dict]:
        """
        从指定端口的命令队列取一条命令；不传 port 则从所有端口轮询。
        """
        with self._lock:
            if port is not None:
                listener = self._listeners.get(port)
                return listener.get_command() if listener else None
            # 轮询所有端口
            for listener in self._listeners.values():
                cmd = listener.get_command()
                if cmd is not None:
                    return cmd
        return None

    # ------------------------------------------------------------------
    # 回调
    # ------------------------------------------------------------------

    def set_client_change_callback(self, cb) -> None:
        """cb(port, clients) — 某端口客户端列表变化时调用。"""
        self._client_change_callback = cb

    def _on_port_change(self, port: int, clients: list):
        if self._client_change_callback:
            try:
                self._client_change_callback(port, clients)
            except Exception as e:
                logger.warning(f"client_change_callback 异常：{e}")

    # ------------------------------------------------------------------
    # 帧编解码（静态方法，供 _PortListener 使用）
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_frame(data) -> bytes:
        """编码帧。data 为 dict 时用 JSON，为字符串时直接发送纯文本+换行。"""
        if isinstance(data, str):
            return data.encode('utf-8') + b'\n'
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
        return bytes([STX]) + payload + bytes([ETX]) + b'\n'

    @staticmethod
    def _decode_frame(raw: bytes) -> Optional[dict]:
        try:
            stx_idx = raw.index(STX)
            etx_idx = raw.index(ETX, stx_idx + 1)
        except ValueError:
            return None
        payload = raw[stx_idx + 1:etx_idx]
        try:
            return json.loads(payload.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"帧 JSON 解析失败：{e}")
            return None
