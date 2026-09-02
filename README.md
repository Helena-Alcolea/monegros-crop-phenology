# Fenología de cultivos en Monegros II

<En desarrollo>

Dashboard geoespacial para explorar la evolución estacional de los cultivos de
secano, regadío y pivote central en una zona piloto de Monegros II. Combina
declaraciones PAC/SIGPAC de 2025 con una serie temporal Sentinel-2 L2A desde
septiembre de 2024 hasta octubre de 2025.

> **English summary:** Bilingual Streamlit dashboard combining declared crop
> parcels, monthly Sentinel-2 imagery and robust NDVI phenology curves for a
> pilot agricultural area in Monegros II, Spain.

## Aplicación

La interfaz permite:

- cambiar entre español e inglés;
- seleccionar secano, regadío sin pivote o pivote central;
- comparar uno o varios cultivos y secuencias en una lista de selección múltiple;
- recorrer 14 mosaicos mensuales Sentinel-2 en color real;
- superponer los cultivos declarados sobre una imagen fija del área de estudio;
- comparar la mediana móvil de NDVI de cada cultivo junto con su rango
  intercuartílico;
- consultar de forma resumida el momento y valor de los máximos observados.

Los colores se mantienen consistentes entre las capas del mapa y las curvas de
NDVI. La aplicación utiliza exclusivamente los archivos ligeros y versionables
incluidos en `app_data/`.

## Metodología resumida

1. Se recortan las declaraciones PAC/SIGPAC de 2025 al área de estudio.
2. Las unidades se clasifican como secano, regadío sin pivote o pivote central.
3. Para cada fecha Sentinel-2 se calcula el NDVI mediano de cada unidad válida.
4. En los pivotes, los fragmentos PAC de un mismo pivote físico se combinan
   antes de agregar los resultados.
5. Para cada cultivo y sistema se representa la mediana móvil centrada de 30
   días y el rango intercuartílico entre unidades.

Se exige un mínimo del 80 % de píxeles válidos por unidad y fecha, al menos 20
píxeles interiores y un mínimo de tres unidades físicas para publicar una
curva comparativa.

## Área y periodo de estudio

```text
Oeste  -0.078535
Sur    41.455348
Este   -0.020767
Norte  41.492320
Periodo Sentinel-2: 2024-09-01 — 2025-10-31
```

La muestra final contiene 261 unidades de análisis: 152 de secano, 91 de
regadío sin pivote y 18 fragmentos asociados a pivotes. Las curvas de pivote se
agregan por pivote físico, no por fragmento.

## Estructura del repositorio

```text
.
├── .streamlit/
│   └── config.toml
├── app_data/
│   ├── monthly_rgb/
│   ├── curves.csv
│   ├── groups.csv
│   ├── monthly_rgb.json
│   └── units.geojson
├── data_reference/
│   └── crop_codes_2025.csv
├── data_sentinel2/raw/
│   └── README.md
├── data_sigpac/raw/
│   └── README.md
├── monegros_ndvi/
│   ├── __init__.py
│   ├── app_assets.py
│   ├── crop_timeseries.py
│   ├── download_sentinel2.py
│   ├── phenology.py
│   └── settings.py
├── tests/
├── analyze_crop_ndvi.py
├── prepare_streamlit_data.py
├── sentinel2.py
├── streamlit_app.py
├── requirements.txt
├── .env.example
└── .gitignore
```

Los GeoPackage originales, los GeoTIFF Sentinel-2, las credenciales y los
resultados intermedios se mantienen fuera de Git mediante `.gitignore`.

## Ejecución local

Con Python 3.11 o posterior:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

En Windows, la activación del entorno es:

```powershell
.venv\Scripts\activate
```

Para desplegarla en Streamlit Community Cloud, selecciona `streamlit_app.py`
como archivo principal.

## Reproducción del análisis

El dashboard ya incluye los datos compactos necesarios. Para reproducir todo
el procesamiento desde los datos fuente:

```bash
python sentinel2.py plan
python sentinel2.py download
python analyze_crop_ndvi.py
python prepare_streamlit_data.py
```

Las credenciales de Copernicus Data Space deben guardarse localmente a partir
de `.env.example`; nunca deben añadirse al repositorio. Para regenerar también
los mosaicos RGB mensuales:

```bash
python prepare_streamlit_data.py --download-rgb --overwrite-rgb
```

## Fuentes de datos

- Sentinel-2 L2A, Copernicus Data Space Ecosystem.
- Declaraciones de cultivos PAC/SIGPAC 2025 del Gobierno de Aragón.
- Catálogos abiertos de cultivos herbáceos y leñosos del Gobierno de Aragón.
- Calendario oficial de siembra, recolección y comercialización para Aragón
  (MAPA, datos provinciales de Huesca):
  https://www.mapa.gob.es/es/estadistica/temas/estadisticas-agrarias/02-aragon_tcm30-514168.pdf
- *Cebada y maíz rastrojero*, Información Técnica nº 245 del Gobierno de
  Aragón, basada en ensayos realizados en nuevos regadíos de Monegros y Cinco
  Villas:
  https://bibliotecavirtual.aragon.es/es/catalogo_imagenes/grupo.do?path=3707927

## Limitaciones

El proyecto es un análisis descriptivo de una zona piloto. Las declaraciones
PAC representan usos declarados, la nubosidad condiciona algunas fechas y los
pivotes confirmados no constituyen una muestra experimental independiente. Por
ello, las diferencias observadas no se interpretan como efectos causales del
sistema de riego.

Las fases fenológicas que aparecen en la interfaz son calendarios orientativos,
no observaciones directas de siembra o cosecha. Las ventanas de siembra y
recolección se apoyan en las fuentes oficiales anteriores; las fases
intermedias se aproximan entre ambos hitos y pueden variar según campaña,
variedad, disponibilidad de agua y manejo de cada parcela.
