import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from haversine import haversine, Unit
import numpy as np
import sys
import os

# --- 1. SETUP PATHS & IMPORTS ---

from waste_heat_generator import generate_waste_heat_profile, WasteHeatRecord

# Set page to wide layout
st.set_page_config(layout="wide")

# --- 2. HELPER FUNCTIONS ---
def calculate_distance(point1, point2):
    return haversine(point1, point2, unit=Unit.KILOMETERS)

# --- Configuration ---
# List of columns strictly required for the Map and Profile Generator to work
REQUIRED_COLUMNS = [
    "lat", "long", 
    "Company_Name", 
    "City", 
    "Annual_Heat_Amount_kWh_per_Year",
    "Waste_Heat_Potential_Name",
    "Temperature_Range",
    "Avg_Daily_Availability_h",
    "Weekend_Availability",
    # We check just one month as a proxy for the rest to keep the list short, 
    # but you can add all 12 if you want strictly rigid validation.
    "Power_Profile_January_kW" 
]

# --- Load Data Function ---
@st.cache_data
def load_data(file_input):
    """Loads and validates data from an Excel file (path or uploaded object)."""
    try:
        df = pd.read_excel(file_input)
        
        # 1. VALIDATION: Check for missing columns
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        
        if missing_cols:
            # Stop execution and show error if columns are missing
            st.error(f"❌ **File Error:** The uploaded file is missing the following required columns:\n\n" 
                     f"`{', '.join(missing_cols)}`\n\n"
                     f"Please ensure the file matches the standard template.")
            return pd.DataFrame() # Return empty to signal failure

        # 2. PROCESSING: Ensure numeric coordinates
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
        df['long'] = pd.to_numeric(df['long'], errors='coerce')
        
        # Remove rows without valid coordinates
        df.dropna(subset=['lat', 'long'], inplace=True)
        
        return df

    except Exception as e:
        st.error(f"Error loading file: {e}")
        return pd.DataFrame()

# --- 3. LOAD DATA UI ---
st.sidebar.divider()
st.sidebar.header("Data Source")

uploaded_file = st.sidebar.file_uploader("Upload your own Excel file", type=["xlsx"])
DEFAULT_FILE = "data/data_with_coordinates_all_latest.xlsx"

# Logic: Use uploaded file if exists, otherwise default
if uploaded_file is not None:
    df = load_data(uploaded_file)
    if not df.empty:
        st.sidebar.success("✅ Custom file loaded successfully!")
else:
    df = load_data(DEFAULT_FILE)

# Final Safety Check
if df.empty:
    st.warning("⚠️ Application stopped because valid data could not be loaded.")
    st.stop()

# --- 4. SIDEBAR ---
st.title("Waste Heat Potential Map")
st.sidebar.header("Radius Search")

lat_input = st.sidebar.number_input("Latitude", value=52.5200, format="%.4f") 
lon_input = st.sidebar.number_input("Longitude", value=13.4050, format="%.4f")
radius_km = st.sidebar.slider("Radius (km)", 1, 100, 40)

# --- 5. MAIN LOGIC ---
if not df.empty:
    input_point = (lat_input, lon_input)

    # Filter & Sort
    df['distance_km'] = df.apply(lambda row: calculate_distance(input_point, (row['lat'], row['long'])), axis=1)
    df_filtered = df[df['distance_km'] <= radius_km].copy()

    if not df_filtered.empty:
        df_filtered = df_filtered.sort_values('distance_km').reset_index(drop=True)
        df_filtered.insert(0, 'Map_ID', df_filtered.index + 1)

    # Map Generation
    map_center = [51.1657, 10.4515]
    m = folium.Map(location=map_center, zoom_start=6)
    
    folium.Marker(location=input_point, popup="You", icon=folium.Icon(color="blue", icon="user")).add_to(m)
    folium.Circle(location=input_point, radius=radius_km * 1000, color="#1f78b4", fill=True, fill_opacity=0.2).add_to(m)

    if not df_filtered.empty:
        df_filtered['radius_viz'] = np.log1p(df_filtered['Annual_Heat_Amount_kWh_per_Year']) / 2.5
        
        for _, row in df_filtered.iterrows():
            # 1. Format Waste Heat: "1,000" -> "1.000"
            heat_german = f"{row['Annual_Heat_Amount_kWh_per_Year']:,.0f}".replace(",", ".")
            
            # 2. Format Distance: "26.8" -> "26,8"
            dist_german = f"{row['distance_km']:.1f}".replace(".", ",")

            # 3. Create Marker with Detailed Popup
            folium.CircleMarker(
                location=[row['lat'], row['long']],
                radius=row['radius_viz'],
                color="red", 
                fill=True, 
                fill_color="red", 
                fill_opacity=0.6,
                popup=folium.Popup(
                    f"<b>ID: {row['Map_ID']}</b><br>"
                    f"<b>{row['Company_Name']}</b><br>"
                    f"Waste Heat: {heat_german} kWh/a<br>"
                    f"Distance: {dist_german} km",
                    max_width=300
                )
            ).add_to(m)
    st_folium(m, width="100%", height=500)

    # --- 6. TABLE & INTERACTION ---
    st.subheader(f"Found {len(df_filtered)} sites within {radius_km} km")

    if not df_filtered.empty:
        # Define columns to show
        #cols_to_show = ['Map_ID', 'Company_Name', 'City', 'Annual_Heat_Amount_kWh_per_Year', 'distance_km']
        table_view = df_filtered

        st.info("💡 **Tip:** Select multiple rows to download CSV. Select **only one** row to see the Waste Heat Profile.")

        # THE TABLE
        event = st.dataframe(
            table_view,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode="multi-row"  
        )

        selected_indices = event.selection.rows

        # --- LOGIC BRANCHING ---
        if selected_indices:
            
            # A. DOWNLOAD LOGIC (Always available if rows are selected)
            selected_df_download = table_view.iloc[selected_indices]
            csv_data = selected_df_download.to_csv(index=False).encode("utf-8")
            
            st.download_button(
                label=f"📥 Download {len(selected_indices)} Selected Rows (CSV)",
                data=csv_data,
                file_name="selected_sites.csv",
                mime="text/csv",
            )

            # B. PROFILE LOGIC (Only if EXACTLY ONE is selected)
            if len(selected_indices) == 1:
                idx = selected_indices[0]
                full_row_data = df_filtered.iloc[idx] # Get full data (hidden cols included)

                st.divider()
                st.subheader(f"🏭 Analysis: {full_row_data['Company_Name']}")

                try:
                    # Generate Profile
                    record = WasteHeatRecord(**full_row_data.to_dict())
                    profile = generate_waste_heat_profile(record, year=2025)

                    if profile.waste_heat and profile.waste_heat.profile_data is not None:
                        ts_data = profile.waste_heat.profile_data
                        
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.markdown("### 📈 Hourly Load Profile")
                            st.line_chart(ts_data, color="#ff4b4b", y_label="kW")
                        with col2:
                            st.markdown("### ℹ️ Details")
                            st.metric("Total Energy", f"{profile.waste_heat.aggregated_demands:,.0f} kWh")
                            st.metric("Temp", f"{profile.waste_heat.temperature_c} °C")
                            st.metric("Availability", f"{profile.waste_heat.avg_daily_availability_h} h/day")

                        # Single Profile Download
                        # st.download_button(
                        #     label="📥 Download This Profile Data",
                        #     data=ts_data.to_csv().encode('utf-8'),
                        #     file_name=f"profile_{full_row_data['Map_ID']}_{record.company_name}.csv",
                        #     mime="text/csv"
                        # )
                except Exception as e:
                    st.error(f"Error generating profile: {e}")

            elif len(selected_indices) > 1:
                st.caption("ℹ️ *Select a single row to view the visual chart/profile.*")

else:
    st.warning("Could not load data.")