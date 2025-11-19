#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
from wasteheat_analyzer import WasteHeatAnalyzer
# from energy_calculations import EnergyCalculator # Uncomment if needed

def sanity_check(df, comparison_results=None):
    """
    Prints a summary of matched vs. unmatched rows.
    
    Args:
        df (pd.DataFrame): The dataframe containing energy columns.
        comparison_results (list, optional): Pre-calculated results from analyzer.
                                             If None, they will be calculated on the fly.
    """
    # 1. Create the tool
    analyzer = WasteHeatAnalyzer()

    # 2. Calculate results if they weren't passed in
    if comparison_results is None:
        # compare_energy_values is an instance method, so we call it on 'analyzer'
        # It takes 'df' as an argument now.
        df, comparison_results = analyzer.compare_energy_values(df, tolerance=0.10)

    # 3. Build the summary
    # build_comparison_summary is static, so calling it on the class is fine
    summary_df = WasteHeatAnalyzer.build_comparison_summary(df, comparison_results)
    
    print("The Shape of the dataframe: ")
    print(df.shape)
    print("Total Energy Comparisons: ")
    print(summary_df)

def check_working_hours_limits(df, tolerance=0.05):
    """
    Check if Annual_Working_Hours exceeds allowed maximum based on daily and weekend availability.
    Weekend_Availability should be boolean: True = works weekends, False = no weekends.
    """
    # Work on a copy to avoid adding helper columns to the main DataFrame
    df_check = df.copy()

    # Determine number of days per year
    df_check['Days_Per_Year'] = df_check['Weekend_Availability'].apply(lambda x: 365 if x else 261)

    # Calculate max possible annual working hours
    df_check['Max_Possible_Working_Hours'] = df_check['Avg_Daily_Availability_h'] * df_check['Days_Per_Year']

    # Only check rows where Annual_Working_Hours is not NaN
    mask_not_empty = df_check['Annual_Working_Hours'].notna()

    # Find violations
    violations = df_check[
        mask_not_empty & 
        (df_check['Annual_Working_Hours'] > (df_check['Max_Possible_Working_Hours'] * (1 + tolerance)))
    ]

    return violations