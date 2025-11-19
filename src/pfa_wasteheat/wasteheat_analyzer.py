#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File              : wasteheat_analyzer.py
# License           : License: MIT
# Author            : Yusra Senem yuesra.senem@dlr.de
# Date              : 02.08.2025

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import streamlit as st
from matplotlib.ticker import FuncFormatter

from energy_calculations import EnergyCalculator

# --- Central formulas dictionary ---
FORMULAS = {
    # Annual Heat Amount calculations
    "Annual_Heat_Amount_kWh_per_Year": "Provided Annual Energy (Excel data)",
    "Annual_Energy_Months": "By Monthly Powers: monthly_power * Avg.Daily_Availability * working_days",
    "Annual_Energy_Thermal": "By Thermal Power: Max_Thermal_Power * Avg.Daily_Availability * annual_working_days",
    "Annual_Energy_MaxMonth": "By Max Month: Max(Power_Profile_Month) * Avg.Daily_Availability * annual_working_days",

    # Annual Working Hours calculations
    "Annual_Working_Hours": "Provided value (Excel data)",
    "Calc_Working_Hours_Availability": "((365 - 9) / 7) × Weekly_Working_Days × Avg_Daily_Availability_h",
    "Calc_Working_Hours_Fallback": "Alternative fallback calculation"
}

class WasteHeatAnalyzer:
    """
    A stateless analyzer class. 
    Methods accept a DataFrame as input rather than storing it internally.
    """

    def __init__(self):
        # No internal state needed
        pass

    def compare_energy_values(self, df, tolerance=0.10):
        """
        Compare provided vs. calculated annual heat amount.
        Returns the modified DataFrame and a list of result tuples.
        """
        provided_col = 'Annual_Heat_Amount_kWh_per_Year'
        calculated_col = 'Annual_Energy_Months'
        
        diff_col = f'Diff_{calculated_col}'
        match_col = f'Match_{calculated_col}'
        
        # Calculate the absolute difference
        df[diff_col] = df[calculated_col] - df[provided_col]
        
        # Check if the calculated value is within the tolerance range
        df[match_col] = (
            (df[provided_col] * (1 + tolerance) >= df[calculated_col]) &
            (df[provided_col] * (1 - tolerance) <= df[calculated_col])
        )
        
        comparison_results = [(calculated_col, diff_col, match_col)]
        
        return df, comparison_results

    @staticmethod
    def plot_error_distribution_interactive(df, tolerance=0.10, y_axis_limit=100):
        """
        Creates an interactive scatter plot showing the sorted percentage error
        for each observation, with counts in the legend and a visible x-axis scale.
        """
        provided_col = 'Annual_Heat_Amount_kWh_per_Year'
        calculated_col = 'Annual_Energy_Months'

        # --- 1. Data Preparation ---
        plot_df = df[[provided_col, calculated_col]].copy().reset_index().rename(columns={'index': 'Original_Index'})
        
        plot_df['Percentage_Error'] = np.where(
            plot_df[provided_col] > 0,
            ((plot_df[calculated_col] - plot_df[provided_col]) / plot_df[provided_col]) * 100,
            np.inf
        )
        
        plot_df['Match_Status'] = np.where(
            plot_df['Percentage_Error'].abs() <= (tolerance * 100),
            'Matched',
            'Unmatched'
        )
        
        # --- 2. Create Legend Labels with Counts ---
        counts = plot_df['Match_Status'].value_counts()
        matched_label = f"Matched ({counts.get('Matched', 0):,})"
        unmatched_label = f"Unmatched ({counts.get('Unmatched', 0):,})"
        
        plot_df['Legend_Label'] = plot_df['Match_Status'].map({
            'Matched': matched_label,
            'Unmatched': unmatched_label
        })

        # Sort the data by the error
        plot_df = plot_df.sort_values('Percentage_Error', ascending=False).reset_index(drop=True)
        
        # --- 3. Create Interactive Scatter Plot ---
        fig = px.scatter(
            plot_df,
            x=plot_df.index,
            y='Percentage_Error',
            color='Legend_Label',
            color_discrete_map={
                matched_label: 'blue',
                unmatched_label: 'red'
            },
            title='Sorted Error Distribution: Calculated vs. Provided Annual Heat',
            labels={
                'x': 'Observation (Sorted by Error)',
                'Percentage_Error': 'Percentage Error (%)'
            },
            hover_data={
                'Original_Index': True,
                provided_col: ':,',
                calculated_col: ':,',
                'Percentage_Error': ':.2f'
            }
        )

        # Add Tolerance Lines
        fig.add_hline(y=tolerance * 100, line_dash="dash", line_color="gray", annotation_text=f'+{tolerance*100}% Match Tolerance')
        fig.add_hline(y=-tolerance * 100, line_dash="dash", line_color="gray", annotation_text=f'-{tolerance*100}% Match Tolerance')
        
        # --- 4. Customize Layout and Axes ---
        fig.update_xaxes(showticklabels=True, tickmode='linear', dtick=5000)
        fig.update_yaxes(range=[-y_axis_limit, y_axis_limit])
        fig.update_layout(legend_title='Match Status')
        
        return fig

    @staticmethod
    def plot_annual_heat_comparison_by_temp(df):
        heat_cols = {
            'Annual_Heat_Amount_kWh_per_Year': 'Provided Annual Heat',
            'Annual_Energy_Months': 'Calculated from Months'
        }
        FORMULAS = {
            'Annual_Heat_Amount_kWh_per_Year': 'Provided Annual Heat',
            'Annual_Energy_Months': 'Calculated from Months'
        }

        missing_cols = [col for col in heat_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing columns for plotting: {missing_cols}")

        plot_long = df.melt(
            id_vars="Avg_Temperature_Level_C",
            value_vars=list(heat_cols.keys()),
            var_name="Type",
            value_name="Annual_Heat_kWh_per_Year"
        )
        plot_long["Type"] = plot_long["Type"].map(FORMULAS)

        fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(12, 10), sharex=True, sharey=True)
        
        # Plot 1: Provided
        provided_data = plot_long[plot_long['Type'] == 'Provided Annual Heat']
        sns.scatterplot(data=provided_data, x="Avg_Temperature_Level_C", y="Annual_Heat_kWh_per_Year", alpha=0.7, ax=axes[0])
        axes[0].set_title("Provided Annual Heat vs. Temperature Level")
        axes[0].grid(True, which='both', linestyle='--', linewidth=0.5)
        axes[0].set_ylabel("Heat Amount (kWh/year)")

        # Plot 2: Calculated
        calculated_data = plot_long[plot_long['Type'] == 'Calculated from Months']
        sns.scatterplot(data=calculated_data, x="Avg_Temperature_Level_C", y="Annual_Heat_kWh_per_Year", alpha=0.7, color='darkorange', ax=axes[1])
        axes[1].set_title("Calculated Annual Heat vs. Temperature Level")
        axes[1].grid(True, which='both', linestyle='--', linewidth=0.5)
        axes[1].set_ylabel("Heat Amount (kWh/year)")

        # General Customizations
        axes[0].set_yscale('log')
        formatter = FuncFormatter(lambda x, p: format(int(x), ','))
        axes[0].get_yaxis().set_major_formatter(formatter)
        axes[1].set_xlabel("Average Temperature Level (°C)")

        plt.tight_layout()
        st.pyplot(fig)

    @staticmethod
    def display_comparison(df, comparison_results, top_n=20):
        """Show results table and plot in Streamlit."""
        st.subheader("Comparison Table")
        st.dataframe(df)
    
        st.subheader(f"Top {top_n} Differences Plot")
        melted = df.melt(
            id_vars=['Company_Name'],
            value_vars=[c[1] for c in comparison_results],  # diff columns
            var_name='Comparison',
            value_name='Difference (kWh)'
        )

        # Take absolute differences and find top N
        top_diff = (
            melted
            .assign(abs_diff=lambda x: x['Difference (kWh)'].abs())
            .nlargest(top_n, 'abs_diff')
        )
    
        fig = px.bar(
            top_diff,
            x='Company_Name',
            y='Difference (kWh)',
            color='Comparison',
            barmode='group',
            title=f'Top {top_n} Largest Differences Between Calculated and Provided Annual Heat Amounts'
        )
        st.plotly_chart(fig, use_container_width=True)

    @staticmethod
    def build_comparison_summary(df, comparison_results) -> pd.DataFrame:
        """Build a summary table of matched vs unmatched counts."""
        summary = {}
        for calc_col, diff_col, match_col in comparison_results:
            # Get the counts of True (Matched) and False (Unmatched)
            counts = df[match_col].value_counts()
            
            # Ensure both True and False are in the index, filling with 0 if missing
            counts = counts.reindex([True, False], fill_value=0)
            
            summary[calc_col] = counts.rename(
                index={True: "Matched", False: "Unmatched"}
            )
            
        # Transpose → rows = calculations, then reorder columns
        summary_df = pd.DataFrame(summary).T.fillna(0).astype(int)
        return summary_df[["Matched", "Unmatched"]]

    @staticmethod
    def analyze_numeric_correlations(df) -> pd.DataFrame:
        """Analyze correlations between numeric variables"""
        numeric_cols = [
            'Annual_Heat_Amount_kWh_per_Year',
            'Max_Thermal_Power_kW',
            'Avg_Temperature_Level_C',
            'Avg_Daily_Availability_h',
            'Annual_Working_Hours'
        ]

        corr_matrix = df[numeric_cols].corr()

        fig, ax = plt.subplots(figsize=(8, 5))
        sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', center=0, ax=ax)
        ax.set_title("Correlation Matrix of Numeric Variables")
        plt.tight_layout()

        st.pyplot(fig)