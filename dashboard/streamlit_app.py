"""Interactive bilingual portfolio dashboard for the Monegros II crop study."""

from __future__ import annotations

import calendar
import html
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image, ImageDraw

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from monegros_ndvi.phenology import calendar_for


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "app_data"
SYSTEM_COLORS = {
    "dryland": "#D99032",
    "irrigated_non_pivot": "#2A9D6F",
    "pivot": "#3575B5",
}
# Paleta agraria: el tono dice el sistema (tierras en secano, verdes y azules en
# regadío) y el trazo lo repite (continuo, discontinuo, punteado). Al separar los
# dos canales, los colores solo compiten dentro de su propio bloque, y eso permite
# abrirlos sin salirse de la gama. Ninguno pasa de croma 0,155 en OKLCh.
GROUP_COLORS = {
    # Secano · línea continua · tierras
    "20-s-dryland-barbecho-tradicional": "#512E18",
    "5-s-dryland-cebada": "#C39800",
    "13-s-dryland-triticale": "#866222",
    "1-s-dryland-trigo-blando": "#868600",
    "40-s-dryland-guisante": "#7F7D51",
    "53-s-dryland-yeros": "#9E9B66",
    "62-s-dryland-pastos-permanentes-de-5-o-mas-anos": "#6D4935",
    # Regadío sin pivote · línea discontinua · verdes y azules
    "5-r-irrigated-non-pivot-cebada-maiz": "#57A8FF",
    "40-r-irrigated-non-pivot-guisante-maiz": "#1D3F61",
    "60-r-irrigated-non-pivot-alfalfa": "#4E777B",
    "4-r-irrigated-non-pivot-maiz": "#6AB985",
    "20-r-irrigated-non-pivot-barbecho-tradicional": "#005EAB",
    "5-r-irrigated-non-pivot-cebada": "#519FB1",
    "68-r-irrigated-non-pivot-festuca": "#004333",
    "13-r-irrigated-non-pivot-triticale": "#0085B4",
    "52-r-irrigated-non-pivot-veza-maiz": "#2B5C58",
    # Pivote central · línea punteada
    "4-r-pivot-maiz": "#2183D8",
}
PHASE_BAND = {"bottom": 1.018, "top": 1.072}
PHASE_LABEL_ROWS = (1.115, 1.178)
PLOT_DAYS = 426
PLOT_WIDTH_HINT = 1000
PORTFOLIO_GROUP_ORDER = [
    "20-s-dryland-barbecho-tradicional",
    "5-s-dryland-cebada",
    "13-s-dryland-triticale",
    "5-r-irrigated-non-pivot-cebada-maiz",
    "40-r-irrigated-non-pivot-guisante-maiz",
    "60-r-irrigated-non-pivot-alfalfa",
    "4-r-irrigated-non-pivot-maiz",
    "4-r-pivot-maiz",
]
TEXT = {
    "es": {
        "page_title": "Monegros II · Fenología agrícola",
        "eyebrow": "FENOLOGÍA DE CULTIVOS · TELEDETECCIÓN",
        "title": "El pulso agrícola de Monegros II",
        "subtitle": "Explora cómo cambian los cultivos de secano, regadío y pivote a lo largo del año.",
        "meta": (
            ("Zona de estudio", "Monegros II · Huesca, Aragón"),
            ("Campaña", "PAC 2025 · sep 2024 – oct 2025"),
            ("Fuente", "Sentinel-2 L2A · SIGPAC"),
        ),
        "dash_key": "Trazo: continuo secano · discontinuo regadío · punteado pivote",
        "language": "Idioma",
        "system": "Sistema agrícola",
        "all": "Todos",
        "dryland": "Secano",
        "irrigated_non_pivot": "Regadío sin pivote",
        "pivot": "Pivote central",
        "crops": "Cultivos y secuencias",
        "choose_crops": "Seleccionar cultivo",
        "month": "Imagen mensual",
        "layer_opacity": "Opacidad de la capa",
        "map": "Mosaico mensual y cultivos declarados",
        "chart": "Evolución del NDVI · mediana móvil de 30 días",
        "chart_key": "Puntos: medianas observadas · líneas: mediana móvil centrada de 30 días · bandas: rango intercuartílico.",
        "phase_yes": "Fases · Sí",
        "phase_no": "Fases · No",
        "phase_reference": "Calendario orientativo: {crop}",
        "cycle_shown": "Ciclo mostrado",
        "phase_scheme": "Fases orientativas",
        "valid_units": "Nº unidades válidas",
        "no_crop": "Selecciona al menos un cultivo para dibujar su curva y su capa sobre el mosaico.",
        "peak": "Máximo observado",
        "seasonal_variation": "Variación estacional",
        "samples_units": "unidades",
        "samples_pivots": "pivotes",
        "primary_cycle": "Primer ciclo",
        "secondary_cycle": "Segundo ciclo",
        "about": "Acerca de los datos",
        "about_text": "Cultivos declarados PAC 2025 y observaciones Sentinel-2 L2A entre septiembre de 2024 y octubre de 2025. Las curvas muestran la mediana suavizada de las unidades disponibles; dentro de los pivotes, cada pivote físico cuenta una sola vez.",
        "selected_month": "Mes seleccionado",
        "ndvi": "NDVI",
        "date": "Fecha",
    },
    "en": {
        "page_title": "Monegros II · Crop phenology",
        "eyebrow": "CROP PHENOLOGY · REMOTE SENSING",
        "title": "The agricultural pulse of Monegros II",
        "subtitle": "Explore how dryland, irrigated and centre-pivot crops change through the year.",
        "meta": (
            ("Study area", "Monegros II · Huesca, Aragon"),
            ("Campaign", "2025 CAP · Sep 2024 – Oct 2025"),
            ("Source", "Sentinel-2 L2A · SIGPAC"),
        ),
        "dash_key": "Line: solid dryland · dashed irrigated · dotted centre pivot",
        "language": "Language",
        "system": "Agricultural system",
        "all": "All",
        "dryland": "Dryland",
        "irrigated_non_pivot": "Irrigated, non-pivot",
        "pivot": "Centre pivot",
        "crops": "Crops and sequences",
        "choose_crops": "Select crops",
        "month": "Monthly image",
        "layer_opacity": "Layer opacity",
        "map": "Monthly mosaic and declared crops",
        "chart": "NDVI evolution · 30-day rolling median",
        "chart_key": "Dots: observed medians · lines: centred 30-day rolling median · bands: interquartile range.",
        "phase_yes": "Phases · On",
        "phase_no": "Phases · Off",
        "phase_reference": "Indicative calendar: {crop}",
        "cycle_shown": "Cycle shown",
        "phase_scheme": "Indicative phases",
        "valid_units": "Valid units",
        "no_crop": "Select at least one crop to draw its curve and its layer over the mosaic.",
        "peak": "Observed peak",
        "seasonal_variation": "Seasonal variation",
        "samples_units": "units",
        "samples_pivots": "pivots",
        "primary_cycle": "First cycle",
        "secondary_cycle": "Second cycle",
        "about": "About the data",
        "about_text": "Declared 2025 CAP crops and Sentinel-2 L2A observations from September 2024 to October 2025. Curves show the smoothed median of available units; within centre pivots, each physical pivot counts once.",
        "selected_month": "Selected month",
        "ndvi": "NDVI",
        "date": "Date",
    },
}
MONTHS = {
    "es": [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ],
    "en": [month.lower() for month in calendar.month_name[1:]],
}


def dash_for(regime: str, system_class: str) -> str:
    """El trazo repite el sistema agrícola, para que el color no cargue solo."""
    if regime == "S":
        return "solid"
    return "dot" if system_class == "pivot" else "dash"


@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    groups = pd.read_csv(DATA_DIR / "groups.csv")
    groups["color"] = groups["group_id"].map(GROUP_COLORS).fillna(groups["color"])
    groups["dash"] = [
        dash_for(regime, system_class)
        for regime, system_class in zip(groups["regime"], groups["system_class"])
    ]
    curves = pd.read_csv(DATA_DIR / "curves.csv", parse_dates=["date"])
    units = json.loads((DATA_DIR / "units.geojson").read_text(encoding="utf-8"))
    monthly = json.loads((DATA_DIR / "monthly_rgb.json").read_text(encoding="utf-8"))
    return groups, curves, units, monthly


def month_label(value: str, language: str) -> str:
    year, month = (int(item) for item in value.split("-"))
    return f"{MONTHS[language][month - 1].capitalize()} {year}"


def phase_month_range(start: str, end: str, language: str) -> str:
    first = date.fromisoformat(start)
    last = date.fromisoformat(end)
    first_month = MONTHS[language][first.month - 1][:3]
    last_month = MONTHS[language][last.month - 1][:3]
    if first.year == last.year:
        if first.month == last.month:
            return f"{first_month} {first.year}"
        return f"{first_month}–{last_month} {first.year}"
    return f"{first_month} {first.year}–{last_month} {last.year}"


def phase_chart_layers(
    sequence: str,
    language: str,
) -> tuple[list[dict], list[dict]]:
    """Franja de fases situada por encima del área de trazado.

    Las etiquetas ya no se escriben sobre las curvas: viven en una banda propia y
    se reparten en dos filas cuando el nombre no cabe dentro de su tramo.
    """
    shapes: list[dict] = []
    annotations: list[dict] = []
    origin = pd.Timestamp("2024-09-01")
    pixels_per_day = PLOT_WIDTH_HINT / PLOT_DAYS
    font_size = 13
    row_ends = [-1e6, -1e6]
    for phase in calendar_for(sequence):
        start = pd.Timestamp(phase["start"])
        end = pd.Timestamp(phase["end"]) + pd.Timedelta(days=1)
        label = phase[f"label_{language}"]
        shapes.append(
            {
                "type": "rect",
                "xref": "x",
                "yref": "paper",
                "x0": start,
                "x1": end,
                "y0": 0,
                "y1": 1,
                "fillcolor": phase["color"],
                "opacity": 0.075,
                "line": {"width": 0},
                "layer": "below",
            }
        )
        shapes.append(
            {
                "type": "rect",
                "xref": "x",
                "yref": "paper",
                "x0": start,
                "x1": end,
                "y0": PHASE_BAND["bottom"],
                "y1": PHASE_BAND["top"],
                "fillcolor": phase["color"],
                "opacity": 0.62,
                "line": {"width": 0},
            }
        )
        centre_day = (start - origin).days + (end - start).days / 2
        text_days = len(label) * 0.52 * font_size / pixels_per_day
        row = 1 if centre_day - text_days / 2 < row_ends[0] + 3 else 0
        if row == 1 and centre_day - text_days / 2 < row_ends[1] + 3:
            row = 0
        row_ends[row] = centre_day + text_days / 2
        annotations.append(
            {
                "xref": "x",
                "yref": "paper",
                "x": start + (end - start) / 2,
                "y": PHASE_LABEL_ROWS[row],
                "text": f"<b>{label}</b>",
                "showarrow": False,
                "font": {"size": font_size, "color": "#1B3446"},
                "yanchor": "middle",
                "xanchor": "center",
            }
        )
        shapes.append(
            {
                "type": "line",
                "xref": "x",
                "yref": "paper",
                "x0": start + (end - start) / 2,
                "x1": start + (end - start) / 2,
                "y0": PHASE_BAND["top"],
                "y1": PHASE_LABEL_ROWS[row] - 0.022,
                "line": {"color": phase["color"], "width": 1.2},
            }
        )
    return shapes, annotations


def hex_to_rgb(color: str, alpha: int = 118) -> list[int]:
    return [int(color[index:index + 2], 16) for index in (1, 3, 5)] + [alpha]


def feature_subset(units: dict, system: str, selected_groups: list[str]) -> list[dict]:
    if not selected_groups:
        return []
    features = []
    for feature in units["features"]:
        properties = feature["properties"]
        if system != "all" and properties["system_class"] != system:
            continue
        if selected_groups and properties["group_id"] not in selected_groups:
            continue
        features.append(feature)
    return features


def _pixel_ring(
    ring: list[list[float]],
    *,
    width: int,
    height: int,
    bounds: tuple[float, float, float, float],
) -> list[tuple[float, float]]:
    west, south, east, north = bounds
    return [
        (
            (longitude - west) / (east - west) * width,
            (north - latitude) / (north - south) * height,
        )
        for longitude, latitude, *_ in ring
    ]


def _draw_polygon(
    overlay: Image.Image,
    coordinates: list,
    *,
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    bounds: tuple[float, float, float, float],
) -> None:
    draw = ImageDraw.Draw(overlay, "RGBA")
    exterior = _pixel_ring(
        coordinates[0], width=overlay.width, height=overlay.height, bounds=bounds
    )
    draw.polygon(exterior, fill=fill, outline=outline, width=2)
    for interior in coordinates[1:]:
        hole = _pixel_ring(
            interior, width=overlay.width, height=overlay.height, bounds=bounds
        )
        draw.polygon(hole, fill=(0, 0, 0, 0))


def build_aoi_image(
    units: dict,
    monthly: dict,
    selected_month: str,
    system: str,
    selected_groups: list[str],
    color_by_group: dict[str, str],
    opacity: float,
) -> Image.Image:
    bounds = tuple(monthly["bbox_wgs84"])
    image_record = next(item for item in monthly["months"] if item["month"] == selected_month)
    base = Image.open(DATA_DIR / image_record["image"]).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    for feature in feature_subset(units, system, selected_groups):
        properties = feature["properties"]
        color = color_by_group.get(
            properties["group_id"], SYSTEM_COLORS[properties["system_class"]]
        )
        # El contorno se apaga más despacio que el relleno: en opacidades bajas
        # queda el parcelario dibujado sobre la imagen, sin teñir el terreno.
        fill = tuple(hex_to_rgb(color, round(255 * opacity)))
        outline = tuple(hex_to_rgb(color, round(255 * opacity ** 0.25)))
        geometry = feature["geometry"]
        polygons = (
            [geometry["coordinates"]]
            if geometry["type"] == "Polygon"
            else geometry["coordinates"]
        )
        for polygon in polygons:
            _draw_polygon(
                overlay,
                polygon,
                fill=fill,
                outline=outline,
                bounds=bounds,
            )
    return Image.alpha_composite(base, overlay).convert("RGB")


def add_iqr_band(figure: go.Figure, data: pd.DataFrame, color: str) -> None:
    rgba = tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))
    fill = f"rgba({rgba[0]},{rgba[1]},{rgba[2]},0.13)"
    figure.add_trace(
        go.Scatter(
            x=pd.concat([data["date"], data["date"].iloc[::-1]]),
            y=pd.concat([data["ndvi_q75"], data["ndvi_q25"].iloc[::-1]]),
            fill="toself",
            fillcolor=fill,
            line={"color": "rgba(0,0,0,0)"},
            hoverinfo="skip",
            showlegend=False,
        )
    )


def build_chart(
    curves: pd.DataFrame,
    groups: pd.DataFrame,
    selected_groups: list[str],
    selected_month: str,
    language: str,
) -> go.Figure:
    text = TEXT[language]
    figure = go.Figure()
    chosen = groups.set_index("group_id").loc[selected_groups] if selected_groups else groups.iloc[0:0]
    for group_identifier, metadata in chosen.iterrows():
        data = curves[curves["group_id"] == group_identifier].sort_values("date")
        add_iqr_band(figure, data, metadata["color"])
        label = metadata["label_es"] if language == "es" else metadata["label_en"]
        figure.add_trace(
            go.Scatter(
                x=data["date"],
                y=data["ndvi_median"],
                mode="markers",
                marker={"color": metadata["color"], "size": 4, "opacity": 0.28},
                name=label,
                legendgroup=group_identifier,
                showlegend=False,
                hovertemplate=(
                    f"<b>{label}</b><br>{text['date']}: %{{x|%d %b %Y}}"
                    f"<br>{text['ndvi']}: %{{y:.2f}}<extra></extra>"
                ),
            )
        )
        figure.add_trace(
            go.Scatter(
                x=data["date"],
                y=data["ndvi_median_30d"],
                mode="lines",
                name=label,
                legendgroup=group_identifier,
                line={
                    "color": metadata["color"],
                    "width": 3,
                    "dash": metadata["dash"],
                },
                customdata=data[["observed_samples"]],
                hovertemplate=(
                    f"<b>{label}</b><br>{text['date']}: %{{x|%d %b %Y}}"
                    f"<br>{text['ndvi']}: %{{y:.2f}}<extra></extra>"
                ),
            )
        )
    month_start = pd.Timestamp(f"{selected_month}-01")
    month_end = month_start + pd.offsets.MonthEnd(1)
    month_shape = {
        "type": "rect",
        "xref": "x",
        "yref": "paper",
        "x0": month_start,
        "x1": month_end,
        "y0": 0,
        "y1": 1,
        "fillcolor": "#20364B",
        "opacity": 0.07,
        "line": {"width": 0},
        "layer": "below",
    }
    month_annotation = {
        "xref": "x",
        "yref": "paper",
        "x": month_start + (month_end - month_start) / 2,
        "y": 0.015,
        "text": text["selected_month"],
        "showarrow": False,
        "font": {"size": 11, "color": "#344957"},
        "bgcolor": "rgba(252,250,245,0.82)",
        "borderpad": 3,
        "yanchor": "bottom",
    }
    reference_sequence = str(chosen.iloc[0]["crop_sequence"])
    phase_shapes, phase_annotations = phase_chart_layers(reference_sequence, language)
    cycle_label = html.escape(
        str(chosen.iloc[0]["label_es"] if language == "es" else chosen.iloc[0]["label_en"])
    )
    phase_header = {
        "xref": "paper",
        "yref": "paper",
        "x": 0,
        "y": 1.255,
        "text": f'<b>{text["cycle_shown"]} · {cycle_label}</b>',
        "showarrow": False,
        "font": {"size": 12, "color": "#FFFFFF"},
        "bgcolor": "#29495B",
        "bordercolor": "#29495B",
        "borderwidth": 1,
        "borderpad": 6,
        "xanchor": "left",
        "yanchor": "middle",
    }
    base_shapes = [month_shape]
    base_annotations = [month_annotation]
    visible_shapes = [*base_shapes, *phase_shapes]
    visible_annotations = [*base_annotations, phase_header, *phase_annotations]
    tick_dates = pd.date_range("2024-09-01", "2025-10-01", freq="MS")
    tick_labels = [
        f"{MONTHS[language][value.month - 1][:3].capitalize()}<br>{value.year}"
        for value in tick_dates
    ]
    figure.update_layout(
        height=660,
        margin={"l": 22, "r": 20, "t": 190, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FCFAF5",
        hovermode="x unified",
        shapes=visible_shapes,
        annotations=visible_annotations,
        updatemenus=[
            {
                "type": "buttons",
                "direction": "right",
                "showactive": True,
                "active": 0,
                "x": 1,
                "xanchor": "right",
                "y": 1.285,
                "yanchor": "top",
                "pad": {"r": 0, "t": 0},
                "bgcolor": "#FFFCF6",
                "bordercolor": "#A9B3B9",
                "font": {"color": "#20364B", "size": 11},
                "buttons": [
                    {
                        "label": text["phase_yes"],
                        "method": "relayout",
                        "args": [{"shapes": visible_shapes, "annotations": visible_annotations}],
                    },
                    {
                        "label": text["phase_no"],
                        "method": "relayout",
                        "args": [{"shapes": base_shapes, "annotations": base_annotations}],
                    },
                ],
            }
        ],
        legend={"orientation": "h", "y": -0.18, "x": 0, "font": {"size": 12, "color": "#263B49"}},
        xaxis={
            "title": None,
            "showgrid": False,
            "range": ["2024-09-01", "2025-10-31"],
            "tickmode": "array",
            "tickvals": tick_dates,
            "ticktext": tick_labels,
            "tickfont": {"color": "#1E3646", "size": 13},
            "showline": True,
            "linecolor": "#526574",
            "linewidth": 1.4,
            "ticks": "outside",
            "tickcolor": "#526574",
            "ticklen": 5,
            "automargin": True,
        },
        yaxis={
            "title": {"text": "NDVI", "font": {"color": "#17324B", "size": 16}},
            "range": [0, 1],
            "gridcolor": "rgba(32,54,75,0.15)",
            "zeroline": False,
            "tickfont": {"color": "#1E3646", "size": 13},
            "showline": True,
            "linecolor": "#526574",
            "linewidth": 1.4,
            "ticks": "outside",
            "tickcolor": "#526574",
            "ticklen": 5,
            "automargin": True,
        },
    )
    return figure


def format_peak(raw_date: object, raw_ndvi: object, language: str) -> str:
    if pd.isna(raw_date) or pd.isna(raw_ndvi):
        return "—"
    parsed = date.fromisoformat(str(raw_date))
    month = MONTHS[language][parsed.month - 1].capitalize()
    return f"{month} · {float(raw_ndvi):.2f} NDVI"


def phase_schedule_html(sequence: str, language: str) -> str:
    phases = calendar_for(sequence)
    if not phases:
        return ""
    items = []
    for phase in phases:
        label = html.escape(phase[f"label_{language}"])
        period = phase_month_range(phase["start"], phase["end"], language)
        items.append(
            f'<div class="phase-item">'
            f'<span class="phase-swatch" style="background:{phase["color"]}"></span>'
            f'<span class="phase-name">{label}</span>'
            f'<span class="phase-months">{period}</span>'
            f"</div>"
        )
    return '<div class="phase-grid">' + "".join(items) + "</div>"


def render_phenology(groups: pd.DataFrame, selected_groups: list[str], language: str) -> None:
    if not selected_groups:
        return
    text = TEXT[language]
    selected = groups.set_index("group_id").loc[selected_groups]
    cards = st.columns(min(len(selected), 3))
    for index, (_, row) in enumerate(selected.iterrows()):
        label = html.escape(row["label_es"] if language == "es" else row["label_en"])
        peak = format_peak(row["primary_peak_date"], row["primary_peak_ndvi"], language)
        second = format_peak(row["secondary_peak_date"], row["secondary_peak_ndvi"], language)
        phase_schedule = phase_schedule_html(str(row["crop_sequence"]), language)
        with cards[index % len(cards)]:
            second_html = (
                f'<div class="phenology-stat"><span>{text["secondary_cycle"]}</span>'
                f"<strong>{second}</strong></div>"
                if not pd.isna(row["secondary_peak_date"])
                else ""
            )
            st.markdown(
                f'<div class="phenology-card" style="border-top-color:{row["color"]}">'
                f'<div class="phenology-title">{label}</div>'
                f'<div class="phenology-stat"><span>{text["peak"]}</span><strong>{peak}</strong></div>'
                f"{second_html}"
                f'<div class="phenology-meta"><span>{text["seasonal_variation"]}: '
                f'{float(row["seasonal_amplitude"]):.2f}</span>'
                f'<strong>{text["valid_units"]}: {int(row["total_samples"])}</strong></div>'
                f'<div class="phase-heading">{text["phase_scheme"]}</div>'
                f"{phase_schedule}</div>",
                unsafe_allow_html=True,
            )


def main() -> None:
    st.set_page_config(page_title="Monegros II", page_icon="🌾", layout="wide")
    st.markdown(
        """
        <style>
        .stApp { background: #FAF8F2; color: #17324B; }
        [data-testid="stAppDeployButton"] { display:none; }
        .block-container { max-width: 1500px; padding-top: 2.45rem; padding-bottom: 2rem; }
        div[data-testid="stElementContainer"]:has(div[data-testid="stButtonGroup"]) { overflow:visible; }
        div[data-testid="stButtonGroup"] { overflow:visible; padding:4px 0 8px; }
        div[data-testid="stButtonGroup"] > div { overflow:visible; justify-content:flex-end; }
        div[data-testid="stButtonGroup"] button { min-height:38px; padding:5px 20px; font-weight:720; letter-spacing:.08em; line-height:1.5; }
        .hero { padding: .6rem 0 1.1rem; }
        .eyebrow { color:#B06435; font-size:.76rem; font-weight:750; letter-spacing:.16em; }
        .hero h1 { color:#17324B; font-size:clamp(2rem,4vw,3.7rem); line-height:1.02; margin:.28rem 0 .45rem; }
        .hero p { color:#3C5361; font-size:1.06rem; margin:0; }
        .hero-meta { display:flex; flex-wrap:wrap; gap:14px 38px; margin:20px 0 0; padding-top:15px; border-top:1px solid #DED8CA; }
        .hero-meta div { display:flex; flex-direction:column; gap:3px; }
        .hero-meta dt { color:#6E7E88; font-size:.71rem; font-weight:730; letter-spacing:.11em; text-transform:uppercase; }
        .hero-meta dd { margin:0; color:#223D4E; font-size:.95rem; font-weight:660; }
        .section-label { color:#17324B; font-size:1.45rem; font-weight:760; letter-spacing:-.005em; display:flex; align-items:center; gap:14px; margin:1.7rem 0 .85rem; }
        .section-label::before { content:""; width:5px; height:1.1em; border-radius:3px; background:#B06435; flex:none; }
        .section-label::after { content:""; flex:1; height:1px; background:linear-gradient(90deg,#D8D2C5,rgba(216,210,197,0)); }
        .phenology-card { background:#FFFCF6; border-radius:14px; border-top:5px solid; padding:18px 19px; margin:.55rem 0; box-shadow:0 5px 20px rgba(32,54,75,.07); }
        .phenology-title { color:#20364B; font-weight:780; font-size:1.08rem; margin-bottom:12px; }
        .phenology-stat { display:flex; justify-content:space-between; gap:12px; font-size:.93rem; color:#354D5A; padding:2px 0; }
        .phenology-stat strong { color:#1E3443; font-weight:720; }
        .phenology-meta { display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px 14px; color:#344D5A; font-size:.88rem; margin-top:11px; padding-top:10px; border-top:1px solid #E4E0D6; }
        .phenology-meta strong { color:#263E4C; font-weight:720; }
        .phase-heading { color:#263E4C; font-size:.85rem; font-weight:740; margin:14px 0 7px; }
        .phase-grid { display:grid; grid-template-columns:1fr; gap:5px; }
        .phase-item { display:grid; grid-template-columns:10px minmax(0,1fr) auto; align-items:center; gap:7px; color:#304A58; font-size:.79rem; line-height:1.2; }
        .phase-swatch { width:8px; height:8px; border-radius:50%; }
        .phase-name { font-weight:650; }
        .phase-months { color:#3D5360; font-size:.76rem; white-space:nowrap; }
        [data-testid="stCaptionContainer"] p { color:#354D5A; font-size:.91rem; }
        [data-testid="stWidgetLabel"] p { color:#263F4E; font-weight:650; }
        div[data-testid="stMetric"] { background:#FFFCF6; border-radius:12px; padding:10px; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    groups, curves, units, monthly = load_data()

    _, language_slot = st.columns([5, 1])
    with language_slot:
        language = st.segmented_control(
            "Language / Idioma",
            options=["es", "en"],
            default="es",
            format_func=lambda value: "ES" if value == "es" else "EN",
            label_visibility="collapsed",
            key="language",
        )
    language = language or "es"
    text = TEXT[language]
    meta_items = "".join(
        f"<div><dt>{label}</dt><dd>{value}</dd></div>" for label, value in text["meta"]
    )
    st.markdown(
        f"<div class='hero'><div class='eyebrow'>{text['eyebrow']}</div>"
        f"<h1>{text['title']}</h1><p>{text['subtitle']}</p>"
        f"<dl class='hero-meta'>{meta_items}</dl></div>",
        unsafe_allow_html=True,
    )

    control_system, control_crops, control_month, control_opacity = st.columns(
        [1.0, 2.1, 1.3, 1.0]
    )
    system_ids = ["all", "dryland", "irrigated_non_pivot", "pivot"]
    with control_system:
        system = st.selectbox(
            text["system"],
            system_ids,
            format_func=lambda value: text[value],
        )
    available = groups if system == "all" else groups[groups["system_class"] == system]
    labels = available.set_index("group_id")["label_es" if language == "es" else "label_en"].to_dict()
    ordered_ids = [identifier for identifier in PORTFOLIO_GROUP_ORDER if identifier in labels]
    ordered_ids.extend(identifier for identifier in labels if identifier not in ordered_ids)
    with control_crops:
        selected_groups = st.multiselect(
            text["crops"],
            options=ordered_ids,
            default=[],
            format_func=lambda value: labels[value],
            key=f"crop_selection_{system}",
            placeholder=text["choose_crops"],
        )
    months = [item["month"] for item in monthly["months"]]
    with control_month:
        selected_month = st.select_slider(
            text["month"],
            options=months,
            value="2025-07",
            format_func=lambda value: month_label(value, language),
        )
    with control_opacity:
        layer_opacity = st.slider(
            text["layer_opacity"],
            min_value=0,
            max_value=100,
            value=45,
            step=5,
            format="%d%%",
        )

    colors = groups.set_index("group_id")["color"].to_dict()
    st.markdown(f"<div class='section-label'>{text['map']}</div>", unsafe_allow_html=True)
    aoi_image = build_aoi_image(
        units,
        monthly,
        selected_month,
        system,
        selected_groups,
        colors,
        layer_opacity / 100,
    )
    st.image(aoi_image, width="stretch")

    st.markdown(f"<div class='section-label'>{text['chart']}</div>", unsafe_allow_html=True)
    if selected_groups:
        st.plotly_chart(
            build_chart(curves, groups, selected_groups, selected_month, language),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
        )
        reference = groups.set_index("group_id").loc[selected_groups[0]]
        reference_crop = (
            reference["crop_sequence"]
            if language == "es"
            else reference["crop_sequence_en"]
        )
        st.caption(
            f'{text["dash_key"]}. {text["chart_key"]} · '
            f'{text["phase_reference"].format(crop=reference_crop)}.'
        )
    else:
        st.info(text["no_crop"])

    render_phenology(groups, selected_groups, language)
    with st.expander(text["about"]):
        st.caption(text["about_text"])


if __name__ == "__main__":
    main()
