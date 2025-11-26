#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File              : main.py
# License           : License: MIT
# Author            : Yusra Senem yuesra.senem@dlr.de
# Date              : 02.08.2025

import pandas as pd

# --- Custom Imports ---
from data_cleaning import DataCleaner
from energy_calculations import EnergyCalculator
from wasteheat_analyzer import WasteHeatAnalyzer
from utils import sanity_check

# Import the geocoding function from your external file
from geocode import geocode_dataframe

from categorization_of_wasteheat import categorize_waste_heat # Uncomment to use LLM

class WasteHeatAnalysisPipeline:
    def __init__(self, input_path=None):
        """
        Initialize the pipeline tools. 
        Data loading is deferred to the run() method to allow Streamlit uploads.
        """
        self.input_path = input_path
        
        # Initialize tools that don't need data yet
        self.calculator = EnergyCalculator()
        self.cleaner = DataCleaner()
        
        # Analyzer is stateless, so we can initialize it here
        self.analyzer = WasteHeatAnalyzer()

    @staticmethod
    def load_data(file_path):
        """Loads data from a local file path with German formatting."""
        return pd.read_excel(
            file_path, 
            sheet_name='Abwärmepotentiale', 
            skiprows=1, 
            decimal=",", 
            thousands=".", 
            dtype={'PLZ': str}
        )

    def run(self, df=None, run_geocoding=False):
        """
        Runs the full analysis pipeline.
        Args:
            df (pd.DataFrame): DataFrame provided by Streamlit. 
                               If None, loads from self.input_path.
            run_geocoding (bool): Whether to generate the geocoded sample file.
        """
        # --- 1. Logic to determine data source ---
        if df is None:
            if self.input_path:
                print(f"Loading data from path: {self.input_path}")
                df = self.load_data(self.input_path)
            else:
                raise ValueError("Pipeline Error: No DataFrame provided and no input path specified.")
        
        # Ensure tracking column exists
        if 'Original_Excel_Row' not in df.columns:
            df['Original_Excel_Row'] = df.index + 3

        print("Running analysis pipeline...")
        
        # Keep a copy of raw data for comparison later
        raw_df = df.copy()
        
        # --- 2. Text Cleaning Phase ---
        df = self.cleaner.clean_column_names(df)
        df = self.cleaner.clean_all_text_features(df)

        # --- 3. Energy Calculation Phase ---
        df = self.calculator.add_energy_columns(df)  
        
        print("--- BEFORE applying cases ---")
        # Force recalculation inside sanity_check
        sanity_check(df) 
        
        fixed_raw_df = df.copy()

        # --- 4. Numerical Cleaning Phase (Case Logic) ---
        df, change_df, warnings = self.cleaner.apply_case_logic(df)
        
        print("--- AFTER applying cases ---")
        # Force recalculation inside sanity_check
        sanity_check(df)
        
        # --- 5. Geocoding Sample (Optional) ---
        if run_geocoding:
            sample_size = 100
            if sample_size > len(df):
                sample_size = len(df)

            # Create a clean sample for geocoding
            df_sample = df.sample(n=sample_size, random_state=42).copy()

            print("Running geocoding on sample...")
            
            # Call the imported function from geocode.py
            geocode_dataframe(
                df_sample, 
                "data_with_coordinates_SAMPLE.xlsx"
            )

        #-----6. Waste Heat Classification using Blablador LLM -----
        # categorization_results = categorize_waste_heat(df)
        # category_series = pd.Series(categorization_results)
        # df_with_categories = df.copy()
        # df_with_categories['LLM_Category'] = category_series

        # excel_filename = "data/llm_categorization_all_latest.xlsx"
        # try:
        #     df_with_categories.to_excel(excel_filename, index=False)
        #     print(f"✅ Review sample saved to: {excel_filename}")
        # except Exception as e:
        #     print(f"❌ Error saving review file: {e}")

        print("Pipeline run finished.")
        return df, raw_df, change_df, warnings, fixed_raw_df

if __name__ == "__main__":
    # This block handles local testing via 'python main.py'
    input_path = 'src/pfa_wasteheat/pfa_datenpraesentation.xlsx'
    
    pipeline = WasteHeatAnalysisPipeline(input_path)
    
    # We call run() without arguments, so it uses the path
    results = pipeline.run(run_geocoding=False)