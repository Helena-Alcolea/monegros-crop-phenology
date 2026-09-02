# Fenología de cultivos en Monegros II

*En desarrollo*

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

