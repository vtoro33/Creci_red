import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
import os, io, re, hashlib, glob, zipfile, uuid, html
from datetime import datetime, timedelta
from dotenv import load_dotenv, set_key

# ── Config ───────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Red FTTH", page_icon="🖧", layout="wide")

# ── Fix: React removeChild bug con file_uploader ─────────────────────────────
# Streamlit/React a veces falla al reconciliar el DOM cuando se eliminan archivos
# de un file_uploader con accept_multiple_files=True y hay otros uploaders activos.
# Este parche silencia el error parcheando removeChild en el window principal.
components.html("""
<script>
try {
    var w = window.parent;
    if (w && !w.__removeChildPatched) {
        var orig = w.Node.prototype.removeChild;
        w.Node.prototype.removeChild = function(child) {
            if (child.parentNode !== this) {
                return child.parentNode ? child.parentNode.removeChild(child) : child;
            }
            return orig.call(this, child);
        };
        w.__removeChildPatched = true;
    }
} catch(e) {}
</script>
""", height=0)

ENV_PATH = ".env"
DATA_DIR = "data"
TEMP_DIR = os.path.join(DATA_DIR, "temp")
for d in [DATA_DIR, TEMP_DIR]:
    os.makedirs(d, exist_ok=True)

if not os.path.exists(ENV_PATH):
    with open(ENV_PATH, "w") as f:
        f.write(f"ADMIN_PASSWORD={hashlib.sha256('admin123'.encode()).hexdigest()}\n")
load_dotenv(ENV_PATH, override=True)

PREFIJOS_SERIAL = ["ZTE", "SKY", "SDM", "SCO", "HWT", "SEI"]
COLORES = {
    "ZTE":   ("#b794f4", "#68d391", "#63b3ed"),
    "HAW":   ("#63b3ed", "#68d391", "#b794f4"),
    "ATP":   ("#68d391", "#f6ad55", "#63b3ed"),
    "ONNET": ("#f6ad55", "#68d391", "#63b3ed"),
}
COLS = ["vendor", "fecha_carga", "total_olts", "total_troncales", "total_onts"]
VENDOR_NOMBRE = {"ZTE": "ZTE", "HAW": "HUAWEI", "ATP": "ATP", "ONNET": "ONNET"}

# Notas por pestaña
NOTAS_PATH = os.path.join(DATA_DIR, "notas.csv")
TABS_NOTAS = {
    "GENERAL": "⎔ General",
    "ZTE":     "⊞ ZTE",
    "HAW":     "⊞ Huawei",
    "ATP":     "⊞ ATP",
    "ONNET":   "⊞ ONNET",
}

# Configuración de columnas para detalle por OLT (por vendor)
DETALLE_CONFIG = {
    "ZTE": {
        "col_olt":     "NE Name",
        "col_shelf":   "Shelf",
        "col_slot":    "Slot",
        "col_port":    "Port",
        "col_troncal": "Port Name",
        "col_ont":     "ONU Name",
        "ont_agg":     "nunique",
        "tiene_shelf": True,
    },
    "ATP": {
        "col_olt":     "NE Name",
        "col_shelf":   "Shelf",
        "col_slot":    "Slot",
        "col_port":    "Port",
        "col_troncal": "Port Name",
        "col_ont":     "ONU Name",
        "ont_agg":     "nunique",
        "tiene_shelf": True,
    },
    "HAW": {
        "col_olt":     "Device name",
        "col_shelf":   "Frame ID",
        "col_slot":    "Slot ID",
        "col_port":    "Port ID",
        "col_troncal": "User Label",
        "col_ont":     "ONU Alias",
        "ont_agg":     "count",
        "tiene_shelf": True,
    },
    "ONNET": {
        "col_olt":     "OLT",
        "col_troncal": "TRK RR",
        "col_ont":     "SERIAL",
        "ont_agg":     "nunique",
        "tiene_shelf": False,
    },
}

# ── Estilos ───────────────────────────────────────────────────────────────────
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
.warn-box{background:linear-gradient(135deg,#2d1f0a,#3d2a0a);border-left:3px solid #f6ad55;border-radius:0 10px 10px 0;padding:14px 18px;margin:10px 0}
.warn-text{font-size:13px;color:#f6ad55;line-height:1.6}
.err-box{background:linear-gradient(135deg,#2d0a0a,#3d1010);border-left:3px solid #fc8181;border-radius:0 10px 10px 0;padding:14px 18px;margin:10px 0}
.err-text{font-size:13px;color:#fc8181;line-height:1.6}
.ok-box{background:linear-gradient(135deg,#0a2d1a,#0f3d25);border-left:3px solid #68d391;border-radius:0 10px 10px 0;padding:14px 18px;margin:10px 0}
.ok-text{font-size:13px;color:#68d391;line-height:1.6}
.section-title{font-size:13px;color:rgba(255,255,255,0.5);text-transform:uppercase;letter-spacing:1px;margin-bottom:16px;padding-bottom:8px;border-bottom:0.5px solid rgba(255,255,255,0.08)}
.step-line{font-size:12px;color:rgba(255,255,255,0.55);padding:3px 0;font-family:monospace}
.step-ok{color:#68d391}
.edit-box{background:linear-gradient(135deg,#1a2035,#1e2a4a);border:0.5px solid rgba(246,173,85,0.3);border-radius:14px;padding:20px;margin:12px 0}
div[data-testid="element-container"]:has(.discard-atp-marker) + div[data-testid="element-container"] button{background:rgba(246,173,85,0.12) !important;border:1px solid rgba(246,173,85,0.4) !important;color:#f6ad55 !important}
details:has(.panel-zte){border-left:3px solid #b794f4 !important}
details:has(.panel-zte) > summary span{color:#b794f4 !important}
details:has(.panel-atp){border-left:3px solid #68d391 !important}
details:has(.panel-atp) > summary span{color:#68d391 !important}
details:has(.panel-haw){border-left:3px solid #63b3ed !important}
details:has(.panel-haw) > summary span{color:#63b3ed !important}
details:has(.panel-onnet){border-left:3px solid #f6ad55 !important}
details:has(.panel-onnet) > summary span{color:#f6ad55 !important}
div[data-testid="column"]:has(.edit-btn-marker) button{background:rgba(255,45,149,0.22) !important;border:1px solid rgba(255,45,149,0.75) !important;color:#ff2d95 !important}
div[data-testid="stColumn"]:has(.edit-btn-marker) button{background:rgba(255,45,149,0.22) !important;border:1px solid rgba(255,45,149,0.75) !important;color:#ff2d95 !important}
div[data-baseweb="popover"]{margin-top:4px !important}
ul[role="listbox"]{max-height:220px !important}
.detalle-titulo{font-size:14px;color:rgba(255,255,255,0.55);text-transform:uppercase;letter-spacing:1px;margin:24px 0 12px 0;padding-bottom:8px;border-bottom:0.5px solid rgba(255,255,255,0.1)}
.olts-sin-troncal{background:linear-gradient(135deg,#2d1f0a,#3d2a0a);border-left:3px solid #f6ad55;border-radius:0 10px 10px 0;padding:12px 18px;margin:8px 0 16px 0;font-size:12px;color:rgba(255,255,255,0.6);line-height:1.7}
</style>
""", unsafe_allow_html=True)

# ── Session state init ────────────────────────────────────────────────────────
for k, v in {
    "admin_logged":      False,
    "admin_dialog_open": False,
    "login_attempts":    0,
    "lockout_until":     None,
    "resultado_zte":   None,
    "resultado_atp":   None,
    "resultado_haw":   None,
    "resultado_onnet": None,
    "edit_mode_zte":   False,
    "edit_mode_atp":   False,
    "edit_mode_haw":   False,
    "edit_mode_onnet": False,
    "publicado_zte":   False,
    "publicado_atp":   False,
    "publicado_haw":   False,
    "publicado_onnet": False,
    "confirmar_borrado_nota": None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Datos ─────────────────────────────────────────────────────────────────────
@st.cache_data
def cargar():
    archivos = {
        "ZTE":   os.path.join(DATA_DIR, "historico_ZTE.csv"),
        "HAW":   os.path.join(DATA_DIR, "historico_HAW.csv"),
        "ATP":   os.path.join(DATA_DIR, "historico_ATP.csv"),
        "ONNET": os.path.join(DATA_DIR, "historico_ONNET.csv"),
    }
    frames = []
    for vendor, ruta in archivos.items():
        if os.path.exists(ruta):
            df = pd.read_csv(ruta)
            if "vendor" not in df.columns:
                df["vendor"] = vendor
            cols_p = [c for c in COLS if c in df.columns]
            frames.append(df[cols_p])
    if frames:
        df = pd.concat(frames, ignore_index=True)
        df["fecha_carga"] = pd.to_datetime(df["fecha_carga"], format="mixed")
        return df.sort_values("fecha_carga")
    return pd.DataFrame(columns=COLS)

def slabel(fecha):
    f = pd.to_datetime(fecha)
    m = ["","Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"][f.month]
    return f"{f.day} {m}"

def tarjeta(label, val, delta, color):
    d = f'<div class="mdelta">↑ {int(delta):,} vs lectura anterior</div>' if delta and delta > 0 else ""
    st.markdown(
        f'<div class="mcard"><div class="mlabel">{label}</div>'
        f'<div class="mval" style="color:{color}">{int(val):,}</div>{d}</div>',
        unsafe_allow_html=True)

def grafica(df, col, color, titulo):
    VENTANA = 8  # puntos visibles por defecto
    labs = [slabel(f) for f in df["fecha_carga"]]
    vals = df[col].tolist()
    n    = len(vals)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(range(n)), y=vals, mode="lines+markers+text",
        text=[f"{int(v):,}" if v < 10000 else f"{int(v/1000)}K" for v in vals],
        textposition="top center",
        textfont=dict(size=10, color=color),
        line=dict(color=color, width=2.5),
        marker=dict(color=color, size=7, line=dict(color="#1a1d2e", width=2)),
        fill="tozeroy", fillcolor="rgba(99,179,237,0.08)",
        hovertemplate="%{customdata}<br><b>%{y:,}</b><extra></extra>",
        customdata=labs,
    ))

    # Rango visible: últimos VENTANA puntos (o todos si hay menos)
    x_ini = max(0, n - VENTANA) - 0.5
    x_fin = n - 1 + 0.5

    # Solo mostrar rangeslider si hay más puntos que la ventana
    usar_slider = n > VENTANA

    # Padding vertical para que los textos no se corten
    y_max = max(vals) if vals else 0
    y_pad = y_max * 0.12  # 12% de espacio arriba

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=13, color="#fff"), x=0),
        paper_bgcolor="rgba(255,255,255,0.04)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(255,255,255,0.5)", size=10),
        margin=dict(t=50, b=10, l=10, r=10),
        height=320 if usar_slider else 260,
        xaxis=dict(
            showgrid=False, tickangle=45, tickfont=dict(size=10),
            tickvals=list(range(n)), ticktext=labs,
            range=[x_ini, x_fin],
            rangeslider=dict(
                visible=usar_slider,
                thickness=0.18,
                bgcolor="rgba(255,255,255,0.03)",
                bordercolor="rgba(255,255,255,0.08)",
                borderwidth=1,
            ),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="rgba(255,255,255,0.06)",
            tickfont=dict(size=10),
            fixedrange=True,
            range=[0, y_max + y_pad],
        ),
        showlegend=False,
        dragmode="pan",
    )
    st.plotly_chart(fig, use_container_width=True)

def vista(vendor, hist):
    c_onts, c_tronc, c_olts = COLORES[vendor]
    df = hist[hist["vendor"] == vendor].copy() if not hist.empty else pd.DataFrame(columns=COLS)
    if df.empty:
        st.markdown(
            f'<div class="pending"><p style="font-size:16px">⊜ Datos de {VENDOR_NOMBRE.get(vendor, vendor)} pendientes</p>'
            f'<p style="font-size:12px;margin-top:8px">Procesa los archivos desde la pestaña Administrador</p></div>',
            unsafe_allow_html=True)
        return
    ultimo   = df.iloc[-1]
    anterior = df.iloc[-2] if len(df) > 1 else None

    st.markdown(
        '<div class="warn-box"><div class="warn-text">⚠ Esta información corresponde '
        'al estado puntual de la red al momento del procesamiento de las bases y puede '
        'variar según el estado de los equipos al momento de la consulta. Cifras en cero '
        'pueden deberse a equipos temporalmente offline.</div></div>',
        unsafe_allow_html=True)

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
    if len(df) > 1:
        g1, g2, g3 = st.columns(3)
        with g1: grafica(df, "total_olts",      c_olts,  "⎕ OLTs")
        with g2: grafica(df, "total_troncales",  c_tronc, "⏛ Troncales")
        with g3: grafica(df, "total_onts",       c_onts,  "⏣ ONTs activas")
    else:
        st.markdown('<div class="pending"><p style="font-size:13px">Solo hay un registro. Las gráficas aparecerán con más cargas.</p></div>', unsafe_allow_html=True)

    # ── Detalle por OLT (expander) ──
    detalle_por_olt(vendor)


def detalle_por_olt(vendor):
    """Sección fija con detalle por OLT alimentado desde detalle_X.csv."""
    c_onts, c_tronc, c_olts = COLORES[vendor]
    cfg  = DETALLE_CONFIG[vendor]
    ruta = os.path.join(DATA_DIR, f"detalle_{vendor}.csv")
    PLACEHOLDER = "Sin troncales asociadas"

    st.markdown(
        f'<div class="detalle-titulo">≡ Detalle por OLT — '
        f'{VENDOR_NOMBRE.get(vendor, vendor)}</div>',
        unsafe_allow_html=True)

    mostrar_descarga_anterior(vendor, "vista")

    if not os.path.exists(ruta):
        st.markdown(
            '<div class="pending"><p style="font-size:13px">'
            '⊜ Pendiente — los datos se generan al publicar desde Administrador'
            '</p></div>',
            unsafe_allow_html=True)
        return

    df = pd.read_csv(ruta)
    if df.empty:
        st.markdown(
            '<div class="pending"><p style="font-size:13px">'
            '⊜ Sin datos de detalle'
            '</p></div>',
            unsafe_allow_html=True)
        return

    col_olt     = cfg["col_olt"]
    col_troncal = cfg["col_troncal"]
    tiene_shelf = cfg.get("tiene_shelf", False)

    # ── Sección informativa: OLTs sin troncales asociadas ──
    olts_sin = df[df[col_troncal] == PLACEHOLDER][col_olt].unique().tolist()
    if olts_sin:
        lista = ", ".join(sorted(olts_sin, key=str))
        st.markdown(
            f'<div class="olts-sin-troncal">'
            f'⊜ <b>{len(olts_sin)}</b> OLT{"s" if len(olts_sin) > 1 else ""} '
            f'sin troncales asociadas: {lista}</div>',
            unsafe_allow_html=True)

    # ── Selectbox para elegir OLT ──
    olts    = sorted(df[col_olt].dropna().unique().tolist(), key=str)
    olt_sel = st.selectbox(
        "Selecciona una OLT",
        options=olts,
        key=f"sel_olt_{vendor}",
    )
    if not olt_sel:
        return

    df_olt = df[df[col_olt] == olt_sel].copy()

    # ── Métricas de la OLT seleccionada (excluir placeholder) ──
    df_olt_real     = df_olt[df_olt[col_troncal] != PLACEHOLDER]
    total_troncales = len(df_olt_real)
    total_onts      = int(df_olt_real["ONTs"].sum())

    mc1, mc2 = st.columns(2)
    with mc1:
        st.markdown(
            f'<div class="mcard" style="border-color:{c_tronc}44">'
            f'<div class="mlabel" style="color:{c_tronc}">⏛ Troncales</div>'
            f'<div class="mval" style="font-size:22px">{total_troncales:,}</div></div>',
            unsafe_allow_html=True)
    with mc2:
        st.markdown(
            f'<div class="mcard" style="border-color:{c_onts}44">'
            f'<div class="mlabel" style="color:{c_onts}">⏣ ONTs</div>'
            f'<div class="mval" style="font-size:22px">{total_onts:,}</div></div>',
            unsafe_allow_html=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Preparar tabla con renombrado ──
    if tiene_shelf:
        cols_mostrar = [cfg["col_shelf"], cfg["col_slot"], cfg["col_port"], col_troncal, "ONTs"]
        rename_map = {
            cfg["col_shelf"]: "Shelf/Frame",
            cfg["col_slot"]:  "Slot",
            cfg["col_port"]:  "Port",
            col_troncal:      "Nombre troncal",
            "ONTs":           "ONTs asociadas",
        }
    else:
        cols_mostrar = [col_troncal, "ONTs"]
        rename_map = {
            col_troncal: "TRK RR",
            "ONTs":      "ONTs asociadas",
        }

    df_tabla = df_olt[cols_mostrar].rename(columns=rename_map)

    # Limpiar columnas numéricas (1.0 → 1) para display correcto
    if tiene_shelf:
        for col_num in ["Shelf/Frame", "Slot", "Port"]:
            df_tabla[col_num] = pd.to_numeric(df_tabla[col_num], errors="coerce").astype("Int64")

    # ── Filtros individuales por columna ──
    if tiene_shelf:
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            vals = sorted(df_tabla["Shelf/Frame"].dropna().unique().tolist())
            sel_shelf = st.selectbox("Shelf/Frame", ["Todos"] + [str(v) for v in vals], key=f"f_shelf_{vendor}")
        with fc2:
            vals = sorted(df_tabla["Slot"].dropna().unique().tolist())
            sel_slot = st.selectbox("Slot", ["Todos"] + [str(v) for v in vals], key=f"f_slot_{vendor}")
        with fc3:
            vals = sorted(df_tabla["Port"].dropna().unique().tolist())
            sel_port = st.selectbox("Port", ["Todos"] + [str(v) for v in vals], key=f"f_port_{vendor}")
        with fc4:
            vals = sorted(
                df_tabla["Nombre troncal"]
                [df_tabla["Nombre troncal"] != PLACEHOLDER]
                .dropna().unique().tolist(),
                key=str,
            )
            sel_troncal = st.selectbox("Nombre troncal", ["Todos"] + vals, key=f"f_troncal_{vendor}")

        # Aplicar filtros (cada uno independiente)
        if sel_shelf != "Todos":
            df_tabla = df_tabla[df_tabla["Shelf/Frame"].astype(str) == sel_shelf]
        if sel_slot != "Todos":
            df_tabla = df_tabla[df_tabla["Slot"].astype(str) == sel_slot]
        if sel_port != "Todos":
            df_tabla = df_tabla[df_tabla["Port"].astype(str) == sel_port]
        if sel_troncal != "Todos":
            df_tabla = df_tabla[df_tabla["Nombre troncal"] == sel_troncal]
    else:
        # ONNET: solo filtro por TRK RR
        vals = sorted(
            df_tabla["TRK RR"]
            [df_tabla["TRK RR"] != PLACEHOLDER]
            .dropna().unique().tolist(),
            key=str,
        )
        sel_trk = st.selectbox("TRK RR", ["Todos"] + vals, key=f"f_trk_{vendor}")
        if sel_trk != "Todos":
            df_tabla = df_tabla[df_tabla["TRK RR"] == sel_trk]

    # ── Mostrar tabla ──
    if df_tabla.empty:
        st.markdown(
            '<div class="pending"><p style="font-size:13px">'
            '⊜ Sin resultados para el filtro aplicado'
            '</p></div>',
            unsafe_allow_html=True)
    else:
        st.dataframe(
            df_tabla,
            use_container_width=True,
            hide_index=True,
            height=min(400, 35 + 35 * len(df_tabla)),
        )


def mostrar_descarga_anterior(vendor, panel_key):
    """Muestra botón de descarga si existe detalle_X_anterior.csv."""
    ruta = os.path.join(DATA_DIR, f"detalle_{vendor}_anterior.csv")
    if os.path.exists(ruta):
        with open(ruta, "rb") as f:
            data = f.read()
        st.download_button(
            label=f"⬇ Descargar detalle anterior — {VENDOR_NOMBRE.get(vendor, vendor)}",
            data=data,
            file_name=f"detalle_{vendor}_anterior.csv",
            mime="text/csv",
            key=f"dl_ant_{panel_key}_{vendor}",
        )

# ── Utils ─────────────────────────────────────────────────────────────────────
def es_numerico_valido(serie):
    return serie.astype(str).str.strip().str.match(r"^\d+(\.0+)?$")

def normalizar_enteros(df, columnas):
    df = df.copy()
    for col in columnas:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df

def validar_excel(archivo):
    if not (archivo.name.lower().endswith(".xlsx") or archivo.name.lower().endswith(".xls")):
        return False, f"'{archivo.name}' no es un archivo Excel (.xlsx / .xls)"
    return True, ""

def detectar_grupos(archivos):
    prefijos = [re.match(r"^(\d+)", f.name) for f in archivos]
    if any(p is None for p in prefijos):
        sin = [f.name for f, p in zip(archivos, prefijos) if p is None]
        return None, None, f"Archivos sin prefijo numérico: {', '.join(sin)}"
    pstr = [p.group(1) for p in prefijos]
    uniq = list(dict.fromkeys(pstr))
    if len(uniq) == 1:
        return None, None, "Todos los archivos tienen el mismo prefijo. Se esperan 2 grupos distintos."
    if len(uniq) > 2:
        return None, None, f"Se detectaron {len(uniq)} prefijos. Se esperan exactamente 2."
    ga = [f for f, p in zip(archivos, pstr) if p == uniq[0]]
    gb = [f for f, p in zip(archivos, pstr) if p == uniq[1]]
    return ga, gb, None

def leer_excel_seguro(archivo, columnas, sheet=None, conservar_na_texto=False):
    try:
        kwargs = {"engine": "openpyxl"}
        if conservar_na_texto:
            kwargs["keep_default_na"] = False
            kwargs["na_values"] = [""]
        if sheet:
            kwargs["sheet_name"] = sheet
        df = pd.read_excel(archivo, **kwargs)
        df.columns = [str(c).strip() for c in df.columns]
        faltantes = [c for c in columnas if c not in df.columns]
        if faltantes:
            return None, f"'{archivo.name}' no tiene columnas: {', '.join(faltantes)}"
        return df[columnas].copy(), None
    except Exception as e:
        msg = str(e)
        if "password" in msg.lower() or "encrypt" in msg.lower():
            return None, f"'{archivo.name}' está protegido con contraseña."
        return None, f"No se pudo leer '{archivo.name}': {msg}"

def validar_metricas(m):
    return [k.replace("total_", "") for k in ["total_olts","total_troncales","total_onts"] if m.get(k, 0) == 0]

def csv_bytes(df):
    buf = io.BytesIO()
    df.to_csv(buf, index=False, encoding="utf-8", na_rep="NA")
    return buf.getvalue()

def hacer_zip(archivos_dict):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre, data in archivos_dict.items():
            zf.writestr(nombre, data)
    return buf.getvalue()

def limpiar_temp():
    limite = datetime.now() - timedelta(days=5)
    for f in glob.glob(os.path.join(TEMP_DIR, "*")):
        if os.path.isfile(f) and datetime.fromtimestamp(os.path.getmtime(f)) < limite:
            os.remove(f)

@st.cache_data
def cargar_notas():
    if os.path.exists(NOTAS_PATH):
        df = pd.read_csv(NOTAS_PATH, dtype={"id": str, "vendor": str, "texto": str})
        return df
    return pd.DataFrame(columns=["id", "vendor", "texto", "fecha"])

def guardar_nota(vendor, texto):
    ruta  = NOTAS_PATH
    fila  = pd.DataFrame([{
        "id":     uuid.uuid4().hex[:8],
        "vendor": vendor,
        "texto":  texto.strip(),
        "fecha":  datetime.now().strftime("%Y-%m-%d %H:%M"),
    }])
    if os.path.exists(ruta):
        df = pd.read_csv(ruta, dtype={"id": str, "vendor": str, "texto": str})
        df = pd.concat([df, fila], ignore_index=True)
    else:
        df = fila
    df.to_csv(ruta, index=False)

def borrar_nota(nota_id):
    if not os.path.exists(NOTAS_PATH):
        return
    df = pd.read_csv(NOTAS_PATH, dtype={"id": str, "vendor": str, "texto": str})
    df = df[df["id"] != nota_id]
    df.to_csv(NOTAS_PATH, index=False)

def guardar_historico(vendor, metricas):
    ruta  = os.path.join(DATA_DIR, f"historico_{vendor}.csv")
    nueva = pd.DataFrame([{
        "vendor":          vendor,
        "fecha_carga":     metricas["fecha_carga"],
        "total_olts":      metricas["total_olts"],
        "total_troncales": metricas["total_troncales"],
        "total_onts":      metricas["total_onts"],
    }])
    if os.path.exists(ruta):
        hist = pd.read_csv(ruta)
        hist = pd.concat([hist, nueva], ignore_index=True)
        hist = hist.drop_duplicates(subset=["vendor","fecha_carga"], keep="last")
    else:
        hist = nueva
    hist.to_csv(ruta, index=False)

def rotar_y_guardar_detalle(vendor, df_detalle):
    """Rotación de archivos de detalle: anterior→borrar, actual→anterior, nuevo→actual."""
    ruta_actual   = os.path.join(DATA_DIR, f"detalle_{vendor}.csv")
    ruta_anterior = os.path.join(DATA_DIR, f"detalle_{vendor}_anterior.csv")

    # 1. Si existe anterior → borrar
    if os.path.exists(ruta_anterior):
        os.remove(ruta_anterior)

    # 2. Si existe actual → renombrar a anterior
    if os.path.exists(ruta_actual):
        os.rename(ruta_actual, ruta_anterior)

    # 3. Guardar nuevos datos como actual
    df_detalle.to_csv(ruta_actual, index=False)

def generar_detalle(key, vendors):
    """Genera archivos detalle_X.csv agrupando la base cruzada por troncal.

    Incluye filas placeholder para OLTs que existen en la base pero no tienen
    troncales asociadas (Shelf/Slot/Port vacíos, nombre = 'Sin troncales asociadas',
    ONTs = 0).
    """
    resultado = st.session_state.get(f"resultado_{key}")
    if not resultado:
        return
    base = resultado.get("base")
    if base is None or base.empty:
        return

    PLACEHOLDER = "Sin troncales asociadas"

    for vendor in vendors:
        cfg         = DETALLE_CONFIG[vendor]
        col_olt     = cfg["col_olt"]
        col_troncal = cfg["col_troncal"]
        col_ont     = cfg["col_ont"]
        ont_agg     = cfg["ont_agg"]
        tiene_shelf = cfg.get("tiene_shelf", False)

        # Separar base del vendor
        if key in ("zte", "atp"):
            base_vendor = base[base["vendor"] == vendor].copy()
        else:
            base_vendor = base.copy()

        if base_vendor.empty:
            continue

        # Todas las OLTs que existen en la base (incluidas las sin troncales)
        todas_olts = base_vendor[col_olt].dropna().unique()

        # Filas con troncales válidas → groupby
        df_con_troncal = base_vendor[base_vendor[col_troncal].notna()]

        if tiene_shelf:
            group_cols = [col_olt, cfg["col_shelf"], cfg["col_slot"],
                          cfg["col_port"], col_troncal]
        else:
            group_cols = [col_olt, col_troncal]

        if not df_con_troncal.empty:
            det = df_con_troncal.groupby(group_cols, dropna=False).agg(
                ONTs=(col_ont, ont_agg)
            ).reset_index()
        else:
            det = pd.DataFrame(columns=group_cols + ["ONTs"])

        # OLTs sin troncales → agregar fila placeholder
        olts_con_troncal = det[col_olt].unique() if not det.empty else []
        olts_sin_troncal = [o for o in todas_olts if o not in olts_con_troncal]

        if olts_sin_troncal:
            filas_ph = []
            for olt in olts_sin_troncal:
                fila = {col_olt: olt, col_troncal: PLACEHOLDER, "ONTs": 0}
                if tiene_shelf:
                    fila[cfg["col_shelf"]] = pd.NA
                    fila[cfg["col_slot"]]  = pd.NA
                    fila[cfg["col_port"]]  = pd.NA
                filas_ph.append(fila)
            det = pd.concat([det, pd.DataFrame(filas_ph)], ignore_index=True)

        rotar_y_guardar_detalle(vendor, det)

def verificar_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest() == os.environ.get("ADMIN_PASSWORD", "")

def mostrar_error(msg):
    st.markdown(f'<div class="err-box"><div class="err-text">⚠ {msg}</div></div>', unsafe_allow_html=True)

def mostrar_ok(msg):
    st.markdown(f'<div class="ok-box"><div class="ok-text">✓ {msg}</div></div>', unsafe_allow_html=True)

def mostrar_warn(msg):
    st.markdown(f'<div class="warn-box"><div class="warn-text">⚠ {msg}</div></div>', unsafe_allow_html=True)

# ── Procesadores ──────────────────────────────────────────────────────────────
def procesar_zte_atp(archivos, grupo_tronc, pb, stxt, vendor_forzado=None):
    log   = []
    ts    = datetime.now().strftime("%Y-%m-%d_%H%M")
    pasos = 8
    paso  = [0]

    def avanzar(msg):
        paso[0] += 1
        pb.progress(paso[0] / pasos)
        stxt.markdown(f'<div class="step-line"><span class="step-ok">✓</span> {msg}</div>', unsafe_allow_html=True)

    archivos_tronc = [f for f in archivos if f in grupo_tronc]
    archivos_onts  = [f for f in archivos if f not in grupo_tronc]

    COLS_ONTS  = ["NE Name","Shelf","Slot","Port","ONU Name","Operational Status"]
    COLS_TRONC = ["NE Name","Shelf","Slot","Port","Port Name"]

    # ── Leer ONTs ──
    stxt.markdown('<div class="step-line">⟳ Leyendo archivos de ONTs...</div>', unsafe_allow_html=True)
    lista = []
    for f in archivos_onts:
        df, err = leer_excel_seguro(f, COLS_ONTS)
        if err: return None, err
        df["archivo_fuente"] = f.name
        lista.append(df)
    onts_raw = pd.concat(lista, ignore_index=True)
    n_inicio = len(onts_raw)
    avanzar(f"ONTs leídas: {n_inicio:,} registros")

    # ── Depurar ONTs ──
    stxt.markdown('<div class="step-line">⟳ Depurando ONTs...</div>', unsafe_allow_html=True)

    def reg(fila, columna, motivo):
        return {
            "archivo_fuente": fila["archivo_fuente"],
            "NE_Name":        str(fila.get("NE Name", "")),
            "Shelf":          str(fila.get("Shelf", "")),
            "Slot":           str(fila.get("Slot", "")),
            "Port":           str(fila.get("Port", "")),
            "columna":        columna,
            "valor_original": str(fila.get(columna, "")),
            "motivo":         motivo,
        }

    # R1 NE Name
    ne_str = onts_raw["NE Name"].astype(str).str.strip()
    m = ~ne_str.str.startswith("ZAC")
    log += [reg(r, "NE Name", "No inicia con ZAC") for _, r in onts_raw[m].iterrows()]
    onts = onts_raw[~m].copy()

    # R2-R4 numéricos
    for col, lbl in [("Shelf","R2"),("Slot","R3"),("Port","R4")]:
        col_orig = onts[col].copy()
        onts[col] = onts[col].astype(str)
        mk = ~es_numerico_valido(onts[col])
        mk_log = mk & ~col_orig.isna() & (onts[col].str.strip() != "")
        log += [reg(r, col, f"Valor no numerico en {col}") for _, r in onts[mk_log].iterrows()]
        onts = onts[~mk].copy()
      
    onts = normalizar_enteros(onts, ["Shelf", "Slot", "Port"])  

    # R5 Operational Status
    status_str = onts["Operational Status"].astype(str).str.strip().str.lower()
    m = (status_str != "online")
    log += [reg(r, "Operational Status", "Estado no es Online") for _, r in onts[m].iterrows()]
    onts = onts[~m].copy()

    # R6 ONU Name serial
    patron = "^(" + "|".join(PREFIJOS_SERIAL) + ")"
    onu_str = onts["ONU Name"].astype(str).str.strip()
    m = onts["ONU Name"].isna() | (~onu_str.str.match(patron))
    m_log = (~onts["ONU Name"].isna()) & (onu_str != "") & (~onu_str.str.match(patron))
    log += [reg(r, "ONU Name", "Serial no inicia con prefijo valido (ZTE/SKY/SDM/SCO/HWT/SEI)") for _, r in onts[m_log].iterrows()]
    onts_dep = onts[~m].copy()
    avanzar(f"ONTs depuradas: {len(onts_dep):,} válidas de {n_inicio:,}")

    # ── Leer Troncales ──
    stxt.markdown('<div class="step-line">⟳ Leyendo archivos de Troncales...</div>', unsafe_allow_html=True)
    lista = []
    for f in archivos_tronc:
        df, err = leer_excel_seguro(f, COLS_TRONC, conservar_na_texto=True)
        if err: return None, err
        df["archivo_fuente"] = f.name
        lista.append(df)
    tronc_raw  = pd.concat(lista, ignore_index=True)
    n_inicio_t = len(tronc_raw)
    avanzar(f"Troncales leídas: {n_inicio_t:,} registros")

    # ── Depurar Troncales ──
    stxt.markdown('<div class="step-line">⟳ Depurando Troncales...</div>', unsafe_allow_html=True)

    ne_tronc_str = tronc_raw["NE Name"].astype(str).str.strip()
    olts_maestro = tronc_raw[ne_tronc_str.str.startswith("ZAC")][["NE Name"]].drop_duplicates()

    def reg_tronc(fila, columna, motivo):
        return {
            "archivo_fuente": fila.get("archivo_fuente", ""),
            "NE_Name":        str(fila.get("NE Name", "")),
            "Shelf":          str(fila.get("Shelf", "")),
            "Slot":           str(fila.get("Slot", "")),
            "Port":           str(fila.get("Port", "")),
            "columna":        columna,
            "valor_original": str(fila.get(columna, "")),
            "motivo":         motivo,
        }

    m = ~ne_tronc_str.str.startswith("ZAC")
    log += [reg_tronc(r, "NE Name", "No inicia con ZAC") for _, r in tronc_raw[m].iterrows()]
    tronc = tronc_raw[~m].copy()

    for col in ["Shelf","Slot","Port"]:
        col_orig = tronc[col].copy()
        tronc[col] = tronc[col].astype(str)
        mk = ~es_numerico_valido(tronc[col])
        mk_log = mk & ~col_orig.isna() & (tronc[col].str.strip() != "")
        log += [reg_tronc(r, col, f"Valor no numerico en {col}") for _, r in tronc[mk_log].iterrows()]
        tronc = tronc[~mk].copy()

    tronc = normalizar_enteros(tronc, ["Shelf", "Slot", "Port"])

    # Port Name: solo loguear si tiene valor real pero no empieza con TRK
    pn_orig = tronc["Port Name"].copy()
    pn = tronc["Port Name"].astype(str).str.strip()
    m_trk = pn_orig.isna() | (pn == "") | (~pn.str.startswith("TRK"))
    m_trk_log = ~pn_orig.isna() & (pn != "") & ~pn.str.startswith("TRK")
    log += [reg_tronc(r, "Port Name", "No inicia con TRK") for _, r in tronc[m_trk_log].iterrows()]
    tronc = tronc[~m_trk].copy()

    pn2      = tronc["Port Name"].astype(str).str.strip()
    m_ftth   = pn2.str.match(r"^TRK[_ ]?FTT[HO]", case=False)
    tronc_ftth = tronc[m_ftth].copy()
    tronc      = tronc[~m_ftth].copy()
    tronc      = tronc.drop_duplicates()

    # Puertos ambiguos
    puertos_ambiguos_rev = pd.DataFrame()
    dup = tronc.groupby(["NE Name","Shelf","Slot","Port"]).filter(lambda x: len(x) > 1)
    if not dup.empty:
        rev = dup[~dup["NE Name"].astype(str).str.contains("ATP", na=False)]
        if not rev.empty:
            puertos_ambiguos_rev = rev.sort_values(["NE Name","Shelf","Slot","Port"])
            atp_part  = tronc[tronc["NE Name"].astype(str).str.contains("ATP", na=False)]
            rest_part = tronc[~tronc["NE Name"].astype(str).str.contains("ATP", na=False)].drop_duplicates(subset=["NE Name","Shelf","Slot","Port"])
            tronc = pd.concat([atp_part, rest_part])
    avanzar(f"Troncales depuradas: {len(tronc):,} válidas de {n_inicio_t:,}")

    # ── Warning: OLTs en ONTs sin presencia en Troncales ──
    olts_en_onts  = set(onts_dep["NE Name"].unique())
    olts_en_tronc = set(olts_maestro["NE Name"].unique())
    olts_solo_onts = olts_en_onts - olts_en_tronc
    if olts_solo_onts:
        for olt in sorted(olts_solo_onts):
            n = int(onts_dep[onts_dep["NE Name"] == olt].shape[0])
            log.append({
                "archivo_fuente": "", "NE_Name": olt,
                "Shelf": "", "Slot": "", "Port": "",
                "columna": "NE Name", "valor_original": olt,
                "motivo": f"OLT con {n:,} ONTs en archivo de ONTs pero sin presencia en archivo de Troncales",
            })

    # ── Cruce ──
    stxt.markdown('<div class="step-line">⟳ Cruzando Troncales con ONTs...</div>', unsafe_allow_html=True)
    base = (
        olts_maestro
        .merge(tronc.drop(columns=["archivo_fuente"]), on="NE Name", how="left")
        .merge(onts_dep.drop(columns=["archivo_fuente"]), on=["NE Name","Shelf","Slot","Port"], how="left")
    )
    base["fecha_carga"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    if vendor_forzado:
        base["vendor"] = vendor_forzado
    else:
        base["vendor"] = base["NE Name"].apply(
        lambda x: "ATP" if "ATP" in str(x) else "ZTE"
    )
    avanzar(f"Cruce completado: {len(base):,} registros")

    # ── Métricas ──
    stxt.markdown('<div class="step-line">⟳ Calculando métricas...</div>', unsafe_allow_html=True)

    def calc(df_v, vend):
        df_tr = df_v.dropna(subset=["Port Name"])
        return {
            "vendor":          vend,
            "fecha_carga":     datetime.now().strftime("%Y-%m-%d %H:%M"),
            "total_olts":      int(df_v["NE Name"].nunique()),
            "total_troncales": int(
                df_tr[["NE Name","Shelf","Slot","Port"]]
                .drop_duplicates()
                .shape[0]
            ),
            "total_onts":      int(df_v["ONU Name"].dropna().nunique()),
        }

    m_zte = calc(base[base["vendor"] == "ZTE"], "ZTE")
    m_atp = calc(base[base["vendor"] == "ATP"], "ATP")
    avanzar("Métricas calculadas")

    # ── Archivos ZIP ──
    stxt.markdown('<div class="step-line">⟳ Preparando archivos...</div>', unsafe_allow_html=True)
    # FTTH cruzado con ONTs igual que R
    if not tronc_ftth.empty:
        ftth_cruzado = (
            tronc_ftth
            .merge(onts_dep.drop(columns=["archivo_fuente"]),
                   on=["NE Name","Shelf","Slot","Port"], how="left")
            [["NE Name","Shelf","Slot","Port","Port Name","ONU Name"]]
        )
    else:
        ftth_cruzado = pd.DataFrame()

    log_df = pd.DataFrame(log) if log else pd.DataFrame()
    az = {f"base_ZTE_ATP_{ts}.csv": csv_bytes(base)}
    if not log_df.empty:
        az[f"log_depuracion_{ts}.csv"] = csv_bytes(log_df)
    if not ftth_cruzado.empty:
        az[f"troncales_FTTH_{ts}.csv"] = csv_bytes(ftth_cruzado)
    if not puertos_ambiguos_rev.empty:
        az["puertos_ambiguos_revisar.csv"] = csv_bytes(puertos_ambiguos_rev)
    avanzar("Archivos listos para descarga")
    pb.progress(1.0)

    return {
        "metricas_zte":   m_zte,
        "metricas_atp":   m_atp,
        "base":           base,
        "tronc_ftth":     tronc_ftth,
        "log":            log_df,
        "archivos_zip":   az,
        "ts":             ts,
        "n_onts_inicio":  n_inicio,
        "n_onts_final":   len(onts_dep),
        "n_tronc_inicio": n_inicio_t,
        "n_tronc_final":  len(tronc),
    }, None


def procesar_huawei(archivos, grupo_tronc, pb, stxt):
    log   = []
    ts    = datetime.now().strftime("%Y-%m-%d_%H%M")
    pasos = 8
    paso  = [0]

    def avanzar(msg):
        paso[0] += 1
        pb.progress(paso[0] / pasos)
        stxt.markdown(f'<div class="step-line"><span class="step-ok">✓</span> {msg}</div>', unsafe_allow_html=True)

    archivos_tronc   = [f for f in archivos if f in grupo_tronc]
    archivos_cliente = [f for f in archivos if f not in grupo_tronc]

    COLS_CLI   = ["Device name","Frame ID","Slot ID","Port ID","ONU Alias","Running Status"]
    COLS_TRONC = ["Device name","Frame ID","Slot ID","Port ID","RunStatus","User Label"]

    # ── Leer clientes ──
    stxt.markdown('<div class="step-line">⟳ Leyendo archivos de clientes...</div>', unsafe_allow_html=True)
    lista = []
    for f in archivos_cliente:
        df, err = leer_excel_seguro(f, COLS_CLI)
        if err: return None, err
        df["archivo_fuente"] = f.name
        lista.append(df)
    cli_raw  = pd.concat(lista, ignore_index=True)
    n_inicio = len(cli_raw)
    avanzar(f"Clientes leídos: {n_inicio:,} registros")

    # ── Depurar clientes ──
    stxt.markdown('<div class="step-line">⟳ Depurando clientes...</div>', unsafe_allow_html=True)

    def reg_haw(fila, columna, motivo):
        return {
            "archivo_fuente": fila["archivo_fuente"],
            "Device_name":    str(fila.get("Device name", "")),
            "Frame_ID":       str(fila.get("Frame ID", "")),
            "Slot_ID":        str(fila.get("Slot ID", "")),
            "Port_ID":        str(fila.get("Port ID", "")),
            "columna":        columna,
            "valor_original": str(fila.get(columna, "")),
            "motivo":         motivo,
        }

    dn_str = cli_raw["Device name"].astype(str).str.strip()
    m = ~dn_str.str.startswith("HAC")
    log += [reg_haw(r, "Device name", "No inicia con HAC") for _, r in cli_raw[m].iterrows()]
    cli = cli_raw[~m].copy()

    for col in ["Frame ID","Slot ID","Port ID"]:
        col_orig = cli[col].copy()
        cli[col] = cli[col].astype(str)
        mk = ~es_numerico_valido(cli[col])
        mk_log = mk & ~col_orig.isna() & (cli[col].str.strip() != "")
        log += [reg_haw(r, col, f"Valor no numerico en {col}") for _, r in cli[mk_log].iterrows()]
        cli = cli[~mk].copy()
    cli = normalizar_enteros(cli, ["Frame ID", "Slot ID", "Port ID"])

    rs_str = cli["Running Status"].astype(str).str.strip().str.lower()
    m = (rs_str != "online")
    log += [reg_haw(r, "Running Status", "Estado no es Online") for _, r in cli[m].iterrows()]
    cli = cli[~m].copy()

    oa_str = cli["ONU Alias"].astype(str).str.strip()
    m = (oa_str != "--")
    log += [reg_haw(r, "ONU Alias", "ONU Alias no es '--'") for _, r in cli[m].iterrows()]
    cli_dep = cli[~m].copy()
    avanzar(f"Clientes depurados: {len(cli_dep):,} válidos de {n_inicio:,}")

    # ── Leer troncales ──
    stxt.markdown('<div class="step-line">⟳ Leyendo Troncales...</div>', unsafe_allow_html=True)
    lista = []
    for f in archivos_tronc:
        df, err = leer_excel_seguro(f, COLS_TRONC, conservar_na_texto=True)
        if err: return None, err
        df["archivo_fuente"] = f.name
        lista.append(df)
    tronc_raw  = pd.concat(lista, ignore_index=True)
    n_inicio_t = len(tronc_raw)
    avanzar(f"Troncales leídas: {n_inicio_t:,} registros")

    # ── Depurar troncales ──
    stxt.markdown('<div class="step-line">⟳ Depurando Troncales...</div>', unsafe_allow_html=True)

    dn_tronc_str = tronc_raw["Device name"].astype(str).str.strip()
    olts_maestro = tronc_raw[dn_tronc_str.str.startswith("HAC")][["Device name"]].drop_duplicates()

    def reg_tronc_haw(fila, columna, motivo):
        return {
            "archivo_fuente": fila.get("archivo_fuente", ""),
            "Device_name":    str(fila.get("Device name", "")),
            "Frame_ID":       str(fila.get("Frame ID", "")),
            "Slot_ID":        str(fila.get("Slot ID", "")),
            "Port_ID":        str(fila.get("Port ID", "")),
            "columna":        columna,
            "valor_original": str(fila.get(columna, "")),
            "motivo":         motivo,
        }

    m = ~dn_tronc_str.str.startswith("HAC")
    log += [reg_tronc_haw(r, "Device name", "No inicia con HAC") for _, r in tronc_raw[m].iterrows()]
    tronc = tronc_raw[~m].copy()

    for col in ["Frame ID","Slot ID","Port ID"]:
        col_orig = tronc[col].copy()
        tronc[col] = tronc[col].astype(str)
        mk = ~es_numerico_valido(tronc[col])
        mk_log = mk & ~col_orig.isna() & (tronc[col].str.strip() != "")
        log += [reg_tronc_haw(r, col, f"Valor no numerico en {col}") for _, r in tronc[mk_log].iterrows()]
        tronc = tronc[~mk].copy()
    tronc = normalizar_enteros(tronc, ["Frame ID", "Slot ID", "Port ID"])

    # User Label: solo loguear si tiene valor real pero no empieza con TRK
    ul_orig = tronc["User Label"].copy()
    ul_str  = tronc["User Label"].astype(str).str.strip()
    m_trk   = ul_orig.isna() | (ul_str == "") | (~ul_str.str.startswith("TRK"))
    m_trk_log = ~ul_orig.isna() & (ul_str != "") & ~ul_str.str.startswith("TRK")
    log += [reg_tronc_haw(r, "User Label", "No inicia con TRK") for _, r in tronc[m_trk_log].iterrows()]
    tronc  = tronc[~m_trk].copy()
    tronc  = tronc.drop_duplicates()
    avanzar(f"Troncales depuradas: {len(tronc):,} válidas de {n_inicio_t:,}")

    # ── Warning: OLTs en Clientes sin presencia en Troncales ──
    olts_en_cli   = set(cli_dep["Device name"].unique())
    olts_en_tronc = set(olts_maestro["Device name"].unique())
    olts_solo_cli = olts_en_cli - olts_en_tronc
    if olts_solo_cli:
        for olt in sorted(olts_solo_cli):
            n = int(cli_dep[cli_dep["Device name"] == olt].shape[0])
            log.append({
                "archivo_fuente": "", "Device_name": olt,
                "Frame_ID": "", "Slot_ID": "", "Port_ID": "",
                "columna": "Device name", "valor_original": olt,
                "motivo": f"OLT con {n:,} clientes en archivo de Clientes pero sin presencia en archivo de Troncales",
            })

    # ── Cruce ──
    stxt.markdown('<div class="step-line">⟳ Cruzando datos...</div>', unsafe_allow_html=True)
    base = (
        olts_maestro
        .merge(tronc.drop(columns=["archivo_fuente","RunStatus"]), on="Device name", how="left")
        .merge(cli_dep.drop(columns=["archivo_fuente","Running Status"]), on=["Device name","Frame ID","Slot ID","Port ID"], how="left")
    )
    base["vendor"]      = "HAW"
    base["fecha_carga"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    avanzar(f"Cruce completado: {len(base):,} registros")

    # ── Métricas ──
    stxt.markdown('<div class="step-line">⟳ Calculando métricas...</div>', unsafe_allow_html=True)
    metricas = {
        "vendor":          "HAW",
        "fecha_carga":     datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_olts":      int(base["Device name"].nunique()),
        "total_troncales": int(
            base.dropna(subset=["User Label"])
            [["Device name","Frame ID","Slot ID","Port ID"]]
            .drop_duplicates()
            .shape[0]
        ),
        "total_onts":      int((~base["ONU Alias"].isna()).sum()),
    }
    avanzar("Métricas calculadas")

    log_df = pd.DataFrame(log) if log else pd.DataFrame()
    az = {f"base_Huawei_{ts}.csv": csv_bytes(base)}
    if not log_df.empty:
        az[f"log_depuracion_Huawei_{ts}.csv"] = csv_bytes(log_df)
    avanzar("Archivos listos para descarga")
    pb.progress(1.0)

    return {
        "metricas":       metricas,
        "base":           base,
        "log":            log_df,
        "archivos_zip":   az,
        "ts":             ts,
        "n_cli_inicio":   n_inicio,
        "n_cli_final":    len(cli_dep),
        "n_tronc_inicio": n_inicio_t,
        "n_tronc_final":  len(tronc),
    }, None


def procesar_onnet(archivos, pb, stxt):
    """Depuración ONNET — misma lógica que el script R 'DEPURACIÓN ONNET v1.4 (conteo histórico)'.

    A diferencia de la versión anterior, NO se filtra por la fecha más reciente antes de
    depurar: se conserva y depura todo el histórico. Luego se determina, por SERIAL, cuál
    es su OLT/TRK RR vigente (el registro más reciente) y se marca cada ONT como ACTIVO
    (si su último registro corresponde a la fecha más reciente del histórico) o INACTIVO
    (si su último registro es de una fecha anterior).
    """
    log   = []
    ts    = datetime.now().strftime("%Y-%m-%d_%H%M")
    pasos = 6
    paso  = [0]

    def avanzar(msg):
        paso[0] += 1
        pb.progress(paso[0] / pasos)
        stxt.markdown(f'<div class="step-line"><span class="step-ok">✓</span> {msg}</div>', unsafe_allow_html=True)

    COLS_ONNET = ["SERIAL","OLT","TRK RR","FECHA"]

    # ── PASO 1: Leer y consolidar TODOS los archivos (histórico completo) ──
    stxt.markdown('<div class="step-line">⟳ Leyendo y consolidando archivos ONNET...</div>', unsafe_allow_html=True)
    lista = []
    for f in archivos:
        try:
            hojas = pd.ExcelFile(f, engine="openpyxl").sheet_names
        except Exception as e:
            return None, f"No se pudo abrir '{f.name}': {e}"
        if "BASE ONNET" not in hojas:
            return None, f"'{f.name}' no tiene la hoja 'BASE ONNET'. Hojas disponibles: {', '.join(hojas)}"
        df, err = leer_excel_seguro(f, COLS_ONNET, sheet="BASE ONNET")
        if err: return None, err
        df["archivo_fuente"] = f.name
        lista.append(df)

    base_raw = pd.concat(lista, ignore_index=True)
    base_raw["FECHA"] = pd.to_datetime(base_raw["FECHA"], errors="coerce").dt.date
    avanzar(f"Archivos leídos y consolidados: {len(base_raw):,} registros históricos")

    # ── PASO 2: Detectar la fecha más reciente (informativa; NO se filtra el histórico) ──
    fecha_max = base_raw["FECHA"].max()
    avanzar(f"Fecha más reciente detectada: {fecha_max}")

    # ── PASO 3: Depuración sobre TODO el histórico ──
    stxt.markdown('<div class="step-line">⟳ Depurando registros (histórico completo)...</div>', unsafe_allow_html=True)
    n_inicio = len(base_raw)

    # [R1] OLT debe empezar por "OH"
    olt_str = base_raw["OLT"].astype(str).str.strip()
    m1 = base_raw["OLT"].isna() | (~olt_str.str.startswith("OH"))
    log += [{"regla":"R1","campo":"OLT","valor":str(r["OLT"]),"motivo":"No inicia con OH","archivo":r["archivo_fuente"]} for _,r in base_raw[m1].iterrows()]
    base_d1 = base_raw[~m1].copy()

    # [R2] SERIAL con prefijo no reconocido: solo advertencia, NO se elimina
    patron  = "^(" + "|".join(PREFIJOS_SERIAL) + ")"
    ser_str = base_d1["SERIAL"].astype(str).str.strip()
    m_raro  = base_d1["SERIAL"].isna() | (~ser_str.str.match(patron))
    if m_raro.any():
        log += [{
            "regla":"R2","campo":"SERIAL","valor":str(r["SERIAL"]),
            "motivo":f"Prefijo no reconocido — revisar ({'/'.join(PREFIJOS_SERIAL)})",
            "archivo":r["archivo_fuente"],
        } for _,r in base_d1[m_raro].iterrows()]

    # [R3] SERIAL no puede ser vacío o nulo
    m_vacio  = base_d1["SERIAL"].isna() | (base_d1["SERIAL"].astype(str).str.strip() == "")
    log     += [{
        "regla":"R3","campo":"SERIAL","valor":"(vacío)",
        "motivo":"Serial vacío o nulo — eliminado","archivo":str(r["archivo_fuente"]),
    } for _,r in base_d1[m_vacio].iterrows()]

    base_dep = base_d1[~m_vacio].copy()
    avanzar(f"Depuración histórica: {len(base_dep):,} válidos de {n_inicio:,}")

    # ── PASO 4: Relación ONT → OLT vigente + estado (ACTIVO / INACTIVO) ──
    # Un ONT puede tener varios registros en el histórico (distintas fechas).
    # Se toma el más reciente por SERIAL → esa es la OLT/TRK RR "vigente" del ONT.
    stxt.markdown('<div class="step-line">⟳ Relacionando cada ONT con su OLT y marcando estado...</div>', unsafe_allow_html=True)
    base_relacion = (
        base_dep.sort_values("FECHA", ascending=False, kind="mergesort")
        .drop_duplicates(subset="SERIAL", keep="first")
        .copy()
    )
    base_relacion["ESTADO"] = base_relacion["FECHA"].apply(lambda f: "ACTIVO" if f == fecha_max else "INACTIVO")

    n_activos   = int((base_relacion["ESTADO"] == "ACTIVO").sum())
    n_inactivos = int((base_relacion["ESTADO"] == "INACTIVO").sum())

    # Log de advertencia: ONTs que NO están activos en la fecha más reciente
    if n_inactivos > 0:
        inactivos = base_relacion[base_relacion["ESTADO"] == "INACTIVO"]
        log += [{
            "regla":"INACTIVO","campo":"SERIAL","valor":str(r["SERIAL"]),
            "motivo": f"INACTIVO — última vez visto {r['FECHA']} en OLT {r['OLT']} / TRK RR {r['TRK RR']} (no aparece en {fecha_max})",
            "archivo": r["archivo_fuente"],
        } for _,r in inactivos.iterrows()]

    avanzar(f"Relación ONT-OLT: {n_activos:,} activos / {n_inactivos:,} inactivos")

    # ── PASO 5: Métricas (histórico) ──
    metricas = {
        "vendor":               "ONNET",
        "fecha_carga":          datetime.now().strftime("%Y-%m-%d %H:%M"),
        "fecha_analizada":      str(fecha_max),
        "total_olts":           int(base_dep["OLT"].nunique()),
        "total_troncales":      int(base_dep["TRK RR"].nunique()),
        "total_onts":           int(base_dep["SERIAL"].nunique()),
        "total_onts_activos":   n_activos,
        "total_onts_inactivos": n_inactivos,
    }
    avanzar("Métricas calculadas")

    # ── PASO 6: Exportar archivos ──
    log_df = pd.DataFrame(log) if log else pd.DataFrame()
    az = {f"relacion_ONT_OLT_{ts}.csv": csv_bytes(base_relacion)}
    if not log_df.empty:
        az[f"log_depuracion_ONNET_{ts}.csv"] = csv_bytes(log_df)
    avanzar("Archivos listos para descarga")
    pb.progress(1.0)

    return {
        "metricas":     metricas,
        "base":         base_relacion,  # 1 fila por SERIAL, OLT/TRK RR vigente + ESTADO
        "log":          log_df,
        "archivos_zip": az,
        "ts":           ts,
        "n_inicio":     n_inicio,
        "n_final":      len(base_dep),
        "fecha_max":    fecha_max,
        "n_activos":    n_activos,
        "n_inactivos":  n_inactivos,
    }, None


# ── Bloque resultado: descarga + edición + publicar ───────────────────────────
def bloque_resultado(key, metricas_list, color_accent):
    r = st.session_state.get(f"resultado_{key}")
    if not r:
        return

    publicado = st.session_state.get(f"publicado_{key}", False)

    # Métricas visuales
    for m in metricas_list:
        vend = m["vendor"]
        vend_d = VENDOR_NOMBRE.get(vend, vend)
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f'<div class="mcard" style="border-color:{color_accent}44"><div class="mlabel">⎕ OLTs — {vend_d}</div><div class="mval" style="color:{color_accent}">{m["total_olts"]:,}</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="mcard" style="border-color:{color_accent}44"><div class="mlabel">⏛ Troncales — {vend_d}</div><div class="mval" style="color:{color_accent}">{m["total_troncales"]:,}</div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="mcard" style="border-color:{color_accent}44"><div class="mlabel">⏣ ONTs — {vend_d}</div><div class="mval" style="color:{color_accent}">{m["total_onts"]:,}</div></div>', unsafe_allow_html=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── DESCARGA ZIP — siempre visible ──
    zip_bytes = hacer_zip(r["archivos_zip"])
    ts        = r.get("ts", datetime.now().strftime("%Y-%m-%d_%H%M"))
    st.download_button(
        label     = "⬇ Descargar archivos (.zip)",
        data      = zip_bytes,
        file_name = f"resultados_{key}_{ts}.zip",
        mime      = "application/zip",
        key       = f"dl_{key}_{ts}",
    )

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    if publicado:
        mostrar_ok("Datos ya publicados en el dashboard.")
        return

    # ── EDICIÓN ──
    st.markdown("---")
    edit_key = f"edit_mode_{key}"

    if not st.session_state.get(edit_key, False):
        col_e, col_p = st.columns([2, 2])
        with col_e:
            pwd_edit = st.text_input("Contraseña para editar", type="password",
                                     key=f"pwd_edit_{key}", placeholder="Contraseña")
            st.markdown('<div class="edit-btn-marker"></div>', unsafe_allow_html=True)
            if st.button("✏ Habilitar edición", key=f"btn_edit_{key}"):
                if verificar_password(pwd_edit):
                    st.session_state[edit_key] = True
                    st.rerun(scope="app")
                else:
                    mostrar_error("Contraseña incorrecta.")
        with col_p:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("▷ Guardar y publicar", key=f"btn_pub_{key}", type="primary"):
                _publicar(key, metricas_list)
    else:
        # Edición activa
        st.markdown('<div class="edit-box">', unsafe_allow_html=True)
        st.markdown("**✏ Editar valores antes de publicar**")
        metricas_editadas = []
        for m in metricas_list:
            vend = m["vendor"]
            st.markdown(f"*{VENDOR_NOMBRE.get(vend, vend)}*")
            c1, c2, c3 = st.columns(3)
            with c1:
                olts  = st.number_input("OLTs",       value=int(m["total_olts"]),      min_value=0, key=f"e_olts_{key}_{vend}")
            with c2:
                tronc = st.number_input("Troncales",  value=int(m["total_troncales"]),  min_value=0, key=f"e_tronc_{key}_{vend}")
            with c3:
                onts  = st.number_input("ONTs",        value=int(m["total_onts"]),       min_value=0, key=f"e_onts_{key}_{vend}")
            metricas_editadas.append({**m, "total_olts": olts, "total_troncales": tronc, "total_onts": onts})

        # Opción para descartar ATP del resultado combinado ZTE/ATP
        if key == "zte" and any(m["vendor"] == "ATP" for m in metricas_list):
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            st.markdown('<div class="discard-atp-marker"></div>', unsafe_allow_html=True)
            if st.button("🗑 Descartar resultado ATP (usar ATP Independiente)", key="btn_discard_atp_zte"):
                st.session_state["resultado_zte"]["metricas_atp"] = None
                st.session_state[edit_key] = False
                st.rerun(scope="app")

        st.markdown('</div>', unsafe_allow_html=True)

        col_pub, col_can = st.columns([1, 1])
        with col_pub:
            if st.button("▷ Guardar y publicar", key=f"btn_pub_edit_{key}", type="primary"):
                _publicar(key, metricas_editadas)
        with col_can:
            if st.button("✕ Cancelar edición", key=f"btn_can_{key}"):
                st.session_state[edit_key] = False
                st.rerun(scope="app")

    # Log
    log_df = r.get("log", pd.DataFrame())
    with st.expander(f"≡ Log de depuración — {len(log_df):,} registros"):
        if log_df.empty:
            mostrar_ok("Sin registros eliminados.")
        else:
            st.dataframe(log_df, use_container_width=True, height=200)


def _publicar(key, metricas_list):
    """Guarda en histórico sin hacer rerun para no perder botones de descarga."""
    for m in metricas_list:
        prob = validar_metricas(m)
        if prob:
            mostrar_error(f"{VENDOR_NOMBRE.get(m['vendor'], m['vendor'])} tiene valores en 0: {', '.join(prob)}. Corrige antes de publicar.")
            return
    for m in metricas_list:
        guardar_historico(m["vendor"], m)
    generar_detalle(key, [m["vendor"] for m in metricas_list])
    limpiar_temp()
    st.cache_data.clear()
    st.session_state[f"publicado_{key}"]  = True
    st.session_state[f"edit_mode_{key}"]  = False
    st.rerun(scope="app")


# ── Paneles admin ─────────────────────────────────────────────────────────────
@st.fragment
def panel_zte():
    st.markdown('<div class="section-title panel-zte">⊞ ZTE / ATP Combinado</div>', unsafe_allow_html=True)

    # Si ya hay resultado, mostrar directamente sin uploader
    if st.session_state.get("resultado_zte"):
        r  = st.session_state["resultado_zte"]
        ml = [r["metricas_zte"]]
        if r.get("metricas_atp"):
            ml.append(r["metricas_atp"])
        bloque_resultado("zte", ml, "#b794f4")
        if st.button("↺ Nuevo procesamiento ZTE/ATP", key="reset_zte"):
            st.session_state["resultado_zte"]  = None
            st.session_state["publicado_zte"]  = False
            st.session_state["edit_mode_zte"]  = False
            st.rerun(scope="app")
        return

    archivos = st.file_uploader("Sube los archivos Excel (ONTs + Troncales ZTE/ATP)",
        type=["xlsx","xls"], accept_multiple_files=True, key="up_zte")

    if not archivos:
        st.markdown('<div class="nota"><div class="nota-texto">Sube al menos 2 archivos. Los grupos se detectan automáticamente por el prefijo numérico del nombre.</div></div>', unsafe_allow_html=True)
        return

    if len(archivos) > 20:
        mostrar_error("Máximo 20 archivos por procesamiento."); return
    for f in archivos:
        ok, err = validar_excel(f)
        if not ok:
            mostrar_error(err); return

    ga, gb, err = detectar_grupos(archivos)
    if err:
        mostrar_error(err); return

    st.markdown(f'<div class="nota"><div class="nota-texto"><b>Grupo A:</b> {", ".join(f.name for f in ga)}<br><b>Grupo B:</b> {", ".join(f.name for f in gb)}</div></div>', unsafe_allow_html=True)
    sel = st.radio("¿Cuál grupo es Troncales?", ["Grupo A","Grupo B"], key="radio_zte", horizontal=True)
    grupo_tronc = ga if sel == "Grupo A" else gb

    if st.button("⟳ Procesar ZTE / ATP", key="btn_zte", type="primary"):
        pb   = st.progress(0)
        stxt = st.empty()
        try:
            resultado, err = procesar_zte_atp(archivos, grupo_tronc, pb, stxt)
        except Exception as e:
            mostrar_error(f"Error inesperado: {e}"); return
        if err:
            mostrar_error(err); return

        prob_zte = validar_metricas(resultado["metricas_zte"])
        if prob_zte:
            mostrar_error(f"ZTE tiene valores en 0: {', '.join(prob_zte)}. Revisa los archivos.")
            return

        prob_atp = validar_metricas(resultado["metricas_atp"])
        if prob_atp:
            mostrar_warn("ATP tiene valores en 0. Solo se guardará ZTE. Si ATP no venía en estos archivos, usa ATP Independiente.")
            resultado["metricas_atp"] = None

        st.session_state["resultado_zte"] = resultado
        st.session_state["publicado_zte"] = False
        pb.empty()
        stxt.empty()
        st.rerun(scope="app")


@st.fragment
def panel_atp():
    st.markdown('<div class="section-title panel-atp">⊞ ATP Independiente</div>', unsafe_allow_html=True)
    st.markdown('<div class="nota"><div class="nota-texto">Usa este procesador cuando ATP no estaba incluido en los archivos ZTE o sus métricas quedaron en 0.</div></div>', unsafe_allow_html=True)

    if st.session_state.get("resultado_atp"):
        r = st.session_state["resultado_atp"]
        bloque_resultado("atp", [r["metricas_atp"]], "#68d391")
        if st.button("↺ Nuevo procesamiento ATP", key="reset_atp"):
            st.session_state["resultado_atp"] = None
            st.session_state["publicado_atp"] = False
            st.session_state["edit_mode_atp"] = False
            st.rerun(scope="app")
        return

    archivos = st.file_uploader("Sube los archivos Excel ATP (ONTs + Troncales)",
        type=["xlsx","xls"], accept_multiple_files=True, key="up_atp")

    if not archivos:
        return
    if len(archivos) > 20:
        mostrar_error("Máximo 20 archivos."); return
    for f in archivos:
        ok, err = validar_excel(f)
        if not ok:
            mostrar_error(err); return

    ga, gb, err = detectar_grupos(archivos)
    if err:
        mostrar_error(err); return

    st.markdown(f'<div class="nota"><div class="nota-texto"><b>Grupo A:</b> {", ".join(f.name for f in ga)}<br><b>Grupo B:</b> {", ".join(f.name for f in gb)}</div></div>', unsafe_allow_html=True)
    sel = st.radio("¿Cuál grupo es Troncales?", ["Grupo A","Grupo B"], key="radio_atp", horizontal=True)
    grupo_tronc = ga if sel == "Grupo A" else gb

    if st.button("⟳ Procesar ATP", key="btn_atp", type="primary"):
        pb   = st.progress(0)
        stxt = st.empty()
        try:
            resultado, err = procesar_zte_atp(archivos,grupo_tronc,pb,stxt,vendor_forzado="ATP")
        except Exception as e:
            mostrar_error(f"Error inesperado: {e}"); return
        if err:
            mostrar_error(err); return

        prob = validar_metricas(resultado["metricas_atp"])
        if prob:
            mostrar_error(f"ATP tiene valores en 0: {', '.join(prob)}. Revisa los archivos.")
            return

        ts = resultado["ts"]
        base_atp = resultado["base"][resultado["base"]["vendor"] == "ATP"]
        az = {f"base_ATP_{ts}.csv": csv_bytes(base_atp)}
        if not resultado["log"].empty:
            az[f"log_depuracion_ATP_{ts}.csv"] = csv_bytes(resultado["log"])
        tronc_ftth_atp = resultado.get("tronc_ftth", pd.DataFrame())
        if not tronc_ftth_atp.empty:
            onts_dep_atp = resultado["base"][resultado["base"]["vendor"] == "ATP"][
                ["NE Name","Shelf","Slot","Port","ONU Name"]
            ].dropna(subset=["ONU Name"])
            ftth_atp_cruzado = (
                tronc_ftth_atp
                .merge(onts_dep_atp, on=["NE Name","Shelf","Slot","Port"], how="left")
                [["NE Name","Shelf","Slot","Port","Port Name","ONU Name"]]
            )
            az[f"troncales_FTTH_ATP_{ts}.csv"] = csv_bytes(ftth_atp_cruzado)
        resultado["archivos_zip"] = az

        st.session_state["resultado_atp"] = resultado
        st.session_state["publicado_atp"] = False
        pb.empty()
        stxt.empty()
        st.rerun(scope="app")


@st.fragment
def panel_huawei():
    st.markdown('<div class="section-title panel-haw">⊞ Huawei</div>', unsafe_allow_html=True)

    if st.session_state.get("resultado_haw"):
        r = st.session_state["resultado_haw"]
        bloque_resultado("haw", [r["metricas"]], "#63b3ed")
        if st.button("↺ Nuevo procesamiento Huawei", key="reset_haw"):
            st.session_state["resultado_haw"] = None
            st.session_state["publicado_haw"] = False
            st.session_state["edit_mode_haw"] = False
            st.rerun(scope="app")
        return

    archivos = st.file_uploader("Sube los archivos Excel Huawei (Clientes + Troncales)",
        type=["xlsx","xls"], accept_multiple_files=True, key="up_haw")

    if not archivos:
        st.markdown('<div class="nota"><div class="nota-texto">Sube al menos 2 archivos: uno de Clientes y uno de Troncales.</div></div>', unsafe_allow_html=True)
        return
    if len(archivos) > 20:
        mostrar_error("Máximo 20 archivos."); return
    for f in archivos:
        ok, err = validar_excel(f)
        if not ok:
            mostrar_error(err); return

    ga, gb, err = detectar_grupos(archivos)
    if err:
        mostrar_error(err); return

    st.markdown(f'<div class="nota"><div class="nota-texto"><b>Grupo A:</b> {", ".join(f.name for f in ga)}<br><b>Grupo B:</b> {", ".join(f.name for f in gb)}</div></div>', unsafe_allow_html=True)
    sel = st.radio("¿Cuál grupo es Troncales?", ["Grupo A","Grupo B"], key="radio_haw", horizontal=True)
    grupo_tronc = ga if sel == "Grupo A" else gb

    if st.button("⟳ Procesar Huawei", key="btn_haw", type="primary"):
        pb   = st.progress(0)
        stxt = st.empty()
        try:
            resultado, err = procesar_huawei(archivos, grupo_tronc, pb, stxt)
        except Exception as e:
            mostrar_error(f"Error inesperado: {e}"); return
        if err:
            mostrar_error(err); return

        prob = validar_metricas(resultado["metricas"])
        if prob:
            mostrar_error(f"Huawei tiene valores en 0: {', '.join(prob)}. Revisa los archivos.")
            return

        st.session_state["resultado_haw"] = resultado
        st.session_state["publicado_haw"] = False
        pb.empty()
        stxt.empty()
        st.rerun(scope="app")


@st.fragment
def panel_onnet():
    st.markdown('<div class="section-title panel-onnet">⊞ ONNET</div>', unsafe_allow_html=True)

    if st.session_state.get("resultado_onnet"):
        r = st.session_state["resultado_onnet"]
        m = r["metricas"]
        st.markdown(f'''<div class="nota"><div class="nota-texto">
            ≡ Fecha más reciente del histórico: <span class="nota-fecha">{m.get("fecha_analizada","")}</span> ·
            ONTs activos: <b style="color:#68d391">{m.get("total_onts_activos", 0):,}</b> ·
            ONTs inactivos: <b style="color:#fc8181">{m.get("total_onts_inactivos", 0):,}</b>
        </div></div>''', unsafe_allow_html=True)
        bloque_resultado("onnet", [m], "#f6ad55")
        if st.button("↺ Nuevo procesamiento ONNET", key="reset_onnet"):
            st.session_state["resultado_onnet"] = None
            st.session_state["publicado_onnet"] = False
            st.session_state["edit_mode_onnet"] = False
            st.rerun(scope="app")
        return

    archivos = st.file_uploader("Sube los archivos Excel ONNET (hoja 'BASE ONNET')",
        type=["xlsx","xls"], accept_multiple_files=True, key="up_onnet")

    if not archivos:
        st.markdown('<div class="nota"><div class="nota-texto">El archivo debe tener la hoja "BASE ONNET" con columnas: SERIAL, OLT, TRK RR, FECHA.</div></div>', unsafe_allow_html=True)
        return
    if len(archivos) > 20:
        mostrar_error("Máximo 20 archivos."); return
    for f in archivos:
        ok, err = validar_excel(f)
        if not ok:
            mostrar_error(err); return

    if st.button("⟳ Procesar ONNET", key="btn_onnet", type="primary"):
        pb   = st.progress(0)
        stxt = st.empty()
        try:
            resultado, err = procesar_onnet(archivos, pb, stxt)
        except Exception as e:
            mostrar_error(f"Error inesperado: {e}"); return
        if err:
            mostrar_error(err); return

        prob = validar_metricas(resultado["metricas"])
        if prob:
            mostrar_error(f"ONNET tiene valores en 0: {', '.join(prob)}. Revisa los archivos.")
            return

        st.session_state["resultado_onnet"] = resultado
        st.session_state["publicado_onnet"] = False
        pb.empty()
        stxt.empty()
        st.rerun(scope="app")  # necesario para mostrar bloque_resultado sin uploader


@st.fragment
def panel_notas():
    st.markdown('<div class="section-title">⊙ Notas</div>', unsafe_allow_html=True)

    # ── Agregar nota ──
    vendor_sel = st.selectbox(
        "Pestaña", list(TABS_NOTAS.keys()),
        format_func=lambda v: TABS_NOTAS[v], key="nota_vendor_select",
    )
    texto_nuevo = st.text_area("Nueva nota", key="nota_texto_nueva", placeholder="Escribe la nota...")
    if st.button("＋ Agregar nota", key="btn_agregar_nota"):
        if texto_nuevo.strip():
            guardar_nota(vendor_sel, texto_nuevo)
            st.cache_data.clear()
            del st.session_state["nota_texto_nueva"]
            mostrar_ok("Nota agregada.")
            st.rerun(scope="app")
        else:
            mostrar_error("La nota no puede estar vacía.")

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ── Listado de notas existentes, agrupadas por pestaña ──
    df_notas = cargar_notas()
    if df_notas.empty:
        mostrar_ok("No hay notas registradas todavía.")
    else:
        for vendor_tag in TABS_NOTAS:
            sub = df_notas[df_notas["vendor"] == vendor_tag].sort_values("fecha", ascending=False)
            if sub.empty:
                continue
            st.markdown(f"**{TABS_NOTAS[vendor_tag]}**")
            for _, row in sub.iterrows():
                nid        = row["id"]
                texto_html = html.escape(str(row["texto"])).replace("\n", "<br>")
                c1, c2 = st.columns([6, 1])
                with c1:
                    st.markdown(
                        f'<div class="nota"><div class="nota-texto">{texto_html}<br>'
                        f'<span style="color:rgba(255,255,255,0.35);font-size:11px">{row["fecha"]}</span></div></div>',
                        unsafe_allow_html=True,
                    )
                with c2:
                    if st.button("🗑", key=f"btn_del_nota_{nid}", help="Borrar nota"):
                        st.session_state["confirmar_borrado_nota"] = nid
                        st.rerun(scope="app")
            st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # ── Confirmación de borrado (requiere contraseña) ──
    pendiente = st.session_state.get("confirmar_borrado_nota")
    if pendiente:
        fila   = df_notas[df_notas["id"] == pendiente]
        previa = html.escape(str(fila.iloc[0]["texto"]))[:120] if not fila.empty else ""
        st.markdown(
            f'<div class="warn-box"><div class="warn-text">⚠ Vas a borrar esta nota: "{previa}". '
            f'Ingresa la contraseña para confirmar.</div></div>',
            unsafe_allow_html=True,
        )
        pwd_borrar = st.text_input("Contraseña", type="password", key="pwd_borrar_nota")
        cc1, cc2 = st.columns([1, 1])
        with cc1:
            if st.button("✕ Confirmar borrado", key="btn_confirmar_borrado_nota"):
                if verificar_password(pwd_borrar):
                    borrar_nota(pendiente)
                    st.cache_data.clear()
                    st.session_state["confirmar_borrado_nota"] = None
                    mostrar_ok("Nota borrada.")
                    st.rerun(scope="app")
                else:
                    mostrar_error("Contraseña incorrecta.")
        with cc2:
            if st.button("Cancelar", key="btn_cancelar_borrado_nota"):
                st.session_state["confirmar_borrado_nota"] = None
                st.rerun(scope="app")


def panel_password():
    st.markdown('<div class="section-title">⊙ Cambiar contraseña</div>', unsafe_allow_html=True)
    actual  = st.text_input("Contraseña actual",          type="password", key="pwd_actual")
    nueva   = st.text_input("Nueva contraseña",            type="password", key="pwd_nueva")
    confirm = st.text_input("Confirmar nueva contraseña",  type="password", key="pwd_confirm")
    if st.button("Cambiar contraseña", key="btn_cambiar_pwd"):
        if not verificar_password(actual):
            mostrar_error("La contraseña actual no es correcta.")
        elif len(nueva) < 6:
            mostrar_error("La nueva contraseña debe tener al menos 6 caracteres.")
        elif nueva != confirm:
            mostrar_error("Las contraseñas no coinciden.")
        else:
            nuevo_hash = hashlib.sha256(nueva.encode()).hexdigest()
            set_key(ENV_PATH, "ADMIN_PASSWORD", nuevo_hash)
            load_dotenv(ENV_PATH, override=True)
            os.environ["ADMIN_PASSWORD"] = nuevo_hash
            mostrar_ok("Contraseña actualizada correctamente.")


@st.dialog("⚙ Panel de Administrador")
def dialogo_admin():
    st.session_state["admin_dialog_open"] = True

    if not st.session_state.admin_logged:
        st.markdown("#### ⊡ Acceso Administrador")

        if st.session_state.lockout_until:
            restante = (st.session_state.lockout_until - datetime.now()).total_seconds()
            if restante > 0:
                mostrar_error(f"Demasiados intentos fallidos. Espera {int(restante)} segundos.")
                st.stop()
            else:
                st.session_state.lockout_until  = None
                st.session_state.login_attempts = 0

        pwd = st.text_input("", type="password", key="pwd_login",
                            placeholder="Ingresa la contraseña de administrador")
        col_btn, _ = st.columns([1, 3])
        with col_btn:
            if st.button("Ingresar", key="btn_login", type="primary"):
                if verificar_password(pwd):
                    st.session_state.admin_logged   = True
                    st.session_state.login_attempts = 0
                    st.rerun(scope="app")
                else:
                    st.session_state.login_attempts += 1
                    restantes = 3 - st.session_state.login_attempts
                    if st.session_state.login_attempts >= 3:
                        st.session_state.lockout_until = datetime.now() + timedelta(minutes=5)
                        mostrar_error("Demasiados intentos. Bloqueado por 5 minutos.")
                    else:
                        mostrar_error(f"Contraseña incorrecta. {restantes} intento(s) restante(s).")
    else:
        col_t, col_s = st.columns([4, 1])
        with col_t:
            st.markdown("#### ⚙ Panel de Administrador")
        with col_s:
            if st.button("↩ Cerrar sesión", key="btn_logout"):
                st.session_state.admin_logged      = False
                st.session_state["admin_dialog_open"] = False
                st.rerun(scope="app")

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        with st.expander("⊞ ZTE / ATP Combinado", expanded=True):
            panel_zte()
        with st.expander("⊞ ATP Independiente"):
            panel_atp()
        with st.expander("⊞ Huawei"):
            panel_huawei()
        with st.expander("⊞ ONNET"):
            panel_onnet()

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        with st.expander("⊙ Notas"):
            panel_notas()

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        with st.expander("⊙ Cambiar contraseña"):
            panel_password()


# ── Notas públicas (solo lectura) ────────────────────────────────────────────
def mostrar_notas_publicas(vendor_tag):
    df_notas = cargar_notas()
    sub = df_notas[df_notas["vendor"] == vendor_tag].sort_values("fecha", ascending=False) if not df_notas.empty else df_notas
    if sub.empty:
        return
    with st.expander(f"📌 Notas ({len(sub)})"):
        for _, row in sub.iterrows():
            texto_html = html.escape(str(row["texto"])).replace("\n", "<br>")
            st.markdown(
                f'<div class="nota"><div class="nota-texto">{texto_html}<br>'
                f'<span style="color:rgba(255,255,255,0.35);font-size:11px">{row["fecha"]}</span></div></div>',
                unsafe_allow_html=True,
            )


# ── Header ────────────────────────────────────────────────────────────────────
hist = cargar()

h1, h2, h3 = st.columns([3, 1, 0.3])
with h1:
    st.markdown("## 🖧 Red FTTH — Crecimiento")
    if not hist.empty:
        ultima     = hist["fecha_carga"].max()
        ultima_str = ultima.strftime("%d %b %Y") if (ultima.hour == 0 and ultima.minute == 0) else ultima.strftime("%d %b %Y — %H:%M")
    else:
        ultima_str = "Sin datos"
    st.markdown(f"<p style='color:rgba(255,255,255,0.35);font-size:12px;margin-top:-10px'>Última ejecución: {ultima_str}</p>", unsafe_allow_html=True)
with h2:
    if st.button("⟳ Actualizar datos"):
        st.cache_data.clear()
        st.rerun(scope="app")
with h3:
    if st.button("⚙", key="btn_abrir_admin", help="Panel de administrador"):
        st.session_state["admin_dialog_open"] = True

# Abre (o reabre tras cualquier rerun: login, publicar, nuevo procesamiento, etc.)
# el diálogo de admin mientras la bandera siga activa, para que no se sienta
# como que "te saca" del panel.
if st.session_state.get("admin_dialog_open", False):
    dialogo_admin()

if not hist.empty:
    ultima_nota = hist["fecha_carga"].max()
    fn = ultima_nota.strftime("%d de %B de %Y a las %H:%M") if not (ultima_nota.hour == 0 and ultima_nota.minute == 0) else ultima_nota.strftime("%d de %B de %Y")
    st.markdown(f"""<div class="nota"><div class="nota-texto">
        ≡ Los valores reportados corresponden únicamente a equipos activos y operativos en la red residencial FTTH
        a <span class="nota-fecha">{fn}</span>.
        Esta fecha y hora corresponde al momento de ejecución y depuración de los scripts de procesamiento.
    </div></div>""", unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ── Pestañas ──────────────────────────────────────────────────────────────────
t0, t1, t2, t3, t4 = st.tabs(["⎔ General","⊞ ZTE","⊞ Huawei","⊞ ATP","⊞ ONNET"])

with t0:
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    mostrar_notas_publicas("GENERAL")
    if not hist.empty:
        ultimos         = hist.sort_values("fecha_carga").groupby("vendor").last().reset_index()
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
    for i, vendor in enumerate(["ZTE","HAW","ATP","ONNET"]):
        c_onts, c_tronc, c_olts = COLORES[vendor]
        with cols[i]:
            df_v = hist[hist["vendor"] == vendor] if not hist.empty else pd.DataFrame(columns=COLS)
            if not df_v.empty:
                u = df_v.iloc[-1]
                st.markdown(f'''<div class="mcard" style="border-color:{c_onts}44">
                    <div class="mlabel" style="color:{c_onts}">{VENDOR_NOMBRE.get(vendor, vendor)}</div>
                    <div style="font-size:11px;color:rgba(255,255,255,0.4);margin-top:8px">⎕ OLTs</div>
                    <div style="font-size:20px;font-weight:600;color:#fff">{int(u["total_olts"]):,}</div>
                    <div style="font-size:11px;color:rgba(255,255,255,0.4);margin-top:6px">⏛ Troncales</div>
                    <div style="font-size:20px;font-weight:600;color:#fff">{int(u["total_troncales"]):,}</div>
                    <div style="font-size:11px;color:rgba(255,255,255,0.4);margin-top:6px">⏣ ONTs</div>
                    <div style="font-size:20px;font-weight:600;color:#fff">{int(u["total_onts"]):,}</div>
                </div>''', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="mcard" style="border-color:rgba(255,255,255,0.08)"><div class="mlabel" style="color:rgba(255,255,255,0.25)">{VENDOR_NOMBRE.get(vendor, vendor)}</div><div style="font-size:13px;color:rgba(255,255,255,0.2);margin-top:20px">⊜ Pendiente</div></div>', unsafe_allow_html=True)

with t1:
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    mostrar_notas_publicas("ZTE")
    vista("ZTE", hist)

with t2:
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    mostrar_notas_publicas("HAW")
    vista("HAW", hist)

with t3:
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    mostrar_notas_publicas("ATP")
    vista("ATP", hist)

with t4:
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    mostrar_notas_publicas("ONNET")
    vista("ONNET", hist)
