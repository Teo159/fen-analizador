import io
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

st.set_page_config(page_title="FEN Analizador 3.0", page_icon="🌎", layout="wide", initial_sidebar_state="expanded")

MONTHS = {
    "Enero":1,"Febrero":2,"Marzo":3,"Abril":4,"Mayo":5,"Junio":6,
    "Julio":7,"Agosto":8,"Septiembre":9,"Setiembre":9,"Octubre":10,
    "Noviembre":11,"Novimebre":11,"Diciembre":12,
    "Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12
}

DISPLAY = {"C":"Índice C", "E":"Índice E", "MEI":"MEI v2", "PDO":"PDO", "SOI":"SOI"}

DESCRIPTIONS = {
    "C":"Componente C del enfoque E/C de ENSO. Se utiliza junto con E para describir distintos regímenes espaciales de la variabilidad del Pacífico tropical.",
    "E":"Componente E del enfoque E/C de ENSO. Se asocia principalmente con la variabilidad del Pacífico oriental.",
    "MEI":"Índice Multivariado de ENSO que combina información oceánica y atmosférica para caracterizar el estado del Pacífico tropical.",
    "PDO":"Índice de variabilidad de baja frecuencia del Pacífico Norte. No debe interpretarse como una clasificación directa de El Niño o La Niña.",
    "SOI":"Índice atmosférico basado en la diferencia normalizada de presión entre Tahití y Darwin. Su signo debe interpretarse considerando persistencia y metodología."
}

THRESHOLDS = {"C":0.5,"E":0.5,"MEI":0.5,"PDO":1.0,"SOI":0.5}

st.markdown("""
<style>
:root { --ink:#123B5D; --muted:#60758A; --line:#DCE6EF; --soft:#F5F9FC; --accent:#1E88C8; }
.block-container {padding-top:1.2rem; padding-bottom:2.5rem; max-width:1500px;}
.hero {padding:2rem 2.2rem; border:1px solid #D8E5EF; border-radius:22px; background:linear-gradient(135deg,#F2F9FE 0%,#FFFFFF 55%,#F7FBFD 100%); margin-bottom:1.2rem;}
.hero h1 {margin:0; color:#123B5D; font-size:2.6rem; letter-spacing:-.04em;}
.hero p {margin:.55rem 0 0; color:#5E7488; font-size:1.08rem;}
.kicker {font-size:.78rem; font-weight:800; letter-spacing:.13em; color:#1E88C8; text-transform:uppercase; margin-bottom:.35rem;}
.card {padding:1.05rem 1.15rem; border:1px solid #DCE6EF; border-radius:16px; background:white; min-height:112px;}
.card .label {color:#6A7E91; font-size:.82rem; margin-bottom:.35rem;}
.card .value {color:#123B5D; font-size:1.65rem; font-weight:800;}
.card .note {color:#718598; font-size:.8rem; margin-top:.2rem;}
.section {margin:1.35rem 0 .75rem; color:#123B5D; font-size:1.45rem; font-weight:800;}
.pill {display:inline-block; padding:.25rem .55rem; border:1px solid #D7E5EF; border-radius:999px; color:#42657D; background:#F7FBFE; font-size:.78rem; margin:.1rem .15rem .1rem 0;}
.note-box {padding:1rem 1.1rem; border-left:4px solid #1E88C8; background:#F5F9FC; border-radius:10px; color:#4E6679;}
.small {font-size:.84rem; color:#687D90;}
</style>
""", unsafe_allow_html=True)


def card(label, value, note=""):
    st.markdown(f'<div class="card"><div class="label">{label}</div><div class="value">{value}</div><div class="note">{note}</div></div>', unsafe_allow_html=True)


def standardize(s):
    x = s.dropna()
    if len(x) < 2 or x.std() == 0:
        return s * 0
    return (s - x.mean()) / x.std()


def fig_bytes(fig):
    b = io.BytesIO(); fig.savefig(b, format="png", dpi=220, bbox_inches="tight"); b.seek(0); return b.getvalue()


def parse_data(file_bytes):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    result = {}
    if "C y E" in xls.sheet_names:
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name="C y E")
        df.columns = [str(c).strip() for c in df.columns]
        req = {"year","month","E_index","C_index"}
        if req.issubset(df.columns):
            y = pd.to_numeric(df["year"], errors="coerce")
            m = pd.to_numeric(df["month"], errors="coerce")
            d = pd.to_datetime(dict(year=y, month=m, day=1), errors="coerce")
            result["C"] = pd.DataFrame({"Date":d,"C":pd.to_numeric(df["C_index"], errors="coerce")}).dropna(subset=["Date"])
            result["E"] = pd.DataFrame({"Date":d,"E":pd.to_numeric(df["E_index"], errors="coerce")}).dropna(subset=["Date"])
    for name in ["MEI","PDO","SOI"]:
        if name not in xls.sheet_names: continue
        df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=name)
        df.columns = [str(c).strip() for c in df.columns]
        rows=[]; year_col=df.columns[0]
        for _, row in df.iterrows():
            year=pd.to_numeric(row[year_col], errors="coerce")
            if pd.isna(year): continue
            for col in df.columns[1:]:
                month=MONTHS.get(str(col).strip())
                if month is None: continue
                val=pd.to_numeric(pd.Series([row[col]]), errors="coerce").iloc[0]
                rows.append({"Date":pd.Timestamp(int(year),month,1), name:val})
        result[name]=pd.DataFrame(rows)
    if not result: raise ValueError("No se encontraron hojas compatibles. Se esperan C y E, MEI, PDO y/o SOI.")
    frames=[v.set_index("Date") for v in result.values() if not v.empty]
    data=pd.concat(frames,axis=1).sort_index()
    data=data[~data.index.duplicated(keep="first")]
    return data


def summary(data, indices):
    out=[]
    for n in indices:
        s=data[n].dropna()
        out.append({"Índice":DISPLAY[n],"Código":n,"Válidos":len(s),"Inicio":s.index.min().strftime("%Y-%m") if len(s) else "—","Fin":s.index.max().strftime("%Y-%m") if len(s) else "—","Faltantes":int(data[n].isna().sum()),"Media":s.mean() if len(s) else np.nan,"DE":s.std() if len(s) else np.nan})
    return pd.DataFrame(out)


def events(s, threshold, duration):
    s=s.dropna().sort_index(); rows=[]
    for sign,label in [(1,"Positivo"),(-1,"Negativo")]:
        mask=s>=threshold if sign==1 else s<=-threshold
        start=None; prev=None
        for dt,flag in mask.items():
            if flag and start is None: start=dt
            if not flag and start is not None:
                end=prev; dur=(end.year-start.year)*12+end.month-start.month+1
                if dur>=duration:
                    seg=s.loc[start:end]; rows.append({"Señal":label,"Inicio":start.strftime('%Y-%m'),"Fin":end.strftime('%Y-%m'),"Meses":dur,"Extremo":float(seg.max() if sign==1 else seg.min())})
                start=None
            prev=dt
        if start is not None and prev is not None:
            end=prev; dur=(end.year-start.year)*12+end.month-start.month+1
            if dur>=duration:
                seg=s.loc[start:end]; rows.append({"Señal":label,"Inicio":start.strftime('%Y-%m'),"Fin":end.strftime('%Y-%m'),"Meses":dur,"Extremo":float(seg.max() if sign==1 else seg.min())})
    return pd.DataFrame(rows)

# Sidebar
st.sidebar.markdown("# 🌎 FEN Analizador")
st.sidebar.caption("Versión 3.0 · análisis climático e índices ENSO/FEN")
uploaded=st.sidebar.file_uploader("Cargar datos de Excel", type=["xlsx","xls"])
if uploaded is not None:
    raw=uploaded.getvalue(); source_name=uploaded.name
else:
    default=Path("DATOS.xlsx")
    raw=default.read_bytes() if default.exists() else None; source_name="DATOS.xlsx" if raw else ""

if raw is None:
    st.markdown('<div class="hero"><div class="kicker">Herramienta académica</div><h1>🌎 FEN Analizador 3.0</h1><p>Analiza C, E, MEI, PDO y SOI desde un archivo Excel y convierte los resultados en gráficos, estadísticas e interpretaciones comprensibles.</p></div>', unsafe_allow_html=True)
    st.info("Carga un archivo Excel para comenzar. El formato base usa las hojas C y E, MEI, PDO y SOI.")
    st.stop()

try:
    data=parse_data(raw)
except Exception as e:
    st.error(f"No se pudo leer el Excel: {e}"); st.stop()

indices=[x for x in ["C","E","MEI","PDO","SOI"] if x in data.columns]

# Header
st.markdown('<div class="hero"><div class="kicker">Sistema de análisis climático</div><h1>🌎 FEN Analizador 3.0</h1><p>Exploración estadística, comparación temporal y lectura física de los índices climáticos asociados al ENSO y al FEN.</p><div style="margin-top:.8rem">' + ''.join([f'<span class="pill">{DISPLAY[x]}</span>' for x in indices]) + '</div></div>', unsafe_allow_html=True)

# Navigation tabs
pages=st.tabs(["🏠 Inicio","📈 Series","🔄 Comparar","🔗 Correlación","⏱️ Rezagos","🌊 Eventos","📊 Estadísticas","🧠 Interpretación","📚 Metodología"])

# HOME
with pages[0]:
    st.markdown('<div class="section">Resumen del archivo cargado</div>', unsafe_allow_html=True)
    c=st.columns(4)
    c[0].markdown(f'<div class="card"><div class="label">Índices disponibles</div><div class="value">{len(indices)}</div><div class="note">C · E · MEI · PDO · SOI</div></div>',unsafe_allow_html=True)
    c[1].markdown(f'<div class="card"><div class="label">Meses registrados</div><div class="value">{len(data):,}</div><div class="note">Filas temporales consolidadas</div></div>',unsafe_allow_html=True)
    c[2].markdown(f'<div class="card"><div class="label">Inicio</div><div class="value">{data.index.min():%Y-%m}</div><div class="note">Primer registro disponible</div></div>',unsafe_allow_html=True)
    c[3].markdown(f'<div class="card"><div class="label">Fin</div><div class="value">{data.index.max():%Y-%m}</div><div class="note">Último registro disponible</div></div>',unsafe_allow_html=True)
    st.markdown('<div class="section">Calidad y cobertura de datos</div>',unsafe_allow_html=True)
    st.dataframe(summary(data,indices).round(3), width="stretch", hide_index=True)
    st.markdown('<div class="section">Evolución conjunta estandarizada</div>',unsafe_allow_html=True)
    fig,ax=plt.subplots(figsize=(14,5.2))
    for n in indices: ax.plot(data.index,standardize(data[n]),linewidth=1.0,label=n)
    ax.axhline(0,linewidth=.8); ax.set_ylabel("z-score"); ax.set_xlabel("Fecha"); ax.grid(alpha=.18); ax.legend(ncol=len(indices),loc="upper left")
    st.pyplot(fig,width="stretch"); st.download_button("⬇ Descargar gráfico PNG",fig_bytes(fig),"FEN_dashboard.png","image/png")
    st.markdown('<div class="note-box"><b>Cómo leer este gráfico:</b> la estandarización permite comparar la posición relativa de series con escalas diferentes. No significa que C, E, MEI, PDO y SOI tengan el mismo significado físico.</div>',unsafe_allow_html=True)

# SERIES
with pages[1]:
    st.markdown('<div class="section">Series temporales</div>',unsafe_allow_html=True)
    n=st.selectbox("Índice",indices,key="series_index")
    s=data[n].dropna()
    c1,c2,c3=st.columns(3)
    threshold=c1.number_input("Umbral visual",value=float(THRESHOLDS[n]),min_value=0.0,step=.1)
    window=c2.number_input("Media móvil (meses)",value=3,min_value=1,max_value=60,step=1)
    show=c3.checkbox("Mostrar media móvil",True)
    years=(int(s.index.year.min()),int(s.index.year.max()))
    if years[0]<years[1]: yr=st.slider("Periodo",years[0],years[1],years,key=f"yr_{n}")
    else: yr=years
    ss=s[(s.index.year>=yr[0])&(s.index.year<=yr[1])]
    fig,ax=plt.subplots(figsize=(14,5.4)); ax.plot(ss.index,ss.values,linewidth=1.15,label=n)
    if show: ax.plot(ss.index,ss.rolling(int(window),min_periods=max(2,int(window)//2)).mean(),linewidth=2,label=f"Media móvil {window} meses")
    ax.axhline(0,linewidth=.8); ax.axhline(threshold,linestyle="--",linewidth=.8); ax.axhline(-threshold,linestyle="--",linewidth=.8)
    ax.set_title(f"{DISPLAY[n]} · {yr[0]}–{yr[1]}"); ax.set_xlabel("Fecha"); ax.set_ylabel(n); ax.grid(alpha=.18); ax.legend()
    st.pyplot(fig,width="stretch"); st.download_button("⬇ Descargar PNG",fig_bytes(fig),f"serie_{n}.png","image/png")
    st.info(DESCRIPTIONS[n]); st.caption("El umbral mostrado es exploratorio y debe sustituirse por el criterio formal que corresponda a la metodología de tu investigación.")

# COMPARE
with pages[2]:
    st.markdown('<div class="section">Comparación de índices</div>',unsafe_allow_html=True)
    selected=st.multiselect("Índices a comparar",indices,default=indices,key="cmp")
    if selected:
        fig,ax=plt.subplots(figsize=(14,5.8))
        for n in selected: ax.plot(data.index,standardize(data[n]),linewidth=1,label=n)
        ax.axhline(0,linewidth=.8); ax.set_title("Índices estandarizados"); ax.set_ylabel("z-score"); ax.grid(alpha=.18); ax.legend(ncol=len(selected))
        st.pyplot(fig,width="stretch"); st.download_button("⬇ Descargar PNG",fig_bytes(fig),"comparacion_FEN.png","image/png")
        st.warning("La comparación estandarizada facilita observar coincidencias temporales, pero no prueba causalidad ni equivalencia física entre índices.")

# CORR
with pages[3]:
    st.markdown('<div class="section">Matriz de correlación</div>',unsafe_allow_html=True)
    selected=st.multiselect("Índices",indices,default=indices,key="corr")
    if len(selected)>=2:
        corr=data[selected].corr(min_periods=3); st.dataframe(corr.round(3),width="stretch")
        fig,ax=plt.subplots(figsize=(8,6)); im=ax.imshow(corr.values,vmin=-1,vmax=1,cmap="RdBu_r"); ax.set_xticks(range(len(selected)),selected); ax.set_yticks(range(len(selected)),selected)
        for i in range(len(selected)):
            for j in range(len(selected)): ax.text(j,i,f"{corr.iloc[i,j]:.2f}",ha="center",va="center")
        ax.set_title("Pearson r"); fig.colorbar(im,ax=ax); st.pyplot(fig,width="stretch")
        st.download_button("⬇ Descargar CSV",corr.to_csv().encode(),"correlaciones_FEN.csv","text/csv")
        st.info("Una correlación describe asociación lineal. No demuestra causalidad y debe evaluarse junto con el periodo, la cobertura y la autocorrelación.")
    else: st.info("Selecciona al menos dos índices.")

# LAGS
with pages[4]:
    st.markdown('<div class="section">Análisis de rezagos</div>',unsafe_allow_html=True)
    c1,c2,c3=st.columns(3); a=c1.selectbox("Índice A",indices,index=indices.index("MEI") if "MEI" in indices else 0); b=c2.selectbox("Índice B",indices,index=indices.index("SOI") if "SOI" in indices else min(1,len(indices)-1)); maxlag=c3.number_input("± meses",value=24,min_value=1,max_value=60,step=1)
    lags=list(range(-int(maxlag),int(maxlag)+1)); rs=[]; ns=[]
    for lag in lags:
        pair=pd.concat([data[a],data[b].shift(lag)],axis=1).dropna(); rs.append(pair.iloc[:,0].corr(pair.iloc[:,1]) if len(pair)>=3 else np.nan); ns.append(len(pair))
    fig,ax=plt.subplots(figsize=(14,5)); ax.plot(lags,rs,marker="o",markersize=3); ax.axhline(0,linewidth=.8); ax.axvline(0,linestyle="--",linewidth=.8); ax.set_ylim(-1,1); ax.set_xlabel("Rezago (meses)"); ax.set_ylabel("Pearson r"); ax.set_title(f"{a} vs {b}"); ax.grid(alpha=.18); st.pyplot(fig,width="stretch")
    valid=[(abs(r),lag,r,n) for lag,r,n in zip(lags,rs,ns) if not pd.isna(r)]
    if valid:
        _,lag,r,n=max(valid); card("Mayor |r| observado",f"{r:.3f}",f"rezago {lag} meses · n={n}")
    st.warning("Un máximo de correlación con rezago no demuestra una relación causal. Conviene contrastar significancia, autocorrelación y estabilidad temporal.")

# EVENTS
with pages[5]:
    st.markdown('<div class="section">Explorador de eventos</div>',unsafe_allow_html=True)
    st.warning("Modo exploratorio: no reemplaza una clasificación oficial de ENSO/FEN.")
    n=st.selectbox("Índice",indices,index=indices.index("MEI") if "MEI" in indices else 0,key="event_index")
    c1,c2=st.columns(2); th=c1.number_input("Umbral",value=float(THRESHOLDS[n]),min_value=0.0,step=.1,key="event_th"); dur=c2.number_input("Duración mínima (meses)",value=3,min_value=1,step=1,key="event_dur")
    ev=events(data[n],th,int(dur)); st.dataframe(ev.round(3),width="stretch",hide_index=True)
    st.download_button("⬇ Descargar eventos CSV",ev.to_csv(index=False).encode(),"eventos_exploratorios.csv","text/csv")
    st.markdown('<div class="section">Ventanas históricas de referencia</div>',unsafe_allow_html=True)
    windows={"1982–83":("1982-01","1983-12"),"1997–98":("1997-01","1998-12"),"2015–16":("2015-01","2016-12"),"2023–24":("2023-01","2024-12")}
    w=st.selectbox("Periodo",list(windows.keys())); sub=data.loc[windows[w][0]:windows[w][1],indices]
    if len(sub):
        st.dataframe(pd.DataFrame([{ "Índice":x,"n":sub[x].count(),"Media":sub[x].mean(),"Mínimo":sub[x].min(),"Máximo":sub[x].max()} for x in indices]).round(3),width="stretch",hide_index=True)
        fig,ax=plt.subplots(figsize=(14,5));
        for x in indices: ax.plot(sub.index,standardize(sub[x]),label=x,linewidth=1)
        ax.axhline(0,linewidth=.8); ax.set_title(f"Comparación estandarizada · {w}"); ax.grid(alpha=.18); ax.legend(ncol=len(indices)); st.pyplot(fig,width="stretch")
    else: st.info("No hay datos suficientes para esa ventana.")

# STATS
with pages[6]:
    st.markdown('<div class="section">Estadística descriptiva</div>',unsafe_allow_html=True)
    rows=[]
    for n in indices:
        s=data[n].dropna(); rows.append({"Índice":n,"n":len(s),"Inicio":s.index.min().strftime("%Y-%m"),"Fin":s.index.max().strftime("%Y-%m"),"Media":s.mean(),"DE":s.std(),"Mínimo":s.min(),"Fecha mín":s.idxmin().strftime("%Y-%m"),"Máximo":s.max(),"Fecha máx":s.idxmax().strftime("%Y-%m"),"P10":s.quantile(.10),"P50":s.quantile(.50),"P90":s.quantile(.90)})
    df=pd.DataFrame(rows); st.dataframe(df.round(3),width="stretch",hide_index=True); st.download_button("⬇ Descargar CSV",df.to_csv(index=False).encode(),"estadisticas_FEN.csv","text/csv")

# INTERPRETATION
with pages[7]:
    st.markdown('<div class="section">Interpretación didáctica</div>',unsafe_allow_html=True)
    n=st.selectbox("Índice",indices,index=indices.index("MEI") if "MEI" in indices else 0,key="int_index")
    s=data[n].dropna(); th=st.number_input("Umbral de apoyo",value=float(THRESHOLDS[n]),min_value=0.0,step=.1,key="int_th")
    pos=int((s>=th).sum()); neg=int((s<=-th).sum())
    st.markdown(f'<div class="note-box"><b>{DISPLAY[n]}:</b> {DESCRIPTIONS[n]}<br><br>En el archivo cargado hay <b>{pos}</b> meses ≥ +{th:.2f} y <b>{neg}</b> meses ≤ −{th:.2f}. Esto es una descripción estadística; por sí sola no constituye una clasificación oficial de El Niño, La Niña o FEN.</div>',unsafe_allow_html=True)
    st.markdown('<div class="section">Lectura recomendada</div>',unsafe_allow_html=True)
    st.write("1. Verifica la fuente, versión y periodo del índice.\n2. Observa la serie y su persistencia.\n3. Compara con otros índices sin asumir equivalencia física.\n4. Evalúa rezagos y correlaciones con cautela.\n5. Contrasta cualquier clasificación de ENSO/FEN con la metodología oficial usada en tu investigación.")

# METHODOLOGY
with pages[8]:
    st.markdown('<div class="section">Metodología, definiciones y alcance</div>',unsafe_allow_html=True)
    st.markdown("**C y E:** componentes utilizados para describir regímenes espaciales de ENSO en el enfoque E/C. La definición exacta debe corresponder a la fuente de los datos cargados.")
    st.markdown("**MEI v2:** índice multivariado que resume información oceánica y atmosférica del Pacífico tropical.")
    st.markdown("**SOI:** indicador de la Oscilación del Sur basado en presión atmosférica entre Tahití y Darwin; la interpretación del signo debe considerar persistencia y la metodología empleada.")
    st.markdown("**PDO:** patrón de variabilidad del Pacífico Norte; se presenta separadamente de una clasificación directa de ENSO.")
    st.markdown("**FEN en Perú:** para conclusiones oficiales o académicas debe contrastarse con los índices y criterios definidos por la metodología de la investigación y las instituciones competentes.")
    st.markdown('<div class="note-box"><b>Alcance:</b> esta aplicación es una herramienta de análisis exploratorio. Los umbrales de los módulos gráficos/eventos son configurables y no deben presentarse como criterios oficiales sin documentar la fuente correspondiente.</div>',unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.caption(f"Archivo: {source_name}")
st.sidebar.caption("FEN Analizador 3.0 · versión web")
