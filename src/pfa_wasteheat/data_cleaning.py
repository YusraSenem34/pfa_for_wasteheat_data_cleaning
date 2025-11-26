#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File              : data_cleaning.py
# License           : License: MIT
# Author            : Yusra Senem yuesra.senem@dlr.de
# Date              : 16.07.2025


import pandas as pd
import numpy as np
import re
from typing import Tuple
from energy_calculations import *
from wasteheat_analyzer import *
from utils import sanity_check, check_working_hours_limits

class DataCleaner:
    """Handles all data cleaning and preprocessing operations"""
    
    def __init__(self):
        # Constants
        self.changelog = []
        self.warnings = []
        # inside DataCleaner.apply_case_logic
        self.column_mapping = {
            # German to English column name mapping
            "Firmenname": "Company_Name",
            "Standortname": "Site_Name",
            "Straße_und_Hausnummer": "Street_and_House_Number", 
            "PLZ": "Postal_Code", 
            "Ort": "City",
            "Name_des_Abwärmepotentials": "Waste_Heat_Potential_Name", 
            "Wärmemenge_pro_Jahr_(in_kWh/a)": "Annual_Heat_Amount_kWh_per_Year", 
            "Maximale_thermische_Leistung_(in_kW)": "Max_Thermal_Power_kW",
            "Durchschnittliches_Temperaturniveau_(in_°C)": "Avg_Temperature_Level_C", 
            "Temperaturbereich": "Temperature_Range", 
            "Durchschnittliche_tägl._Verfügbarkeit_(in_h)": "Avg_Daily_Availability_h",
            "Verfügbarkeit_am_Wochenende": "Weekend_Availability", 
            "Verfügbarkeit": "Availability", 
            "Vorhersehbarkeit_der_Verfügbarkeit": "Availability_Predictability",
            "Vorhandene_Regelungsmöglichkeiten": "Existing_Control_Options", 
            "Leistungsprofil_Januar_(in_kW)": "Power_Profile_January_kW", 
            "Leistungsprofil_Februar_(in_kW)": "Power_Profile_February_kW",
            "Leistungsprofil_März_(in_kW)": "Power_Profile_March_kW", 
            "Leistungsprofil_April_(in_kW)": "Power_Profile_April_kW", 
            "Leistungsprofil_Mai_(in_kW)": "Power_Profile_May_kW",
            "Leistungsprofil_Juni_(in_kW)": "Power_Profile_June_kW", 
            "Leistungsprofil_Juli_(in_kW)": "Power_Profile_July_kW", 
            "Leistungsprofil_August_(in_kW)": "Power_Profile_August_kW",
            "Leistungsprofil_September_(in_kW)": "Power_Profile_September_kW", 
            "Leistungsprofil_Oktober_(in_kW)": "Power_Profile_October_kW", 
            "Leistungsprofil_November_(in_kW)": "Power_Profile_November_kW",
            "Leistungsprofil_Dezember_(in_kW)": "Power_Profile_December_kW", 
            "Ergänzende_Informationen_zum_Abwärmepotential": "Additional_Info_on_Waste_Heat_Potential", 
            "E-Mail-Adresse": "Email_Address",
            "Telefonnummer": "Phone_Number", 
            "Weitere_Hinweise": "Additional_Notes"
        }

    def clean_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize and rename columns"""
        # Clean existing names
        df.columns = [ re.sub(r'\s+', '_', col.replace('\n', ' ').replace('\r', ' ').strip()) for col in df.columns]
        
        # Rename German to English
        df.rename(columns=self.column_mapping, inplace=True)
        
        # Remove unnecessary columns
        cols_to_drop = ["Email_Address", "Phone_Number", "Additional_Notes"]
        return df.drop(columns=[col for col in cols_to_drop if col in df.columns], errors='ignore')

    def clean_all_text_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Runs a comprehensive cleaning and parsing pipeline on all text features
        in the correct order to prepare for geocoding and analysis.
        """
        print("*** RUNNING v3.0 OF clean_all_text_features (WITH THE 'E-' FIX) ***")
        
        # --- 1. CLEAN ADDRESS DATA (FOR GEOCODING) ---

        if 'City' in df.columns:
            print("[DataCleaner] Cleaning 'City' column...")
            clean_col = df['City'].astype(str).str.strip()

            #Fix Country Prefixes
            #    e.g., "De-86983 Lechbruck Am See" -> "86983 Lechbruck Am See"
            #    e.g., "D - 86983..." -> "86983..."
            # Regex: Finds 'D','DE' or 'E' at the start, followed by optional spaces/hyphens
            country_prefix_pattern = r'^(DE|D|E)[\s-]*(\d)'
        
            clean_col = clean_col.str.replace(country_prefix_pattern, r'\2', regex=True, case=False).str.strip()
            
            # Fix: "38642_Goslar" or "38642 Goslar" -> "Goslar"
            regex_pattern = r'^(\d{5})[_\s-]*(.*)$'
            clean_col = clean_col.str.replace(regex_pattern, r'\2', regex=True).str.strip()
            
            # Fix: "Aalen, Daimlerstr." -> "Aalen"
            clean_col = clean_col.str.split(',').str[0].str.strip()
            
            # Fix: "Achim/Embsen" -> "Achim"
            clean_col = clean_col.str.split('/').str[0].str.strip()
            
            # Fix: "Albersdorf OT Rendsburg" -> "Albersdorf"
            clean_col = clean_col.str.split(r'\s+OT\s+', regex=True).str[0].str.strip()

            # We now check for these words anchored to the start (^)
            # or as whole words (\b) to avoid matching parts of city names.
            junk_indicators = [
                r'^An der ',      # Starts with "An der "
                r'^Im ',          # Starts with "Im "
                r'^Auf der ',     # Starts with "Auf der "
                r'^Straße\s',     # Starts with "Straße "
                r'\bunbekannt\b', # The whole word 'unbekannt'
                r'\bsiehe\b'      # The whole word 'siehe'
                ]
            mask = clean_col.str.contains('|'.join(junk_indicators), case=False, na=False)
            clean_col.loc[mask] = pd.NA
            
            # Final cleanup (capitalize, fix spaces, keep hyphens)
            clean_col = clean_col.str.replace(r'[\r\n\t_]+', ' ', regex=True).str.replace(r'\s+', ' ', regex=True)
            df['City'] = clean_col.str.strip().str.title()
            df.loc[df['City'] == '', 'City'] = pd.NA # Set empty strings to NA

        if 'Street_and_House_Number' in df.columns:
            print("[DataCleaner] Cleaning 'Street_and_House_Number' column...")
            clean_col = df['Street_and_House_Number'].astype(str).str.strip()
            

            # Fix: Normalize newlines, tabs, and underscores to spaces
            clean_col = clean_col.str.replace(r'[\r\n\t_]+', ' ', regex=True)
            
            # Fix: Nullify junk data
            junk_indicators = ['Postfach', 'unbekannt', 'keine Angabe', 'siehe']
            mask = clean_col.str.contains('|'.join(junk_indicators), case=False, na=False)
            clean_col.loc[mask] = pd.NA
            
            # Standardize 'str.' to 'straße'
            clean_col = clean_col.str.replace(r'str\.', 'straße', regex=True, case=False)
            clean_col = clean_col.str.replace(r'Bismarkstrasse', 'Bismarckstraße', regex=True, case=False)

            # This looks for company indicators and removes everything before them
            company_indicators = ['Gmbh', 'AG', 'KG', 'Stiftung', 'Co\.']
            # Regex: (.*?) finds the company name, (\b(Gmbh|AG|...)\b) finds the indicator,
            # and (.*) finds the real street address after it.
            regex_pattern = r'^(.*?)(\b(' + '|'.join(company_indicators) + r')\b)(.*)$'
            # We replace the entire string with just the 4th part (the real street)
            clean_col = clean_col.str.replace(regex_pattern, r'\4', regex=True, case=False).str.strip()

            clean_col = clean_col.str.replace('Ã', 'ß', regex=False)
            
            # Final cleanup (consolidate spaces, capitalize)
            clean_col = clean_col.str.replace(r'\s+', ' ', regex=True)
            df['Street_and_House_Number'] = clean_col.str.strip().str.title()

            

        if 'Postal_Code' in df.columns:
            print("[DataCleaner] Cleaning 'Postal_Code' column...")
            clean_col = df['Postal_Code'].astype(str).str.strip()
            
            # Extract the first 5-digit number found
            extracted_plz = clean_col.str.extract(r'(\d{5})')
            df['Postal_Code'] = extracted_plz # This will be NA if no 5-digit number was found
            
        
        # --- 2. CLEAN GENERAL NAME COLUMNS ---
        
        name_cols = ['Company_Name', 'Site_Name', 'Waste_Heat_Potential_Name']
        for col in name_cols:
            if col in df.columns:
                clean_col = df[col].astype(str).str.strip()
                # Normalize separators (slash, underscore) to spaces
                clean_col = clean_col.str.replace(r'[/\_]+', ' ', regex=True)
                # Remove newlines and tabs
                clean_col = clean_col.str.replace(r'[\r\n\t]+', ' ', regex=True)
                # Consolidate multiple spaces into one
                clean_col = clean_col.str.replace(r'\s+', ' ', regex=True)
                # Final strip and capitalize (we keep hyphens)
                df[col] = clean_col.str.strip().str.title()

        # --- 3. CLEAN CATEGORICAL COLUMNS ---
        
        cat_cols = [
            'Temperature_Range', 'Weekend_Availability', 'Availability', 
            'Availability_Predictability', 'Existing_Control_Options'
        ]
        for col in cat_cols:
            if col in df.columns:
                clean_col = df[col].astype(str).str.strip()
                # Just strip, lowercase, and set empty to NA
                clean_col = clean_col.str.lower()
                clean_col[clean_col.isin(['', 'nan', 'none'])] = pd.NA
                df[col] = clean_col

        # --- 4. CLEAN NOTES FIELD ---
        
        if 'Additional_Info_on_Waste_Heat_Potential' in df.columns:
            clean_col = df['Additional_Info_on_Waste_Heat_Potential'].astype(str).str.strip()
            # Just fix whitespace, don't change case or remove punctuation
            clean_col = clean_col.str.replace(r'[\r\n\t]+', ' ', regex=True)
            clean_col = clean_col.str.replace(r'\s+', ' ', regex=True)
            clean_col[clean_col.isin(['', 'nan', 'none'])] = pd.NA
            df[col] = clean_col.str.strip()

        print("[DataCleaner] All text features have been cleaned.")
        return df
    
 
    def _get_power_statistics(self, df: pd.DataFrame) -> pd.DataFrame:
        power_df = df[EnergyCalculator.power_cols]
        return pd.DataFrame({
        'monthly_any_gt1': (power_df > 1).any(axis=1), # at least one monthly value is > 1
        'monthly_all_less1': (power_df <= 1).all(axis=1), # all monthly values <= 1
        'monthly_all_equal': power_df.nunique(axis=1).eq(1),
        'max_monthly_power': power_df.max(axis=1)
    }, index=df.index)
    def _update_working_hours_from_availability(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator, case_name: str, reason: str = "") -> pd.DataFrame:
        """
        Calculate Annual_Working_Hours based on monthly working days
        and Avg_Daily_Availability_h.
        """
        if mask.sum() == 0:
            self.warnings.append(f"[{case_name}] No rows matched — no updates performed.")
            return df

        updated_rows = df[mask].copy()
        updated_rows['prev_Annual_Working_Hours'] = updated_rows['Annual_Working_Hours']

        df.loc[mask, 'Annual_Working_Hours'] = calculator.calculate_annual_working_hours_from_availability(df[mask])
        updated_rows['new_Annual_Working_Hours'] = df.loc[mask, 'Annual_Working_Hours']
        updated_rows['change_reason'] = case_name
        self.changelog.append(updated_rows)
        print(f"[Update] {len(updated_rows)} rows Updated. Reason: {reason}")

        print(f"[{case_name}] Updated Annual_Working_Hours for {mask.sum()} rows.")
        return df
    def _update_annual_heat_with_calc_energy(self, df: pd.DataFrame, mask: pd.Series, case_name: str, reason: str = "") -> pd.DataFrame:
        if mask.sum() == 0:
            self.warnings.append(f"[{case_name}] No rows matched — no updates performed.")
            return df
        updated_rows = df[mask].copy()
        updated_rows['prev_Annual_Heat_Amount_kWh_per_Year'] = updated_rows['Annual_Heat_Amount_kWh_per_Year'] #for changelog

        # Update annual heat amount with calculated annual energy
        df.loc[mask, 'Annual_Heat_Amount_kWh_per_Year'] = EnergyCalculator().calculate_annual_energy(df.loc[mask])

        updated_rows['new_Annual_Heat_Amount_kWh_per_Year'] = df.loc[mask, 'Annual_Heat_Amount_kWh_per_Year']
        # Tag change reason in both changelog AND dataframe
        df.loc[mask, 'change_reason'] = case_name
        updated_rows['change_reason'] = case_name # don't forget to add it for other functions as well.
        self.changelog.append(updated_rows) #for changelog
        print(f"[Update] {len(updated_rows)} rows Updated. Reason: {reason}")

        return df

    def _update_annual_heat_with_calc_from_power(self, df: pd.DataFrame, mask: pd.Series, case_name: str, reason: str = "") -> pd.DataFrame:
        if mask.sum() == 0:
            self.warnings.append(f"[{case_name}] No rows matched — no updates performed.")
            return df        
        updated_rows = df[mask].copy()
        updated_rows['prev_Annual_Heat_Amount_kWh_per_Year'] = updated_rows['Annual_Heat_Amount_kWh_per_Year'] #for changelog

        # Update annual heat amount with calculated annual energy from thermal power
        df.loc[mask, 'Annual_Heat_Amount_kWh_per_Year'] = EnergyCalculator().calculate_annual_energy_from_thermal_power(df.loc[mask])
        
        updated_rows['new_Annual_Heat_Amount_kWh_per_Year'] = df.loc[mask, 'Annual_Heat_Amount_kWh_per_Year']
        updated_rows['change_reason'] = case_name
        self.changelog.append(updated_rows) #for changelog
        print(f"[Update] {len(updated_rows)} rows Updated. Reason: {reason}")

        return df
   
    def _update_annual_heat_from_avg_power(self, df: pd.DataFrame, mask: pd.Series, case_name: str, reason: str = "") -> pd.DataFrame:
        """
        Calculate annual energy using avg thermal power
        Formula: AVG_Thermal_Power × Annual_Working_Hours
        """
        if mask.sum() == 0:
            self.warnings.append(f"[{case_name}] No rows matched — no updates performed.")
            return df        
        updated_rows = df[mask].copy()
        updated_rows['prev_Annual_Heat_Amount_kWh_per_Year'] = updated_rows['Annual_Heat_Amount_kWh_per_Year'] #for changelog

        # Update annual heat amount with calculated annual energy from thermal power
        df.loc[mask, 'Annual_Heat_Amount_kWh_per_Year'] = EnergyCalculator().calculate_annual_energy_from_avg_thermal_power(df.loc[mask])
        
        updated_rows['new_Annual_Heat_Amount_kWh_per_Year'] = df.loc[mask, 'Annual_Heat_Amount_kWh_per_Year']
        updated_rows['change_reason'] = case_name
        self.changelog.append(updated_rows) #for changelog
        print(f"[Update] {len(updated_rows)} rows Updated. Reason: {reason}")

        return df
    
    def _update_max_power_from_monthly_max(self, df: pd.DataFrame, mask: pd.Series, case_name: str, reason: str = "") -> pd.DataFrame:
        if mask.sum() == 0:
            self.warnings.append(f"[{case_name}] No rows matched — no updates performed.")
            return df
        updated_rows = df[mask].copy()
        updated_rows['prev_Max_Thermal_Power_kW'] = updated_rows['Max_Thermal_Power_kW']
    
        # Update Max_Thermal_Power_kW with the max monthly value
        max_monthly_power = df.loc[mask, EnergyCalculator.power_cols].max(axis=1)
        df.loc[mask, 'Max_Thermal_Power_kW'] = max_monthly_power

        # Now update Annual_Heat with thermal power method
        df = self._update_annual_heat_with_calc_from_power(df, mask)

        updated_rows['new_Max_Thermal_Power_kW'] = df.loc[mask, 'Max_Thermal_Power_kW']
        updated_rows['change_reason'] = case_name
        self.changelog.append(updated_rows) #for changelog
        print(f"[Update] {len(updated_rows)} rows Updated. Reason: {reason}")
        
        return df
    
    def _drop_rows(self, df: pd.DataFrame, mask: pd.Series, case_name: str, reason: str = "") -> pd.DataFrame:
        """Drop rows based on mask and optionally log reason"""
        if mask.sum() == 0:
            self.warnings.append(f"[{case_name}] No rows matched — no updates performed.")
            return df
        dropped = df[mask].copy() 
        if not dropped.empty:
            dropped['change_reason'] = case_name
            self.changelog.append(dropped) #for changelog
            print(f"[Drop] {len(dropped)} rows dropped. Reason: {reason}")
        return df[~mask].copy()
    
    def _update_max_power_from_monthly(self, df: pd.DataFrame, mask: pd.Series, case_name: str, reason: str = "") -> pd.DataFrame:
        """Update Max_Thermal_Power_kW with max of monthly power columns"""
        if mask.sum() == 0:
            self.warnings.append(f"[{case_name}] No rows matched — no updates performed.")
            return df
        updated_rows = df[mask].copy()
        updated_rows['prev_Max_Thermal_Power_kW'] = updated_rows['Max_Thermal_Power_kW'] #for changelog

        df.loc[mask, 'Max_Thermal_Power_kW'] = df.loc[mask, EnergyCalculator.power_cols].max(axis=1)

        updated_rows['new_Max_Thermal_Power_kW'] = df.loc[mask, 'Max_Thermal_Power_kW']
        updated_rows['change_reason'] = case_name
        self.changelog.append(updated_rows) #for changelog
        print(f"[Update] {len(updated_rows)} rows Updated. Reason: {reason}")
        
        return df
    
    def _update_thermal_power_with_calculated_thermal(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator, case_name: str, reason: str = "") -> pd.DataFrame:
        """
        Update Max_Thermal_Power and monthly power values with calculated thermal power
        """
        if mask.sum() == 0:
            self.warnings.append(f"[{case_name}] No rows matched — no updates performed.")
            return df
        updated_rows = df[mask].copy()
        for col in EnergyCalculator.power_cols + ['Max_Thermal_Power_kW']:
            updated_rows[f'prev_{col}'] = updated_rows[col] #for changelog

        calculated_power = calculator.calculate_max_avg_thermal_power_from_energy(df[mask])
        df.loc[mask, 'Max_Thermal_Power_kW'] = calculated_power
        for col in EnergyCalculator.power_cols:
            df.loc[mask, col] = calculated_power

        for col in EnergyCalculator.power_cols + ['Max_Thermal_Power_kW']:
            updated_rows[f'new_{col}'] = df.loc[mask, col]
        updated_rows['change_reason'] = case_name
        self.changelog.append(updated_rows) #for changelog
        print(f"[Update] {len(updated_rows)} rows Updated. Reason: {reason}")

        return df
    
    def _update_monthly_power_with_max_power(self, df: pd.DataFrame, mask: pd.Series, case_name: str, reason: str = "") -> pd.DataFrame:
        """Only update monthly power columns with Max_Thermal_Power_kW """
        if mask.sum() == 0:
            self.warnings.append(f"[{case_name}] No rows matched — no updates performed.")
            return df
        updated_rows = df[mask].copy()
        for col in EnergyCalculator.power_cols:
            updated_rows[f'prev_{col}'] = updated_rows[col] #for changelog

        for col in EnergyCalculator.power_cols:
            df.loc[mask, col] = df.loc[mask, 'Max_Thermal_Power_kW']

        for col in EnergyCalculator.power_cols:
            updated_rows[f'new_{col}'] = df.loc[mask, col]
        updated_rows['change_reason'] = case_name
        self.changelog.append(updated_rows) #for changelog
        print(f"[Update] {len(updated_rows)} rows Updated. Reason: {reason}")

        return df
    
    def _update_annual_hours_with_calculated(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator, case_name: str, reason: str = "") -> pd.DataFrame:
        """
        Calculate annual working hours using:
        Annual_Working_Hours = Annual_Heat_Amount_per_Year_KWh / Max_Thermal_Power_kW
        """
        if mask.sum() == 0:
            self.warnings.append(f"[{case_name}] No rows matched — no updates performed.")
            return df
        updated_rows = df[mask].copy()
        updated_rows['prev_Annual_Working_Hours'] = updated_rows['Annual_Working_Hours'] #for changelog

        calculated_hours = calculator.calculate_annual_hours_from_energy_and_power(df[mask])
        df.loc[mask, 'Annual_Working_Hours'] = calculated_hours
        
        updated_rows['new_Annual_Working_Hours'] = df.loc[mask, 'Annual_Working_Hours']
        updated_rows['change_reason'] = case_name
        self.changelog.append(updated_rows) #for changelog
        print(f"[Update] {len(updated_rows)} rows Updated. Reason: {reason}")
        
        return df
    
    def _update_avg_daily_availability(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator, case_name: str, reason: str = "") -> pd.DataFrame:
        """
        Calculate average daily availability (hours).
        Formula: Annual_Working_Hours / Annual Working Days
        """
        if mask.sum() == 0:
            self.warnings.append(f"[{case_name}] No rows matched — no updates performed.")
            return df

        # Keep track of the rows being updated
        updated_rows = df[mask].copy()
        updated_rows['prev_Avg_Daily_Availability_h'] = updated_rows['Avg_Daily_Availability_h']  # for changelog

        # Use calculator to compute new values
        # Use calculator to compute new values
        calculated_availability_float = calculator.calculate_avg_daily_availability(df[mask])

        # Apply custom rounding logic using np.where
        calculated_availability_int = np.where(
            # Condition 1: Is the value between 0 (exclusive) and 1 (exclusive)?
            (calculated_availability_float > 0) & (calculated_availability_float < 1), 
            # Value if True: Round up to 1
            1, 
            # Value if False: Round down (take the floor)
            np.floor(calculated_availability_float) 
        ).astype(int) # Convert the final result to integer

        # Assign the correctly rounded integer value
        df.loc[mask, 'Avg_Daily_Availability_h'] = calculated_availability_int
        df.loc[mask, 'Avg_Daily_Availability_h'] = calculated_availability_int

        # Track changes
        updated_rows['new_Avg_Daily_Availability_h'] = df.loc[mask, 'Avg_Daily_Availability_h']
        updated_rows['change_reason'] = case_name
        self.changelog.append(updated_rows)
        print(f"[Update] {len(updated_rows)} rows Updated. Reason: {reason}")
    
        return df


    def _update_monthly_power_with_avg_thermal_power(self, df: pd.DataFrame, mask: pd.Series, case_name: str, reason: str = "") -> pd.DataFrame:
        """Only update monthly power columns with AVG_Thermal_Power """
        if mask.sum() == 0:
            self.warnings.append(f"[{case_name}] No rows matched — no updates performed.")
            return df
        updated_rows = df[mask].copy()
        for col in EnergyCalculator.power_cols:
            updated_rows[f'prev_{col}'] = updated_rows[col] #for changelog

        for col in EnergyCalculator.power_cols:
            df.loc[mask, col] = df.loc[mask, 'AVG_Thermal_Power']

        for col in EnergyCalculator.power_cols:
            updated_rows[f'new_{col}'] = df.loc[mask, col]
        updated_rows['change_reason'] = case_name
        self.changelog.append(updated_rows) #for changelog
        print(f"[Update] {len(updated_rows)} rows Updated. Reason: {reason}")

        return df
    
    def _update_annual_hours_with_avg_power(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator, case_name: str, reason: str = "") -> pd.DataFrame:
        """
        Calculate annual working hours using:
        Annual_Working_Hours = Annual_Heat_Amount_per_Year_KWh / AVG_Thermal_Power
        """
        if mask.sum() == 0:
            self.warnings.append(f"[{case_name}] No rows matched — no updates performed.")
            return df
        updated_rows = df[mask].copy()
        updated_rows['prev_Annual_Working_Hours'] = updated_rows['Annual_Working_Hours'] #for changelog

        calculated_hours = calculator.calculate_annual_hours_from_energy_and_avg_power(df[mask])
        df.loc[mask, 'Annual_Working_Hours'] = calculated_hours
        
        updated_rows['new_Annual_Working_Hours'] = df.loc[mask, 'Annual_Working_Hours']
        updated_rows['change_reason'] = case_name
        self.changelog.append(updated_rows) #for changelog
        print(f"[Update] {len(updated_rows)} rows Updated. Reason: {reason}")
        
        return df
    
    def _apply_power_correction(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator, case_name: str, reason: str = "") -> pd.DataFrame:
        """
        Wrapper function to apply a power correction strategy and handle the changelog.
        """
        if not mask.any():
            self.warnings.append(f"[{case_name}] No rows matched the criteria for correction.")
            return df

        # Get the subset of rows that will be tested for correction
        unmatched_df = df[mask].copy()
        
        # --- Call the calculation logic from EnergyCalculator ---
        # This returns a DataFrame with *only* the successfully corrected rows
        corrected_subset = calculator.correct_powers_watts_to_kw(unmatched_df)

        if corrected_subset.empty:
            print(f"[{case_name}] No rows were successfully corrected by this logic.")
            return df

        # --- Handle Changelog and Update Main DataFrame ---
        matched_indices = corrected_subset.index

        # Create the changelog entry from the original state of the matched rows
        updated_rows_log = df.loc[matched_indices].copy()
        for col in EnergyCalculator.power_cols:
            updated_rows_log[f'prev_{col}'] = updated_rows_log[col]

        # Update the main DataFrame with the corrected values
        df.loc[matched_indices, EnergyCalculator.power_cols] = corrected_subset[EnergyCalculator.power_cols]
        df.loc[matched_indices, 'Logic_of_Energy_Correction'] = corrected_subset['Logic_of_Energy_Correction']

        # Add the new values to the changelog entry
        for col in EnergyCalculator.power_cols:
            updated_rows_log[f'new_{col}'] = df.loc[matched_indices, col]
        updated_rows_log['change_reason'] = case_name
        self.changelog.append(updated_rows_log)

        print(f"[{case_name}] Successfully updated {len(matched_indices)} rows in the main DataFrame.")
        
        return df
    
    def _apply_power_correction_strategy2(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator, case_name: str, reason: str = "") -> pd.DataFrame:
        if not mask.any(): return df
        unmatched_df = df[mask].copy()
        
        # Call the new calculation function for Strategy 2
        corrected_subset = calculator.correct_powers_energy_to_power(unmatched_df)

        if corrected_subset.empty:
            print(f"[{case_name}] No rows were successfully corrected.")
            return df

        # --- Handle Changelog and Update (this part is the same) ---
        matched_indices = corrected_subset.index
        updated_rows_log = df.loc[matched_indices].copy()
        for col in EnergyCalculator.power_cols:
            updated_rows_log[f'prev_{col}'] = updated_rows_log[col]

        df.loc[matched_indices, EnergyCalculator.power_cols] = corrected_subset[EnergyCalculator.power_cols]
        df.loc[matched_indices, 'Logic_of_Energy_Correction'] = corrected_subset['Logic_of_Energy_Correction']

        for col in EnergyCalculator.power_cols:
            updated_rows_log[f'new_{col}'] = df.loc[matched_indices, col]
        updated_rows_log['change_reason'] = case_name
        self.changelog.append(updated_rows_log)

        print(f"[{case_name}] Successfully updated {len(matched_indices)} rows.")
        return df
    
    def _apply_power_correction_strategy3(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator, case_name: str, reason: str = "") -> pd.DataFrame:
        if not mask.any(): return df
        unmatched_df = df[mask].copy()
        
        # Call the new calculation function for Strategy 3
        corrected_subset = calculator.correct_powers_wh_to_kw(unmatched_df)

        if corrected_subset.empty:
            print(f"[{case_name}] No rows were successfully corrected.")
            return df

        # --- Handle Changelog and Update (this part is the same) ---
        matched_indices = corrected_subset.index
        updated_rows_log = df.loc[matched_indices].copy()
        for col in EnergyCalculator.power_cols:
            updated_rows_log[f'prev_{col}'] = updated_rows_log[col]

        df.loc[matched_indices, EnergyCalculator.power_cols] = corrected_subset[EnergyCalculator.power_cols]
        df.loc[matched_indices, 'Logic_of_Energy_Correction'] = corrected_subset['Logic_of_Energy_Correction']

        for col in EnergyCalculator.power_cols:
            updated_rows_log[f'new_{col}'] = df.loc[matched_indices, col]
        updated_rows_log['change_reason'] = case_name
        self.changelog.append(updated_rows_log)

        print(f"[{case_name}] Successfully updated {len(matched_indices)} rows.")
        return df
    
    def _apply_power_correction_strategy4(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator, case_name: str, reason: str = "") -> pd.DataFrame:
        if not mask.any(): return df
        unmatched_df = df[mask].copy()
        
        # Call the new calculation function for Strategy 4
        corrected_subset = calculator.correct_powers_by_scaling_factor(unmatched_df)

        if corrected_subset.empty:
            print(f"[{case_name}] No rows were successfully corrected.")
            return df

        # --- Handle Changelog and Update (this part is the same) ---
        matched_indices = corrected_subset.index
        updated_rows_log = df.loc[matched_indices].copy()
        for col in EnergyCalculator.power_cols:
            updated_rows_log[f'prev_{col}'] = updated_rows_log[col]

        df.loc[matched_indices, EnergyCalculator.power_cols] = corrected_subset[EnergyCalculator.power_cols]
        df.loc[matched_indices, 'Logic_of_Energy_Correction'] = corrected_subset['Logic_of_Energy_Correction']

        for col in EnergyCalculator.power_cols:
            updated_rows_log[f'new_{col}'] = df.loc[matched_indices, col]
        updated_rows_log['change_reason'] = case_name
        self.changelog.append(updated_rows_log)

        print(f"[{case_name}] Successfully updated {len(matched_indices)} rows.")
        return df

    def _update_avg_thermal_power_from_monthly(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator, case_name: str, reason: str = "") -> pd.DataFrame:
        """
        Calculate and update the AVG_Thermal_Power column based on monthly power profiles.
        Formula: (Sum of monthly power values) / 12
        """
        if not mask.any(): # Use 'not mask.any()' for clarity
            self.warnings.append(f"[{case_name}] No rows matched — no updates performed.")
            return df

        # --- Calculation ---
        # Calculate the average power only for the specified subset
        calculated_avg_power = calculator.calculate_avg_thermal_power_by_monthly_powers(df[mask])

        # --- Changelog Preparation ---
        # Copy the original values *before* updating the DataFrame
        updated_rows = df[mask].copy()
        updated_rows['prev_AVG_Thermal_Power'] = updated_rows['AVG_Thermal_Power'] # Store previous value

        # --- Update Main DataFrame ---
        # Assign the calculated values to the correct rows in the main DataFrame
        df.loc[mask, 'AVG_Thermal_Power'] = calculated_avg_power

        # --- Finalize Changelog ---
        # Add the new values and reason to the log entry
        updated_rows['new_AVG_Thermal_Power'] = df.loc[mask, 'AVG_Thermal_Power'] # Store new value
        updated_rows['change_reason'] = case_name
        self.changelog.append(updated_rows)

        print(f"[Update][{case_name}] Updated AVG_Thermal_Power for {mask.sum()} rows. Reason: {reason}")
        
        return df

    #............

    def apply_case_logic(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply all case-based cleaning logic"""
        calculator = EnergyCalculator()
        analyzer = WasteHeatAnalyzer()
        # Get power stats for cases 3, 4, 5...
        power_stats = self._get_power_statistics(df)
        # Initialize Annual_Working_Hours column to use in the cases
        df['Annual_Working_Hours'] = np.nan
        df['AVG_Thermal_Power'] = np.nan
        cols_to_show = ["Annual_Heat_Amount_kWh_per_Year",
                        "Max_Thermal_Power_kW",
                        "AVG_Thermal_Power",
                        "Avg_Daily_Availability_h",
                        "Annual_Working_Hours"
                        ]


        #------------------------------------------------------------------
        # power_stats = self._get_power_statistics(df)
        # power_stats = power_stats.set_index(df.index)
        #CASES

        # Case 1 : Delete Rows 
        #Total Energy Kwh: Yes	
        # Max Thermal Power Kw: No	
        # AVG Daily Availability: No	
        # Monthly Power: No
        # To Do: Delete

        case1_mask = (
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] <= 2) & ## because of possible rounding issues, it is set to 2 instead of 1
            (df['Avg_Daily_Availability_h'] <= 1) &
            (power_stats['monthly_all_less1'])
            )
        if case1_mask.any():
            print("Case1 results:\n", df.loc[case1_mask, ["Annual_Energy_Months", "Annual_Heat_Amount_kWh_per_Year"]])
            df = self._drop_rows(df, case1_mask, case_name='Case 1 Invalid Rows', reason="")
            print("Case1 results:\n", df.loc[case1_mask, cols_to_show])
            print("Case1 Match Check: ", sanity_check(df))

        # Case 2 : Delete Rows 
        #Total Energy Kwh: No	
        # Max Thermal Power Kw: Yes	
        # AVG Daily Availability: No	
        # Monthly Power: Yes
        # To Do: Delete
        case2_mask =(
            (df['Annual_Heat_Amount_kWh_per_Year'] <= 2) & ## because of possible rounding issues, it is set to 2 instead of 1
            (df['Max_Thermal_Power_kW'] > 1) &
            (df['Avg_Daily_Availability_h'] <= 1) &
            (power_stats['monthly_any_gt1'])
            )
        
        if case2_mask.any():
            print("Case2 results:\n", df.loc[case2_mask, cols_to_show])
            df = self._drop_rows(df, case2_mask, case_name='Case 2 Invalid Rows', reason="")
            print("Case2 results:\n", df.loc[case2_mask, cols_to_show])
            print("Case2 Match Check: ", sanity_check(df))

        # Case 3 : Delete Rows 
        #Total Energy Kwh: No	
        # Max Thermal Power Kw: No	
        # AVG Daily Availability: No	
        # Monthly Power: No
        # To Do: Delete
        case3_mask = (
            (df['Annual_Heat_Amount_kWh_per_Year'] <= 2) & ## because of possible rounding issues, it is set to 2 instead of 1
            (df['Max_Thermal_Power_kW'] <= 2) & ## because of possible rounding issues, it is set to 2 instead of 1
            (df['Avg_Daily_Availability_h'] <= 1) &             
            (power_stats['monthly_all_less1'])
            )
        if case3_mask.any():
            print("Case3 results:\n", df.loc[case3_mask, cols_to_show])
            df = self._drop_rows(df, case3_mask, case_name='Case 3 Invalid Rows', reason="")
            print("Case3 results:\n", df.loc[case3_mask, cols_to_show])
            print("Case3 Match Check: ", sanity_check(df))
    
        # Case 4 : Delete Rows 
        #Total Energy Kwh: No	
        # Max Thermal Power Kw: Yes	
        # AVG Daily Availability: No	
        # Monthly Power: No
        # To Do: Delete
        case4_mask =(
            (df['Annual_Heat_Amount_kWh_per_Year'] <= 2) & ## because of possible rounding issues, it is set to 2 instead of 1
            (df['Max_Thermal_Power_kW'] > 1) &
            (df['Avg_Daily_Availability_h'] <= 1) &             
            (power_stats['monthly_all_less1'])
            )
        if case4_mask.any():
            print("Case4 results:\n", df.loc[case4_mask, cols_to_show])
            df = self._drop_rows(df, case4_mask, case_name='Case 4 Invalid Rows', reason="")
            print("Case4 results:\n", df.loc[case4_mask, cols_to_show])
            print("Case4 Match Check: ", sanity_check(df))
        
        # Case 5 : Delete Rows 
        #Total Energy Kwh: No	
        # Max Thermal Power Kw: No	
        # AVG Daily Availability: Yes	
        # Monthly Power: No
        # To Do: Delete
        case5_mask =(
            (df['Annual_Heat_Amount_kWh_per_Year'] <= 1) &
            (df['Max_Thermal_Power_kW'] <= 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_all_less1'])
            )
        if case5_mask.any():
            print("Case5 results:\n", df.loc[case5_mask, cols_to_show])
            df = self._drop_rows(df, case5_mask, case_name='Case 5 Invalid Rows', reason="")
            print("Case5 results:\n", df.loc[case5_mask, cols_to_show])
            print("Case5 Match Check: ", sanity_check(df))
    
            

        # Case 6 : Delete Rows 
        #Total Energy Kwh: No	
        # Max Thermal Power Kw: No	
        # AVG Daily Availability: No	
        # Monthly Power: Yes
        # To Do: Delete
        case6_mask =(
            (df['Annual_Heat_Amount_kWh_per_Year'] <= 1) &
            (df['Max_Thermal_Power_kW'] <= 1) &
            (df['Avg_Daily_Availability_h'] <= 1) &             
            (power_stats['monthly_any_gt1'])
            )
        
        if case6_mask.any():
            print("Case6 results:\n", df.loc[case6_mask, cols_to_show])
            df = self._drop_rows(df, case6_mask, case_name='Case 6 Invalid Rows', reason="")
            print("Case6 results:\n", df.loc[case6_mask, cols_to_show])
            print("Case6 Match Check: ", sanity_check(df))
        df = df.reset_index(drop=True)
        power_stats = self._get_power_statistics(df).reset_index(drop=True)

        #------------------------------------------------------------------
    # Case unmatched1 : Final Correction for Plausible Unmatched Rows
        # Total Energy Kwh: Yes (but doesn't match)
        # AVG Daily Availability: Yes (>1)
        # Monthly Power: Yes (All >1)
        # To Do: Attempt to correct monthly powers by assuming they were provided in Watts instead of kW.
        
        # First, ensure the comparison column is up-to-date
        df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
    
        df, comparison_results = analyzer.compare_energy_values(df, tolerance=0.10)

        # Get the name of the match column
        match_col_name = comparison_results[0][2]

        case_unmatched_mask = (
            # Condition: Provided and calculated values do not match
            (~df[match_col_name]) &            
            # Condition: Annual heat, daily availability, and all monthly powers are plausible
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &
            (power_stats['monthly_any_gt1'])
        )
        
        if case_unmatched_mask.any():
            df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
            print("Case unmatched Match Check: ", sanity_check(df.loc[case_unmatched_mask].copy()))
            print(f"\n--- Found {case_unmatched_mask.sum()} plausible but unmatched rows for Final Correction ---")
            df = self._apply_power_correction(df, case_unmatched_mask, calculator, case_name='Case unmatched Correction: W to kW',reason="Correcting monthly power profiles assuming original data was in Watts.")
            #df.loc[case_unmatched_mask,'AVG_Thermal_Power'] = calculator.calculate_avg_thermal_power_by_monthly_powers(df[case_unmatched_mask])
            #df = self._update_max_power_from_monthly(df, case_unmatched_mask, case_name='Case unmatched Correction: W to kW', reason="Updating Max_Thermal_Power_kW from monthly power columns after correction.")
            df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
            print("Case unmatched Match Check: ", sanity_check(df.loc[case_unmatched_mask].copy()))

   # Case unmatched2 : Final Correction for Plausible Unmatched Rows
        # Total Energy Kwh: Yes (but doesn't match)
        # AVG Daily Availability: Yes (>1)
        # Monthly Power: Yes (All >1)
        # To Do: Attempt to correct monthly powers by assuming they were provided in energy instead of kW.
        
        # First, ensure the comparison column is up-to-date
        df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
    
        df, comparison_results = analyzer.compare_energy_values(df, tolerance=0.10)

        # Get the name of the match column
        match_col_name = comparison_results[0][2]

        case_unmatched2_mask = (
            # Condition: Provided and calculated values do not match
            (~df[match_col_name]) &            
            # Condition: Annual heat, daily availability, and all monthly powers are plausible
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &
            (power_stats['monthly_any_gt1'])
        )
        
        if case_unmatched2_mask.any():
            df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
            print("Case unmatched Match Check: ", sanity_check(df.loc[case_unmatched2_mask].copy()))
            print(f"\n--- Found {case_unmatched2_mask.sum()} plausible but unmatched rows for Final Correction ---")
            df = self._apply_power_correction_strategy2(df, case_unmatched2_mask, calculator, case_name='Case unmatched Correction: energy to kW',reason="Correcting monthly power profiles assuming original data was in energy.")
            #df.loc[case_unmatched2_mask,'AVG_Thermal_Power'] = calculator.calculate_avg_thermal_power_by_monthly_powers(df[case_unmatched2_mask])
            #df = self._update_max_power_from_monthly(df, case_unmatched2_mask, case_name='Case unmatched Correction: energy to kW', reason="Updating Max_Thermal_Power_kW from monthly power columns after correction.")
            df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
            print("Case unmatched Match Check: ", sanity_check(df.loc[case_unmatched2_mask].copy()))
            print("Case unmatched Match Check: ", sanity_check(df))

  # Case unmatched3 : Final Correction for Plausible Unmatched Rows
        # Total Energy Kwh: Yes (but doesn't match)
        # AVG Daily Availability: Yes (>1)
        # Monthly Power: Yes (All >1)
        # To Do: Attempt to correct monthly powers by assuming they were provided in energy instead of kW.
        
        # First, ensure the comparison column is up-to-date
        df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
    
        df, comparison_results = analyzer.compare_energy_values(df, tolerance=0.10)

        # Get the name of the match column
        match_col_name = comparison_results[0][2]

        case_unmatched3_mask = (
            # Condition: Provided and calculated values do not match
            (~df[match_col_name]) &            
            # Condition: Annual heat, daily availability, and all monthly powers are plausible
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &
            (power_stats['monthly_any_gt1'])
        )
        
        if case_unmatched3_mask.any():
            df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
            print("Case unmatched Match Check: ", sanity_check(df.loc[case_unmatched3_mask].copy()))
            print(f"\n--- Found {case_unmatched3_mask.sum()} plausible but unmatched rows for Final Correction ---")
            df = self._apply_power_correction_strategy3(df, case_unmatched3_mask, calculator, case_name='Case unmatched Correction: energy in watt to kW',reason="Correcting monthly power profiles assuming original data was in energy in watt.")
            #df.loc[case_unmatched3_mask,'AVG_Thermal_Power'] = calculator.calculate_avg_thermal_power_by_monthly_powers(df[case_unmatched3_mask])
            #df = self._update_max_power_from_monthly(df, case_unmatched3_mask, case_name='Case unmatched Correction: energy in watt to kW', reason="Updating Max_Thermal_Power_kW from monthly power columns after correction.")
            df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
            print("Case unmatched Match Check: ", sanity_check(df.loc[case_unmatched3_mask].copy()))
            print("Case unmatched Match Check: ", sanity_check(df))
        #------------------------------------------------------------------
            

        # Case 7 : Update Rows 
        # Total Energy Kwh: No	
        # Max Thermal Power Kw: No	
        # AVG Daily Availability: Yes	
        # Monthly Power: Yes
        # To Do: Calculate avg thermal power with monthly power values/12. Update the max thermal power as max value of monthly power values
        # calculate total energy by avg thermal power or monthly power values.
        case7_mask =(
            (df['Annual_Heat_Amount_kWh_per_Year'] <= 1) &
            (df['Max_Thermal_Power_kW'] <= 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_any_gt1'])
            )
        if case7_mask.any():
            print("Case7 results:\n", df.loc[case7_mask, cols_to_show])
            df.loc[case7_mask, "AVG_Thermal_Power"] = calculator.calculate_avg_thermal_power_by_monthly_powers(df[case7_mask])
            df = self._update_max_power_from_monthly(df, case7_mask, case_name='Case 7 Update Rows', reason="Max_Thermal_Power_kW is invalid, updated from monthly max") #may check it with max of monthly powers
            df = self._update_working_hours_from_availability(df, case7_mask, calculator, case_name='Case 7 Update Rows', reason="") #may check it with annual hours calculated by avg thermal power
            df = self._update_annual_heat_from_avg_power(df, case7_mask, case_name='Case 7 Update Rows', reason="" ) #may check it with annual energy calculated by monthly powers
            print("Case7 results:\n", df.loc[case7_mask, cols_to_show])
            df.loc[case7_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case7_mask])
            print("Case7 Match Check: ", sanity_check(df))
            case7_mask.to_excel("data/case7_mask.xlsx", index=False)
        # Case 8 : Update rows 
        # Total Energy Kwh: No	
        # Max Thermal Power Kw: Yes	
        # AVG Daily Availability: Yes	
        # Monthly Power: Yes
        # To Do: Calculate AVG Thermal Power(monthly powers/12) Update total energy based on the AVG thermal power. check with total energy calculated by monthly powers
        # check also if the maxMonth==Max thermal power
        case8_mask =(
            (df['Annual_Heat_Amount_kWh_per_Year'] <= 1) &
            (df['Max_Thermal_Power_kW'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_any_gt1'])
            )
        if case8_mask.any():
            print("Case8 results:\n", df.loc[case8_mask, cols_to_show])
            # Calculates ONLY for the subset and assigns back to that same subset
            df.loc[case8_mask, "AVG_Thermal_Power"] = calculator.calculate_avg_thermal_power_by_monthly_powers(df[case8_mask])
            df = self._update_working_hours_from_availability(df, case8_mask, calculator, case_name='Case 8 Update Rows', reason="Annual_Working_Hours is missing, updated by availability hours") #may check it with annual hours calculated by avg thermal power
            df = self._update_annual_heat_from_avg_power(df, case8_mask, case_name='Case 8 Update Rows', reason="Annual_Heat_Amount_kWh_per_Year is invalid, updated by AVG power * annual working hours") #may check it with annual energy calculated by monthly powers
            print("Case8 results:\n", df.loc[case8_mask, cols_to_show])
            print("Case8 results:\n", df.loc[case8_mask, ['Annual_Heat_Amount_kWh_per_Year', 'Annual_Energy_Months']])
            df.loc[case8_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case8_mask])
            print("Case8 Match Check: ", sanity_check(df))
            case8_mask.to_excel("data/case8_mask.xlsx", index=False)
        # Case 9 : Update rows
        # Total Energy Kwh: No	
        # Max Thermal Power Kw: Yes	
        # AVG Daily Availability: Yes	
        # Monthly Power: No
        # To Do: Update all the monthly power and avg thermal power as max thermal power. update total energy calculated by avg thermal or montly values.
        case9_mask =(
            (df['Annual_Heat_Amount_kWh_per_Year'] <= 1) &
            (df['Max_Thermal_Power_kW'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_all_less1'])
            )
        if case9_mask.any():
            print("Case9 results:\n", df.loc[case9_mask, cols_to_show])
            df = self._update_monthly_power_with_max_power(df, case9_mask, case_name='Case 9 Update Rows', reason="Monthly power values are invalid, updated from Max_Thermal_Power_kW") # check with "total energy calculated by avg thermal"
            df.loc[case9_mask, "AVG_Thermal_Power"] = df.loc[case9_mask, "Max_Thermal_Power_kW"]
            df = self._update_working_hours_from_availability(df, case9_mask, case_name='Case 9 Update Rows', reason="Annual hours are missing, updated from working days * daily availability") # check with "total energy calculated by avg thermal"
            df = self._update_annual_heat_from_avg_power(df, case9_mask, case_name='Case 9 Update Rows', reason="") # check with "total energy calculated by avg thermal"
            # I used annual_energy_by_Months because was not sure of AVG thermal because we updated it from max thermal. I should check the comparison between them
            df.loc[case9_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case9_mask])
            print("Case9 results:\n", df.loc[case9_mask, cols_to_show])
            print("Case9 results:\n", df.loc[case9_mask, ['Annual_Heat_Amount_kWh_per_Year', 'Annual_Energy_Months']])
            print("Case9 Match Check: ", sanity_check(df))
            case9_mask.to_excel("data/case9_mask.xlsx", index=False)

        # Case 10 : Update rows
        # Total Energy Kwh: Yes	
        # Max Thermal Power Kw: Yes	
        # AVG Daily Availability: Yes	
        # Monthly Power: Yes
        # To Do: Calculate the avg thermal power by total energy / hours per year
        # check if avg thermal power == avg of monthly power values
        case10_mask =(
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_any_gt1'])
            )
        if case10_mask.any():
            print("Case10 results:\n", df.loc[case10_mask, cols_to_show].head(25))
            df = self._update_working_hours_from_availability(df, case10_mask, calculator, case_name='Case 10 Check-Update', reason="")
            df.loc[case10_mask, "AVG_Thermal_Power"] = calculator.calculate_max_avg_thermal_power_from_energy(df[case10_mask]).round(2)
            df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
            print("Case10 results:\n", df.loc[case10_mask, cols_to_show].head(25))
            print("Case10 Match Check: ", sanity_check(df))
            case10_mask.to_excel("data/case10_mask.xlsx", index=False)


        # Case 11 : Update rows
        # Total Energy Kwh: Yes	
        # Max Thermal Power Kw: Yes	
        # AVG Daily Availability: No	
        # Monthly Power: Yes
        # To Do: calculate avg thermal power. update Avg daily availability: total energy/avg thermal power >yearly max hours?
        # if yes, we will calculate avg thermal power with a different way. before that lets see how many cases we have
        case11_mask =(
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] > 1) &
            (df['Avg_Daily_Availability_h'] <= 1) &             
            (power_stats['monthly_any_gt1'])
            )
        if case11_mask.any():
            print("Case11 results:\n", df.loc[case11_mask, cols_to_show])
            df = self._update_avg_thermal_power_from_monthly(df, case11_mask, calculator, case_name='Case 11 Update Rows', reason="AVG_Thermal_Power is invalid, updated by monthly power values") # check with "total energy calculated by avg thermal"
            df = self._update_annual_hours_with_avg_power(df, case11_mask, calculator, case_name='Case 11 Update Rows', reason="Annual_Working_Hours is missing, updated by Annual_Heat_Energy / AVG_Thermal_Power") # check with "total energy calculated by avg thermal"
            df = self._update_avg_daily_availability(df, case11_mask, calculator, case_name='Case 11 Update Rows', reason="AVG daily availability is invalid, updated by (Annual Heat Energy / AVG Thermal Power) / Annual Working Day") # check with "total energy calculated by avg thermal"
            df.loc[case11_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case11_mask])
            print("Case11 results:\n", df.loc[case11_mask, cols_to_show])
            print("Case11 Match Check: ", sanity_check(df))
            #  Call your check function for working hour limits
            # --- START: New Physical Limit Check ---
            print("\n--- Checking for 24-hour physical limit violations... ---")

            case11_mask.to_excel("data/case11.xlsx", index=False)

            # 1. Get a copy of the updated Case 11 data
            df_case11_check = df.loc[case11_mask].copy()

            # 2. Find rows where the new Avg_Daily_Availability_h exceeds 24
            violations_mask = df_case11_check['Avg_Daily_Availability_h'] > 24
            
            # 3. Print the results
            if violations_mask.any():
                violations_df = df_case11_check[violations_mask]
                print(f"WARNING: Found {len(violations_df)} rows where calculated 'Avg_Daily_Availability_h' exceeds 24 hours.")
                print(violations_df[['Annual_Heat_Amount_kWh_per_Year', 'AVG_Thermal_Power', 'Annual_Working_Hours', 'Avg_Daily_Availability_h']])
            else:
                print("OK: All calculated 'Avg_Daily_Availability_h' values are within the 24-hour physical limit.")
            # --- END: New Check ---
            # --- Corrected Case-Dependent for max thermal == avg thermal Check ---
            # Get the subset of data for only this case
            avg_power_subset = df.loc[case11_mask, 'AVG_Thermal_Power']
            max_power_subset = df.loc[case11_mask, 'Max_Thermal_Power_kW']

            # Perform the check only on that subset
            count_within_tolerance = np.isclose(avg_power_subset, max_power_subset, rtol=0.03).sum()
            
            print(f"Case 11 - Max Power = AVG Power: {count_within_tolerance} (out of {case11_mask.sum()} total case rows)")
            # --- End Check ---
            df_11 = df.loc[case11_mask]
            df_11.to_excel("data/df_11.xlsx", index=False)

        # Case 12 : Update rows
        # Total Energy Kwh: Yes	
        # Max Thermal Power Kw: No	
        # AVG Daily Availability: Yes	
        # Monthly Power: Yes
        # To Do: Calculate AVG thermal power. Total energy/hours per year. Is this the same result with monthly power values/12 If yes, great
        # If no, we will pursued a different case
        case12_mask =(
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] <= 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_any_gt1'])
            )
        if case12_mask.any():
            print("Case12 results:\n", df.loc[case12_mask, cols_to_show])
            df = self._update_working_hours_from_availability(df, case12_mask, calculator, case_name='Case 12 Update Rows', reason="")
            df.loc[case12_mask, "AVG_Thermal_Power"] = calculator.calculate_max_avg_thermal_power_from_energy(df[case12_mask])
            print("Case12 results:\n", df.loc[case12_mask, cols_to_show])
            df.loc[case12_mask, "AVG_Thermal_Power"]= calculator.calculate_avg_thermal_power_by_monthly_powers(df[case12_mask])
            df.loc[case12_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case12_mask])
            print("Case12 results:\n", df.loc[case12_mask, cols_to_show])
            print("Case12 Match Check: ", sanity_check(df))
            case12_mask.to_excel("data/case12_mask.xlsx", index=False)


        # Case 13 : Update rows
        # Total Energy Kwh: Yes	
        # Max Thermal Power Kw: Yes	
        # AVG Daily Availability: Yes	
        # Monthly Power: No
        # To Do: Calculate avg thermal power with Total energy/hours per year. Update all monthly power values with avg thermal power.
        # for how many cases max thermal power==avg thermal power
        case13_mask =(
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_all_less1'])
            )
        if case13_mask.any():
            print("Case13 results:\n", df.loc[case13_mask, cols_to_show])
            # --- ADD THIS VERIFICATION STEP ---
            # Check how many of the 217 rows were already matched
            pre_update_matches = df.loc[case13_mask, 'Match_Annual_Energy_Months'].sum()
            print(f"VERIFICATION: {pre_update_matches} of these {case13_mask.sum()} rows were already 'Matched'.")
            # --- END VERIFICATION ---
            df = self._update_working_hours_from_availability(df, case13_mask, calculator, case_name='Case 13 Update Rows', reason="Annual_Working_Hours is missing, updated by working days * daily availability") # max and avg power are the same so i can use that function
            df.loc[case13_mask, "AVG_Thermal_Power"] = calculator.calculate_max_avg_thermal_power_from_energy(df[case13_mask])
            df = self._update_monthly_power_with_avg_thermal_power(df, case13_mask, case_name='Case 13 Update Rows', reason="Monthly power values are invalid, updated by AVG_Thermal_Power") # check with "total energy calculated by avg thermal"
            print("Case13 results:\n", df.loc[case13_mask, cols_to_show])
            df.loc[case13_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case13_mask])
            
            case13_mask.to_excel("data/case13_mask.xlsx", index=False)

            # 1. Get a clean copy of the updated Case 11 data
            #    We use .copy() to avoid a SettingWithCopyWarning
            df_case13_check = df.loc[case13_mask].copy()

            # 2. Prepare the 'Weekend_Availability' column as required by your function
            #    (Converts "Ja"/"Nein" strings to True/False)
            df_case13_check['Weekend_Availability'] = df_case13_check['Weekend_Availability'].str.lower() == 'ja'
            
            # 3. Call your check function
            violations_df = check_working_hours_limits(df_case13_check, tolerance=0.01)

            # 4. Print the results to the console
            if not violations_df.empty:
                print(f"WARNING: Found {len(violations_df)} rows where 'Annual_Working_Hours' exceeds the max possible.")
                # Print the key columns from the violations
                print(violations_df[['Annual_Working_Hours', 'Max_Possible_Working_Hours', 'Avg_Daily_Availability_h', 'Days_Per_Year']])
            else:
                print("OK: No working hour violations found for this case.")
            # --- END: New Code ---
                        # --- END: New Check ---
            # --- Corrected Case-Dependent for max thermal == avg thermal Check ---
            # Get the subset of data for only this case
            avg_power_subset = df.loc[case13_mask, 'AVG_Thermal_Power']
            max_power_subset = df.loc[case13_mask, 'Max_Thermal_Power_kW']

            # Perform the check only on that subset
            count_within_tolerance = np.isclose(avg_power_subset, max_power_subset, rtol=0.03).sum()
            
            print(f"Case 13 - Max Power = AVG Power: {count_within_tolerance} (out of {case13_mask.sum()} total case rows)")
            # --- End Check ---
            print("Case13 Match Check: ", sanity_check(df))
            df_13 = df.loc[case13_mask]
            df_13.to_excel("data/df_13.xlsx", index=False)

        # Case 14 : Update rows
        # Total Energy Kwh: Yes	
        # Max Thermal Power Kw: Yes	
        # AVG Daily Availability: No	
        # Monthly Power: No
        # To Do: Update monthly power with max thermal power and Avg thermal power also. Calculate hours per year total energy/avg thermal power.
        # after calculating total hours per year then divide it per day to update avg daily availability then update avg daily availability
        # avg daily availability should be int not float. We can check it later. 
        # Again time > yearly hours ? then we will decide it.
        case14_mask =(
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] > 1) &
            (df['Avg_Daily_Availability_h'] <= 1) &             
            (power_stats['monthly_all_less1'])
            )
        if case14_mask.any():
            print("Case14 results:\n", df.loc[case14_mask, cols_to_show])
                        # --- ADD THIS VERIFICATION STEP ---
            # Check how many of the 19 rows were already matched
            pre_update_matches = df.loc[case14_mask, 'Match_Annual_Energy_Months'].sum()
            print(f"VERIFICATION: {pre_update_matches} of these {case14_mask.sum()} rows were already 'Matched'.")
            # --- END VERIFICATION ---
            df.loc[case14_mask, "AVG_Thermal_Power"] = df.loc[case14_mask, "Max_Thermal_Power_kW"]
            df = self._update_monthly_power_with_max_power(df, case14_mask, case_name='Case 14 Update Rows', reason="Monthly power values are invalid, updated by Max_Thermal_Power_kW") # max and avg power are the same so i can use that function
            df = self._update_annual_hours_with_calculated(df, case14_mask, calculator, case_name='Case 14 Update Rows', reason="Annual working hours is missing, updated by Annual_Heat_Amount_per_Year_KWh / Max_Thermal_Power_kW ") # max and avg power are the same so i can use that function
            df = self._update_avg_daily_availability(df, case14_mask, calculator, case_name='Case 14 Update Rows', reason="AVG daily availability is invalid, updated by (Annual Heat Energy / AVG Thermal Power) / Annual Working Day") # check with "total energy calculated by avg thermal"
            df.loc[case14_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case14_mask])
            print("Case14 results:\n", df.loc[case14_mask, cols_to_show])
            
            case14_mask.to_excel("data/case14_mask.xlsx", index=False)

            # 1. Get a clean copy of the updated Case 11 data
            #    We use .copy() to avoid a SettingWithCopyWarning
            df_case14_check = df.loc[case14_mask].copy()

            # 2. Prepare the 'Weekend_Availability' column as required by your function
            #    (Converts "Ja"/"Nein" strings to True/False)
            df_case14_check['Weekend_Availability'] = df_case14_check['Weekend_Availability'].str.lower() == 'ja'
            
            # 3. Call your check function
            violations_df = check_working_hours_limits(df_case14_check, tolerance=0.01)

            # 4. Print the results to the console
            if not violations_df.empty:
                print(f"WARNING: Found {len(violations_df)} rows where 'Annual_Working_Hours' exceeds the max possible.")
                # Print the key columns from the violations
                print(violations_df[['Annual_Working_Hours', 'Max_Possible_Working_Hours', 'Avg_Daily_Availability_h', 'Days_Per_Year']])
            else:
                print("OK: No working hour violations found for this case.")
            # --- END: New Code ---
                        # --- END: New Check ---
            # --- Corrected Case-Dependent for max thermal == avg thermal Check ---
            # Get the subset of data for only this case
            avg_power_subset = df.loc[case14_mask, 'AVG_Thermal_Power']
            max_power_subset = df.loc[case14_mask, 'Max_Thermal_Power_kW']

            # Perform the check only on that subset
            count_within_tolerance = np.isclose(avg_power_subset, max_power_subset, rtol=0.03).sum()
            
            print(f"Case 14 - Max Power = AVG Power: {count_within_tolerance} (out of {case14_mask.sum()} total case rows)")
            # --- End Check ---
            print("Case14 Match Check: ", sanity_check(df))
            df_14 = df.loc[case14_mask]
            df_14.to_excel("df_14.xlsx", index=False)
            print("Case14 Match Check: ", sanity_check(df))
        
        # Case 15 : Update rows
        # Total Energy Kwh: Yes	
        # Max Thermal Power Kw: No	
        # AVG Daily Availability: Yes	
        # Monthly Power: No
        # To Do: Calculate avg thermal power by total energy/hours per year. Update max thermal power and monthly values as avg thermal power
        case15_mask =(
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] <= 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_all_less1'])
            )
        if case15_mask.any():
            print("Case15 results:\n", df.loc[case15_mask, cols_to_show])
            df = self._update_working_hours_from_availability(df, case15_mask, calculator, case_name='Case 15 Update Rows', reason="Annual_Working_Hours is missing, updated by working days * daily availability") # max and avg power are the same so i can use that function
            df.loc[case15_mask, "AVG_Thermal_Power"] = calculator.calculate_max_avg_thermal_power_from_energy(df[case15_mask])
            df.loc[case15_mask, "Max_Thermal_Power_kW"] = df.loc[case15_mask, "AVG_Thermal_Power"]
            df = self._update_monthly_power_with_avg_thermal_power(df, case15_mask, case_name='Case 15 Update Rows', reason="Monthly power values are invalid, updated by AVG_Thermal_Power") # check with "total energy calculated by avg thermal"
            df.loc[case15_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case15_mask])
            print("Case15 results:\n", df.loc[case15_mask, cols_to_show])
            print("Case15 Match Check: ", sanity_check(df))
            case15_mask.to_excel("data/case15_mask.xlsx", index=False)

        # Case 16 : Update rows
        # Total Energy Kwh: Yes	
        # Max Thermal Power Kw: No	
        # AVG Daily Availability: No	
        # Monthly Power: Yes
        # To Do: Calculate avg thermal power with monthly power/12. yearly hours is total energy/avg thermal power and then find and update the avg daily availablity. check data type of avg daily availability
        case16_mask =(
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] <= 1) &
            (df['Avg_Daily_Availability_h'] <= 1) &             
            (power_stats['monthly_any_gt1'])
            )
        if case16_mask.any():
            print("Case16 results:\n", df.loc[case16_mask, cols_to_show])
            df.loc[case16_mask, "AVG_Thermal_Power"] = calculator.calculate_avg_thermal_power_by_monthly_powers(df[case16_mask])
            df = self._update_annual_hours_with_avg_power(df, case16_mask, calculator, case_name='Case 16 Update Rows', reason="Annual_Working_Hours is missing, updated by Annual_Heat_Amount_per_Year_KWh / AVG_Thermal_Power") # check with "total energy calculated by avg thermal"
            df = self._update_avg_daily_availability(df, case16_mask, calculator, case_name='Case 16 Update Rows', reason="AVG daily availability is invalid, updated by (Annual Heat Energy / AVG Thermal Power) / Annual Working Day") # check with "total energy calculated by avg thermal"
            df.loc[case16_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case16_mask])
            print("Case16 results:\n", df.loc[case16_mask, cols_to_show])
            print("Case16 Match Check: ", sanity_check(df))
            case16_mask.to_excel("data/case16_mask.xlsx", index=False)
            
    #------------------------------------------------------------------


  # Case unmatched4: Final Correction for Plausible Unmatched Rows
        # Total Energy Kwh: Yes (but doesn't match)
        # AVG Daily Availability: Yes (>1)
        # Monthly Power: Yes (All >1)
        # To Do: Attempt to correct monthly powers by scaling factor of the energy.
        
        # First, ensure the comparison column is up-to-date
        df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
    
        df, comparison_results = analyzer.compare_energy_values(df, tolerance=0.10)

        # Get the name of the match column
        match_col_name = comparison_results[0][2]

        case_unmatched4_mask = (
            # Condition: Provided and calculated values do not match
            (~df[match_col_name]) &            
            # Condition: Annual heat, daily availability, and all monthly powers are plausible
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &
            (power_stats['monthly_any_gt1'])
        )
        
        if case_unmatched4_mask.any():
            df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
            print("Case unmatched Match Check: ", sanity_check(df.loc[case_unmatched4_mask].copy()))
            print(f"\n--- Found {case_unmatched4_mask.sum()} plausible but unmatched rows for Final Correction ---")
            df = self._apply_power_correction_strategy4(df, case_unmatched4_mask, calculator, case_name='Case unmatched Correction: scaling factor of energy',reason="Correcting monthly power profiles by scaling factor of the energies.")
            #df.loc[case_unmatched4_mask,'AVG_Thermal_Power'] = calculator.calculate_avg_thermal_power_by_monthly_powers(df[case_unmatched4_mask])
            #df = self._update_max_power_from_monthly(df, case_unmatched4_mask, case_name='Case unmatched Correction: scaling factor of energy', reason="Updating Max_Thermal_Power_kW from monthly power columns after correction.")
            df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
            print("Case unmatched Match Check: ", sanity_check(df.loc[case_unmatched4_mask].copy()))
            print("Case unmatched Match Check: ", sanity_check(df))
    #------------------------------------------------------------------


        if self.changelog:
            change_df = pd.concat(self.changelog, ignore_index=False)
        else:
            change_df = pd.DataFrame()

        return df, change_df, self.warnings

