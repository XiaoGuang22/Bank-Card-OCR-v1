"""
脚本引擎模块

提供 Python 子集脚本执行环境，支持四个触发点、系统变量、用户变量和持久变量。
触发点：solution_initialize、pre_image_process、post_image_process、periodic
"""

import ctypes
import logging
import time
import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from Card_OCR_v1.services.tcp_service import TcpService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 沙箱：安全内置函数白名单（需求 9.1, 9.2）
# ---------------------------------------------------------------------------

SAFE_BUILTINS = {
    name: __builtins__[name] if isinstance(__builtins__, dict) else getattr(__builtins__, name)
    for name in (
        'abs', 'bool', 'dict', 'float', 'int', 'len',
        'list', 'max', 'min', 'print', 'range', 'round',
        'str', 'sum', 'tuple', 'type', 'zip', 'enumerate',
    )
}


class ProtectedNamespace(dict):
    """
    受保护的脚本执行命名空间（需求 6.5）。

    继承自 dict，重写 __setitem__：若赋值目标是系统变量名，则忽略赋值并记录警告。
    """

    def __init__(self, sys_var_names: set, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sys_var_names = sys_var_names

    def __setitem__(self, key, value):
        if key in self._sys_var_names:
            logger.warning(
                f"[ScriptEngine] 脚本尝试修改只读系统变量 '{key}'，已忽略"
            )
            return
        super().__setitem__(key, value)


class ProgNamespace:
    """
    持久变量命名空间（需求 6.4）。

    脚本中通过 ``Prog.x = value`` / ``Prog.x`` 访问持久变量，
    实际存储在 ScriptEngine._prog_vars 字典中。
    """

    def __init__(self, prog_vars: dict):
        # 直接写入 __dict__ 避免触发自定义 __setattr__
        object.__setattr__(self, '_prog_vars', prog_vars)

    def __getattr__(self, name: str):
        prog_vars = object.__getattribute__(self, '_prog_vars')
        try:
            return prog_vars[name]
        except KeyError:
            raise AttributeError(f"Prog 没有属性 '{name}'") from None

    def __setattr__(self, name: str, value):
        prog_vars = object.__getattribute__(self, '_prog_vars')
        prog_vars[name] = value


class ScriptEngine:
    """脚本引擎核心类，管理脚本存储、变量系统和触发点执行。"""

    TRIGGER_POINTS = [
        "solution_initialize",
        "pre_image_process",
        "post_image_process",
        "periodic",
    ]

    def __init__(self, tcp_service):
        """
        初始化脚本引擎。

        :param tcp_service: TcpService 实例，用于内置函数 tcp_send/tcp_recv
        """
        self._tcp_service = tcp_service

        # 各触发点脚本内容，键为触发点名称，值为脚本字符串
        self._scripts: dict[str, str] = {}

        # 系统变量（只读，由引擎自动维护）
        self._sys_vars: dict = {
            "Result": 1,           # int: 1=Pass / 2=Recycle / 3=Reject
            "CardNumber": "",      # str
            "Confidence": 0.0,     # float: 0.0~1.0
            "Timestamp": "",       # str
            "RunMode": 1,          # int: 0=运行中 / 1=已停止
            "TcpClients": 0,       # int
        }

        # 用户自定义变量（脚本中直接赋值创建，无需预先声明）
        self._user_vars: dict = {}

        # 持久变量（以 Prog. 开头，方案切换不清空，程序关闭才清除）
        self._prog_vars: dict = {}

        # 回调函数（由 RunInterface 注入）
        self._trigger_capture_cb = None
        self._reset_stats_cb = None

        # periodic 定时线程状态
        self._periodic_stop_event = threading.Event()
        self._periodic_thread: Optional[threading.Thread] = None

        # 内置函数注入环境（需求 8.1~8.5）
        self._builtins_env = self._build_builtins_env()

    # ------------------------------------------------------------------
    # Script management
    # ------------------------------------------------------------------

    def set_scripts(self, scripts: dict[str, str]) -> None:
        """
        设置各触发点的脚本内容。切换方案时调用，不清空持久变量。

        :param scripts: 触发点名称 -> 脚本字符串 的映射
        """
        self._scripts = {k: v for k, v in scripts.items() if k in self.TRIGGER_POINTS}
        # 注意：_prog_vars 不清空（需求 6.4）

    def get_scripts(self) -> dict[str, str]:
        """返回当前所有触发点的脚本内容副本。"""
        return dict(self._scripts)

    # ------------------------------------------------------------------
    # Variable management
    # ------------------------------------------------------------------

    def update_system_vars(self, **kwargs) -> None:
        """
        更新系统变量。由 RunInterface 在 OCR 识别完成后调用。
        同时自动同步 TcpClients 为当前连接数（需求 6.2）。

        :param kwargs: 要更新的系统变量键值对，键必须是已知系统变量名
        """
        for key, value in kwargs.items():
            if key in self._sys_vars:
                self._sys_vars[key] = value
            else:
                logger.warning(f"update_system_vars: 未知系统变量 '{key}'，已忽略")
        # 自动同步 TcpClients
        self._sys_vars["TcpClients"] = self._tcp_service.client_count

    def get_user_vars(self) -> dict:
        """返回当前用户自定义变量字典副本（供 ScriptEditorFrame 树形列表刷新）。"""
        return dict(self._user_vars)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    @staticmethod
    def _inject_exception(thread_id: int, exc_type: type) -> bool:
        """
        通过 ctypes 向目标线程注入异常（Windows 兼容方式）。

        :param thread_id: 目标线程的 ident
        :param exc_type: 要注入的异常类型
        :return: True 表示注入成功，False 表示失败
        """
        ret = ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_ulong(thread_id),
            ctypes.py_object(exc_type),
        )
        return ret == 1

    def execute(self, trigger: str) -> None:
        """
        执行指定触发点的脚本，带 100ms 超时中断（需求 9.3）。

        若该触发点没有配置脚本，则静默跳过，不产生错误（需求 7.5）。
        脚本在独立 daemon 线程中运行；若 100ms 内未完成，通过 ctypes 注入
        SystemExit 强制中断，记录 warning 后正常返回，不影响调用方。

        :param trigger: 触发点名称，应为 TRIGGER_POINTS 之一
        """
        code = self._scripts.get(trigger, "").strip()
        if not code:
            # 未配置脚本，静默跳过（需求 7.5）
            return

        sys_var_names = set(self._sys_vars.keys())

        # 构建受保护的执行命名空间（需求 6.5, 9.1, 9.2）
        namespace = ProtectedNamespace(sys_var_names)
        # 注入安全内置函数白名单，禁止 open/exec/eval/__import__ 等危险函数
        namespace['__builtins__'] = SAFE_BUILTINS
        # 注入系统变量（只读，ProtectedNamespace 会拦截对这些键的写操作）
        for k, v in self._sys_vars.items():
            dict.__setitem__(namespace, k, v)
        # 注入用户变量
        for k, v in self._user_vars.items():
            dict.__setitem__(namespace, k, v)
        # 注入内置函数（需求 8.1~8.5）：tcp_send、tcp_recv、trigger_capture、reset_stats、log
        for k, v in self._builtins_env.items():
            dict.__setitem__(namespace, k, v)
        # 注入 Prog 持久变量对象（需求 6.4）
        dict.__setitem__(namespace, 'Prog', ProgNamespace(self._prog_vars))

        # 用于从脚本线程回传执行结果
        result_holder: dict = {"namespace": None, "error": None}

        def _run():
            try:
                exec(code, namespace)  # noqa: S102
                result_holder["namespace"] = namespace
            except SystemExit:
                # 超时注入的 SystemExit，静默退出线程
                pass
            except Exception as e:
                result_holder["error"] = e

        script_thread = threading.Thread(target=_run, daemon=True)
        script_thread.start()
        # periodic 触发点允许更长执行时间（500ms），其他触发点 100ms
        timeout = 0.5 if trigger == "periodic" else 0.1
        script_thread.join(timeout=timeout)

        if script_thread.is_alive():
            self._inject_exception(script_thread.ident, SystemExit)
            logger.warning(
                f"[ScriptEngine] 触发点 '{trigger}' 执行超时（>{int(timeout*1000)}ms），已强制中断"
            )
            script_thread.join(timeout=0.05)
            return

        if result_holder["error"] is not None:
            logger.error(
                f"[ScriptEngine] 触发点 '{trigger}' 执行异常：{result_holder['error']}"
            )
            return

        # 将脚本中新增/修改的非系统变量回写到 _user_vars
        final_ns = result_holder["namespace"]
        if final_ns is not None:
            for key, value in final_ns.items():
                if key.startswith("__") or key in sys_var_names or key == 'Prog':
                    continue
                self._user_vars[key] = value

    # ------------------------------------------------------------------
    # Callback injection (to be used by RunInterface)
    # ------------------------------------------------------------------

    def set_trigger_capture_callback(self, cb) -> None:
        """注入 trigger_capture 实现（需求 8.3）。"""
        self._trigger_capture_cb = cb
        # 重建内置函数环境以使新回调生效
        self._builtins_env = self._build_builtins_env()

    def set_reset_stats_callback(self, cb) -> None:
        """注入 reset_stats 实现（需求 8.4）。"""
        self._reset_stats_cb = cb
        # 重建内置函数环境以使新回调生效
        self._builtins_env = self._build_builtins_env()

    # ------------------------------------------------------------------
    # Built-in function environment (需求 8)
    # ------------------------------------------------------------------

    def _build_builtins_env(self) -> dict:
        """
        构建脚本内置函数字典。

        - tcp_send(data, port=None)  → 向指定端口广播，不传 port 则广播所有端口
        - tcp_recv(port=None)        → 从指定端口取一条消息字符串，不传则轮询所有端口
        - trigger_capture()          → 触发拍照
        - reset_stats()              → 重置统计
        - log(msg)                   → 写日志
        """
        def _trigger_capture():
            if self._trigger_capture_cb is not None:
                self._trigger_capture_cb()

        def _reset_stats():
            if self._reset_stats_cb is not None:
                self._reset_stats_cb()

        return {
            'tcp_send':        lambda data, port=None: self._tcp_service.broadcast(data, port),
            'tcp_recv':        self._tcp_recv_str,
            'trigger_capture': _trigger_capture,
            'reset_stats':     _reset_stats,
            'log':             lambda msg: logger.info(f"[Script] {msg}"),
        }

    def _tcp_recv_str(self, port: Optional[int] = None) -> Optional[str]:
        """
        从命令队列取一条命令，返回字符串内容。

        :param port: 指定端口，None 则轮询所有端口
        """
        cmd = self._tcp_service.get_command(port)
        if cmd is None:
            return None
        if isinstance(cmd, dict):
            if 'data' in cmd:
                return str(cmd['data'])
            if len(cmd) == 1:
                return str(next(iter(cmd.values())))
            return str(cmd)
        return str(cmd)

    def start_periodic(self, interval_ms: int = 100) -> None:
        """
        启动 periodic 定时线程（需求 7.4）。

        以 daemon 线程运行，按 interval_ms 毫秒间隔循环调用 execute("periodic")，
        直到 stop_periodic() 被调用。若线程已在运行，先停止旧线程再启动新线程。

        :param interval_ms: 循环间隔，单位毫秒，默认 100ms
        """
        self.stop_periodic()  # 确保旧线程已停止

        self._periodic_stop_event.clear()
        interval_sec = interval_ms / 1000.0

        def _loop():
            while not self._periodic_stop_event.is_set():
                self.execute("periodic")
                self._periodic_stop_event.wait(timeout=interval_sec)

        self._periodic_thread = threading.Thread(target=_loop, daemon=True, name="ScriptEngine-periodic")
        self._periodic_thread.start()
        logger.info(f"[ScriptEngine] periodic 定时线程已启动，间隔 {interval_ms}ms")

    def stop_periodic(self) -> None:
        """
        停止 periodic 定时线程（需求 7.4）。

        设置停止标志并等待线程退出。若线程未运行，则静默返回。
        """
        self._periodic_stop_event.set()
        if self._periodic_thread is not None and self._periodic_thread.is_alive():
            self._periodic_thread.join(timeout=1.0)
            self._periodic_thread = None
            logger.info("[ScriptEngine] periodic 定时线程已停止")


    # ------------------------------------------------------------------
    # Script Editor helpers (需求 10.4, 10.5)
    # ------------------------------------------------------------------

    # 测试执行时使用的模拟系统变量（需求 10.5）
    MOCK_SYS_VARS = {
        'Result': 1,
        'CardNumber': '6225880000000000',
        'Confidence': 0.95,
        'Timestamp': '2026-01-01 00:00:00',
        'RunMode': 0,
        'TcpClients': 0,
    }

    def check_syntax(self, code: str) -> tuple[bool, str]:
        """
        对脚本进行静态语法检查，不执行代码（需求 10.4）。

        :param code: 待检查的 Python 脚本字符串
        :return: (True, '') 表示语法正确；(False, 错误信息) 表示语法错误
        """
        try:
            compile(code, '<string>', 'exec')
            return True, ''
        except SyntaxError as e:
            return False, f"SyntaxError: {e.msg} (第 {e.lineno} 行)"
        except Exception as e:
            return False, str(e)

    def test_execute(self, trigger: str) -> str:
        """
        使用模拟数据执行一次脚本，收集 log()/print() 输出并返回（需求 10.5）。

        - 使用 MOCK_SYS_VARS 替代真实系统变量
        - 捕获 log() 调用和 print() 的输出
        - 不依赖真实相机或 TCP 连接
        - tcp_send/tcp_recv 替换为 no-op，避免真实网络操作

        :param trigger: 触发点名称
        :return: 脚本执行期间所有 log()/print() 输出拼接的字符串
        """
        import io
        import sys

        code = self._scripts.get(trigger, "").strip()
        if not code:
            return "(该触发点没有配置脚本)"

        output_lines: list[str] = []

        # 重定向 stdout 捕获 print() 输出
        captured_stdout = io.StringIO()

        def _mock_log(msg):
            output_lines.append(str(msg))

        def _mock_print(*args, **kwargs):
            sep = kwargs.get('sep', ' ')
            end = kwargs.get('end', '\n')
            text = sep.join(str(a) for a in args) + end
            captured_stdout.write(text)

        sys_var_names = set(self.MOCK_SYS_VARS.keys())

        # 构建受保护的执行命名空间
        namespace = ProtectedNamespace(sys_var_names)
        # 安全内置函数白名单，print 替换为捕获版本
        mock_builtins = dict(SAFE_BUILTINS)
        mock_builtins['print'] = _mock_print
        namespace['__builtins__'] = mock_builtins

        # 注入模拟系统变量
        for k, v in self.MOCK_SYS_VARS.items():
            dict.__setitem__(namespace, k, v)

        # 注入 Prog 持久变量对象
        dict.__setitem__(namespace, 'Prog', ProgNamespace(self._prog_vars))

        # 注入内置函数（tcp_send/tcp_recv 替换为 no-op，log 替换为捕获版本）
        mock_env = {
            'tcp_send':        lambda data: output_lines.append(f"[tcp_send] {data}"),
            'tcp_recv':        lambda: None,
            'trigger_capture': lambda: output_lines.append("[trigger_capture]"),
            'reset_stats':     lambda: output_lines.append("[reset_stats]"),
            'log':             _mock_log,
        }
        for k, v in mock_env.items():
            dict.__setitem__(namespace, k, v)

        # 重定向 sys.stdout 以捕获直接写入 sys.stdout 的输出
        old_stdout = sys.stdout
        sys.stdout = captured_stdout
        try:
            exec(code, namespace)  # noqa: S102
        except Exception as e:
            output_lines.append(f"[执行错误] {type(e).__name__}: {e}")
        finally:
            sys.stdout = old_stdout

        # 合并 print 输出和 log 输出
        print_output = captured_stdout.getvalue()
        if print_output:
            output_lines.extend(print_output.splitlines())

        return '\n'.join(output_lines) if output_lines else "(无输出)"


# ---------------------------------------------------------------------------
# 脚本序列化/反序列化辅助函数（需求 13.1, 13.2, 13.3, 13.4）
# ---------------------------------------------------------------------------

def serialize_scripts(scripts: dict) -> dict:
    """
    将脚本字典序列化为可 JSON 存储的格式（需求 13.1, 13.4）。

    接收包含触发点脚本内容和 ``periodic_interval_ms`` 的字典，
    返回一个新字典，所有值均为 JSON 可序列化类型（str / int）。

    :param scripts: 包含触发点脚本字符串和 ``periodic_interval_ms`` 的字典
    :return: 可直接传给 ``json.dump`` 的字典
    """
    result = {}
    for trigger in ScriptEngine.TRIGGER_POINTS:
        result[trigger] = str(scripts.get(trigger, ""))
    result["periodic_interval_ms"] = int(scripts.get("periodic_interval_ms", 100))
    return result


def deserialize_scripts(data: dict) -> dict:
    """
    从 JSON 数据恢复脚本字典（需求 13.2, 13.3）。

    接收从 JSON 文件读取的字典（可能缺少部分键），返回包含所有四个触发点
    脚本内容（缺失时用空字符串）和 ``periodic_interval_ms``（缺失时用 100）的字典。

    :param data: 从 JSON 读取的原始字典，可能为空或缺少部分键
    :return: 包含所有触发点脚本和 ``periodic_interval_ms`` 的完整字典
    """
    result = {}
    for trigger in ScriptEngine.TRIGGER_POINTS:
        result[trigger] = str(data.get(trigger, ""))
    result["periodic_interval_ms"] = int(data.get("periodic_interval_ms", 100))
    return result
