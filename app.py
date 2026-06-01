import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os

st.set_page_config(page_title="Red FTTH", page_icon="🖧", layout="wide")

st.markdown("""
<style>
.stApp{background:#0f1117}
.block-container{padding:2rem}
.mcard{background:linear-gradient(135deg,#1e2a4a,#243358);border:0.5px solid rgba(99,179,237,0.2);border-radius:14px;padding:18px;margin-bottom:8px}
.mlabel{font-size:11px;color:rgba(255,255,255,0.45);text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px}
.mval{font-size:28px;font-weight:700;color:#fff}
.mdelta{font-size:12px;color:#68d391;margin-top:6px}
.pending{background:rgba(255,255,255,0.04);border:0.5px solid rgba(255,255,255,0.08);border-radius:14px;padding:40px;text-align:center;color:rgba(255,255,255,0.3)}
.nota{background:linear-gradient(135deg,#1a2035,#1e2a4a);border-left:3px solid #63b3ed;border-radius:0 10px 10px 0;padding:12px 18px;margin:8px 0 18px 0}
.nota-texto{font-size:12px;color:rgba(255,255,255,0.6);line-height:1.7}
.nota-fecha{color:#63b3ed;font-weight:600}
</style>
""", unsafe_allow_html=True)

COLS = ["vendor","fecha_carga","total_olts","total_troncales","total_onts"]
COLORES = {
    "ZTE":   ("#b794f4","#68d391","#63b3ed"),
    "HAW":   ("#63b3ed","#68d391","#b794f4"),
    "ATP":   ("#68d391","#f6ad55","#63b3ed"),
    "ONNET": ("#f6ad55","#68d391","#63b3ed"),
}

# ── Carga de datos ──
@st.cache_data
def cargar():
    archivos = {
        "ZTE":   "data/historico_ZTE.csv",
        "HAW":   "data/historico_HAW.csv",
        "ATP":   "data/historico_ATP.csv",
        "ONNET": "data/historico_ONNET.csv",
    }
    frames = []
    for vendor, ruta in archivos.items():
        if os.path.exists(ruta):
            df = pd.read_csv(ruta)
            if "vendor" not in df.columns:
                df["vendor"] = vendor
            cols_presentes = [c for c in COLS if c in df.columns]
            frames.append(df[cols_presentes])
    if frames:
        df = pd.concat(frames, ignore_index=True)
        df["fecha_carga"] = pd.to_datetime(df["fecha_carga"], format='mixed')
        return df.sort_values("fecha_carga")
    return pd.DataFrame(columns=COLS)

hist = cargar()

# ── Helpers ──
def slabel(fecha):
    f = pd.to_datetime(fecha)
    m = ["","Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][f.month]
    return f"{f.day} {m}"

def tarjeta(label, val, delta, color):
    # CAMBIO 1: "vs semana anterior" → "vs lectura anterior"
    d = f'<div class="mdelta">↑ {int(delta):,} vs lectura anterior</div>' if delta and delta > 0 else ""
    st.markdown(f'<div class="mcard"><div class="mlabel">{label}</div><div class="mval" style="color:{color}">{int(val):,}</div>{d}</div>', unsafe_allow_html=True)

def grafica(df, col, color, titulo):
    labs = [slabel(f) for f in df["fecha_carga"]]
    vals = df[col].tolist()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=labs, y=vals,
        mode="lines+markers+text",
        text=[f"{int(v):,}" if v < 10000 else f"{int(v/1000)}K" for v in vals],
        textposition="top center",
        textfont=dict(size=10, color=color),
        line=dict(color=color, width=2.5),
        marker=dict(color=color, size=7, line=dict(color="#1a1d2e", width=2)),
        fill="tozeroy", fillcolor="rgba(99,179,237,0.08)",
        hovertemplate="%{x}<br><b>%{y:,}</b><extra></extra>"
    ))
    fig.update_layout(
        title=dict(text=titulo, font=dict(size=13, color="#fff"), x=0),
        paper_bgcolor="rgba(255,255,255,0.04)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(255,255,255,0.5)", size=10),
        margin=dict(t=50, b=40, l=10, r=10), height=260,
        xaxis=dict(showgrid=False, tickangle=45, tickfont=dict(size=10)),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)", tickfont=dict(size=10)),
        showlegend=False
    )
    st.plotly_chart(fig, use_container_width=True)

def vista(vendor):
    c_onts, c_tronc, c_olts = COLORES[vendor]
    df = hist[hist["vendor"] == vendor].copy() if not hist.empty else pd.DataFrame(columns=COLS)

    if df.empty:
        st.markdown(f'<div class="pending"><p style="font-size:16px">⊜ Datos de {vendor} pendientes</p><p style="font-size:12px;margin-top:8px">Agrega el archivo historico_{vendor}.csv en la carpeta data/</p></div>', unsafe_allow_html=True)
        return

    ultimo = df.iloc[-1]
    anterior = df.iloc[-2] if len(df) > 1 else None

    # Tarjetas alineadas: OLTs | Troncales | ONTs
    c1, c2, c3 = st.columns(3)
    with c1:
        delta = int(ultimo["total_olts"] - anterior["total_olts"]) if anterior is not None else None
        tarjeta("⎕ OLTs únicas", ultimo["total_olts"], delta, c_olts)
    with c2:
        delta = int(ultimo["total_troncales"] - anterior["total_troncales"]) if anterior is not None else None
        tarjeta("⏛ Troncales", ultimo["total_troncales"], delta, c_tronc)
    with c3:
        delta = int(ultimo["total_onts"] - anterior["total_onts"]) if anterior is not None else None
        tarjeta("⏣ ONTs activas", ultimo["total_onts"], delta, c_onts)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Gráficas alineadas debajo de su tarjeta correspondiente: OLTs | Troncales | ONTs
    if len(df) > 1:
        g1, g2, g3 = st.columns(3)
        with g1: grafica(df, "total_olts", c_olts, "⎕ OLTs")
        with g2: grafica(df, "total_troncales", c_tronc, "⏛ Troncales")
        with g3: grafica(df, "total_onts", c_onts, "⏣ ONTs activas")
    else:
        st.markdown('<div class="pending"><p style="font-size:13px">Solo hay un registro. Las gráficas aparecerán con más cargas semanales.</p></div>', unsafe_allow_html=True)

# ── Header ──
h1, h2 = st.columns([3, 1])
with h1:
    st.markdown("## 🖧 Red FTTH — Crecimiento")
    # CAMBIO 2: mostrar hora si está disponible
    if not hist.empty:
        ultima = hist["fecha_carga"].max()
        if ultima.hour == 0 and ultima.minute == 0:
            ultima_str = ultima.strftime("%d %b %Y")
        else:
            ultima_str = ultima.strftime("%d %b %Y — %H:%M")
    else:
        ultima_str = "Sin datos"
    st.markdown(f"<p style='color:rgba(255,255,255,0.35);font-size:12px;margin-top:-10px'>Última ejecución: {ultima_str}</p>", unsafe_allow_html=True)
with h2:
    if st.button("⟳ Actualizar datos"):
        st.cache_data.clear()
        st.rerun()

# CAMBIO 3: nota informativa
if not hist.empty:
    ultima_nota = hist["fecha_carga"].max()
    if ultima_nota.hour == 0 and ultima_nota.minute == 0:
        fecha_nota = ultima_nota.strftime("%d de %B de %Y")
    else:
        fecha_nota = ultima_nota.strftime("%d de %B de %Y a las %H:%M")
    st.markdown(f"""
    <div class="nota">
        <div class="nota-texto">
            📋 Los valores reportados corresponden únicamente a equipos activos y operativos en la red residencial FTTH
            a <span class="nota-fecha">{fecha_nota}</span>.
            Esta fecha y hora corresponde al momento de ejecución y depuración de los scripts de procesamiento.
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ── Pestañas ──
t0, t1, t2, t3, t4 = st.tabs(["⎔ General", "⊞ ZTE", "⊞ Huawei", "⊞ ATP", "⊞ ONNET"])

with t0:
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    if not hist.empty:
        ultimos = hist.sort_values("fecha_carga").groupby("vendor").last().reset_index()
        total_olts      = int(ultimos["total_olts"].sum())
        total_troncales = int(ultimos["total_troncales"].sum())
        total_onts      = int(ultimos["total_onts"].sum())

        st.markdown("#### ⎔ Total Red")
        tc1, tc2, tc3 = st.columns(3)
        with tc1:
            st.markdown(f'<div class="mcard" style="border-color:#f6ad5544"><div class="mlabel" style="color:#f6ad55">⬡ Total OLTs</div><div class="mval">{total_olts:,}</div></div>', unsafe_allow_html=True)
        with tc2:
            st.markdown(f'<div class="mcard" style="border-color:#68d39144"><div class="mlabel" style="color:#68d391">◉ Total Troncales</div><div class="mval">{total_troncales:,}</div></div>', unsafe_allow_html=True)
        with tc3:
            st.markdown(f'<div class="mcard" style="border-color:#63b3ed44"><div class="mlabel" style="color:#63b3ed">▲ Total ONTs</div><div class="mval">{total_onts:,}</div></div>', unsafe_allow_html=True)

        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
        st.markdown("#### Por vendor")

    cols = st.columns(4)
    for i, vendor in enumerate(["ZTE", "HAW", "ATP", "ONNET"]):
        c_onts, c_tronc, c_olts = COLORES[vendor]
        with cols[i]:
            df_v = hist[hist["vendor"] == vendor] if not hist.empty else pd.DataFrame(columns=COLS)
            if not df_v.empty:
                u = df_v.iloc[-1]
                st.markdown(f'''<div class="mcard" style="border-color:{c_onts}44">
                    <div class="mlabel" style="color:{c_onts}">{vendor}</div>
                    <div style="font-size:11px;color:rgba(255,255,255,0.4);margin-top:8px">⎕ OLTs</div>
                    <div style="font-size:20px;font-weight:600;color:#fff">{int(u["total_olts"]):,}</div>
                    <div style="font-size:11px;color:rgba(255,255,255,0.4);margin-top:6px">⏛ Troncales</div>
                    <div style="font-size:20px;font-weight:600;color:#fff">{int(u["total_troncales"]):,}</div>
                    <div style="font-size:11px;color:rgba(255,255,255,0.4);margin-top:6px">⏣ ONTs</div>
                    <div style="font-size:20px;font-weight:600;color:#fff">{int(u["total_onts"]):,}</div>
                </div>''', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="mcard" style="border-color:rgba(255,255,255,0.08)"><div class="mlabel" style="color:rgba(255,255,255,0.25)">{vendor}</div><div style="font-size:13px;color:rgba(255,255,255,0.2);margin-top:20px">⊜ Pendiente</div></div>', unsafe_allow_html=True)

with t1:
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    vista("ZTE")
with t2:
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    vista("HAW")
with t3:
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    vista("ATP")
with t4:
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    vista("ONNET")
