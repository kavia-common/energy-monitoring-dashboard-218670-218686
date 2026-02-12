import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

import psycopg


def _find_repo_root(start: Path) -> Path:
    """
    Walk up directories until we find the monorepo/workspace root (folder that starts with
    'energy-monitoring-dashboard-') or fall back to filesystem root.
    """
    current = start.resolve()
    for _ in range(10):
        if current.name.startswith("energy-monitoring-dashboard-"):
            return current
        if current.parent == current:
            break
        current = current.parent
    return start.resolve()


def _default_db_connection_txt_path() -> Path:
    """
    Locate the database container's db_connection.txt in the sibling workspace.
    Expected structure:
      <repo_root>/energy-monitoring-dashboard-.../energy_monitor_database/db_connection.txt
    """
    repo_root = _find_repo_root(Path(__file__).resolve())
    # We are in .../energy_monitor_backend/src/api/db.py. Sibling container is in a different workspace
    # (energy-monitoring-dashboard-218670-218684) but shares the same parent folder.
    # So: parent_of_this_workspace = repo_root.parent; then search for energy_monitor_database.
    base_parent = repo_root.parent
    candidates = list(base_parent.glob("energy-monitoring-dashboard-*/energy_monitor_database/db_connection.txt"))
    if candidates:
        # Prefer the first match; in this template there should be only one database workspace.
        return candidates[0]
    # Fallback: try relative to backend container root
    backend_root = Path(__file__).resolve().parents[3]  # .../energy_monitor_backend
    fallback = backend_root.parent / "energy_monitor_database" / "db_connection.txt"
    return fallback


def _parse_psql_cmd_to_dsn(psql_cmd: str) -> str:
    """
    Accepts contents like:
      'psql postgresql://user:pass@host:port/dbname'
    Returns the DSN part.
    """
    parts = psql_cmd.strip().split()
    if not parts:
        raise ValueError("db_connection.txt was empty.")
    if len(parts) == 1 and parts[0].startswith("postgres"):
        return parts[0]
    if parts[0] != "psql":
        raise ValueError("db_connection.txt must start with 'psql ...' or contain a postgres DSN.")
    if len(parts) < 2:
        raise ValueError("db_connection.txt must contain a postgres DSN after 'psql'.")
    return parts[1]


# PUBLIC_INTERFACE
def get_database_dsn() -> str:
    """Return PostgreSQL DSN. Prefers env var DATABASE_URL, otherwise parses database container db_connection.txt."""
    env_dsn = os.getenv("DATABASE_URL")
    if env_dsn:
        return env_dsn

    db_conn_path = os.getenv("DB_CONNECTION_TXT")
    path = Path(db_conn_path) if db_conn_path else _default_db_connection_txt_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise RuntimeError(
            f"Could not find db_connection.txt at {path}. "
            "Set DATABASE_URL or DB_CONNECTION_TXT environment variables."
        ) from e

    return _parse_psql_cmd_to_dsn(raw)


@contextmanager
def _connect() -> Generator[psycopg.Connection, None, None]:
    """
    Context manager for a psycopg connection.

    NOTE: Uses autocommit=False; callers must commit/rollback.
    """
    dsn = get_database_dsn()
    conn = psycopg.connect(dsn)
    try:
        yield conn
    finally:
        conn.close()


# PUBLIC_INTERFACE
def fetch_one(query: str, params: Optional[tuple] = None) -> Optional[dict]:
    """Execute a query and return the first row as dict (or None)."""
    with _connect() as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
        conn.rollback()
        return row


# PUBLIC_INTERFACE
def fetch_all(query: str, params: Optional[tuple] = None) -> list[dict]:
    """Execute a query and return all rows as list of dicts."""
    with _connect() as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(query, params or ())
            rows = cur.fetchall()
        conn.rollback()
        return list(rows)


# PUBLIC_INTERFACE
def execute(query: str, params: Optional[tuple] = None) -> int:
    """Execute a statement and return affected rowcount."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or ())
            rowcount = cur.rowcount
        conn.commit()
        return rowcount


# PUBLIC_INTERFACE
def execute_returning_one(query: str, params: Optional[tuple] = None) -> dict:
    """Execute a statement with RETURNING and return the first row as dict."""
    with _connect() as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(query, params or ())
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("RETURNING query returned no row.")
        conn.commit()
        return row
