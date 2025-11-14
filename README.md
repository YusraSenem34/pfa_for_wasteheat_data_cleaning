# PFA Waste Heat Data Cleaning

A Python-based data analysis pipeline for cleaning, processing, and analyzing waste heat potential data from industrial facilities in Germany. This project is part of the DLR (Deutsches Zentrum für Luft- und Raumfahrt) energy profile research initiative.

## Description

This project provides a comprehensive pipeline for processing waste heat data from industrial sites. It includes:

- **Data Cleaning**: Automated cleaning of textual and numerical data from Excel datasets
- **Energy Calculations**: Computation of energy metrics based on temperature, flow rate, and operating hours
- **Geocoding**: Integration with geopy to geocode facility addresses and obtain coordinates
- **Waste Heat Classification**: Automated categorization of waste heat sources using LLM (Blablador) and manual rule-based approaches
- **Data Validation**: Sanity checks and consistency validation throughout the pipeline

The pipeline processes data from the "Abwärmepotentiale" (Waste Heat Potential) dataset, which contains information about industrial facilities including company names, locations, waste heat sources, temperatures, and flow rates.

## Features

- Clean and standardize column names and text data
- Calculate energy values from temperature, flow rate, and operating hours
- Geocode facility addresses to obtain latitude and longitude coordinates
- Classify waste heat types (Water, Exhaust, Steam, Air, Oil) using AI
- Generate detailed change logs and warnings for data modifications
- Export processed data to Excel files for further analysis

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)
- Git (optional, for cloning the repository)

### Verify Python Installation

Before starting, verify that Python is installed on your system:

**Windows:**
```bash
python --version
```

**Linux/macOS:**
```bash
python3 --version
```

If Python is not installed, download it from [python.org](https://www.python.org/downloads/) or use your system's package manager.

### Setting Up a Virtual Environment

#### Windows (PowerShell/Command Prompt):

```bash
# Navigate to the project directory
cd pfa_wasteheat_data_cleaning

# Create a virtual environment
python -m venv venv

# Activate the virtual environment (PowerShell)
venv\Scripts\Activate
```

**Note for Windows users:** If you encounter an execution policy error in PowerShell, run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### Linux:

```bash
# Navigate to the project directory
cd pfa_wasteheat_data_cleaning

# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate
```

**Note for Linux users:** If `python3-venv` is not installed, install it first:
```bash
# For Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3-venv

# For Fedora/RHEL
sudo dnf install python3-venv

# For Arch Linux
sudo pacman -S python
```

#### macOS:

```bash
# Navigate to the project directory
cd pfa_wasteheat_data_cleaning

# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate
```

**Note for macOS users:** If you don't have Python 3, install it using Homebrew:
```bash
brew install python3
```

### Installing Dependencies

Once your virtual environment is activated (you should see `(venv)` in your terminal prompt), install all required packages:

**All platforms:**
```bash
pip install -r requirements.txt
```

### Deactivating the Virtual Environment

When you're done working, you can deactivate the virtual environment:

**All platforms:**
```bash
deactivate
```

### Required Dependencies

The project uses the following Python packages:

- `pandas` - Data manipulation and analysis
- `numpy` - Numerical computing
- `openpyxl` - Excel file reading and writing
- `geopy` - Geocoding and location services
- `openai` - LLM integration for waste heat classification

## Usage

### Running the Main Pipeline

To run the complete waste heat analysis pipeline:

```python
python src/pfa_wasteheat/main.py
```

### Using Individual Components

You can also import and use individual components in your own scripts:

```python
from pfa_wasteheat.data_cleaning import DataCleaner
from pfa_wasteheat.energy_calculations import EnergyCalculator
from pfa_wasteheat.wasteheat_analyzer import WasteHeatAnalyzer

# Initialize components
cleaner = DataCleaner()
calculator = EnergyCalculator()

# Use them in your workflow
df_cleaned = cleaner.clean_column_names(df)
df_with_energy = calculator.add_energy_columns(df_cleaned)
```

### Input Data Format

The pipeline expects an Excel file with a sheet named "Abwärmepotentiale" containing columns for:
- Company information (name, location)
- Address data (street, postal code, city)
- Waste heat source details
- Temperature and flow rate measurements
- Operating hours

## Project Structure

```
pfa_wasteheat_data_cleaning/
├── src/
│   └── pfa_wasteheat/
│       ├── __init__.py
│       ├── main.py                          # Main pipeline orchestrator
│       ├── data_cleaning.py                 # Data cleaning operations
│       ├── energy_calculations.py           # Energy metric calculations
│       ├── wasteheat_analyzer.py           # Waste heat analysis
│       ├── categorization_of_wasteheat.py  # LLM-based classification
│       ├── geocode.py                       # Geocoding utilities
│       ├── utils.py                         # Helper functions
│       ├── app.py                           # Application interface
│       └── app2.py                          # Alternative interface
├── requirements.txt                         # Project dependencies
└── README.md                               # This file
```

## Authors and Acknowledgment

- **Yusra Senem** (yuesra.senem@dlr.de) - Primary Developer
- **DLR (Deutsches Zentrum für Luft- und Raumfahrt)** - Project Sponsor

## License

This project is licensed under the MIT License.

## Project Status

Active development. The project is currently being used for waste heat potential analysis in German industrial facilities.
