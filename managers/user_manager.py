"""
用户管理器

使用 SQLite 存储用户信息和密码，替代 users.json
"""

import sqlite3
import os
import hashlib
from threading import Lock


# 用户数据库路径
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_DB_PATH = os.path.join(_BASE_DIR, "Logs", "user.db")


class UserManager:
    """用户管理器（单例）"""

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
        os.makedirs(os.path.dirname(USER_DB_PATH), exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                    username   TEXT    UNIQUE NOT NULL,
                    password   TEXT    NOT NULL,
                    role       TEXT    NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_username ON users(username)"
            )
            conn.commit()

    def _connect(self):
        return sqlite3.connect(USER_DB_PATH, timeout=10)

    @staticmethod
    def _hash_password(password: str) -> str:
        """对密码进行哈希处理"""
        return hashlib.md5(password.encode()).hexdigest()

    # ------------------------------------------------------------------
    # 用户操作
    # ------------------------------------------------------------------
    def add_user(self, username: str, password: str, role: str) -> tuple:
        """添加用户，返回 (success, message)"""
        hashed_password = self._hash_password(password)
        import time
        ts = int(time.time())
        
        with self._db_lock:
            try:
                with self._connect() as conn:
                    conn.execute(
                        """INSERT INTO users (username, password, role, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (username, hashed_password, role, ts, ts)
                    )
                    conn.commit()
                return True, "用户添加成功"
            except sqlite3.IntegrityError:
                return False, "用户名已存在"
            except Exception as e:
                return False, f"添加失败: {e}"

    def delete_user(self, username: str) -> tuple:
        """删除用户，返回 (success, message)"""
        with self._db_lock:
            try:
                with self._connect() as conn:
                    cur = conn.execute("DELETE FROM users WHERE username = ?", (username,))
                    conn.commit()
                    if cur.rowcount > 0:
                        return True, "用户删除成功"
                    else:
                        return False, "用户不存在"
            except Exception as e:
                return False, f"删除失败: {e}"

    def update_user(self, username: str, password: str = None, role: str = None) -> tuple:
        """更新用户信息，返回 (success, message)"""
        import time
        ts = int(time.time())
        
        with self._db_lock:
            try:
                with self._connect() as conn:
                    if password and role:
                        hashed_password = self._hash_password(password)
                        conn.execute(
                            "UPDATE users SET password = ?, role = ?, updated_at = ? WHERE username = ?",
                            (hashed_password, role, ts, username)
                        )
                    elif password:
                        hashed_password = self._hash_password(password)
                        conn.execute(
                            "UPDATE users SET password = ?, updated_at = ? WHERE username = ?",
                            (hashed_password, ts, username)
                        )
                    elif role:
                        conn.execute(
                            "UPDATE users SET role = ?, updated_at = ? WHERE username = ?",
                            (role, ts, username)
                        )
                    else:
                        return False, "没有要更新的内容"
                    
                    conn.commit()
                    if conn.total_changes > 0:
                        return True, "用户更新成功"
                    else:
                        return False, "用户不存在"
            except Exception as e:
                return False, f"更新失败: {e}"

    def get_user(self, username: str) -> dict:
        """获取用户信息，返回 dict 或 None"""
        with self._db_lock:
            try:
                with self._connect() as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT user_id, username, password, role FROM users WHERE username = ?",
                        (username,)
                    ).fetchone()
                    return dict(row) if row else None
            except Exception:
                return None

    def get_all_users(self) -> list:
        """获取所有用户，返回 list[dict]"""
        with self._db_lock:
            try:
                with self._connect() as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute(
                        "SELECT user_id, username, role FROM users ORDER BY username"
                    ).fetchall()
                    return [dict(r) for r in rows]
            except Exception:
                return []

    def verify_password(self, username: str, password: str) -> bool:
        """验证密码是否正确"""
        user = self.get_user(username)
        if not user:
            return False
        hashed_password = self._hash_password(password)
        return user["password"] == hashed_password

    def init_default_users(self):
        """初始化默认用户（仅在数据库为空时调用）"""
        users = self.get_all_users()
        if users:
            return  # 已有用户，不初始化
        
        default_users = [
            ("admin", "1", "管理员"),
            # ("operator", "operator123", "操作员"),
            # ("technician", "tech123", "技术员"),
        ]
        
        for username, password, role in default_users:
            self.add_user(username, password, role)
