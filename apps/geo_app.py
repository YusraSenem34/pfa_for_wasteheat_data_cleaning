"""Streamlit app: map of waste heat sources with radius search and hourly profiles.

    python -m pfa_wasteheat.pipeline
    python -m pfa_wasteheat.enrich.geocode --legacy data/data_with_coordinates_all_latest.xlsx
    streamlit run apps/geo_app.py
"""

from pathlib import Path

import folium
import numpy as np
import pandas as pd
import streamlit as st
from haversine import Unit, haversine
from streamlit_folium import st_folium

from pfa_wasteheat import columns as C
from pfa_wasteheat.config import load_config
from pfa_wasteheat.profiles.hourly import energy_profile

st.set_page_config(layout="wide")
cfg = load_config()
DEFAULT_FILE = Path(cfg.paths.output_dir) / "pfa_cleaned_geo.parquet"

REQUIRED_COLUMNS = ["lat", "long", C.COMPANY, C.CITY, C.SOURCE_NAME, C.ANNUAL_KWH_CLEAN,
                    C.DAILY_HOURS_CLEAN, "weekend_available", "quality_tier"] + C.ENERGY_COLS_CLEAN


@st.cache_data
def load_data(file_input) -> pd.DataFrame:
    name = getattr(file_input, "name", str(file_input))
    df = pd.read_parquet(file_input) if name.endswith(".parquet") else pd.read_excel(file_input)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        st.error("The file is missing required columns:\n\n`" + "`, `".join(missing) + "`\n\n"
                 "Use the output of the cleaning pipeline + geocoding step.")
        return pd.DataFrame()
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["long"] = pd.to_numeric(df["long"], errors="coerce")
    return df.dropna(subset=["lat", "long", C.ANNUAL_KWH_CLEAN])


# --- Data source ---
st.sidebar.header("Data source")
uploaded = st.sidebar.file_uploader("Cleaned + geocoded file", type=["parquet", "xlsx"])
if uploaded is not None:
    df = load_data(uploaded)
elif DEFAULT_FILE.exists():
    df = load_data(DEFAULT_FILE)
else:
    st.warning(f"`{DEFAULT_FILE}` not found. Run the pipeline and the geocoding step first.")
    st.stop()
if df.empty:
    st.stop()

# --- Filters ---
st.title("Waste heat potential map")
st.sidebar.header("Radius search")
lat_input = st.sidebar.number_input("Latitude", value=52.5200, format="%.4f")
lon_input = st.sidebar.number_input("Longitude", value=13.4050, format="%.4f")
radius_km = st.sidebar.slider("Radius (km)", 1, 100, 40)
tiers = st.sidebar.multiselect("Quality tier", ["A", "B", "C", "D"], default=["A", "B", "C"])

point = (lat_input, lon_input)
df = df[df["quality_tier"].isin(tiers)].copy()
df["distance_km"] = [haversine(point, (a, b), unit=Unit.KILOMETERS) for a, b in zip(df["lat"], df["long"])]
near = df[df["distance_km"] <= radius_km].sort_values("distance_km").reset_index(drop=True)
near.insert(0, "Map_ID", near.index + 1)

# --- Map ---
m = folium.Map(location=[51.1657, 10.4515], zoom_start=6)
folium.Marker(point, popup="You", icon=folium.Icon(color="blue", icon="user")).add_to(m)
folium.Circle(point, radius=radius_km * 1000, color="#1f78b4", fill=True, fill_opacity=0.2).add_to(m)
for _, row in near.iterrows():
    heat = f"{row[C.ANNUAL_KWH_CLEAN]:,.0f}".replace(",", ".")
    dist = f"{row['distance_km']:.1f}".replace(".", ",")
    folium.CircleMarker(
        [row["lat"], row["long"]], radius=float(np.log1p(row[C.ANNUAL_KWH_CLEAN]) / 2.5),
        color="red", fill=True, fill_color="red", fill_opacity=0.6,
        popup=folium.Popup(f"<b>ID: {row['Map_ID']}</b><br><b>{row[C.COMPANY]}</b><br>"
                           f"Waste heat: {heat} kWh/a<br>Distance: {dist} km<br>"
                           f"Quality tier: {row['quality_tier']}", max_width=300),
    ).add_to(m)
st_folium(m, width="100%", height=500)

# --- Table and profile ---
st.subheader(f"Found {len(near)} sources within {radius_km} km")
if near.empty:
    st.stop()

st.info("Select rows to download them. Select exactly one row to see its hourly profile.")
event = st.dataframe(near, width="stretch", hide_index=True, on_select="rerun", selection_mode="multi-row")
selected = event.selection.rows

if selected:
    st.download_button(f"Download {len(selected)} selected rows (CSV)",
                       near.iloc[selected].to_csv(index=False).encode("utf-8"),
                       "selected_sources.csv", "text/csv")
if len(selected) == 1:
    row = near.iloc[selected[0]]
    st.divider()
    st.subheader(f"{row[C.COMPANY]} - {row[C.SOURCE_NAME]}")
    try:
        prof = energy_profile(row, cfg.calendar_year)
        ts = prof.waste_heat.profile_data
        c1, c2 = st.columns([3, 1])
        c1.line_chart(ts, color="#ff4b4b", y_label="kW")
        c2.metric("Annual energy", f"{prof.waste_heat.aggregated_demands:,.0f} kWh")
        c2.metric("Temperature", f"{row.get(C.TEMP_C)} °C")
        c2.metric("Availability", f"{row[C.DAILY_HOURS_CLEAN]:.1f} h/day")
        c2.metric("Quality tier", row["quality_tier"])
        st.caption(f"Monthly values: {row['monthly_source']}")
        st.download_button("Download hourly profile (CSV)", ts.to_csv().encode("utf-8"),
                           f"profile_row{int(row[C.ROW_ID])}.csv", "text/csv")
    except Exception as exc:
        st.error(f"Could not build the profile: {exc}")
elif len(selected) > 1:
    st.caption("Select a single row to see its profile.")
