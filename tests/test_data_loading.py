import unittest

import pandas as pd

from data_loading import read_activities_csv


class DuplicateColumnTests(unittest.TestCase):
    def test_rejects_empty_and_blank_files_consistently(self) -> None:
        for file_bytes in (b"", b"\n"):
            with self.subTest(file_bytes=file_bytes), self.assertRaisesRegex(
                ValueError, "CSV file is empty"
            ):
                read_activities_csv(file_bytes)

    def test_reads_a_utf8_bom_and_assigns_unique_blank_header_names(self) -> None:
        frame = read_activities_csv("\ufeff,Distance,\nA,10,B\n".encode())

        self.assertEqual(list(frame.columns), ["Unnamed: 0", "Distance", "Unnamed: 2"])
        self.assertEqual(frame.loc[0, "Distance"], 10)

    def test_coalesces_duplicate_columns_row_by_row(self) -> None:
        csv_bytes = (
            "Activity,Distance,Distance\n"
            "Morning ride,85,.\n"
            "Evening ride,,42\n"
            "Lunch ride,10,11\n"
        ).encode()

        frame = read_activities_csv(csv_bytes)

        self.assertEqual(list(frame.columns), ["Activity", "Distance"])
        self.assertEqual(frame["Distance"].tolist(), [85.0, 42.0, 10.0])

    def test_prefers_the_duplicate_with_better_data_coverage(self) -> None:
        csv_bytes = (
            "Distance,Distance\n"
            "1,90\n"
            ".,80\n"
            ",70\n"
        ).encode()

        frame = read_activities_csv(csv_bytes)

        self.assertEqual(frame["Distance"].tolist(), [90, 80, 70])

    def test_treats_common_placeholder_values_as_missing(self) -> None:
        csv_bytes = (
            "Distance,Distance\n"
            ".,1\n"
            "--,2\n"
            "null,3\n"
            "N/A,4\n"
        ).encode()

        frame = read_activities_csv(csv_bytes)

        self.assertEqual(frame["Distance"].tolist(), [1, 2, 3, 4])

    def test_does_not_merge_distinct_dot_suffixed_names(self) -> None:
        frame = read_activities_csv(b"Distance,Distance.1\n10,20\n")

        self.assertEqual(list(frame.columns), ["Distance", "Distance.1"])
        pd.testing.assert_series_equal(
            frame["Distance.1"],
            pd.Series([20], name="Distance.1"),
        )


if __name__ == "__main__":
    unittest.main()
