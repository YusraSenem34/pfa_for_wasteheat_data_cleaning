#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File              : profile.py
# License           : License: 
# Author            : Konstantinos Papanikandros
# Date              : MIT

import os
import datetime
from typing import Dict, List

import matplotlib.pyplot as plt
import pandas as pd
from pydantic import BaseModel, ConfigDict


class WasteHeatProfile(BaseModel):
    """
    Complete waste-heat profile including metadata and time series.
    """
    waste_heat_potential_name: str
    temperature_c: int
    weekend_available: bool
    avg_daily_availability_h: float
    profile_data: pd.DataFrame
    aggregated_demands: float | None = None
    unit_of_output: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ElectricityProfile(BaseModel):
    """
    Complete electricity profile including metadata and time series.
    """
    profile_data: pd.DataFrame
    aggregated_demands: float | None = None
    unit_of_output: str

    model_config = ConfigDict(arbitrary_types_allowed=True)


class EnergyProfile(BaseModel):
    """
    Generic energy profile for a process or asset.

    This has been refactored to use pydantic for validation and type safety.
    """
    company_name: str | None = None
    site_name: str | None = None
    city: str | None = None
    nace_code: str
    description: str
    production_volume: float
    start_time: int
    end_time: int
    weekdays: List[int]
    weekend_days: List[int]
    year: int
    working_hours: Dict
    holidays: Dict

    # Optional nested waste-heat info (only populated for waste-heat profiles)
    waste_heat: WasteHeatProfile | None = None
    electricity: ElectricityProfile | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_profile_df(self) -> pd.DataFrame:
        """
        Resolve the DataFrame that contains the time series.

        Priority:
        1. Nested waste_heat.profile_data if available
        2. Nested electricity.profile_data if available
        """
        if self.waste_heat is not None:
            return self.waste_heat.profile_data
        if self.electricity is not None:
            return self.electricity.profile_data
        raise ValueError("No profile_data available in nested WasteHeatProfile or ElectricityProfile")

    def save_to_csv(self, output_dir='src/plots'):
        """
        Save the energy profile to a CSV file.
        
        Args:
            output_dir (str): Directory to save the CSV file
        """
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, f"energy_profile_{self.nace_code}_{self.year}.csv")
        df = self._get_profile_df()
        df.to_csv(output_file)
        print(f"\nEnergy profile saved to {output_file}")
        return output_file

    def plot(self, output_dir: str = 'src/plots', filename: str | None = None):
        """
        Create and save plots of the energy profile.
        
        Args:
            output_dir (str): Directory to save the plot
        """
        os.makedirs(output_dir, exist_ok=True)
        df = self._get_profile_df()
        
        # Create main profile plot
        plt.figure(figsize=(15, 8))
        
        for column in df.columns:
            # Calculate total demand in kW
            total_demand = df[column].sum() / 1000  # Convert to kW
            # Format total demand with German number format
            formatted_demand = self.format_german_number(total_demand)
            # Create label with total demand
            label = f"{column.replace(' [W]', ' [kW]')} (Total: {formatted_demand} kWh)"
            # Convert W to kW by dividing by 1000
            plt.plot(df.index, df[column] / 1000, label=label)
        
        plt.title(f"Energy Profile for NACE {self.nace_code} ({self.year})")
        plt.xlabel("Time")
        plt.ylabel("Power (kW)")
        plt.legend()
        plt.grid(True)
        
        # Format y-axis ticks with German number format
        ax = plt.gca()
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: self.format_german_number(x)))
        
        # Save plot
        if filename is None:
            filename = f"energy_profile_{self.nace_code}_{self.year}.png"
        plot_file = os.path.join(output_dir, filename)
        plt.savefig(plot_file)
        plt.close()
        print(f"Plot saved to {plot_file}")
        return plot_file

    def format_german_number(self, number):
        """Format a number in German style (1.234,56)"""
        # Format with 2 decimal places
        formatted = f"{number:,.2f}"
        # Replace comma with dot for thousands
        formatted = formatted.replace(",", "X")
        # Replace dot with comma for decimal
        formatted = formatted.replace(".", ",")
        # Replace X with dot for thousands
        formatted = formatted.replace("X", ".")
        return formatted

    def calculate_total_working_hours(self) -> int:
        """
        Calculate the total number of working hours per year.
        Takes into account:
        - Weekdays vs weekend days
        - Working hours per day
        - Holidays
        
        Returns:
            int: Total number of working hours per year
        """
        # Create a date range for the entire year
        start_date = datetime.datetime(self.year, 1, 1)
        end_date = datetime.datetime(self.year, 12, 31)
        date_range = pd.date_range(start=start_date, end=end_date, freq="D")
        
        total_hours = 0
        daily_hours = self.end_time - self.start_time
        
        for date in date_range:
            # Skip if it's a holiday
            if date.date() in self.holidays:
                continue
                
            # Check if it's a weekday or weekend
            if date.weekday() + 1 in self.weekdays:  # +1 because weekday() returns 0-6
                total_hours += daily_hours
            elif date.weekday() + 1 in self.weekend_days:
                # Weekend days have reduced hours (10% of normal hours)
                # TODO: Make this factor configurable
                total_hours += daily_hours * 0.1
        
        return int(total_hours)

    @property
    def total_working_hours(self) -> int:
        """Expose total working hours as a property, computed on demand."""
        return self.calculate_total_working_hours()

    def print_summary(self):
        """Print a summary of the energy profile."""
        print(f"\nEnergy Profile Summary for NACE {self.nace_code}:")
        if self.company_name:
            print(f"Company: {self.company_name}")
        if self.site_name:
            print(f"Site: {self.site_name}")
        if self.city:
            print(f"City: {self.city}")
        print(f"Description: {self.description}")
        print(f"Production Volume: {self.format_german_number(self.production_volume)}")
        print(f"Total Working Hours per Year: {self.format_german_number(self.total_working_hours)} h")
        
        if self.waste_heat is not None:
            print(f"\nWaste Heat Profile:")
            print(f"  Potential Name: {self.waste_heat.waste_heat_potential_name}")
            print(f"  Temperature: {self.waste_heat.temperature_c} °C")
            print(f"  Weekend Available: {self.waste_heat.weekend_available}")
            print(f"  Avg Daily Availability: {self.waste_heat.avg_daily_availability_h} h")
            if self.waste_heat.aggregated_demands is not None:
                print(f"  Total Waste Heat: {self.format_german_number(self.waste_heat.aggregated_demands)} {self.waste_heat.unit_of_output}")
        
        if self.electricity is not None:
            print(f"\nElectricity Profile:")
            if self.electricity.aggregated_demands is not None:
                print(f"  Total Electricity: {self.format_german_number(self.electricity.aggregated_demands)} {self.electricity.unit_of_output}")

    def sanity_check(self):
        """
        Verify that the aggregated demands match the sum of hourly energy demands.
        Prints a warning if there are discrepancies.
        """
        print("\nRunning sanity check...")
        
        df = self._get_profile_df()

        # Check waste heat demand if available
        if self.waste_heat is not None and self.waste_heat.aggregated_demands is not None:
            # Find the waste heat column (should match temperature)
            waste_heat_col = None
            for col in df.columns:
                if f"waste_heat_{self.waste_heat.temperature_c}" in col or "waste_heat" in col.lower():
                    waste_heat_col = col
                    break
            
            if waste_heat_col:
                # Values are already in kW, so sum gives kWh
                hourly_sum = df[waste_heat_col].sum()  # Already in kW, sum gives kWh
                aggregated = self.waste_heat.aggregated_demands
                if abs(hourly_sum - aggregated) > 0.01:  # Allow for small floating point differences
                    print(f"WARNING: Waste heat demand mismatch!")
                    print(f"  Aggregated: {self.format_german_number(aggregated)} {self.waste_heat.unit_of_output}")
                    print(f"  Hourly sum: {self.format_german_number(hourly_sum)} {self.waste_heat.unit_of_output}")
                    print(f"  Difference: {self.format_german_number(abs(hourly_sum - aggregated))} {self.waste_heat.unit_of_output}")
                else:
                    print(f"✓ Waste heat demand check passed")
            else:
                print("⚠ Could not find waste heat column for sanity check")
        
        # Check electricity demand if available
        if self.electricity is not None and self.electricity.aggregated_demands is not None:
            electricity_col = None
            for col in df.columns:
                if "electricity" in col.lower():
                    electricity_col = col
                    break
            
            if electricity_col:
                # Convert from W to kW if needed
                if " [W]" in electricity_col:
                    hourly_sum = df[electricity_col].sum() / 1000  # Convert to kWh
                else:
                    hourly_sum = df[electricity_col].sum()  # Already in kW
                aggregated = self.electricity.aggregated_demands
                if abs(hourly_sum - aggregated) > 0.01:  # Allow for small floating point differences
                    print(f"WARNING: Electricity demand mismatch!")
                    print(f"  Aggregated: {self.format_german_number(aggregated)} {self.electricity.unit_of_output}")
                    print(f"  Hourly sum: {self.format_german_number(hourly_sum)} {self.electricity.unit_of_output}")
                    print(f"  Difference: {self.format_german_number(abs(hourly_sum - aggregated))} {self.electricity.unit_of_output}")
                else:
                    print("✓ Electricity demand check passed")
            else:
                print("⚠ Could not find electricity column for sanity check")
        
        if self.waste_heat is None and self.electricity is None:
            print("No profile data available for sanity check")
