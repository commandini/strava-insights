import unittest
from datetime import date

import pandas as pd
from streamlit.testing.v1 import AppTest


class ApplicationSmokeTests(unittest.TestCase):
    def test_initial_page_renders_without_exceptions(self) -> None:
        app = AppTest.from_file("app.py").run(timeout=10)

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.title[0].value, "Strava Insights")
        self.assertIn("Get Insights", app.info[0].value)

    def test_processed_report_renders_with_partial_activity_data(self) -> None:
        activities = pd.DataFrame({
            "_date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
            "_type": ["Ride", "Ride"],
            "_name": ["Complete ride", "Partial ride"],
            "_series": ["Complete ride", "Partial ride"],
            "_gear": ["Bike", "Bike"],
            "_distance_km": [20.0, None],
            "_moving_hours": [1.0, 2.0],
            "_avg_speed_kmh": [20.0, None],
            "_elevation_m": [100.0, None],
            "_calories": [400.0, None],
            "_avg_hr": [140.0, None],
            "_avg_watts": [180.0, None],
            "_relative_effort": [30.0, None],
        })
        app = AppTest.from_file("app.py")
        app.session_state["activities"] = activities
        app.session_state["applied_date_range"] = (
            date(2024, 1, 1),
            date(2024, 2, 29),
        )
        app.session_state["applied_filters"] = {
            "name_search": "",
            "series": [],
            "gears": [],
            "distance_range": None,
            "speed_range": None,
        }

        app.run(timeout=20)

        self.assertEqual(len(app.exception), 0)
        report_sections = [item.value for item in app.subheader]
        self.assertNotIn("Overall performance", report_sections)
        self.assertEqual(report_sections[1], "Metrics")
        self.assertEqual(report_sections[2], "Heatmaps")
        self.assertIn("Monthly Performance", [item.value for item in app.subheader])
        self.assertIn("Yearly Performance", [item.value for item in app.subheader])
        self.assertEqual(app.metric[0].label, "Activity count")
        self.assertEqual(app.metric[7].label, "Average pace (min/km)")
        self.assertEqual(app.metric[8].label, "Metric Eddington number")
        self.assertIn("Average speed (km/h)", app.dataframe[0].value.columns)
        self.assertNotIn("Overall average speed (km/h)", app.dataframe[0].value.columns)
        self.assertIn("Average speed (km/h)", app.dataframe[2].value.columns)
        self.assertNotIn("Overall average speed (km/h)", app.dataframe[2].value.columns)


if __name__ == "__main__":
    unittest.main()
