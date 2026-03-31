"""
脚本编辑器界面

提供图形化脚本编辑功能，包含触发点选择、变量/函数树形列表、
脚本编辑区、语法检查和测试执行功能。

需求: 10.1 ~ 10.7
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable


class ScriptEditorFrame(tk.Frame):
    """
    脚本编辑器面板，内嵌在主界面内容区（不弹窗）。

    构造参数
    ----------
    parent : tk.Widget
        父容器
    script_engine : ScriptEngine
        脚本引擎实例，用于语法检查、测试执行和获取用户变量
    save_callback : callable, optional
        保存回调 ``save_callback(scripts_dict)``，由 InspectMainWindow 注入，
        用于将脚本写入 Solution 文件
    """

    # 四个触发点（与 ScriptEngine.TRIGGER_POINTS 保持一致）
    TRIGGER_POINTS = [
        "solution_initialize",
        "pre_image_process",
        "post_image_process",
        "periodic",
    ]

    # 系统变量（静态，需求 6.1）
    SYSTEM_VARS = [
        "Result",
        "CardNumber",
        "Confidence",
        "Timestamp",
        "RunMode",
        "TcpClients",
    ]

    # 内置函数（静态，需求 8）
    BUILTIN_FUNCS = [
        "tcp_send",
        "tcp_recv",
        "trigger_capture",
        "reset_stats",
        "log",
    ]

    def __init__(self, parent, script_engine, save_callback: Optional[Callable] = None):
        super().__init__(parent, bg="white")
        self._engine = script_engine
        self._save_callback = save_callback

        # 每个触发点的脚本内容缓存
        self._scripts: dict[str, str] = {t: "" for t in self.TRIGGER_POINTS}
        self._periodic_interval_ms: int = 100

        # 当前选中的触发点
        self._current_trigger = tk.StringVar(value=self.TRIGGER_POINTS[0])

        self._create_ui()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _create_ui(self) -> None:
        """构建整体 UI 布局。"""
        # ── 顶部工具栏 ──────────────────────────────────────────────
        self._create_toolbar()

        # ── 中间主体（左侧树 + 右侧编辑区）────────────────────────
        body = tk.Frame(self, bg="white")
        body.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 4))

        self._create_tree_panel(body)
        self._create_editor_panel(body)

        # ── 底部按钮行 + 输出框 ─────────────────────────────────────
        self._create_bottom_panel()

    def _create_toolbar(self) -> None:
        """顶部：触发点下拉框 + periodic 间隔输入框。"""
        bar = tk.Frame(self, bg="white", pady=6)
        bar.pack(fill=tk.X, padx=6)

        # 触发点标签
        tk.Label(bar, text="触发点：", bg="white",
                 font=("Microsoft YaHei UI", 10)).pack(side=tk.LEFT)

        # 触发点下拉框（需求 10.1）
        self._combo_trigger = ttk.Combobox(
            bar,
            textvariable=self._current_trigger,
            values=self.TRIGGER_POINTS,
            state="readonly",
            width=24,
            font=("Microsoft YaHei UI", 10),
        )
        self._combo_trigger.pack(side=tk.LEFT, padx=(0, 16))
        self._combo_trigger.bind("<<ComboboxSelected>>", self._on_trigger_change)

        # periodic 间隔标签（需求 10.6）
        self._lbl_interval = tk.Label(bar, text="间隔（ms）：", bg="white",
                                      font=("Microsoft YaHei UI", 10))
        self._lbl_interval.pack(side=tk.LEFT)

        # periodic 间隔输入框（默认 100ms）
        self._var_interval = tk.StringVar(value="100")
        self._entry_interval = tk.Entry(
            bar,
            textvariable=self._var_interval,
            width=6,
            font=("Microsoft YaHei UI", 10),
            relief="solid",
            bd=1,
        )
        self._entry_interval.pack(side=tk.LEFT)

        # 初始状态：仅 periodic 触发点时启用间隔输入框
        self._refresh_interval_state()

    def _create_tree_panel(self, parent: tk.Frame) -> None:
        """左侧：变量/函数树形列表（需求 10.2）。"""
        left = tk.Frame(parent, bg="white", width=180)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 4))
        left.pack_propagate(False)

        tk.Label(left, text="变量 / 函数", bg="white",
                 font=("Microsoft YaHei UI", 9, "bold"),
                 fg="#555555").pack(anchor="w", pady=(2, 2))

        # Treeview + 滚动条
        tree_frame = tk.Frame(left, bg="white")
        tree_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree = ttk.Treeview(
            tree_frame,
            yscrollcommand=scrollbar.set,
            selectmode="browse",
            show="tree",  # 只显示树形，不显示列标题
        )
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self._tree.yview)

        # 构建静态节点
        self._node_sys = self._tree.insert("", "end", text="系统变量", open=True)
        self._node_user = self._tree.insert("", "end", text="用户变量", open=True)
        self._node_func = self._tree.insert("", "end", text="内置函数", open=True)

        # 填充系统变量（静态）
        for var in self.SYSTEM_VARS:
            self._tree.insert(self._node_sys, "end", text=var, tags=("leaf",))

        # 填充内置函数（静态）
        for func in self.BUILTIN_FUNCS:
            self._tree.insert(self._node_func, "end", text=func, tags=("leaf",))

        # 刷新用户变量（动态）
        self._refresh_user_vars()

        # 双击叶节点插入到编辑区（需求 10.3）
        self._tree.bind("<Double-1>", self._on_tree_double_click)

        # 刷新用户变量按钮
        btn_refresh = tk.Button(
            left,
            text="↻ 刷新变量",
            bg="#f0f0f0",
            fg="#333",
            font=("Microsoft YaHei UI", 8),
            relief="flat",
            cursor="hand2",
            command=self._refresh_user_vars,
        )
        btn_refresh.pack(fill=tk.X, pady=(4, 0))

    def _create_editor_panel(self, parent: tk.Frame) -> None:
        """右侧：脚本编辑区（等宽字体，需求 10）。"""
        right = tk.Frame(parent, bg="white")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(right, text="脚本编辑区", bg="white",
                 font=("Microsoft YaHei UI", 9, "bold"),
                 fg="#555555").pack(anchor="w", pady=(2, 2))

        editor_frame = tk.Frame(right, bg="white")
        editor_frame.pack(fill=tk.BOTH, expand=True)

        # 行号 + 编辑区水平/垂直滚动条
        v_scroll = ttk.Scrollbar(editor_frame, orient=tk.VERTICAL)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        h_scroll = ttk.Scrollbar(editor_frame, orient=tk.HORIZONTAL)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)

        self._text_editor = tk.Text(
            editor_frame,
            font=("Courier New", 11),
            bg="white",
            fg="#1a1a1a",
            insertbackground="#333",
            selectbackground="#b3d7ff",
            wrap=tk.NONE,
            undo=True,
            yscrollcommand=v_scroll.set,
            xscrollcommand=h_scroll.set,
            relief="solid",
            bd=1,
        )
        self._text_editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll.config(command=self._text_editor.yview)
        h_scroll.config(command=self._text_editor.xview)

    def _create_bottom_panel(self) -> None:
        """底部：按钮行 + 输出文本框。"""
        bottom = tk.Frame(self, bg="white")
        bottom.pack(fill=tk.X, padx=6, pady=(0, 6))

        # 按钮行
        btn_row = tk.Frame(bottom, bg="white")
        btn_row.pack(fill=tk.X, pady=(0, 4))

        btn_style = dict(
            font=("Microsoft YaHei UI", 10),
            relief="raised",
            cursor="hand2",
            padx=10,
            pady=3,
        )

        tk.Button(btn_row, text="检查语法", bg="#5B9BD5", fg="white",
                  command=self._on_check_syntax, **btn_style).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(btn_row, text="测试执行", bg="#70AD47", fg="white",
                  command=self._on_test_execute, **btn_style).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(btn_row, text="保存", bg="#ED7D31", fg="white",
                  command=self._on_save, **btn_style).pack(side=tk.LEFT)

        # 输出文本框（带滚动条）
        output_frame = tk.Frame(bottom, bg="white")
        output_frame.pack(fill=tk.X)

        tk.Label(output_frame, text="输出：", bg="white",
                 font=("Microsoft YaHei UI", 9, "bold"),
                 fg="#555555").pack(anchor="w")

        out_inner = tk.Frame(output_frame, bg="white")
        out_inner.pack(fill=tk.X)

        out_scroll = ttk.Scrollbar(out_inner, orient=tk.VERTICAL)
        out_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._text_output = tk.Text(
            out_inner,
            height=5,
            font=("Courier New", 10),
            bg="#f8f8f8",
            fg="#333",
            state=tk.DISABLED,
            relief="solid",
            bd=1,
            wrap=tk.WORD,
            yscrollcommand=out_scroll.set,
        )
        self._text_output.pack(side=tk.LEFT, fill=tk.X, expand=True)
        out_scroll.config(command=self._text_output.yview)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _refresh_interval_state(self) -> None:
        """根据当前触发点启用/禁用 periodic 间隔输入框。"""
        is_periodic = self._current_trigger.get() == "periodic"
        state = tk.NORMAL if is_periodic else tk.DISABLED
        self._entry_interval.config(state=state)

    def _refresh_user_vars(self) -> None:
        """从 script_engine 刷新用户变量节点（需求 10.2）。"""
        # 清空旧的用户变量子节点
        for child in self._tree.get_children(self._node_user):
            self._tree.delete(child)

        user_vars = self._engine.get_user_vars()
        for var_name in sorted(user_vars.keys()):
            self._tree.insert(self._node_user, "end", text=var_name, tags=("leaf",))

    def _set_output(self, text: str) -> None:
        """向输出框写入文本（清空后写入）。"""
        self._text_output.config(state=tk.NORMAL)
        self._text_output.delete("1.0", tk.END)
        self._text_output.insert(tk.END, text)
        self._text_output.config(state=tk.DISABLED)
        self._text_output.see(tk.END)

    def _save_current_script(self) -> None:
        """将当前编辑区内容保存到内部缓存。"""
        trigger = self._current_trigger.get()
        code = self._text_editor.get("1.0", tk.END)
        # tk.Text.get 末尾会多一个换行，去掉
        if code.endswith("\n"):
            code = code[:-1]
        self._scripts[trigger] = code

    def _load_script_to_editor(self, trigger: str) -> None:
        """将指定触发点的脚本加载到编辑区。"""
        code = self._scripts.get(trigger, "")
        self._text_editor.delete("1.0", tk.END)
        self._text_editor.insert("1.0", code)

    def _get_periodic_interval(self) -> int:
        """读取 periodic 间隔输入框的值，非法时返回 100。"""
        try:
            val = int(self._var_interval.get())
            return max(1, val)
        except (ValueError, TypeError):
            return 100

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _on_trigger_change(self, event=None) -> None:
        """切换触发点：保存当前脚本，加载新触发点脚本（需求 10.1）。"""
        # 先保存当前编辑区内容（注意：此时 _current_trigger 已经变为新值，
        # 需要在 Combobox 绑定前记录旧值）
        # 由于 <<ComboboxSelected>> 触发时 StringVar 已更新，
        # 我们在每次切换前通过 _save_current_script 保存的是新触发点对应的内容，
        # 因此需要在切换前先保存旧触发点内容。
        # 解决方案：在 _combo_trigger 绑定时先记录旧触发点。
        # 这里通过 _prev_trigger 属性实现。
        prev = getattr(self, "_prev_trigger", self.TRIGGER_POINTS[0])
        # 保存旧触发点的脚本
        code = self._text_editor.get("1.0", tk.END)
        if code.endswith("\n"):
            code = code[:-1]
        self._scripts[prev] = code

        # 更新 _prev_trigger
        new_trigger = self._current_trigger.get()
        self._prev_trigger = new_trigger

        # 加载新触发点脚本
        self._load_script_to_editor(new_trigger)

        # 刷新间隔输入框状态
        self._refresh_interval_state()

    def _on_tree_double_click(self, event=None) -> None:
        """双击树节点：将叶节点名称插入到编辑区光标位置（需求 10.3）。"""
        item = self._tree.focus()
        if not item:
            return
        # 只处理叶节点（有 "leaf" tag 的节点）
        tags = self._tree.item(item, "tags")
        if "leaf" not in tags:
            return
        name = self._tree.item(item, "text")
        if not name:
            return
        # 插入到编辑区当前光标位置
        self._text_editor.insert(tk.INSERT, name)
        self._text_editor.focus_set()

    def _on_check_syntax(self) -> None:
        """检查语法：调用 script_engine.check_syntax()，显示结果（需求 10.4）。"""
        self._save_current_script()
        trigger = self._current_trigger.get()
        code = self._scripts.get(trigger, "")

        ok, msg = self._engine.check_syntax(code)
        if ok:
            self._set_output("✓ 语法检查通过，未发现错误。")
        else:
            self._set_output(f"✗ 语法错误：\n{msg}")

    def _on_test_execute(self) -> None:
        """测试执行：调用 script_engine.test_execute()，显示输出（需求 10.5）。"""
        self._save_current_script()
        trigger = self._current_trigger.get()

        # 先将当前编辑区脚本同步到引擎
        scripts_snapshot = dict(self._scripts)
        self._engine.set_scripts(scripts_snapshot)

        output = self._engine.test_execute(trigger)
        self._set_output(output)

        # 测试执行后刷新用户变量列表
        self._refresh_user_vars()

    def _on_save(self) -> None:
        """保存：收集所有触发点脚本，调用 save_callback（需求 10.7）。"""
        # 先保存当前编辑区内容
        self._save_current_script()

        scripts_dict = self.get_scripts()

        # 同步到引擎
        self._engine.set_scripts({k: v for k, v in scripts_dict.items()
                                   if k in self.TRIGGER_POINTS})

        if self._save_callback is not None:
            self._save_callback(scripts_dict)
            self._set_output("✓ 脚本已保存。")
        else:
            self._set_output("⚠ 未配置保存回调，脚本未写入文件。")

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def load_scripts(self, scripts: dict) -> None:
        """
        从外部加载脚本内容到编辑器（需求 13.2）。

        :param scripts: 包含触发点脚本字符串和可选 ``periodic_interval_ms`` 的字典
        """
        for trigger in self.TRIGGER_POINTS:
            self._scripts[trigger] = scripts.get(trigger, "")

        interval = scripts.get("periodic_interval_ms", 100)
        try:
            self._periodic_interval_ms = int(interval)
        except (ValueError, TypeError):
            self._periodic_interval_ms = 100
        self._var_interval.set(str(self._periodic_interval_ms))

        # 重置到第一个触发点并加载
        self._current_trigger.set(self.TRIGGER_POINTS[0])
        self._prev_trigger = self.TRIGGER_POINTS[0]
        self._load_script_to_editor(self.TRIGGER_POINTS[0])
        self._refresh_interval_state()

    def get_scripts(self) -> dict:
        """
        返回当前所有触发点脚本内容和 periodic_interval_ms。

        :return: 包含四个触发点脚本字符串和 ``periodic_interval_ms`` 的字典
        """
        # 确保当前编辑区内容已同步
        self._save_current_script()
        result = dict(self._scripts)
        result["periodic_interval_ms"] = self._get_periodic_interval()
        return result
