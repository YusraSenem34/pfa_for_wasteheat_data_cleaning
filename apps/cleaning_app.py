"""Streamlit app: run the cleaning pipeline and explore flags and quality tiers.

    streamlit run apps/cleaning_app.py
"""

import io
from dataclasses import replace

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from pfa_wasteheat import columns as C
from pfa_wasteheat.config import load_config
from pfa_wasteheat.loading import read_raw_excel
from pfa_wasteheat.pipeline import run
from pfa_wasteheat.reporting import FLAG_COLUMNS, summarize

st.set_page_config(page_title="Waste Heat Data Cleaning", layout="wide")
st.title("Waste heat data cleaning and quality flags")

cfg = load_config()

with st.sidebar:
    st.header("Input")
    uploaded = st.file_uploader("PfA export (.xlsx)", type=["xlsx"])
    st.caption(f"Without upload: `{cfg.paths.raw_file.name}`")
    st.header("Settings")
    tol = st.slider("Consistency tolerance", 0.01, 0.30, cfg.consistency.tolerance, 0.01)
    strategy = st.radio("When nothing fits", ["trust_annual", "trust_profile"],
                        index=["trust_annual", "trust_profile"].index(cfg.consistency.unmatched_strategy))

cfg = replace(cfg, consistency=replace(cfg.consistency, tolerance=tol, unmatched_strategy=strategy))


@st.cache_data(show_spinner="Running pipeline ...")
def cached_run(file_bytes, tolerance, unmatched_strategy):
    raw = read_raw_excel(io.BytesIO(file_bytes) if file_bytes else cfg.paths.raw_file, cfg.paths.raw_sheet)
    return run(cfg, raw=raw)


df = cached_run(uploaded.getvalue() if uploaded else None, tol, strategy)
tables = summarize(df)

# --- Overview ---
cols = st.columns(4)
for col, tier in zip(cols, ["A", "B", "C", "D"]):
    n = int((df["quality_tier"] == tier).sum())
    col.metric(f"Tier {tier}", f"{n:,}", f"{100 * n / len(df):.1f} % of rows", delta_color="off")

left, right = st.columns(2)
with left:
    st.subheader("Quality tiers")
    st.dataframe(tables["quality_tiers"], hide_index=True)
    st.subheader("Consistency status")
    st.dataframe(tables["consistency_status"], hide_index=True)
    st.subheader("Best reading of the monthly columns (matched rows)")
    st.dataframe(tables["best_interpretation"], hide_index=True)
with right:
    st.subheader("Flags")
    st.dataframe(tables["flags"], hide_index=True, height=420)
    st.subheader("Rescale factors (rows where nothing fit)")
    st.dataframe(tables["rescale_factors"], hide_index=True)

# --- Agreement plot ---
st.subheader("Reported vs. recalculated annual energy (best reading)")
plot_df = df.loc[df["interp_ratio"].notna(), [C.ROW_ID, C.COMPANY, "interp_best", "interp_ratio"]].copy()
plot_df["log10_ratio"] = np.log10(plot_df["interp_ratio"])
fig = px.histogram(plot_df, x="log10_ratio", color="interp_best", nbins=120,
                   labels={"log10_ratio": "log10(reported / recalculated)"})
for x in (np.log10(1 - tol), np.log10(1 + tol)):
    fig.add_vline(x=x, line_dash="dash", line_color="gray")
st.plotly_chart(fig, width="stretch")

# --- Row explorer ---
st.subheader("Rows")
c1, c2 = st.columns(2)
tiers = c1.multiselect("Quality tier", ["A", "B", "C", "D"], default=["A", "B", "C", "D"])
flag = c2.selectbox("Only rows with flag", ["(none)"] + [f for f in FLAG_COLUMNS if f in df.columns])
view = df[df["quality_tier"].isin(tiers)]
if flag != "(none)":
    view = view[view[flag].fillna(False)]
st.caption(f"{len(view):,} rows")
st.dataframe(view, width="stretch", hide_index=True)


@st.cache_data
def to_excel(frame: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    frame.to_excel(buf, index=False)
    return buf.getvalue()


st.download_button("Download shown rows (Excel)", to_excel(view), "pfa_cleaned_selection.xlsx")
st.download_button("Download all rows (CSV)", df.to_csv(index=False).encode("utf-8"), "pfa_cleaned.csv")
