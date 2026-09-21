import io
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

MONTHS = {
    "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5,
    "Junio": 6, "Julio": 7, "Agosto": 8, "Septiembre": 9,
    "Setiembre": 9, "Octubre": 10, "Noviembre": 11, "Novimebre": 11,
    "Diciembre": 12
}

DISPLAY = {
    "C": "Índice C", "E": "Índice E", "MEI": "MEI v2",
    "PDO": "PDO", "SOI": "SOI"
}

DESCRIPTIONS = {
    "C": "Variabilidad ENSO asociada principalmente al Pacífico central; forma parte del enfoque E/C de Takahashi et al. (2011).",
    "E": "Índice asociado al régimen del Pacífico oriental (EP), especialmente útil para caracterizar calentamientos extremos en el este del Pacífico.",
    "MEI": "Índice multivariado que integra variables oceánicas y atmosféricas del Pacífico tropical.",
    "PDO": "Modo de variabilidad de baja frecuencia del Pacífico Norte; no es una clasificación directa de El Niño o La Niña.",
    "SOI": "Indicador atmosférico basado en la diferencia normalizada de presión entre Tahití y Darwin."
}

DEFAULT_THRESHOLDS = {"C": 0.5, "E": 0.5, "MEI": 0.5, "PDO": 1.0, "SOI": 0.5}
HISTORICAL_WINDOWS = {
    "1982–83": ("1982-01", "1983-12"),
    "1997–98": ("1997-01", "1998-12"),
    "2015–16": ("2015-01", "2016-12"),
    "2023–24": ("2023-01", "2024-12")
}

st.set_page_config(page_title="FEN Analizador 2.0", page_icon="🌎", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container {padding-top: 1.4rem; padding-bottom: 2rem;}
.hero {padding: 1.5rem 1.7rem; border-radius: 18px; border: 1px solid #d9e3ee; background: linear-gradient(135deg,#f6fbff,#ffffff); margin-bottom: 1rem;}
.hero h1 {margin:0; font-size:2.15rem; color:#163A5F;}
.hero p {margin:.35rem 0 0; color:#5b7083; font-size:1.03rem;}
.card {padding: 1rem; border-radius: 14px; border: 1px solid #dfe7ef; background:#fff;}
.small {color:#657786; font-size:.9rem;}
.section-title {color:#163A5F; font-weight:700; font-size:1.45rem; margin-top:.4rem;}
</style>
""", unsafe_allow_html=True)


def make_date(year, month):
    return pd.to_datetime(dict(year=year, month=month, day=1), errors="coerce")


@st.cache_data

def load_data(file_bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    result = {}

    if "C y E" in xls.sheet_names:
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name="C y E")
        df.columns = [str(c).strip() for c in df.columns]
        required = {"year", "month", "E_index", "C_index"}
        if required.issubset(df.columns):
            years = pd.to_numeric(df["year"], errors="coerce")
            months = pd.to_numeric(df["month"], errors="coerce")
            df["Date"] = make_date(years, months)
            result["C"] = df[["Date", "C_index"]].rename(columns={"C_index": "C"})
            result["E"] = df[["Date", "E_index"]].rename(columns={"E_index": "E"})

    for name in ["MEI", "PDO", "SOI"]:
        if name not in xls.sheet_names:
            continue
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=name)
        df.columns = [str(c).strip() for c in df.columns]
        year_col = df.columns[0]
        rows = []
        for _, row in df.iterrows():
            year = pd.to_numeric(row[year_col], errors="coerce")
            if pd.isna(year):
                continue
            for col in df.columns[1:]:
                month = MONTHS.get(str(col).strip())
                if month is None:
                    continue
                value = pd.to_numeric(pd.Series([row[col]]), errors="coerce").iloc[0]
                rows.append({"Date": pd.Timestamp(int(year), month, 1), name: value})
        result[name] = pd.DataFrame(rows)

    if not result:
        raise ValueError("No se encontraron hojas compatibles.")
    frames = [v.set_index("Date") for v in result.values() if not v.empty]
    data = pd.concat(frames, axis=1).sort_index()
    data = data[~data.index.duplicated(keep="first")]
    return data


def standardize(s):
    valid = s.dropna()
    if len(valid) < 2 or valid.std() == 0:
        return s * 0
    return (s - valid.mean()) / valid.std()


def rolling(s, months):
    return s.rolling(months, min_periods=max(2, months // 2)).mean()


def safe_fig(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight")
    buf.seek(0)
    return buf.getvalue()


def event_table(s, threshold, min_duration, positive_label="Positivo", negative_label="Negativo"):
    s = s.dropna().sort_index()
    rows = []
    for positive, label in [(True, positive_label), (False, negative_label)]:
        mask = s >= threshold if positive else s <= -threshold
        start = None
        previous = None
        for date, flag in mask.items():
            if flag and start is None:
                start = date
            if not flag and start is not None:
                end = previous
                duration = (end.year - start.year) * 12 + end.month - start.month + 1
                if duration >= min_duration:
                    seg = s.loc[start:end]
                    rows.append({"Señal": label, "Inicio": start.strftime("%Y-%m"), "Fin": end.strftime("%Y-%m"), "Duración (meses)": duration, "Extremo": round(float(seg.max() if positive else seg.min()), 3)})
                start = None
            previous = date
        if start is not None and previous is not None:
            end = previous
            duration = (end.year - start.year) * 12 + end.month - start.month + 1
            if duration >= min_duration:
                seg = s.loc[start:end]
                rows.append({"Señal": label, "Inicio": start.strftime("%Y-%m"), "Fin": end.strftime("%Y-%m"), "Duración (meses)": duration, "Extremo": round(float(seg.max() if positive else seg.min()), 3)})
    return pd.DataFrame(rows)


def interpretation(name, s, threshold):
    s = s.dropna()
    if s.empty:
        return "No existen datos válidos para interpretar."
    if name == "SOI":
        physical = "El SOI representa la componente atmosférica de ENSO. NOAA indica que períodos negativos prolongados coinciden con condiciones típicas de El Niño y períodos positivos prolongados con condiciones típicas de La Niña."
    elif name == "MEI":
        physical = "El MEI integra variables oceánicas y atmosféricas y permite seguir la intensidad y evolución de las condiciones ENSO. Valores positivos suelen corresponder a una señal cálida y negativos a una señal fría."
    elif name == "PDO":
        physical = "El PDO describe una modalidad de variabilidad del Pacífico Norte de escala temporal más larga. Debe analizarse como variabilidad del Pacífico y no como una clasificación directa de ENSO."
    elif name == "E":
        physical = "En el enfoque de Takahashi et al. (2011), el E-index caracteriza la componente del Pacífico oriental y es especialmente relevante para eventos cálidos extremos."
    else:
        physical = "En el enfoque de Takahashi et al. (2011), el C-index representa principalmente la variabilidad asociada al Pacífico central y participa en la descripción conjunta de la diversidad de ENSO."
    pos = int((s >= threshold).sum())
    neg = int((s <= -threshold).sum())
    return f"{physical} En esta serie hay {pos} meses con valores ≥ +{threshold:.2f} y {neg} meses con valores ≤ −{threshold:.2f}. Esto es una descripción estadística del archivo cargado; no constituye por sí sola una clasificación oficial de El Niño o La Niña."


def build_summary(data, indices):
    rows = []
    for n in indices:
        s = data[n].dropna()
        rows.append({
            "Índice": DISPLAY[n], "Código": n, "Datos válidos": len(s),
            "Inicio": s.index.min().strftime("%Y-%m") if not s.empty else "—",
            "Fin": s.index.max().strftime("%Y-%m") if not s.empty else "—",
            "Faltantes": int(data[n].isna().sum()),
            "Media": s.mean() if not s.empty else np.nan,
            "Desv. estándar": s.std() if not s.empty else np.nan
        })
    return pd.DataFrame(rows)


# ----------------- Carga -----------------
st.sidebar.markdown("# 🌎 FEN Analizador 2.0")
st.sidebar.caption("C · E · MEI · PDO · SOI")
uploaded = st.sidebar.file_uploader("📂 Subir archivo Excel", type=["xlsx", "xls"])
if uploaded is None:
    default = Path("DATOS.xlsx")
    file_bytes = default.read_bytes() if default.exists() else None
    if file_bytes is not None:
        st.sidebar.success("DATOS.xlsx encontrado")
else:
    file_bytes = uploaded.getvalue()
    st.sidebar.success(f"Cargado: {uploaded.name}")

if file_bytes is None:
    st.markdown('<div class="hero"><h1>🌎 FEN Analizador 2.0</h1><p>Herramienta para explorar índices climáticos asociados al ENSO y al FEN.</p></div>', unsafe_allow_html=True)
    st.info("Carga un archivo Excel para comenzar. El formato base contiene las hojas: C y E, MEI, PDO y SOI.")
    st.stop()

try:
    data = load_data(file_bytes)
except Exception as e:
    st.error(f"No se pudo leer el archivo: {e}")
    st.stop()

indices = [x for x in ["C", "E", "MEI", "PDO", "SOI"] if x in data.columns]

st.sidebar.markdown("---")
module = st.sidebar.radio("Módulo", [
    "🏠 Dashboard", "📈 Series temporales", "🔄 Comparación", "🔗 Correlaciones",
    "⏱️ Rezagos", "🌊 Eventos", "📊 Estadísticas", "🧠 Interpretación", "📚 Metodología"
])

st.sidebar.markdown("---")
st.sidebar.caption(f"Período disponible: {data.index.min():%Y-%m} → {data.index.max():%Y-%m}")

# ----------------- Dashboard -----------------
if module == "🏠 Dashboard":
    st.markdown('<div class="hero"><h1>🌎 FEN Analizador 2.0</h1><p>Exploración estadística, comparación e interpretación didáctica de C, E, MEI, PDO y SOI.</p></div>', unsafe_allow_html=True)
    a,b,c,d = st.columns(4)
    a.metric("Índices disponibles", len(indices))
    b.metric("Meses", f"{len(data):,}")
    c.metric("Inicio", data.index.min().strftime("%Y-%m"))
    d.metric("Fin", data.index.max().strftime("%Y-%m"))
    st.markdown("### Estado de los datos")
    st.dataframe(build_summary(data, indices).round(3), use_container_width=True, hide_index=True)
    st.markdown("### Evolución conjunta estandarizada")
    fig, ax = plt.subplots(figsize=(13, 5.5))
    for n in indices:
        ax.plot(data.index, standardize(data[n]), linewidth=1, label=n)
    ax.axhline(0, linewidth=.8)
    ax.set_ylabel("z-score")
    ax.set_xlabel("Fecha")
    ax.grid(alpha=.2)
    ax.legend(ncol=5)
    st.pyplot(fig, use_container_width=True)
    st.download_button("⬇ Descargar gráfico PNG", safe_fig(fig), "dashboard_FEN.png", "image/png")
    st.info("La estandarización sirve para comparar la posición relativa de las series. No convierte sus definiciones físicas en equivalentes.")

# ----------------- Series -----------------
elif module == "📈 Series temporales":
    st.markdown('<div class="section-title">📈 Series temporales</div>', unsafe_allow_html=True)
    n = st.selectbox("Índice", indices, index=indices.index("MEI") if "MEI" in indices else 0)
    c1,c2,c3 = st.columns(3)
    threshold = c1.number_input("Umbral visual", value=float(DEFAULT_THRESHOLDS[n]), min_value=0.0, step=.1)
    window = c2.number_input("Media móvil (meses)", value=3, min_value=1, max_value=60, step=1)
    show_roll = c3.checkbox("Mostrar media móvil", True)
    start_year, end_year = int(data.index.year.min()), int(data.index.year.max())
    if start_year < end_year:
        years = st.slider("Rango de años", start_year, end_year, (start_year, end_year))
    else:
        years = (start_year, end_year)
    s = data[n].dropna()
    s = s[(s.index.year >= years[0]) & (s.index.year <= years[1])]
    fig, ax = plt.subplots(figsize=(13,5.5))
    ax.plot(s.index, s.values, linewidth=1.2, label=n)
    if show_roll and len(s) > 1:
        ax.plot(s.index, rolling(s, window), linewidth=1.8, label=f"Media móvil {window} meses")
    ax.axhline(0, linewidth=.8)
    ax.axhline(threshold, linestyle="--", linewidth=.8)
    ax.axhline(-threshold, linestyle="--", linewidth=.8)
    ax.set_title(f"{DISPLAY[n]} — {years[0]} a {years[1]}")
    ax.set_xlabel("Fecha"); ax.set_ylabel(n); ax.grid(alpha=.2); ax.legend()
    st.pyplot(fig, use_container_width=True)
    st.download_button("⬇ Descargar PNG", safe_fig(fig), f"{n}_serie.png", "image/png")
    st.info(interpretation(n, s, threshold))
    st.markdown(f"**Descripción:** {DESCRIPTIONS[n]}")

# ----------------- Comparison -----------------
elif module == "🔄 Comparación":
    st.markdown('<div class="section-title">🔄 Comparación de índices</div>', unsafe_allow_html=True)
    selected = st.multiselect("Selecciona índices", indices, default=indices)
    if selected:
        fig, ax = plt.subplots(figsize=(13,6))
        for n in selected:
            ax.plot(data.index, standardize(data[n]), linewidth=1, label=n)
        ax.axhline(0, linewidth=.8)
        ax.set_title("Índices estandarizados (z-score)"); ax.set_xlabel("Fecha"); ax.set_ylabel("z-score")
        ax.grid(alpha=.2); ax.legend(ncol=5)
        st.pyplot(fig, use_container_width=True)
        st.download_button("⬇ Descargar PNG", safe_fig(fig), "comparacion_indices.png", "image/png")
        st.warning("La comparación estandarizada es estadística. Para una interpretación climática deben considerarse las definiciones de cada índice y su fuente.")

# ----------------- Correlation -----------------
elif module == "🔗 Correlaciones":
    st.markdown('<div class="section-title">🔗 Correlaciones</div>', unsafe_allow_html=True)
    selected = st.multiselect("Índices", indices, default=indices)
    if len(selected) >= 2:
        corr = data[selected].corr(min_periods=3)
        st.dataframe(corr.round(3), use_container_width=True)
        fig, ax = plt.subplots(figsize=(8,6))
        im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="RdBu_r")
        ax.set_xticks(range(len(selected)), selected); ax.set_yticks(range(len(selected)), selected)
        for i in range(len(selected)):
            for j in range(len(selected)):
                ax.text(j, i, f"{corr.iloc[i,j]:.2f}", ha="center", va="center")
        ax.set_title("Matriz de correlación de Pearson"); fig.colorbar(im, ax=ax)
        st.pyplot(fig, use_container_width=True)
        st.download_button("⬇ Descargar matriz CSV", corr.to_csv().encode("utf-8"), "correlaciones_FEN.csv", "text/csv")
        st.info("Pearson mide asociación lineal. Una correlación alta no demuestra causalidad ni implica que dos índices tengan el mismo significado físico.")
    else:
        st.info("Selecciona al menos dos índices.")

# ----------------- Lags -----------------
elif module == "⏱️ Rezagos":
    st.markdown('<div class="section-title">⏱️ Análisis de rezagos</div>', unsafe_allow_html=True)
    c1,c2,c3 = st.columns(3)
    a = c1.selectbox("Índice A", indices, index=indices.index("MEI") if "MEI" in indices else 0)
    b = c2.selectbox("Índice B", indices, index=indices.index("SOI") if "SOI" in indices else min(1,len(indices)-1))
    maxlag = c3.number_input("Máximo rezago (meses)", value=24, min_value=1, max_value=60, step=1)
    lags = range(-int(maxlag), int(maxlag)+1)
    rs, ns = [], []
    for lag in lags:
        pair = pd.concat([data[a], data[b].shift(lag)], axis=1).dropna()
        rs.append(pair.iloc[:,0].corr(pair.iloc[:,1]) if len(pair)>=3 else np.nan)
        ns.append(len(pair))
    fig, ax = plt.subplots(figsize=(13,5))
    ax.plot(list(lags), rs, marker="o", markersize=3)
    ax.axhline(0, linewidth=.8); ax.axvline(0, linestyle="--", linewidth=.8)
    ax.set_ylim(-1,1); ax.set_xlabel("Rezago (meses)"); ax.set_ylabel("r de Pearson")
    ax.set_title(f"Rezagos: {a} vs {b}"); ax.grid(alpha=.2)
    st.pyplot(fig, use_container_width=True)
    valid = [(abs(r),lag,r,n) for lag,r,n in zip(lags,rs,ns) if not pd.isna(r)]
    if valid:
        _, lag, r, n = max(valid)
        st.metric("Mayor |r| observado", f"{r:.3f}", f"rezago {lag} meses · n={n}")
    st.warning("El rezago indica asociación temporal, no causalidad. La autocorrelación y el tamaño de muestra deben considerarse antes de interpretar significancia.")

# ----------------- Events -----------------
elif module == "🌊 Eventos":
    st.markdown('<div class="section-title">🌊 Explorador de eventos</div>', unsafe_allow_html=True)
    st.warning("Este módulo es exploratorio. No sustituye una clasificación oficial de ENSO/FEN. Los umbrales dependen del índice y de la metodología seleccionada.")
    n = st.selectbox("Índice para explorar", indices, index=indices.index("MEI") if "MEI" in indices else 0)
    c1,c2 = st.columns(2)
    threshold = c1.number_input("Umbral exploratorio", value=float(DEFAULT_THRESHOLDS[n]), min_value=0.0, step=.1)
    duration = c2.number_input("Duración mínima (meses)", value=3, min_value=1, step=1)
    pos_label, neg_label = ("Señal cálida / positiva", "Señal fría / negativa")
    if n == "SOI": pos_label, neg_label = ("SOI positivo", "SOI negativo")
    if n == "PDO": pos_label, neg_label = ("PDO positivo", "PDO negativo")
    events = event_table(data[n], threshold, duration, pos_label, neg_label)
    st.dataframe(events, use_container_width=True, hide_index=True)
    st.download_button("⬇ Descargar eventos CSV", events.to_csv(index=False).encode("utf-8"), "eventos_exploratorios.csv", "text/csv")

    st.markdown("### Comparación rápida de períodos históricos")
    selected_event = st.selectbox("Período", list(HISTORICAL_WINDOWS.keys()))
    ini, fin = HISTORICAL_WINDOWS[selected_event]
    sub = data.loc[ini:fin, indices]
    if not sub.empty:
        rows=[]
        for x in indices:
            s=sub[x].dropna()
            rows.append({"Índice":x,"n":len(s),"Media":s.mean(),"Mínimo":s.min(),"Máximo":s.max()})
        st.dataframe(pd.DataFrame(rows).round(3), use_container_width=True, hide_index=True)
        fig, ax = plt.subplots(figsize=(13,5))
        for x in indices:
            ax.plot(sub.index, standardize(sub[x]), label=x, linewidth=1)
        ax.axhline(0, linewidth=.8); ax.legend(ncol=5); ax.grid(alpha=.2)
        ax.set_title(f"Comparación estandarizada: {selected_event}"); ax.set_xlabel("Fecha")
        st.pyplot(fig, use_container_width=True)
    else:
        st.info("Ese período no está disponible en el archivo cargado.")

# ----------------- Statistics -----------------
elif module == "📊 Estadísticas":
    st.markdown('<div class="section-title">📊 Estadísticas descriptivas</div>', unsafe_allow_html=True)
    rows=[]
    for n in indices:
        s=data[n].dropna()
        rows.append({"Índice":n,"Datos":len(s),"Inicio":s.index.min().strftime("%Y-%m"),"Fin":s.index.max().strftime("%Y-%m"),"Media":s.mean(),"Desv. estándar":s.std(),"Mínimo":s.min(),"Fecha mín.":s.idxmin().strftime("%Y-%m"),"Máximo":s.max(),"Fecha máx.":s.idxmax().strftime("%Y-%m"),"P10":s.quantile(.1),"P50":s.quantile(.5),"P90":s.quantile(.9)})
    df=pd.DataFrame(rows)
    st.dataframe(df.round(3), use_container_width=True, hide_index=True)
    st.download_button("⬇ Descargar estadísticas CSV", df.to_csv(index=False).encode("utf-8"), "estadisticas_FEN.csv", "text/csv")

# ----------------- Interpretation -----------------
elif module == "🧠 Interpretación":
    st.markdown('<div class="section-title">🧠 Interpretación didáctica</div>', unsafe_allow_html=True)
    n=st.selectbox("Índice", indices, index=indices.index("MEI") if "MEI" in indices else 0)
    threshold=st.number_input("Umbral estadístico de apoyo", value=float(DEFAULT_THRESHOLDS[n]), min_value=0.0, step=.1)
    s=data[n].dropna()
    st.info(interpretation(n,s,threshold))
    st.markdown("### ¿Qué significa cada índice?")
    for x in indices:
        with st.expander(f"{DISPLAY[x]} ({x})"):
            st.write(DESCRIPTIONS[x])
    st.markdown("### Lectura responsable")
    st.write("1. Primero observa la señal estadística. 2. Luego interpreta el significado físico del índice. 3. Finalmente contrasta con los demás índices y con la metodología oficial de tu investigación. 4. No declares un evento oficial solo por superar un umbral exploratorio.")

# ----------------- Methodology -----------------
elif module == "📚 Metodología":
    st.markdown('<div class="section-title">📚 Metodología y fuentes</div>', unsafe_allow_html=True)
    st.markdown("**C y E — Takahashi et al. (2011).** Los índices E y C se construyen a partir de los dos primeros componentes principales de anomalías de SST tropicales y mediante una rotación de 45°. El E-index se asocia al régimen del Pacífico oriental y el C-index al régimen central/cálido moderado y frío.")
    st.markdown("**MEI v2 — NOAA PSL.** Integra presión al nivel del mar, SST, vientos zonales y meridionales y OLR para caracterizar el estado ENSO.")
    st.markdown("**SOI — NOAA CPC.** Representa la Oscilación del Sur mediante diferencias de presión normalizadas entre Tahití y Darwin; la señal negativa se asocia típicamente a El Niño y la positiva a La Niña cuando es persistente.")
    st.markdown("**PDO — NOAA PSL.** Es un patrón de variabilidad del Pacífico Norte y debe analizarse separadamente de una clasificación directa de ENSO.")
    st.markdown("**Para el FEN en Perú:** IMARPE/SIOFEN presenta ICEN, ONI, MEI v2, IOS y otros índices; la herramienta debe usarse junto con la metodología específica de la investigación.")
    st.markdown("### Fuentes consultadas")
    st.markdown("- Takahashi et al. (2011), *ENSO regimes: Reinterpreting the canonical and Modoki El Niño*.\n- NOAA Physical Sciences Laboratory — MEI v2, ENSO Dashboard y PDO.\n- NOAA Climate Prediction Center — SOI.\n- IMARPE/SIOFEN — Índices climáticos.")
    st.info("Nota: los umbrales de los módulos exploratorios no deben confundirse con criterios oficiales de clasificación. Para una publicación académica conviene documentar la fuente, versión del índice, período base y criterio de clasificación usado.")

st.sidebar.markdown("---")
st.sidebar.caption("FEN Analizador 2.0 · herramienta académica de análisis exploratorio")
