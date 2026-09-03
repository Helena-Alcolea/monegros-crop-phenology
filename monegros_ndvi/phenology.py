"""Approximate crop calendars used by the portfolio interface.

The windows are visual guidance, not parcel-level observations. Sowing and
harvest periods follow official calendars for Huesca and an Aragonese study of
double-cropping in Monegros; intermediate stages are agronomic approximations
between those anchors.
"""

from __future__ import annotations


PHASE_COLORS = {
    "sowing": "#9A6A3A",
    "establishment": "#9BAE65",
    "growth": "#4C9B68",
    "reproductive": "#D6A63B",
    "maturity": "#C9783F",
    "harvest": "#795548",
    "dormancy": "#85929B",
    "management": "#A67855",
}


def _phase(
    start: str,
    end: str,
    phase_type: str,
    label_es: str,
    label_en: str,
) -> dict[str, str]:
    return {
        "start": start,
        "end": end,
        "phase_type": phase_type,
        "label_es": label_es,
        "label_en": label_en,
        "color": PHASE_COLORS[phase_type],
    }


WINTER_CEREAL = [
    _phase("2024-10-01", "2024-12-31", "sowing", "Siembra y nascencia", "Sowing and emergence"),
    _phase("2025-01-01", "2025-02-28", "establishment", "Ahijado", "Tillering"),
    _phase("2025-03-01", "2025-04-30", "growth", "Crecimiento y espigado", "Growth and heading"),
    _phase("2025-05-01", "2025-05-31", "maturity", "Maduración", "Ripening"),
    _phase("2025-06-01", "2025-07-15", "harvest", "Cosecha", "Harvest"),
]

GRAIN_LEGUME = [
    _phase("2024-10-15", "2024-12-31", "sowing", "Siembra y nascencia", "Sowing and emergence"),
    _phase("2025-01-01", "2025-02-28", "establishment", "Implantación", "Establishment"),
    _phase("2025-03-01", "2025-04-30", "growth", "Crecimiento y floración", "Growth and flowering"),
    _phase("2025-05-01", "2025-06-30", "harvest", "Maduración y cosecha", "Ripening and harvest"),
]

MAIZE = [
    _phase("2025-04-01", "2025-05-31", "sowing", "Siembra y nascencia", "Sowing and emergence"),
    _phase("2025-06-01", "2025-07-15", "growth", "Crecimiento vegetativo", "Vegetative growth"),
    _phase("2025-07-16", "2025-09-15", "reproductive", "Floración y llenado", "Flowering and grain fill"),
    _phase("2025-09-16", "2025-10-31", "harvest", "Maduración y cosecha", "Ripening and harvest"),
]

PERMANENT_GRASS = [
    _phase("2024-09-01", "2024-10-31", "growth", "Rebrote otoñal", "Autumn regrowth"),
    _phase("2024-11-01", "2025-02-28", "dormancy", "Reposo invernal", "Winter dormancy"),
    _phase("2025-03-01", "2025-05-31", "growth", "Crecimiento primaveral", "Spring growth"),
    _phase("2025-06-01", "2025-08-31", "harvest", "Siega o pastoreo", "Cutting or grazing"),
    _phase("2025-09-01", "2025-10-31", "growth", "Rebrote otoñal", "Autumn regrowth"),
]


CROP_CALENDARS: dict[str, list[dict[str, str]]] = {
    "Barbecho tradicional": [
        _phase("2024-09-01", "2025-02-28", "dormancy", "Reposo y cubierta", "Rest and ground cover"),
        _phase("2025-03-01", "2025-05-31", "growth", "Vegetación espontánea", "Spontaneous vegetation"),
        _phase("2025-06-01", "2025-08-31", "management", "Control de cubierta", "Ground-cover control"),
        _phase("2025-09-01", "2025-10-31", "management", "Preparación del suelo", "Soil preparation"),
    ],
    "Cebada": WINTER_CEREAL,
    "Trigo blando": WINTER_CEREAL,
    "Triticale": WINTER_CEREAL,
    "Guisante": GRAIN_LEGUME,
    "Veza": GRAIN_LEGUME,
    "Yeros": GRAIN_LEGUME,
    "Maíz": MAIZE,
    "Pastos permanentes de 5 o más años": PERMANENT_GRASS,
    "Festuca": PERMANENT_GRASS,
    "Alfalfa": [
        _phase("2024-09-01", "2024-10-31", "growth", "Rebrote otoñal", "Autumn regrowth"),
        _phase("2024-11-01", "2025-02-28", "dormancy", "Reposo invernal", "Winter dormancy"),
        _phase("2025-03-01", "2025-04-30", "growth", "Rebrote primaveral", "Spring regrowth"),
        _phase("2025-05-01", "2025-09-30", "harvest", "Cortes y rebrotes", "Cuts and regrowth"),
        _phase("2025-10-01", "2025-10-31", "maturity", "Declive otoñal", "Autumn decline"),
    ],
    "Cebada → Maíz": [
        _phase("2024-10-01", "2024-11-30", "sowing", "Siembra de cebada", "Barley sowing"),
        _phase("2024-12-01", "2025-05-31", "growth", "Ciclo de cebada", "Barley cycle"),
        _phase("2025-06-01", "2025-06-30", "sowing", "Cosecha y siembra de maíz", "Harvest and maize sowing"),
        _phase("2025-07-01", "2025-08-31", "growth", "Crecimiento del maíz", "Maize growth"),
        _phase("2025-09-01", "2025-09-30", "reproductive", "Llenado del grano", "Grain fill"),
        _phase("2025-10-01", "2025-10-31", "harvest", "Cosecha de maíz", "Maize harvest"),
    ],
    "Guisante → Maíz": [
        _phase("2024-11-01", "2025-01-15", "sowing", "Siembra de guisante", "Pea sowing"),
        _phase("2025-01-16", "2025-05-31", "growth", "Ciclo de guisante", "Pea cycle"),
        _phase("2025-06-01", "2025-06-30", "sowing", "Cosecha y siembra de maíz", "Harvest and maize sowing"),
        _phase("2025-07-01", "2025-08-31", "growth", "Crecimiento del maíz", "Maize growth"),
        _phase("2025-09-01", "2025-10-31", "harvest", "Llenado y cosecha", "Grain fill and harvest"),
    ],
    "Veza → Maíz": [
        _phase("2024-10-15", "2024-12-31", "sowing", "Siembra de veza", "Vetch sowing"),
        _phase("2025-01-01", "2025-05-31", "growth", "Ciclo de veza", "Vetch cycle"),
        _phase("2025-06-01", "2025-06-30", "sowing", "Cosecha y siembra de maíz", "Harvest and maize sowing"),
        _phase("2025-07-01", "2025-08-31", "growth", "Crecimiento del maíz", "Maize growth"),
        _phase("2025-09-01", "2025-10-31", "harvest", "Llenado y cosecha", "Grain fill and harvest"),
    ],
}


def calendar_for(sequence: str) -> list[dict[str, str]]:
    """Return the approximate phase calendar for a declared crop sequence."""
    return CROP_CALENDARS.get(sequence, [])

