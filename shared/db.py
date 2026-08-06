import os
from pathlib import Path
import sqlite3


REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("EXTRACTOR_DB_PATH", REPO_ROOT / "system.db"))

VALID_ROLES = ("reader", "writer", "admin")
DEFAULT_ROLE = "reader"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def normalize_role(role: str) -> str:
    """Normalize and validate an application API-token role."""
    normalized_role = role.strip().lower()

    if normalized_role not in VALID_ROLES:
        allowed_roles = ", ".join(VALID_ROLES)
        raise ValueError(
            f"Invalid role '{role}'. Expected one of: {allowed_roles}"
        )

    return normalized_role


def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()

        # Table for indexing PDF files
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pdf_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                processed BOOLEAN DEFAULT 0
            )
            """
        )

        # Table for storing hashed API tokens and their application roles.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL DEFAULT 'reader'
                    CHECK (role IN ('reader', 'writer', 'admin'))
            )
            """
        )

        # Migrate databases created before Task 3B. Existing tokens receive
        # the least-privileged role.
        token_columns = {
            row[1]
            for row in cursor.execute("PRAGMA table_info(api_tokens)")
        }

        if "role" not in token_columns:
            cursor.execute(
                """
                ALTER TABLE api_tokens
                ADD COLUMN role TEXT NOT NULL DEFAULT 'reader'
                    CHECK (role IN ('reader', 'writer', 'admin'))
                """
            )

        conn.commit()


def add_pdf(filename):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO pdf_files (filename, processed) VALUES (?, ?)",
            (filename, False),
        )
        conn.commit()


def save_token_hash(token_hash, role=DEFAULT_ROLE):
    normalized_role = normalize_role(role)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO api_tokens (token_hash, role) VALUES (?, ?)",
            (token_hash, normalized_role),
        )
        conn.commit()


def get_token_role(token_hash):
    """Return the role associated with a token hash, or None."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role FROM api_tokens WHERE token_hash = ?",
            (token_hash,),
        )
        row = cursor.fetchone()
        return row[0] if row else None


def verify_token_hash(token_hash):
    """Preserve the existing boolean token-verification interface."""
    return get_token_role(token_hash) is not None


def delete_token_by_hash(token_hash):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM api_tokens WHERE token_hash = ?",
            (token_hash,),
        )
        conn.commit()


def list_token_hashes():
    """Preserve the existing token-listing interface."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT token_hash FROM api_tokens ORDER BY id")
        return [row[0] for row in cursor.fetchall()]


def list_token_records():
    """Return token hashes together with their roles."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT token_hash, role FROM api_tokens ORDER BY id"
        )
        return cursor.fetchall()
