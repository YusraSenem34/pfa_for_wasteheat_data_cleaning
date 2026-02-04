#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File              : energy_calculations.py
# License           : License: MIT
# Author            : Yusra Senem yuesra.senem@dlr.de
# Date              : 04.08.2025

import numpy as np
import pandas as pd
from typing import Dict
import calendar
from datetime import date
from workalendar.europe import Germany

class EnergyCalculator:
    """Handles all waste heat energy calculations"""
    def __init__(self, year=2025):
        # Initialize the dictionaries dynamically
        self.weekdays_per_month, self.days_per_month = self._generate_calendar_data(year)

    def _generate_calendar_data(self, year):
        """
        Generates the 'days_per_month' and 'weekdays_per_month' dictionaries
        dynamically for the given year using workalendar.
        """
        cal = Germany()
        weekdays_dict = {}
        days_dict = {}

        # Hardcoded English names to match your existing keys strictly
        month_names = [
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
        ]

        for i, month_name in enumerate(month_names, start=1):
            # 1. Total Days (handles leap years automatically)
            # calendar.monthrange returns (start_weekday, num_days)
            total_days = calendar.monthrange(year, i)[1]
            days_dict[month_name] = total_days

            # 2. Working Days (Mon-Fri minus Holidays)
            # We count days that are NOT weekends and NOT holidays
            working_count = 0
            for day in range(1, total_days + 1):
                if cal.is_working_day(date(year, i, day)):
                    working_count += 1
            
            weekdays_dict[month_name] = working_count
        return weekdays_dict, days_dict
    # # Constants
    # weekdays_per_month = {
    #     'January': 23, 'February': 20, 'March': 23, 'April': 21,
    #     'May': 23, 'June': 22, 'July': 23, 'August': 23,
    #     'September': 21, 'October': 23, 'November': 22, 'December': 23
    # }
        
    # days_per_month = {
    #     'January': 31, 'February': 28, 'March': 31, 'April': 30,
    #     'May': 31, 'June': 30, 'July': 31, 'August': 31,
    #     'September': 30, 'October': 31, 'November': 30, 'December': 31
    # }
        
    power_cols = [
        'Power_Profile_January_kW', 'Power_Profile_February_kW', 'Power_Profile_March_kW',
        'Power_Profile_April_kW', 'Power_Profile_May_kW', 'Power_Profile_June_kW',
        'Power_Profile_July_kW', 'Power_Profile_August_kW', 'Power_Profile_September_kW',
        'Power_Profile_October_kW', 'Power_Profile_November_kW', 'Power_Profile_December_kW'
    ]
    
    months = [col.replace('Power_Profile_', '').replace('_kW', '') 
              for col in power_cols]


    def calculate_annual_energy(self, df:pd.DataFrame) -> pd.Series:
        """
        Calculate annual energy from monthly power profiles
        Formula: Σ (Monthly_Power × Daily_Hours × Working_Days)
        """
        annual_energy = pd.Series(0, index=df.index)
    
        # loop over power columns and their corresponding months
        for month_col, month in zip(self.power_cols, self.months):
            working_days = self._get_working_days(df, month)
            annual_energy += df[month_col] * df['Avg_Daily_Availability_h'] * working_days
        return annual_energy

 
    # def calculate_annual_energy_from_thermal_power(self, df:pd.DataFrame) -> pd.Series:
    #     """
    #     Calculate annual energy using max thermal power
    #     Formula: Max_Thermal_Power × Annual_Working_Hours
    #     """
    #     # reuse your existing function instead of repeating logic
    #     annual_working_hours = self.calculate_annual_working_hours_from_availability(df)

    #     annual_energy_T = df['Max_Thermal_Power_kW'] * annual_working_hours
    #     return annual_energy_T


    # def calculate_annual_energy_from_max_month(self, df:pd.DataFrame) -> pd.Series:
    #     """
    #     Calculate annual energy using the MAXIMUM monthly power value
    #     Formula: Max(Power_Profile_*_kW) × Daily_Hours × Annual_Working_Days
        
    #     Args:
    #         df: Input DataFrame with power columns
            
    #     Returns:
    #         pd.Series with calculated annual energy values
    #     """
    #     # Find max power across all months for each row
    #     max_power = df[self.power_cols].max(axis=1)
        
    #     # Calculate annual working days
    #     # reuse your existing function instead of repeating logic
    #     annual_working_hours = self.calculate_annual_working_hours_from_availability(df)
    #     annual_energy_M = max_power * annual_working_hours
    #     return annual_energy_M
    
    def calculate_annual_energy_from_avg_thermal_power(self, df:pd.DataFrame) -> pd.Series:
        """
        Calculate annual energy using avg thermal power
        Formula: AVG_Thermal_Power × Annual_Working_Hours
        """
        # reuse your existing function instead of repeating logic
        annual_working_hours = self.calculate_annual_working_hours_from_availability(df)
        avg_thermal = self.calculate_avg_thermal_power_by_monthly_powers(df)

        annual_energy_A_T = avg_thermal * annual_working_hours
        return annual_energy_A_T
   
    def calculate_max_avg_thermal_power_from_energy(self, df:pd.DataFrame) -> pd.Series:
        """
        Calculate thermal power from annual energy and working hours
        Formula: Q / h = Annual_Heat_Amount_kWh_per_Year / Annual_Working_Hours
        """
        return df['Annual_Heat_Amount_kWh_per_Year'] / df['Annual_Working_Hours']
    
    def calculate_annual_working_hours_from_availability(self, df: pd.DataFrame) -> pd.Series:
            """
            Calculate Annual_Working_Hours based on monthly working days
            and Avg_Daily_Availability_h.
            """
            annual_hours = pd.Series(0, index=df.index)

            for month in self.months:
                working_days = self._get_working_days(df, month)
                annual_hours += working_days * df['Avg_Daily_Availability_h']
            return annual_hours
    
    def calculate_annual_hours_from_energy_and_power(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate annual working hours using:
        Annual_Working_Hours = Annual_Heat_Amount_per_Year_KWh / Max_Thermal_Power_kW
        """
        return df['Annual_Heat_Amount_kWh_per_Year'] / df['Max_Thermal_Power_kW']

    def calculate_annual_hours_from_energy_and_avg_power(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate annual working hours using:
        Annual_Working_Hours = Annual_Heat_Amount_per_Year_KWh / AVG_Thermal_Power
        """
        return df['Annual_Heat_Amount_kWh_per_Year'] / df['AVG_Thermal_Power']
    
    def calculate_avg_thermal_power_by_monthly_powers(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate average thermal power from monthly power profile.
        Formula: (Sum of monthly power values) / 12
        """
        monthly_powers = df[self.power_cols]   # select all monthly power columns
        return monthly_powers.sum(axis=1) / 12
    
    def calculate_avg_daily_availability(self, df: pd.DataFrame) -> pd.Series:
        """
        Calculate average daily availability (hours).
        Formula: Annual_Working_Hours / Annual Working Days
        """
        # Calculate annual working days by summing over months
        annual_working_days = pd.Series(0, index=df.index)
        for month in self.months:
            annual_working_days += self._get_working_days(df, month)

        return (df['Annual_Working_Hours'] / annual_working_days)

    
    def add_energy_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        df['Annual_Energy_Months'] = self.calculate_annual_energy(df)
        # df['Annual_Energy_Thermal'] = self.calculate_annual_energy_from_thermal_power(df)
        # df['Annual_Energy_MaxMonth'] = self.calculate_annual_energy_from_max_month(df)
        return df

    def correct_powers_watts_to_kw(self, df_unmatched: pd.DataFrame, tolerance=0.10) -> pd.DataFrame:
        """
        Applies the 'Watts to kW' correction strategy to a DataFrame of unmatched rows.
        Returns a DataFrame containing only the newly matched rows with their corrected values.
        """
        # Work on a copy to avoid side effects
        df = df_unmatched.copy()

        # --- STRATEGY 1: Assume Watts, convert to kW ---
        print("\n--- Applying Strategy 1: Watts to kW ---")
        
        # Apply the transformation
        df[self.power_cols] = df[self.power_cols] / 1000
        
        # Recalculate energy and check for matches
        new_energy = self.calculate_annual_energy(df)
        # Use the same logic as your compare_energy_values function for consistency
        provided_energy = df['Annual_Heat_Amount_kWh_per_Year']
        match_mask = (
            (provided_energy * (1 + tolerance) >= new_energy) &
            (provided_energy * (1 - tolerance) <= new_energy)
        )
        
        # Tag the rows that were successfully corrected
        df['Logic_of_Energy_Correction'] = np.where(match_mask, 'Corrected: W to kW', None)
        
        print(f"Matched {match_mask.sum()} rows with this strategy.")
        
        # Return only the subset of rows that were successfully matched and corrected
        return df[match_mask]
    
    def correct_powers_energy_to_power(self, df_unmatched: pd.DataFrame, tolerance=0.10) -> pd.DataFrame:
        """
        Applies the 'Monthly kWh to Power' correction strategy to a DataFrame of unmatched rows.
        Returns a DataFrame containing only the newly matched rows with their corrected values.
        """
        # Work on a copy to avoid side effects
        df = df_unmatched.copy()

        # --- STRATEGY 2: Assume Monthly Energy (kWh), convert to Power (kW) ---
        print("\n--- Applying Strategy 2: Monthly kWh to Power ---")

        # Calculate the operational hours for each month
        monthly_hours = self._get_monthly_hours(df)
        # Avoid division by zero by replacing 0 with NaN
        monthly_hours[monthly_hours == 0] = np.nan

        # Apply the transformation: Power = Energy / Time
        df[self.power_cols] = df[self.power_cols] / monthly_hours

        # Recalculate the total annual energy with the new power values
        new_energy = self.calculate_annual_energy(df)

        # Use the same comparison logic for consistency
        provided_energy = df['Annual_Heat_Amount_kWh_per_Year']
        match_mask = (
            (provided_energy * (1 + tolerance) >= new_energy) &
            (provided_energy * (1 - tolerance) <= new_energy)
        )

        # Tag the rows that were successfully corrected
        df['Logic_of_Energy_Correction'] = np.where(match_mask, 'Corrected: Monthly kWh to Power', None)

        print(f"Matched {match_mask.sum()} rows with this strategy.")

        # Return only the subset of rows that were successfully matched and corrected
        return df[match_mask]

    def correct_powers_wh_to_kw(self, df_unmatched: pd.DataFrame, tolerance=0.10) -> pd.DataFrame:
        """
        Applies the 'Monthly Wh to Power (kW)' correction strategy to a DataFrame.
        Returns a DataFrame containing only the newly matched rows with their corrected values.
        """
        # Work on a copy to avoid side effects
        df = df_unmatched.copy()

        # --- STRATEGY 3: Assume Monthly Wh, convert to Power (kW) ---
        print("\n--- Applying Strategy 3: Monthly Wh to Power ---")

        # Calculate the operational hours for each month
        monthly_hours = self._get_monthly_hours(df)
        # Avoid division by zero by replacing 0 with NaN
        monthly_hours[monthly_hours == 0] = np.nan

        # Apply the transformation: Power (kW) = (Energy (Wh) / 1000) / Time (h)
        df[self.power_cols] = (df[self.power_cols] / 1000) / monthly_hours

        # Recalculate the total annual energy with the new power values
        new_energy = self.calculate_annual_energy(df)

        # Use the same comparison logic for consistency
        provided_energy = df['Annual_Heat_Amount_kWh_per_Year']
        match_mask = (
            (provided_energy * (1 + tolerance) >= new_energy) &
            (provided_energy * (1 - tolerance) <= new_energy)
        )

        # Tag the rows that were successfully corrected
        df['Logic_of_Energy_Correction'] = np.where(match_mask, 'Corrected: Monthly Wh to Power', None)

        print(f"Matched {match_mask.sum()} rows with this strategy.")

        # Return only the subset of rows that were successfully matched and corrected
        return df[match_mask]

    def correct_powers_by_scaling_factor(self, df_unmatched: pd.DataFrame, tolerance=0.10) -> pd.DataFrame:
        """
        Applies a scaling factor to monthly powers to match the provided annual energy.
        Returns a DataFrame containing only the newly matched rows with their corrected values.
        """
        # Work on a copy to avoid side effects
        df = df_unmatched.copy()

        # --- STRATEGY 4: Apply Scaling Factor ---
        print("\n--- Applying Strategy 4: Scaling Factor ---")

        # Calculate the energy with the current (wrong) values
        current_energy = self.calculate_annual_energy(df)
        provided_energy = df['Annual_Heat_Amount_kWh_per_Year']

        # Calculate the scaling factor, avoiding division by zero
        factor = np.where(
            (current_energy > 0) & (provided_energy > 1),
            provided_energy / current_energy,
            1  # Default to 1 (no change) if conditions aren't met
        )

        # Apply the transformation by multiplying each row's power values by its factor
        df[self.power_cols] = df[self.power_cols].multiply(factor, axis=0)

        # Recalculate the total annual energy with the new power values
        new_energy = self.calculate_annual_energy(df)

        # Use the same comparison logic for consistency
        match_mask = (
            (provided_energy * (1 + tolerance) >= new_energy) &
            (provided_energy * (1 - tolerance) <= new_energy)
        )

        # Tag the rows that were successfully corrected
        df['Logic_of_Energy_Correction'] = np.where(match_mask, 'Corrected: Factor Scaling', None)

        print(f"Matched {match_mask.sum()} rows with this strategy.")

        # Return only the subset of rows that were successfully matched and corrected
        return df[match_mask]

    # HELPER FUNCTIONS (internal use only) 
    def _get_working_days(self, df, month):
        """Calculate working days for a month considering weekends (vectorized)."""
        # Create a boolean series to check for weekend availability
        runs_on_weekends = (df['Weekend_Availability'].str.lower() == 'ja')
    
        # Use np.where to choose values based on the condition
        # This is highly efficient and preserves the original index
        return pd.Series(
            np.where(
                runs_on_weekends, 
                self.days_per_month[month],       # Value if True
                self.weekdays_per_month[month]    # Value if False
            ),
            index=df.index  # Explicitly set the index to ensure alignment
        )
    
    def _get_monthly_hours(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates the total operational hours for each month for each row."""
        monthly_hours = {}
        for month_col, month in zip(self.power_cols, self.months):
            working_days = self._get_working_days(df, month)
            monthly_hours[month_col] = working_days * df['Avg_Daily_Availability_h']
        return pd.DataFrame(monthly_hours, index=df.index)