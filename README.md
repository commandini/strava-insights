# Strava Insights

Strava Insights is a single-page Streamlit application that turns an exported sports-activity CSV into a focused,
filterable report. It is designed for cycling, running, and walking data and can export the displayed report as a
color-preserving PDF.

## Features

- Date, name, series, activity type, distance, gear, and average-speed filters
- Summary metrics with activity-specific pace and cycling metrics
- Average-speed distribution with activity counts and distance totals
- Calendar-day and start-hour heatmaps
- Gear usage, highlights, and monthly and yearly performance
- Ride-only Eddington number and consistency metrics
- Configurable report background with matching PDF output
- Row-by-row recovery of useful values from duplicate CSV columns

## Quick start

Python 3.9 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
streamlit run app.py
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

Upload an activities CSV, choose an activity type and any optional filters, and select **Get Insights**. The included
`data.csv` contains fully synthetic activities that can be used to explore the report.

## CSV compatibility

The loader recognizes common detailed and summary export names, including:

| Purpose             | Recognized columns                                                                     |
|---------------------|----------------------------------------------------------------------------------------|
| Date and start time | `Activity Date`, `Start Time`, `Date`                                                  |
| Activity type       | `Activity Type`, `Type`                                                                |
| Activity name       | `Activity Name`, `Name`                                                                |
| Gear                | `Activity Gear`, `Gear`                                                                |
| Distance            | `Distance`, `Grade Adjusted Distance`                                                  |
| Duration            | `Moving Time`, `Timer Time`, `Elapsed Time`                                            |
| Average speed       | `Average Speed`                                                                        |
| Additional metrics  | `Elevation Gain`, `Calories`, `Average Heart Rate`, `Average Watts`, `Relative Effort` |

Exact duplicate headers are coalesced independently for every row. Meaningful values take precedence over empty cells
and placeholders such as `.`, `--`, `N/A`, and `null`. Invalid negative or non-finite measurements are ignored rather
than included in report calculations.

When distance and speed units can be verified from distance, duration, and speed together, the app normalizes them
automatically. It also recognizes the conventions used by common detailed and summary exports. If a custom CSV does not
contain enough information to determine its units reliably, the page displays a warning instead of presenting the
inference as certain.

## Data privacy

Activity processing and PDF generation happen inside the running Streamlit process. The application contains no code
that uploads activity data to an external service, and Streamlit usage telemetry is disabled in
`.streamlit/config.toml`.

## Development

Install the development dependencies and run the same checks used by CI:

```bash
python -m pip install -e ".[dev]"
ruff check .
python -m unittest discover -s tests
```

GitHub Actions runs these checks on Python 3.9 and Python 3.12 for every push and pull request.

Remove generated reports, build artifacts, and tool caches while preserving `.venv`:

```bash
python scripts/clean.py
```

Preview the affected paths first with `python scripts/clean.py --dry-run`.

## Creating an encrypted archive

Create a minimal password-protected project archive with:

```bash
python scripts/package.py
```

The system ZIP utility prompts for the password twice, so the password is never passed as a command-line argument. Use
`--include-sample-data` to include `data.csv`, and `--force` to atomically replace an existing archive after the
replacement passes verification.

The built-in ZIP utility uses traditional ZIP encryption for compatibility. Use a dedicated AES-capable archiver when
stronger encryption is required.

## Project structure

```text
app.py                   Streamlit page and filter workflow
activity_processing.py   Activity normalization and filtering
data_loading.py          CSV ingestion and duplicate-column handling
reporting.py             Report model, web rendering, and PDF generation
theme.py                 Shared typography and color values
tests/                   Unit and Streamlit smoke tests
scripts/clean.py         Safe generated-artifact cleanup
scripts/package.py       Minimal encrypted project archive command
.streamlit/config.toml   Streamlit runtime settings
.github/workflows/ci.yml GitHub Actions checks
pyproject.toml           Project metadata, dependencies, and tooling
```

Generated PDFs and temporary rendering files belong under `output/` and `tmp/`; both directories are ignored by Git.

## License

This project is available under the [MIT License](LICENSE).
