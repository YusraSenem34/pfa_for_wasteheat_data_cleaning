"""Column names used throughout the pipeline (single source of truth)."""

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# ---- Raw columns (as reported, English names). These are NEVER modified after loading. ----
COMPANY = "Company_Name"
SITE = "Site_Name"
STREET = "Street_and_House_Number"
POSTAL_CODE = "Postal_Code"
CITY = "City"
SOURCE_NAME = "Waste_Heat_Potential_Name"
ANNUAL_KWH = "Annual_Heat_Amount_kWh_per_Year"
MAX_POWER_KW = "Max_Thermal_Power_kW"
TEMP_C = "Avg_Temperature_Level_C"
TEMP_RANGE = "Temperature_Range"
DAILY_HOURS = "Avg_Daily_Availability_h"
WEEKEND = "Weekend_Availability"
AVAILABILITY = "Availability"
PREDICTABILITY = "Availability_Predictability"
CONTROL_OPTIONS = "Existing_Control_Options"
INFO = "Additional_Info_on_Waste_Heat_Potential"
POWER_COLS = [f"Power_Profile_{m}_kW" for m in MONTHS]

# ---- Identifiers added by the pipeline ----
ROW_ID = "row_id"                 # stable id = position in the raw file (0-based)
EXCEL_ROW = "Original_Excel_Row"  # row number as seen in Excel
COMPANY_ID = "company_id"
SITE_ID = "site_id"

# ---- Cleaned values (new columns; raw columns stay untouched) ----
ANNUAL_KWH_CLEAN = "annual_kwh_clean"
MAX_POWER_KW_CLEAN = "max_power_kw_clean"
DAILY_HOURS_CLEAN = "daily_hours_clean"
ANNUAL_HOURS_CLEAN = "annual_operating_hours_clean"
ENERGY_COLS_CLEAN = [f"energy_{m}_kwh_clean" for m in MONTHS]  # monthly ENERGY (kWh), not power
SHARE_COLS_CLEAN = [f"share_{m}" for m in MONTHS]              # monthly energy / annual energy
