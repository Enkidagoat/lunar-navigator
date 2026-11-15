"""Validate the precomputed CSV and its static Pages summary."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "drama_windows.csv"
SUMMARY_PATH = ROOT / "docs" / "drama_windows.json"
RANKING_PATH = ROOT / "data" / "comparison_rankings.json"
PRIMARY_WINDOW = "2028-01-01_14d"


def test_csv_digest_matches_ranking_metadata():
    ranking = json.loads(RANKING_PATH.read_text(encoding="utf-8"))
    csv_metadata = ranking["input_files"]["drama_windows.csv"]
    assert csv_metadata["rows"] == 3024
    assert csv_metadata["sha256"] == hashlib.sha256(CSV_PATH.read_bytes()).hexdigest()


def test_primary_window_locked_counts_in_csv():
    with CSV_PATH.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))

    assert len(rows) == 3024
    for site_id, expected in {
        "DM2-358": (326, 324, 324),
        "SITE07-1223": (237, 275, 237),
    }.items():
        samples = [
            row
            for row in rows
            if row["window_id"] == PRIMARY_WINDOW and row["site_id"] == site_id
        ]
        assert len(samples) == 336
        sun_above = sum(float(row["sun_elevation_deg"]) > 0 for row in samples)
        earth_above = sum(float(row["earth_elevation_deg"]) > 0 for row in samples)
        simultaneous = sum(
            float(row["sun_elevation_deg"]) > 0
            and float(row["earth_elevation_deg"]) > 0
            for row in samples
        )
        assert (sun_above, earth_above, simultaneous) == expected


def test_pages_summary_is_derived_from_primary_csv_counts():
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    assert summary["primary_window_id"] == PRIMARY_WINDOW
    sites = {site["site_id"]: site for site in summary["sites"]}
    expected = {"DM2-358": 324, "SITE07-1223": 237}
    for site_id, simultaneous_count in expected.items():
        window = next(
            item
            for item in sites[site_id]["windows"]
            if item["window_id"] == PRIMARY_WINDOW
        )
        assert window["sample_count"] == 336
        assert window["simultaneous_count"] == simultaneous_count
