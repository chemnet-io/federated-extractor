import sqlite3

DB_PATH = "/home/pcarmo/repositories/federated-extractor/system.db"

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        # Table for indexing PDF files
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pdf_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                processed BOOLEAN DEFAULT 0
            )
        ''')
        # Table for storing API tokens (hashed)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT UNIQUE NOT NULL
            )
        ''')
        conn.commit()

def add_pdf(filename):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO pdf_files (filename, processed) VALUES (?, ?)', (filename, False))
        conn.commit()

def save_token_hash(token_hash):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO api_tokens (token_hash) VALUES (?)', (token_hash,))
        conn.commit()

def verify_token_hash(token_hash):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM api_tokens WHERE token_hash = ?', (token_hash,))
        return cursor.fetchone() is not None

def delete_token_by_hash(token_hash):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM api_tokens WHERE token_hash = ?', (token_hash,))
        conn.commit()

def list_token_hashes():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT token_hash FROM api_tokens')
        return [row[0] for row in cursor.fetchall()]
