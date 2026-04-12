"""Lưu slot kích hoạt: SQLite (mặc định) hoặc MySQL/MariaDB (hosting)."""
from __future__ import annotations

import os
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

# --- SQLite ---

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS activations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    binding_id TEXT NOT NULL,
    machine_fingerprint TEXT NOT NULL,
    key_hint TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(binding_id, machine_fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_activations_binding ON activations(binding_id);
"""


def _sqlite_db_path(root: Path) -> Path:
    raw = (os.getenv("LICENSE_SERVER_DATABASE") or "").strip()
    if raw and not raw.lower().startswith("mysql"):
        return Path(raw)
    return root / "data" / "license_slots.db"


class ActivationsStore(ABC):
    @abstractmethod
    def list_all(self) -> list[dict[str, Any]]:
        ...

    @abstractmethod
    def count_for_binding(self, binding_id: str) -> int:
        ...

    @abstractmethod
    def has_machine(self, binding_id: str, machine_fingerprint: str) -> bool:
        ...

    @abstractmethod
    def insert_activation(
        self,
        binding_id: str,
        machine_fingerprint: str,
        key_hint: str,
        created_at: str,
    ) -> int:
        ...

    @abstractmethod
    def delete_by_binding_and_machine(self, binding_id: str, machine_fingerprint: str) -> int:
        ...

    @abstractmethod
    def delete_by_id(self, row_id: int) -> int:
        ...

    @abstractmethod
    def connection_info(self) -> str:
        ...


class _SQLiteStore(ActivationsStore):
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SQLITE_SCHEMA)
        self._conn.commit()

    def connection_info(self) -> str:
        return f"SQLite: {self._path.resolve()}"

    def list_all(self) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT id, binding_id, machine_fingerprint, key_hint, created_at "
            "FROM activations ORDER BY created_at DESC"
        )
        return [_row_sqlite(r) for r in cur.fetchall()]

    def count_for_binding(self, binding_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM activations WHERE binding_id = ?",
            (binding_id,),
        ).fetchone()
        return int(row["c"]) if row else 0

    def has_machine(self, binding_id: str, machine_fingerprint: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM activations WHERE binding_id = ? AND machine_fingerprint = ? LIMIT 1",
            (binding_id, machine_fingerprint),
        ).fetchone()
        return row is not None

    def insert_activation(
        self,
        binding_id: str,
        machine_fingerprint: str,
        key_hint: str,
        created_at: str,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO activations (binding_id, machine_fingerprint, key_hint, created_at) "
            "VALUES (?, ?, ?, ?)",
            (binding_id, machine_fingerprint, key_hint, created_at),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def delete_by_binding_and_machine(self, binding_id: str, machine_fingerprint: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM activations WHERE binding_id = ? AND machine_fingerprint = ?",
            (binding_id, machine_fingerprint),
        )
        self._conn.commit()
        return cur.rowcount

    def delete_by_id(self, row_id: int) -> int:
        cur = self._conn.execute("DELETE FROM activations WHERE id = ?", (row_id,))
        self._conn.commit()
        return cur.rowcount


def _row_sqlite(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


# --- MySQL ---

_MYSQL_CREATE = """
CREATE TABLE IF NOT EXISTS activations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    binding_id VARCHAR(128) NOT NULL,
    machine_fingerprint VARCHAR(128) NOT NULL,
    key_hint VARCHAR(64) NULL,
    created_at VARCHAR(32) NOT NULL,
    UNIQUE KEY uk_binding_machine (binding_id, machine_fingerprint),
    KEY idx_binding (binding_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


class _MySQLStore(ActivationsStore):
    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        database: str,
        charset: str,
    ):
        import pymysql.cursors

        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._database = database
        self._charset = charset
        self._cursorclass = pymysql.cursors.DictCursor
        import pymysql as _p

        self._pymysql = _p
        self._ensure_schema()

    def connection_info(self) -> str:
        return f"MySQL: {self._user}@{self._host}:{self._port}/{self._database}"

    def _connect(self):
        return self._pymysql.connect(
            host=self._host,
            port=self._port,
            user=self._user,
            password=self._password,
            database=self._database,
            charset=self._charset,
            cursorclass=self._cursorclass,
        )

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(_MYSQL_CREATE)
            conn.commit()
        finally:
            conn.close()

    def list_all(self) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, binding_id, machine_fingerprint, key_hint, created_at "
                    "FROM activations ORDER BY created_at DESC"
                )
                rows = cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def count_for_binding(self, binding_id: str) -> int:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS c FROM activations WHERE binding_id = %s",
                    (binding_id,),
                )
                row = cur.fetchone()
            return int(row["c"]) if row else 0
        finally:
            conn.close()

    def has_machine(self, binding_id: str, machine_fingerprint: str) -> bool:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 AS x FROM activations WHERE binding_id = %s AND machine_fingerprint = %s LIMIT 1",
                    (binding_id, machine_fingerprint),
                )
                return cur.fetchone() is not None
        finally:
            conn.close()

    def insert_activation(
        self,
        binding_id: str,
        machine_fingerprint: str,
        key_hint: str,
        created_at: str,
    ) -> int:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO activations (binding_id, machine_fingerprint, key_hint, created_at) "
                    "VALUES (%s, %s, %s, %s)",
                    (binding_id, machine_fingerprint, key_hint, created_at),
                )
                conn.commit()
                return int(cur.lastrowid)
        finally:
            conn.close()

    def delete_by_binding_and_machine(self, binding_id: str, machine_fingerprint: str) -> int:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM activations WHERE binding_id = %s AND machine_fingerprint = %s",
                    (binding_id, machine_fingerprint),
                )
                conn.commit()
                return cur.rowcount
        finally:
            conn.close()

    def delete_by_id(self, row_id: int) -> int:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM activations WHERE id = %s", (row_id,))
                conn.commit()
                return cur.rowcount
        finally:
            conn.close()


def use_mysql() -> bool:
    d = (os.getenv("LICENSE_DB_DRIVER") or "").strip().lower()
    if d in ("mysql", "mariadb"):
        return True
    return bool((os.getenv("MYSQL_HOST") or "").strip())


def _mysql_from_env() -> _MySQLStore:
    try:
        import pymysql  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "MySQL được bật nhưng chưa cài PyMySQL. Chạy: pip install pymysql"
        ) from exc

    host = (os.getenv("MYSQL_HOST") or "localhost").strip()
    try:
        port = int(os.getenv("MYSQL_PORT", "3306") or "3306")
    except ValueError:
        port = 3306
    user = (os.getenv("MYSQL_USER") or "").strip()
    password = os.getenv("MYSQL_PASSWORD") or ""
    database = (os.getenv("MYSQL_DATABASE") or "").strip()
    if not user or not database:
        raise RuntimeError(
            "MySQL: thiếu MYSQL_USER hoặc MYSQL_DATABASE trong môi trường / .env."
        )
    charset = (os.getenv("MYSQL_CHARSET") or "utf8mb4").strip()
    return _MySQLStore(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset=charset,
    )


_store_singleton: ActivationsStore | None = None


def get_store(root: Path | None = None) -> ActivationsStore:
    """Singleton store (SQLite một connection; MySQL mở connection theo từng thao tác)."""
    global _store_singleton
    if _store_singleton is not None:
        return _store_singleton
    if use_mysql():
        _store_singleton = _mysql_from_env()
    else:
        r = root or Path(__file__).resolve().parent.parent
        _store_singleton = _SQLiteStore(_sqlite_db_path(r))
    return _store_singleton


def reset_store_for_tests() -> None:
    global _store_singleton
    _store_singleton = None


def connect(db_path: Path) -> sqlite3.Connection:
    """Chỉ dùng cho SQLite trực tiếp; ưu tiên get_store()."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SQLITE_SCHEMA)
    conn.commit()
    return conn


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}
