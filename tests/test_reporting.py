import unittest
from datetime import date

import pandas as pd

from reporting import (
    NAVY,
    PDF_FONT_REGULAR,
    SPEED_DISTRIBUTION_BAR_SIZE,
    build_calendar_heatmap,
    build_calendar_heatmap_chart,
    build_hourly_heatmap,
    build_hourly_heatmap_chart,
    build_monthly_performance,
    build_performance_row,
    build_report_context,
    build_report_model,
    build_report_pdf,
    build_ride_metrics,
    build_speed_distribution,
    build_speed_distribution_chart,
    build_speed_distribution_coverage,
    build_summary_metrics,
    build_yearly_distance_chart,
    build_yearly_speed_chart,
    build_yearly_statistics,
    format_hours,
    format_number,
    format_pace,
)
from theme import APP_FONT_CSS


def activities_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame["_date"] = pd.to_datetime(frame["_date"], format="mixed")
    defaults = {
        "_type": "Ride",
        "_name": "Test activity",
        "_gear": "",
        "_moving_hours": 1.0,
        "_avg_speed_kmh": 20.0,
        "_elevation_m": 0.0,
        "_calories": float("nan"),
        "_avg_hr": float("nan"),
        "_avg_watts": float("nan"),
        "_relative_effort": float("nan"),
    }
    for column, value in defaults.items():
        if column not in frame:
            frame[column] = value
    return frame


class MonthlyPerformanceTests(unittest.TestCase):
    def test_includes_empty_months_in_selected_range(self) -> None:
        activities = activities_frame([
            {"_date": "2024-01-10", "_distance_km": 20.0},
            {"_date": "2024-03-10", "_distance_km": 30.0},
        ])

        monthly = build_monthly_performance(
            activities,
            date(2024, 1, 1),
            date(2024, 3, 31),
        )

        self.assertEqual(
            [row["Month"] for row in monthly],
            ["January 2024", "February 2024", "March 2024"],
        )
        self.assertEqual(monthly[1]["Activity count"], 0)
        self.assertEqual(monthly[1]["Distance (km)"], 0.0)

    def test_uses_distance_weighted_overall_speed(self) -> None:
        activities = activities_frame([
            {"_date": "2024-01-10", "_distance_km": 20.0, "_moving_hours": 1.0},
            {"_date": "2024-01-11", "_distance_km": 30.0, "_moving_hours": 2.0},
        ])

        row = build_monthly_performance(activities)[0]

        self.assertEqual(row["Average speed (km/h)"], 16.7)
        self.assertLess(
            list(row).index("Average speed (km/h)"),
            list(row).index("Average heart rate (bpm)"),
        )


class YearlyStatisticsTests(unittest.TestCase):
    def test_totals_distance_and_includes_empty_years(self) -> None:
        activities = activities_frame([
            {"_date": "2023-01-10", "_distance_km": 20.0},
            {"_date": "2023-06-10", "_distance_km": 30.0},
            {"_date": "2025-03-10", "_distance_km": 40.0},
        ])

        yearly = build_yearly_statistics(
            activities,
            date(2023, 1, 1),
            date(2025, 12, 31),
        )

        self.assertEqual(yearly["Year"].tolist(), ["2023", "2024", "2025"])
        self.assertEqual(yearly["Distance (km)"].tolist(), [50.0, 0.0, 40.0])
        self.assertEqual(yearly.loc[0, "Overall average speed (km/h)"], 25.0)
        self.assertTrue(pd.isna(yearly.loc[1, "Overall average speed (km/h)"]))
        self.assertEqual(yearly.loc[2, "Overall average speed (km/h)"], 40.0)

    def test_speed_uses_only_rows_with_both_distance_and_time(self) -> None:
        activities = activities_frame([
            {"_date": "2024-01-10", "_distance_km": 20.0, "_moving_hours": 1.0},
            {"_date": "2024-01-11", "_distance_km": 30.0, "_moving_hours": None},
            {"_date": "2024-01-12", "_distance_km": None, "_moving_hours": 2.0},
        ])

        yearly = build_yearly_statistics(activities)

        self.assertEqual(yearly.loc[0, "Distance (km)"], 50.0)
        self.assertEqual(yearly.loc[0, "Overall average speed (km/h)"], 20.0)

    def test_distinguishes_missing_distance_from_an_empty_year(self) -> None:
        activities = activities_frame([
            {"_date": "2024-01-10", "_distance_km": None},
        ])

        yearly = build_yearly_statistics(
            activities, date(2023, 1, 1), date(2025, 12, 31)
        )

        self.assertEqual(yearly.loc[0, "Distance (km)"], 0.0)
        self.assertTrue(pd.isna(yearly.loc[1, "Distance (km)"]))
        self.assertEqual(yearly.loc[2, "Distance (km)"], 0.0)

    def test_chart_axes_are_explicitly_visible(self) -> None:
        yearly = pd.DataFrame({
            "Year": ["2023", "2024"],
            "Distance (km)": [100.0, 150.0],
            "Overall average speed (km/h)": [20.0, 22.5],
        })

        for chart in (
            build_yearly_distance_chart(yearly),
            build_yearly_speed_chart(yearly),
        ):
            spec = chart.to_dict()
            encoding = spec["layer"][0]["encoding"]
            for channel in ("x", "y"):
                axis = encoding[channel]["axis"]
                self.assertTrue(axis["domain"])
                self.assertTrue(axis["labels"])
                self.assertTrue(axis["ticks"])
                self.assertEqual(axis["labelColor"], NAVY)
                self.assertEqual(axis["labelFont"], APP_FONT_CSS)

            self.assertFalse(encoding["x"]["axis"]["labelOverlap"])
            self.assertEqual(encoding["y"]["axis"]["gridColor"], "#E1E7EF")


class SpeedDistributionTests(unittest.TestCase):
    def test_uses_complete_non_overlapping_two_kilometre_ranges(self) -> None:
        activities = activities_frame([
            {
                "_date": "2024-01-01",
                "_distance_km": None if speed is None or speed < 0 else 1.0,
                "_moving_hours": None if speed is None or speed < 0 else 1.0,
                "_avg_speed_kmh": speed,
            }
            for speed in [-1.0, None, 0.0, 10.0, 10.1, 12.0, 12.1, 38.0, 38.1, 39.9, 40.0, 42.0]
        ])

        distribution = build_speed_distribution(activities)
        counts = distribution.set_index("Range")["Activity count"]

        self.assertEqual(len(distribution), 17)
        self.assertEqual(int(counts.sum()), 10)
        self.assertEqual(counts["<10"], 1)
        self.assertEqual(counts["[10,12)"], 2)
        self.assertEqual(counts["[12,14)"], 2)
        self.assertEqual(counts["[36,38)"], 0)
        self.assertEqual(counts["[38,40)"], 3)
        self.assertEqual(counts[">=40"], 2)
        self.assertEqual(distribution.iloc[-2]["Definition"], "[38,40)")

    def test_uses_distance_and_time_when_exported_speed_is_unusable(self) -> None:
        activities = activities_frame([
            {
                "_date": "2024-01-01",
                "_avg_speed_kmh": None,
                "_distance_km": 20.0,
                "_moving_hours": 1.0,
            },
            {
                "_date": "2024-01-02",
                "_avg_speed_kmh": -1.0,
                "_distance_km": 30.0,
                "_moving_hours": 2.0,
            },
            {
                "_date": "2024-01-03",
                "_avg_speed_kmh": None,
                "_distance_km": None,
                "_moving_hours": 1.0,
            },
        ])

        distribution = build_speed_distribution(activities).set_index("Range")
        coverage = build_speed_distribution_coverage(activities)

        self.assertEqual(int(distribution["Activity count"].sum()), 2)
        self.assertEqual(distribution.loc["[14,16)", "Activity count"], 1)
        self.assertEqual(distribution.loc["[20,22)", "Activity count"], 1)
        self.assertEqual(coverage["available"], 2)
        self.assertEqual(coverage["total"], 3)
        self.assertEqual(
            coverage["label"],
            "Distribution includes 2 of 3 activities with usable speed data.",
        )

    def test_sums_distances_for_activities_in_each_speed_range(self) -> None:
        activities = activities_frame([
            {
                "_date": "2024-01-01",
                "_avg_speed_kmh": speed,
                "_distance_km": distance,
            }
            for speed, distance in [
                (20.1, 10.0),
                (20.5, 20.0),
                (21.0, 30.0),
                (21.9, 40.0),
                (22.0, 50.0),
            ]
        ])

        distribution = build_speed_distribution(activities).set_index("Range")

        self.assertEqual(distribution.loc["[20,22)", "Activity count"], 4)
        self.assertEqual(distribution.loc["[20,22)", "Distance (km)"], 100.0)
        self.assertEqual(distribution.loc["[22,24)", "Activity count"], 1)
        self.assertEqual(distribution.loc["[22,24)", "Distance (km)"], 50.0)

    def test_chart_displays_activity_counts_as_labels(self) -> None:
        activities = activities_frame([
            {"_date": "2024-01-01", "_distance_km": 1.0, "_avg_speed_kmh": 20.0},
        ])
        chart = build_speed_distribution_chart(build_speed_distribution(activities))
        spec = chart.to_dict()

        self.assertEqual(spec["layer"][1]["encoding"]["text"]["field"], "Activity count")
        self.assertIsNone(spec["layer"][0]["encoding"]["y"]["title"])
        self.assertEqual(spec["layer"][0]["mark"]["size"], SPEED_DISTRIBUTION_BAR_SIZE)
        tooltip = spec["layer"][0]["encoding"]["tooltip"]
        self.assertEqual([field["title"] for field in tooltip], [
            "Speed range (km/h)",
            "Activity count",
            "Distance (km)",
        ])
        self.assertEqual(tooltip[2]["format"], ".1f")


class CalendarHeatmapTests(unittest.TestCase):
    def test_includes_every_leap_year_day_and_aggregates_across_years(self) -> None:
        activities = activities_frame([
            {"_date": "2018-05-26"},
            {"_date": "2022-05-26"},
            {"_date": "2022-05-26 18:00"},
            {"_date": "2024-02-29"},
            {"_date": None},
        ])

        calendar = build_calendar_heatmap(activities)
        by_day = calendar.set_index("Calendar day")

        self.assertEqual(len(calendar), 366)
        self.assertIn("February 29", by_day.index)
        self.assertEqual(by_day.loc["February 29", "Activity count"], 1)
        self.assertEqual(by_day.loc["May 26", "Activity count"], 3)
        self.assertEqual(int(calendar["Activity count"].sum()), 4)
        self.assertEqual(calendar["Is peak"].sum(), 1)
        self.assertTrue(by_day.loc["May 26", "Is peak"])

    def test_marks_the_earliest_day_when_maximum_counts_are_tied(self) -> None:
        activities = activities_frame([
            {"_date": "2020-01-01"},
            {"_date": "2021-12-31"},
        ])

        calendar = build_calendar_heatmap(activities).set_index("Calendar day")

        self.assertTrue(calendar.loc["January 1", "Is peak"])
        self.assertFalse(calendar.loc["December 31", "Is peak"])

    def test_chart_uses_a_diamond_for_the_peak_day(self) -> None:
        calendar = build_calendar_heatmap(activities_frame([
            {"_date": "2024-05-26"},
        ]))

        spec = build_calendar_heatmap_chart(calendar).to_dict()

        self.assertEqual(spec["layer"][0]["mark"]["type"], "rect")
        self.assertEqual(spec["layer"][1]["mark"]["shape"], "diamond")
        self.assertIn("Is peak", spec["layer"][1]["transform"][0]["filter"])
        self.assertEqual(len(spec["datasets"][next(iter(spec["datasets"]))]), 366)

    def test_hourly_heatmap_contains_all_hours_and_aggregates_start_times(self) -> None:
        activities = activities_frame([
            {"_date": "2018-05-26 06:10"},
            {"_date": "2022-01-01 06:45"},
            {"_date": "2024-02-29 23:59"},
            {"_date": None},
        ])

        hours = build_hourly_heatmap(activities).set_index("Hour")

        self.assertEqual(len(hours), 24)
        self.assertEqual(hours.loc[6, "Activity count"], 2)
        self.assertEqual(hours.loc[23, "Activity count"], 1)
        self.assertEqual(int(hours["Activity count"].sum()), 3)
        self.assertEqual(hours.loc[23, "Start hour"], "23:00-24:00")
        self.assertTrue(hours.loc[6, "Is peak"])
        self.assertEqual(hours["Is peak"].sum(), 1)

    def test_heatmaps_preserve_offset_timestamp_local_day_and_hour(self) -> None:
        activities = activities_frame([
            {"_date": "2024-01-01T00:30:00+02:00"},
        ])

        calendar = build_calendar_heatmap(activities).set_index("Calendar day")
        hours = build_hourly_heatmap(activities).set_index("Hour")

        self.assertEqual(calendar.loc["January 1", "Activity count"], 1)
        self.assertEqual(calendar.loc["December 31", "Activity count"], 0)
        self.assertEqual(hours.loc[0, "Activity count"], 1)

    def test_hourly_heatmap_marks_earliest_hour_when_counts_are_tied(self) -> None:
        activities = activities_frame([
            {"_date": "2024-01-01 08:00"},
            {"_date": "2024-01-01 18:00"},
        ])

        hours = build_hourly_heatmap(activities).set_index("Hour")

        self.assertTrue(hours.loc[8, "Is peak"])
        self.assertFalse(hours.loc[18, "Is peak"])

    def test_hourly_chart_uses_24_cells_and_a_diamond_peak_marker(self) -> None:
        hours = build_hourly_heatmap(activities_frame([
            {"_date": "2024-01-01 08:00"},
        ]))

        spec = build_hourly_heatmap_chart(hours).to_dict()

        self.assertEqual(spec["layer"][0]["mark"]["type"], "rect")
        self.assertEqual(spec["layer"][1]["mark"]["shape"], "diamond")
        self.assertEqual(len(spec["datasets"][next(iter(spec["datasets"]))]), 24)
        tooltip = spec["layer"][0]["encoding"]["tooltip"]
        self.assertEqual(
            [field["title"] for field in tooltip],
            ["Start hour", "Activity count"],
        )


class RideMetricsTests(unittest.TestCase):
    def test_eddington_combines_multiple_rides_on_the_same_day(self) -> None:
        activities = activities_frame([
            {"_date": "2024-01-01 08:00", "_distance_km": 1.5},
            {"_date": "2024-01-01 17:00", "_distance_km": 1.5},
            {"_date": "2024-01-02", "_distance_km": 2.0},
            {"_date": "2024-01-03", "_distance_km": 1.0},
        ])

        metrics = build_ride_metrics(activities)

        self.assertIsNotNone(metrics)
        self.assertEqual(metrics["metrics"][0]["value"], "2")

    def test_metrics_are_not_built_for_non_ride_activities(self) -> None:
        activities = activities_frame([
            {"_date": "2024-01-01", "_distance_km": 5.0, "_type": "Run"},
        ])

        self.assertIsNone(build_ride_metrics(activities))

    def test_calculates_weekly_streak_and_active_week_coverage(self) -> None:
        activities = activities_frame([
            {"_date": "2024-01-01", "_distance_km": 10.0},
            {"_date": "2024-01-08", "_distance_km": 10.0},
            {"_date": "2024-01-29", "_distance_km": 10.0},
        ])

        metrics = build_ride_metrics(activities)["metrics"]

        self.assertEqual(metrics[1]["value"], "2 weeks")
        self.assertEqual(metrics[2]["value"], "3 of 5")

    def test_weekly_metrics_include_rides_without_distance(self) -> None:
        activities = activities_frame([
            {"_date": "2024-01-01", "_distance_km": 10.0},
            {"_date": "2024-01-08", "_distance_km": None},
        ])

        metrics = build_ride_metrics(activities)["metrics"]

        self.assertEqual(metrics[0]["value"], "1")
        self.assertEqual(metrics[1]["value"], "2 weeks")
        self.assertEqual(metrics[2]["value"], "2 of 2")

    def test_active_week_coverage_uses_the_selected_date_range(self) -> None:
        activities = activities_frame([
            {"_date": "2024-01-08", "_distance_km": 10.0},
        ])

        metrics = build_ride_metrics(
            activities, date(2024, 1, 1), date(2024, 1, 28)
        )["metrics"]

        self.assertEqual(metrics[2]["value"], "1 of 4")
        self.assertEqual(metrics[2]["detail"], "25% of the selected period")


class ReportModelTests(unittest.TestCase):
    def test_formats_duration_and_pace_edge_cases(self) -> None:
        self.assertEqual(format_hours(1.5), "1h 30m")
        self.assertEqual(format_hours(float("nan")), "-")
        self.assertEqual(format_pace(12), "5:00 min/km")
        self.assertEqual(format_pace(0), "-")
        self.assertEqual(format_number(14000, 0), "14000")
        self.assertEqual(format_number(70.8, 1), "70.8")

    def test_performance_uses_weighted_speed_and_coverage_thresholds(self) -> None:
        activities = activities_frame([
            {
                "_date": "2024-01-01",
                "_distance_km": 20.0,
                "_moving_hours": 1.0,
                "_avg_speed_kmh": 20.0,
                "_avg_hr": 140.0,
                "_avg_watts": 180.0,
            },
            {
                "_date": "2024-01-02",
                "_distance_km": 40.0,
                "_moving_hours": 3.0,
                "_avg_speed_kmh": 40.0,
            },
        ])

        row = build_performance_row(activities, "Ride")

        self.assertEqual(row["Overall average speed (km/h)"], 15.0)
        self.assertEqual(row["Average heart rate (bpm)"], "140")
        self.assertEqual(row["Average power (W)"], "180")

    def test_summary_metrics_have_the_requested_labels_and_values(self) -> None:
        activities = activities_frame([
            {
                "_date": "2024-01-01",
                "_distance_km": 20.0,
                "_moving_hours": 1.0,
                "_elevation_m": 100.0,
                "_avg_watts": 180.0,
            },
            {
                "_date": "2024-01-02",
                "_distance_km": 40.0,
                "_moving_hours": 2.0,
                "_elevation_m": 300.0,
                "_avg_watts": 220.0,
            },
        ])

        metrics = build_summary_metrics(activities)

        self.assertEqual(
            [metric["label"] for metric in metrics],
            [
                "Activity count",
                "Distance (km)",
                "Moving time (h)",
                "Average distance (km)",
                "Elevation gain (m)",
                "Average speed (km/h)",
                "Average power (W)",
                "Average pace (min/km)",
            ],
        )
        self.assertEqual(
            [metric["value"] for metric in metrics],
            ["2", "60.0", "3.0", "30.0", "400", "20.0", "200", "-"],
        )

    def test_summary_metrics_show_pace_for_running(self) -> None:
        activities = activities_frame([
            {
                "_date": "2024-01-01",
                "_type": "Run",
                "_distance_km": 10.0,
                "_moving_hours": 1.0,
            },
        ])

        summary = {
            metric["label"]: metric["value"]
            for metric in build_summary_metrics(activities)
        }

        self.assertEqual(summary["Average speed (km/h)"], "10.0")
        self.assertEqual(summary["Average power (W)"], "-")
        self.assertEqual(summary["Average pace (min/km)"], "6:00")

    def test_partial_rows_do_not_mix_unrelated_distance_and_time(self) -> None:
        activities = activities_frame([
            {
                "_date": "2024-01-01",
                "_gear": "Bike A",
                "_distance_km": 20.0,
                "_moving_hours": 1.0,
            },
            {
                "_date": "2024-01-02",
                "_gear": "Bike A",
                "_distance_km": 30.0,
                "_moving_hours": None,
            },
            {
                "_date": "2024-01-03",
                "_gear": "Bike A",
                "_distance_km": None,
                "_moving_hours": 2.0,
            },
        ])

        model = build_report_model(activities)

        summary = {metric["label"]: metric["value"] for metric in model["summary_metrics"]}
        self.assertEqual(summary["Average speed (km/h)"], "20.0")
        self.assertEqual(model["gear"].loc[0, "Average_distance"], 25.0)
        self.assertEqual(model["gear"].loc[0, "Overall_average_speed"], 20.0)

    def test_pdf_handles_reports_with_missing_distance_and_time(self) -> None:
        activities = activities_frame([
            {
                "_date": "2024-01-01",
                "_gear": "Bike A",
                "_distance_km": None,
                "_moving_hours": None,
            },
        ])

        model = build_report_model(activities)

        self.assertTrue(pd.isna(model["gear"].loc[0, "Distance_km"]))
        pdf = build_report_pdf(model)
        self.assertTrue(pdf.startswith(b"%PDF"))
        if PDF_FONT_REGULAR.startswith("Avenir"):
            self.assertIn(b"Avenir", pdf)

    def test_invalid_measurements_do_not_corrupt_metrics_or_pdf(self) -> None:
        activities = activities_frame([
            {
                "_date": "2024-01-01",
                "_name": "Invalid ride",
                "_gear": "Bike A",
                "_distance_km": float("inf"),
                "_moving_hours": -1.0,
                "_avg_speed_kmh": float("inf"),
                "_elevation_m": -100.0,
                "_calories": float("inf"),
                "_avg_hr": float("inf"),
                "_avg_watts": -20.0,
                "_relative_effort": -1.0,
            },
            {
                "_date": "2024-01-02",
                "_name": "Valid ride",
                "_gear": "Bike A",
                "_distance_km": 20.0,
                "_moving_hours": 1.0,
                "_avg_speed_kmh": 20.0,
                "_elevation_m": 200.0,
                "_calories": 400.0,
                "_avg_hr": 140.0,
                "_avg_watts": 200.0,
                "_relative_effort": 30.0,
            },
        ])

        model = build_report_model(activities)
        summary = {metric["label"]: metric["value"] for metric in model["summary_metrics"]}

        self.assertEqual(summary["Distance (km)"], "20.0")
        self.assertEqual(summary["Moving time (h)"], "1.0")
        self.assertEqual(summary["Elevation gain (m)"], "200")
        self.assertEqual(summary["Average speed (km/h)"], "20.0")
        self.assertNotIn("inf", str(model).lower())
        self.assertTrue(build_report_pdf(model).startswith(b"%PDF"))

    def test_context_describes_selected_range_and_active_filters(self) -> None:
        activities = activities_frame([
            {"_date": "2024-02-10", "_distance_km": 20.0},
        ])

        context = build_report_context(
            activities,
            date(2024, 1, 1),
            date(2024, 3, 31),
            {
                "name_search": "morning & <fast>",
                "series": ["Joe"],
                "gears": ["Bike A"],
                "distance_range": (10.0, 50.0),
                "speed_range": (20.0, 30.0),
            },
        )

        self.assertIn("Date: 01 Jan 2024 - 31 Mar 2024", context)
        self.assertIn('Name contains: "morning & <fast>"', context)
        self.assertIn("Series: Joe", context)
        self.assertIn("Gear: Bike A", context)
        self.assertIn("Distance: 10.0-50.0 km", context)
        self.assertIn("Speed: 20.0-30.0 km/h", context)
        self.assertNotIn("1 activities", context)

        model = build_report_model(
            activities,
            date(2024, 1, 1),
            date(2024, 3, 31),
            {"name_search": "morning & <fast>"},
        )
        self.assertTrue(build_report_pdf(model).startswith(b"%PDF"))

    def test_model_builds_highlights_gear_totals_and_pdf(self) -> None:
        activities = activities_frame([
            {
                "_date": "2024-01-01",
                "_name": "Short ride",
                "_gear": "Bike A",
                "_distance_km": 20.0,
                "_moving_hours": 1.0,
                "_avg_speed_kmh": 20.0,
                "_elevation_m": 100.0,
                "_calories": 400.0,
                "_relative_effort": 30.0,
            },
            {
                "_date": "2024-01-02",
                "_name": "Long ride",
                "_gear": "Bike A",
                "_distance_km": 60.0,
                "_moving_hours": 2.0,
                "_avg_speed_kmh": 30.0,
                "_elevation_m": 500.0,
                "_calories": 900.0,
                "_relative_effort": 80.0,
            },
        ])

        model = build_report_model(activities)

        self.assertEqual(model["highlights"][0]["Activity"], "Long ride")
        self.assertEqual(model["highlights"][4]["Highlight"], "Highest average speed")
        self.assertEqual(model["highlights"][5]["Highlight"], "Lowest average speed")
        self.assertEqual(model["highlights"][3]["Value"], "900")
        self.assertEqual(model["gear"].loc[0, "Activity_count"], 2)
        self.assertEqual(model["gear"].loc[0, "Distance_km"], 80.0)
        self.assertEqual(model["gear"].loc[0, "Overall_average_speed"], 80 / 3)
        self.assertTrue(build_report_pdf(model).startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
