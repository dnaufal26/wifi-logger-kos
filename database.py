import os
import sqlite3
from contextlib import closing

DB_PATH = os.path.abspath(os.environ.get(
    "WIFI_LOG_DB", os.path.join(os.path.dirname(__file__), "data", "wifi_log.db")
))
DB_DIR = os.path.dirname(DB_PATH)

def get_connection():
    """Membuka koneksi ke SQLite database."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Siapkan tabel dan tambahkan kolom probe ke skema lama."""
    with closing(get_connection()) as conn, conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        # 1. Tabel log hasil ping berkala (setiap 5 detik)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ping_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            router_ping REAL,          -- RTT ke router dalam ms (NULL jika timeout/loss)
            internet_ping REAL,        -- RTT ke internet/DNS publik (misal 1.1.1.1 atau 8.8.8.8) dalam ms
            status TEXT NOT NULL       -- kode diagnosis pada saat sampel ditulis
        )
        """)

        # Tambahkan kolom baru pada database versi sebelumnya.
        existing_columns = {row["name"] for row in cursor.execute("PRAGMA table_info(ping_logs)")}
        probe_columns = {
            "router_result": "TEXT",
            "internet_result": "TEXT",
            "backup_ping": "REAL",
            "backup_result": "TEXT",
            "tcp_result": "TEXT",
        }
        for name, column_type in probe_columns.items():
            if name not in existing_columns:
                cursor.execute(f"ALTER TABLE ping_logs ADD COLUMN {name} {column_type}")

        # 2. Tabel catatan keluhan dari penghuni kos
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            nama TEXT,
            lantai TEXT,               -- contoh: 'Lantai 1', 'Lantai 2'
            perangkat TEXT,            -- contoh: 'Android', 'iOS', 'Laptop'
            gejala TEXT,               -- contoh: 'Situs tidak bisa dibuka', 'Login ulang terus'
            dampak TEXT                -- contoh: 'Kuliah online terputus'
        )
        """)

        # Index untuk mempercepat query berdasarkan waktu di dashboard
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ping_timestamp ON ping_logs(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_complaint_timestamp ON complaints(timestamp)")

    print("Database SQLite berhasil diinisialisasi di:", DB_PATH)

def insert_ping_log(
    router_ping, internet_ping, status, *, timestamp=None,
    router_result=None, internet_result=None, backup_ping=None,
    backup_result=None, tcp_result=None,
):
    """Menyimpan hasil probe dalam satu sampel."""
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO ping_logs (
                    timestamp, router_ping, internet_ping, status,
                    router_result, internet_result, backup_ping, backup_result, tcp_result
                ) VALUES (COALESCE(?, datetime('now', 'localtime')), ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (timestamp, router_ping, internet_ping, status,
                 router_result, internet_result, backup_ping, backup_result, tcp_result),
            )
    finally:
        conn.close()


def insert_complaint(nama, lantai, perangkat, gejala, dampak):
    """Menyimpan keluhan penghuni kos ke tabel complaints."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO complaints (timestamp, nama, lantai, perangkat, gejala, dampak)
        VALUES (datetime('now', 'localtime'), ?, ?, ?, ?, ?)
    """, (nama, lantai, perangkat, gejala, dampak))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
