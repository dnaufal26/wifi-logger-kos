import sqlite3
import os

DB_DIR = os.path.join(os.path.dirname(__file__), "data")
DB_PATH = os.path.join(DB_DIR, "wifi_log.db")

def get_connection():
    """Membuka koneksi ke SQLite database."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Membuat tabel-tabel yang diperlukan jika belum ada."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Tabel log hasil ping berkala (setiap 5 detik)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ping_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        router_ping REAL,          -- RTT ke router dalam ms (NULL jika timeout/loss)
        internet_ping REAL,        -- RTT ke internet/DNS publik (misal 1.1.1.1 atau 8.8.8.8) dalam ms
        status TEXT NOT NULL       -- 'NORMAL', 'GANGGUAN_LOKAL', 'GANGGUAN_ISP', 'DISCONNECTED'
    )
    """)

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

    conn.commit()
    conn.close()
    print("Database SQLite berhasil diinisialisasi di:", DB_PATH)

def insert_ping_log(router_ping, internet_ping, status):
    """Menyimpan 1 baris hasil observasi ping ke tabel ping_logs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ping_logs (timestamp, router_ping, internet_ping, status)
        VALUES (datetime('now', 'localtime'), ?, ?, ?)
    """, (router_ping, internet_ping, status))
    conn.commit()
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