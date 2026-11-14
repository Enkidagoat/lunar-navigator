"""Lunar Navigator — Streamlit comparison of geometric Sun/Earth elevations."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ephemeris import (
    MAX_SUPPORTED_DATE,
    MIN_SUPPORTED_DATE,
    EphemerisDataError,
    GeometryInputError,
    LunarGeometry,
    build_hourly_utc_grid,
)
from sites import FRAME_INTERPRETATION, get_site_list

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
KERNEL_DIR = Path(os.environ.get("LUNAR_NAVIGATOR_KERNEL_DIR", PROJECT_ROOT / "data" / "kernels"))
DRAMA_CSV = DATA_DIR / "drama_windows.csv"

st.set_page_config(page_title="Lunar Navigator", layout="wide")
st.title("Lunar Navigator")
st.caption("Geometric Sun-center and Earth-center elevation comparison")

LIMITATIONS = (
    "Geometric center of the Sun and Earth above a smooth spherical tangent plane. "
    "Not terrain-aware, not apparent-disk visibility, not power, thermal, or communications assessment. "
    "Hourly samples; no interpolation. Coordinates provisionally interpreted as planetocentric in MOON_ME_DE421."
)

st.info(LIMITATIONS)
st.warning(FRAME_INTERPRETATION)

# --- Data load ---
@st.cache_data
def load_drama() -> pd.DataFrame:
    if not DRAMA_CSV.exists():
        return pd.DataFrame()
    df = pd.read_csv(DRAMA_CSV)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"])
    return df

drama = load_drama()
sites = get_site_list()
site_by_id = {s.site_id: s for s in sites}

# --- Sidebar ---
with st.sidebar:
    st.header("Mode")
    mode = st.radio("Data source", ["Drama windows (precomputed)", "Live calculation"], index=0)

    if mode == "Drama windows (precomputed)" and not drama.empty:
        windows = sorted(drama["window_id"].unique())
        default_window = "2028-01-01_14d" if "2028-01-01_14d" in windows else windows[0]
        window = st.selectbox("Window", windows, index=windows.index(default_window))
        available_sites = sorted(drama[drama["window_id"] == window]["site_id"].unique())
        site_a = st.selectbox("Site A", available_sites, index=available_sites.index("DM2-358") if "DM2-358" in available_sites else 0)
        site_b = st.selectbox("Site B", available_sites, index=available_sites.index("SITE07-1223") if "SITE07-1223" in available_sites else 0)
    else:
        st.subheader("Live calculation")
        selected = st.multiselect(
            "Sites",
            options=[s.name for s in sites],
            default=[sites[0].name, sites[2].name],
        )
        start = st.date_input("Start (UTC)", value=date(2028, 1, 1), min_value=MIN_SUPPORTED_DATE, max_value=MAX_SUPPORTED_DATE)
        end = st.date_input("End (UTC, inclusive)", value=date(2028, 1, 14), min_value=MIN_SUPPORTED_DATE, max_value=MAX_SUPPORTED_DATE)
        run_live = st.button("Calculate", type="primary")

# --- Drama path ---
if mode == "Drama windows (precomputed)" and not drama.empty:
    subset = drama[drama["window_id"] == window]
    col1, col2 = st.columns(2)

    def kpi_and_timeline(df: pd.DataFrame, site_id: str, container) -> None:
        s = df[df["site_id"] == site_id].sort_values("timestamp_utc")
        if s.empty:
            return
        sun_above = int((s["sun_elevation_deg"] > 0).sum())
        earth_above = int((s["earth_elevation_deg"] > 0).sum())
        both = int(((s["sun_elevation_deg"] > 0) & (s["earth_elevation_deg"] > 0)).sum())
        n = len(s)
        with container:
            st.subheader(site_by_id[site_id].name)
            st.metric("Sun above", f"{sun_above} / {n}", f"{sun_above/n:.1%}")
            st.metric("Earth above", f"{earth_above} / {n}", f"{earth_above/n:.1%}")
            st.metric("Simultaneous", f"{both} / {n}", f"{both/n:.1%}")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=s["timestamp_utc"], y=s["sun_elevation_deg"], name="Sun", mode="lines"))
            fig.add_trace(go.Scatter(x=s["timestamp_utc"], y=s["earth_elevation_deg"], name="Earth", mode="lines"))
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            fig.update_layout(height=360, hovermode="x unified", yaxis_title="Elevation (deg)")
            st.plotly_chart(fig, use_container_width=True)

    kpi_and_timeline(subset, site_a, col1)
    kpi_and_timeline(subset, site_b, col2)

    st.caption(f"Window {window} · {len(subset)} total samples · source: drama_windows.csv")

# --- Live path ---
elif mode == "Live calculation" and run_live:
    if len(selected) < 1:
        st.error("Select at least one site.")
    else:
        geometry = None
        try:
            timestamps = build_hourly_utc_grid(start, end)
            geometry = LunarGeometry(KERNEL_DIR)
            results = [geometry.calculate_site(next(s for s in sites if s.name == name), timestamps) for name in selected]
        except (GeometryInputError, EphemerisDataError, KeyError, OSError) as exc:
            st.error(str(exc))
        else:
            for result in results:
                sun_above = sum(e > 0 for e in result.sun_elevation_deg)
                earth_above = sum(e > 0 for e in result.earth_elevation_deg)
                both = sum(s > 0 and e > 0 for s, e in zip(result.sun_elevation_deg, result.earth_elevation_deg))
                n = len(result.timestamps_utc)
                st.subheader(result.site.name)
                c1, c2, c3 = st.columns(3)
                c1.metric("Sun above", f"{sun_above} / {n}")
                c2.metric("Earth above", f"{earth_above} / {n}")
                c3.metric("Simultaneous", f"{both} / {n}")
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=result.timestamps_utc, y=result.sun_elevation_deg, name="Sun", mode="lines"))
                fig.add_trace(go.Scatter(x=result.timestamps_utc, y=result.earth_elevation_deg, name="Earth", mode="lines"))
                fig.add_hline(y=0, line_dash="dash", line_color="gray")
                fig.update_layout(height=360, hovermode="x unified", yaxis_title="Elevation (deg)")
                st.plotly_chart(fig, use_container_width=True)
            st.caption(f"{len(timestamps)} hourly UTC samples · live geometry")
        finally:
            if geometry is not None:
                geometry.close()

st.divider()
st.caption(LIMITATIONS)
