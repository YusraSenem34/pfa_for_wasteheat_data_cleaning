import json
import os
import pandas as pd
from openai import OpenAI
from tqdm import tqdm
import time

# --- Groq Configuration ---
API_URL = "https://api.groq.com/openai/v1"
API_KEY = "GrokAPIKey"  
MODEL_NAME = "openai/gpt-oss-20b" 
BATCH_SIZE = 25  
CHECKPOINT_FILE = "data/classification_checkpoint.csv"

CATEGORIES = ["Water", "Exhaust", "Steam", "Air", "Oil", "Refrigerant"]

# --- Initialize Client ---
client = OpenAI(
    api_key=API_KEY,
    base_url=API_URL,
)


def extract_category(raw_val: str) -> str:
    """Validate and clean category string."""
    if not isinstance(raw_val, str):
        return "Unknown"
    for cat in CATEGORIES:
        if cat.lower() in raw_val.lower():
            return cat
    return "Unknown"


def build_system_prompt() -> str:
    categories_str = ", ".join(CATEGORIES)
    return (
        "You are an industrial waste heat classification system.\n"
        "Your task: Classify each waste heat entry into EXACTLY ONE category.\n"
        f"Allowed categories: [{categories_str}].\n"
        "Respond STRICTLY with valid JSON matching this structure:\n"
        '{"results": [{"id": 0, "category": "Water"}, {"id": 1, "category": "Exhaust"}]}'
    )


def classify_batch(batch_df: pd.DataFrame) -> dict:
    """Sends a batch of rows to Ollama and returns a mapping of index -> category."""
    items = []
    for idx, row in batch_df.iterrows():
        items.append(
            {
                "id": idx,
                "name": str(row.get("Waste_Heat_Potential_Name", "")),
                "info": str(
                    row.get("Additional_Info_on_Waste_Heat_Potential", "")
                ),
            }
        )

    user_content = json.dumps(items, ensure_ascii=False)

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {
                    "role": "user",
                    "content": f"Classify the following entries:\n{user_content}",
                },
            ],
            response_format={"type": "json_object"},  # Force JSON output
            temperature=0.0,
        )

        reply_content = response.choices[0].message.content
        parsed = json.loads(reply_content)

        batch_results = {}
        for entry in parsed.get("results", []):
            row_id = entry.get("id")
            cat = extract_category(entry.get("category", ""))
            batch_results[row_id] = cat

        # Fill any dropped IDs with 'Unknown'
        for idx in batch_df.index:
            if idx not in batch_results:
                batch_results[idx] = "Unknown"

        return batch_results

    except Exception as e:
        print(f"\n[Warning] Batch failed ({e}). Falling back to 'Unknown'...")
        return {idx: "Unknown" for idx in batch_df.index}


def run_classification_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """Classifies the dataframe in batches with checkpoint auto-resuming."""
    df_out = df.copy()

    # --- Resume from Checkpoint if exists ---
    if os.path.exists(CHECKPOINT_FILE):
        print(f"Resuming from existing checkpoint: {CHECKPOINT_FILE}")
        checkpoint_df = pd.read_csv(CHECKPOINT_FILE, index_col=0)
        df_out["LLM_Category"] = checkpoint_df["LLM_Category"]
    else:
        if "LLM_Category" not in df_out.columns:
            df_out["LLM_Category"] = None

    # Filter rows that still need classification
    pending_indices = df_out[
        df_out["LLM_Category"].isna() | (df_out["LLM_Category"] == "Unknown")
    ].index
    print(f"Total rows to process: {len(pending_indices)} / {len(df_out)}")

    if len(pending_indices) == 0:
        print("All rows already classified!")
        return df_out

# Process in chunks
    for i in tqdm(
        range(0, len(pending_indices), BATCH_SIZE), desc="Processing Batches"
    ):
        batch_ids = pending_indices[i : i + BATCH_SIZE]
        batch_df = df_out.loc[batch_ids]

        # Classify the batch
        batch_predictions = classify_batch(batch_df)

        # Update dataframe
        for row_id, cat in batch_predictions.items():
            df_out.loc[row_id, "LLM_Category"] = cat

        # Save checkpoint every 5 batches
        if (i // BATCH_SIZE) % 5 == 0:
            df_out[["LLM_Category"]].to_csv(CHECKPOINT_FILE)

        # Force the script to wait 2.5 seconds before asking Groq for the next batch
        time.sleep(2.5)

    # Final checkpoint save
    df_out[["LLM_Category"]].to_csv(CHECKPOINT_FILE)
    print(f"Done! Final output saved to {CHECKPOINT_FILE}")
    return df_out


# --- Test / Execution Block ---
if __name__ == "__main__":
    # Example loading your actual cleaned dataset:
    df = pd.read_csv("data/cleaned_data.csv")

    # Quick test dummy data
    test_df = pd.DataFrame(
        {
            "Waste_Heat_Potential_Name": [
                "Abwärme aus Kesselhaus",
                "Kühlwasserkreislauf",
                "Dampfkondensat",
                "Druckluftkompressor Abluft",
                "Thermalölkreislauf",
                "Kälteanlage Verflüssiger",
            ],
            "Additional_Info_on_Waste_Heat_Potential": [
                "Heißes Abgas",
                "Warmes Wasser 45°C",
                "Dampfentnahme",
                "Warme Luft",
                "Öl 180°C",
                "Kältemittel NH3",
            ],
        }
    )

    result_df = run_classification_pipeline(df)
    print("\n--- Results Sample ---")
    print(result_df[["Waste_Heat_Potential_Name", "LLM_Category"]].head(10))
    result_df.to_csv("data/cleaned_and_classified.csv", index=False)
    print("\nClassification complete! Your final file is saved as 'cleaned_and_classified.csv'.")