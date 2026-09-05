"""CSV loading helpers for normalizing duplicate activity columns."""

from __future__ import annotations

import csv
from collections import defaultdict
from io import BytesIO, StringIO

import pandas as pd

MISSING_TEXT_VALUES = frozenset({"", ".", "-", "--", "n/a", "na", "nan", "none", "null"})


def _read_header(file_bytes: bytes) -> list[str]:
    text = file_bytes.decode("utf-8-sig")
    try:
        raw_header = next(csv.reader(StringIO(text)))
    except StopIteration as error:
        raise ValueError("The CSV file is empty") from error
    if not raw_header:
        raise ValueError("The CSV file is empty")

    return [
        str(name).strip() or f"Unnamed: {position}"
        for position, name in enumerate(raw_header)
    ]


def _meaningful_values(series: pd.Series) -> pd.Series:
    normalized = series.astype("string").str.strip().str.casefold()
    return series.notna() & ~normalized.isin(MISSING_TEXT_VALUES)


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
        candidates.sort(
            key=lambda series: int(_meaningful_values(series).sum()),
            reverse=True,
        )
        combined = pd.Series(pd.NA, index=frame.index, dtype="object")
        for candidate in candidates:
            use_candidate = combined.isna() & _meaningful_values(candidate)
            combined.loc[use_candidate] = candidate.loc[use_candidate]
        numeric_combined = pd.to_numeric(combined, errors="coerce")
        if numeric_combined.notna().sum() == combined.notna().sum():
            combined = numeric_combined
        result[name] = combined

    return pd.DataFrame(result, index=frame.index)


def read_activities_csv(file_bytes: bytes) -> pd.DataFrame:
    """Read CSV bytes and safely coalesce columns with duplicate names."""
    header = _read_header(file_bytes)
    frame = pd.read_csv(BytesIO(file_bytes), encoding="utf-8-sig")
    return coalesce_duplicate_columns(frame, header)
