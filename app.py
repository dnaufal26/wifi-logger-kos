from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from database import get_connection, init_db, insert_complaint
from diagnostics import DIAGNOSES, display_status
from incidents import GAP_SECONDS, MIN_DOWNTIME_SECONDS, analyze_samples
from monitor import BACKUP_TARGET, INTERNET_TARGET, ROUTER_IP

st.set_page_config(page_title="Pemantauan Wi-Fi PTS Kost", page_icon="📶", layout="wide")


@st.cache_resource
def prepare_database():
    init_db()
    return True


def parse_complaint_time(value):
    if not value:
        return pd.NaT
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.notna(parsed) and parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def load_data(since):
    with closing(get_connection()) as connection:
        ping_rows = connection.execute(
            """
            SELECT * FROM ping_logs
            WHERE timestamp >= ? ORDER BY timestamp, id
            """,
            (since.isoformat(sep=" ", timespec="seconds"),),
        ).fetchall()
        complaints = [dict(row) for row in connection.execute(
            "SELECT timestamp, nama, lantai, perangkat, gejala, dampak FROM complaints ORDER BY id DESC"
        )]

    if complaints:
        frame = pd.DataFrame(complaints)
        # Import lama menyimpan format CSV mentah, jadi tangani lebih dari satu format.
        parsed = frame["timestamp"].map(parse_complaint_time)
        frame = frame.loc[parsed.isna() | (parsed >= since)].copy()
        unparsed = parsed.loc[frame.index].isna()
        frame.loc[unparsed, "timestamp"] = frame.loc[unparsed, "timestamp"].astype(str) + " (cek format waktu)"
    else:
        frame = pd.DataFrame()
    return ping_rows, frame


def format_duration(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours} j {minutes} m {seconds} d" if hours else f"{minutes} m {seconds} d"


def probe_text(result, rtt):
    if result is None:
        return "—" if rtt is None else f"{rtt:g} ms"
    labels = {"OK": "Merespons", "TIDAK_MERESPONS": "Tidak merespons",
              "GAGAL_KIRIM": "Gagal dikirim / tujuan tak terjangkau",
              "ERROR_UKUR": "Pengukuran bermasalah"}
    return f"{rtt:g} ms" if rtt is not None else labels[result]


def show_latency(rows, timestamps):
    series = (
        ("Gateway", "router_ping"),
        (INTERNET_TARGET, "internet_ping"),
        (BACKUP_TARGET, "backup_ping"),
    )
    recent = list(zip(timestamps[-300:], rows[-300:]))
    x_values = []
    y_values = {column: [] for _, column in series}
    for timestamp, row in recent:
        if x_values and (timestamp - x_values[-1]).total_seconds() > GAP_SECONDS:
            x_values.append(timestamp)
            for values in y_values.values():
                values.append(None)
        x_values.append(timestamp)
        for _, column in series:
            y_values[column].append(row[column])
    fig = go.Figure()
    for label, column in series:
        fig.add_trace(go.Scatter(
            x=x_values, y=y_values[column], name=label, mode="lines+markers", connectgaps=False,
        ))
    fig.update_layout(xaxis_title="Waktu lokal laptop", yaxis_title="RTT (ms)", height=360)
    st.plotly_chart(fig)
    st.caption("Maksimal 300 sampel terakhir. Titik kosong menandakan RTT tidak tersedia.")


def incident_record(incident):
    diagnosis = DIAGNOSES[incident.diagnosis_code]
    evidence = " · ".join(
        f"{DIAGNOSES[code].title} ({count} sampel)"
        for code, count in incident.patterns.items()
    )
    return {
        "Mulai teramati": incident.started_at,
        "Terakhir gagal": incident.last_failed_at,
        "Pulih teramati": incident.recovered_at,
        "Durasi teramati": format_duration(incident.observed_seconds),
        "Status": incident.state,
        "Indikasi": diagnosis.title,
        "Pola sampel": evidence,
        "Yang perlu diperiksa": diagnosis.action,
    }


prepare_database()
st.title("Pemantauan Wi-Fi PTS Kost")
st.caption(f"Titik pantau laptop · Gateway terkonfigurasi {ROUTER_IP}")

with st.sidebar:
    hours = st.selectbox("Rentang tampilan", [6, 24, 48], index=1, format_func=lambda n: f"{n} jam")
    auto_refresh = st.checkbox("Perbarui dashboard tiap 5 detik", value=True)
    st.button("Muat ulang data")
    with st.form("form_keluhan", clear_on_submit=True):
        st.subheader("Catat keluhan")
        name = st.text_input("Nama (opsional)")
        floor = st.selectbox("Lantai kamar", ["Lantai 1", "Lantai 2", "Lantai 3"])
        device = st.selectbox("Perangkat", ["HP Android", "HP iOS (iPhone)", "Laptop"])
        symptom = st.text_input("Gejala")
        impact = st.text_input("Dampak")
        if st.form_submit_button("Simpan keluhan"):
            if symptom.strip() and impact.strip():
                insert_complaint(name.strip() or "Anonim", floor, device, symptom.strip(), impact.strip())
                st.success("Keluhan tersimpan.")
            else:
                st.warning("Isi gejala dan dampak sebelum menyimpan.")


@st.fragment(run_every=5 if auto_refresh else None)
def show_dashboard():
    now = datetime.now()
    rows, complaints = load_data(now - timedelta(hours=hours))
    timestamps = [datetime.fromisoformat(row["timestamp"]) for row in rows]
    codes = [display_status(row) for row in rows]
    history = analyze_samples(zip(timestamps, codes), now)
    st.caption(f"Dashboard terakhir membaca database pukul {now:%H:%M:%S}.")
    if rows:
        latest = rows[-1]
        age = int((now - timestamps[-1]).total_seconds())
        diagnosis = DIAGNOSES[codes[-1]]
        if age > GAP_SECONDS:
            st.warning(f"Data terbaru belum masuk selama {age} detik. Cek terminal monitor.py.")
        elif history.pending_seconds is not None:
            st.info(f"Kegagalan sedang diamati ({history.pending_seconds} detik sejak sampel gagal pertama).")
        elif history.incidents and history.incidents[-1].state in ("Berlangsung", "Menunggu konfirmasi pulih"):
            incident = history.incidents[-1]
            st.warning(f"{incident.state} sejak {incident.started_at:%H:%M:%S} · {DIAGNOSES[incident.diagnosis_code].title}")
        st.caption(f"Sampel terakhir {timestamps[-1]:%d/%m/%Y %H:%M:%S} · {diagnosis.title}")
        st.write(diagnosis.evidence)
        if age <= GAP_SECONDS and codes[-1] != "NORMAL":
            st.write(diagnosis.action)
        columns = st.columns(4)
        probes = (
            ("Gateway", "router_result", "router_ping"),
            (INTERNET_TARGET, "internet_result", "internet_ping"),
            (BACKUP_TARGET, "backup_result", "backup_ping"),
        )
        for col, (label, result, rtt) in zip(columns, probes):
            col.markdown(f"**{label}**")
            col.write(probe_text(latest[result], latest[rtt]))
        columns[3].markdown("**TCP 443**")
        columns[3].write(probe_text(latest["tcp_result"], None))
    else:
        st.warning("Belum ada sampel di rentang tampilan. Jalankan monitor.py di terminal terpisah.")

    incidents_tab, graph_tab, complaints_tab, report_tab = st.tabs(
        ["Riwayat downtime", "Pengukuran", "Keluhan", "Laporan pengelola"]
    )
    with incidents_tab:
        st.caption(
            f"Downtime tercatat setelah sampel gagal beruntun mencakup minimal {MIN_DOWNTIME_SECONDS} detik. "
            "Pemulihan memerlukan dua sampel yang menunjukkan akses kembali. "
            "Durasi dihitung dari sampel dalam rentang tampilan."
        )
        c1, c2, c3 = st.columns(3)
        c1.metric("Downtime terkonfirmasi", len(history.incidents))
        c2.metric("Kegagalan singkat yang kembali normal", history.short_failures)
        c3.metric("Jeda sampel", len(history.gaps))
        if history.incidents:
            st.dataframe([incident_record(item) for item in reversed(history.incidents)], hide_index=True)
        if history.gaps:
            st.subheader("Jeda lebih dari 15 detik")
            st.dataframe([
                {"Sampel terakhir sebelum jeda": left, "Batas akhir observasi jeda": right,
                 "Selang antarsampel": format_duration(int((right - left).total_seconds()))}
                for left, right in reversed(history.gaps)
            ], hide_index=True)
    with graph_tab:
        if rows:
            show_latency(rows, timestamps)
            st.dataframe([
                {"Waktu": ts, "Status": DIAGNOSES[code].title,
                 "Gateway": probe_text(row["router_result"], row["router_ping"]),
                 INTERNET_TARGET: probe_text(row["internet_result"], row["internet_ping"]),
                 BACKUP_TARGET: probe_text(row["backup_result"], row["backup_ping"]),
                 "TCP 443": probe_text(row["tcp_result"], None)}
                for ts, code, row in reversed(list(zip(timestamps[-30:], codes[-30:], rows[-30:])))
            ], hide_index=True)
    with complaints_tab:
        if complaints.empty:
            st.info("Belum ada keluhan pada rentang ini.")
        else:
            st.dataframe(complaints, hide_index=True)
    with report_tab:
        counts = Counter(codes)
        lines = [
            "LAPORAN PEMANTAUAN WI-FI PTS KOST",
            f"Rentang tampilan {hours} jam · waktu lokal laptop",
            f"Downtime terkonfirmasi {len(history.incidents)} kejadian",
            f"Total durasi downtime teramati {format_duration(sum(item.observed_seconds for item in history.incidents))}",
            f"Kegagalan singkat yang kembali normal {history.short_failures} kejadian",
            f"Jeda pengukuran terdeteksi {len(history.gaps)}",
            f"Sampel dengan bukti terbatas {counts['LEGACY_UNCERTAIN'] + counts['PROBE_ERROR']}",
            f"Keluhan dalam rentang atau perlu cek waktu {len(complaints)}",
        ]
        if timestamps:
            lines.append(f"Sampel tersedia {timestamps[0]:%d/%m %H:%M:%S} s.d. {timestamps[-1]:%d/%m %H:%M:%S}")
        else:
            lines.append("Belum ada sampel dalam rentang ini.")
        if history.incidents:
            lines.append("Rincian hingga lima downtime terakhir")
        for incident in history.incidents[-5:]:
            diagnosis = DIAGNOSES[incident.diagnosis_code]
            recovery = f" · pulih {incident.recovered_at:%d/%m %H:%M:%S}" if incident.recovered_at else ""
            lines.extend([
                "",
                f"{incident.started_at:%d/%m %H:%M:%S}{recovery} · {incident.state} · {format_duration(incident.observed_seconds)}",
                diagnosis.title,
                diagnosis.evidence,
                incident_record(incident)["Pola sampel"],
                diagnosis.action,
            ])
        st.code("\n".join(lines), language=None)


show_dashboard()
