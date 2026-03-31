"""
操作日志面板

显示在摄像头预览区域下方，支持实时追加和历史查询。
权限规则：
  管理员  -> 查看所有用户记录
  技术员  -> 查看自己 + 所有操作员记录
  操作员  -> 仅查看自己的记录
"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
import threading

from managers.audit_log_manager import AuditLogManager


# 日志级别颜色
_LEVEL_COLORS = {
    "成功": "#1a7a1a",
    "失败": "#cc2200",
    "警告": "#b86000",
}
_DEFAULT_FG = "#333333"


class AuditLogPanel:
    """操作日志面板"""

    def __init__(self, parent: tk.Widget, viewer_name: str, viewer_role: str):
        self.parent = parent
        self.viewer_name = viewer_name
        self.viewer_role = viewer_role
        self._manager = AuditLogManager()

        self.frame = tk.Frame(parent, bg="#f5f5f5")
        self._build_ui()
        self._load_recent()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self):
        # 标题栏
        header = tk.Frame(self.frame, bg="#2c3e50", height=26)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header, text="操作日志", font=("Microsoft YaHei UI", 9, "bold"),
            fg="white", bg="#2c3e50"
        ).pack(side=tk.LEFT, padx=8)

        # 右侧按钮区
        btn_cfg = dict(font=("Microsoft YaHei UI", 8), relief=tk.FLAT,
                       bd=0, cursor="hand2", padx=6, pady=1)

        # 仅管理员显示清理按钮
        if self.viewer_role == "管理员":
            tk.Button(
                header, text="清理日志", bg="#e74c3c", fg="white",
                command=self._on_clear_logs, **btn_cfg
            ).pack(side=tk.RIGHT, padx=4, pady=3)

        tk.Button(
            header, text="刷新", bg="#3498db", fg="white",
            command=self._load_recent, **btn_cfg
        ).pack(side=tk.RIGHT, padx=2, pady=3)

        # 搜索栏
        search_bar = tk.Frame(self.frame, bg="#ecf0f1", pady=3)
        search_bar.pack(fill=tk.X, padx=4)

        tk.Label(search_bar, text="搜索:", bg="#ecf0f1",
                 font=("Microsoft YaHei UI", 8)).pack(side=tk.LEFT, padx=(4, 2))
        self._search_var = tk.StringVar()
        search_entry = tk.Entry(search_bar, textvariable=self._search_var,
                                font=("Microsoft YaHei UI", 8), width=20,
                                relief=tk.SOLID, bd=1)
        search_entry.pack(side=tk.LEFT, padx=2)
        search_entry.bind("<Return>", lambda e: self._load_recent())

        tk.Button(
            search_bar, text="查询", font=("Microsoft YaHei UI", 8),
            relief=tk.FLAT, bd=0, cursor="hand2", padx=6,
            bg="#3498db", fg="white", command=self._load_recent
        ).pack(side=tk.LEFT, padx=4)

        # 日志表格
        table_frame = tk.Frame(self.frame, bg="#f5f5f5")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        cols = ("时间", "用户", "角色", "操作类型", "具体动作", "目标对象", "结果", "IP")
        self._tree = ttk.Treeview(
            table_frame, columns=cols, show="headings",
            selectmode="browse", height=6
        )

        col_widths = {
            "时间": 130, "用户": 80, "角色": 60,
            "操作类型": 90, "具体动作": 110, "目标对象": 100,
            "结果": 50, "IP": 110
        }
        for col in cols:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=col_widths.get(col, 80),
                              minwidth=40, anchor="w")

        # 滚动条
        vsb = ttk.Scrollbar(table_frame, orient=tk.VERTICAL,
                            command=self._tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL,
                            command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self._tree.pack(fill=tk.BOTH, expand=True)

        # 行颜色标签
        self._tree.tag_configure("success", foreground=_LEVEL_COLORS["成功"])
        self._tree.tag_configure("fail",    foreground=_LEVEL_COLORS["失败"])
        self._tree.tag_configure("warn",    foreground=_LEVEL_COLORS["警告"])
        self._tree.tag_configure("even",    background="#f9f9f9")
        self._tree.tag_configure("odd",     background="#ffffff")

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    def _load_recent(self):
        """从数据库加载最近日志（在后台线程执行，避免阻塞 UI）"""
        keyword = self._search_var.get().strip() if hasattr(self, "_search_var") else ""
        threading.Thread(
            target=self._fetch_and_render,
            args=(keyword,),
            daemon=True
        ).start()

    def _fetch_and_render(self, keyword: str):
        rows = self._manager.query(
            viewer_name=self.viewer_name,
            viewer_role=self.viewer_role,
            limit=200,
            keyword=keyword,
        )
        # 回到主线程更新 UI
        self.frame.after(0, lambda: self._render_rows(rows))

    def _render_rows(self, rows: list):
        # 清空旧数据
        for item in self._tree.get_children():
            self._tree.delete(item)

        for i, r in enumerate(rows):
            ts_str = AuditLogManager.format_ts(r["timestamp"])
            result = r["operation_result"]
            tag_result = "success" if result == "成功" else "fail"
            tag_row = "even" if i % 2 == 0 else "odd"
            self._tree.insert(
                "", tk.END,
                values=(
                    ts_str,
                    r["user_name"],
                    r["user_role"],
                    r["operation_type"],
                    r["operation_action"],
                    r["target_object"],
                    result,
                    r["ip_address"],
                ),
                tags=(tag_result, tag_row),
            )

    # ------------------------------------------------------------------
    # 实时追加（由主窗口调用，无需刷新全表）
    # ------------------------------------------------------------------
    def append_log(
        self,
        user_name: str,
        user_role: str,
        operation_type: str,
        operation_action: str,
        target_object: str = "",
        old_value: str = "",
        new_value: str = "",
        operation_result: str = "成功",
        ip_address: str = "",
    ):
        """
        写入数据库并实时追加到表格顶部。
        此方法可在任意线程调用。
        """
        # 写库
        self._manager.log(
            user_name=user_name,
            user_role=user_role,
            operation_type=operation_type,
            operation_action=operation_action,
            target_object=target_object,
            old_value=old_value,
            new_value=new_value,
            operation_result=operation_result,
            ip_address=ip_address or "",
        )
        # 刷新表格（回主线程）
        self.frame.after(0, self._load_recent)

    # ------------------------------------------------------------------
    # 清理日志（管理员）
    # ------------------------------------------------------------------
    def _on_clear_logs(self):
        if self.viewer_role != "管理员":
            messagebox.showwarning("权限不足", "仅管理员可清理日志")
            return

        choice = messagebox.askyesnocancel(
            "清理日志",
            "选择清理范围：\n\n"
            "  是(Yes)  → 清理 90 天前的记录\n"
            "  否(No)   → 清理全部记录\n"
            "  取消     → 放弃操作",
        )
        if choice is None:
            return

        before_days = 90 if choice else None
        ok, msg = self._manager.clear_logs(
            operator_name=self.viewer_name,
            operator_role=self.viewer_role,
            before_days=before_days,
        )
        if ok:
            messagebox.showinfo("清理完成", msg)
        else:
            messagebox.showerror("清理失败", msg)
        self._load_recent()
