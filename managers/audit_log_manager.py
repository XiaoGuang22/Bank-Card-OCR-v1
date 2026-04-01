"""
操作日志管理器

使用 SQLite 存储用户操作日志，支持按角色权限过滤查询。
"""

import sqlite3
import os
import time
import socket
from datetime import datetime, timedelta
from threading import Lock


# 日志数据库路径
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DB_PATH = os.path.join(_BASE_DIR, "Logs", "audit_log.db")

# 自动清理配置
AUTO_CLEAN_DAYS = 90          # 保留最近 N 天
AUTO_CLEAN_MAX_MB = 100       # 超过此大小（MB）时触发清理


def _get_local_ip():
    """获取本机 IP 地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class AuditLogManager:
    """操作日志管理器（单例）"""

    _instance = None
    _lock = Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._db_lock = Lock()
        self._ensure_db()

    # ------------------------------------------------------------------
    # 数据库初始化
    # ------------------------------------------------------------------
    def _ensure_db(self):
        """确保数据库目录和表存在"""
        os.makedirs(os.path.dirname(LOG_DB_PATH), exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS operation_log (
                    log_id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_name        TEXT    NOT NULL,
                    user_role        TEXT    NOT NULL,
                    operation_type   TEXT    NOT NULL,
                    operation_action TEXT    NOT NULL,
                    target_object    TEXT,
                    old_value        TEXT,
                    new_value        TEXT,
                    operation_result TEXT    NOT NULL DEFAULT '成功',
                    ip_address       TEXT,
                    timestamp        INTEGER NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_timestamp ON operation_log(timestamp)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user ON operation_log(user_name)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_role ON operation_log(user_role)"
            )
            conn.commit()

    def _connect(self):
        return sqlite3.connect(LOG_DB_PATH, timeout=10)

    # ------------------------------------------------------------------
    # 写入日志
    # ------------------------------------------------------------------
    def log(
        self,
        user_name: str,
        user_role: str,
        operation_type: str,
        operation_action: str,
        target_object: str = "",
        old_value: str = "",
        new_value: str = "",
        operation_result: str = "成功",
        ip_address: str = None,
    ):
        """写入一条操作日志"""
        if ip_address is None:
            ip_address = _get_local_ip()
        ts = int(time.time())
        with self._db_lock:
            try:
                with self._connect() as conn:
                    conn.execute(
                        """INSERT INTO operation_log
                           (user_name, user_role, operation_type, operation_action,
                            target_object, old_value, new_value, operation_result,
                            ip_address, timestamp)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (user_name, user_role, operation_type, operation_action,
                         target_object or "", old_value or "", new_value or "",
                         operation_result, ip_address, ts),
                    )
                    conn.commit()
                self._auto_clean_if_needed()
            except Exception as e:
                print(f"[AuditLog] 写入失败: {e}")

    # ------------------------------------------------------------------
    # 查询日志（按角色权限过滤）
    # ------------------------------------------------------------------
    def query(
        self,
        viewer_name: str,
        viewer_role: str,
        limit: int = 200,
        keyword: str = "",
        start_ts: int = None,
        end_ts: int = None,
    ) -> list:
        """
        按权限查询日志。
        - 管理员：所有记录
        - 技术员：自己 + 所有操作员的记录
        - 操作员：仅自己的记录
        返回 list[dict]，按时间倒序。
        """
        conditions = []
        params = []

        # 权限过滤
        if viewer_role == "管理员":
            pass  # 无限制
        elif viewer_role == "技术员":
            conditions.append(
                "(user_name = ? OR user_role = '操作员')"
            )
            params.append(viewer_name)
        else:  # 操作员
            conditions.append("user_name = ?")
            params.append(viewer_name)

        # 关键字过滤（支持用户名、角色名、操作类型、具体动作、目标对象）
        if keyword:
            conditions.append(
                "(user_name LIKE ? OR user_role LIKE ? OR operation_type LIKE ? OR "
                "operation_action LIKE ? OR target_object LIKE ?)"
            )
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw, kw, kw])

        # 时间范围
        if start_ts:
            conditions.append("timestamp >= ?")
            params.append(start_ts)
        if end_ts:
            conditions.append("timestamp <= ?")
            params.append(end_ts)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT log_id, user_name, user_role, operation_type, operation_action,
                   target_object, old_value, new_value, operation_result,
                   ip_address, timestamp
            FROM operation_log
            {where}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(limit)

        with self._db_lock:
            try:
                with self._connect() as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(sql, params).fetchall()
                    return [dict(r) for r in rows]
            except Exception as e:
                print(f"[AuditLog] 查询失败: {e}")
                return []

    # ------------------------------------------------------------------
    # 手动清理（仅管理员）
    # ------------------------------------------------------------------
    def clear_logs(
        self,
        operator_name: str,
        operator_role: str,
        before_days: int = None,
    ):
        """
        手动清理日志。
        before_days=None 表示清除全部，否则清除 N 天前的记录。
        """
        if operator_role != "管理员":
            return False, "权限不足，仅管理员可清理日志"

        if before_days is None:
            desc = "全部日志"
            cutoff_ts = int(time.time()) + 1  # 全部
        else:
            cutoff = datetime.now() - timedelta(days=before_days)
            cutoff_ts = int(cutoff.timestamp())
            desc = f"{before_days}天前的日志"

        with self._db_lock:
            try:
                with self._connect() as conn:
                    cur = conn.execute(
                        "DELETE FROM operation_log WHERE timestamp < ?", (cutoff_ts,)
                    )
                    deleted = cur.rowcount
                    conn.commit()
                result = "成功"
                msg = f"已删除 {deleted} 条记录"
            except Exception as e:
                result = "失败"
                msg = str(e)

        # 记录清理操作本身
        self.log(
            user_name=operator_name,
            user_role=operator_role,
            operation_type="log_management",
            operation_action="clear_logs",
            target_object=desc,
            old_value="",
            new_value=msg,
            operation_result=result,
        )
        return result == "成功", msg

    # ------------------------------------------------------------------
    # 自动清理
    # ------------------------------------------------------------------
    def _auto_clean_if_needed(self):
        """超过大小或天数限制时自动清理"""
        try:
            # 检查文件大小
            if os.path.exists(LOG_DB_PATH):
                size_mb = os.path.getsize(LOG_DB_PATH) / (1024 * 1024)
                if size_mb > AUTO_CLEAN_MAX_MB:
                    cutoff = int((datetime.now() - timedelta(days=30)).timestamp())
                    with self._connect() as conn:
                        conn.execute(
                            "DELETE FROM operation_log WHERE timestamp < ?", (cutoff,)
                        )
                        conn.commit()
                    return

            # 检查天数
            cutoff = int((datetime.now() - timedelta(days=AUTO_CLEAN_DAYS)).timestamp())
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM operation_log WHERE timestamp < ?", (cutoff,)
                )
                conn.commit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 格式化时间戳
    # ------------------------------------------------------------------
    @staticmethod
    def format_ts(ts: int) -> str:
        """将 Unix 时间戳格式化为可读字符串"""
        try:
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(ts)
