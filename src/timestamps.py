"""
Timestamp normalization for the unified ground-truth table.

Source datasets describe *when the data was generated* in heterogeneous free-text forms
("2014 (Chave et al. 2014 GCB)", "2003.0", "2015-10-30/2017-10-29", "2009-2016 (TropiSAR)").
`normalize_timestamp` converts any of these to machine-queryable ISO-8601 bounds plus a
precision flag, so rows can be filtered to an exact date window.
"""

from __future__ import annotations

import calendar
import re
from typing import Dict, Optional

# What the timestamp actually represents, per dataset_source. Anything not listed is "measurement".
TIMESTAMP_BASIS: Dict[str, str] = {
    "Chave_2014_Pantropical_Destructive_Harvest": "publication_year_proxy",  # harvests were 1990s-2000s
    "Zenodo_3977089_Bennett2020": "publication_date_proxy",  # plots measured over many earlier years
    "Zenodo_15622257_Sentinel2_Sentinel1_Field_AGB": "campaign_year",
    "OffsetsDB_Global_Registries": "registry_event_date",
    "CarbonPlan_CARB_Verra_CAR_ACR_IFM_DB": "crediting_period",
    "Zenodo_6992943_FAO_FRA_NFI_vs_ESA_CCI": "reporting_year",
}

_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_ISO_MONTH = re.compile(r"(\d{4})-(\d{2})(?!\d|-)")
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?:\.0)?(?!\d)")


def _bounds(year: int, month: Optional[int], day: Optional[int]) -> tuple[str, str]:
    if month is None:
        return f"{year:04d}-01-01", f"{year:04d}-12-31"
    if day is None:
        return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
    d = f"{year:04d}-{month:02d}-{day:02d}"
    return d, d


def normalize_timestamp(raw: object) -> Dict[str, Optional[str]]:
    """Return {start, end, precision} (ISO dates) parsed from a free-text timestamp."""
    empty = {"start": None, "end": None, "precision": "unknown"}
    if raw is None:
        return empty
    s = str(raw).strip()
    if not s or s.lower() in {"nan", "none"}:
        return empty

    dates = _ISO_DATE.findall(s)
    if dates:
        (y1, m1, d1), (y2, m2, d2) = dates[0], dates[-1]
        start, _ = _bounds(int(y1), int(m1), int(d1))
        end, _ = _bounds(int(y2), int(m2), int(d2))
        return {"start": start, "end": end, "precision": "day" if start == end else "day_range"}

    # Year range, e.g. "2009-2016 (TropiSAR)" -- evaluated before single month/year.
    m = re.match(r"\s*((?:19|20)\d{2})\s*[-–/]\s*((?:19|20)\d{2})", s)
    if m:
        return {"start": f"{m.group(1)}-01-01", "end": f"{m.group(2)}-12-31", "precision": "year_range"}

    m = _ISO_MONTH.search(s)
    if m and 1 <= int(m.group(2)) <= 12:
        start, end = _bounds(int(m.group(1)), int(m.group(2)), None)
        return {"start": start, "end": end, "precision": "month"}

    m = _YEAR.search(s)
    if m:
        start, end = _bounds(int(m.group(1)), None, None)
        return {"start": start, "end": end, "precision": "year"}

    return empty
