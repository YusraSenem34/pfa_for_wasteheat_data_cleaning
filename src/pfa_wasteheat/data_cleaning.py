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
from utils import sanity_check, check_working_hours_limits, get_violations_report

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
            df['Additional_Info_on_Waste_Heat_Potential'] = clean_col.str.strip()

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
    
    def _update_working_hours_from_availability(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator) -> pd.DataFrame:
        """
        Calculate Annual_Working_Hours based on monthly working days
        and Avg_Daily_Availability_h.
        """
        if mask.sum() == 0: return df # No rows to update
        df.loc[mask, 'Annual_Working_Hours'] = calculator.calculate_annual_working_hours_from_availability(df[mask])
        return df
    
    def _update_annual_heat_with_calc_energy(self, df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
        if mask.sum() == 0: return df # No rows to update
        # Update annual heat amount with calculated annual energy
        df.loc[mask, 'Annual_Heat_Amount_kWh_per_Year'] = EnergyCalculator().calculate_annual_energy(df.loc[mask])
        return df

    def _update_annual_heat_with_calc_from_power(self, df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
        if mask.sum() == 0: return df        
        # Update annual heat amount with calculated annual energy from thermal power
        df.loc[mask, 'Annual_Heat_Amount_kWh_per_Year'] = EnergyCalculator().calculate_annual_energy_from_thermal_power(df.loc[mask])
        return df
   
    def _update_annual_heat_from_avg_power(self, df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
        """
        Calculate annual energy using avg thermal power
        Formula: AVG_Thermal_Power × Annual_Working_Hours
        """
        if mask.sum() == 0: return df # No rows to update      
        # Update annual heat amount with calculated annual energy from thermal power
        df.loc[mask, 'Annual_Heat_Amount_kWh_per_Year'] = EnergyCalculator().calculate_annual_energy_from_avg_thermal_power(df.loc[mask])
        return df
    
    def _update_max_power_from_monthly(self, df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
        """Update Max_Thermal_Power_kW with max of monthly power columns"""
        if mask.sum() == 0: return df # No rows to update
        df.loc[mask, 'Max_Thermal_Power_kW'] = df.loc[mask, EnergyCalculator.power_cols].max(axis=1)
        return df
    
    def _update_monthly_power_with_max_power(self, df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
        """Only update monthly power columns with Max_Thermal_Power_kW """
        if mask.sum() == 0: return df # No rows to update
        for col in EnergyCalculator.power_cols:
            df.loc[mask, col] = df.loc[mask, 'Max_Thermal_Power_kW']
        return df
    
    def _update_annual_hours_with_calculated(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator) -> pd.DataFrame:
        """
        Calculate annual working hours using:
        Annual_Working_Hours = Annual_Heat_Amount_per_Year_KWh / Max_Thermal_Power_kW
        """
        if mask.sum() == 0: return df # No rows to update
        calculated_hours = calculator.calculate_annual_hours_from_energy_and_power(df[mask])
        df.loc[mask, 'Annual_Working_Hours'] = calculated_hours
        return df
    
    def _update_avg_daily_availability(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator) -> pd.DataFrame:
        """
        Calculate average daily availability (hours).
        Formula: Annual_Working_Hours / Annual Working Days
        """
        if mask.sum() == 0: return df # No rows to update

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
        return df


    def _update_monthly_power_with_avg_thermal_power(self, df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
        """Only update monthly power columns with AVG_Thermal_Power """
        if mask.sum() == 0: return df # No rows to update

        for col in EnergyCalculator.power_cols:
            df.loc[mask, col] = df.loc[mask, 'AVG_Thermal_Power']
        return df
    
    def _update_annual_hours_with_avg_power(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator) -> pd.DataFrame:
        """
        Calculate annual working hours using:
        Annual_Working_Hours = Annual_Heat_Amount_per_Year_KWh / AVG_Thermal_Power
        """
        if mask.sum() == 0: return df # No rows to update
        calculated_hours = calculator.calculate_annual_hours_from_energy_and_avg_power(df[mask])
        df.loc[mask, 'Annual_Working_Hours'] = calculated_hours  
        return df
    
    def _update_avg_thermal_power_from_monthly(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator) -> pd.DataFrame:
        """
        Calculate and update the AVG_Thermal_Power column based on monthly power profiles.
        Formula: (Sum of monthly power values) / 12
        """
        if not mask.any(): return df # No rows to update
        # --- Calculation ---
        # Calculate the average power only for the specified subset
        calculated_avg_power = calculator.calculate_avg_thermal_power_by_monthly_powers(df[mask])
        # --- Update Main DataFrame ---
        # Assign the calculated values to the correct rows in the main DataFrame
        df.loc[mask, 'AVG_Thermal_Power'] = calculated_avg_power
        return df
    
    def _apply_power_correction(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator) -> Tuple[pd.DataFrame, pd.Series]:
        updated_mask = pd.Series(False, index=df.index)
        if not mask.any(): return df, updated_mask
        unmatched_df = df[mask].copy()
        corrected_subset = calculator.correct_powers_watts_to_kw(unmatched_df)
        if corrected_subset.empty: return df, updated_mask
        
        matched_indices = corrected_subset.index
        df.loc[matched_indices, EnergyCalculator.power_cols] = corrected_subset[EnergyCalculator.power_cols]
        df.loc[matched_indices, 'Logic_of_Energy_Correction'] = corrected_subset['Logic_of_Energy_Correction']
        updated_mask.loc[matched_indices] = True
        return df, updated_mask
    
    def _apply_power_correction_strategy2(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator) -> Tuple[pd.DataFrame, pd.Series]:
        updated_mask = pd.Series(False, index=df.index)
        if not mask.any(): return df, updated_mask
        unmatched_df = df[mask].copy()
        corrected_subset = calculator.correct_powers_energy_to_power(unmatched_df)
        if corrected_subset.empty: return df, updated_mask
        
        matched_indices = corrected_subset.index
        df.loc[matched_indices, EnergyCalculator.power_cols] = corrected_subset[EnergyCalculator.power_cols]
        df.loc[matched_indices, 'Logic_of_Energy_Correction'] = corrected_subset['Logic_of_Energy_Correction']
        updated_mask.loc[matched_indices] = True
        return df, updated_mask
    
    def _apply_power_correction_strategy3(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator) -> Tuple[pd.DataFrame, pd.Series]:
        updated_mask = pd.Series(False, index=df.index)
        if not mask.any(): return df, updated_mask
        unmatched_df = df[mask].copy()
        corrected_subset = calculator.correct_powers_wh_to_kw(unmatched_df)
        if corrected_subset.empty: return df, updated_mask
        
        matched_indices = corrected_subset.index
        df.loc[matched_indices, EnergyCalculator.power_cols] = corrected_subset[EnergyCalculator.power_cols]
        df.loc[matched_indices, 'Logic_of_Energy_Correction'] = corrected_subset['Logic_of_Energy_Correction']
        updated_mask.loc[matched_indices] = True
        return df, updated_mask
    
    def _apply_power_correction_strategy4(self, df: pd.DataFrame, mask: pd.Series, calculator: EnergyCalculator) -> Tuple[pd.DataFrame, pd.Series]:
        updated_mask = pd.Series(False, index=df.index)
        if not mask.any(): return df, updated_mask
        unmatched_df = df[mask].copy()
        corrected_subset = calculator.correct_powers_by_scaling_factor(unmatched_df)
        if corrected_subset.empty: return df, updated_mask
        
        matched_indices = corrected_subset.index
        df.loc[matched_indices, EnergyCalculator.power_cols] = corrected_subset[EnergyCalculator.power_cols]
        df.loc[matched_indices, 'Logic_of_Energy_Correction'] = corrected_subset['Logic_of_Energy_Correction']
        updated_mask.loc[matched_indices] = True
        return df, updated_mask
    
    def _drop_rows(self, df: pd.DataFrame, mask: pd.Series, case_name: str, reason: str = "") -> pd.DataFrame:
        """Drop rows based on mask and optionally log reason"""
        if mask.sum() == 0: return df # No rows to drop
        dropped = df[mask].copy() 
        if not dropped.empty:
            dropped['change_reason'] = case_name
            self.changelog.append(dropped) #for changelog
            print(f"[Drop] {len(dropped)} rows dropped. Reason: {reason}")
        return df[~mask].copy()
    
    def _log_updated_rows(self, df: pd.DataFrame, mask: pd.Series, rows_before: pd.DataFrame, case_name: str):
        """Saves a snapshot of the rows, automatically generating prev/new columns for changes."""
        if mask.sum() == 0:
            return 
            
        updated_rows = df[mask].copy()
        updated_rows['change_reason'] = case_name
        
        # Columns we want to track for prev/new changes
        cols_to_track = [
            'Annual_Heat_Amount_kWh_per_Year', 'Max_Thermal_Power_kW', 'AVG_Thermal_Power', 
            'Avg_Daily_Availability_h', 'Annual_Working_Hours', 'Annual_Energy_Months'
        ] + EnergyCalculator.power_cols

        # Automatically detect changes and append prev_ / new_
        for col in cols_to_track:
            if col in updated_rows.columns and col in rows_before.columns:
                # Compare the before and after series (handling NaNs safely)
                changed = updated_rows[col].fillna(-9999) != rows_before[col].fillna(-9999)
                if changed.any():
                    updated_rows[f'prev_{col}'] = rows_before[col]
                    updated_rows[f'new_{col}'] = updated_rows[col]
                    
        self.changelog.append(updated_rows)
        
    #............CASE LOGIC - MAIN BLOCK................#

    def apply_case_logic(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply all case-based cleaning logic"""
        calculator = EnergyCalculator()
        analyzer = WasteHeatAnalyzer()
        # Get power stats for cases 3, 4, 5...
        power_stats = self._get_power_statistics(df)
        # Initialize Annual_Working_Hours column to use in the cases
        df['Annual_Working_Hours'] = np.nan
        df['AVG_Thermal_Power'] = np.nan
        df['Update_History'] = "" # New column to track which cases have been applied to each row
        df['case_resolved'] = False # New column to track if a row has been resolved by any case
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
            print("Case6 Match Check: ", sanity_check(df))
        
        power_stats = self._get_power_statistics(df)

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
            (~df[match_col_name]) &            
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &
            (power_stats['monthly_any_gt1'])
        )
        if case_unmatched_mask.any():
            df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
            print(f"\n--- Found {case_unmatched_mask.sum()} plausible but unmatched rows for Final Correction ---")
            
            # ---> TAKE SNAPSHOT BEFORE CHANGES <---
            rows_before = df.copy() 
            
            df, updated_mask = self._apply_power_correction(df, case_unmatched_mask, calculator)
            if updated_mask.any():
                df.loc[updated_mask, 'Update_History'] += "Case Unmatched 1: Corrected W to kW | "
                df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
                
                # ---> PASS ALIGNED SNAPSHOT TO LOGGER <---
                self._log_updated_rows(df, updated_mask, rows_before.loc[updated_mask], 'Case unmatched Correction: W to kW')
        
        power_stats = self._get_power_statistics(df)

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
            (~df[match_col_name]) &            
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &
            (power_stats['monthly_any_gt1'])
        )
        if case_unmatched2_mask.any():
            df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
            print(f"\n--- Found {case_unmatched2_mask.sum()} plausible but unmatched rows for Final Correction ---")
            
            rows_before = df.copy()
            df, updated_mask = self._apply_power_correction_strategy2(df, case_unmatched2_mask, calculator)
            
            if updated_mask.any():
                df.loc[updated_mask, 'Update_History'] += "Case Unmatched 2: Corrected Energy to kW | "
                df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
                self._log_updated_rows(df, updated_mask, rows_before.loc[updated_mask], 'Case unmatched Correction: energy to kW')

        power_stats = self._get_power_statistics(df)

  # Case unmatched3 : Final Correction for Plausible Unmatched Rows
        # Total Energy Kwh: Yes (but doesn't match) energy in watt to kWh
        # AVG Daily Availability: Yes (>1)
        # Monthly Power: Yes (All >1)
        # To Do: Attempt to correct monthly powers by assuming they were provided energy in watt instead of kW.
        
        # First, ensure the comparison column is up-to-date
        df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
    
        df, comparison_results = analyzer.compare_energy_values(df, tolerance=0.10)

        # Get the name of the match column
        match_col_name = comparison_results[0][2]

        case_unmatched3_mask = (
            (~df[match_col_name]) &            
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &
            (power_stats['monthly_any_gt1'])
        )
        if case_unmatched3_mask.any():
            df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
            print(f"\n--- Found {case_unmatched3_mask.sum()} plausible but unmatched rows for Final Correction ---")
            
            rows_before = df.copy()
            df, updated_mask = self._apply_power_correction_strategy3(df, case_unmatched3_mask, calculator)
            
            if updated_mask.any():
                df.loc[updated_mask, 'Update_History'] += "Case Unmatched 3: Corrected Energy (W) to kW | "
                df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
                self._log_updated_rows(df, updated_mask, rows_before.loc[updated_mask], 'Case unmatched Correction: energy in watt to kW')
        
        power_stats = self._get_power_statistics(df)

        # Case 7 : Update Rows 
        # Total Energy Kwh: No	
        # Max Thermal Power Kw: No	
        # AVG Daily Availability: Yes	
        # Monthly Power: Yes
        # To Do: Calculate avg thermal power with monthly power values/12. Update the max thermal power as max value of monthly power values
        # calculate total energy by avg thermal power or monthly power values.
        case7_mask =(
            (~df['case_resolved']) &
            (df['Annual_Heat_Amount_kWh_per_Year'] <= 1) &
            (df['Max_Thermal_Power_kW'] <= 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_any_gt1'])
            )
        if case7_mask.any():
            print("Case7 results:\n", df.loc[case7_mask, cols_to_show])
            
            # ---> TAKE SNAPSHOT BEFORE CHANGES <---
            rows_before = df[case7_mask].copy()
            
            df.loc[case7_mask, "AVG_Thermal_Power"] = calculator.calculate_avg_thermal_power_by_monthly_powers(df[case7_mask])
            df = self._update_max_power_from_monthly(df, case7_mask) 
            df = self._update_working_hours_from_availability(df, case7_mask, calculator) 
            df = self._update_annual_heat_from_avg_power(df, case7_mask) 
            df.loc[case7_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case7_mask])
            
            df.loc[case7_mask, 'Update_History'] += "Case 7: Updated Total Energy | "
            df.loc[case7_mask, 'case_resolved'] = True
            # ---> PASS SNAPSHOT TO LOGGER <---
            self._log_updated_rows(df, case7_mask, rows_before, 'Case 7 Update Rows')

        power_stats = self._get_power_statistics(df)
        # Case 8 : Update rows 
        # Total Energy Kwh: No	
        # Max Thermal Power Kw: Yes	
        # AVG Daily Availability: Yes	
        # Monthly Power: Yes
        # To Do: Calculate AVG Thermal Power(monthly powers/12) Update total energy based on the AVG thermal power. check with total energy calculated by monthly powers
        # check also if the maxMonth==Max thermal power
        case8_mask =(
            (~df['case_resolved']) &
            (df['Annual_Heat_Amount_kWh_per_Year'] <= 1) &
            (df['Max_Thermal_Power_kW'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_any_gt1'])
            )
        if case8_mask.any():
            print("Case8 results:\n", df.loc[case8_mask, cols_to_show])
            rows_before = df[case8_mask].copy()
            
            df.loc[case8_mask, "AVG_Thermal_Power"] = calculator.calculate_avg_thermal_power_by_monthly_powers(df[case8_mask])
            df = self._update_working_hours_from_availability(df, case8_mask, calculator) 
            df = self._update_annual_heat_from_avg_power(df, case8_mask) 
            df.loc[case8_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case8_mask])
            
            df.loc[case8_mask, 'Update_History'] += "Case 8: Updated Total Energy | "
            df.loc[case8_mask, 'case_resolved'] = True
            self._log_updated_rows(df, case8_mask, rows_before, 'Case 8 Update Rows')

        power_stats = self._get_power_statistics(df)
           
        # Case 9 : Update rows
        # Total Energy Kwh: No	
        # Max Thermal Power Kw: Yes	
        # AVG Daily Availability: Yes	
        # Monthly Power: No
        # To Do: Update all the monthly power and avg thermal power as max thermal power. update total energy calculated by avg thermal or montly values.
        case9_mask =(
            (~df['case_resolved']) &
            (df['Annual_Heat_Amount_kWh_per_Year'] <= 1) &
            (df['Max_Thermal_Power_kW'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_all_less1'])
            )
        if case9_mask.any():
            print("Case9 results:\n", df.loc[case9_mask, cols_to_show])
            rows_before = df[case9_mask].copy()
            
            df = self._update_monthly_power_with_max_power(df, case9_mask) 
            df.loc[case9_mask, "AVG_Thermal_Power"] = df.loc[case9_mask, "Max_Thermal_Power_kW"]
            df = self._update_working_hours_from_availability(df, case9_mask, calculator) 
            df = self._update_annual_heat_from_avg_power(df, case9_mask) 
            df.loc[case9_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case9_mask])
            
            df.loc[case9_mask, 'Update_History'] += "Case 9: Updated Monthly Power | "
            df.loc[case9_mask, 'case_resolved'] = True
            self._log_updated_rows(df, case9_mask, rows_before, 'Case 9 Update Rows')

        power_stats = self._get_power_statistics(df)

        # Case 10 : Update rows
        # Total Energy Kwh: Yes	
        # Max Thermal Power Kw: Yes	
        # AVG Daily Availability: Yes	
        # Monthly Power: Yes
        # To Do: Calculate the avg thermal power by total energy / hours per year
        # check if avg thermal power == avg of monthly power values
        case10_mask =(
            (~df['case_resolved']) &
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_any_gt1'])
            )
        if case10_mask.any():
            print("Case10 results:\n", df.loc[case10_mask, cols_to_show].head(25))
            rows_before = df[case10_mask].copy()
            
            df = self._update_working_hours_from_availability(df, case10_mask, calculator)
            df.loc[case10_mask, "AVG_Thermal_Power"] = calculator.calculate_max_avg_thermal_power_from_energy(df[case10_mask]).round(2)
            df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
            
            df.loc[case10_mask, 'Update_History'] += "Case 10: Updated Annual Working Hours + AVG Thermal | "
            df.loc[case10_mask, 'case_resolved'] = True
            self._log_updated_rows(df, case10_mask, rows_before, 'Case 10 Check-Update')

        power_stats = self._get_power_statistics(df)
        # Case 11 : Update rows
        # Total Energy Kwh: Yes	
        # Max Thermal Power Kw: Yes	
        # AVG Daily Availability: No	
        # Monthly Power: Yes
        # To Do: calculate avg thermal power. update Avg daily availability: total energy/avg thermal power >yearly max hours?
        # if yes, we will calculate avg thermal power with a different way. before that lets see how many cases we have
        case11_mask =(
            (~df['case_resolved']) &
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] > 1) &
            (df['Avg_Daily_Availability_h'] <= 1) &             
            (power_stats['monthly_any_gt1'])
            )
        if case11_mask.any():
            print("Case11 results:\n", df.loc[case11_mask, cols_to_show])
            rows_before = df[case11_mask].copy()
            
            df = self._update_avg_thermal_power_from_monthly(df, case11_mask, calculator) 
            df = self._update_annual_hours_with_avg_power(df, case11_mask, calculator) 
            df = self._update_avg_daily_availability(df, case11_mask, calculator) 
            df.loc[case11_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case11_mask])
            
            df.loc[case11_mask, 'Update_History'] += "Case 11: Updated AVG Daily Availability| "
            df.loc[case11_mask, 'case_resolved'] = True
            self._log_updated_rows(df, case11_mask, rows_before, 'Case 11 Update Rows')
            
            # --- Physical Limit Check ---
            df_case11_check = df.loc[case11_mask].copy()
            violations_mask = df_case11_check['Avg_Daily_Availability_h'] > 24
            if violations_mask.any():
                violations_df = df_case11_check[violations_mask]
                print(f"WARNING: Found {len(violations_df)} rows where calculated 'Avg_Daily_Availability_h' exceeds 24 hours.")
            
            avg_power_subset = df.loc[case11_mask, 'AVG_Thermal_Power']
            max_power_subset = df.loc[case11_mask, 'Max_Thermal_Power_kW']
            count_within_tolerance = np.isclose(avg_power_subset, max_power_subset, rtol=0.03).sum()
            print(f"Case 11 - Max Power = AVG Power: {count_within_tolerance} (out of {case11_mask.sum()} total case rows)")

        power_stats = self._get_power_statistics(df)
        # Case 12 : Update rows
        # Total Energy Kwh: Yes	
        # Max Thermal Power Kw: No	
        # AVG Daily Availability: Yes	
        # Monthly Power: Yes
        # To Do: Calculate AVG thermal power. Total energy/hours per year. Is this the same result with monthly power values/12 If yes, great
        # If no, we will pursued a different case
        case12_mask =(
            (~df['case_resolved']) &
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] <= 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_any_gt1'])
            )
        if case12_mask.any():
            print("Case12 results:\n", df.loc[case12_mask, cols_to_show])
            rows_before = df[case12_mask].copy()
            
            df = self._update_working_hours_from_availability(df, case12_mask, calculator)
            df = self._update_max_power_from_monthly(df, case12_mask) 
            df.loc[case12_mask, "AVG_Thermal_Power"]= calculator.calculate_avg_thermal_power_by_monthly_powers(df[case12_mask])
            df.loc[case12_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case12_mask])
            
            df.loc[case12_mask, 'Update_History'] += "Case 12: Updated Max Thermal Power | "
            df.loc[case12_mask, 'case_resolved'] = True
            self._log_updated_rows(df, case12_mask, rows_before, 'Case 12 Update Rows')
            
        power_stats = self._get_power_statistics(df)

        # Case 13 : Update rows
        # Total Energy Kwh: Yes	
        # Max Thermal Power Kw: Yes	
        # AVG Daily Availability: Yes	
        # Monthly Power: No
        # To Do: Calculate avg thermal power with Total energy/hours per year. Update all monthly power values with avg thermal power.
        # for how many cases max thermal power==avg thermal power
        case13_mask =(
            (~df['case_resolved']) &
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] > 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_all_less1'])
            )
        if case13_mask.any():
            print("Case13 results:\n", df.loc[case13_mask, cols_to_show])
            rows_before = df[case13_mask].copy()
            
            df = self._update_working_hours_from_availability(df, case13_mask, calculator) 
            df.loc[case13_mask, "AVG_Thermal_Power"] = calculator.calculate_max_avg_thermal_power_from_energy(df[case13_mask])
            df = self._update_monthly_power_with_avg_thermal_power(df, case13_mask) 
            df.loc[case13_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case13_mask])
            
            df.loc[case13_mask, 'Update_History'] += "Case 13: Updated Monthly Power | "
            df.loc[case13_mask, 'case_resolved'] = True
            self._log_updated_rows(df, case13_mask, rows_before, 'Case 13 Update Rows')

            df_case13_check = df.loc[case13_mask].copy()
            df_case13_check['Weekend_Availability'] = df_case13_check['Weekend_Availability'].str.lower() == 'ja'
            violations_df = get_violations_report(df_case13_check, calculator)
            if not violations_df.empty:
                print(f"WARNING: Found {len(violations_df)} rows where 'Annual_Working_Hours' exceeds the max possible.")
            
            avg_power_subset = df.loc[case13_mask, 'AVG_Thermal_Power']
            max_power_subset = df.loc[case13_mask, 'Max_Thermal_Power_kW']
            count_within_tolerance = np.isclose(avg_power_subset, max_power_subset, rtol=0.03).sum()
            print(f"Case 13 - Max Power = AVG Power: {count_within_tolerance} (out of {case13_mask.sum()} total case rows)")

        power_stats = self._get_power_statistics(df)

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
            (~df['case_resolved']) &
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] > 1) &
            (df['Avg_Daily_Availability_h'] <= 1) &             
            (power_stats['monthly_all_less1'])
            )
        if case14_mask.any():
            print("Case14 results:\n", df.loc[case14_mask, cols_to_show])
            rows_before = df[case14_mask].copy()
            
            df.loc[case14_mask, "AVG_Thermal_Power"] = df.loc[case14_mask, "Max_Thermal_Power_kW"]
            df = self._update_monthly_power_with_max_power(df, case14_mask) 
            df = self._update_annual_hours_with_calculated(df, case14_mask, calculator) 
            df = self._update_avg_daily_availability(df, case14_mask, calculator) 
            df.loc[case14_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case14_mask])
            
            df.loc[case14_mask, 'Update_History'] += "Case 14: Updated Monthly Power + AVG Daily Availability | "
            df.loc[case14_mask, 'case_resolved'] = True
            self._log_updated_rows(df, case14_mask, rows_before, 'Case 14 Update Rows')

            df_case14_check = df.loc[case14_mask].copy()
            df_case14_check['Weekend_Availability'] = df_case14_check['Weekend_Availability'].str.lower() == 'ja'
            violations_df = get_violations_report(df_case14_check, calculator)
            if not violations_df.empty:
                print(f"WARNING: Found {len(violations_df)} rows where 'Annual_Working_Hours' exceeds the max possible.")
        
        power_stats = self._get_power_statistics(df)

        # Case 15 : Update rows
        # Total Energy Kwh: Yes	
        # Max Thermal Power Kw: No	
        # AVG Daily Availability: Yes	
        # Monthly Power: No
        # To Do: Calculate avg thermal power by total energy/hours per year. Update max thermal power and monthly values as avg thermal power
        case15_mask =(
            (~df['case_resolved']) &
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] <= 1) &
            (df['Avg_Daily_Availability_h'] > 1) &             
            (power_stats['monthly_all_less1'])
            )
        if case15_mask.any():
            print("Case15 results:\n", df.loc[case15_mask, cols_to_show])
            rows_before = df[case15_mask].copy()
            
            df = self._update_working_hours_from_availability(df, case15_mask, calculator) 
            df.loc[case15_mask, "AVG_Thermal_Power"] = calculator.calculate_max_avg_thermal_power_from_energy(df[case15_mask])
            df.loc[case15_mask, "Max_Thermal_Power_kW"] = df.loc[case15_mask, "AVG_Thermal_Power"]
            df = self._update_monthly_power_with_avg_thermal_power(df, case15_mask) 
            df.loc[case15_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case15_mask])
            
            df.loc[case15_mask, 'Update_History'] += "Case 15: Updated Monthly Power + MAX Thermal Power| "
            df.loc[case15_mask, 'case_resolved'] = True
            self._log_updated_rows(df, case15_mask, rows_before, 'Case 15 Update Rows')
        
        power_stats = self._get_power_statistics(df)

        # Case 16 : Update rows
        # Total Energy Kwh: Yes	
        # Max Thermal Power Kw: No	
        # AVG Daily Availability: No	
        # Monthly Power: Yes
        # To Do: Calculate avg thermal power with monthly power/12. yearly hours is total energy/avg thermal power and then find and update the avg daily availablity. check data type of avg daily availability
        case16_mask =(
            (~df['case_resolved']) &
            (df['Annual_Heat_Amount_kWh_per_Year'] > 1) &
            (df['Max_Thermal_Power_kW'] <= 1) &
            (df['Avg_Daily_Availability_h'] <= 1) &             
            (power_stats['monthly_any_gt1'])
            )
        if case16_mask.any():
            print("Case16 results:\n", df.loc[case16_mask, cols_to_show])
            rows_before = df[case16_mask].copy()
            
            df.loc[case16_mask, "AVG_Thermal_Power"] = calculator.calculate_avg_thermal_power_by_monthly_powers(df[case16_mask])
            df = self._update_annual_hours_with_avg_power(df, case16_mask, calculator) 
            df = self._update_avg_daily_availability(df, case16_mask, calculator) 
            df.loc[case16_mask, 'Annual_Energy_Months'] = calculator.calculate_annual_energy(df[case16_mask])
            
            df.loc[case16_mask, 'Update_History'] += "Case 16: Updated AVG Daily Availability + MAX Thermal Power | "
            df.loc[case15_mask, 'case_resolved'] = True
            self._log_updated_rows(df, case16_mask, rows_before, 'Case 16 Update Rows')
            
        power_stats = self._get_power_statistics(df)  
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
            print(f"\n--- Found {case_unmatched4_mask.sum()} plausible but unmatched rows for Final Correction ---")
            
            rows_before = df.copy()
            df, updated_mask = self._apply_power_correction_strategy4(df, case_unmatched4_mask, calculator)
            
            if updated_mask.any():
                df.loc[updated_mask, 'Update_History'] += "Case Unmatched 4: Corrected by scaling factor | "
                df['Annual_Energy_Months'] = calculator.calculate_annual_energy(df)
                self._log_updated_rows(df, updated_mask, rows_before.loc[updated_mask], 'Case unmatched Correction: scaling factor of energy')
        
        power_stats = self._get_power_statistics(df)
        
        # ─── BfEE Step 1: Plant-Level Filter ───────────────────────────────────────
        # Remove entries below ANY of the three plant-level thresholds (OR logic).
        # Regulation from PFA: < 200 MWh/a (200.000 kWh/a)  OR  < 1,500 h/year  OR  avg temp < 25°C
        bfee_plant_mask = (
            (df['Annual_Heat_Amount_kWh_per_Year'] < 200000) | # kWh/a
            (df['Annual_Working_Hours'] < 1500)              |
            (df['Avg_Temperature_Level_C'] < 25)
        )
        if bfee_plant_mask.any():
            print(f"BfEE Plant Filter: removing {bfee_plant_mask.sum()} entries below plant-level threshold.")
            df = self._drop_rows(df, bfee_plant_mask, case_name='BfEE Plant-Level Filter', reason='Entry below plant-level threshold (< 200 MWh/a, < 1500 h/year, or < 25°C)')

        # ─── BfEE Step 2: Site-Level Filter ────────────────────────────────────────
        # After plant filter, group by Site_Name and remove entire sites
        # whose total waste heat is below 800 MWh/a. (800.000 kWh/a)
        # Note: reset index first so groupby aligns correctly after previous drops.
        
        site_totals = df.groupby('Site_Name')['Annual_Heat_Amount_kWh_per_Year'].transform('sum')
        bfee_site_mask = site_totals < 800000
        if bfee_site_mask.any():
            print(f"BfEE Site Filter: removing {bfee_site_mask.sum()} entries from sites below 800 MWh/a total.")
            df = self._drop_rows(df, bfee_site_mask, case_name='BfEE Site-Level Filter', reason='Site total waste heat below 800 MWh/a threshold')
        
        violations_df = get_violations_report(df, calculator)


        if self.changelog:
            change_df = pd.concat(self.changelog, ignore_index=False)
        else:
            change_df = pd.DataFrame()

        return df, change_df, self.warnings, violations_df

