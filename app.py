"""
Observatorio Económico y Social de Nariño
-----------------------------------------
Prototipo en Streamlit, centrado en Nariño y comparativo con los demás
departamentos de Colombia.

Regla de oro: TODOS los datos se descargan en vivo de fuentes oficiales
(DANE, DNP, datos.gov.co / SODA, MinCiencias). No se usan datos aleatorios
ni sintéticos. Si una fuente falla, la app lo informa y no inventa valores.
"""

import io
import re
import unicodedata
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================
st.set_page_config(
    page_title="Observatorio Económico y Social de Nariño",
    page_icon="📊",
    layout="wide",
)

UA = {"User-Agent": "Mozilla/5.0 (Observatorio Narino - proyecto academico)"}
SODA = "https://www.datos.gov.co"
TTL = 60 * 60 * 24  # los datos se guardan en caché 24 horas
NARINO = "Nariño"
VERDE_NARINO = "#15803D"   # verde de la bandera de Nariño
ORO_NARINO = "#CA8A04"     # amarillo de la bandera de Nariño
GRIS = "#A8B3BF"
ANIO_ACTUAL = datetime.now().year

st.markdown(
    f"""
<style>
.hero {{
  background: {VERDE_NARINO};
  border-bottom: 6px solid {ORO_NARINO};
  padding: 1.3rem 1.6rem 1.1rem;
  border-radius: 10px;
  margin-bottom: 1.2rem;
}}
.hero h1 {{ color: #ffffff; margin: 0; font-size: 1.85rem; line-height: 1.2; }}
.hero p  {{ color: #ECFDF5; margin: .4rem 0 0; max-width: 75ch; }}
div[data-testid="stMetric"] {{
  border-left: 5px solid {ORO_NARINO};
  padding: .5rem .9rem;
  background: rgba(21,128,61,.06);
  border-radius: 6px;
}}
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# NORMALIZACIÓN DE NOMBRES Y AÑOS
# ============================================================
def quitar_tildes(texto):
    t = str(texto).strip().lower()
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


DEPTOS = {
    "amazonas": "Amazonas", "antioquia": "Antioquia", "arauca": "Arauca",
    "atlantico": "Atlántico", "bogota": "Bogotá D.C.", "bogota d c": "Bogotá D.C.",
    "bogota dc": "Bogotá D.C.", "bolivar": "Bolívar", "boyaca": "Boyacá",
    "caldas": "Caldas", "caqueta": "Caquetá", "casanare": "Casanare", "cauca": "Cauca",
    "cesar": "Cesar", "choco": "Chocó", "cordoba": "Córdoba", "cundinamarca": "Cundinamarca",
    "guainia": "Guainía", "guaviare": "Guaviare", "huila": "Huila",
    "la guajira": "La Guajira", "guajira": "La Guajira", "magdalena": "Magdalena",
    "meta": "Meta", "narino": "Nariño", "norte de santander": "Norte de Santander",
    "putumayo": "Putumayo", "quindio": "Quindío", "risaralda": "Risaralda",
    "san andres": "San Andrés y Providencia",
    "archipielago de san andres": "San Andrés y Providencia",
    "santander": "Santander", "sucre": "Sucre", "tolima": "Tolima",
    "valle": "Valle del Cauca", "valle del cauca": "Valle del Cauca",
    "vaupes": "Vaupés", "vichada": "Vichada",
}
CLAVES_ORDENADAS = sorted(DEPTOS, key=len, reverse=True)
LISTA_DEPTOS = sorted(set(DEPTOS.values()))


def normalizar_departamento(nombre):
    """Convierte cualquier forma de escribir un departamento a su nombre oficial."""
    if nombre is None or (isinstance(nombre, float) and pd.isna(nombre)):
        return None
    s = re.sub(r"^\s*\d{1,5}[\s\-_.]*", "", str(nombre))
    clave = quitar_tildes(s)
    if not clave:
        return None
    if clave in DEPTOS:
        return DEPTOS[clave]
    for k in CLAVES_ORDENADAS:
        if clave.startswith(k + " "):
            return DEPTOS[k]
    if "bogota" in clave:
        return "Bogotá D.C."
    if "san andres" in clave:
        return "San Andrés y Providencia"
    return None


def a_anio(x):
    """Extrae un año (1950-2039) de un número o texto como '2024pr'."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if isinstance(x, (int, float)):
        if float(x).is_integer() and 1950 <= x <= 2039:
            return int(x)
        return None
    m = re.search(r"(19[5-9]\d|20[0-3]\d)", str(x))
    return int(m.group(1)) if m else None


def fila_de_anios(valores, minimo=4):
    """Si una fila es un encabezado de años crecientes, devuelve {columna: año}."""
    mapa = {}
    for j, v in enumerate(valores):
        a = a_anio(v)
        if a:
            mapa[j] = a
    anios = list(mapa.values())
    if len(anios) >= minimo and anios == sorted(anios) and len(set(anios)) == len(anios):
        return mapa
    return None


def fmt(v, dec=2):
    """Número con formato colombiano: 1.234,56"""
    if v is None or pd.isna(v):
        return "sin dato"
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# Servidores oficiales con certificado SSL incompleto (les falta el certificado intermedio).
# Solo para ellos se reintenta la descarga sin verificar el certificado.
SERVIDORES_SSL_INCOMPLETO = ("colaboracion.dnp.gov.co",)


def bajar(url, timeout=180):
    try:
        r = requests.get(url, headers=UA, timeout=timeout)
    except requests.exceptions.SSLError:
        if not any(s in url for s in SERVIDORES_SSL_INCOMPLETO):
            raise
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        r = requests.get(url, headers=UA, timeout=timeout, verify=False)
    r.raise_for_status()
    return r.content


# ============================================================
# LECTORES DE ARCHIVOS EXCEL DEL DANE
# ============================================================
def titulo_hoja(df):
    for i in range(min(12, len(df))):
        for v in df.iloc[i].tolist():
            if isinstance(v, str) and len(v.strip()) > 12:
                return re.sub(r"\s+", " ", v.strip())
    return None


def parse_ancho(df):
    """Tabla con departamentos en filas y años en columnas (formato típico del DANE).
    Toma solo el primer bloque de la hoja para no mezclar tablas distintas."""
    encabezado = None
    for i in range(min(len(df), 60)):
        mapa = fila_de_anios(df.iloc[i].tolist())
        if mapa:
            encabezado = (i, mapa)
            break
    if not encabezado:
        return pd.DataFrame()
    i0, cols = encabezado
    candidatos = {}   # departamento -> lista de (etiqueta, fila)
    orden = []
    for i in range(i0 + 1, len(df)):
        fila = df.iloc[i].tolist()
        depto, etiqueta = None, ""
        for j, v in enumerate(fila):
            if j in cols or not isinstance(v, str) or not v.strip():
                continue
            d = normalizar_departamento(v) if depto is None else None
            if d:
                depto = d
            else:
                etiqueta += " " + quitar_tildes(v)
        if not depto:
            continue
        if depto in candidatos and not etiqueta.strip():
            break  # empieza otro bloque de la misma hoja
        if depto not in candidatos:
            candidatos[depto] = []
            orden.append(depto)
        candidatos[depto].append((etiqueta.strip(), fila))

    preferidas = ("producto interno bruto", "pib", "total")
    filas = []
    for depto in orden:
        opciones = candidatos[depto]
        elegida = next((f for e, f in opciones if any(p in e for p in preferidas)), opciones[0][1])
        for j, anio in cols.items():
            v = pd.to_numeric(elegida[j], errors="coerce")
            if pd.notna(v):
                filas.append((depto, anio, float(v)))
    return pd.DataFrame(filas, columns=["departamento", "anio", "valor"])


def parse_largo(df):
    """Tabla con columnas Departamento | Año | Valor (formato largo)."""
    for i in range(min(len(df), 40)):
        enc = [quitar_tildes(v) if isinstance(v, str) else "" for v in df.iloc[i].tolist()]
        c_dep = next((j for j, n in enumerate(enc) if "depart" in n and "cod" not in n), None)
        c_anio = next((j for j, n in enumerate(enc) if n in ("ano", "anio", "periodo", "vigencia") or n.startswith("ano ")), None)
        if c_dep is None or c_anio is None:
            continue
        cuerpo = df.iloc[i + 1:]
        numericas = [j for j in range(df.shape[1]) if j not in (c_dep, c_anio)
                     and pd.to_numeric(cuerpo.iloc[:, j], errors="coerce").notna().mean() > 0.6]
        if not numericas:
            return pd.DataFrame()
        d = pd.DataFrame({
            "departamento": cuerpo.iloc[:, c_dep].apply(normalizar_departamento),
            "anio": cuerpo.iloc[:, c_anio].apply(a_anio),
            "valor": pd.to_numeric(cuerpo.iloc[:, numericas[-1]], errors="coerce"),
        }).dropna()
        return d.groupby(["departamento", "anio"], as_index=False)["valor"].first()
    return pd.DataFrame()


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_excel_ancho(url, prefijo, solo=None):
    xl = pd.ExcelFile(io.BytesIO(bajar(url)))
    excluir = ("indice", "contenido", "ficha", "nota", "error", "glosario")
    partes, nombres = [], set()
    for hoja in xl.sheet_names:
        hn = quitar_tildes(hoja)
        if any(e in hn for e in excluir):
            continue
        if solo and not any(s in hn for s in solo):
            continue
        raw = pd.read_excel(xl, sheet_name=hoja, header=None)
        d = parse_ancho(raw)
        if d.empty:  # quizá los años están en filas y los departamentos en columnas
            d = parse_ancho(raw.T.reset_index(drop=True))
        if d.empty:  # quizá es una tabla larga: Departamento | Año | Valor
            d = parse_largo(raw)
        if d.empty or d["departamento"].nunique() < 10:
            continue
        nombre = f"{prefijo}: {titulo_hoja(raw) or hoja}"[:120]
        if nombre in nombres:
            nombre = f"{nombre} [{hoja}]"
        nombres.add(nombre)
        d["indicador"] = nombre
        partes.append(d)
    if not partes:
        raise ValueError(f"No se reconoció ninguna tabla por departamento. Hojas: {xl.sheet_names}")
    return pd.concat(partes, ignore_index=True)


TASAS_GEIH = [
    ("tasa de desocupacion", "Tasa de desocupación (%)"),
    ("tasa de subocupacion", "Tasa de subocupación (%)"),
    ("tasa de ocupacion", "Tasa de ocupación (%)"),
    ("tasa global de participacion", "Tasa global de participación (%)"),
    ("tasa de informalidad", "Tasa de informalidad (%)"),
    ("proporcion de informalidad", "Tasa de informalidad (%)"),
]


def parse_geih(df, sufijo):
    filas, depto, anios = [], None, None
    for i in range(len(df)):
        fila = df.iloc[i].tolist()
        mapa = fila_de_anios(fila[1:], minimo=5)
        if mapa:
            anios = {j + 1: a for j, a in mapa.items()}
            continue
        etiqueta = fila[0]
        if not isinstance(etiqueta, str) or not etiqueta.strip():
            continue
        en = quitar_tildes(etiqueta)
        if en.startswith("total"):
            depto = None
            continue
        d = normalizar_departamento(etiqueta)
        if d:
            depto = d
            continue
        for clave, nombre in TASAS_GEIH:
            if en.startswith(clave) and depto and anios:
                for j, a in anios.items():
                    v = pd.to_numeric(fila[j], errors="coerce")
                    if pd.notna(v) and 0 <= v <= 100:
                        filas.append((depto, a, float(v), nombre + sufijo))
                break
    return pd.DataFrame(filas, columns=["departamento", "anio", "valor", "indicador"])


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_geih(url):
    xl = pd.ExcelFile(io.BytesIO(bajar(url)))
    hojas = {
        "departamentos anual": "",
        "departamentos anual hombres": " – hombres",
        "departamentos anual mujeres": " – mujeres",
        "departamento anual cabeceras": " – cabeceras (urbano)",
        "departamento anual centrosp": " – centros poblados y rural disperso",
    }
    partes = []
    for h in xl.sheet_names:
        hn = quitar_tildes(h)
        if hn in hojas:
            partes.append(parse_geih(pd.read_excel(xl, sheet_name=h, header=None), hojas[hn]))
    d = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    if d.empty:
        raise ValueError(f"No se reconocieron las tasas laborales. Hojas: {xl.sheet_names}")
    return d.drop_duplicates(["departamento", "anio", "indicador"])


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_poblacion(url):
    xl = pd.ExcelFile(io.BytesIO(bajar(url, 240)))
    hoja = next((h for h in xl.sheet_names if "area" in quitar_tildes(h)), xl.sheet_names[0])
    df = pd.read_excel(xl, sheet_name=hoja, header=None)
    filas = []
    for i in range(len(df)):
        fila = df.iloc[i].tolist()
        if len(fila) < 5 or "total" not in quitar_tildes(fila[3]):
            continue
        d, a = normalizar_departamento(fila[1]), a_anio(fila[2])
        v = pd.to_numeric(fila[4], errors="coerce")
        if d and a and pd.notna(v):
            filas.append((d, a, float(v)))
    p = pd.DataFrame(filas, columns=["departamento", "anio", "poblacion"])
    if p.empty:
        raise ValueError("No se reconoció la tabla de población.")
    return p.drop_duplicates(["departamento", "anio"])


# ============================================================
# LECTORES DE LA API SODA (datos.gov.co)
# ============================================================
def elegir_columna(cols, incluye, excluye=()):
    for c in cols:
        n = c.lower()
        if any(i in n for i in incluye) and not any(e in n for e in excluye):
            return c
    return None


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_soda_conteo(dsid, nombre_respaldo):
    """Cuenta casos por departamento y año. La suma se hace en el servidor de
    datos.gov.co, así no hay límite de filas y no se pierde información."""
    r = requests.get(f"{SODA}/api/views/{dsid}.json", headers=UA, timeout=60)
    r.raise_for_status()
    meta = r.json()
    nombre = meta.get("name") or nombre_respaldo
    columnas = meta.get("columns", [])
    cols = [c["fieldName"] for c in columnas]
    tipos = {c["fieldName"]: c.get("dataTypeName", "") for c in columnas}

    dep = "departamento" if "departamento" in cols else elegir_columna(cols, ["depart", "dpto", "depto"], ["cod"])
    if not dep:
        raise ValueError(f"No hay columna de departamento. Columnas: {cols}")
    fechas = [c for c in cols if tipos.get(c) in ("calendar_date", "floating_timestamp")]
    fecha = elegir_columna(fechas, ["fecha"]) or (fechas[0] if fechas else None)
    col_anio = elegir_columna(cols, ["anio", "a_o", "ano", "vigencia", "convocatoria", "periodo"], ["fecha"])
    expr_anio = f"date_extract_y({fecha})" if fecha else col_anio

    medidas = (["sum(cantidad)"] if "cantidad" in cols else []) + ["count(*)"]
    datos, ultimo_error = None, None
    for medida in medidas:
        select = f"{dep} as departamento, {medida} as valor"
        grupo = dep
        if expr_anio:
            select += f", {expr_anio} as anio"
            grupo += f", {expr_anio}"
        try:
            resp = requests.get(
                f"{SODA}/resource/{dsid}.json",
                params={"$select": select, "$group": grupo, "$limit": 50000},
                headers=UA, timeout=180,
            )
            resp.raise_for_status()
            datos = pd.DataFrame(resp.json())
            if not datos.empty:
                break
        except Exception as e:
            ultimo_error = e
    if datos is None or datos.empty:
        raise ValueError(f"La consulta a datos.gov.co falló: {ultimo_error}")

    datos["departamento"] = datos["departamento"].apply(normalizar_departamento)
    if expr_anio:
        datos["anio"] = datos["anio"].apply(a_anio)
    else:  # sin columna de tiempo: se usa la fecha oficial de corte de la base
        corte = pd.to_datetime(meta.get("rowsUpdatedAt"), unit="s")
        datos["anio"] = corte.year
        nombre += f" (corte {corte:%Y-%m})"
    datos["valor"] = pd.to_numeric(datos["valor"], errors="coerce")
    datos = datos.dropna(subset=["departamento", "anio", "valor"])
    datos = datos.groupby(["departamento", "anio"], as_index=False)["valor"].sum()
    datos["anio"] = datos["anio"].astype(int)
    datos["indicador"] = f"{nombre} (número de casos)"
    if fecha:
        datos["nota"] = datos["anio"].apply(lambda a: "Año en curso (incompleto)" if a >= ANIO_ACTUAL else "")
    return datos


# ============================================================
# LECTOR DE FINANZAS PÚBLICAS (OEC – DNP)
# ============================================================
CONCEPTOS_OEC = [
    ("ingresos totales", "Ingresos totales"),
    ("gastos totales", "Gastos totales"),
    ("ingresos corrientes", "Ingresos corrientes"),
    ("ingresos tributarios", "Ingresos tributarios"),
    ("deficit o superavit total", "Déficit o superávit total"),
    ("regalias", "Regalías"),
]


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_oec(url):
    xl = pd.ExcelFile(io.BytesIO(bajar(url, 300)))
    hoja, fila_enc = None, None
    for h in xl.sheet_names:
        muestra = pd.read_excel(xl, sheet_name=h, header=None, nrows=40)
        for i in range(len(muestra)):
            celdas = [quitar_tildes(v) for v in muestra.iloc[i].tolist() if isinstance(v, str)]
            if len(celdas) >= 3 and any("depart" in c for c in celdas):
                hoja, fila_enc = h, i
                break
        if hoja:
            break
    if hoja is None:
        raise ValueError(f"No se reconoció la estructura del archivo OEC. Hojas: {xl.sheet_names}")

    df = pd.read_excel(xl, sheet_name=hoja, header=fila_enc)
    df.columns = [str(c) for c in df.columns]
    norm = {c: quitar_tildes(c) for c in df.columns}
    dep = next((c for c, n in norm.items() if "depart" in n and "cod" not in n), None)
    anio = next((c for c, n in norm.items() if n in ("ano", "anio", "vigencia", "periodo")
                 or n.startswith("ano ") or "vigencia" in n), None)
    valor = None

    # Si los años vienen como columnas (2000, 2001, ...), se pasan a filas
    cols_anio = [c for c in df.columns if re.fullmatch(r"\s*(19|20)\d{2}(\.0)?\s*", c)]
    if anio is None and cols_anio:
        fijos = [c for c in df.columns if c not in cols_anio]
        df = df.melt(id_vars=fijos, value_vars=cols_anio, var_name="__anio", value_name="__valor")
        anio, valor = "__anio", "__valor"
        norm = {c: quitar_tildes(c) for c in df.columns}

    if not dep or not anio:
        raise ValueError(f"Falta columna de departamento o año. Columnas: {list(df.columns)[:40]}")

    partes = []
    # Caso A: cada concepto es una columna
    if valor is None:
        for clave, etiqueta in CONCEPTOS_OEC:
            col = next((c for c, n in norm.items() if n.startswith(clave)), None)
            if col:
                d = df[[dep, anio, col]].copy()
                d.columns = ["departamento", "anio", "valor"]
                d["concepto"] = etiqueta
                partes.append(d)
    # Caso B: hay una columna con el nombre del concepto y otra con el valor
    if not partes:
        concepto = next((c for c, n in norm.items()
                         if any(k in n for k in ("concepto", "cuenta", "descripcion", "detalle", "nombre"))
                         and not any(k in n for k in ("depart", "municip", "entidad"))), None)
        if valor is None:
            valor = next((c for c, n in norm.items() if "valor" in n or n == "total"), None)
        if concepto and valor:
            texto = df[concepto].astype(str).map(quitar_tildes)
            for clave, etiqueta in CONCEPTOS_OEC:
                d = df.loc[texto.str.startswith(clave), [dep, anio, valor]].copy()
                d.columns = ["departamento", "anio", "valor"]
                d["concepto"] = etiqueta
                partes.append(d)
    partes = [p for p in partes if not p.empty]
    if not partes:
        raise ValueError(f"No se encontraron conceptos fiscales. Columnas: {list(df.columns)[:40]}")

    d = pd.concat(partes, ignore_index=True)
    d["departamento"] = d["departamento"].apply(normalizar_departamento)
    d["anio"] = d["anio"].apply(a_anio)
    d["valor"] = pd.to_numeric(d["valor"], errors="coerce")
    d = d.dropna(subset=["departamento", "anio", "valor"])
    d = d.groupby(["departamento", "anio", "concepto"], as_index=False)["valor"].sum()
    d["indicador"] = "Finanzas territoriales (OEC) – " + d["concepto"] + " – suma de entidades del departamento"
    return d.drop(columns="concepto")


# ============================================================
# CATÁLOGO DE FUENTES OFICIALES
# ============================================================
URL_POBLACION = ("https://www.dane.gov.co/files/censo2018/proyecciones-de-poblacion/"
                 "Departamental/PPED-AreaDep-2018-2050_VP.xlsx")

CATEGORIAS = {
    "Crecimiento / PIB": [
        dict(nombre="PIB total por departamentos 2005–2025pr", institucion="DANE",
             url="https://www.dane.gov.co/files/operaciones/PIB/anex-PIBDep-TotalDep-2025pr.xlsx",
             fn=lambda u: cargar_excel_ancho(u, "PIB"), derivado="per_capita"),
    ],
    "Mercado laboral": [
        dict(nombre="GEIH – Mercado laboral por departamentos", institucion="DANE",
             url="https://www.dane.gov.co/files/operaciones/GEIH/anex-GEIHDepartamentos-2025.xls",
             fn=cargar_geih, derivado=None),
    ],
    "Seguridad ciudadana": [
        dict(nombre="Delitos – Policía Nacional / MinDefensa (4rxi-8m8d)", institucion="datos.gov.co",
             url=f"{SODA}/resource/4rxi-8m8d.json",
             fn=lambda u: cargar_soda_conteo("4rxi-8m8d", "Delitos"), derivado="tasa"),
        dict(nombre="Homicidios – MinDefensa (m8fd-ahd9)", institucion="datos.gov.co",
             url=f"{SODA}/resource/m8fd-ahd9.json",
             fn=lambda u: cargar_soda_conteo("m8fd-ahd9", "Homicidios"), derivado="tasa"),
    ],
    "Finanzas públicas": [
        dict(nombre="Operaciones Efectivas de Caja (OEC) 2000–2024", institucion="DNP",
             url=("https://colaboracion.dnp.gov.co/CDT/Desarrollo%20Territorial/CIFFIT_ArchivosConsolidados/"
                  "HistoricoOEC_Con_SGR_Para_Municipios_Periodo_2000_2024.xlsx"),
             fn=cargar_oec, derivado="per_capita_fiscal"),
    ],
    "Ciencia, tecnología e innovación (CTI)": [
        dict(nombre="Grupos de investigación reconocidos (hrhc-c4wu)", institucion="MinCiencias / datos.gov.co",
             url=f"{SODA}/resource/hrhc-c4wu.json",
             fn=lambda u: cargar_soda_conteo("hrhc-c4wu", "Grupos de investigación reconocidos"),
             derivado="tasa"),
    ],
    "Pobreza y equidad": [
        dict(nombre="Pobreza monetaria y Gini departamental 2021–2025", institucion="DANE",
             url="https://www.dane.gov.co/files/operaciones/PM/anex-PMDepartamental-2025.xlsx",
             fn=lambda u: cargar_excel_ancho(u, "Pobreza monetaria", solo=("act met", "gini")), derivado=None),
        dict(nombre="Pobreza multidimensional (IPM) departamental", institucion="DANE",
             url="https://www.dane.gov.co/files/operaciones/PM/anex-PMultidimensional-Departamental-2025.xlsx",
             fn=lambda u: cargar_excel_ancho(u, "IPM", solo=("depart",)), derivado=None),
    ],
}


def agregar_derivados(base, fuente, pob):
    """Indicadores calculados con la población oficial del DANE."""
    if pob is None or pob.empty or not fuente.get("derivado"):
        return pd.DataFrame()
    m = base.merge(pob, on=["departamento", "anio"], how="inner")
    if m.empty:
        return pd.DataFrame()
    tipo = fuente["derivado"]
    if tipo == "tasa":
        m["valor"] = m["valor"] / m["poblacion"] * 100000
        m["indicador"] = m["indicador"].str.replace(" (número de casos)", "", regex=False) + " – tasa por 100.000 hab."
    elif tipo == "per_capita":
        n = m["indicador"].map(quitar_tildes)
        m = m[n.str.contains("miles de millones") & ~n.str.contains("variacion|particip|indice")]
        m["valor"] = m["valor"] * 1000 / m["poblacion"]  # miles de millones -> millones por persona
        m["indicador"] = "PIB per cápita (millones de pesos) – " + m["indicador"].str.replace("PIB: ", "", regex=False)
    elif tipo == "per_capita_fiscal":
        m["valor"] = m["valor"] / m["poblacion"]
        m["indicador"] = m["indicador"] + " – por habitante"
    else:
        return pd.DataFrame()
    return m.drop(columns="poblacion")


def cargar_categoria(nombre_cat):
    partes, estados = [], []
    try:
        pob = cargar_poblacion(URL_POBLACION)
    except Exception:
        pob = None
    for f in CATEGORIAS[nombre_cat]:
        try:
            d = f["fn"](f["url"]).copy()
            d["fuente"] = f"{f['institucion']} – {f['nombre']}"
            d["url_fuente"] = f["url"]
            extra = agregar_derivados(d, f, pob)
            partes += [d, extra]
            estados.append(dict(Categoría=nombre_cat, Fuente=f["nombre"], Institución=f["institucion"],
                                Estado="✅ Cargada", Registros=len(d), Indicadores=d["indicador"].nunique(),
                                Años=f"{int(d['anio'].min())}–{int(d['anio'].max())}", Detalle="", Enlace=f["url"]))
        except Exception as e:
            estados.append(dict(Categoría=nombre_cat, Fuente=f["nombre"], Institución=f["institucion"],
                                Estado="❌ No disponible", Registros=0, Indicadores=0, Años="",
                                Detalle=str(e)[:400], Enlace=f["url"]))
    partes = [p for p in partes if p is not None and not p.empty]
    datos = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    if not datos.empty:
        if "nota" not in datos.columns:
            datos["nota"] = ""
        datos["nota"] = datos["nota"].fillna("")
        datos = datos[datos["departamento"].isin(LISTA_DEPTOS)]
        datos["anio"] = datos["anio"].astype(int)
        datos = datos.drop_duplicates(["indicador", "departamento", "anio"], keep="first")
        datos["categoria"] = nombre_cat
    return datos, estados


# ============================================================
# MAPA
# ============================================================
GEOJSON_URL = ("https://gist.githubusercontent.com/john-guerra/43c7656821069d00dcbc/raw/"
               "be6a6e239cd5b5b803c6e7c2ec405b793a9064dd/Colombia.geo.json")

CENTROIDES = {
    "Amazonas": (-71.5, -1.5), "Antioquia": (-75.5, 6.9), "Arauca": (-70.8, 6.6),
    "Atlántico": (-74.9, 10.7), "Bogotá D.C.": (-74.1, 4.6), "Bolívar": (-74.6, 8.7),
    "Boyacá": (-73.0, 5.8), "Caldas": (-75.3, 5.3), "Caquetá": (-74.2, 0.9),
    "Casanare": (-71.6, 5.4), "Cauca": (-76.8, 2.4), "Cesar": (-73.5, 9.4),
    "Chocó": (-76.9, 5.7), "Córdoba": (-75.8, 8.4), "Cundinamarca": (-74.1, 5.0),
    "Guainía": (-68.6, 2.6), "Guaviare": (-72.4, 2.0), "Huila": (-75.6, 2.5),
    "La Guajira": (-72.6, 11.4), "Magdalena": (-74.2, 10.2), "Meta": (-72.9, 3.4),
    "Nariño": (-77.6, 1.4), "Norte de Santander": (-72.8, 8.0), "Putumayo": (-75.9, 0.4),
    "Quindío": (-75.7, 4.5), "Risaralda": (-75.9, 5.1), "San Andrés y Providencia": (-81.7, 12.5),
    "Santander": (-73.4, 6.9), "Sucre": (-75.1, 9.0), "Tolima": (-75.2, 4.0),
    "Valle del Cauca": (-76.4, 3.8), "Vaupés": (-70.7, 0.6), "Vichada": (-69.4, 4.8),
}


@st.cache_data(ttl=TTL, show_spinner=False)
def cargar_geojson():
    r = requests.get(GEOJSON_URL, headers=UA, timeout=60)
    r.raise_for_status()
    gj = r.json()
    for f in gj.get("features", []):
        p = f.get("properties", {})
        nombre = p.get("NOMBRE_DPT") or p.get("DPTO_CNMBR") or p.get("name") or p.get("NAME_1")
        f["id"] = normalizar_departamento(nombre)
    return gj


def figura_mapa(dm, titulo):
    try:
        gj = cargar_geojson()
        ids = {f.get("id") for f in gj.get("features", [])}
        if len(ids & set(dm["departamento"])) < 15:
            raise ValueError("El mapa base no coincide con los departamentos.")
        fig = px.choropleth(dm, geojson=gj, locations="departamento", color="valor",
                            color_continuous_scale="YlGn", hover_name="departamento",
                            hover_data={"valor": ":,.2f", "departamento": False}, title=titulo)
        fig.update_geos(fitbounds="locations", visible=False)
    except Exception:
        dm = dm.copy()
        dm["lon"] = dm["departamento"].map(lambda x: CENTROIDES.get(x, (None, None))[0])
        dm["lat"] = dm["departamento"].map(lambda x: CENTROIDES.get(x, (None, None))[1])
        dm = dm.dropna(subset=["lon", "lat"])
        fig = px.scatter_geo(dm, lat="lat", lon="lon", color="valor", size=dm["valor"].abs() + 1e-9,
                             hover_name="departamento", color_continuous_scale="YlGn", title=titulo)
        fig.update_geos(lataxis_range=[-4.5, 13.5], lonaxis_range=[-82, -66], showcountries=True)
    narino = dm[dm["departamento"] == NARINO]
    if not narino.empty and NARINO in CENTROIDES:
        lon, lat = CENTROIDES[NARINO]
        fig.add_trace(go.Scattergeo(lon=[lon], lat=[lat], text=["Nariño"], mode="markers+text",
                                    marker=dict(size=12, color=ORO_NARINO, line=dict(width=2, color="#fff")),
                                    textposition="bottom center", showlegend=False, hoverinfo="skip"))
    fig.update_layout(height=620, margin=dict(l=0, r=0, t=50, b=0))
    return fig


# ============================================================
# INTERFAZ
# ============================================================
st.markdown(
    """
<div class="hero">
  <h1>Observatorio Económico y Social de Nariño</h1>
  <p>Indicadores oficiales de Nariño frente a los demás departamentos de Colombia:
  crecimiento, mercado laboral, seguridad, finanzas públicas, ciencia y pobreza.
  Los datos se descargan en vivo del DANE, el DNP y datos.gov.co.</p>
</div>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Filtros")
    categoria = st.selectbox("Categoría", list(CATEGORIAS))

with st.spinner("Descargando datos oficiales… la primera carga puede tardar un minuto."):
    datos, estados = cargar_categoria(categoria)

for e in estados:
    if e["Estado"].startswith("❌"):
        st.warning(f"No se pudo cargar **{e['Fuente']}** ({e['Institución']}). "
                   "El observatorio no reemplaza datos faltantes con valores inventados. "
                   "Revisa la pestaña *Fuentes y diagnóstico*.")

if datos.empty:
    st.error("Ninguna fuente de esta categoría respondió. Intenta más tarde o elige otra categoría.")
    st.dataframe(pd.DataFrame(estados), use_container_width=True)
    st.stop()

with st.sidebar:
    indicadores = sorted(datos["indicador"].unique())
    indicador = st.selectbox("Indicador", indicadores)
    d_ind = datos[datos["indicador"] == indicador]

    incluir_incompleto = True
    if (d_ind["nota"] != "").any():
        incluir_incompleto = st.checkbox("Incluir año en curso (incompleto)", value=False)
        if not incluir_incompleto:
            d_ind = d_ind[d_ind["nota"] == ""]

    amin, amax = int(d_ind["anio"].min()), int(d_ind["anio"].max())
    if amin < amax:
        a0, a1 = st.slider("Rango de años", amin, amax, (amin, amax))
    else:
        a0 = a1 = amin
        st.info(f"Este indicador solo tiene datos de {amin}.")

    disponibles = sorted(d_ind["departamento"].unique())
    sugeridos = [d for d in [NARINO, "Cauca", "Putumayo", "Valle del Cauca", "Antioquia", "Bogotá D.C."]
                 if d in disponibles]
    seleccion = st.multiselect("Departamentos a comparar", disponibles, default=sugeridos)
    fijar_narino = st.checkbox("Mostrar siempre Nariño como referencia", value=True)
    if fijar_narino and NARINO in disponibles and NARINO not in seleccion:
        seleccion = [NARINO] + seleccion

    st.caption(f"Fuente: {d_ind['fuente'].iloc[0]}")

dr = d_ind[(d_ind["anio"] >= a0) & (d_ind["anio"] <= a1)].copy()
if dr.empty:
    st.info("No hay datos en ese rango de años. Amplía el rango en la barra lateral.")
    st.stop()

# ---------------- KPIs ----------------
ult = int(dr["anio"].max())
corte = dr[dr["anio"] == ult].sort_values("valor", ascending=False).reset_index(drop=True)
val_nar = corte.loc[corte["departamento"] == NARINO, "valor"]
val_nar = float(val_nar.iloc[0]) if len(val_nar) else None
previos = dr[(dr["departamento"] == NARINO) & (dr["anio"] < ult)].sort_values("anio")
val_prev = float(previos["valor"].iloc[-1]) if len(previos) else None
anio_prev = int(previos["anio"].iloc[-1]) if len(previos) else None
promedio = float(corte["valor"].mean())
puesto = corte.index[corte["departamento"] == NARINO]
puesto = int(puesto[0]) + 1 if len(puesto) else None

st.subheader(indicador)
c1, c2, c3, c4 = st.columns(4)
c1.metric(f"Nariño ({ult})", fmt(val_nar),
          delta=(f"{fmt(val_nar - val_prev)} frente a {anio_prev}" if val_nar is not None and val_prev is not None else None))
c2.metric(f"Promedio departamental ({ult})", fmt(promedio), help="Promedio simple de los departamentos con dato.")
c3.metric("Puesto de Nariño", f"{puesto} de {len(corte)}" if puesto else "sin dato",
          help="1 = el departamento con el valor más alto.")
c4.metric("Nariño frente al promedio",
          f"{(val_nar / promedio - 1) * 100:+.1f} %".replace(".", ",") if val_nar is not None and promedio else "sin dato")

if (dr["nota"] != "").any():
    st.caption("⚠️ El último año está incompleto: no lo compares directamente con años completos.")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["📈 Tendencia", "🏆 Ranking", "🗺️ Mapa", "📋 Estadística descriptiva", "🗂️ Datos y descarga", "🔎 Fuentes y diagnóstico"]
)

# ---------------- Tendencia ----------------
with tab1:
    dl = dr[dr["departamento"].isin(seleccion)].sort_values("anio")
    fig = px.line(dl, x="anio", y="valor", color="departamento", markers=True,
                  labels={"anio": "Año", "valor": "Valor", "departamento": "Departamento"})
    for tr in fig.data:
        if tr.name == NARINO:
            tr.update(line=dict(color=VERDE_NARINO, width=5))
        else:
            tr.update(line=dict(width=2), opacity=0.75)
    prom = dr.groupby("anio", as_index=False)["valor"].mean()
    fig.add_trace(go.Scatter(x=prom["anio"], y=prom["valor"], name="Promedio departamental",
                             mode="lines", line=dict(color=ORO_NARINO, dash="dash", width=3)))
    fig.update_layout(height=480, hovermode="x unified", legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)

    serie_nar = dr[dr["departamento"] == NARINO].sort_values("anio")
    if len(serie_nar) >= 2:
        v_ini, v_fin = serie_nar["valor"].iloc[0], serie_nar["valor"].iloc[-1]
        y_ini, y_fin = int(serie_nar["anio"].iloc[0]), int(serie_nar["anio"].iloc[-1])
        cambio = f" ({(v_fin / v_ini - 1) * 100:+.1f} %)".replace(".", ",") if v_ini else ""
        direccion = "subió" if v_fin > v_ini else ("bajó" if v_fin < v_ini else "se mantuvo")
        st.markdown(f"**Lectura automática:** entre {y_ini} y {y_fin}, el indicador en Nariño {direccion} "
                    f"de {fmt(v_ini)} a {fmt(v_fin)}{cambio}. La línea punteada amarilla es el promedio de "
                    f"los departamentos con dato en cada año.")

# ---------------- Ranking ----------------
with tab2:
    anios_r = sorted(dr["anio"].unique())
    anio_r = st.select_slider("Año del ranking", options=anios_r, value=anios_r[-1]) if len(anios_r) > 1 else anios_r[0]
    rk = dr[dr["anio"] == anio_r].sort_values("valor")
    rk["grupo"] = rk["departamento"].apply(lambda d: "Nariño" if d == NARINO else "Otros departamentos")
    fig = px.bar(rk, x="valor", y="departamento", orientation="h", color="grupo",
                 color_discrete_map={"Nariño": VERDE_NARINO, "Otros departamentos": GRIS},
                 labels={"valor": "Valor", "departamento": "", "grupo": ""})
    fig.update_layout(height=max(420, 26 * len(rk)), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Se muestran todos los departamentos con dato, para que Nariño siempre aparezca en la comparación.")

# ---------------- Mapa ----------------
with tab3:
    anios_m = sorted(dr["anio"].unique())
    anio_m = st.select_slider("Año del mapa", options=anios_m, value=anios_m[-1], key="anio_mapa") if len(anios_m) > 1 else anios_m[0]
    dm = dr[dr["anio"] == anio_m][["departamento", "valor"]]
    st.plotly_chart(figura_mapa(dm, f"{indicador} – {anio_m}"), use_container_width=True)
    st.caption("Límites departamentales: archivo GeoJSON público de Colombia. Los valores son de la fuente oficial indicada.")

# ---------------- Estadística descriptiva ----------------
with tab4:
    st.markdown("**Resumen por departamento en el rango de años elegido**")
    grupo = dr[dr["departamento"].isin(seleccion)] if seleccion else dr
    desc = grupo.groupby("departamento")["valor"].agg(
        Observaciones="count", Promedio="mean", Mediana="median",
        Desviación_estándar="std", Mínimo="min", Máximo="max",
    )
    desc["Coef. de variación (%)"] = desc["Desviación_estándar"] / desc["Promedio"].abs() * 100
    piv = dr.pivot_table(index="anio", columns="departamento", values="valor")
    variaciones = {}
    for d in desc.index:
        s = piv[d].dropna() if d in piv else pd.Series(dtype=float)
        variaciones[d] = (s.iloc[-1] / s.iloc[0] - 1) * 100 if len(s) >= 2 and s.iloc[0] != 0 else None
    desc["Variación en el período (%)"] = pd.Series(variaciones)
    total = dr["valor"].agg(["count", "mean", "median", "std", "min", "max"])
    desc.loc["Todos los departamentos"] = [total["count"], total["mean"], total["median"], total["std"],
                                           total["min"], total["max"],
                                           total["std"] / abs(total["mean"]) * 100 if total["mean"] else None, None]
    desc = desc.rename(columns={"Desviación_estándar": "Desviación estándar"})
    st.dataframe(desc.round(2), use_container_width=True)

    st.markdown("**Distribución entre departamentos por año** (el punto verde es Nariño)")
    figb = px.box(dr, x="anio", y="valor", points=False, labels={"anio": "Año", "valor": "Valor"},
                  color_discrete_sequence=[GRIS])
    nar = dr[dr["departamento"] == NARINO]
    figb.add_trace(go.Scatter(x=nar["anio"], y=nar["valor"], mode="markers+lines", name="Nariño",
                              marker=dict(color=VERDE_NARINO, size=10), line=dict(color=VERDE_NARINO)))
    figb.update_layout(height=420)
    st.plotly_chart(figb, use_container_width=True)
    st.caption("La caja cubre del 25 % al 75 % de los departamentos; la línea interna es la mediana. "
               "Si el punto de Nariño está por encima de la caja, está entre los valores más altos del país.")

# ---------------- Datos y descarga ----------------
with tab5:
    tabla = dr.sort_values(["anio", "departamento"]).rename(columns={
        "departamento": "Departamento", "anio": "Año", "valor": "Valor", "indicador": "Indicador",
        "fuente": "Fuente", "url_fuente": "Enlace de la fuente", "nota": "Nota"})
    tabla = tabla[["Departamento", "Año", "Valor", "Indicador", "Fuente", "Enlace de la fuente", "Nota"]]
    st.dataframe(tabla, use_container_width=True, height=420)
    col_a, col_b = st.columns(2)
    col_a.download_button("Descargar datos filtrados (CSV)", tabla.to_csv(index=False).encode("utf-8-sig"),
                          file_name="observatorio_narino_filtrado.csv", mime="text/csv")
    col_b.download_button(f"Descargar toda la categoría «{categoria}» (CSV)",
                          datos.to_csv(index=False).encode("utf-8-sig"),
                          file_name="observatorio_narino_categoria.csv", mime="text/csv")

# ---------------- Fuentes y diagnóstico ----------------
with tab6:
    st.markdown("**Estado de las fuentes de esta categoría**")
    st.dataframe(pd.DataFrame(estados), use_container_width=True)
    if st.button("Probar todas las fuentes del observatorio"):
        todos = []
        with st.spinner("Probando todas las fuentes…"):
            for cat in CATEGORIAS:
                todos += cargar_categoria(cat)[1]
        st.dataframe(pd.DataFrame(todos), use_container_width=True)
    st.markdown(
        """
**Notas metodológicas**
- Todos los valores provienen de archivos y APIs oficiales; no hay datos simulados ni aleatorios.
- Los nombres de departamentos se normalizan (tildes, mayúsculas, códigos) para poder cruzar fuentes.
- Las tasas por 100.000 habitantes y los valores per cápita usan las proyecciones de población del DANE (CNPV 2018), disponibles desde 2018.
- Los delitos se suman por año en el servidor de datos.gov.co, así no hay límite de filas.
- Las finanzas OEC se presentan como suma de las entidades territoriales que reporta el DNP para cada departamento.
- El PIB 2024–2025 es preliminar (pr) y puede ser revisado por el DANE.
"""
    )

st.markdown("---")
st.caption("Observatorio Económico y Social de Nariño · Prototipo académico · Fuentes: DANE, DNP, "
           "datos.gov.co (Policía Nacional, MinDefensa, MinCiencias).")
