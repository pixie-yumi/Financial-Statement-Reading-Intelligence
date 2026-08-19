"""
dashboard.py

Purpose: A click-through Streamlit UI on top of FinSight's existing
pipeline outputs. Flow: pick company -> pick version -> pick statement
-> type a line item -> get the value. Reuses query_engine.py's
existing functions, no duplicated logic.
"""
import sys
import os
import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(__file__))

from query_engine import load_results, query, RANGES_PATH, STATEMENT_TYPES


st.set_page_config(page_title="FinSight Dashboard", layout="wide")

st.title("FinSight")
st.caption("Financial Statement Reading Intelligence -- SBP internship project")

results_df = load_results()

if results_df.empty:
    st.error("No processed data found. Run the main pipeline first.")
    st.stop()

try:
    ranges_df = pd.read_csv(RANGES_PATH)
except Exception:
    ranges_df = pd.DataFrame(columns=["filename", "version", "type"])

if "company" not in st.session_state:
    st.session_state.company = None
if "version" not in st.session_state:
    st.session_state.version = None
if "stype" not in st.session_state:
    st.session_state.stype = None


def reset_from(step):
    if step in ("company", "all"):
        st.session_state.company = None
        st.session_state.version = None
        st.session_state.stype = None
    elif step == "version":
        st.session_state.version = None
        st.session_state.stype = None
    elif step == "stype":
        st.session_state.stype = None


crumb_parts = []
if st.session_state.company:
    crumb_parts.append(st.session_state.company.replace(".pdf", ""))
if st.session_state.version:
    crumb_parts.append(st.session_state.version.title())
if st.session_state.stype:
    crumb_parts.append(st.session_state.stype.replace("_", " ").title())

if crumb_parts:
    col_crumb, col_reset = st.columns([5, 1])
    with col_crumb:
        st.markdown("**" + " -> ".join(crumb_parts) + "**")
    with col_reset:
        if st.button("Start over"):
            reset_from("all")
            st.rerun()

st.divider()

if not st.session_state.company:
    st.subheader("Pick a company")
    companies = sorted(results_df["filename"].unique())

    cols = st.columns(3)
    for i, company in enumerate(companies):
        display_name = company.replace(".pdf", "")
        with cols[i % 3]:
            if st.button(display_name, key=f"company_{i}", use_container_width=True):
                st.session_state.company = company
                st.rerun()

elif not st.session_state.version:
    company = st.session_state.company
    company_ranges = ranges_df[ranges_df["filename"].str.contains(
        company.replace(".pdf", ""), case=False, na=False
    )]
    available_versions = sorted(set(company_ranges["version"].unique())) if not company_ranges.empty else ["unknown"]

    if available_versions == ["unknown"] or not available_versions:
        st.session_state.version = "unknown"
        st.rerun()
    else:
        st.subheader("Consolidated or Unconsolidated?")
        cols = st.columns(len(available_versions))
        for i, v in enumerate(available_versions):
            with cols[i]:
                if st.button(v.title(), key=f"version_{i}", use_container_width=True):
                    st.session_state.version = v
                    st.rerun()

elif not st.session_state.stype:
    company = st.session_state.company
    version = st.session_state.version

    company_ranges = ranges_df[ranges_df["filename"].str.contains(
        company.replace(".pdf", ""), case=False, na=False
    )]
    if version != "unknown":
        version_filtered = company_ranges[company_ranges["version"] == version]
        if not version_filtered.empty:
            company_ranges = version_filtered

    available_types = sorted(set(
        company_ranges[company_ranges["type"].isin(STATEMENT_TYPES)]["type"].unique()
    ))

    if not available_types:
        st.warning("No statements found for this company/version.")
        if st.button("Go back"):
            reset_from("version")
            st.rerun()
    else:
        st.subheader("Pick a statement")
        cols = st.columns(len(available_types))
        for i, t in enumerate(available_types):
            with cols[i]:
                if st.button(t.replace("_", " ").title(), key=f"stype_{i}", use_container_width=True):
                    st.session_state.stype = t
                    st.rerun()

else:
    company = st.session_state.company
    version = st.session_state.version
    stype = st.session_state.stype

    st.subheader("What line item do you want?")
    line_item = st.text_input("e.g. revenue, trade receivables, total assets", key="line_item_input")

    if st.button("Get value") and line_item.strip():
        result = query(
            company.replace(".pdf", ""), "2025", line_item, results_df,
            version=version if version != "unknown" else None, stype=stype
        )
        if not result["found"]:
            result = query(
                company.replace(".pdf", ""), "2024", line_item, results_df,
                version=version if version != "unknown" else None, stype=stype
            )

        if result["found"]:
            st.success(f"**{result['raw_label']}**  ({result['category']})")
            col_a, col_b = st.columns(2)

            row_match = results_df[
                (results_df["filename"] == result["company"]) &
                (results_df["category"] == result["category"]) &
                (results_df["statement_type"] == result["statement_type"])
            ]
            if not row_match.empty:
                row = row_match.iloc[0]
                with col_a:
                    st.metric("2025", f"{row['value_2025']:,.0f}" if pd.notna(row["value_2025"]) else "--")
                with col_b:
                    st.metric("2024", f"{row['value_2024']:,.0f}" if pd.notna(row["value_2024"]) else "--")

            st.caption(f"Match confidence: {result['match_confidence']}%")
        else:
            st.error(result["message"])

    if st.button("Ask about a different statement"):
        reset_from("stype")
        st.rerun()