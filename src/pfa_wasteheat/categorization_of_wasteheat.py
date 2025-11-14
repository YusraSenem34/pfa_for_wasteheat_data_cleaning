#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File           : categorization_of_wasteheat.py
# License        : License: MIT
# Author         : Yusra Senem yuesra.senem@dlr.de
# Date           : 31.10.2025

import pandas as pd
from openai import OpenAI  # Use the standard OpenAI client

# --- LLM API Configuration ---
API_KEY = "glpat-9HcHBOoCcyM5FDVRDu91cm86MQp1Om12awk.01.0z1wq3pul"
API_URL = "https://api.helmholtz-blablador.fz-juelich.de/v1"
MODEL_NAME = "alias-large"

# --- Define your categories ---
CATEGORIES = ["Water", "Exhaust", "Steam", "Air", "Oil"]

# --- 1. Helper Function to Extract Category ---
# We need this again because we are not using pydantic-ai
def extract_category(reply_text: str) -> str:
    """
    Attempts to find one of the predefined categories in the LLM's reply.
    Returns the first category found or 'Unknown'.
    """
    if not isinstance(reply_text, str):
        return "Invalid Response"
        
    reply_lower = reply_text.lower()
    for category in CATEGORIES:
        if category.lower() in reply_lower:
            return category
    return "Unknown" # If no category keyword is found

# --- 2. Configure the Client ---
# Create an OpenAI client instance pointed at the Blablador API
client = OpenAI(
    api_key=API_KEY,
    base_url=API_URL,
)

# --- 3. Main Categorization Function ---
def categorize_waste_heat_sample(df_sample: pd.DataFrame) -> dict:
    """
    Calls an LLM API to categorize waste heat sources using the OpenAI client.
    """
    results_dict = {}
    print(f"Starting categorization for {len(df_sample)} rows...")

    for index, row in df_sample.iterrows():
        col1_text = str(row.get('Waste_Heat_Potential_Name', ''))
        col2_text = str(row.get('Additional_Info_on_Waste_Heat_Potential', ''))

        user_content = (
            f"Waste_Heat_Potential_Name: '{col1_text}'\n"
            f"Additional_Info_on_Waste_Heat_Potential: '{col2_text}'"
        )
        
        system_prompt = (
            "You are an expert in industrial processes and waste heat. "
            "Your task is to categorize the source of waste heat based on the input. "
            "Output ONLY one of the following five categories: Water, Exhaust, Steam, Air, Oil. "
            "Do not add any other words or explanation."
        )

        try:
            # --- 4. Make the direct API call ---
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                max_tokens=20,  # We only need one word
                temperature=0.0   # We want the most likely, non-creative answer
            )
            
            # --- 5. Extract and Store the Result ---
            reply = response.choices[0].message.content
            category = extract_category(reply)
            results_dict[index] = category 

        except Exception as e:
            # Catches API errors, timeouts, etc.
            print(f"Error processing row index {index}: {e}")
            results_dict[index] = "Error"

    print(f"Categorization finished. Processed {len(results_dict)} rows.")
    return results_dict

# --- Test Block ---
if __name__ == "__main__":
    print("Testing categorization file...")
    test_data = {
        "Waste_Heat_Potential_Name": ["Abwärme aus Kesselhaus", "Kühlwasserkreislauf"],
        "Additional_Info_on_Waste_Heat_Potential": ["Heißes Abgas", "Warmes Wasser"]
    }
    df_test_sample = pd.DataFrame(test_data)
    results = categorize_waste_heat_sample(df_test_sample)
    
    print("\n--- Test Results ---")
    print(results)
    
    df_test_sample['LLM_Category'] = df_test_sample.index.map(results)
    print(df_test_sample)





























#-----Waste Heat Classification using Manual Rules -----
# import re
# import pandas as pd
# class WasteHeatClassifier:
#     """
#     Classify waste heat sources into categories:
#     - air
#     - exhaust
#     - water

#     Uses rule-based keyword matching on 'Waste_Heat_Potential_Name'
#     and 'Additional_Notes'.
#     """

#     CATEGORIES = ["air", "exhaust", "water", "Steam", "Oil"]

#     # Define keyword rules per class
#     RULES = {
#         "air": [
#             r"luft", r"abluft", r"betriebsabluft", r"kompressoren",
#             r"ventilation", r"gebläse"
#         ],
#         "exhaust": [
#             r"abgas", r"kamin", r"ofen", r"dampfkessel", r"schornstein"
#         ],
#         "water": [
#             r"wasser", r"abwasser", r"kühlwasser", r"blutwasser", r"kläranlage"
#         ],
#         "steam": [
#         r"dampf",                # steam in general
#         r"sattdampf",            # saturated steam
#         r"autoklav",             # autoclave steam systems
#         r"hochdruckdampf",       # high-pressure steam
#         r"niederdruckdampf",     # low-pressure steam
#         r"restdampf",            # residual steam
#         r"kondensat",            # steam condensate
#     ],
#     "oil": [
#         r"öl",                   # general oil
#         r"thermoöl",             # thermal oil systems
#         r"thermalöl",            # spelling variant
#         r"fett",                 # fat/oil (e.g. frying)
#         r"trafo",                # transformer (oil-cooled)
#         r"fettback",             # deep-fat fryer (oil-heated)
#     ],
#     }

#     def __init__(self):
#         self.log = []  # keep classification history

#     def classify_text(self, text: str) -> tuple[str, float, str]:
#         """
#         Classify a single string into one of the categories.

#         Returns:
#             (label, confidence, reason)
#         """
#         if not isinstance(text, str) or text.strip() == "":
#             return ("unknown", 0.0, "empty or non-text")

#         text_lower = text.lower()
#         matches = []

#         for label, patterns in self.RULES.items():
#             for pat in patterns:
#                 if re.search(pat, text_lower):
#                     matches.append((label, pat))

#         if not matches:
#             return ("unknown", 0.0, "no rule matched")

#         # If multiple matches, pick the first but log all
#         chosen_label, chosen_pat = matches[0]
#         reason = f"matched: {', '.join([f'{lbl}:{pat}' for lbl, pat in matches])}"
#         confidence = 1.0 if len(matches) == 1 else 0.7  # lower if ambiguous

#         return (chosen_label, confidence, reason)

#     def classify_row(self, row: pd.Series) -> dict:
#         """
#         Classify a row using both Waste_Heat_Potential_Name and Additional_Notes.
#         """
#         texts = [
#             str(row.get("Waste_Heat_Potential_Name", "")),
#             str(row.get("Additional_Info_on_Waste_Heat_Potential", "")),
#         ]

#         # Collect results from both columns
#         results = [self.classify_text(t) for t in texts if t.strip()]

#         if not results:
#             return {"label": "unknown", "confidence": 0.0, "reason": "no text available"}

#         # Take the result with highest confidence
#         best = max(results, key=lambda x: x[1])

#         # Log for later inspection
#         self.log.append({"row_id": row.name, **dict(zip(["label","confidence","reason"], best))})

#         return {"label": best[0], "confidence": best[1], "reason": best[2]}

#     def classify_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
#         """
#         Add classification columns to a DataFrame.
#         """
#         results = df.apply(self.classify_row, axis=1, result_type="expand")
#         return df.join(results)

