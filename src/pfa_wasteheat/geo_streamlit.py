import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from haversine import haversine, Unit
import numpy as np

# Set page to wide layout
st.set_page_config(layout="wide")

# --- Function to Calculate Distance ---
def calculate_distance(point1, point2):
    """Calculates the distance between two lat/long points in km."""
    return haversine(point1, point2, unit=Unit.KILOMETERS)

# --- Load Data ---
@st.cache_data
def load_data(filepath):
    """Loads the pre-geocoded data from the Excel file."""
    try:
        df = pd.read_excel(filepath)
        # Ensure lat/long are numeric
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
        df['long'] = pd.to_numeric(df['long'], errors='coerce')
        df.dropna(subset=['lat', 'long'], inplace=True)
        return df
    except FileNotFoundError:
        st.error(f"Error: Data file '{filepath}' not found.")
        return pd.DataFrame()

# Load data
DATA_FILE = "data/data_with_coordinates_all_latest.xlsx"
df = load_data(DATA_FILE)

# --- Streamlit UI ---
st.title("Waste Heat Potential Map & Radius Search")

st.sidebar.header("Radius Search")
st.sidebar.write("Enter a coordinate to find waste heat sources within a radius.")

# Default location (Berlin)
lat_input = st.sidebar.number_input("Enter Latitude", value=52.5200) 
lon_input = st.sidebar.number_input("Enter Longitude", value=13.4050)
radius_km = st.sidebar.slider("Radius (km)", min_value=1, max_value=100, value=40)

# --- Core Logic ---
if not df.empty:
    input_point = (lat_input, lon_input)

    # Calculate distance for each point
    df['distance_km'] = df.apply(
        lambda row: calculate_distance(input_point, (row['lat'], row['long'])), 
        axis=1
    )
    
    # 1. Filter inside radius
    df_filtered = df[df['distance_km'] <= radius_km].copy()

    # 2. Sort and Add IDs IMMEDIATELY (So Map and Table match)
    if not df_filtered.empty:
        # Sort by distance
        df_filtered = df_filtered.sort_values('distance_km').reset_index(drop=True)
        # Add a sequential ID (1, 2, 3...) column at the start
        df_filtered.insert(0, 'Map_ID', df_filtered.index + 1)

    # --- Map Creation ---
    map_center = [51.1657, 10.4515]  # Germany center
    m = folium.Map(location=map_center, zoom_start=6)

    # Add user's location marker
    folium.Marker(
        location=input_point,
        popup="Your Location",
        icon=folium.Icon(color="blue", icon="user"),
    ).add_to(m)

    # Add radius circle
    folium.Circle(
        location=input_point,
        radius=radius_km * 1000,
        color="#1f78b4",
        fill=True,
        fill_color="#a6cee3",
        fill_opacity=0.2,
        popup=f"{radius_km} km Radius",
    ).add_to(m)

    # Add filtered waste heat points
    if not df_filtered.empty:
        df_filtered['radius_viz'] = np.log1p(df_filtered['Annual_Heat_Amount_kWh_per_Year']) / 2.5
    
        for _, row in df_filtered.iterrows():
            # Heat: "1,000" -> "1.000"
            heat_german = f"{row['Annual_Heat_Amount_kWh_per_Year']:,.0f}".replace(",", ".")
            
            # Distance: "26.8" -> "26,8"
            dist_german = f"{row['distance_km']:.1f}".replace(".", ",")

            folium.CircleMarker(
                location=[row['lat'], row['long']],
                radius=row['radius_viz'],
                color="red",
                fill=True,
                fill_color="red",
                fill_opacity=0.6,
                popup=folium.Popup(
                    f"<b>ID: {row['Map_ID']}</b><br>"  # ID Added Here
                    f"<b>{row['Company_Name']}</b><br>"
                    f"Waste Heat: {heat_german} kWh/a<br>"
                    f"Distance: {dist_german} km",
                    max_width=300
                )
            ).add_to(m)

    # Display map
    st_folium(m, width="100%", height=500)

    # --- Summary & Selectable Table ---
    st.subheader(f"Found {len(df_filtered)} sites within {radius_km} km")

    if not df_filtered.empty:

        # Select columns to display, making sure Map_ID is first
        #cols_to_show = ['Map_ID', 'Company_Name', 'City', 'Annual_Heat_Amount_kWh_per_Year', 'distance_km']
        
        # Filter mostly for clean display, but keep the ID
        table_data = df_filtered

        st.subheader("Select rows to download")

        # Selectable table
        event = st.dataframe(
            table_data,
            width="stretch",
            hide_index=True,
            on_select="rerun",             # Enable selection events
            selection_mode="multi-row"     # Enable multi-row selection
        )

        # Handle selected rows
        selected_indices = event.selection.rows

        # 3. Check if anything is selected
        if selected_indices:
            st.write(f"You have selected {len(selected_indices)} rows.")
            
            # Filter the dataframe using the selected indices
            selected_df = table_data.iloc[selected_indices]

            csv_data = selected_df.to_csv(index=False).encode("utf-8")

            st.download_button(
                label="📥 Download Selected Rows (CSV)",
                data=csv_data,
                file_name="selected_waste_heat_sites.csv",
                mime="text/csv",
            )
        else:
            st.info("Select rows in the table above to enable download.")

else:
    st.warning("Could not load data.")