#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File              : app.py
# License           : License: MIT
# Author            : Yusra Senem yuesra.senem@dlr.de
# Date              : 07.08.2025

import streamlit as st
import pandas as pd
from main import WasteHeatAnalysisPipeline
import os
from wasteheat_analyzer import WasteHeatAnalyzer
from utils import check_working_hours_limits, get_violations_report
import io # for in-memory file handling in download of excel file


st.set_page_config(page_title="Waste Heat Analyzer", layout="wide")
st.title("Waste Heat Data Cleaning & Analysis")

# Automatically load the file
#default_file_path = os.path.join(os.path.dirname(__file__), "pfa_datenpraesentation.xlsx")

# --- 1. File Uploader ---
uploaded_file = st.file_uploader("Upload your Waste Heat Excel file", type=["xlsx"])

if uploaded_file is not None:
    try:
        # --- 2. Load Data Immediately (Crucial for Postal Codes) ---
        # We load it here to ensure 'PLZ' is read as a string before any processing
        df_initial = pd.read_excel(
            uploaded_file, 
            sheet_name='Abwärmepotentiale',  # Select the correct sheet
            skiprows=1,                      # Skip the first row
            decimal=",",                     # Handle German decimals
            thousands=".",                   # Handle German thousands separators
            dtype={'PLZ': str}               # Force Postal Code to be string
        )
        
        # Initialize pipeline with no path (we are passing the data directly)
        pipeline = WasteHeatAnalysisPipeline(None)
        
        # --- 3. Run Pipeline with the Dataframe ---
        # We pass the dataframe we just loaded
        df, raw_df, change_df, warnings, fixed_raw_df, violations_df = pipeline.run(df_initial)

        st.success("✅ Data cleaned successfully!")

        # --- Cleaning Summary ---
        st.subheader("Summary")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Rows Before Cleaning", raw_df.shape[0])
        col2.metric("Total Rows After Cleaning", df.shape[0]) 
        col3.metric("Total Changes Logged", change_df.shape[0])
        col4.metric("Cases Triggered", len(change_df['change_reason'].unique()) if not change_df.empty else 0)

        # --- Warnings ---
        if warnings:
            st.subheader("⚠️ Warnings")
            for w in warnings:
                st.warning(w)

        # --- Cleaned Data ---
        analyzer = WasteHeatAnalyzer()
        st.subheader("Cleaned Data")
        st.dataframe(df, use_container_width=True)
        


        if not change_df.empty:
            st.subheader("Changelog")
            # Group by change_reason, then count the unique indexes in each group
            case_counts = (
                change_df.groupby('change_reason')
                .apply(lambda x: x.index.nunique()) # <-- This is the key change
                .reset_index(name='count')
            )
            # Extract case numbers and sort
            case_counts['case_num'] = (
                case_counts['change_reason']
                .str.extract(r'Case (\d+)', expand=False)
                .astype(float)
                .fillna(999)
            )
            case_counts_sorted = case_counts.sort_values('case_num')
            # Build options as 'CaseName (count)'
            case_options = [f"{row['change_reason']} ({row['count']})" for _, row in case_counts_sorted.iterrows()]
            selected_case_label = st.selectbox("Filter by change reason", ["All"] + case_options)

            # Map label back to case name
            if selected_case_label == "All":
                filtered_change_df = change_df
                selected_case = "All"
            else:
                selected_case = selected_case_label.split(" (")[0]
                filtered_change_df = change_df[change_df['change_reason'] == selected_case]
            
            #st.dataframe(filtered_change_df, use_container_width=True)
            
            display_df = filtered_change_df.reset_index().rename(columns={'index': 'Original_Pandas_Row_ID'})
            st.dataframe(display_df, use_container_width=True)
            # --- Run comparison ---
            if selected_case == "All":
                # Comparison after all updates
                df_final, comparison_results = analyzer.compare_energy_values(df, tolerance=0.10)
                summary_df = analyzer.build_comparison_summary(df_final, comparison_results)

            else:
                # Comparison after only this case applied
                df_after_case = df.copy()
                # replace rows in df with updated ones from this case
                common_cols = [col for col in df_after_case.columns if col in filtered_change_df.columns]

                # If Row 15 is in here twice, keep only the latest ('last') version of it.
                #Important: This is because of the Bfee restriction condition in data cleaning which causes second update(deletion) for the same index.
                math_ready_change_df = filtered_change_df[~filtered_change_df.index.duplicated(keep='last')]
                
                # 2. Find only the row indices that STILL EXIST in the final dataset
                valid_indices = math_ready_change_df.index.intersection(df_after_case.index)
                
                # 3. Only run the update if there are surviving rows to update!
                if not valid_indices.empty:
                    df_after_case.loc[valid_indices, common_cols] = math_ready_change_df.loc[valid_indices, common_cols]

                df_after_case, comparison_results = analyzer.compare_energy_values(df_after_case, tolerance=0.10)
                summary_df = analyzer.build_comparison_summary(df_after_case, comparison_results)

            
            ##########################################



        # --- Download Buttons ---
        st.subheader("📥 Download Cleaned Data")

        @st.cache_data
        # convert dataframe to csv
        def convert_df_to_csv(df):
            return df.to_csv(index=False).encode("utf-8")

        # Download cleaned data as CSV
        st.download_button("Download Cleaned Data (CSV)", convert_df_to_csv(df), "cleaned_data.csv", "text/csv")

        @st.cache_data
        def convert_df_to_excel(df):
            output = io.BytesIO()
            # Use 'openpyxl' engine which you already installed
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Cleaned Data')
            processed_data = output.getvalue()
            return processed_data
        
        # Excel Button (NEW)
        excel_data = convert_df_to_excel(df)
        st.download_button(
            label="Download Cleaned Data (Excel)",
            data=excel_data,
            file_name="cleaned_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        if not change_df.empty:
            st.download_button("Download Change Log (CSV)", convert_df_to_csv(change_df), "change_log.csv", "text/csv")
        
        fig = analyzer.plot_error_distribution_interactive(df)

        if hasattr(fig, 'show'):  # for plotly figures
            st.plotly_chart(fig, use_container_width=True)
        else:  # fallback to matplotlib figures
            st.pyplot(fig)

        fig2 = analyzer.plot_annual_heat_comparison_by_temp(df)

        # df, comparison_results = WasteHeatAnalyzer.compare_energy_values(df)
        # WasteHeatAnalyzer.display_comparison(df, comparison_results, top_n=20)

        fig3 = analyzer.analyze_numeric_correlations(df)
        # Calculate totals once

        if not violations_df.empty:
            st.warning(f"⚠ Found {len(violations_df)} rows where Annual_Working_Hours exceed the maximum possible.")
            st.dataframe(violations_df) # It looks like the foundations are only for the data which Avg. Daily Availability haven't been provided. (664 rows)
        else:
            st.success("✅ All Annual_Working_Hours are within limits.")


        st.divider()
        st.subheader("🚩 Full Report: Daily Availability > 24h")

        # Filter for the awkward updates
        daily_violations = df[df['Avg_Daily_Availability_h'] > 24].copy()

        if not daily_violations.empty:
            st.error(f"Impossible Daily Limit: {len(daily_violations)} rows detected.")
            
            # Passing the whole dataframe displays all columns
            st.dataframe(daily_violations)
            
            # Optional: Add a download button specifically for these "Error" rows
            # csv = daily_violations.to_csv(index=False).encode('utf-8')
            # st.download_button(
            #     label="Download Physical Violations Only",
            #     data=csv,
            #     file_name="daily_limit_errors.csv",
            #     mime="text/csv",
            # )
        else:
            st.success("✅ No physical daily limit violations found in the cleaned data.")
        # Run classification
        # classifier = WasteHeatClassifier()
        # df_classified = classifier.classify_dataframe(df)
        # df_classified .to_csv("all_classified.csv", index=False)



        # Show results
        # st.subheader("Classified Waste Heat Potentials")
        # st.dataframe(df_classified[["Company_Name", "Waste_Heat_Potential_Name", "label", "confidence"]])
        # st.subheader("Label Distribution")
        # st.table(df_classified["label"].value_counts())
        st.subheader("Baseline Comparison (Before Any Cases Applied)")
        # Run comparison on the original dataset BEFORE cleaning
        df_raw, comparison_results_raw = analyzer.compare_energy_values(fixed_raw_df.copy(), tolerance=0.10)
        summary_raw = analyzer.build_comparison_summary(df_raw, comparison_results_raw)

        st.write("Comparison summary BEFORE applying any cleaning cases:")
        st.table(summary_raw)

        #Show comparison between matched and unmatched values of provided and calculated annual heat amounts.
        df, comparison_results = analyzer.compare_energy_values(df, tolerance=0.10)
        summary_df = analyzer.build_comparison_summary(df, comparison_results)

        # Now you can use this in Streamlit
        st.subheader("Comparing Calculated Annual Energies to Provided Annual Energy (±10% tolerance)")
        st.table(summary_df)

    except Exception as e:
            st.error(f"An error occurred during processing: {e}")

else:
    st.info("Please upload an Excel file to begin the analysis.")
    st.stop()