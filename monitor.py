import errno
import os
import re
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from database import init_db, insert_ping_log
from diagnostics import ERROR, NO_REPLY, OK, SEND_FAILED, classify

ROUTER_IP = os.environ.get("WIFI_LOG_ROUTER", "172.16.10.1")
INTERNET_TARGET = "1.1.1.1"
BACKUP_TARGET = "8.8.8.8"
INTERVAL_DETIK = 5
PING_TIMEOUT_MS = 1200
TCP_TIMEOUT_SEC = 1.2
RTT_PATTERN = re.compile(r"(?:time|waktu)\s*([=<])\s*(\d+)\s*ms", re.I)
NO_ROUTE = {errno.ENETDOWN, errno.ENETUNREACH, errno.EHOSTUNREACH, 10050, 10051, 10065}


def ping_host(host):
    """Ukur satu ping Windows. Kembalikan (hasil probe, RTT atau None)."""
    try:
        result = subprocess.run(
            ["ping", "-4", "-n", "1", "-w", str(PING_TIMEOUT_MS), host],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=2.5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ERROR, None

    output = result.stdout.lower()
    match = RTT_PATTERN.search(output)
    if match:
        # Ping Windows menampilkan '<1 ms'. Simpan 0,5 ms sebagai pendekatan.
        rtt = 0.5 if match[1] == "<" else float(match[2])
        return OK, rtt
    if "ttl=" in output:
        return OK, None
    if any(term in output for term in (
        "general failure", "transmit failed", "destination host unreachable",
        "destination net unreachable", "host tujuan tidak dapat dijangkau",
    )):
        return SEND_FAILED, None
    if "request timed out" in output or "permintaan habis" in output:
        return NO_REPLY, None
    return ERROR, None


def probe_tcp():
    """Coba membuka koneksi TCP ke IP publik tanpa bergantung pada DNS."""
    try:
        with socket.create_connection((INTERNET_TARGET, 443), timeout=TCP_TIMEOUT_SEC):
            return OK
    except TimeoutError:
        return NO_REPLY
    except OSError as exc:
        if exc.errno in NO_ROUTE or getattr(exc, "winerror", None) in NO_ROUTE:
            return SEND_FAILED
        return ERROR


def main():
    init_db()
    print(f"Memantau gateway {ROUTER_IP} dan target {INTERNET_TARGET} / {BACKUP_TARGET}.")
    print("Interval 5 detik. Tekan Ctrl+C untuk berhenti.")
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            next_start = time.monotonic()
            while True:
                sampled_at = datetime.now().isoformat(sep=" ", timespec="seconds")
                router_job = pool.submit(ping_host, ROUTER_IP)
                primary_job = pool.submit(ping_host, INTERNET_TARGET)
                backup_job = pool.submit(ping_host, BACKUP_TARGET)
                router_result, router_rtt = router_job.result()
                primary_result, primary_rtt = primary_job.result()
                backup_result, backup_rtt = backup_job.result()

                tcp_result = None
                if OK not in (primary_result, backup_result):
                    tcp_result = probe_tcp()
                status = classify(router_result, primary_result, backup_result, tcp_result)
                insert_ping_log(
                    router_rtt, primary_rtt, status,
                    timestamp=sampled_at,
                    router_result=router_result,
                    internet_result=primary_result,
                    backup_ping=backup_rtt,
                    backup_result=backup_result,
                    tcp_result=tcp_result,
                )
                print(
                    f"[{sampled_at}] Gateway {router_result} | "
                    f"1.1.1.1 {primary_result} | 8.8.8.8 {backup_result} | "
                    f"TCP {tcp_result or '—'} | {status}", flush=True,
                )

                next_start += INTERVAL_DETIK
                while next_start < time.monotonic():
                    next_start += INTERVAL_DETIK
                time.sleep(max(0, next_start - time.monotonic()))
    except KeyboardInterrupt:
        print("\nMonitoring dihentikan. Sampel yang sudah tercatat tetap tersimpan.")


if __name__ == "__main__":
    main()
