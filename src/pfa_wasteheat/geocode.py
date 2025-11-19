#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File              : geocode.py
# License           : License: MIT
# Author            : Yusra Senem yuesra.senem@dlr.de
# Date              : 19.11.2025

from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
import time

#that function "geocode_dataframe" is a function need to be used only once to geocode the dataset and save it to a file.

def geocode_dataframe(df, file_to_save):
    """
    Takes a DataFrame, adds lat/long columns, and saves it to a file.
    """
    # Initialize the geocoder
    geolocator = Nominatim(user_agent="pfa_wasteheat_app_ys", timeout=5)
    
    # Use RateLimiter to respect the API's 1-request-per-second limit
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1, error_wait_seconds=10)

    print(f"\n--- Starting Geocoding for {len(df)} rows ---")
    start_time = time.time()
    
    # Create the 'full_address' string for the geocoder
    df['full_address'] = df['Street_and_House_Number'].fillna('') + ', ' + \
                         df['Postal_Code'].astype(str) + ' ' + \
                         df['City'].fillna('') + ', Germany'

    # --- Apply the geocode function to each row ---
    # We use a loop with print statements to show progress
    locations = []
    for i, row in df.iterrows():
        # Print progress every 10 rows
        if (i + 1) % 10 == 0:
            print(f"Processing row {i+1}/{len(df)}...")
            
        # Handle blank addresses
        if row['full_address'].strip() == ',':
            locations.append(None)
            continue
            
        try:
            locations.append(geocode(row['full_address']))
        except Exception as e:
            print(f"Error on row {i}: {e}. Appending None.")
            locations.append(None)

    # --- Process the results ---
    df['location'] = locations
    df['lat'] = df['location'].apply(lambda loc: loc.latitude if loc else None)
    df['long'] = df['location'].apply(lambda loc: loc.longitude if loc else None)

# --- Save the new DataFrame ---
    if file_to_save.endswith('.xlsx'):
        print(f"Saving to Excel file: {file_to_save}")
        df.to_excel(file_to_save, index=False, engine='openpyxl')
    else:
        print(f"Saving to CSV file: {file_to_save}")
        df.to_csv(file_to_save, index=False)
    
    end_time = time.time()
    duration = (end_time - start_time) / 60 # in minutes
    found_count = df['lat'].notna().sum()
    
    print(f"\n✅ Geocoding complete in {duration:.1f} minutes.")
    print(f"Found {found_count} of {len(df)} addresses.")
    print(f"Geocoded sample data saved to {file_to_save}")
    
    return df
