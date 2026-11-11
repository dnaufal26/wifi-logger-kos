"""Klasifikasi berdasarkan bukti yang terukur dari laptop pemantau."""
from dataclasses import dataclass

OK = "OK"
NO_REPLY = "TIDAK_MERESPONS"
SEND_FAILED = "GAGAL_KIRIM"
ERROR = "ERROR_UKUR"
NO_RESPONSE = {NO_REPLY, SEND_FAILED}

UP_STATES = {"NORMAL", "GATEWAY_SILENT", "PARTIAL_PUBLIC", "TCP_REACHABLE"}
DOWN_STATES = {"LOCAL_ACCESS", "UPSTREAM_ACCESS"}


@dataclass(frozen=True)
class Diagnosis:
    title: str
    evidence: str
    action: str


DIAGNOSES = {
    "NORMAL": Diagnosis(
        "Koneksi terpantau",
        "Pemeriksaan koneksi dari laptop pemantau berhasil.",
        "Jika penghuni masih mengalami kendala, bandingkan perangkat, lantai, dan waktu keluhan.",
    ),
    "GATEWAY_SILENT": Diagnosis(
        "Gateway tidak menjawab, akses keluar terukur",
        "Setidaknya satu target publik merespons meski ping gateway gagal.",
        "Cek IP Default Gateway pada adaptor Wi-Fi dan apakah gateway memang menjawab ping.",
    ),
    "PARTIAL_PUBLIC": Diagnosis(
        "Sebagian pemeriksaan target publik gagal",
        "Setidaknya satu ping publik berhasil.",
        "Bandingkan hasil kedua target. Jika keluhan hanya tentang satu situs, catat nama situsnya.",
    ),
    "TCP_REACHABLE": Diagnosis(
        "Ping publik gagal, koneksi TCP masih berhasil",
        "Kedua ping publik gagal, tetapi laptop bisa membuka koneksi TCP ke 1.1.1.1:443.",
        "Jika web tetap gagal dibuka, catat situs dan periksa DNS, halaman login, serta akses dari perangkat lain.",
    ),
    "LOCAL_ACCESS": Diagnosis(
        "Akses dari laptop ke jaringan kos perlu diperiksa",
        "Gateway, kedua ping publik, dan koneksi TCP gagal dari laptop pemantau.",
        "Cek laptop masih terhubung ke Wi-Fi kos. Bandingkan dengan HP di lokasi yang sama. "
        "Jika beberapa perangkat ikut gagal, minta petugas memeriksa daya dan kabel AP/router.",
    ),
    "UPSTREAM_ACCESS": Diagnosis(
        "Jalur keluar dari jaringan kos perlu diperiksa",
        "Gateway menjawab, tetapi kedua ping publik dan koneksi TCP gagal.",
        "Minta petugas cek lampu Internet/WAN pada router dan indikator modem/ONT bila ada. "
        "Jika perangkat lain juga gagal dan masalah berlanjut, laporkan waktu kejadian ke ISP.",
    ),
    "PROBE_ERROR": Diagnosis(
        "Bukti pengukuran belum cukup",
        "Ada pemeriksaan yang gagal dijalankan atau hasilnya tidak bisa ditafsirkan.",
        "Cek terminal pemantau, konfigurasi gateway, dan adaptor jaringan laptop.",
    ),
    "LEGACY_UNCERTAIN": Diagnosis(
        "Sampel lama dengan bukti terbatas",
        "Versi lama belum merekam kedua target publik dan pembanding TCP.",
        "Simpan sebagai riwayat pengukuran. Bandingkan dengan keluhan pada waktu yang sama.",
    ),
    "MIXED": Diagnosis(
        "Pola kegagalan berubah",
        "Respons gateway berubah selama gangguan akses ke target publik.",
        "Bandingkan perangkat dan lokasi yang terdampak, lalu teruskan rincian probe ke petugas.",
    ),
}


def classify(router, primary, backup, tcp):
    if OK in (primary, backup):
        if router in NO_RESPONSE:
            return "GATEWAY_SILENT"
        if router == primary == backup == OK:
            return "NORMAL"
        return "PARTIAL_PUBLIC"
    if tcp == OK:
        return "TCP_REACHABLE"
    if all(result in NO_RESPONSE for result in (primary, backup, tcp)):
        if router == OK:
            return "UPSTREAM_ACCESS"
        if router in NO_RESPONSE:
            return "LOCAL_ACCESS"
    return "PROBE_ERROR"


def display_status(row):
    """Tafsirkan format lama secara konservatif tanpa mengubah catatan asli."""
    status = row["status"]
    if status in DIAGNOSES:
        return status
    if row["internet_ping"] is not None and row["router_ping"] is None:
        return "GATEWAY_SILENT"
    return "LEGACY_UNCERTAIN"
