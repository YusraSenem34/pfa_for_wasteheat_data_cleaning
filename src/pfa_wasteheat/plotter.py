#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Plotting utilities for energy profiles.
"""

import os
from datetime import datetime
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter

from src.energy_profile_generator.profile import EnergyProfile


def plot_energy_profile(
    energy_profile: EnergyProfile,
    output_dir: str = "src/plots",
    filename: Optional[str] = None,
    waste_heat_record: Optional[object] = None,
) -> str:
    """
    Plot energy profile with time span of a year and month markers.

    This function now creates **two** PNGs per call:
    - one for the time-series diagram
    - one for the waste-heat record table (if a record is provided)

    The return value is the path to the time-series PNG (for backward compatibility).
    """
    os.makedirs(output_dir, exist_ok=True)

    # Get the profile DataFrame
    df = energy_profile._get_profile_df()

    # ------------------------------------------------------------------
    # 1) TIME-SERIES PLOT
    # ------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(20, 8))

    # Plot each column in the profile data
    for column in df.columns:
        # Convert to kW if needed (check if column is in W or kW)
        if " [W]" in column:
            values = df[column] / 1000  # Convert W to kW
            label = column.replace(" [W]", " [kW]")
        elif " [kW]" in column:
            values = df[column]
            label = column
        else:
            # Assume kW if no unit specified
            values = df[column]
            label = f"{column} [kW]"

        # Plot the time series
        ax.plot(df.index, values, label=label, linewidth=1.5)

    # Set x-axis to show full year with month markers
    ax.set_xlim(df.index[0], df.index[-1])

    # Format x-axis to show months
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.xaxis.set_minor_locator(mdates.WeekdayLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    # Automatically adjust label spacing and rotation to prevent overlap
    fig.autofmt_xdate(rotation=45, ha="right")

    # Add vertical lines at the start of each month
    month_starts = [datetime(energy_profile.year, month, 1) for month in range(1, 13)]
    for month_start in month_starts:
        ax.axvline(
            x=month_start, color="gray", linestyle="--", linewidth=0.5, alpha=0.5
        )

    # Set labels and title
    ax.set_xlabel("Time", fontsize=12)
    ax.set_ylabel("Waste Heat (kW)", fontsize=12)

    # Create title with profile information
    title_parts = [
        f"Waste Heat Profile {energy_profile.waste_heat.temperature_c}C ({energy_profile.year})"
    ]
    if energy_profile.company_name:
        title_parts.append(f"Company: {energy_profile.company_name}")
    if energy_profile.description:
        title_parts.append(f"Description: {energy_profile.description}")
    ax.set_title(" | ".join(title_parts), fontsize=14, fontweight="bold")

    # Add legend
    ax.legend(loc="upper right", fontsize=10)

    # Add grid
    ax.grid(True, alpha=0.3, linestyle="-", linewidth=0.5)
    ax.grid(True, which="minor", alpha=0.2, linestyle=":", linewidth=0.5)

    # Format y-axis with German number format if available
    if hasattr(energy_profile, "format_german_number"):
        ax.yaxis.set_major_formatter(
            FuncFormatter(lambda x, p: energy_profile.format_german_number(x))
        )

    # Determine base filename
    if filename is None:
        base_name = (
            f"energy_profile_{energy_profile.nace_code}_{energy_profile.year}.png"
        )
    else:
        base_name = filename

    # Main plot filename/path
    main_filename = base_name
    main_path = os.path.join(output_dir, main_filename)

    # Save main time-series plot
    plt.savefig(main_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Plot (time-series) saved to {main_path}")

    # ------------------------------------------------------------------
    # 2) TABLE PLOT (separate PNG)
    # ------------------------------------------------------------------
    if waste_heat_record is not None:
        fig_table, ax_table = plt.subplots(figsize=(16, 10))
        ax_table.axis("off")

        # Prepare table data from WasteHeatRecord
        table_data = []

        # Basic company information
        table_data.append(
            ["Company Name", getattr(waste_heat_record, "company_name", "N/A")]
        )
        table_data.append(
            ["Site Name", getattr(waste_heat_record, "site_name", "N/A")]
        )
        table_data.append(
            [
                "Street and House Number",
                getattr(waste_heat_record, "street_and_house_number", "N/A") or "N/A",
            ]
        )
        table_data.append(
            [
                "Postal Code",
                str(getattr(waste_heat_record, "postal_code", "N/A"))
                if getattr(waste_heat_record, "postal_code", None) is not None
                else "N/A",
            ]
        )
        table_data.append(["City", getattr(waste_heat_record, "city", "N/A")])
        table_data.append(
            [
                "Waste Heat Potential Name",
                getattr(waste_heat_record, "waste_heat_potential_name", "N/A"),
            ]
        )

        # Energy and power information
        annual_heat = getattr(
            waste_heat_record, "annual_heat_amount_kwh_per_year", None
        )
        if annual_heat is not None:
            formatted = (
                energy_profile.format_german_number(annual_heat)
                if hasattr(energy_profile, "format_german_number")
                else f"{annual_heat:,.2f}"
            )
            table_data.append(["Annual Heat Amount", f"{formatted} kWh/year"])

        max_power = getattr(waste_heat_record, "max_thermal_power_kw", None)
        if max_power is not None:
            formatted = (
                energy_profile.format_german_number(max_power)
                if hasattr(energy_profile, "format_german_number")
                else f"{max_power:,.2f}"
            )
            table_data.append(["Max Thermal Power", f"{formatted} kW"])

        avg_temp = getattr(waste_heat_record, "avg_temperature_level_c_raw", None)
        if avg_temp is not None:
            table_data.append(["Avg Temperature Level", f"{avg_temp} °C"])

        # Temperature and availability
        table_data.append(
            [
                "Temperature Range (Max)",
                f"{getattr(waste_heat_record, 'temperature_c', 'N/A')} °C",
            ]
        )
        table_data.append(
            [
                "Avg Daily Availability",
                f"{getattr(waste_heat_record, 'avg_daily_availability_h', 'N/A')} h",
            ]
        )
        weekend_avail = getattr(
            waste_heat_record, "weekend_availability_raw", "N/A"
        )
        table_data.append(["Weekend Availability", str(weekend_avail)])

        # Monthly power profiles
        months = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        monthly_powers = getattr(waste_heat_record, "monthly_power_kw", [])
        if monthly_powers:
            for month, power in zip(months, monthly_powers):
                formatted = (
                    energy_profile.format_german_number(power)
                    if hasattr(energy_profile, "format_german_number")
                    else f"{power:,.2f}"
                )
                table_data.append([f"Power Profile {month}", f"{formatted} kW"])

        # Additional information
        additional_info = getattr(
            waste_heat_record, "additional_info_on_waste_heat_potential", None
        )
        if additional_info:
            info_str = str(additional_info)
            if len(info_str) > 120:
                info_str = info_str[:117] + "..."
            table_data.append(["Additional Info", info_str])

        # Working hours (from EnergyProfile)
        if energy_profile.waste_heat is not None:
            table_data.append(["Start Time", f"{energy_profile.start_time:02d}:00"])
            table_data.append(["End Time", f"{energy_profile.end_time:02d}:00"])
            table_data.append(
                [
                    "Working Hours per Day",
                    f"{energy_profile.end_time - energy_profile.start_time} h",
                ]
            )
            table_data.append(
                [
                    "Weekdays",
                    ", ".join(
                        [
                            ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d - 1]
                            for d in energy_profile.weekdays
                        ]
                    ),
                ]
            )
            table_data.append(
                [
                    "Weekend Days",
                    ", ".join(
                        [
                            ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d - 1]
                            for d in energy_profile.weekend_days
                        ]
                    )
                    if energy_profile.weekend_days
                    else "None",
                ]
            )

        # Aggregated demands from waste heat profile
        if (
            energy_profile.waste_heat is not None
            and energy_profile.waste_heat.aggregated_demands is not None
        ):
            formatted_demand = (
                energy_profile.format_german_number(
                    energy_profile.waste_heat.aggregated_demands
                )
                if hasattr(energy_profile, "format_german_number")
                else f"{energy_profile.waste_heat.aggregated_demands:,.2f}"
            )
            table_data.append(
                [
                    "Total Annual Waste Heat",
                    f"{formatted_demand} {energy_profile.waste_heat.unit_of_output}",
                ]
            )

        # Other record fields
        annual_working_hours = getattr(
            waste_heat_record, "annual_working_hours", None
        )
        if annual_working_hours is not None:
            table_data.append(["Annual Working Hours", f"{annual_working_hours:.0f} h"])

        avg_thermal_power = getattr(
            waste_heat_record, "avg_thermal_power_kw", None
        )
        if avg_thermal_power is not None:
            formatted = (
                energy_profile.format_german_number(avg_thermal_power)
                if hasattr(energy_profile, "format_german_number")
                else f"{avg_thermal_power:,.2f}"
            )
            table_data.append(["Avg Thermal Power", f"{formatted} kW"])

        logic_correction = getattr(
            waste_heat_record, "logic_of_energy_correction", None
        )
        if logic_correction:
            table_data.append(["Logic of Energy Correction", str(logic_correction)])

        llm_category = getattr(waste_heat_record, "llm_category", None)
        if llm_category:
            table_data.append(["LLM Category", str(llm_category)])

        # Create table
        table = ax_table.table(
            cellText=table_data,
            colLabels=["Parameter", "Value"],
            cellLoc="left",
            loc="center",
            colWidths=[0.35, 0.65],
        )

        # Style the table
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1, 1.6)

        # Style header row
        for i in range(2):
            table[(0, i)].set_facecolor("#40466e")
            table[(0, i)].set_text_props(weight="bold", color="white")

        # Alternate row colors for better readability
        for i in range(1, len(table_data) + 1):
            for j in range(2):
                if i % 2 == 0:
                    table[(i, j)].set_facecolor("#f0f0f0")
                else:
                    table[(i, j)].set_facecolor("white")

        # Set table title
        ax_table.set_title(
            "Waste Heat Record Parameters", fontsize=12, fontweight="bold", pad=20
        )

        fig_table.tight_layout()

        # Derive table filename from main/base name
        if base_name.lower().endswith(".png"):
            name_no_ext = base_name[:-4]
        else:
            name_no_ext = base_name
        table_filename = f"{name_no_ext}_table.png"
        table_path = os.path.join(output_dir, table_filename)

        fig_table.savefig(table_path, dpi=300, bbox_inches="tight")
        plt.close(fig_table)
        print(f"Plot (table) saved to {table_path}")

    # Return path to main time-series plot (backward compatible)
    return main_path
