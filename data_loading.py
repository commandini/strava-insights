"""CSV loading helpers for normalizing duplicate activity columns."""

from __future__ import annotations

import csv
from collections import defaultdict
from io import BytesIO, TextIOWrapper

import pandas as pd

MISSING_TEXT_VALUES = frozenset({"", ".", "-", "--", "n/a", "na", "nan", "none", "null"})
MEASUREMENT_COLUMNS = frozenset({
    "Distance", "Grade Adjusted Distance", "Moving Time", "Timer Time", "Elapsed Time",
    "Average Speed", "Elevation Gain", "Calories", "Average Heart Rate", "Average Watts",
    "Relative Effort",
})


def _read_header(file_bytes: bytes) -> list[str]:
    with TextIOWrapper(BytesIO(file_bytes), encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        raw_header = next(reader, None)
        if not raw_header:
            raise ValueError("The CSV file is empty")

    return [
        str(name).strip() or f"Unnamed: {position}"
        for position, name in enumerate(raw_header)
    ]


def _meaningful_values(series: pd.Series) -> pd.Series:
    normalized = series.astype("string").str.strip().str.casefold()
    return series.notna() & ~normalized.isin(MISSING_TEXT_VALUES)


def nonnegative_measurements(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.where(values.ge(0) & values.lt(float("inf")))


def coalesce_duplicate_columns(frame: pd.DataFrame, header: list[str]) -> pd.DataFrame:
    """Collapse duplicate headers, selecting the best available value for each row."""
    if len(header) != len(frame.columns):
        raise ValueError(
            "The parsed CSV header does not match the number of data columns "
            f"({len(header)} headers, {len(frame.columns)} columns)"
        )

    positions_by_name: dict[str, list[int]] = defaultdict(list)
    for position, name in enumerate(header):
        positions_by_name[name].append(position)

    result: dict[str, pd.Series] = {}
    for name, positions in positions_by_name.items():
        if len(positions) == 1:
            result[name] = frame.iloc[:, positions[0]]
            continue

        candidates = [frame.iloc[:, position] for position in positions]
        if name in MEASUREMENT_COLUMNS:
            candidates = [nonnegative_measurements(candidate) for candidate in candidates]
        else:
            candidates = [
                candidate.where(_meaningful_values(candidate)) for candidate in candidates
            ]
        candidates.sort(key=lambda series: int(series.count()), reverse=True)
        combined = pd.Series(pd.NA, index=frame.index, dtype="object")
        for candidate in candidates:
            use_candidate = combined.isna() & candidate.notna()
            combined.loc[use_candidate] = candidate.loc[use_candidate]
        numeric_combined = pd.to_numeric(combined, errors="coerce")
        if numeric_combined.notna().sum() == combined.notna().sum():
            combined = numeric_combined
        result[name] = combined

    return pd.DataFrame(result, index=frame.index)


def read_activity_columns(file_bytes: bytes) -> pd.DataFrame:
    """Read CSV columns in file order, preserving duplicate headers."""
    header = _read_header(file_bytes)
    # The header fixes the width when read as a record, preventing implicit index inference.
    pd.read_csv(BytesIO(file_bytes), encoding="utf-8-sig", header=None, nrows=2, dtype=str)
    frame = pd.read_csv(BytesIO(file_bytes), encoding="utf-8-sig")
    frame.columns = header
    return frame


def read_activities_csv(file_bytes: bytes) -> pd.DataFrame:
    """Read CSV bytes and safely coalesce columns with duplicate names."""
    frame = read_activity_columns(file_bytes)
    return coalesce_duplicate_columns(frame, list(frame.columns))
