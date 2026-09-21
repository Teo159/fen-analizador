# app.py
# FEN Analizador - versión web
# Ejecutar con: streamlit run app.py

import io
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from pathlib import Path

MONTHS = {
    "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5,
    "Junio": 6, "Julio": 7, "Agosto": 8, "Septiembre": 9,
    "Octubre": 10, "Noviembre": 11, "Novimebre": 11, "Diciembre": 12
}

DISPLAY = {"C":"Índice C","E":"Índice E","MEI":"MEI","PDO":"PDO","SOI":"SOI"}
DEFAULT_THRESHOLDS = {"C":0.5,"E":0.5,"MEI":0.5,"PDO":1.0,"SOI":0.5}

st.set_page_config(
    page_title="FEN Analizador | C · E · MEI · PDO · SOI",
    page_icon="🌎",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.main-title {font-size: 2rem; font-weight: 700; color:#163A5F;}
.subtitle {color:#60758A;}
.card {padding: 1rem; border-radius: 12px; background: #ffffff;
       border: 1px solid #dfe7ef; margin-bottom: 1rem;}
.warning {padding: 1rem; border-radius: 10px; background:#FFF4E5; color:#795A20;}
</style>
""", unsafe_allow_html=True)


@st.cache_data
def load_data(file_bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    result = {}

    if "C y E" in xls.sheet_names:
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name="C y E")
        df.columns = [str(c).strip() for c in df.columns]
        required = {"year", "month", "E_index", "C_index"}
        if required.issubset(df.columns):
            df["Date"] = pd.to_datetime(
                dict(
                    year=pd.to_numeric(df["year"], errors="coerce"),
                    month=pd.to_numeric(df["month"], errors="coerce"),
                    day=1
                ), errors="coerce"
            )
            result["C"] = df[["Date","C_index"]].rename(columns={"C_index":"C"})
            result["E"] = df[["Date","E_index"]].rename(columns={"E_index":"E"})

    for name in ["MEI","PDO","SOI"]:
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
                rows.append({"Date":pd.Timestamp(int(year),month,1), name:value})
        result[name] = pd.DataFrame(rows)

    frames = [v.set_index("Date") for v in result.values()]
    if not frames:
        raise ValueError("No se encontraron hojas compatibles.")

    data = pd.concat(frames, axis=1).sort_index()
    return data[~data.index.duplicated(keep="first")]


def standardize(s):
    valid = s.dropna()
    if len(valid) < 2 or valid.std() == 0:
        return s * 0
    return (s - valid.mean()) / valid.std()


def interpretation(name, s, threshold):
    s = s.dropna()
    if s.empty:
        return "No existen datos válidos."

    mean, mn, mx = s.mean(), s.min(), s.max()

    if name == "SOI":
        base = ("El SOI es un indicador atmosférico. Valores negativos son "
                "compatibles con una señal cálida tipo El Niño y valores "
                "positivos con una señal fría tipo La Niña.")
    elif name == "MEI":
        base = ("El MEI combina variables oceánicas y atmosféricas del Pacífico "
                "tropical. Valores positivos representan una señal cálida y "
                "valores negativos una señal fría.")
    elif name == "PDO":
        base = ("El PDO representa un patrón de variabilidad del Pacífico Norte. "
                "Su fase debe interpretarse como PDO y no como una clasificación "
                "directa de El Niño o La Niña.")
    else:
        base = (f"El {DISPLAY[name]} muestra la evolución temporal de su señal. "
                "La interpretación específica debe seguir la definición de la fuente original.")

    if mx >= threshold and mn <= -threshold:
        behavior = (f"En el período analizado se observan valores positivos y negativos "
                     f"que superan el umbral referencial ±{threshold:.2f}.")
    elif mx >= threshold:
        behavior = (f"Se observan valores positivos que superan el umbral referencial "
                     f"{threshold:.2f}.")
    elif mn <= -threshold:
        behavior = (f"Se observan valores negativos que superan en magnitud el umbral "
                     f"{threshold:.2f}.")
    else:
        behavior = (f"Los valores observados permanecen dentro del intervalo "
                     f"±{threshold:.2f} utilizado como referencia.")

    return base + " " + behavior + (
        " Esta interpretación es descriptiva y debe contrastarse con otros índices "
        "y con la metodología oficial utilizada en la investigación."
    )


def event_table(s, name, threshold, min_duration):
    s = s.dropna()
    rows = []
    if name == "SOI":
        labels = [(True, "Señal compatible con La Niña"),
                  (False, "Señal compatible con El Niño")]
    elif name == "MEI":
        labels = [(True, "Señal cálida / El Niño"),
                  (False, "Señal fría / La Niña")]
    else:
        labels = [(True, "Valores positivos"), (False, "Valores negativos")]

    for positive, label in labels:
        mask = s >= threshold if positive else s <= -threshold
        start = None
        previous = None
        groups = []

        for date, flag in mask.items():
            if flag and start is None:
                start = date
            if not flag and start is not None:
                groups.append((start, previous))
                start = None
            previous = date
        if start is not None:
            groups.append((start, previous))

        for start, end in groups:
            if start is None or end is None:
                continue
            duration = (end.year-start.year)*12 + end.month-start.month + 1
            if duration >= min_duration:
                seg = s.loc[start:end]
                extreme = seg.max() if positive else seg.min()
                rows.append({
                    "Señal": label,
                    "Inicio": start.strftime("%Y-%m"),
                    "Fin": end.strftime("%Y-%m"),
                    "Duración (meses)": duration,
                    "Extremo": round(float(extreme), 3)
                })
    return pd.DataFrame(rows)


st.sidebar.markdown("# 🌎 FEN Analizador")
st.sidebar.caption("Análisis exploratorio de índices asociados al FEN")
st.sidebar.caption("C · E · MEI · PDO · SOI")
uploaded = st.sidebar.file_uploader(
    "Cargar datos",
    type=["xlsx", "xls"],
    help="Puedes usar tu DATOS.xlsx o un archivo con la misma estructura."
)

if uploaded is None:
    default = Path("DATOS.xlsx")
    if default.exists():
        file_bytes = default.read_bytes()
        st.sidebar.success("DATOS.xlsx encontrado.")
    else:
        file_bytes = None
else:
    file_bytes = uploaded.getvalue()
    st.sidebar.success(f"Archivo cargado: {uploaded.name}")

if file_bytes is None:
    st.markdown('<div class="main-title">Análisis de los Índices del Fenómeno El Niño</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Carga un archivo Excel para comenzar.</div>', unsafe_allow_html=True)
    st.info("El archivo esperado contiene las hojas: C y E, MEI, PDO y SOI.")
    st.stop()

try:
    data = load_data(file_bytes)
except Exception as e:
    st.error(f"No se pudo leer el archivo: {e}")
    st.stop()

indices = [x for x in ["C","E","MEI","PDO","SOI"] if x in data.columns]

st.sidebar.markdown("---")
with st.sidebar.expander("📘 Formato del Excel"):
    st.write("Hojas esperadas: **C y E**, **MEI**, **PDO** y **SOI**.")
    st.write("La hoja **C y E** debe contener: `year`, `month`, `E_index`, `C_index`. Las demás usan `year` + meses.")

section = st.sidebar.radio(
    "Módulo",
    ["Inicio","Gráficos","Comparación","Correlaciones","Rezagos",
     "Eventos FEN","Estadísticas","Interpretación"]
)

st.sidebar.markdown("---")
st.sidebar.caption(
    f"Período general: {data.index.min():%Y-%m} → {data.index.max():%Y-%m}"
)

if section == "Inicio":
    st.markdown('<div class="main-title">Sistema de análisis climático</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Explora los índices del FEN y genera interpretaciones didácticas.</div>', unsafe_allow_html=True)
    st.write("")
    c1,c2,c3 = st.columns(3)
    c1.metric("Índices", len(indices))
    c2.metric("Meses registrados", f"{len(data):,}")
    c3.metric("Período", f"{data.index.min():%Y}–{data.index.max():%Y}")
    st.markdown("### Datos disponibles")
    summary = []
    for n in indices:
        s = data[n].dropna()
        summary.append({
            "Índice": n, "Datos válidos": len(s),
            "Inicio": s.index.min().strftime("%Y-%m"),
            "Fin": s.index.max().strftime("%Y-%m"),
            "Faltantes": int(data[n].isna().sum())
        })
    st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)
    st.markdown("### ℹ️ Alcance")
    st.info("Las gráficas, correlaciones y rezagos son análisis estadísticos de las series cargadas. La clasificación formal de eventos ENSO/FEN debe seguir la metodología y fuente definida en tu investigación.")

elif section == "Gráficos":
    st.markdown('<div class="main-title">Gráficos individuales</div>', unsafe_allow_html=True)
    name = st.selectbox("Índice", indices, index=indices.index("MEI") if "MEI" in indices else 0)
    threshold = st.number_input("Umbral referencial", value=float(DEFAULT_THRESHOLDS[name]), min_value=0.0, step=0.1)
    start, end = st.slider(
        "Período",
        int(data.index.year.min()), int(data.index.year.max()),
        (int(data.index.year.min()), int(data.index.year.max()))
    )
    s = data[name].dropna()
    s = s[(s.index.year >= start) & (s.index.year <= end)]

    fig, ax = plt.subplots(figsize=(13,5))
    ax.plot(s.index, s.values, linewidth=1.2)
    ax.axhline(0, linewidth=0.8)
    ax.axhline(threshold, linestyle="--", linewidth=0.8)
    ax.axhline(-threshold, linestyle="--", linewidth=0.8)
    ax.set_title(f"Evolución temporal de {DISPLAY[name]}")
    ax.set_xlabel("Año")
    ax.set_ylabel(name)
    ax.grid(alpha=.2)
    st.pyplot(fig, use_container_width=True)

    st.markdown("### 🧠 Interpretación")
    st.info(interpretation(name, s, threshold))

elif section == "Comparación":
    st.markdown('<div class="main-title">Comparación de índices</div>', unsafe_allow_html=True)
    selected = st.multiselect("Índices", indices, default=indices)
    if selected:
        fig, ax = plt.subplots(figsize=(13,6))
        for n in selected:
            ax.plot(data.index, standardize(data[n]), linewidth=1.0, label=n)
        ax.axhline(0, linewidth=.8)
        ax.set_title("Índices estandarizados (z-score)")
        ax.set_xlabel("Año")
        ax.set_ylabel("Desviaciones estándar")
        ax.legend(ncol=3)
        ax.grid(alpha=.2)
        st.pyplot(fig, use_container_width=True)
        st.warning("La estandarización permite comparar la posición relativa de las series; no hace idénticas sus definiciones físicas.")

elif section == "Correlaciones":
    st.markdown('<div class="main-title">Correlaciones</div>', unsafe_allow_html=True)
    corr = data[indices].corr(min_periods=3)
    st.dataframe(corr.round(3), use_container_width=True)
    fig, ax = plt.subplots(figsize=(8,6))
    im = ax.imshow(corr.values, vmin=-1, vmax=1, cmap="RdBu_r")
    ax.set_xticks(range(len(indices)), indices)
    ax.set_yticks(range(len(indices)), indices)
    for i in range(len(indices)):
        for j in range(len(indices)):
            ax.text(j, i, f"{corr.iloc[i,j]:.2f}", ha="center", va="center")
    ax.set_title("Matriz de correlación de Pearson")
    fig.colorbar(im, ax=ax)
    st.pyplot(fig, use_container_width=True)
    st.info("La correlación describe asociación lineal. No demuestra causalidad.")

elif section == "Rezagos":
    st.markdown('<div class="main-title">Análisis de rezagos</div>', unsafe_allow_html=True)
    a, b = st.columns(2)
    name_a = a.selectbox("Índice A", indices, index=indices.index("MEI") if "MEI" in indices else 0)
    name_b = b.selectbox("Índice B", indices, index=indices.index("SOI") if "SOI" in indices else min(1,len(indices)-1))
    lags = range(-12,13)
    rs, ns = [], []
    for lag in lags:
        pair = pd.concat([data[name_a], data[name_b].shift(lag)], axis=1).dropna()
        rs.append(pair.iloc[:,0].corr(pair.iloc[:,1]) if len(pair)>=3 else np.nan)
        ns.append(len(pair))
    fig, ax = plt.subplots(figsize=(13,5))
    ax.plot(list(lags), rs, marker="o")
    ax.axhline(0, linewidth=.8)
    ax.axvline(0, linestyle="--", linewidth=.8)
    ax.set_ylim(-1,1)
    ax.set_xlabel("Rezago (meses)")
    ax.set_ylabel("r de Pearson")
    ax.set_title(f"Rezagos: {name_a} vs {name_b}")
    ax.grid(alpha=.2)
    st.pyplot(fig, use_container_width=True)
    valid = [(abs(r),lag,r,n) for lag,r,n in zip(lags,rs,ns) if not pd.isna(r)]
    if valid:
        _,lag,r,n=max(valid)
        st.metric("Mayor |correlación|", f"r = {r:.3f}", f"rezago {lag} meses · n={n}")

elif section == "Eventos FEN":
    st.markdown('<div class="main-title">Eventos y períodos destacados</div>', unsafe_allow_html=True)
    name = st.selectbox("Índice", indices, index=indices.index("MEI") if "MEI" in indices else 0)
    c1,c2=st.columns(2)
    threshold=c1.number_input("Umbral", value=float(DEFAULT_THRESHOLDS[name]), min_value=0.0, step=.1)
    duration=c2.number_input("Duración mínima (meses)", value=3, min_value=1, step=1)
    events=event_table(data[name], name, threshold, duration)
    st.dataframe(events, use_container_width=True, hide_index=True)
    st.warning("La detección es exploratoria. La definición oficial de eventos debe seguir la metodología seleccionada para tu investigación.")

elif section == "Estadísticas":
    st.markdown('<div class="main-title">Estadísticas descriptivas</div>', unsafe_allow_html=True)
    rows=[]
    for n in indices:
        s=data[n].dropna()
        rows.append({
            "Índice":n,"Datos":len(s),"Inicio":s.index.min().strftime("%Y-%m"),
            "Fin":s.index.max().strftime("%Y-%m"),"Media":s.mean(),
            "Desv. estándar":s.std(),"Mínimo":s.min(),"Fecha mín.":s.idxmin().strftime("%Y-%m"),
            "Máximo":s.max(),"Fecha máx.":s.idxmax().strftime("%Y-%m"),
            "P10":s.quantile(.1),"P50":s.quantile(.5),"P90":s.quantile(.9)
        })
    df=pd.DataFrame(rows)
    st.dataframe(df.round(3), use_container_width=True, hide_index=True)
    st.download_button("⬇ Descargar estadísticas CSV", df.to_csv(index=False).encode("utf-8"), "estadisticas_FEN.csv", "text/csv")

elif section == "Interpretación":
    st.markdown('<div class="main-title">🧠 Interpretación automática</div>', unsafe_allow_html=True)
    name=st.selectbox("Índice", indices, index=indices.index("MEI") if "MEI" in indices else 0)
    threshold=st.number_input("Umbral referencial", value=float(DEFAULT_THRESHOLDS[name]), min_value=0.0, step=.1)
    s=data[name].dropna()
    st.info(interpretation(name,s,threshold))
    st.markdown("### ¿Cómo leer el gráfico?")
    st.write(
        f"• Valores por encima de +{threshold:.2f}: señal positiva respecto al umbral configurado.\n\n"
        f"• Valores por debajo de -{threshold:.2f}: señal negativa respecto al umbral configurado.\n\n"
        "• El significado físico depende de cada índice.\n\n"
        "• Para declarar formalmente El Niño o La Niña deben combinarse los índices y utilizarse la metodología correspondiente."
    )
