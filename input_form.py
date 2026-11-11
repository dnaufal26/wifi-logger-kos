import csv
import os
import sys
from datetime import datetime
from database import insert_complaint, get_connection, init_db

def input_manual_terminal():
    """Form interaktif di terminal untuk mencatat keluhan penghuni."""
    print("\n" + "=" * 50)
    print("📝 FORM CATATAN KELUHAN PENGHUNI (PTS KOST)")
    print("=" * 50)
    
    nama = input("Nama Penghuni (opsional / Enter jika anonim): ").strip()
    if not nama:
        nama = "Anonim"
        
    print("\nPilih Lantai:")
    print("1. Lantai 1 (Area risiko tanpa sinyal seluler)")
    print("2. Lantai 2")
    print("3. Lantai 3")
    pilihan_lantai = input("Pilihan (1/2/3) [Default 1]: ").strip()
    lantai_map = {"1": "Lantai 1", "2": "Lantai 2", "3": "Lantai 3"}
    lantai = lantai_map.get(pilihan_lantai, "Lantai 1")

    print("\nPilih Perangkat:")
    print("1. HP Android")
    print("2. HP iOS (iPhone)")
    print("3. Laptop (Windows/Mac)")
    pilihan_device = input("Pilihan (1/2/3) [Default 1]: ").strip()
    device_map = {"1": "HP Android", "2": "HP iOS", "3": "Laptop"}
    perangkat = device_map.get(pilihan_device, "HP Android")

    gejala = input("\nGejala gangguan (contoh: Tidak bisa buka web / Login ulang): ").strip()
    if not gejala:
        gejala = "Tidak bisa akses internet"

    dampak = input("Dampak (contoh: Kuliah online terganggu / Tugas terhambat): ").strip()
    if not dampak:
        dampak = "Aktivitas terganggu"

    insert_complaint(nama, lantai, perangkat, gejala, dampak)
    print("\n✅ Keluhan berhasil disimpan ke database!")

def import_dari_csv(csv_path):
    """
    Mengimpor keluhan dari file CSV Google Form.
    Format kolom fleksibel menyesuaikan Google Form standar.
    """
    if not os.path.exists(csv_path):
        print(f"❌ File CSV '{csv_path}' tidak ditemukan.")
        return

    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    count = 0
    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Sesuaikan dengan header umum Google Form
            timestamp_raw = row.get("Timestamp") or row.get("Waktu") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            nama = row.get("Nama") or row.get("Nama Lengkap") or "Anonim"
            lantai = row.get("Lantai") or row.get("Posisi Kamar") or "Lantai 1"
            perangkat = row.get("Perangkat") or row.get("Tipe Perangkat") or "HP"
            gejala = row.get("Gejala") or row.get("Keluhan") or "Gangguan internet"
            dampak = row.get("Dampak") or row.get("Dampak Gangguan") or "-"

            cursor.execute("""
                INSERT INTO complaints (timestamp, nama, lantai, perangkat, gejala, dampak)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (timestamp_raw, nama, lantai, perangkat, gejala, dampak))
            count += 1

    conn.commit()
    conn.close()
    print(f"✅ Sukses mengimpor {count} keluhan dari {csv_path} ke database.")

def tampilkan_keluhan_terkini():
    """Melihat daftar keluhan terakhir yang ada di database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, timestamp, nama, lantai, perangkat, gejala, dampak FROM complaints ORDER BY id DESC LIMIT 5")
    rows = cursor.fetchall()
    conn.close()

    print("\n📋 5 KELUHAN TERBARU DI DATABASE:")
    if not rows:
        print("   (Belum ada data keluhan)")
        return

    for r in rows:
        print(f"[{r['timestamp']}] ID #{r['id']} | {r['nama']} ({r['lantai']} - {r['perangkat']}) : {r['gejala']} -> Dampak: {r['dampak']}")

if __name__ == "__main__":
    init_db()
    if len(sys.argv) > 1 and sys.argv[1].endswith(".csv"):
        import_dari_csv(sys.argv[1])
    else:
        input_manual_terminal()
        tampilkan_keluhan_terkini()