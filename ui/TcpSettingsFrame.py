"""
TCP 配置界面（多端口版本）

支持同时监听多个端口，每个端口独立启停，左侧显示 AppVar 变量树。
需求: 1.1, 1.3, 1.4, 2.5, 5.3, 7.4, 11.1-11.5, 14.1-14.3
"""

import json
import logging
import os
import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable

import config

logger = logging.getLogger(__name__)

_CONFIG_DIR = os.path.dirname(os.path.abspath(config.__file__))
TCP_CONFIG_FILE = os.path.join(_CONFIG_DIR, "tcp_config.json")

SYSTEM_VARS = ["Result", "CardNumber", "Confidence", "Timestamp", "RunMode", "TcpClients"]
BUILTIN_FUNCS = ["tcp_send", "tcp_recv", "trigger_capture", "reset_stats", "log"]


class TcpSettingsFrame(tk.Frame):
    """TCP 多端口配置面板，内嵌在左侧侧边栏。"""

    def __init__(self, parent, tcp_service, script_engine=None,
                 save_callback: Optional[Callable] = None,
                 back_callback: Optional[Callable] = None):
        super().__init__(parent, bg="white")
        self._tcp_service = tcp_service
        self._script_engine = script_engine
        self._save_callback = save_callback
        self._back_callback = back_callback
        self._port_frames: dict = {}  # port -> dict of widgets
        self._create_ui()
        self.load_config()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _create_ui(self):
        # 顶部：标题 + 返回按钮
        header = tk.Frame(self, bg="white")
        header.pack(fill=tk.X, padx=(10, 5), pady=5)
        tk.Label(header, text="通信设置", font=("Microsoft YaHei UI", 11, "bold"),
                 bg="white", fg="#0055A4").pack(side=tk.LEFT)
        if self._back_callback:
            tk.Button(header, text="← 返回",
                      font=("Microsoft YaHei UI", 8),
                      bg="#F0F0F0", relief=tk.FLAT, cursor="hand2",
                      command=self._back_callback).pack(side=tk.RIGHT)
        tk.Frame(self, bg="#E0E0E0", height=1).pack(fill=tk.X, padx=(10, 5), pady=(0, 6))

        # 添加端口行
        add_frame = tk.Frame(self, bg="white")
        add_frame.pack(fill=tk.X, padx=12, pady=(0, 4))
        tk.Label(add_frame, text="新增端口：", bg="white",
                 font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT)
        self._new_port_var = tk.StringVar(value="5024")
        tk.Entry(add_frame, textvariable=self._new_port_var, width=7,
                 font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(add_frame, text="添加", font=("Microsoft YaHei UI", 8),
                  bg="#5B9BD5", fg="white", relief="raised", cursor="hand2",
                  command=self._on_add_port).pack(side=tk.LEFT)

        self._interval_var = tk.StringVar(value="100")

        # 端口列表容器（可滚动）
        ports_outer = tk.LabelFrame(self, text="端口列表", bg="white",
                                    font=("Microsoft YaHei UI", 9, "bold"),
                                    padx=4, pady=4)
        ports_outer.pack(fill=tk.X, padx=12, pady=(0, 4))
        self._ports_container = tk.Frame(ports_outer, bg="white")
        self._ports_container.pack(fill=tk.X)

        # AppVar 变量树
        vf = tk.LabelFrame(self, text="AppVar", bg="white",
                           font=("Microsoft YaHei UI", 9, "bold"), padx=6, pady=4)
        vf.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))
        tree_sb = tk.Scrollbar(vf)
        tree_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._var_tree = ttk.Treeview(vf, yscrollcommand=tree_sb.set,
                                      show="tree", selectmode="browse")
        self._var_tree.pack(fill=tk.BOTH, expand=True)
        tree_sb.config(command=self._var_tree.yview)
        bot = tk.Frame(vf, bg="white")
        bot.pack(fill=tk.X, pady=(4, 0))
        tk.Button(bot, text="删除", font=("Microsoft YaHei UI", 8),
                  bg="#F0F0F0", relief="raised", cursor="hand2",
                  command=self._on_var_delete).pack(side=tk.RIGHT)

        # 注册回调
        self._tcp_service.set_client_change_callback(self._on_client_change)
        self._build_var_tree()

    def _add_port_row(self, port: int):
        """在端口列表中添加一行端口控件。"""
        if port in self._port_frames:
            return

        row = tk.Frame(self._ports_container, bg="white", pady=2)
        row.pack(fill=tk.X)

        tk.Label(row, text=f":{port}", bg="white", width=6,
                 font=("Consolas", 9, "bold"), fg="#333").pack(side=tk.LEFT)

        status_var = tk.StringVar(value="已停止")
        status_lbl = tk.Label(row, textvariable=status_var, bg="white",
                               fg="#888", font=("Microsoft YaHei UI", 8), width=6)
        status_lbl.pack(side=tk.LEFT)

        btn_start = tk.Button(row, text="启动", width=4,
                              bg="#4CAF50", fg="white",
                              font=("Microsoft YaHei UI", 8), relief="raised",
                              cursor="hand2",
                              command=lambda p=port: self._on_start(p))
        btn_start.pack(side=tk.LEFT, padx=(2, 1))

        btn_stop = tk.Button(row, text="停止", width=4,
                             bg="#F44336", fg="white",
                             font=("Microsoft YaHei UI", 8), relief="raised",
                             cursor="hand2", state=tk.DISABLED,
                             command=lambda p=port: self._on_stop(p))
        btn_stop.pack(side=tk.LEFT, padx=(1, 2))

        btn_del = tk.Button(row, text="✕", width=2,
                            bg="#F0F0F0", font=("Microsoft YaHei UI", 8),
                            relief="flat", cursor="hand2",
                            command=lambda p=port: self._on_remove_port(p))
        btn_del.pack(side=tk.LEFT)

        self._port_frames[port] = {
            "row": row,
            "status_var": status_var,
            "status_lbl": status_lbl,
            "btn_start": btn_start,
            "btn_stop": btn_stop,
        }
        self._rebuild_tcp_nodes()

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _on_add_port(self):
        try:
            port = int(self._new_port_var.get())
        except ValueError:
            return
        self._add_port_row(port)
        self.save_config()

    def _on_remove_port(self, port: int):
        if port in self._port_frames:
            self._on_stop(port)
            self._port_frames[port]["row"].destroy()
            del self._port_frames[port]
        self._rebuild_tcp_nodes()
        self.save_config()

    def _on_start(self, port: int):
        if self._tcp_service.start(port):
            w = self._port_frames.get(port, {})
            if w:
                w["status_var"].set("监听中")
                w["status_lbl"].config(fg="#4CAF50")
                w["btn_start"].config(state=tk.DISABLED)
                w["btn_stop"].config(state=tk.NORMAL)
            # 启动 periodic（只在第一个端口启动时启动一次）
            if self._script_engine and not self._script_engine._periodic_thread:
                try:
                    interval = int(self._interval_var.get())
                    interval = max(10, interval)
                except ValueError:
                    interval = 100
                self._script_engine.start_periodic(interval)
            self._rebuild_tcp_nodes()
            self.save_config()
        else:
            w = self._port_frames.get(port, {})
            if w:
                w["status_var"].set("失败")
                w["status_lbl"].config(fg="#F44336")

    def _on_stop(self, port: int):
        self._tcp_service.stop(port)
        w = self._port_frames.get(port, {})
        if w:
            w["status_var"].set("已停止")
            w["status_lbl"].config(fg="#888")
            w["btn_start"].config(state=tk.NORMAL)
            w["btn_stop"].config(state=tk.DISABLED)
        # 若所有端口都停了，停止 periodic
        if self._script_engine and not self._tcp_service.running_ports:
            self._script_engine.stop_periodic()
        self._rebuild_tcp_nodes()

    def _on_client_change(self, port: int, clients: list):
        self.after(0, self._rebuild_tcp_nodes)

    # ------------------------------------------------------------------
    # AppVar 变量树
    # ------------------------------------------------------------------

    def _build_var_tree(self):
        t = self._var_tree
        for item in t.get_children():
            t.delete(item)

        root = t.insert("", "end", text="📁 AppVar", open=True)

        # TCP 端口节点（动态）
        self._tcp_root_node = t.insert(root, "end", text="📡 TCP 端口", open=True)

        # Global 系统变量
        global_node = t.insert(root, "end", text="📁 Global", open=True)
        descs = {
            "Result": "int  1=Pass/2=Recycle/3=Reject",
            "CardNumber": "str  识别卡号",
            "Confidence": "float  置信度",
            "Timestamp": "str  时间戳",
            "RunMode": "int  0=运行/1=停止",
            "TcpClients": "int  连接总数",
        }
        for name in SYSTEM_VARS:
            t.insert(global_node, "end", text=f"◆ {name}  ({descs.get(name, '')})")

        # 用户变量
        self._user_node = t.insert(root, "end", text="📁 用户变量", open=False)
        self._refresh_user_vars()
        self._rebuild_tcp_nodes()

    def _rebuild_tcp_nodes(self):
        """重建 TCP 端口子节点。"""
        if not hasattr(self, '_tcp_root_node'):
            return
        t = self._var_tree
        for child in t.get_children(self._tcp_root_node):
            t.delete(child)
        all_clients = self._tcp_service.all_clients()
        for port in sorted(self._port_frames.keys()):
            is_up = self._tcp_service.is_running(port)
            status = "🟢" if is_up else "⚫"
            port_node = t.insert(self._tcp_root_node, "end",
                                 text=f"{status} TcpP{port} : port {port}",
                                 open=True)
            for addr in all_clients.get(port, []):
                label = f"  ◆ {addr[0]}:{addr[1]}" if isinstance(addr, (tuple, list)) else f"  ◆ {addr}"
                t.insert(port_node, "end", text=label)

    def _refresh_user_vars(self):
        if not hasattr(self, '_user_node') or not self._script_engine:
            return
        t = self._var_tree
        for child in t.get_children(self._user_node):
            t.delete(child)
        for name in sorted(self._script_engine.get_user_vars().keys()):
            t.insert(self._user_node, "end", text=f"◆ {name}")

    def _on_var_delete(self):
        sel = self._var_tree.selection()
        if not sel:
            return
        item = sel[0]
        parent = self._var_tree.parent(item)
        if hasattr(self, '_user_node') and parent == self._user_node:
            name = self._var_tree.item(item, "text").lstrip("◆ ").split()[0]
            self._var_tree.delete(item)
            if self._script_engine and name in self._script_engine._user_vars:
                del self._script_engine._user_vars[name]

    # ------------------------------------------------------------------
    # 配置持久化
    # ------------------------------------------------------------------

    def load_config(self):
        try:
            with open(TCP_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            ports = data.get("ports", [config.TCP_SETTINGS.get("port", 5024)])
            interval = data.get("periodic_interval_ms", 100)
        except (FileNotFoundError, json.JSONDecodeError):
            ports = [config.TCP_SETTINGS.get("port", 5024)]
            interval = 100
        self._interval_var.set(str(interval))
        for port in ports:
            self._add_port_row(port)

    def save_config(self):
        ports = list(self._port_frames.keys())
        try:
            interval = int(self._interval_var.get())
        except ValueError:
            interval = 100
        try:
            with open(TCP_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"ports": ports, "periodic_interval_ms": interval,
                           "auto_start": False}, f, indent=2)
        except OSError as e:
            logger.warning(f"保存 TCP 配置失败：{e}")
