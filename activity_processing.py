"""Normalize and filter activity data independently of the Streamlit UI."""

from __future__ import annotations

from datetime import date

import pandas as pd

from data_loading import (
    MISSING_TEXT_VALUES,
    coalesce_duplicate_columns,
    nonnegative_measurements,
    read_activity_columns,
)

MAX_UNIT_RELATIVE_ERROR = 0.2
DISTANCE_FACTORS = (1.0, 0.001)
DISTANCE_COLUMNS = ("Distance", "Grade Adjusted Distance")
CLOCK_ONLY = (
    r"\d{1,2}(?::\d{2}(?::\d{2}(?:\.\d+)?)?(?:\s*[ap]\.?m\.?)?|\s*[ap]\.?m\.?)"
    r"(?:\s*(?:Z|[+-]\d{2}(?::?\d{2})?))?"
)


def _meaningful_text(series: pd.Series) -> pd.Series:
    normalized = series.astype("string").str.strip().str.casefold()
    return series.notna() & ~normalized.isin(MISSING_TEXT_VALUES)


def text_series(frame: pd.DataFrame, *names: str, default: str = "") -> pd.Series:
    result = pd.Series(pd.NA, index=frame.index, dtype="string")
    for name in names:
        if name not in frame.columns:
            continue
        candidate = frame[name].astype("string")
        result = result.fillna(candidate.where(_meaningful_text(frame[name])))
    return result.fillna(default).str.strip()


def numeric_series(frame: pd.DataFrame, *names: str) -> pd.Series:
    result = pd.Series(float("nan"), index=frame.index, dtype="float64")
    for name in names:
        if name not in frame.columns:
            continue
        result = result.fillna(pd.to_numeric(frame[name], errors="coerce"))
    return result.replace([float("inf"), float("-inf")], float("nan"))


def nonnegative_series(frame: pd.DataFrame, *names: str) -> pd.Series:
    """Return finite numeric values, treating negative domain values as missing."""
    result = pd.Series(float("nan"), index=frame.index, dtype="float64")
    for name in names:
        if name not in frame.columns:
            continue
        result = result.fillna(nonnegative_measurements(frame[name]))
    return result


def effective_speed_series(
    activities: pd.DataFrame,
    *,
    exported_speed: pd.Series | None = None,
) -> pd.Series:
    """Return one usable km/h speed per row, deriving it when necessary."""
    index = activities.index
    missing = pd.Series(float("nan"), index=index, dtype="float64")
    exported_source = (
        exported_speed.reindex(index)
        if exported_speed is not None
        else activities.get("_avg_speed_kmh", missing)
    )
    exported = pd.to_numeric(
        exported_source, errors="coerce"
    )
    distance = pd.to_numeric(
        activities.get("_distance_km", missing), errors="coerce"
    )
    moving = pd.to_numeric(
        activities.get("_moving_hours", missing), errors="coerce"
    )

    exported = exported.where(exported.ge(0) & exported.lt(float("inf")))
    derived = distance.div(moving).where(
        distance.ge(0)
        & distance.lt(float("inf"))
        & moving.gt(0)
        & moving.lt(float("inf"))
    )
    return exported.fillna(derived)


def datetime_series(frame: pd.DataFrame, *names: str, require_time: bool = False) -> pd.Series:
    result = pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    for name in names:
        if name not in frame.columns:
            continue
        values = frame[name]
        text = values.astype("string").str.strip()
        if require_time:
            has_time = text.str.contains(
                r"\d{1,2}:\d{2}|\d{1,2}\s*[ap]\.?m\b|T\d{2}", case=False, na=False
            )
            values = values.where(has_time)
        else:
            values = values.mask(text.str.fullmatch(CLOCK_ONLY, case=False, na=False))
        parsed = values.map(_parse_local_datetime).astype("datetime64[ns]")
        result = result.fillna(parsed)
    return result


def _parse_local_datetime(value) -> pd.Timestamp:
    """Parse one timestamp while preserving its recorded local calendar values."""
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except (TypeError, ValueError, OverflowError):
        return pd.NaT
    if pd.isna(parsed):
        return pd.NaT
    timestamp = pd.Timestamp(parsed)
    return timestamp.tz_localize(None) if timestamp.tzinfo is not None else timestamp


def _infer_unit_factors(
    distance: pd.Series,
    moving_hours: pd.Series,
    raw_speed: pd.Series,
    *,
    detailed_export: bool = False,
    summary_export: bool = False,
    distance_factors: tuple[float, ...] = DISTANCE_FACTORS,
) -> tuple[float, float, bool]:
    paired = distance.notna() & distance.gt(0) & moving_hours.gt(0) & raw_speed.gt(0)
    if paired.any():
        best_error = float("inf")
        best_factors = (1.0, 1.0)
        for distance_factor in distance_factors:
            implied_speed = distance[paired] * distance_factor / moving_hours[paired]
            for speed_factor in (1.0, 3.6):
                candidate_speed = raw_speed[paired] * speed_factor
                relative_error = ((candidate_speed - implied_speed).abs() / implied_speed).median()
                if relative_error < best_error:
                    best_error = float(relative_error)
                    best_factors = (distance_factor, speed_factor)
        return *best_factors, best_error <= MAX_UNIT_RELATIVE_ERROR

    if detailed_export:
        return 0.001, 3.6, False
    if summary_export:
        return 1.0, 1.0, False

    known_distances = distance.dropna()
    distance_factor = (
        0.001 if not known_distances.empty and known_distances.median() > 500 else 1.0
    )
    return distance_factor, 1.0, False


def _normalize_distance_columns(
    columns: pd.DataFrame,
    moving_hours: pd.Series,
    raw_speed: pd.Series,
    default_factor: float,
) -> tuple[pd.Series, bool]:
    candidates = []
    for name in DISTANCE_COLUMNS:
        measurements = columns.loc[:, columns.columns == name]
        candidates.extend(sorted(
            (nonnegative_measurements(column) for _, column in measurements.items()),
            key=lambda column: int(column.count()),
            reverse=True,
        ))
    preferred = candidates[0]

    factors = []
    for candidate in candidates:
        factor, _, verified = _infer_unit_factors(candidate, moving_hours, raw_speed)
        factors.append(factor if verified else None)

    # Positive overlaps can identify metre/kilometre pairs even without speed data.
    relative_factors = []
    for candidate in candidates:
        overlap = preferred.gt(0) & candidate.gt(0)
        ratio = (preferred[overlap] / candidate[overlap]).median() if overlap.any() else None
        relative_factors.append(next((
            factor for factor in (1.0, 0.001, 1000.0)
            if ratio is not None and abs(ratio / factor - 1) <= MAX_UNIT_RELATIVE_ERROR
        ), None))

    preferred_factor = factors[0]
    if preferred_factor is None:
        for factor, relative in zip(factors, relative_factors):
            if relative == 1.0 and factor is not None:
                preferred_factor = factor
            elif relative == 0.001:
                preferred_factor = 1.0
            elif relative == 1000.0:
                preferred_factor = 0.001
            if preferred_factor is not None:
                break

    distances = pd.Series(float("nan"), index=columns.index, dtype="float64")
    contributors = 0
    assumed_units = False
    for candidate, factor, relative in zip(candidates, factors, relative_factors):
        if factor is None and preferred_factor is not None and relative is not None:
            inferred = preferred_factor * relative
            if inferred in DISTANCE_FACTORS:
                factor = inferred
        if (distances.isna() & candidate.gt(0)).any():
            contributors += 1
            assumed_units |= factor is None
        distances = distances.fillna(candidate * (factor or preferred_factor or default_factor))
    return distances, contributors > 1 and assumed_units


def prepare_activities(file_bytes: bytes) -> pd.DataFrame:
    """Read exported activities and add the normalized fields used by the report."""
    columns = read_activity_columns(file_bytes)
    frame = coalesce_duplicate_columns(columns, list(columns.columns))

    frame["_date"] = datetime_series(frame, "Activity Date", "Start Time", "Date")
    frame["_start_hour"] = datetime_series(
        frame, "Start Time", "Activity Date", "Date", require_time=True
    ).dt.hour

    frame["_type"] = text_series(frame, "Activity Type", "Type", default="Unknown")
    canonical_types = {"ride": "Ride", "run": "Run", "walk": "Walk"}
    frame["_type"] = frame["_type"].map(
        lambda value: canonical_types.get(value.casefold(), value)
    )
    frame["_name"] = text_series(frame, "Activity Name", "Name")
    frame["_series"] = (
        frame["_name"].str.replace(r"\s*\[[^\]]+\]\s*$", "", regex=True).str.strip()
    )
    frame["_gear"] = text_series(frame, "Activity Gear", "Gear")

    distance = nonnegative_series(frame, *DISTANCE_COLUMNS)
    moving_seconds = nonnegative_series(frame, "Moving Time", "Timer Time", "Elapsed Time")
    moving_hours = moving_seconds / 3600
    frame["_moving_hours"] = moving_hours

    raw_speed = nonnegative_series(frame, "Average Speed")
    detailed_export = "Activity ID" in frame.columns or "Filename" in frame.columns
    summary_export = not detailed_export and any(
        name in frame.columns for name in ("Date", "Name", "Gear")
    )
    distance_factor, speed_factor, units_verified = _infer_unit_factors(
        distance,
        moving_hours,
        raw_speed,
        detailed_export=detailed_export,
        summary_export=summary_export,
    )
    distance_km = distance * distance_factor
    distance_columns = columns.loc[:, columns.columns.isin(DISTANCE_COLUMNS)]
    assumed_distance_units = False
    if distance_columns.shape[1] > 1:
        distance_km, assumed_distance_units = _normalize_distance_columns(
            distance_columns, moving_hours, raw_speed, distance_factor
        )
        _, speed_factor, units_verified = _infer_unit_factors(
            distance_km, moving_hours, raw_speed,
            detailed_export=detailed_export,
            summary_export=summary_export,
            distance_factors=(1.0,),
        )
    frame["_distance_km"] = distance_km
    normalized_speed = raw_speed * speed_factor
    frame["_avg_speed_kmh"] = effective_speed_series(
        frame,
        exported_speed=normalized_speed,
    )

    mappings = {
        "_elevation_m": "Elevation Gain",
        "_calories": "Calories",
        "_avg_hr": "Average Heart Rate",
        "_avg_watts": "Average Watts",
        "_relative_effort": "Relative Effort",
    }
    for internal, source in mappings.items():
        frame[internal] = nonnegative_series(frame, source)

    has_unit_evidence = (distance.gt(0) & moving_hours.gt(0) & raw_speed.gt(0)).any()
    if assumed_distance_units:
        frame.attrs["unit_inference_warning"] = (
            "Units could not be verified for all distance columns. "
            "Check the CSV units before relying on distance or speed totals."
        )
    elif has_unit_evidence and not units_verified:
        frame.attrs["unit_inference_warning"] = (
            "Distance, duration, and speed disagree under the supported unit conventions. "
            "Check the CSV units and recorded values before relying on this report."
        )
    elif not detailed_export and not summary_export and not units_verified:
        frame.attrs["unit_inference_warning"] = (
            "Distance and speed units could not be verified from the available columns. "
            "The report inferred them from the recorded values."
        )
    return frame


def filter_activities(
    activities: pd.DataFrame,
    date_from: date | None,
    date_to: date | None,
    name_search: str,
    series: list[str],
    activity_type: str | None,
    distance_min: float,
    distance_max: float,
    gears: list[str],
    speed_min: float,
    speed_max: float,
) -> pd.DataFrame:
    """Apply the page filters and return a cleanly indexed result."""
    filtered = activities.copy()
    if date_from is not None or date_to is not None:
        dates = activities["_date"].dt.date
        known_dates = dates.dropna()
        date_mask = pd.Series(True, index=activities.index)
        if date_from is not None:
            date_mask &= dates >= date_from
        if date_to is not None:
            date_mask &= dates <= date_to
        unrestricted_dates = not known_dates.empty
        if date_from is not None:
            unrestricted_dates &= date_from <= known_dates.min()
        if date_to is not None:
            unrestricted_dates &= date_to >= known_dates.max()
        if unrestricted_dates:
            date_mask |= dates.isna()
        filtered = filtered[date_mask.loc[filtered.index]]
    if name_search.strip():
        filtered = filtered[
            filtered["_name"].str.contains(
                name_search.strip(), case=False, na=False, regex=False
            )
        ]
    if series:
        filtered = filtered[filtered["_series"].isin(series)]
    if activity_type:
        filtered = filtered[filtered["_type"] == activity_type]
    else:
        filtered = filtered.iloc[0:0]
    known_distances = activities["_distance_km"].dropna()
    distance_mask = activities["_distance_km"].between(distance_min, distance_max)
    unrestricted_distance = known_distances.empty or (
        distance_min <= known_distances.min() and distance_max >= known_distances.max()
    )
    if unrestricted_distance:
        distance_mask |= activities["_distance_km"].isna()
    filtered = filtered[distance_mask.loc[filtered.index]]
    if gears:
        filtered = filtered[filtered["_gear"].isin(gears)]
    effective_speeds = effective_speed_series(activities)
    known_speeds = effective_speeds.dropna()
    speed_mask = effective_speeds.between(speed_min, speed_max)
    unrestricted_speed = known_speeds.empty or (
        speed_min <= known_speeds.min() and speed_max >= known_speeds.max()
    )
    if unrestricted_speed:
        speed_mask |= effective_speeds.isna()
    filtered = filtered[speed_mask.loc[filtered.index]]
    return filtered.reset_index(drop=True)
