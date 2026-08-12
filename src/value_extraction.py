"""
value_extraction.py

Purpose: Final stage of the pipeline -- takes the matched header labels
from Header Identification, re-extracts their full rows across ALL
matching statement ranges (not just the first one -- companies with
multiple balance sheet/P&L ranges, like consolidated + unconsolidated
versions, need every range combined), and cleans the raw numeric
strings into actual usable numbers.
"""
import re
import pandas as pd
from rapidfuzz import fuzz
from extract_tables import extract_table_for_range


def is_plausible_value(raw):
    """Checks whether this genuinely looks like a financial value,
    not a note-number (which are small numbers without commas)."""
    if not raw or raw.strip() in ("-", ""):
        return True

    raw = raw.strip()

    # FIX: a small value wrapped in parentheses (e.g. "(475)" for a
    # dividend payment) is unambiguously a real negative financial
    # amount -- note references are never shown in parentheses -- so
    # don't reject it just for having fewer than 4 digits.
    if raw.startswith("(") and raw.endswith(")"):
        return True

    raw = raw.lstrip("(").rstrip(")")

    if "," in raw or "." in raw:
        return True

    digits_only = raw.replace("-", "")
    if digits_only.isdigit() and len(digits_only) < 4:
        return False

    return True


def clean_value(raw):
    """Extracts a clean numeric value from the raw string.
    Handles both complete and incomplete bracket formatting."""
    # NEW: pandas sometimes reads a CSV column as float64 (not string)
    # if it looks numeric enough overall, turning missing cells into
    # NaN (a float) instead of an empty string -- .strip() then crashes
    # since floats don't have that method. Normalize to string first.
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    raw = str(raw)

    if not raw or raw.strip() in ("-", ""):
        return None

    if not is_plausible_value(raw):
        return None

    raw = raw.strip().replace(",", "")

    is_negative = raw.startswith("(")
    raw = raw.lstrip("(").rstrip(")")

    try:
        value = float(raw)
        return -value if is_negative else value
    except ValueError:
        return None


def get_label_variants(row):
    parts = [p.strip() for p in row[:3] if p and p.strip()]
    spaced = " ".join(parts)
    no_space = "".join(parts)
    return list({spaced, no_space})


if __name__ == "__main__":
    matches_df = pd.read_csv("output/header_matches.csv")

    results = []

    for _, match_row in matches_df.iterrows():
        filename = match_row["filename"]
        stype = match_row["statement_type"]
        version = match_row["version"] if "version" in match_row else "unknown"
        raw_label = match_row["raw_label"]
        category = match_row["matched_category"]

        # NEW: use the raw value strings captured DIRECTLY at match
        # time in header_identification.py, instead of re-extracting
        # the table here and searching for a row by label text. That
        # re-search approach broke whenever two rows shared an
        # identical label (e.g. "Long term deposits" on both the
        # Assets side and the Liabilities side) -- it always found the
        # FIRST matching row, silently giving both entries the SAME
        # value even though header_identification.py had correctly told
        # them apart. Using the value recorded at the exact point of
        # matching removes this ambiguity entirely.
        if "raw_value_2025" not in match_row or "raw_value_2024" not in match_row:
            continue  # older header_matches.csv without captured values

        value_2025 = clean_value(match_row["raw_value_2025"])
        value_2024 = clean_value(match_row["raw_value_2024"])

        results.append({
            "filename": filename,
            "statement_type": stype,
            "version": version,
            "category": category,
            "raw_label": raw_label,
            "value_2025": value_2025,
            "value_2024": value_2024,
        })

    results_df = pd.DataFrame(results)

    before_count = len(results_df)
    results_df = results_df[
        results_df["value_2025"].notna() | results_df["value_2024"].notna()
    ]

    # NEW: final safety net -- catches any "#NAME?"/"#REF!"/"#VALUE!"
    # style Excel-error labels that might slip through despite the
    # is_junk_label() check in header_identification.py (e.g. due to
    # hidden unicode whitespace in the extracted text). Belt-and-
    # suspenders: even if the upstream check misses it, we don't want
    # these in the final results.
    results_df = results_df[
        ~results_df["raw_label"].astype(str).str.contains(
            r"#NAME\?|#REF!|#VALUE!", case=False, regex=True, na=False
        )
    ]

    dropped = before_count - len(results_df)

    # NEW (Issue 3): drop exact duplicate rows. Companies whose
    # statements appear twice (Unconsolidated + Consolidated) can have
    # overlapping page ranges, which caused the SAME row -- same
    # filename, category, label, AND both values -- to get captured
    # twice, inflating counts and skewing completeness stats. This only
    # removes true exact duplicates; two genuinely different rows
    # (e.g. real Unconsolidated vs Consolidated figures) are untouched
    # since their values differ.
    before_dedup = len(results_df)
    results_df = results_df.drop_duplicates(
        subset=["filename", "statement_type", "version", "category", "raw_label", "value_2025", "value_2024"]
    )
    duplicates_dropped = before_dedup - len(results_df)

    results_df.to_csv("output/value_extraction_results.csv", index=False)

    both_complete = (results_df["value_2025"].notna() & results_df["value_2024"].notna()).sum()

    print(f"Total rows before junk filtering: {before_count}")
    print(f"Junk rows dropped: {dropped}")
    print(f"Exact duplicate rows dropped: {duplicates_dropped}")
    print(f"Total rows after filtering: {len(results_df)}")
    print(f"Values with valid 2025 number: {results_df['value_2025'].notna().sum()}")
    print(f"Values with valid 2024 number: {results_df['value_2024'].notna().sum()}")
    print(f"Both years complete: {both_complete}")
    print(f"Completeness rate: {both_complete / len(results_df):.2%}" if len(results_df) > 0 else "N/A")
    print("\nSaved: output/value_extraction_results.csv")