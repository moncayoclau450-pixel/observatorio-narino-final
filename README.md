# Observatorio Económico y Social de Nariño

Prototipo tecnológico de un observatorio económico y social centrado en **Nariño** y comparativo con los demás departamentos de Colombia. Es una aplicación web interactiva hecha en **Python + Streamlit**, desplegada en **Streamlit Cloud**.

## Regla antialucinación

Todos los datos se descargan en vivo de **fuentes oficiales**. La aplicación **no usa datos aleatorios ni sintéticos** (no hay `np.random`). Si una fuente no responde, la app lo informa al usuario y no inventa valores. La pestaña *Fuentes y diagnóstico* muestra el estado de cada fuente.

## Categorías y fuentes

| Categoría | Fuente oficial | Formato |
|---|---|---|
| Crecimiento / PIB | DANE – PIB por departamentos 2005–2025pr | Excel |
| Mercado laboral | DANE – GEIH, mercado laboral por departamentos (total, hombres, mujeres, urbano y rural) | Excel |
| Seguridad ciudadana | datos.gov.co (Policía Nacional / MinDefensa): conjuntos `4rxi-8m8d` y `m8fd-ahd9` | API SODA |
| Finanzas públicas | DNP – Operaciones Efectivas de Caja (OEC) 2000–2024 | Excel |
| Ciencia, tecnología e innovación | MinCiencias en datos.gov.co: grupos de investigación reconocidos `hrhc-c4wu` | API SODA |
| Pobreza y equidad | DANE – Pobreza monetaria, Gini e IPM departamental | Excel |
| Población (para tasas) | DANE – Proyecciones de población departamental CNPV 2018 | Excel |

## Funcionalidades

- **Filtros** por categoría, indicador, rango de años y departamentos.
- **Tarjetas de métricas (KPIs):** valor de Nariño, variación anual, promedio departamental, puesto de Nariño y brecha frente al promedio.
- **Gráficos interactivos con Plotly:** tendencia (Nariño resaltado y promedio departamental), ranking de todos los departamentos y mapa coroplético.
- **Estadística descriptiva automatizada:** observaciones, promedio, mediana, desviación estándar, mínimo, máximo, coeficiente de variación y variación en el período, más diagramas de caja por año.
- **Visor de datos** con descarga en CSV (datos filtrados o categoría completa).
- **Indicadores calculados:** tasas por 100.000 habitantes (delitos, grupos de investigación), PIB per cápita y finanzas por habitante, usando la población oficial del DANE.

## Limpieza automatizada de datos

- Normalización de nombres de departamentos (tildes, mayúsculas, códigos DANE, variantes como "Bogotá, D.C." o "Archipiélago de San Andrés…").
- Detección automática de encabezados de años en los anexos del DANE (incluye años preliminares como "2024pr").
- Manejo de valores faltantes: las celdas vacías o no numéricas se descartan, no se rellenan.
- Los delitos se agregan por año en el servidor de datos.gov.co, sin límite de filas.
- El año en curso de los delitos se marca como incompleto y se excluye por defecto.

## Archivos

- `app.py`: aplicación principal de Streamlit.
- `requirements.txt`: librerías necesarias.
- `README.md`: esta documentación.

## Ejecución local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Limitaciones

- El PIB de los últimos años es preliminar y puede ser revisado por el DANE.
- Las tasas per cápita solo existen desde 2018, por la cobertura de las proyecciones de población.
- Las finanzas OEC se presentan como suma de las entidades territoriales reportadas para cada departamento.
- El servidor del DNP tiene un certificado de seguridad incompleto; para ese único servidor oficial la descarga se reintenta sin verificar el certificado.
- La base de grupos de investigación tiene su propia fecha de corte, indicada por MinCiencias.
- El mapa usa un archivo público de límites departamentales; los valores siempre vienen de la fuente oficial.
