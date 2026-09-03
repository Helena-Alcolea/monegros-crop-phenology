"""Interactive bilingual portfolio dashboard for the Monegros II crop study."""

from __future__ import annotations

import calendar
import html
import json
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image, ImageDraw

from monegros_ndvi.phenology import calendar_for


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "app_data"
SYSTEM_COLORS = {
    "dryland": "#D99032",
    "irrigated_non_pivot": "#2A9D6F",
    "pivot": "#3575B5",
}
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
        "eyebrow": "SENTINEL-2 · CAMPAÑA PAC 2025",
        "title": "El pulso agrícola de Monegros II",
        "subtitle": "Explora cómo cambian los cultivos de secano, regadío y pivote a lo largo del año.",
        "language": "Idioma",
        "system": "Sistema agrícola",
        "all": "Todos",
        "dryland": "Secano",
        "irrigated_non_pivot": "Regadío sin pivote",
        "pivot": "Pivote central",
        "crops": "Cultivos y secuencias",
        "choose_crops": "Selecciona una o varias opciones",
        "month": "Imagen mensual",
        "map": "Mosaico mensual y cultivos declarados",
        "chart": "Evolución del NDVI · mediana móvil de 30 días",
        "chart_key": "Puntos: medianas observadas · líneas: mediana móvil centrada de 30 días · bandas: rango intercuartílico.",
        "phase_yes": "Fases · Sí",
        "phase_no": "Fases · No",
        "phase_reference": "Calendario orientativo: {crop}",
        "phase_scheme": "Fases orientativas",
        "valid_units": "Nº unidades válidas",
        "no_crop": "Selecciona al menos un cultivo para mostrar su curva.",
        "peak": "Máximo observado",
        "amplitude": "Amplitud",
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
        "eyebrow": "SENTINEL-2 · 2025 CAP CAMPAIGN",
        "title": "The agricultural pulse of Monegros II",
        "subtitle": "Explore how dryland, irrigated and centre-pivot crops change through the year.",
        "language": "Language",
        "system": "Agricultural system",
        "all": "All",
        "dryland": "Dryland",
        "irrigated_non_pivot": "Irrigated, non-pivot",
        "pivot": "Centre pivot",
        "crops": "Crops and sequences",
        "choose_crops": "Select one or more options",
        "month": "Monthly image",
        "map": "Monthly mosaic and declared crops",
        "chart": "NDVI evolution · 30-day rolling median",
        "chart_key": "Dots: observed medians · lines: centred 30-day rolling median · bands: interquartile range.",
        "phase_yes": "Phases · On",
        "phase_no": "Phases · Off",
        "phase_reference": "Indicative calendar: {crop}",
        "phase_scheme": "Indicative phases",
        "valid_units": "Valid units",
        "no_crop": "Select at least one crop to display its curve.",
        "peak": "Observed peak",
        "amplitude": "Amplitude",
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


@st.cache_data
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, dict, dict]:
    groups = pd.read_csv(DATA_DIR / "groups.csv")
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
    shapes: list[dict] = []
    annotations: list[dict] = []
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
        annotations.append(
            {
                "xref": "x",
                "yref": "paper",
                "x": start + (end - start) / 2,
                "y": 0.985,
                "text": label,
                "textangle": -90 if (end - start).days < 48 else 0,
                "showarrow": False,
                "font": {"size": 9, "color": "#344957"},
                "yanchor": "top",
            }
        )
    return shapes, annotations


def hex_to_rgb(color: str, alpha: int = 118) -> list[int]:
    return [int(color[index:index + 2], 16) for index in (1, 3, 5)] + [alpha]


def feature_subset(units: dict, system: str, selected_groups: list[str]) -> list[dict]:
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
        fill = tuple(hex_to_rgb(color, 112))
        outline = tuple(hex_to_rgb(color, 245))
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
                line={"color": metadata["color"], "width": 3},
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
        "y": 1.01,
        "text": text["selected_month"],
        "showarrow": False,
        "font": {"size": 10, "color": "#344957"},
        "yanchor": "bottom",
    }
    reference_sequence = str(chosen.iloc[0]["crop_sequence"])
    phase_shapes, phase_annotations = phase_chart_layers(reference_sequence, language)
    base_shapes = [month_shape]
    base_annotations = [month_annotation]
    visible_shapes = [*base_shapes, *phase_shapes]
    visible_annotations = [*base_annotations, *phase_annotations]
    tick_dates = pd.date_range("2024-09-01", "2025-10-01", freq="MS")
    tick_labels = [
        f"{MONTHS[language][value.month - 1][:3].capitalize()}<br>{value.year}"
        for value in tick_dates
    ]
    figure.update_layout(
        height=540,
        margin={"l": 18, "r": 18, "t": 70, "b": 16},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#F7F4ED",
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
                "y": 1.16,
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
        legend={"orientation": "h", "y": -0.18, "x": 0, "font": {"size": 11}},
        xaxis={
            "title": None,
            "showgrid": False,
            "range": ["2024-09-01", "2025-10-31"],
            "tickmode": "array",
            "tickvals": tick_dates,
            "ticktext": tick_labels,
            "tickfont": {"color": "#263B49", "size": 11},
            "showline": True,
            "linecolor": "#526574",
            "linewidth": 1.4,
            "ticks": "outside",
            "tickcolor": "#526574",
            "ticklen": 5,
            "automargin": True,
        },
        yaxis={
            "title": {"text": "NDVI", "font": {"color": "#20364B", "size": 14}},
            "range": [0, 1],
            "gridcolor": "rgba(32,54,75,0.15)",
            "zeroline": False,
            "tickfont": {"color": "#263B49", "size": 12},
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
                f'<div class="phenology-meta"><span>Δ {float(row["seasonal_amplitude"]):.2f}</span>'
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
        .stApp { background: #F4F0E7; color: #20364B; }
        [data-testid="stAppDeployButton"] { display:none; }
        .block-container { max-width: 1500px; padding-top: 1.4rem; padding-bottom: 2rem; }
        .hero { padding: .6rem 0 1.1rem; }
        .eyebrow { color:#B06435; font-size:.76rem; font-weight:750; letter-spacing:.16em; }
        .hero h1 { color:#17324B; font-size:clamp(2rem,4vw,3.7rem); line-height:1.02; margin:.28rem 0 .45rem; }
        .hero p { color:#526574; font-size:1.06rem; margin:0; }
        .section-label { color:#17324B; font-size:1.18rem; font-weight:780; letter-spacing:.02em; margin:.55rem 0 .7rem; }
        .phenology-card { background:#FFFCF6; border-radius:14px; border-top:5px solid; padding:18px 19px; margin:.55rem 0; box-shadow:0 5px 20px rgba(32,54,75,.07); }
        .phenology-title { color:#20364B; font-weight:780; font-size:1.08rem; margin-bottom:12px; }
        .phenology-stat { display:flex; justify-content:space-between; gap:12px; font-size:.93rem; color:#445865; padding:2px 0; }
        .phenology-stat strong { color:#1E3443; font-weight:720; }
        .phenology-meta { display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px 14px; color:#465A66; font-size:.88rem; margin-top:11px; padding-top:10px; border-top:1px solid #E4E0D6; }
        .phenology-meta strong { color:#263E4C; font-weight:720; }
        .phase-heading { color:#263E4C; font-size:.85rem; font-weight:740; margin:14px 0 7px; }
        .phase-grid { display:grid; grid-template-columns:1fr; gap:5px; }
        .phase-item { display:grid; grid-template-columns:10px minmax(0,1fr) auto; align-items:center; gap:7px; color:#405561; font-size:.79rem; line-height:1.2; }
        .phase-swatch { width:8px; height:8px; border-radius:50%; }
        .phase-name { font-weight:650; }
        .phase-months { color:#526672; font-size:.76rem; white-space:nowrap; }
        div[data-testid="stMetric"] { background:#FFFCF6; border-radius:12px; padding:10px; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    groups, curves, units, monthly = load_data()

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
    st.markdown(
        f"<div class='hero'><div class='eyebrow'>{text['eyebrow']}</div>"
        f"<h1>{text['title']}</h1><p>{text['subtitle']}</p></div>",
        unsafe_allow_html=True,
    )

    control_system, control_crops, control_month = st.columns([1.0, 2.25, 1.35])
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
    default_ids = [
        identifier
        for identifier in [
            "5-s-dryland-cebada",
            "4-r-irrigated-non-pivot-maiz",
            "4-r-pivot-maiz",
        ]
        if identifier in labels
    ]
    with control_crops:
        selected_groups = st.multiselect(
            text["crops"],
            options=ordered_ids,
            default=default_ids,
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

    colors = groups.set_index("group_id")["color"].to_dict()
    st.markdown(f"<div class='section-label'>{text['map']}</div>", unsafe_allow_html=True)
    aoi_image = build_aoi_image(
        units,
        monthly,
        selected_month,
        system,
        selected_groups,
        colors,
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
            f'{text["chart_key"]} · '
            f'{text["phase_reference"].format(crop=reference_crop)}.'
        )
    else:
        st.info(text["no_crop"])

    render_phenology(groups, selected_groups, language)
    with st.expander(text["about"]):
        st.caption(text["about_text"])


if __name__ == "__main__":
    main()
