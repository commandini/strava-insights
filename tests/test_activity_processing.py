import unittest
from datetime import date

import pandas as pd

from activity_processing import filter_activities, prepare_activities


class PrepareActivitiesTests(unittest.TestCase):
    def test_normalizes_detailed_export_units_and_series(self) -> None:
        activities = prepare_activities(
            (
                "Activity Date,Activity Type,Activity Name,Activity Gear,Distance,Moving Time,"
                "Average Speed,Elevation Gain,Average Heart Rate\n"
                "2024-01-02,Ride,Joe[0],Road bike,36000,3600,10,420,145\n"
                '2024-01-03,Ride,"Joe[3,4]",Road bike,18000,1800,10,210,\n'
            ).encode()
        )

        self.assertEqual(activities["_distance_km"].tolist(), [36.0, 18.0])
        self.assertEqual(activities["_avg_speed_kmh"].tolist(), [36.0, 36.0])
        self.assertEqual(activities["_moving_hours"].tolist(), [1.0, 0.5])
        self.assertEqual(activities["_series"].tolist(), ["Joe", "Joe"])
        self.assertEqual(activities["_gear"].tolist(), ["Road bike", "Road bike"])
        self.assertEqual(activities.loc[0, "_avg_hr"], 145)

    def test_keeps_summary_export_distance_and_speed_in_kilometres(self) -> None:
        activities = prepare_activities(
            (
                "Date,Type,Name,Gear,Distance,Moving Time,Average Speed\n"
                "2024-01-02,Run,Tempo,Shoes,10,3600,10\n"
                "2024-01-03,Run,Long run,Shoes,20,7200,10\n"
            ).encode()
        )

        self.assertEqual(activities["_distance_km"].tolist(), [10, 20])
        self.assertEqual(activities["_avg_speed_kmh"].tolist(), [10, 10])
        self.assertEqual(activities["_type"].tolist(), ["Run", "Run"])

    def test_recovers_row_values_from_duplicate_distance_columns(self) -> None:
        activities = prepare_activities(
            (
                "Activity Date,Activity Type,Distance,Distance,Moving Time,Average Speed\n"
                "2024-01-02,Ride,85000,.,10800,7.87\n"
                "2024-01-03,Ride,,42000,5400,7.78\n"
            ).encode()
        )

        self.assertEqual(activities["_distance_km"].tolist(), [85.0, 42.0])

    def test_missing_optional_columns_produce_safe_defaults(self) -> None:
        activities = prepare_activities(b"Activity Name\nUntimed activity\n")

        self.assertEqual(activities.loc[0, "_type"], "Unknown")
        self.assertEqual(activities.loc[0, "_gear"], "")
        self.assertTrue(pd.isna(activities.loc[0, "_date"]))
        for column in (
            "_distance_km",
            "_moving_hours",
            "_avg_speed_kmh",
            "_elevation_m",
            "_calories",
            "_avg_hr",
            "_avg_watts",
            "_relative_effort",
        ):
            self.assertTrue(pd.isna(activities.loc[0, column]), column)

    def test_falls_back_to_populated_aliases_for_each_row(self) -> None:
        activities = prepare_activities(
            (
                "Activity Date,Start Time,Activity Type,Type,Activity Name,Name,"
                "Activity Gear,Gear,Distance,Grade Adjusted Distance,Moving Time,Average Speed\n"
                ",2024-02-03T10:00:00Z,,run,,Fallback name,,Shoes,not recorded,10,3600,10\n"
            ).encode()
        )

        self.assertEqual(activities.loc[0, "_date"], pd.Timestamp("2024-02-03 10:00:00"))
        self.assertEqual(activities.loc[0, "_type"], "Run")
        self.assertEqual(activities.loc[0, "_name"], "Fallback name")
        self.assertEqual(activities.loc[0, "_gear"], "Shoes")
        self.assertEqual(activities.loc[0, "_distance_km"], 10)

    def test_preserves_local_calendar_values_for_mixed_timezone_dates(self) -> None:
        activities = prepare_activities(
            (
                "Activity Date,Activity Type,Distance,Moving Time,Average Speed\n"
                "2024-01-01 10:00:00,Ride,10,3600,10\n"
                "2024-01-02T10:00:00+02:00,Ride,10,3600,10\n"
            ).encode()
        )

        self.assertEqual(str(activities["_date"].dtype), "datetime64[ns]")
        self.assertEqual(activities.loc[1, "_date"], pd.Timestamp("2024-01-02 10:00:00"))

    def test_rejects_non_finite_and_negative_measurements(self) -> None:
        activities = prepare_activities(
            (
                "Date,Type,Distance,Moving Time,Average Speed,Elevation Gain,Calories,"
                "Average Heart Rate,Average Watts,Relative Effort\n"
                "2024-01-01,Ride,inf,-3600,-20,-10,inf,-1,-50,-2\n"
            ).encode()
        )

        for column in (
            "_distance_km",
            "_moving_hours",
            "_avg_speed_kmh",
            "_elevation_m",
            "_calories",
            "_avg_hr",
            "_avg_watts",
            "_relative_effort",
        ):
            self.assertTrue(pd.isna(activities.loc[0, column]), column)

    def test_uses_detailed_export_units_without_speed_or_time_evidence(self) -> None:
        activities = prepare_activities(
            b"Activity ID,Activity Date,Activity Type,Distance\n1,2024-01-01,Walk,400\n"
        )

        self.assertEqual(activities.loc[0, "_distance_km"], 0.4)

    def test_warns_when_units_cannot_be_verified(self) -> None:
        activities = prepare_activities(
            b"Activity Date,Activity Type,Distance\n2024-01-01,Walk,400\n"
        )

        self.assertIn("could not be verified", activities.attrs["unit_inference_warning"])

    def test_uses_motion_consistency_to_infer_distance_units(self) -> None:
        kilometres = prepare_activities(
            b"Activity Type,Distance,Moving Time,Average Speed\nRide,600,72000,30\n"
        )
        metres = prepare_activities(
            b"Activity Type,Distance,Moving Time,Average Speed\nWalk,400,120,3.333333\n"
        )

        self.assertEqual(kilometres.loc[0, "_distance_km"], 600)
        self.assertEqual(kilometres.loc[0, "_avg_speed_kmh"], 30)
        self.assertAlmostEqual(metres.loc[0, "_distance_km"], 0.4)
        self.assertAlmostEqual(metres.loc[0, "_avg_speed_kmh"], 12, places=5)


class FilterActivitiesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.activities = pd.DataFrame(
            {
                "_date": pd.to_datetime(["2024-01-01", "2024-01-15", "2024-02-01"]),
                "_name": ["Joe[0]", "Joe. Recovery", "Other"],
                "_series": ["Joe", "Joe", "Other"],
                "_type": ["Ride", "Ride", "Run"],
                "_distance_km": [20.0, 40.0, 10.0],
                "_gear": ["Bike A", "Bike B", "Shoes"],
                "_avg_speed_kmh": [20.0, 25.0, 10.0],
            }
        )

    def test_combines_filters_inclusively_and_uses_literal_name_search(self) -> None:
        filtered = filter_activities(
            self.activities,
            date(2024, 1, 1),
            date(2024, 1, 31),
            "joe[",
            ["Joe"],
            "Ride",
            20.0,
            40.0,
            ["Bike A"],
            20.0,
            25.0,
        )

        self.assertEqual(filtered["_name"].tolist(), ["Joe[0]"])
        self.assertEqual(filtered.index.tolist(), [0])

    def test_requires_an_activity_type(self) -> None:
        filtered = filter_activities(
            self.activities, None, None, "", [], None, 0, 100, [], 0, 100
        )

        self.assertTrue(filtered.empty)

    def test_full_ranges_keep_activities_with_unknown_filter_values(self) -> None:
        activities = self.activities.copy()
        activities.loc[1, "_distance_km"] = float("nan")
        activities.loc[2, "_avg_speed_kmh"] = float("nan")
        activities.loc[2, "_date"] = pd.NaT

        filtered = filter_activities(
            activities,
            date(2024, 1, 1),
            date(2024, 1, 31),
            "",
            [],
            "Ride",
            10,
            20,
            [],
            10,
            25,
        )

        self.assertEqual(filtered["_name"].tolist(), ["Joe[0]", "Joe. Recovery"])

    def test_narrowed_ranges_exclude_unknown_values(self) -> None:
        activities = self.activities.copy()
        activities.loc[1, "_distance_km"] = float("nan")

        filtered = filter_activities(
            activities, None, None, "", [], "Ride", 15, 25, [], 15, 30
        )

        self.assertEqual(filtered["_name"].tolist(), ["Joe[0]"])

    def test_speed_filter_uses_distance_time_fallback(self) -> None:
        activities = self.activities.copy()
        activities["_moving_hours"] = [1.0, 2.0, 1.0]
        activities.loc[1, "_avg_speed_kmh"] = float("nan")

        filtered = filter_activities(
            activities, None, None, "", [], "Ride", 0, 100, [], 19, 21
        )

        self.assertEqual(filtered["_name"].tolist(), ["Joe[0]", "Joe. Recovery"])


if __name__ == "__main__":
    unittest.main()
