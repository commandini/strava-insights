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

    def test_rejects_extra_fields_even_when_pandas_could_infer_an_index(self) -> None:
        for rows, line in ((b"0,10,extra\n1,20\n", 2), (b"0,10\n1,20,\n", 3)):
            with self.subTest(rows=rows), self.assertRaisesRegex(
                pd.errors.ParserError, rf"line {line}, saw 3"
            ):
                read_activities_csv(b"Activity,Distance\n" + rows)

    def test_accepts_quoted_multiline_fields_and_missing_trailing_values(self) -> None:
        frame = read_activities_csv(b'Activity,Distance,Notes\r\n"Ride,\r\n morning",10\r\n')

        self.assertEqual(frame.loc[0, "Activity"], "Ride,\r\n morning")
        self.assertTrue(pd.isna(frame.loc[0, "Notes"]))

    def test_accepts_long_quoted_fields(self) -> None:
        notes = b"Ride notes, continued\n" * 7000
        frame = read_activities_csv(b'Activity,Notes\nRide,"' + notes + b'"\n')

        self.assertEqual(frame.loc[0, "Notes"], notes.decode())

    def test_selects_valid_duplicate_measurements(self) -> None:
        frame = read_activities_csv(
            b"Distance,Distance,Average Speed,Average Speed\n"
            b"-1,10,inf,20\n40,,30,\n50,,35,\n"
        )

        self.assertEqual(frame["Distance"].tolist(), [10, 40, 50])
        self.assertEqual(frame["Average Speed"].tolist(), [20, 30, 35])

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
