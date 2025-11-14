#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File              : main.py
# License           : License: MIT
# Author            : Yusra Senem yuesra.senem@dlr.de
# Date              : 02.08.2025

from data_cleaning import DataCleaner
from energy_calculations import EnergyCalculator
from wasteheat_analyzer import WasteHeatAnalyzer
import pandas as pd
from utils import sanity_check
from categorization_of_wasteheat import categorize_waste_heat_sample
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from geopy.exc import GeocoderServiceError, GeocoderTimedOut
import time

# In main.py (the function "geocode_dataframe" should be placed somewhere else) !! that function "geocode_dataframe" is a function need to be used only once to geocode the dataset and save it to a file.

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

class WasteHeatAnalysisPipeline:
    def __init__(self, file_path):
        self.df = self.load_data(file_path)
        self.df['Original_Excel_Row'] = self.df.index + 3
        self.calculator = EnergyCalculator()
        self.cleaner = DataCleaner()
        self.analyzer = WasteHeatAnalyzer(self.df)
        

    def run(self):
        # Perform your analysis using self.df
        print("Running analysis...")

        # Declaring the dataset
        df = self.df
        raw_df = df.copy()
        
        
        # Clean string(object) data in the dataset for titles(column names) and text entities
        df = self.cleaner.clean_column_names(df)
        df = self.cleaner.clean_all_text_features(df)

        # Add calculated energy column and the calculation to the df
        df =self.calculator.add_energy_columns(df)  
        
        # Total Energy Comparisons before any case applied
        print("--- BEFORE applying cases ---")
        sanity_check(df)
        
        # The raw dataset after cleaning only text features. This dataset will remain untouched for probable usage in comparisons
        fixed_raw_df = df.copy()

        # Clean numerical data in the dataset
        df, change_df, warnings = self.cleaner.apply_case_logic(df)
        
        # Total Energy Comparisons after all cases applied
        print("--- AFTER applying cases ---")
        sanity_check(df)
        
        # Define how many rows you want
        sample_size = 100

        # Make sure you don't ask for more rows than you have
        if sample_size > len(df):
            sample_size = len(df)

        # Create the sample DataFrame
        # random_state ensures you get the same sample each time you run the code (useful for testing)
        df_sample = df.sample(n=sample_size, random_state=42)

        # # Call the new function
        # df_sample_geocoded = geocode_dataframe(
        #     df, 
        #     "dataset_with_coordinates_.xlsx"
        # )

        #excel_filename = "all_features_cleaned.xlsx"
        #df.to_excel(excel_filename, index=False) # index=False avoids writing the pandas index as a column
        
        #-----Waste Heat Classification using Blablador LLM -----
        categorization_results = categorize_waste_heat_sample(df)
        category_series = pd.Series(categorization_results)
        df_with_categories = df.copy()
        df_with_categories['LLM_Category'] = category_series

        excel_filename = "llm_categorization_all_review2.xlsx"
        try:
            df_with_categories.to_excel(excel_filename, index=False)
            print(f"✅ Review sample saved to: {excel_filename}")
        except Exception as e:
            print(f"❌ Error saving review file: {e}")

        #-----Waste Heat Classification using Manual Rules -----
        # classifier = WasteHeatClassifier()
        # df_sampled_classified = classifier.classify_dataframe(df_sample)
        # df_sampled_classified.to_excel("manual_cat_sample.xlsx", index=False)
       
        return df, raw_df, change_df, warnings, fixed_raw_df#, df_sample#, categorization_results
    
    @staticmethod
    def load_data(file_path):
        return pd.read_excel(file_path, sheet_name='Abwärmepotentiale', skiprows=1, decimal=",",thousands=".", dtype={'PLZ': str})

if __name__ == "__main__":
    file_path = 'src/pfa_wasteheat/pfa_datenpraesentation.xlsx'
    pipeline = WasteHeatAnalysisPipeline(file_path)
    results = pipeline.run() 
    # results.to_csv("processed_data.csv", index=False) 
