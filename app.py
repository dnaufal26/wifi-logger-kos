import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import sqlite3
import os

# Konfigurasi Halaman Streamlit
st.set_page_config(
    page_title="Pencatat Gangguan Wi-Fi PTS Kost",
    page_icon="📶",
    layout="wide"
)

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "wifi_log.db")

def load_data():
    """Mengambil data log ping dan keluhan dari SQLite."""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame(), pd.DataFrame()
    
    conn = sqlite3.connect(DB_PATH)
    
    # 1. Baca Ping Logs
    query_ping = "SELECT * FROM ping_logs ORDER BY timestamp ASC"
    df_ping = pd.read_sql_query(query_ping, conn)
    
    # 2. Baca Complaints
    query_comp = "SELECT * FROM complaints ORDER BY timestamp DESC"
    df_comp = pd.read_sql_query(query_comp, conn)
    
    conn.close()
    
    if not df_ping.empty:
        df_ping['timestamp'] = pd.to_datetime(df_ping['timestamp'])
    if not df_comp.empty:
        df_comp['timestamp'] = pd.to_datetime(df_comp['timestamp'])
        
    return df_ping, df_comp

def group_incidents(df_ping, gap_threshold_sec=15):
    """
    Mengelompokkan deretan ping bermasalah menjadi satu 'Insiden Kejadian'.
    Membedakan laptop mati (jeda > 15 detik) vs gangguan jaringan.
    """
    if df_ping.empty:
        return []
    
    incidents = []
    current_incident = None
    
    for i in range(len(df_ping)):
        row = df_ping.iloc[i]
        status = row['status']
        ts = row['timestamp']
        
        # Cek jika ada jeda karena laptop mati (> 15 detik antar pembacaan berurutan)
        if i > 0:
            delta = (ts - df_ping.iloc[i-1]['timestamp']).total_seconds()
            if delta > gap_threshold_sec and current_incident is not None:
                # Tutup insiden sebelumnya karena ada jeda pemantauan
                current_incident['end_time'] = df_ping.iloc[i-1]['timestamp']
                current_incident['duration_min'] = max(1, round((current_incident['end_time'] - current_incident['start_time']).total_seconds() / 60))
                incidents.append(current_incident)
                current_incident = None
        
        if status in ['GANGGUAN_ISP', 'GANGGUAN_LOKAL']:
            if current_incident is None:
                current_incident = {
                    'start_time': ts,
                    'end_time': ts,
                    'type': 'Dugaan ISP (Biznet)' if status == 'GANGGUAN_ISP' else 'Dugaan Lokal (Router/AP)',
                    'status_code': status,
                    'count': 1
                }
            else:
                current_incident['end_time'] = ts
                current_incident['count'] += 1
        else:
            if current_incident is not None:
                current_incident['duration_min'] = max(1, round((current_incident['end_time'] - current_incident['start_time']).total_seconds() / 60))
                incidents.append(current_incident)
                current_incident = None
                
    if current_incident is not None:
        current_incident['duration_min'] = max(1, round((current_incident['end_time'] - current_incident['start_time']).total_seconds() / 60))
        incidents.append(current_incident)
        
    return incidents

# --- HEADER APLIKASI ---
st.title("📶 Pencatat Gangguan Wi-Fi Kos Mahasiswa")
st.caption("Studi Kasus: PTS Kost, Cisitu, Bandung · Tugas UTS Kapita Selekta Telekomunikasi ITB")

df_ping, df_comp = load_data()

# Sidebar: Filter & Aksi Cepat
with st.sidebar:
    st.header("⚙️ Kontrol & Form")
    auto_refresh = st.checkbox("Auto Refresh (Deteksi otomatis)", value=False)
    if auto_refresh:
        st.info("Pembaruan data aktif...")
        # Auto rerun Streamlit
        import time
        time.sleep(5)
        st.rerun()

    st.markdown("---")
    st.subheader("📝 Catat Keluhan Penghuni")
    with st.form("form_keluhan"):
        nama_input = st.text_input("Nama (opsional)", placeholder="cth: Ridho")
        lantai_input = st.selectbox("Lantai Kamar", ["Lantai 1", "Lantai 2", "Lantai 3"])
        perangkat_input = st.selectbox("Perangkat Digunakan", ["HP Android", "HP iOS (iPhone)", "Laptop"])
        gejala_input = st.text_input("Gejala", placeholder="cth: Tidak bisa browsing / lemot")
        dampak_input = st.text_input("Dampak", placeholder="cth: Kuliah online terhenti")
        submitted = st.form_submit_button("Kirim Keluhan")
        
        if submitted:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                INSERT INTO complaints (timestamp, nama, lantai, perangkat, gejala, dampak)
                VALUES (datetime('now', 'localtime'), ?, ?, ?, ?, ?)
            """, (nama_input or "Anonim", lantai_input, perangkat_input, gejala_input or "Koneksi mati", dampak_input or "-"))
            conn.commit()
            conn.close()
            st.success("Keluhan tersimpan!")
            st.rerun()

# --- STATUS REALTIME & METRIK ---
if df_ping.empty:
    st.warning("⚠️ Belum ada data ping di database. Pastikan `python monitor.py` sedang berjalan di terminal!")
else:
    latest = df_ping.iloc[-1]
    last_seen_delta = (datetime.now() - latest['timestamp']).total_seconds()
    
    col1, col2, col3, col4 = st.columns(4)
    
    # 1. Status Terakhir
    status_label = latest['status']
    if last_seen_delta > 20:
        col1.metric("Status Sistem", "💤 Laptop Mati/Sleep", delta=f"Jeda {int(last_seen_delta)}d", delta_color="inverse")
    elif status_label == "NORMAL":
        col1.metric("Status Wi-Fi", "🟢 NORMAL", delta="Koneksi Lancar")
    elif status_label == "GANGGUAN_ISP":
        col1.metric("Status Wi-Fi", "🔴 GANGGUAN ISP", delta="Internet Down (Router OK)", delta_color="inverse")
    else:
        col1.metric("Status Wi-Fi", "🟠 GANGGUAN LOKAL", delta="Router Down", delta_color="inverse")

    # 2. Latency Router
    r_lat = latest['router_ping']
    col2.metric("Latency Router Lokal", f"{r_lat:.1f} ms" if pd.notnull(r_lat) else "TIMEOUT")

    # 3. Latency Internet
    i_lat = latest['internet_ping']
    col3.metric("Latency Internet (1.1.1.1)", f"{i_lat:.1f} ms" if pd.notnull(i_lat) else "TIMEOUT")

    # 4. Total Log Terkumpul
    col4.metric("Total Sampel Ping", f"{len(df_ping)} baris", delta=f"Interval 5s")

    st.markdown("---")

    # --- TABS NAVIGASI UTAMA ---
    tab_grafik, tab_insiden, tab_keluhan, tab_laporan = st.tabs([
        "📊 Grafik Latensi & Riwayat", 
        "⚠️ Ringkasan Insiden (Downtime)", 
        "📋 Data Keluhan Penghuni", 
        "📄 Draf Laporan Pengelola (WhatsApp/Cetak)"
    ])

    with tab_grafik:
        st.subheader("Aktivitas Latensi Jaringan (Waktu Nyata)")
        
        # Batasi tampilan untuk grafik (misal 300 data poin terakhir agar cepat)
        df_display = df_ping.tail(300).copy()
        
        fig = go.Figure()
        # Garis Latensi Router
        fig.add_trace(go.Scatter(
            x=df_display['timestamp'], 
            y=df_display['router_ping'],
            name='Router Kos (172.16.10.1)',
            line=dict(color='#2ecc71', width=2),
            mode='lines+markers'
        ))
        
        # Garis Latensi Internet
        fig.add_trace(go.Scatter(
            x=df_display['timestamp'], 
            y=df_display['internet_ping'],
            name='Internet Publik (1.1.1.1)',
            line=dict(color='#3498db', width=2),
            mode='lines+markers'
        ))
        
        fig.update_layout(
            xaxis_title="Waktu",
            yaxis_title="Latency (ms)",
            hovermode="x unified",
            height=400,
            margin=dict(l=20, r=20, t=30, b=20)
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("ℹ️ *Jika garis terputus atau bernilai 0/hilang, terjadi packet loss / timeout pada titik tersebut.*")

    with tab_insiden:
        st.subheader("Daftar Kejadian Gangguan Terdeteksi")
        incidents = group_incidents(df_ping)
        
        if not incidents:
            st.success("🎉 Tidak ada rekaman insiden gangguan. Koneksi Wi-Fi stabil!")
        else:
            df_inc = pd.DataFrame(incidents)
            df_inc['Mulai'] = df_inc['start_time'].dt.strftime('%d %b %Y, %H:%M:%S')
            df_inc['Selesai'] = df_inc['end_time'].dt.strftime('%d %b %Y, %H:%M:%S')
            df_inc['Durasi'] = df_inc['duration_min'].astype(str) + " Menit"
            df_inc['Klasifikasi'] = df_inc['type']
            
            st.dataframe(
                df_inc[['Mulai', 'Selesai', 'Durasi', 'Klasifikasi', 'count']].rename(columns={'count': 'Total Ping Gagal'}),
                use_container_width=True
            )

    with tab_keluhan:
        st.subheader("Keluhan Tercatat dari Penghuni PTS Kost")
        if df_comp.empty:
            st.info("Belum ada laporan keluhan yang masuk dari penghuni.")
        else:
            st.dataframe(df_comp[['timestamp', 'nama', 'lantai', 'perangkat', 'gejala', 'dampak']], use_container_width=True)

    with tab_laporan:
        st.subheader("Format Laporan Siap Kirim untuk Ibu Kos / Teknisi ISP")
        st.markdown("Kalian dapat langsung menyalin teks ringkasan ini untuk dilaporkan ke pengelola kos:")
        
        # Hitung statistik singkat
        total_logs = len(df_ping)
        gangguan_isp = len(df_ping[df_ping['status'] == 'GANGGUAN_ISP'])
        gangguan_lokal = len(df_ping[df_ping['status'] == 'GANGGUAN_LOKAL'])
        total_gangguan = gangguan_isp + gangguan_lokal
        uptime_pct = ((total_logs - total_gangguan) / total_logs * 100) if total_logs > 0 else 100
        
        sample_keluhan = ""
        if not df_comp.empty:
            top_gejala = df_comp['gejala'].mode()[0] if not df_comp['gejala'].empty else "-"
            sample_keluhan = f"- Gejala terbanyak penghuni: {top_gejala} (Total {len(df_comp)} laporan)"
        
        template_pesan = f"""*LAPORAN PEMANTAUAN WI-FI PTS KOST*
Periode Pantau: {df_ping.iloc[0]['timestamp'].strftime('%d/%m/%Y %H:%M')} s/d {df_ping.iloc[-1]['timestamp'].strftime('%d/%m/%Y %H:%M')}

📊 *Ringkasan Teknis:*
- Ketersediaan Koneksi (Uptime): {uptime_pct:.2f}%
- Gangguan Teridentifikasi: {len(group_incidents(df_ping))} kali kejadian
  • Dugaan Masalah Jalur ISP (Biznet): {gangguan_isp} sampel ping
  • Dugaan Masalah Perangkat Router/AP Lokal: {gangguan_lokal} sampel ping

👥 *Dampak Penghuni:*
{sample_keluhan if sample_keluhan else '- Belum ada keluhan kritis tercatat'}

*Rekomendasi:*
{'Perlu restart/pemeriksaan router fisik kos karena terjadi kendala lokal.' if gangguan_lokal > gangguan_isp else 'Router lokal aman, perlu eskalasi tiket gangguan ke pihak ISP Biznet.'}
        """
        
        st.text_area("Teks Laporan WhatsApp", value=template_pesan, height=260)