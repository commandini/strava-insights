from __future__ import annotations

import math
from functools import partial
from html import escape
from io import BytesIO
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    CondPageBreak,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from activity_processing import datetime_series, effective_speed_series
from theme import APP_FONT_CSS, APP_FONT_FAMILY, DEFAULT_BACKGROUND_RGB

NAVY = "#14213D"
AXIS_GRID = "#E1E7EF"
MIN_COVERAGE = 0.20
SPEED_DISTRIBUTION_BAR_SIZE = 20
PDF_SPEED_DISTRIBUTION_BAR_RATIO = 0.34
PDF_TABLE_FONT_SIZE = 7.5
PDF_BODY_FONT_SIZE = 8.5
PDF_SECTION_FONT_SIZE = 14
PDF_SUBSECTION_FONT_SIZE = 11
PDF_METRIC_LABEL_FONT_SIZE = PDF_TABLE_FONT_SIZE
PDF_METRIC_VALUE_FONT_SIZE = 14
CALENDAR_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CALENDAR_MONTH_WEEKS = {
    0: "Jan",
    4: "Feb",
    8: "Mar",
    13: "Apr",
    17: "May",
    21: "Jun",
    26: "Jul",
    30: "Aug",
    34: "Sep",
    39: "Oct",
    43: "Nov",
    47: "Dec",
}


def _register_pdf_fonts() -> tuple[str, str]:
    avenir_collections = (
        Path("/System/Library/Fonts/Avenir.ttc"),
        Path("/Library/Fonts/Avenir.ttc"),
        Path.home() / "Library/Fonts/Avenir.ttc",
    )
    for font_path in avenir_collections:
        if not font_path.is_file():
            continue
        try:
            regular_name = f"{APP_FONT_FAMILY}-PDF"
            bold_name = f"{APP_FONT_FAMILY}-PDF-Bold"
            pdfmetrics.registerFont(TTFont(
                regular_name,
                str(font_path),
                subfontIndex=0,
            ))
            pdfmetrics.registerFont(TTFont(
                bold_name,
                str(font_path),
                subfontIndex=4,
            ))
            pdfmetrics.registerFontFamily(
                regular_name,
                normal=regular_name,
                bold=bold_name,
                italic=regular_name,
                boldItalic=bold_name,
            )
            return regular_name, bold_name
        except Exception:
            continue
    return "Helvetica", "Helvetica-Bold"


PDF_FONT_REGULAR, PDF_FONT_BOLD = _register_pdf_fonts()


def format_hours(hours: float) -> str:
    if pd.isna(hours) or not math.isfinite(float(hours)):
        return "-"
    minutes = round(max(hours, 0) * 60)
    return f"{minutes // 60}h {minutes % 60:02d}m"


def format_pace(speed_kmh: float) -> str:
    if pd.isna(speed_kmh) or not math.isfinite(float(speed_kmh)) or speed_kmh <= 0:
        return "-"
    seconds = round(3600 / speed_kmh)
    return f"{seconds // 60}:{seconds % 60:02d} min/km"


def format_number(value: float, decimals: int = 1) -> str:
    return (
        "-"
        if pd.isna(value) or not math.isfinite(float(value))
        else f"{value:.{decimals}f}"
    )


def valid_measurements(
    frame: pd.DataFrame,
    column: str,
    *,
    positive: bool = False,
) -> pd.Series:
    """Return finite, domain-valid measurements without changing row identity."""
    if column not in frame:
        return pd.Series(float("nan"), index=frame.index, dtype="float64")
    values = pd.to_numeric(frame[column], errors="coerce").replace(
        [float("inf"), float("-inf")], float("nan")
    )
    return values.where(values.gt(0) if positive else values.ge(0))


def coverage(frame: pd.DataFrame, column: str) -> float:
    return float(valid_measurements(frame, column).notna().mean()) if len(frame) else 0.0


def display_date(value) -> str:
    return value.strftime("%d %b %Y") if pd.notna(value) else "Unknown date"


def left_aligned_number_column(format_string: str):
    config = st.column_config.NumberColumn(format=format_string)
    config["alignment"] = "left"
    return config


def overall_average_speed(frame: pd.DataFrame) -> float:
    distance = valid_measurements(frame, "_distance_km")
    moving_hours = valid_measurements(frame, "_moving_hours", positive=True)
    valid = distance.notna() & moving_hours.notna()
    moving = moving_hours[valid].sum(min_count=1)
    return (
        float(distance[valid].sum(min_count=1) / moving)
        if pd.notna(moving) and moving > 0
        else float("nan")
    )


def build_performance_row(group: pd.DataFrame, activity_type: str) -> dict:
    distances = valid_measurements(group, "_distance_km")
    moving_hours = valid_measurements(group, "_moving_hours")
    elevations = valid_measurements(group, "_elevation_m")
    heart_rates = valid_measurements(group, "_avg_hr")
    powers = valid_measurements(group, "_avg_watts")
    distance = distances.sum(min_count=1)
    moving = moving_hours.sum(min_count=1)
    weighted_speed = overall_average_speed(group)
    row = {
        "Activity count": len(group),
        "Distance (km)": round(distance, 1),
        "Moving time (h)": round(moving, 1),
        "Average distance (km)": round(distances.mean(), 1),
        "Elevation gain (m)": round(elevations.sum(min_count=1), 0),
        "Overall average speed (km/h)": round(weighted_speed, 1),
        "Average heart rate (bpm)": "-",
        "Average power (W)": "-",
        "Average pace (min/km)": "-",
    }
    if activity_type in {"Run", "Walk"}:
        row["Average pace (min/km)"] = format_pace(weighted_speed).replace(" min/km", "")
    if coverage(group, "_avg_hr") >= MIN_COVERAGE:
        row["Average heart rate (bpm)"] = f"{heart_rates.mean():.0f}"
    if activity_type == "Ride" and coverage(group, "_avg_watts") >= MIN_COVERAGE:
        row["Average power (W)"] = f"{powers.mean():.0f}"
    return row


def build_summary_metrics(activities: pd.DataFrame) -> list[dict]:
    activity_types = activities["_type"].dropna().unique()
    activity_type = str(activity_types[0]) if len(activity_types) == 1 else "Unknown"
    performance = build_performance_row(activities, activity_type)
    return [
        {"label": "Activity count", "value": str(len(activities))},
        {
            "label": "Distance (km)",
            "value": format_number(performance["Distance (km)"], 1),
        },
        {
            "label": "Moving time (h)",
            "value": format_number(performance["Moving time (h)"], 1),
        },
        {
            "label": "Average distance (km)",
            "value": format_number(performance["Average distance (km)"], 1),
        },
        {
            "label": "Elevation gain (m)",
            "value": format_number(performance["Elevation gain (m)"], 0),
        },
        {
            "label": "Average speed (km/h)",
            "value": format_number(performance["Overall average speed (km/h)"], 1),
        },
        {"label": "Average power (W)", "value": performance["Average power (W)"]},
        {
            "label": "Average pace (min/km)",
            "value": performance["Average pace (min/km)"],
        },
    ]


def build_speed_distribution_coverage(activities: pd.DataFrame) -> dict:
    available = int(effective_speed_series(activities).notna().sum())
    total = len(activities)
    return {
        "available": available,
        "total": total,
        "label": (
            f"Distribution includes {available} of {total} activities "
            "with usable speed data."
        ),
    }


def build_speed_distribution(activities: pd.DataFrame) -> pd.DataFrame:
    speeds = effective_speed_series(activities).dropna()
    if speeds.empty:
        return pd.DataFrame(
            columns=["Range", "Definition", "Activity count", "Distance (km)"]
        )

    missing_distance = pd.Series(
        float("nan"), index=activities.index, dtype="float64"
    )
    distances = pd.to_numeric(
        activities.get("_distance_km", missing_distance), errors="coerce"
    )
    distances = distances.where(distances.ge(0) & distances.lt(float("inf")))

    buckets = [
        ("<10", "<10", speeds < 10),
        *[
            (
                f"[{lower},{lower + 2})",
                f"[{lower},{lower + 2})",
                speeds.ge(lower) & speeds.lt(lower + 2),
            )
            for lower in range(10, 40, 2)
        ],
        (">=40", "x >= 40", speeds >= 40),
    ]
    return pd.DataFrame([
        {
            "Range": label,
            "Definition": definition,
            "Activity count": int(mask.sum()),
            "Distance (km)": round(
                distances.loc[mask.index][mask].sum(min_count=1), 1
            ),
        }
        for label, definition, mask in buckets
    ])


def build_calendar_heatmap(activities: pd.DataFrame) -> pd.DataFrame:
    """Aggregate activities by Gregorian month/day on a leap-year scaffold."""
    calendar = pd.DataFrame({
        "_calendar_date": pd.date_range("2024-01-01", "2024-12-31", freq="D")
    })
    activity_dates = datetime_series(activities, "_date")
    activity_counts = activity_dates.dt.strftime("%m-%d").value_counts()

    calendar["_key"] = calendar["_calendar_date"].dt.strftime("%m-%d")
    calendar["Calendar day"] = (
        calendar["_calendar_date"].dt.strftime("%B ")
        + calendar["_calendar_date"].dt.day.astype(str)
    )
    calendar["Activity count"] = (
        calendar["_key"].map(activity_counts).fillna(0).astype(int)
    )
    calendar["Week"] = (
        (calendar["_calendar_date"].dt.dayofyear - 1) // 7
    ).astype(int)
    calendar["Weekday"] = calendar["_calendar_date"].dt.day_name().str[:3]
    calendar["Is peak"] = False
    maximum = int(calendar["Activity count"].max())
    if maximum > 0:
        peak_index = calendar.index[calendar["Activity count"].eq(maximum)][0]
        calendar.loc[peak_index, "Is peak"] = True
    return calendar[[
        "Calendar day", "Activity count", "Week", "Weekday", "Is peak"
    ]]


def build_hourly_heatmap(activities: pd.DataFrame) -> pd.DataFrame:
    """Aggregate activity start times into a fixed 24-hour scaffold."""
    hours = pd.DataFrame({"Hour": range(24)})
    start_times = datetime_series(activities, "_date")
    activity_counts = start_times.dt.hour.value_counts()

    hours["Hour label"] = hours["Hour"].map(lambda hour: f"{hour:02d}")
    hours["Start hour"] = hours["Hour"].map(
        lambda hour: f"{hour:02d}:00-{hour + 1:02d}:00"
    )
    hours["Activity count"] = (
        hours["Hour"].map(activity_counts).fillna(0).astype(int)
    )
    hours["Row"] = "Activities"
    hours["Is peak"] = False
    maximum = int(hours["Activity count"].max())
    if maximum > 0:
        peak_index = hours.index[hours["Activity count"].eq(maximum)][0]
        hours.loc[peak_index, "Is peak"] = True
    return hours[[
        "Hour", "Hour label", "Start hour", "Activity count", "Row", "Is peak"
    ]]


def build_monthly_performance(
    activities: pd.DataFrame,
    date_from=None,
    date_to=None,
) -> list[dict]:
    dated = activities.dropna(subset=["_date"])
    range_start = pd.Timestamp(date_from) if date_from is not None else dated["_date"].min()
    range_end = pd.Timestamp(date_to) if date_to is not None else dated["_date"].max()
    if pd.isna(range_start) or pd.isna(range_end):
        return []

    activity_types = activities["_type"].dropna().unique()
    activity_type = str(activity_types[0]) if len(activity_types) else "Unknown"
    months = pd.period_range(range_start.to_period("M"), range_end.to_period("M"), freq="M")
    activity_months = activities["_date"].dt.to_period("M")
    monthly = []
    for month in months:
        group = activities[activity_months == month]
        row = build_performance_row(group, activity_type)
        row = {
            "Average speed (km/h)" if key == "Overall average speed (km/h)" else key: value
            for key, value in row.items()
        }
        if group.empty:
            row.update({
                "Distance (km)": 0.0,
                "Moving time (h)": 0.0,
                "Elevation gain (m)": 0.0,
            })
        monthly.append({"Month": month.to_timestamp().strftime("%B %Y"), **row})
    return monthly


def build_yearly_statistics(
    activities: pd.DataFrame,
    date_from=None,
    date_to=None,
) -> pd.DataFrame:
    dated = activities.dropna(subset=["_date"])
    range_start = pd.Timestamp(date_from) if date_from is not None else dated["_date"].min()
    range_end = pd.Timestamp(date_to) if date_to is not None else dated["_date"].max()
    if pd.isna(range_start) or pd.isna(range_end):
        return pd.DataFrame(columns=["Year", "Distance (km)"])

    dated = dated.assign(
        _year=dated["_date"].dt.year,
        _valid_distance_km=valid_measurements(dated, "_distance_km"),
        _valid_moving_hours=valid_measurements(dated, "_moving_hours", positive=True),
    )
    distance_by_year = (
        dated.groupby("_year")["_valid_distance_km"]
        .sum(min_count=1)
    )
    paired = dated[
        dated["_valid_distance_km"].notna()
        & dated["_valid_moving_hours"].notna()
        ]
    paired_distance_by_year = (
        paired.groupby("_year")["_valid_distance_km"]
        .sum(min_count=1)
    )
    paired_time_by_year = (
        paired
        .groupby("_year")["_valid_moving_hours"]
        .sum(min_count=1)
    )
    years = list(range(range_start.year, range_end.year + 1))
    activity_counts = (
        dated.groupby("_year")
        .size()
        .reindex(years, fill_value=0)
    )
    distance_totals = distance_by_year.reindex(years)
    paired_distance_totals = paired_distance_by_year.reindex(years)
    paired_time_totals = paired_time_by_year.reindex(years)
    yearly_speed = paired_distance_totals / paired_time_totals.where(paired_time_totals > 0)
    return pd.DataFrame({
        "Year": [str(year) for year in years],
        "Distance (km)": [
            0.0
            if activity_counts.loc[year] == 0
            else (
                round(float(distance_totals.loc[year]), 1)
                if pd.notna(distance_totals.loc[year])
                else float("nan")
            )
            for year in years
        ],
        "Overall average speed (km/h)": [
            round(float(yearly_speed.loc[year]), 1) if pd.notna(yearly_speed.loc[year]) else float("nan")
            for year in years
        ],
    })


def _year_axis() -> alt.Axis:
    return alt.Axis(
        domain=True,
        domainColor=NAVY,
        domainWidth=1,
        labelAngle=0,
        labelColor=NAVY,
        labelFont=APP_FONT_CSS,
        labelFontSize=11,
        labelOverlap=False,
        labelPadding=8,
        labels=True,
        tickColor=NAVY,
        tickWidth=1,
        ticks=True,
        title=None,
    )


def _value_axis(title: str, number_format: str) -> alt.Axis:
    return alt.Axis(
        domain=True,
        domainColor=NAVY,
        domainWidth=1,
        format=number_format,
        grid=True,
        gridColor=AXIS_GRID,
        labelColor=NAVY,
        labelFont=APP_FONT_CSS,
        labelFontSize=11,
        labelPadding=6,
        labels=True,
        tickColor=NAVY,
        tickCount=6,
        tickWidth=1,
        ticks=True,
        title=title,
        titleColor=NAVY,
        titleFont=APP_FONT_CSS,
        titleFontSize=12,
        titlePadding=10,
    )


def build_yearly_distance_chart(yearly: pd.DataFrame) -> alt.Chart:
    maximum_distance = max(float(yearly["Distance (km)"].dropna().max()), 1)
    bar_size = max(16, min(48, round(360 / len(yearly))))
    base = alt.Chart(yearly).encode(
        x=alt.X(
            "Year:N",
            sort=None,
            title=None,
            axis=_year_axis(),
            scale=alt.Scale(padding=0.35),
        ),
        y=alt.Y(
            "Distance (km):Q",
            title=None,
            axis=_value_axis("Distance (km)", ".0f"),
            scale=alt.Scale(domain=[0, maximum_distance * 1.12]),
        ),
        tooltip=[
            alt.Tooltip("Year:N", title="Year"),
            alt.Tooltip("Distance (km):Q", title="Distance", format=".1f"),
        ],
    )
    bars = base.mark_bar(
        size=bar_size,
        color="#FF8C00",
        cornerRadiusTopLeft=5,
        cornerRadiusTopRight=5,
    )
    labels = base.mark_text(
        dy=-9,
        color=NAVY,
        font=APP_FONT_CSS,
        fontSize=12,
    ).encode(text=alt.Text("Distance (km):Q", format=".1f"))
    return (bars + labels).properties(height=280).configure_view(strokeOpacity=0)


def build_yearly_speed_chart(yearly: pd.DataFrame) -> alt.Chart:
    maximum_speed = max(float(yearly["Overall average speed (km/h)"].dropna().max()), 1)
    base = alt.Chart(yearly).encode(
        x=alt.X(
            "Year:N",
            sort=yearly["Year"].tolist(),
            title=None,
            axis=_year_axis(),
        ),
        y=alt.Y(
            "Overall average speed (km/h):Q",
            title=None,
            axis=_value_axis("Average speed (km/h)", ".1f"),
            scale=alt.Scale(domain=[0, maximum_speed * 1.14]),
        ),
        tooltip=[
            alt.Tooltip("Year:N", title="Year"),
            alt.Tooltip(
                "Overall average speed (km/h):Q",
                title="Average speed",
                format=".1f",
            ),
        ],
    )
    line = base.mark_line(
        color=NAVY,
        strokeWidth=3,
        interpolate="monotone",
    )
    points = base.mark_point(
        color="#FF8C00",
        filled=True,
        size=90,
    )
    labels = base.mark_text(
        dy=-12,
        color=NAVY,
        font=APP_FONT_CSS,
        fontSize=12,
    ).encode(text=alt.Text("Overall average speed (km/h):Q", format=".1f"))
    return (line + points + labels).properties(height=260).configure_view(strokeOpacity=0)


def build_speed_distribution_chart(distribution: pd.DataFrame) -> alt.Chart:
    maximum_count = max(int(distribution["Activity count"].max()), 1)
    ranges = distribution["Range"].tolist()
    base = alt.Chart(distribution).encode(
        x=alt.X(
            "Range:N",
            sort=ranges,
            title="Average speed (km/h)",
            axis=alt.Axis(
                domain=True,
                domainColor=NAVY,
                labelAngle=-45,
                labelColor=NAVY,
                labelFont=APP_FONT_CSS,
                labelFontSize=10,
                labelOverlap=False,
                labelPadding=6,
                labels=True,
                tickColor=NAVY,
                ticks=True,
                titleColor=NAVY,
                titleFont=APP_FONT_CSS,
                titleFontSize=12,
                titlePadding=12,
            ),
        ),
        y=alt.Y(
            "Activity count:Q",
            title=None,
            axis=_value_axis("Activity count", "d"),
            scale=alt.Scale(domain=[0, maximum_count * 1.18]),
        ),
        tooltip=[
            alt.Tooltip("Definition:N", title="Speed range (km/h)"),
            alt.Tooltip("Activity count:Q", title="Activity count", format="d"),
            alt.Tooltip("Distance (km):Q", title="Distance (km)", format=".1f"),
        ],
    )
    bars = base.mark_bar(
        color="#FF8C00",
        cornerRadiusTopLeft=4,
        cornerRadiusTopRight=4,
        size=SPEED_DISTRIBUTION_BAR_SIZE,
    )
    labels = base.mark_text(
        dy=-7,
        color=NAVY,
        font=APP_FONT_CSS,
        fontSize=11,
    ).encode(text=alt.Text("Activity count:Q", format="d"))
    return (bars + labels).properties(height=280).configure_view(strokeOpacity=0)


def build_calendar_heatmap_chart(calendar: pd.DataFrame) -> alt.Chart:
    maximum = max(int(calendar["Activity count"].max()), 1)
    month_label_expression = " : ".join(
        f"datum.value === {week} ? '{month}'"
        for week, month in CALENDAR_MONTH_WEEKS.items()
    ) + " : ''"
    base = alt.Chart(calendar).encode(
        x=alt.X(
            "Week:O",
            title=None,
            axis=alt.Axis(
                domain=False,
                labelAngle=0,
                labelColor=NAVY,
                labelExpr=month_label_expression,
                labelFont=APP_FONT_CSS,
                labelFontSize=10,
                labelPadding=8,
                orient="top",
                ticks=False,
                values=list(CALENDAR_MONTH_WEEKS),
            ),
        ),
        y=alt.Y(
            "Weekday:N",
            sort=CALENDAR_WEEKDAYS,
            title=None,
            axis=alt.Axis(
                domain=False,
                labelColor=NAVY,
                labelFont=APP_FONT_CSS,
                labelFontSize=10,
                labelPadding=6,
                ticks=False,
            ),
        ),
        tooltip=[
            alt.Tooltip("Calendar day:N", title="Calendar day"),
            alt.Tooltip("Activity count:Q", title="Activity count", format="d"),
        ],
    )
    cells = base.mark_rect(
        cornerRadius=2,
        stroke="#FFFFFF",
        strokeWidth=1,
    ).encode(
        color=alt.Color(
            "Activity count:Q",
            title="Activities",
            scale=alt.Scale(
                domain=[0, maximum],
                range=["#EEF2F6", "#FF8C00"],
                interpolate="rgb",
            ),
        )
    )
    peak = base.transform_filter(alt.datum["Is peak"]).mark_point(
        color=NAVY,
        filled=True,
        shape="diamond",
        size=48,
    )
    return (cells + peak).properties(height=180).configure_view(strokeOpacity=0)


def build_hourly_heatmap_chart(hours: pd.DataFrame) -> alt.Chart:
    maximum = max(int(hours["Activity count"].max()), 1)
    base = alt.Chart(hours).encode(
        x=alt.X(
            "Hour label:N",
            sort=hours["Hour label"].tolist(),
            title="Start hour",
            axis=alt.Axis(
                domain=False,
                labelAngle=0,
                labelColor=NAVY,
                labelFont=APP_FONT_CSS,
                labelFontSize=10,
                labelOverlap=False,
                labelPadding=6,
                ticks=False,
                titleColor=NAVY,
                titleFont=APP_FONT_CSS,
                titleFontSize=12,
                titlePadding=10,
            ),
        ),
        y=alt.Y("Row:N", title=None, axis=None),
        tooltip=[
            alt.Tooltip("Start hour:N", title="Start hour"),
            alt.Tooltip("Activity count:Q", title="Activity count", format="d"),
        ],
    )
    cells = base.mark_rect(
        cornerRadius=2,
        stroke="#FFFFFF",
        strokeWidth=1,
    ).encode(
        color=alt.Color(
            "Activity count:Q",
            title="Activities",
            scale=alt.Scale(
                domain=[0, maximum],
                range=["#EEF2F6", "#FF8C00"],
                interpolate="rgb",
            ),
        )
    )
    peak = base.transform_filter(alt.datum["Is peak"]).mark_point(
        color=NAVY,
        filled=True,
        shape="diamond",
        size=48,
    )
    return (cells + peak).properties(height=80).configure_view(strokeOpacity=0)


def build_ride_metrics(
    activities: pd.DataFrame,
    date_from=None,
    date_to=None,
) -> dict | None:
    rides = activities[activities["_type"] == "Ride"].copy()
    if rides.empty or len(rides) != len(activities):
        return None

    dated_rides = rides.dropna(subset=["_date"]).copy()
    dated_rides["_valid_distance_km"] = valid_measurements(
        dated_rides, "_distance_km"
    )
    distance_rides = dated_rides.dropna(subset=["_valid_distance_km"])
    daily_distance = (
        distance_rides.assign(_day=distance_rides["_date"].dt.normalize())
        .groupby("_day")["_valid_distance_km"]
        .sum()
        .sort_values(ascending=False)
    )

    ranks = pd.Series(range(1, len(daily_distance) + 1), dtype="int64")
    sorted_distances = daily_distance.reset_index(drop=True)
    qualifying_ranks = ranks[sorted_distances >= ranks]
    eddington = int(qualifying_ranks.max()) if not qualifying_ranks.empty else 0

    active_weeks = 0
    longest_streak = 0
    period_start = pd.Timestamp(date_from) if date_from is not None else None
    period_end = pd.Timestamp(date_to) if date_to is not None else None
    if period_start is None and not dated_rides.empty:
        period_start = dated_rides["_date"].min()
    if period_end is None and not dated_rides.empty:
        period_end = dated_rides["_date"].max()
    if period_start is not None and period_end is not None:
        start_week = period_start.to_period("W-SUN").start_time
        end_week = period_end.to_period("W-SUN").start_time
        total_weeks = max(((end_week - start_week).days // 7) + 1, 0)
    else:
        total_weeks = 0

    if not dated_rides.empty:
        weeks = sorted(
            dated_rides["_date"].dt.to_period("W-SUN").dt.start_time.drop_duplicates()
        )
        active_weeks = len(weeks)
        current_streak = 0
        previous_week = None
        for week in weeks:
            current_streak = current_streak + 1 if previous_week is not None and (week - previous_week).days == 7 else 1
            longest_streak = max(longest_streak, current_streak)
            previous_week = week

    active_week_percentage = round(active_weeks / total_weeks * 100) if total_weeks else 0
    metrics = [
        {
            "label": "Metric Eddington number",
            "value": str(eddington),
            "detail": f"{eddington} days of at least {eddington} km" if eddington else "No qualifying distance yet",
        },
        {
            "label": "Longest weekly streak",
            "value": f"{longest_streak} {'week' if longest_streak == 1 else 'weeks'}",
            "detail": "Consecutive weeks with a ride",
        },
        {
            "label": "Active weeks",
            "value": f"{active_weeks} of {total_weeks}",
            "detail": f"{active_week_percentage}% of the selected period",
        },
    ]
    return {"metrics": metrics}


def build_report_context(
    activities: pd.DataFrame,
    date_from=None,
    date_to=None,
    applied_filters: dict | None = None,
) -> str:
    dated = activities.dropna(subset=["_date"])
    first_date = dated["_date"].min() if not dated.empty else pd.NaT
    last_date = dated["_date"].max() if not dated.empty else pd.NaT
    displayed_start = pd.Timestamp(date_from) if date_from is not None else first_date
    displayed_end = pd.Timestamp(date_to) if date_to is not None else last_date
    period = (
        f"{display_date(displayed_start)} - {display_date(displayed_end)}"
        if pd.notna(displayed_start) and pd.notna(displayed_end)
        else "Dates unavailable"
    )
    types = [value for value in ["Ride", "Run", "Walk"] if value in set(activities["_type"])]
    context_parts = [
        f"Date: {period}",
        f"Type: {', '.join(types) or 'Other activities'}",
    ]
    if applied_filters:
        name_search = str(applied_filters.get("name_search", "")).strip()
        if name_search:
            context_parts.append(f'Name contains: "{name_search}"')
        series = applied_filters.get("series") or []
        if series:
            context_parts.append(f"Series: {', '.join(map(str, series))}")
        gears = applied_filters.get("gears") or []
        if gears:
            context_parts.append(f"Gear: {', '.join(map(str, gears))}")
        distance_range = applied_filters.get("distance_range")
        if distance_range:
            context_parts.append(
                f"Distance: {distance_range[0]:.1f}-{distance_range[1]:.1f} km"
            )
        speed_range = applied_filters.get("speed_range")
        if speed_range:
            context_parts.append(
                f"Speed: {speed_range[0]:.1f}-{speed_range[1]:.1f} km/h"
            )
    return " · ".join(context_parts)


def build_report_model(
    activities: pd.DataFrame,
    date_from=None,
    date_to=None,
    applied_filters: dict | None = None,
) -> dict:
    highlight_specs = [
        ("Furthest distance", "_distance_km", "max", None, lambda value: f"{value:.1f} km"),
        ("Longest moving time", "_moving_hours", "max", None, format_hours),
        ("Biggest climb", "_elevation_m", "max", None, lambda value: f"{value:.0f} m"),
        ("Most calories", "_calories", "max", None, lambda value: f"{value:.0f}"),
        ("Highest average speed", "_avg_speed_kmh", "max", None, lambda value: f"{value:.1f} km/h"),
        ("Lowest average speed", "_avg_speed_kmh", "min", "Ride", lambda value: f"{value:.1f} km/h"),
        ("Highest relative effort", "_relative_effort", "max", None, lambda value: f"{value:.0f}"),
    ]
    highlights = []
    for label, column, direction, activity_type, formatter in highlight_specs:
        valid = activities.assign(_highlight_value=valid_measurements(activities, column))
        if activity_type:
            valid = valid[valid["_type"] == activity_type]
        valid = valid[valid["_highlight_value"] > 0]
        if valid.empty:
            continue
        index = (
            valid["_highlight_value"].idxmax()
            if direction == "max"
            else valid["_highlight_value"].idxmin()
        )
        activity = valid.loc[index]
        highlights.append({
            "Highlight": label,
            "Activity": activity["_name"] or "Unnamed activity",
            "Date": display_date(activity["_date"]),
            "Value": formatter(float(activity["_highlight_value"])),
        })

    geared = activities[activities["_gear"].str.strip() != ""].copy()
    gear = pd.DataFrame()
    if not geared.empty:
        gear_rows = []
        for gear_name, group in geared.groupby("_gear", sort=False):
            distances = valid_measurements(group, "_distance_km")
            moving_hours = valid_measurements(group, "_moving_hours")
            gear_rows.append({
                "Gear": gear_name,
                "Activity_count": len(group),
                "Distance_km": distances.sum(min_count=1),
                "Moving_hours": moving_hours.sum(min_count=1),
                "Last_used": group["_date"].max(),
                "Average_distance": distances.mean(),
                "Overall_average_speed": overall_average_speed(group),
            })
        gear = (
            pd.DataFrame(gear_rows)
            .sort_values("Distance_km", ascending=False, na_position="last")
            .head(10)
            .reset_index(drop=True)
        )

    return {
        "context": build_report_context(
            activities, date_from, date_to, applied_filters
        ),
        "summary_metrics": build_summary_metrics(activities),
        "speed_distribution": build_speed_distribution(activities),
        "speed_distribution_coverage": build_speed_distribution_coverage(activities),
        "calendar_heatmap": build_calendar_heatmap(activities),
        "hourly_heatmap": build_hourly_heatmap(activities),
        "highlights": highlights,
        "gear": gear,
        "monthly": build_monthly_performance(activities, date_from, date_to),
        "yearly": build_yearly_statistics(activities, date_from, date_to),
        "ride_metrics": build_ride_metrics(activities, date_from, date_to),
    }


def render_report(model: dict) -> None:
    st.markdown(
        '<div class="report-heading">'
        '<span class="report-heading__title">Report</span>'
        f'<span class="report-heading__scope">{escape(model["context"])}</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.subheader("Metrics")
    for start in range(0, len(model["summary_metrics"]), 4):
        columns = st.columns(4)
        for column, metric in zip(columns, model["summary_metrics"][start:start + 4]):
            column.metric(metric["label"], metric["value"])

    if model["ride_metrics"] is not None:
        ride_metrics = model["ride_metrics"]["metrics"]
        for start in range(0, len(ride_metrics), 4):
            columns = st.columns(4)
            for column, metric in zip(columns, ride_metrics[start:start + 4]):
                column.metric(metric["label"], metric["value"], help=metric["detail"])

    st.markdown("#### Average speed distribution")
    st.caption(model["speed_distribution_coverage"]["label"])
    if model["speed_distribution"].empty:
        st.info("No average speed information is available.")
    else:
        st.altair_chart(
            build_speed_distribution_chart(model["speed_distribution"]),
            use_container_width=True,
            theme=None,
        )

    st.subheader("Heatmaps")
    st.markdown("#### Calendar days")
    st.caption(
        "Activity counts are aggregated by calendar day across all selected years. "
        "A navy diamond marks the most active day."
    )
    st.altair_chart(
        build_calendar_heatmap_chart(model["calendar_heatmap"]),
        use_container_width=True,
        theme=None,
    )
    st.markdown("#### Start hours")
    st.caption(
        "Activity counts are grouped by start hour. "
        "A navy diamond marks the most active hour."
    )
    st.altair_chart(
        build_hourly_heatmap_chart(model["hourly_heatmap"]),
        use_container_width=True,
        theme=None,
    )

    st.subheader("Gear usage")
    if model["gear"].empty:
        st.info("No gear information is available.")
    else:
        gear_display = model["gear"].rename(columns={
            "Activity_count": "Activity count",
            "Distance_km": "Distance (km)",
            "Average_distance": "Average distance (km)",
            "Moving_hours": "Moving time (h)",
            "Overall_average_speed": "Average speed (km/h)",
            "Last_used": "Last used",
        }).copy()
        gear_display = gear_display[[
            "Gear", "Activity count", "Distance (km)", "Average distance (km)",
            "Moving time (h)", "Average speed (km/h)", "Last used",
        ]]
        for column in ["Distance (km)", "Average distance (km)", "Moving time (h)", "Average speed (km/h)"]:
            gear_display[column] = gear_display[column].round(1)
        gear_display["Last used"] = gear_display["Last used"].dt.strftime("%d %b %Y").fillna("-")
        st.dataframe(
            gear_display,
            width="stretch",
            hide_index=True,
            column_config={
                "Activity count": left_aligned_number_column("%d"),
                "Distance (km)": left_aligned_number_column("%.1f"),
                "Average distance (km)": left_aligned_number_column("%.1f"),
                "Moving time (h)": left_aligned_number_column("%.1f"),
                "Average speed (km/h)": left_aligned_number_column("%.1f"),
            },
        )

    st.subheader("Highlights")
    if model["highlights"]:
        st.dataframe(pd.DataFrame(model["highlights"]), width="stretch", hide_index=True)
    else:
        st.info("No highlight metrics are available.")

    st.subheader("Monthly Performance")
    monthly_display = pd.DataFrame(model["monthly"])
    if monthly_display.empty:
        st.info("No monthly statistics are available.")
    else:
        st.dataframe(
            monthly_display.style.format({
                "Activity count": "{:.0f}",
                "Distance (km)": "{:.1f}",
                "Moving time (h)": "{:.1f}",
                "Average distance (km)": "{:.1f}",
                "Elevation gain (m)": "{:.0f}",
                "Average speed (km/h)": "{:.1f}",
            }, na_rep="-"),
            width="stretch",
            hide_index=True,
            column_config={
                "Activity count": left_aligned_number_column("%d"),
                "Distance (km)": left_aligned_number_column("%.1f"),
                "Moving time (h)": left_aligned_number_column("%.1f"),
                "Average distance (km)": left_aligned_number_column("%.1f"),
                "Elevation gain (m)": left_aligned_number_column("%.0f"),
                "Average speed (km/h)": left_aligned_number_column("%.1f"),
            },
        )

    st.subheader("Yearly Performance")
    if model["yearly"].empty:
        st.info("No yearly statistics are available.")
    else:
        yearly = model["yearly"]
        st.markdown("#### Distance per year")
        valid_distances = yearly["Distance (km)"].dropna()
        if valid_distances.empty:
            st.info("No yearly distance information is available.")
        else:
            st.altair_chart(
                build_yearly_distance_chart(yearly),
                use_container_width=True,
                theme=None,
            )

        st.markdown("#### Average speed per year")
        valid_speeds = yearly["Overall average speed (km/h)"].dropna()
        if valid_speeds.empty:
            st.info("No yearly average speed information is available.")
        else:
            st.altair_chart(
                build_yearly_speed_chart(yearly),
                use_container_width=True,
                theme=None,
            )


def _pdf_table(data, widths=None, header=True):
    table = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    style = [
        ("FONTNAME", (0, 0), (-1, -1), PDF_FONT_REGULAR),
        ("FONTNAME", (0, 0), (-1, 0), PDF_FONT_BOLD if header else PDF_FONT_REGULAR),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2FF") if header else colors.white),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(NAVY)),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7DFEA")),
        ("FONTSIZE", (0, 0), (-1, -1), PDF_TABLE_FONT_SIZE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    table.setStyle(TableStyle(style))
    return table


def _draw_pdf_background(canvas, document, background_rgb: tuple[int, int, int]) -> None:
    page_width, page_height = document.pagesize
    red, green, blue = (channel / 255 for channel in background_rgb)
    bands = 120
    band_height = page_height / bands

    canvas.saveState()
    for band in range(bands):
        progress = band / (bands - 1)
        opacity = 0.26 * (1 - progress) ** 1.35
        fill = colors.Color(
            1 - (1 - red) * opacity,
            1 - (1 - green) * opacity,
            1 - (1 - blue) * opacity,
        )
        canvas.setFillColor(fill)
        canvas.rect(
            0,
            page_height - (band + 1) * band_height,
            page_width,
            band_height + 1,
            stroke=0,
            fill=1,
        )
    canvas.restoreState()


def _pdf_metric_grid(metrics: list[dict], styles) -> list[Table]:
    grids = []
    metric_style = styles["BodyText"].clone("MetricCard")
    metric_style.leading = 15
    for start in range(0, len(metrics), 4):
        cards = []
        for metric in metrics[start:start + 4]:
            detail = metric.get("detail")
            detail_markup = (
                f'<br/><font size="6" color="#53657D">{escape(detail)}</font>'
                if detail
                else ""
            )
            cards.append(Paragraph(
                f'<font size="{PDF_METRIC_LABEL_FONT_SIZE}">'
                f'{escape(metric["label"])}</font><br/>'
                f'<b><font size="{PDF_METRIC_VALUE_FONT_SIZE}">'
                f'{escape(metric["value"])}</font></b>'
                f"{detail_markup}",
                metric_style,
            ))
        cards.extend([""] * (4 - len(cards)))
        grid = Table([cards], colWidths=[64 * mm] * 4, rowHeights=[22 * mm], hAlign="LEFT")
        grid.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.Color(1, 1, 1, alpha=0.82)),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7DFEA")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D7DFEA")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ]))
        grids.append(grid)
    return grids


def _pdf_speed_distribution_chart(distribution: pd.DataFrame) -> Drawing:
    width, height = 256 * mm, 42 * mm
    drawing = Drawing(width, height)
    left, right, bottom, top = 14 * mm, 5 * mm, 10 * mm, 7 * mm
    plot_width = width - left - right
    plot_height = height - bottom - top
    maximum = max(int(distribution["Activity count"].max()), 1)
    slot_width = plot_width / len(distribution)
    bar_width = slot_width * PDF_SPEED_DISTRIBUTION_BAR_RATIO

    drawing.add(Line(
        left,
        bottom,
        left,
        bottom + plot_height,
        strokeColor=colors.HexColor("#AEB9C8"),
    ))
    drawing.add(Line(
        left,
        bottom,
        left + plot_width,
        bottom,
        strokeColor=colors.HexColor("#AEB9C8"),
    ))
    drawing.add(String(
        0,
        bottom + plot_height - 3,
        str(maximum),
        fontName=PDF_FONT_REGULAR,
        fontSize=6,
        fillColor=colors.HexColor("#53657D"),
    ))

    for index, row in enumerate(distribution.itertuples(index=False)):
        center = left + (index + 0.5) * slot_width
        activity_count = int(row[2])
        bar_height = activity_count / maximum * plot_height
        drawing.add(Rect(
            center - bar_width / 2,
            bottom,
            bar_width,
            bar_height,
            fillColor=colors.HexColor("#FF8C00"),
            strokeColor=None,
        ))
        drawing.add(String(
            center,
            max(bottom + bar_height + 3, bottom + 3),
            str(activity_count),
            fontName=PDF_FONT_BOLD,
            fontSize=6.5,
            fillColor=colors.HexColor(NAVY),
            textAnchor="middle",
        ))
        drawing.add(String(
            center,
            1,
            str(row[0]),
            fontName=PDF_FONT_REGULAR,
            fontSize=5.5,
            fillColor=colors.HexColor(NAVY),
            textAnchor="middle",
        ))
    return drawing


def _pdf_calendar_heatmap(calendar: pd.DataFrame) -> Drawing:
    width, height = 256 * mm, 45 * mm
    drawing = Drawing(width, height)
    left, right, bottom, top = 14 * mm, 5 * mm, 2 * mm, 8 * mm
    plot_width = width - left - right
    plot_height = height - bottom - top
    column_pitch = plot_width / 53
    row_pitch = plot_height / 7
    cell_size = min(column_pitch, row_pitch) * 0.82
    maximum = max(int(calendar["Activity count"].max()), 1)
    low = colors.HexColor("#EEF2F6")
    high = colors.HexColor("#FF8C00")

    for week, month in CALENDAR_MONTH_WEEKS.items():
        drawing.add(String(
            left + week * column_pitch,
            height - 5 * mm,
            month,
            fontName=PDF_FONT_REGULAR,
            fontSize=6.5,
            fillColor=colors.HexColor(NAVY),
        ))
    for weekday_index, weekday in enumerate(CALENDAR_WEEKDAYS):
        center_y = bottom + (6 - weekday_index + 0.5) * row_pitch
        drawing.add(String(
            left - 2 * mm,
            center_y - 2,
            weekday,
            fontName=PDF_FONT_REGULAR,
            fontSize=5.5,
            fillColor=colors.HexColor(NAVY),
            textAnchor="end",
        ))

    for _, day in calendar.iterrows():
        weekday_index = CALENDAR_WEEKDAYS.index(day["Weekday"])
        center_x = left + (int(day["Week"]) + 0.5) * column_pitch
        center_y = bottom + (6 - weekday_index + 0.5) * row_pitch
        intensity = (int(day["Activity count"]) / maximum) ** 0.65
        fill = colors.Color(
            low.red + (high.red - low.red) * intensity,
            low.green + (high.green - low.green) * intensity,
            low.blue + (high.blue - low.blue) * intensity,
        )
        drawing.add(Rect(
            center_x - cell_size / 2,
            center_y - cell_size / 2,
            cell_size,
            cell_size,
            rx=1,
            ry=1,
            fillColor=fill,
            strokeColor=colors.white,
            strokeWidth=0.5,
        ))
        if bool(day["Is peak"]):
            radius = cell_size * 0.24
            drawing.add(Polygon(
                [
                    center_x, center_y + radius,
                              center_x + radius, center_y,
                    center_x, center_y - radius,
                              center_x - radius, center_y,
                ],
                fillColor=colors.HexColor(NAVY),
                strokeColor=None,
            ))
    return drawing


def _pdf_hourly_heatmap(hours: pd.DataFrame) -> Drawing:
    width, height = 256 * mm, 19 * mm
    drawing = Drawing(width, height)
    left, right, bottom, top = 5 * mm, 5 * mm, 6 * mm, 1 * mm
    plot_width = width - left - right
    column_pitch = plot_width / 24
    cell_size = min(column_pitch * 0.82, height - bottom - top)
    center_y = bottom + cell_size / 2
    maximum = max(int(hours["Activity count"].max()), 1)
    low = colors.HexColor("#EEF2F6")
    high = colors.HexColor("#FF8C00")

    for _, hour in hours.iterrows():
        center_x = left + (int(hour["Hour"]) + 0.5) * column_pitch
        intensity = (int(hour["Activity count"]) / maximum) ** 0.65
        fill = colors.Color(
            low.red + (high.red - low.red) * intensity,
            low.green + (high.green - low.green) * intensity,
            low.blue + (high.blue - low.blue) * intensity,
        )
        drawing.add(Rect(
            center_x - cell_size / 2,
            center_y - cell_size / 2,
            cell_size,
            cell_size,
            rx=1,
            ry=1,
            fillColor=fill,
            strokeColor=colors.white,
            strokeWidth=0.5,
        ))
        if bool(hour["Is peak"]):
            radius = cell_size * 0.24
            drawing.add(Polygon(
                [
                    center_x, center_y + radius,
                              center_x + radius, center_y,
                    center_x, center_y - radius,
                              center_x - radius, center_y,
                ],
                fillColor=colors.HexColor(NAVY),
                strokeColor=None,
            ))
        drawing.add(String(
            center_x,
            1,
            str(hour["Hour label"]),
            fontName=PDF_FONT_REGULAR,
            fontSize=5.5,
            fillColor=colors.HexColor(NAVY),
            textAnchor="middle",
        ))
    return drawing


def _pdf_yearly_chart(yearly: pd.DataFrame) -> Drawing:
    width, height = 256 * mm, 42 * mm
    drawing = Drawing(width, height)
    left, right, bottom, top = 14 * mm, 5 * mm, 9 * mm, 7 * mm
    plot_width = width - left - right
    plot_height = height - bottom - top
    maximum = max(float(yearly["Distance (km)"].dropna().max()), 1)
    count = len(yearly)
    slot_width = plot_width / max(count, 1)
    bar_width = min(14 * mm, slot_width * 0.42)

    drawing.add(Line(left, bottom, left, bottom + plot_height, strokeColor=colors.HexColor("#AEB9C8")))
    drawing.add(Line(left, bottom, left + plot_width, bottom, strokeColor=colors.HexColor("#AEB9C8")))
    drawing.add(String(
        0,
        bottom + plot_height - 3,
        f"{maximum:.0f} km",
        fontName=PDF_FONT_REGULAR,
        fontSize=6,
        fillColor=colors.HexColor("#53657D"),
    ))

    for index, row in enumerate(yearly.itertuples(index=False)):
        year = str(row[0])
        center = left + (index + 0.5) * slot_width
        if pd.isna(row[1]):
            drawing.add(String(
                center,
                1,
                year,
                fontName=PDF_FONT_REGULAR,
                fontSize=7,
                fillColor=colors.HexColor(NAVY),
                textAnchor="middle",
            ))
            continue
        distance = float(row[1])
        bar_height = distance / maximum * plot_height
        drawing.add(Rect(
            center - bar_width / 2,
            bottom,
            bar_width,
            bar_height,
            fillColor=colors.HexColor("#FF8C00"),
            strokeColor=None,
        ))
        drawing.add(String(
            center,
            max(bottom + bar_height + 3, bottom + 3),
            f"{distance:.1f}",
            fontName=PDF_FONT_BOLD,
            fontSize=6.5,
            fillColor=colors.HexColor(NAVY),
            textAnchor="middle",
        ))
        drawing.add(String(
            center,
            1,
            year,
            fontName=PDF_FONT_REGULAR,
            fontSize=7,
            fillColor=colors.HexColor(NAVY),
            textAnchor="middle",
        ))
    return drawing


def _pdf_yearly_speed_chart(yearly: pd.DataFrame) -> Drawing:
    width, height = 256 * mm, 32 * mm
    drawing = Drawing(width, height)
    left, right, bottom, top = 14 * mm, 5 * mm, 8 * mm, 6 * mm
    plot_width = width - left - right
    plot_height = height - bottom - top
    speeds = yearly["Overall average speed (km/h)"]
    maximum = max(float(speeds.max()), 1)
    count = len(yearly)

    drawing.add(Line(left, bottom, left, bottom + plot_height, strokeColor=colors.HexColor("#AEB9C8")))
    drawing.add(Line(left, bottom, left + plot_width, bottom, strokeColor=colors.HexColor("#AEB9C8")))
    drawing.add(String(
        0,
        bottom + plot_height - 3,
        f"{maximum:.1f} km/h",
        fontName=PDF_FONT_REGULAR,
        fontSize=6,
        fillColor=colors.HexColor("#53657D"),
    ))

    points: list[tuple[float, float] | None] = []
    for index, row in enumerate(yearly.itertuples(index=False)):
        speed = row[2]
        center = left + (index + 0.5) * plot_width / max(count, 1)
        drawing.add(String(
            center,
            1,
            str(row[0]),
            fontName=PDF_FONT_REGULAR,
            fontSize=7,
            fillColor=colors.HexColor(NAVY),
            textAnchor="middle",
        ))
        if pd.isna(speed):
            points.append(None)
            continue
        y = bottom + float(speed) / maximum * plot_height
        points.append((center, y))

    for previous, current in zip(points, points[1:]):
        if previous is not None and current is not None:
            drawing.add(Line(
                previous[0],
                previous[1],
                current[0],
                current[1],
                strokeColor=colors.HexColor(NAVY),
                strokeWidth=1.5,
            ))

    for point, speed in zip(points, speeds):
        if point is None:
            continue
        drawing.add(Circle(
            point[0],
            point[1],
            2.2,
            fillColor=colors.HexColor("#FF8C00"),
            strokeColor=colors.HexColor("#FF8C00"),
        ))
        drawing.add(String(
            point[0],
            point[1] + 6,
            f"{float(speed):.1f}",
            fontName=PDF_FONT_BOLD,
            fontSize=6.5,
            fillColor=colors.HexColor(NAVY),
            textAnchor="middle",
        ))
    return drawing


def build_report_pdf(
    model: dict,
    background_rgb: tuple[int, int, int] = DEFAULT_BACKGROUND_RGB,
) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=landscape(A4), rightMargin=14 * mm, leftMargin=14 * mm,
        topMargin=8 * mm, bottomMargin=8 * mm,
    )
    styles = getSampleStyleSheet()
    styles["BodyText"].fontName = PDF_FONT_REGULAR
    styles["BodyText"].fontSize = PDF_BODY_FONT_SIZE
    styles["BodyText"].leading = 10
    styles["Title"].fontName = PDF_FONT_BOLD
    styles["Title"].fontSize = 18
    styles["Title"].leading = 22
    styles["Title"].textColor = colors.HexColor(NAVY)
    styles["Heading2"].fontName = PDF_FONT_BOLD
    styles["Heading2"].fontSize = PDF_SECTION_FONT_SIZE
    styles["Heading2"].leading = 17
    styles["Heading2"].textColor = colors.HexColor(NAVY)
    styles["Heading3"].fontName = PDF_FONT_BOLD
    styles["Heading3"].fontSize = PDF_SUBSECTION_FONT_SIZE
    styles["Heading3"].leading = 14
    styles["Heading3"].textColor = colors.HexColor(NAVY)
    heatmap_intro_style = styles["BodyText"].clone("HeatmapIntro")
    heatmap_intro_style.leading = 14
    story = [
        Paragraph(f"Report - {escape(model['context'])}", styles["Title"]),
        Spacer(1, 6 * mm),
        Paragraph("Metrics", styles["Heading2"]),
    ]
    for grid in _pdf_metric_grid(model["summary_metrics"], styles):
        story.extend([grid, Spacer(1, 2 * mm)])
    if model["ride_metrics"] is not None:
        for grid in _pdf_metric_grid(model["ride_metrics"]["metrics"], styles):
            story.extend([grid, Spacer(1, 2 * mm)])
    speed_distribution_story = [
        Spacer(1, 2 * mm),
        Paragraph("Average speed distribution", styles["Heading3"]),
        Paragraph(
            escape(model["speed_distribution_coverage"]["label"]),
            styles["BodyText"],
        ),
    ]
    if model["speed_distribution"].empty:
        speed_distribution_story.append(Paragraph(
            "No average speed information is available.",
            styles["BodyText"],
        ))
    else:
        speed_distribution_story.append(
            _pdf_speed_distribution_chart(model["speed_distribution"])
        )
    story.append(KeepTogether(speed_distribution_story))
    heatmap_story = [
        Spacer(1, 5 * mm),
        Paragraph("Heatmaps", styles["Heading2"]),
        Spacer(1, 1 * mm),
        Paragraph(
            "<b><font size=\"11\">Calendar days</font></b><br/>"
            "Activity counts are aggregated by calendar day across all selected years. "
            "A navy diamond marks the most active day.",
            heatmap_intro_style,
        ),
        Spacer(1, 1 * mm),
        _pdf_calendar_heatmap(model["calendar_heatmap"]),
        Spacer(1, 2 * mm),
        Paragraph(
            "<b><font size=\"11\">Start hours</font></b><br/>"
            "Activity counts are grouped by start hour. "
            "A navy diamond marks the most active hour.",
            heatmap_intro_style,
        ),
        Spacer(1, 1 * mm),
        _pdf_hourly_heatmap(model["hourly_heatmap"]),
    ]
    story.append(KeepTogether(heatmap_story))
    gear_story = [Spacer(1, 3 * mm), Paragraph("Gear usage", styles["Heading2"])]
    if model["gear"].empty:
        gear_story.append(Paragraph("No gear information is available.", styles["BodyText"]))
    else:
        gear_rows = [[
            "Gear", "Activity count", "Distance (km)", "Average distance (km)",
            "Moving time (h)", "Average speed (km/h)", "Last used",
        ]]
        for _, row in model["gear"].iterrows():
            gear_rows.append([
                row["Gear"], int(row["Activity_count"]), format_number(row["Distance_km"]),
                format_number(row["Average_distance"]), format_number(row["Moving_hours"]),
                format_number(row["Overall_average_speed"]), display_date(row["Last_used"]),
            ])
        gear_story.append(_pdf_table(
            gear_rows,
            widths=[58 * mm, 24 * mm, 30 * mm, 34 * mm, 30 * mm, 40 * mm, 34 * mm],
        ))
    story.append(KeepTogether(gear_story))
    highlights_story = [
        Spacer(1, 6 * mm),
        Paragraph("Highlights", styles["Heading2"]),
    ]
    if model["highlights"]:
        highlights = pd.DataFrame(model["highlights"]).fillna("-")
        highlights_story.append(_pdf_table(
            [list(highlights.columns)] + highlights.astype(str).to_numpy().tolist()
        ))
    else:
        highlights_story.append(Paragraph(
            "No highlight metrics are available.", styles["BodyText"]
        ))
    story.append(KeepTogether(highlights_story))

    story.extend([
        CondPageBreak(75 * mm),
        Spacer(1, 6 * mm),
        Paragraph("Monthly Performance", styles["Heading2"]),
    ])
    monthly = pd.DataFrame(model["monthly"]).fillna("-")
    if monthly.empty:
        story.append(Paragraph("No monthly statistics are available.", styles["BodyText"]))
    else:
        header_style = styles["BodyText"].clone("MonthlyTableHeader")
        header_style.fontName = PDF_FONT_BOLD
        header_style.fontSize = PDF_TABLE_FONT_SIZE
        header_style.leading = 8.5
        monthly_header = [Paragraph(escape(column), header_style) for column in monthly.columns]
        monthly_rows = [monthly_header] + monthly.astype(str).to_numpy().tolist()
        story.append(_pdf_table(
            monthly_rows,
            widths=[30 * mm, 17 * mm, 25 * mm, 22 * mm, 29 * mm, 24 * mm,
                    25 * mm, 29 * mm, 22 * mm, 27 * mm],
        ))

    yearly_heading = [Spacer(1, 6 * mm), Paragraph("Yearly Performance", styles["Heading2"])]
    if model["yearly"].empty:
        yearly_heading.append(Paragraph("No yearly statistics are available.", styles["BodyText"]))
        story.append(KeepTogether(yearly_heading))
    else:
        yearly_heading.append(Paragraph("Distance per year", styles["Heading3"]))
        if model["yearly"]["Distance (km)"].notna().any():
            yearly_heading.append(_pdf_yearly_chart(model["yearly"]))
        else:
            yearly_heading.append(Paragraph(
                "No yearly distance information is available.",
                styles["BodyText"],
            ))
        story.append(KeepTogether(yearly_heading))
        speed_story = [
            Spacer(1, 3 * mm),
            Paragraph("Average speed per year", styles["Heading3"]),
        ]
        if model["yearly"]["Overall average speed (km/h)"].notna().any():
            speed_story.append(_pdf_yearly_speed_chart(model["yearly"]))
        else:
            speed_story.append(Paragraph(
                "No yearly average speed information is available.",
                styles["BodyText"],
            ))
        story.append(KeepTogether(speed_story))

    draw_background = partial(_draw_pdf_background, background_rgb=background_rgb)
    document.build(
        story,
        onFirstPage=draw_background,
        onLaterPages=draw_background,
    )
    return output.getvalue()
