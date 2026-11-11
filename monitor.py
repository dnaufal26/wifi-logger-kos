import time
import subprocess
import re
import sys
from datetime import datetime
from database import insert_ping_log, init_db

# Konfigurasi Target
ROUTER_IP = "172.16.10.1"      # Default gateway PTS Kost dari ipconfig
INTERNET_TARGET = "1.1.1.1"    # Cloudflare DNS (stabil untuk uji konektivitas ISP)
INTERVAL_DETIK = 5             # Sesuai rancangan proposal: cek tiap 5 detik
TIMEOUT_MS = 2000              # Batas waktu timeout (2 detik)

def ping_host(host, timeout_ms=TIMEOUT_MS):
    """
    Melakukan 1 kali ping ke host target di Windows.
    Mengembalikan latency dalam milidetik (float), atau None jika timeout/loss.
    Metode ini menggunakan ping bawaan Windows sehingga tidak butuh akses root/admin khusus.
    """
    try:
        # Perintah ping Windows: 1 paket (-n 1), batas timeout ms (-w <timeout>)
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), host]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=(timeout_ms / 1000.0) + 1.0)
        
        output = res.stdout
        # Cari pola latensi: "time=XXms" atau "waktu=XXms" atau "time<1ms"
        match = re.search(r'(?:time|waktu)[=<](\d+)ms', output, re.IGNORECASE)
        if match:
            return float(match.group(1))
        
        # Jika time < 1ms, regex di atas menangkap angka 1, tapi jika ada kasus khusus:
        if "<1ms" in output.lower():
            return 0.5
        
        # Jika Destination host unreachable atau Request timed out
        return None
    except Exception:
        return None

def tentukan_status(router_rtt, internet_rtt):
    """
    Memetakan hasil ping ke kategori gangguan sesuai rancangan:
    - Router OK & Internet OK   -> NORMAL
    - Router OK & Internet GAGAL -> GANGGUAN_ISP
    - Router GAGAL & Internet OK -> GANGGUAN_LOKAL (kasus aneh/routing anomali)
    - Router GAGAL & Internet GAGAL -> GANGGUAN_LOKAL (Wi-Fi lokal putus/down)
    """
    if router_rtt is not None and internet_rtt is not None:
        return "NORMAL"
    elif router_rtt is not None and internet_rtt is None:
        return "GANGGUAN_ISP"
    elif router_rtt is None and internet_rtt is not None:
        return "GANGGUAN_LOKAL"
    else:
        return "GANGGUAN_LOKAL"

def main():
    init_db()
    print("=" * 60)
    print("📡 SISTEM PENCATAT GANGGUAN WI-FI KOS (PTS Kost Cisitu)")
    print(f"Target Router   : {ROUTER_IP}")
    print(f"Target Internet : {INTERNET_TARGET}")
    print(f"Interval        : Tiap {INTERVAL_DETIK} detik")
    print("Tekan Ctrl + C di terminal untuk menghentikan monitoring.")
    print("=" * 60)

    count = 0
    try:
        while True:
            waktu_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Lakukan ping ke kedua target
            router_rtt = ping_host(ROUTER_IP)
            internet_rtt = ping_host(INTERNET_TARGET)
            
            # Klasifikasikan status
            status = tentukan_status(router_rtt, internet_rtt)
            
            # Simpan ke SQLite
            insert_ping_log(router_rtt, internet_rtt, status)
            count += 1

            # Format log tampilan di konsol
            r_str = f"{router_rtt:5.1f} ms" if router_rtt is not None else "TIMEOUT "
            i_str = f"{internet_rtt:5.1f} ms" if internet_rtt is not None else "TIMEOUT "
            
            # Beri penanda visual jika ada gangguan
            indikator = "🟢" if status == "NORMAL" else "🔴"
            print(f"[{waktu_str}] #{count:04d} | Router: {r_str} | Internet: {i_str} | Status: {status} {indikator}")
            
            time.sleep(INTERVAL_DETIK)

    except KeyboardInterrupt:
        print("\n\n[INFO] Monitoring dihentikan oleh pengguna. Data tersimpan rapi di SQLite.")
        sys.exit(0)

if __name__ == "__main__":
    main()