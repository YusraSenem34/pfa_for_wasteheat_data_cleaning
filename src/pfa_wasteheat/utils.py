
from wasteheat_analyzer import*
from energy_calculations import*


def sanity_check(df):
    # Capture validation results from cleaner if available
    df_steps, comparison_results = WasteHeatAnalyzer.compare_energy_values(df, tolerance=0.10)
    summary_df = WasteHeatAnalyzer.build_comparison_summary(df_steps, comparison_results)
    print("The Shape of the dataframe: ")
    print(df.shape)
    # print("Comparison results: ")
    # print(comparison_results)
    print("Total Energy Comparisons: ")
    print(summary_df)

def check_working_hours_limits(df, tolerance=0.05):
    """
    Check if Annual_Working_Hours exceeds allowed maximum based on daily and weekend availability.
    Weekend_Availability should be boolean: True = works weekends, False = no weekends.
    """
    # Determine number of days per year
    df['Days_Per_Year'] = df['Weekend_Availability'].apply(lambda x: 365 if x else 261)

    # Calculate max possible annual working hours
    df['Max_Possible_Working_Hours'] = df['Avg_Daily_Availability_h'] * df['Days_Per_Year']

    # Only check rows where Annual_Working_Hours is not NaN
    mask_not_empty = df['Annual_Working_Hours'].notna()

    # Find violations
    violations = df[mask_not_empty & (df['Annual_Working_Hours'] > (df['Max_Possible_Working_Hours'] * (1 + tolerance)))]

    return violations