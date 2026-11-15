#!/usr/bin/env python3
"""Generate the precomputed drama-window CSV and its Pages summary."""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ephemeris import LunarGeometry, build_hourly_utc_grid, verify_kernel_files
from sites import get_site_list

DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_CSV = DATA_DIR / "drama_windows.csv"
OUTPUT_JSON = PROJECT_ROOT / "docs" / "drama_windows.json"
WINDOW_STARTS = (date(2026, 12, 1), date(2027, 6, 1), date(2028, 1, 1))
WINDOW_DAYS = 14
KERNEL_SHA256 = {
    "de421.bsp": "08b20db2ae22488650641c5a9033e5bfda4b1c4b440cfeaf20f621cfa18ecdb3",
    "moon_080317.tf": "78732477b96f9863e7b0d65bcee3c22b8707ca5ed0db56d1173319cb2e8c7993",
    "moon_pa_de421_1900-2050.bpc": "656f90616403d75a75f0cd6c8830fc5b44f8cb4facb5ccb8915e752b397520cf",
    "pck00011.tpc": "3dff7b1dbeceaa01f25467767d3fa25816051c85d162d1edf04acb310ee28bb1",
}
GEOMETRY_MODEL = "deterministic hourly geometric lunar Sun/Earth center elevations and azimuths"
ENVIRONMENTAL_DATA_STATUS = "unavailable_not_computed"
ENVIRONMENTAL_FIELDS = (
    "uv_flux_w_m2",
    "solar_wind_proton_density_cm3",
    "solar_wind_speed_km_s",
    "plasma_electron_temperature_ev",
    "surface_potential_v",
    "surface_electric_field_v_m",
    "dust_density_cm3",
    "dust_charge_e",
    "charging_regime",
)
CSV_FIELDS = (
    "window_id",
    "window_start_utc",
    "window_end_utc_inclusive",
    "window_days",
    "sample_interval_hours",
    "timestamp_utc",
    "site_id",
    "site_name",
    "latitude_planetocentric_deg",
    "longitude_east_signed_deg",
    "reference_frame",
    "reference_surface_elevation_assumption_m",
    "sun_elevation_deg",
    "sun_azimuth_deg",
    "earth_elevation_deg",
    "earth_azimuth_deg",
    "geometry_model",
    "environmental_data_status",
    *ENVIRONMENTAL_FIELDS,
)


def utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect_rows(geometry: LunarGeometry) -> list[dict[str, Any]]:
    rows = []
    for window_start in WINDOW_STARTS:
        window_end = window_start + timedelta(days=WINDOW_DAYS - 1)
        timestamps = build_hourly_utc_grid(window_start, window_end)
        window_id = f"{window_start.isoformat()}_{WINDOW_DAYS}d"
        start_utc = datetime.combine(window_start, datetime.min.time(), timezone.utc)
        end_utc = datetime.combine(window_end, datetime.max.time(), timezone.utc).replace(
            minute=0, second=0, microsecond=0
        )

        for site in get_site_list():
            result = geometry.calculate_site(site, timestamps)
            for timestamp, sun_elevation, sun_azimuth, earth_elevation, earth_azimuth in zip(
                result.timestamps_utc,
                result.sun_elevation_deg,
                result.sun_azimuth_deg,
                result.earth_elevation_deg,
                result.earth_azimuth_deg,
                strict=True,
            ):
                row = {
                    "window_id": window_id,
                    "window_start_utc": utc_text(start_utc),
                    "window_end_utc_inclusive": utc_text(end_utc),
                    "window_days": WINDOW_DAYS,
                    "sample_interval_hours": 1,
                    "timestamp_utc": utc_text(timestamp),
                    "site_id": site.site_id,
                    "site_name": site.name,
                    "latitude_planetocentric_deg": site.latitude_deg,
                    "longitude_east_signed_deg": site.longitude_deg,
                    "reference_frame": site.reference_frame,
                    "reference_surface_elevation_assumption_m": site.elevation_m,
                    "sun_elevation_deg": sun_elevation,
                    "sun_azimuth_deg": sun_azimuth,
                    "earth_elevation_deg": earth_elevation,
                    "earth_azimuth_deg": earth_azimuth,
                    "geometry_model": GEOMETRY_MODEL,
                    "environmental_data_status": ENVIRONMENTAL_DATA_STATUS,
                }
                row.update({field: None for field in ENVIRONMENTAL_FIELDS})
                rows.append(row)
    return rows


def build_pages_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    sites: dict[str, dict[str, Any]] = {}
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        site = sites.setdefault(
            row["site_id"],
            {
                "site_id": row["site_id"],
                "site_name": row["site_name"],
                "latitude_planetocentric_deg": float(row["latitude_planetocentric_deg"]),
                "longitude_east_signed_deg": float(row["longitude_east_signed_deg"]),
                "windows": [],
            },
        )
        grouped.setdefault((row["site_id"], row["window_id"]), []).append(row)

    for (site_id, window_id), samples in grouped.items():
        sun_above = sum(float(sample["sun_elevation_deg"]) > 0 for sample in samples)
        earth_above = sum(float(sample["earth_elevation_deg"]) > 0 for sample in samples)
        simultaneous = sum(
            float(sample["sun_elevation_deg"]) > 0
            and float(sample["earth_elevation_deg"]) > 0
            for sample in samples
        )
        first = samples[0]
        sites[site_id]["windows"].append(
            {
                "window_id": window_id,
                "sample_count": len(samples),
                "sun_above_count": sun_above,
                "earth_above_count": earth_above,
                "simultaneous_count": simultaneous,
                "sun_elevation_deg": float(first["sun_elevation_deg"]),
                "sun_azimuth_deg": float(first["sun_azimuth_deg"]),
                "earth_elevation_deg": float(first["earth_elevation_deg"]),
                "earth_azimuth_deg": float(first["earth_azimuth_deg"]),
            }
        )

    return {
        "schema_version": "1.0",
        "source_csv": "../data/drama_windows.csv",
        "primary_window_id": "2028-01-01_14d",
        "sites": list(sites.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--kernel-dir",
        type=Path,
        default=DATA_DIR / "kernels",
        help="directory containing the verified kernels and manifest.json",
    )
    args = parser.parse_args()

    kernel_files = verify_kernel_files(args.kernel_dir)
    for filename, expected_hash in KERNEL_SHA256.items():
        actual_hash = hashlib.sha256(kernel_files[filename].read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"Unexpected SHA-256 for {filename}: expected {expected_hash}, got {actual_hash}"
            )

    geometry = LunarGeometry(args.kernel_dir)
    try:
        generated_rows = collect_rows(geometry)
    finally:
        geometry.close()

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(generated_rows)

    with OUTPUT_CSV.open(newline="", encoding="utf-8") as source:
        source_rows = list(csv.DictReader(source))
    summary = build_pages_summary(source_rows)
    OUTPUT_JSON.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(source_rows)} samples to {OUTPUT_CSV}")
    print(f"Wrote CSV-derived summary to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
