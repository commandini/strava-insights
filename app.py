from __future__ import annotations

import hashlib
import math

import pandas as pd
import streamlit as st
from streamlit import config as st_config

from activity_processing import filter_activities, prepare_activities
from reporting import build_report_model, build_report_pdf, render_report
from theme import (
    APP_BODY_FONT_SIZE_REM,
    APP_FONT_CSS,
    APP_HEADING_FONT_SIZES,
    APP_METRIC_LABEL_FONT_SIZE_REM,
    APP_METRIC_VALUE_FONT_SIZE_REM,
    APP_PAGE_TITLE_FONT_SIZE_REM,
    APP_REPORT_TITLE_FONT_SIZE_REM,
    APP_SECTION_FONT_SIZE_REM,
    APP_SUBSECTION_FONT_SIZE_REM,
    APP_TABLE_FONT_SIZE_REM,
    DEFAULT_BACKGROUND_RGB,
    hex_to_rgb,
    rgb_to_hex,
)

st_config.set_option("theme.font", APP_FONT_CSS)
st_config.set_option("theme.headingFont", APP_FONT_CSS)
st_config.set_option("theme.baseFontSize", 16)
st_config.set_option("theme.headingFontSizes", list(APP_HEADING_FONT_SIZES))
st.set_page_config(page_title="Activity Insights", page_icon="🚴", layout="wide")

default_background_hex = rgb_to_hex(DEFAULT_BACKGROUND_RGB)
selected_background_hex = st.session_state.get("report_background_color", default_background_hex)
selected_background_rgb = hex_to_rgb(selected_background_hex)
background_rgb_css = ", ".join(map(str, selected_background_rgb))

st.markdown(
    """
    <style>
        .stApp {
            font-family: __APP_FONT_CSS__;
            background:
                linear-gradient(
                    180deg,
                    rgba(__BACKGROUND_RGB__, 0.42) 0%,
                    rgba(__BACKGROUND_RGB__, 0.22) 28%,
                    rgba(__BACKGROUND_RGB__, 0.07) 58%,
                    rgba(__BACKGROUND_RGB__, 0) 100%
                );
        }
        .stApp h1,
        .stApp h2,
        .stApp h3,
        .stApp h4,
        .stApp h5,
        .stApp h6,
        .stApp p,
        .stApp label,
        .stApp button,
        .stApp input,
        .stApp textarea,
        .stApp select,
        .stApp .report-heading__title,
        .stApp .report-heading__scope,
        .stApp [data-testid="stMetricLabel"],
        .stApp [data-testid="stMetricLabel"] *,
        .stApp [data-testid="stMetricValue"],
        .stApp [data-testid="stMetricValue"] *,
        .stApp [data-testid="stMetricDelta"],
        .stApp [data-testid="stMetricDelta"] * {
            font-family: __APP_FONT_CSS__ !important;
        }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(255, 255, 255, 0.88);
            box-shadow: 0 12px 32px rgba(86, 38, 8, 0.08);
            backdrop-filter: blur(12px);
        }
        .stApp h1 {
            font-size: __PAGE_TITLE_FONT_SIZE__rem;
            line-height: 1.18;
            letter-spacing: -0.02em;
        }
        .stApp h2 {
            font-size: __REPORT_TITLE_FONT_SIZE__rem;
            line-height: 1.25;
            letter-spacing: -0.015em;
        }
        .stApp h3 {
            font-size: __SECTION_FONT_SIZE__rem;
            font-weight: 700;
            line-height: 1.3;
            margin-top: 0.65rem;
        }
        .stApp h4 {
            font-size: __SUBSECTION_FONT_SIZE__rem;
            font-weight: 600;
            line-height: 1.35;
        }
        .stApp p,
        .stApp label,
        .stApp button,
        .stApp input,
        .stApp textarea,
        .stApp select {
            font-size: __BODY_FONT_SIZE__rem;
            line-height: 1.45;
        }
        .stApp [data-testid="stMetricLabel"],
        .stApp [data-testid="stMetricLabel"] * {
            font-size: __METRIC_LABEL_FONT_SIZE__rem !important;
            line-height: 1.35;
        }
        .stApp [data-testid="stMetricValue"],
        .stApp [data-testid="stMetricValue"] * {
            font-size: __METRIC_VALUE_FONT_SIZE__rem !important;
            line-height: 1.15;
        }
        .stApp [data-testid="stDataFrame"] {
            font-family: __APP_FONT_CSS__ !important;
            font-size: __TABLE_FONT_SIZE__rem;
        }
        .report-heading {
            display: flex;
            align-items: baseline;
            flex-wrap: wrap;
            gap: 0.45rem 0.7rem;
            margin: 0.1rem 0 0.45rem;
        }
        .report-heading__title {
            color: var(--text-color);
            font-size: __REPORT_TITLE_FONT_SIZE__rem;
            font-weight: 700;
            letter-spacing: -0.015em;
        }
        .report-heading__scope {
            color: color-mix(in srgb, var(--text-color) 64%, transparent);
            font-size: 0.9rem;
            font-weight: 400;
        }
        [data-testid="stVerticalBlock"]:has(
            > [data-testid="stElementContainer"] .report-heading
        ) > [data-testid="stElementContainer"] h3 {
            display: flex;
            align-items: center;
            gap: 0.7rem;
            margin-top: 1.35rem;
            margin-bottom: 0.75rem;
            color: #14213d;
            font-weight: 700;
        }
        [data-testid="stVerticalBlock"]:has(
            > [data-testid="stElementContainer"] .report-heading
        ) > [data-testid="stElementContainer"] h3::before {
            content: "";
            width: 0.24rem;
            height: 1.25rem;
            flex: 0 0 auto;
            border-radius: 999px;
            background: #ff8c00;
        }
        [data-testid="stVerticalBlock"]:has(
            > [data-testid="stElementContainer"] .report-heading
        ) > [data-testid="stElementContainer"] h3::after {
            content: "";
            height: 1px;
            flex: 1 1 auto;
            background: linear-gradient(90deg, rgba(20, 33, 61, 0.24), transparent);
        }
        .report-export-divider {
            border-top: 1px solid color-mix(in srgb, var(--text-color) 14%, transparent);
            margin: 1.4rem 0 1rem;
        }
        div[data-testid="stDataFrame"] { margin-bottom: 0.75rem; }
    </style>
    """
    .replace("__BACKGROUND_RGB__", background_rgb_css)
    .replace("__APP_FONT_CSS__", APP_FONT_CSS)
    .replace("__BODY_FONT_SIZE__", str(APP_BODY_FONT_SIZE_REM))
    .replace("__TABLE_FONT_SIZE__", str(APP_TABLE_FONT_SIZE_REM))
    .replace("__PAGE_TITLE_FONT_SIZE__", str(APP_PAGE_TITLE_FONT_SIZE_REM))
    .replace("__REPORT_TITLE_FONT_SIZE__", str(APP_REPORT_TITLE_FONT_SIZE_REM))
    .replace("__SECTION_FONT_SIZE__", str(APP_SECTION_FONT_SIZE_REM))
    .replace("__SUBSECTION_FONT_SIZE__", str(APP_SUBSECTION_FONT_SIZE_REM))
    .replace("__METRIC_LABEL_FONT_SIZE__", str(APP_METRIC_LABEL_FONT_SIZE_REM))
    .replace("__METRIC_VALUE_FONT_SIZE__", str(APP_METRIC_VALUE_FONT_SIZE_REM)),
    unsafe_allow_html=True,
)

FILTER_KEYS = (
    "filter_date_from", "filter_date_to", "filter_name", "filter_series",
    "filter_type", "filter_gears", "filter_distance", "filter_speed",
)


def clear_filter_state() -> None:
    for key in FILTER_KEYS:
        st.session_state.pop(key, None)


def reset_filters() -> None:
    for key, value in st.session_state.get("filter_defaults", {}).items():
        st.session_state[key] = value


@st.cache_data(show_spinner=False)
def prepare_data(file_bytes: bytes) -> pd.DataFrame:
    return prepare_activities(file_bytes)


@st.cache_data(show_spinner=False)
def prepare_pdf_download(model: dict, background_rgb: tuple[int, int, int]) -> bytes:
    return build_report_pdf(model, background_rgb)


st.title("Activity Insights")
st.caption("A focused overview of your sports activities.")

with st.container(border=True):
    st.subheader("1. Load and filter activities")
    uploaded_file = st.file_uploader("Select CSV file containing your activities", type=["csv"])
    process = False
    if uploaded_file is not None:
        st.markdown(
            '<style>[data-testid="stFileUploaderDropzone"] { display: none !important; }</style>',
            unsafe_allow_html=True,
        )
        file_bytes = uploaded_file.getvalue()
        source_id = hashlib.sha256(file_bytes).hexdigest()
        if st.session_state.get("filter_source_id") != source_id:
            clear_filter_state()
            for key in (
                "filter_defaults",
                "activities",
                "applied_filter_signature",
                "applied_date_range",
                "applied_filters",
            ):
                st.session_state.pop(key, None)
            st.session_state.filter_source_id = source_id

        try:
            source_activities = prepare_data(file_bytes)
        except Exception as error:
            st.error(f"Could not read the CSV: {error}")
            st.stop()

        if unit_warning := source_activities.attrs.get("unit_inference_warning"):
            st.warning(unit_warning)

        valid_dates = source_activities["_date"].dropna()
        st.markdown("#### Filters")
        date_left, date_right, type_column = st.columns([1, 1, 1.35])
        if valid_dates.empty:
            date_from = date_to = None
            date_left.date_input("Date from", disabled=True, key="filter_date_from")
            date_right.date_input("Date to", disabled=True, key="filter_date_to")
        else:
            earliest, latest = valid_dates.min().date(), valid_dates.max().date()
            date_from = date_left.date_input(
                "Date from", earliest, min_value=earliest, max_value=latest, key="filter_date_from"
            )
            date_to = date_right.date_input(
                "Date to", latest, min_value=earliest, max_value=latest, key="filter_date_to"
            )
        available_types = set(source_activities["_type"].dropna())
        activity_type_options = [
            activity_type for activity_type in ["Ride", "Run", "Walk"]
            if activity_type in available_types
        ]
        activity_type = type_column.selectbox(
            "Type",
            activity_type_options,
            key="filter_type",
            disabled=not activity_type_options,
        )

        name_column, series_column, gear_column = st.columns(3)
        name_search = name_column.text_input(
            "Name contains", placeholder="Case-insensitive", key="filter_name"
        )
        series_counts = source_activities.loc[source_activities["_series"] != "", "_series"].value_counts()
        series_options = sorted(series_counts[series_counts > 1].index.tolist(), key=str.casefold)
        selected_series = series_column.multiselect(
            "Series",
            series_options,
            placeholder="All series",
            help="Includes repeated names and names ending in bracket variants such as Joe[0] or Joe[3,4].",
            key="filter_series",
        )
        gear_options = sorted(value for value in source_activities["_gear"].unique() if value)
        selected_gears = gear_column.multiselect(
            "Gear", gear_options, placeholder="All gear", key="filter_gears"
        )

        distances = source_activities["_distance_km"].dropna()
        distance_floor = max(0.0, math.floor(float(distances.min()) * 10) / 10) if not distances.empty else 0.0
        distance_ceiling = max(distance_floor,
                               math.ceil(float(distances.max()) * 10) / 10) if not distances.empty else 0.0
        speeds = source_activities["_avg_speed_kmh"].dropna()
        speed_floor = max(0.0, math.floor(float(speeds.min()) * 10) / 10) if not speeds.empty else 0.0
        speed_ceiling = max(speed_floor, math.ceil(float(speeds.max()) * 10) / 10) if not speeds.empty else 0.0

        st.session_state.filter_defaults = {
            "filter_date_from": earliest if not valid_dates.empty else None,
            "filter_date_to": latest if not valid_dates.empty else None,
            "filter_name": "",
            "filter_series": [],
            "filter_type": activity_type_options[0] if activity_type_options else None,
            "filter_gears": [],
            "filter_distance": (distance_floor, distance_ceiling),
            "filter_speed": (speed_floor, speed_ceiling),
        }

        range_left, range_right = st.columns(2)
        distance_limit = max(distance_ceiling, distance_floor + 0.1)
        speed_limit = max(speed_ceiling, speed_floor + 0.1)
        distance_min, distance_max = range_left.slider(
            "Distance (km)", min_value=distance_floor, max_value=distance_limit,
            value=(distance_floor, distance_ceiling), step=0.1, format="%.1f", key="filter_distance",
        )
        speed_min, speed_max = range_right.slider(
            "Average speed (km/h)", min_value=speed_floor, max_value=speed_limit,
            value=(speed_floor, speed_ceiling), step=0.1, format="%.1f", key="filter_speed",
        )

        valid_ranges = True
        if not activity_type_options:
            st.warning("No supported activity types were found in this file.")
            valid_ranges = False
        if date_from is not None and date_to is not None and date_from > date_to:
            st.warning("Date from must be earlier than or equal to Date to.")
            valid_ranges = False
        filter_signature = (
            source_id, date_from, date_to, name_search.strip().casefold(), tuple(selected_series),
            activity_type, round(distance_min, 3), round(distance_max, 3),
            tuple(selected_gears), round(speed_min, 3), round(speed_max, 3),
        )
        action_column, reset_column, _ = st.columns([1, 1, 4])
        process = action_column.button("Get Insights", type="primary", disabled=not valid_ranges)
        reset_column.button("Reset filters", on_click=reset_filters)
    elif st.session_state.get("filter_source_id"):
        clear_filter_state()
        for key in (
            "filter_source_id", "filter_defaults", "activities",
            "applied_filter_signature", "applied_date_range", "applied_filters",
        ):
            st.session_state.pop(key, None)

if process:
    st.session_state.activities = filter_activities(
        source_activities, date_from, date_to, name_search, selected_series, activity_type,
        distance_min, distance_max, selected_gears, speed_min, speed_max,
    )
    st.session_state.applied_filter_signature = filter_signature
    st.session_state.applied_date_range = (date_from, date_to)
    st.session_state.applied_filters = {
        "name_search": name_search.strip(),
        "series": list(selected_series),
        "gears": list(selected_gears),
        "distance_range": (
            None
            if math.isclose(distance_min, distance_floor)
               and math.isclose(distance_max, distance_ceiling)
            else (distance_min, distance_max)
        ),
        "speed_range": (
            None
            if math.isclose(speed_min, speed_floor)
               and math.isclose(speed_max, speed_ceiling)
            else (speed_min, speed_max)
        ),
    }

if "activities" not in st.session_state:
    st.info("Choose a CSV file, set optional filters, and click **Get Insights**.")
    st.stop()

activities = st.session_state.activities
if uploaded_file is not None and st.session_state.get("applied_filter_signature") != filter_signature:
    st.warning("Filters have changed. Click **Get Insights** to refresh the report.")
if activities.empty:
    st.warning("No activities match the selected filters. Adjust the filters and process again.")
    st.stop()

applied_date_from, applied_date_to = st.session_state.get("applied_date_range", (None, None))
report_model = build_report_model(
    activities,
    applied_date_from,
    applied_date_to,
    st.session_state.get("applied_filters"),
)

with st.container(border=True):
    render_report(report_model)
    st.markdown('<div class="report-export-divider"></div>', unsafe_allow_html=True)
    _, color_column, export_column = st.columns(
        [4, 0.8, 1.2],
        vertical_alignment="bottom",
    )
    with color_column:
        st.color_picker(
            "Background color",
            value=default_background_hex,
            key="report_background_color",
            help="Preview the background color used by the page and exported PDF.",
            width="stretch",
        )
    with export_column:
        st.download_button(
            "Export as PDF",
            data=prepare_pdf_download(report_model, selected_background_rgb),
            file_name="activity_report.pdf",
            mime="application/pdf",
            help="Download a PDF version of the report section.",
            on_click="ignore",
            width="stretch",
        )

with st.expander(f"View filtered activities ({len(activities)})"):
    visible_columns = [column for column in activities.columns if not column.startswith("_")]
    st.dataframe(activities[visible_columns], width="stretch", hide_index=True)
