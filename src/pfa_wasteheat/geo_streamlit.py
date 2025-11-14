import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from haversine import haversine, Unit
import numpy as np

# Set page to wide mode for a better map layout
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
        # Drop rows where geocoding failed
        df.dropna(subset=['lat', 'long'], inplace=True)
        return df
    except FileNotFoundError:
        st.error(f"Error: Data file '{filepath}' not found. Did you run the geocoding script first?")
        return pd.DataFrame()

# Load your geocoded sample file
DATA_FILE = "dataset_with_coordinates_.xlsx"
df = load_data(DATA_FILE)

# --- Streamlit UI ---
st.title("Waste Heat Potential Map & Radius Search")

st.sidebar.header("Radius Search")
st.sidebar.write("Enter a coordinate to find waste heat sources within a radius.")

# User inputs in the sidebar
# Default coordinates are for Berlin
lat_input = st.sidebar.number_input("Enter Latitude", value=52.5200) 
lon_input = st.sidebar.number_input("Enter Longitude", value=13.4050)
radius_km = st.sidebar.slider("Radius (km)", min_value=1, max_value=100, value=40)

# --- Core Logic ---
if not df.empty:
    input_point = (lat_input, lon_input)

    # Calculate distance for every site from the input point
    df['distance_km'] = df.apply(
        lambda row: calculate_distance(input_point, (row['lat'], row['long'])), 
        axis=1
    )
    
    # Filter the DataFrame to get sites within the radius
    df_filtered = df[df['distance_km'] <= radius_km].copy()
    
    # --- Map Creation ---
    
    # Create a base map centered on Germany
    map_center = [51.1657, 10.4515] # Center of Germany
    m = folium.Map(location=map_center, zoom_start=6)

    # 1. Add the user's input location as a blue marker
    folium.Marker(
        location=input_point,
        popup="Your Location",
        icon=folium.Icon(color="blue", icon="user"),
    ).add_to(m)

    # 2. Add a circle representing the search radius
    folium.Circle(
        location=input_point,
        radius=radius_km * 1000, # Radius in meters
        color="#1f78b4",
        fill=True,
        fill_color="#a6cee3",
        fill_opacity=0.2,
        popup=f"{radius_km} km Radius",
    ).add_to(m)

    # 3. Add all the filtered waste heat points to the map
    # We use log-scale for radius to make visualization clearer
    if not df_filtered.empty:
        # Scale radius by log of heat amount so big sites don't hide small ones
        df_filtered['radius_viz'] = np.log1p(df_filtered['Annual_Heat_Amount_kWh_per_Year']) / 2.5
        
        for _, row in df_filtered.iterrows():
            folium.CircleMarker(
                location=[row['lat'], row['long']],
                radius=row['radius_viz'],
                color="red",
                fill=True,
                fill_color="red",
                fill_opacity=0.6,
                popup=folium.Popup(
                    f"<b>{row['Company_Name']}</b><br>"
                    f"Waste Heat: {row['Annual_Heat_Amount_kWh_per_Year']:,.0f} kWh/a<br>"
                    f"Distance: {row['distance_km']:.1f} km",
                    max_width=300
                )
            ).add_to(m)
    
    # Display the map in Streamlit
    st_folium(m, width="100%", height=500)
    
    # --- Summary Table ---
    st.subheader(f"Found {len(df_filtered)} sites within {radius_km} km")
    
    if not df_filtered.empty:
        st.dataframe(
            df_filtered[['Company_Name', 'City', 'Annual_Heat_Amount_kWh_per_Year', 'distance_km']]
            .sort_values('distance_km')
            .reset_index(drop=True)
        )
else:
    st.warning("Could not load data.")