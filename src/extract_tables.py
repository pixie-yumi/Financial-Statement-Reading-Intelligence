import re
import pdfplumber
import fitz  # PyMuPDF
import pandas as pd
from extract_st_id import extract_pages
from extract_by_position import extract_rows_by_position_for_range, extract_rows_by_position


def is_text_garbled(text, threshold=0.3):
    if not text:
        return False
    cid_matches = text.count("(cid:")
    total_words = len(text.split())
    if total_words == 0:
        return False
    return (cid_matches / total_words) > threshold


def _patch_missing_values(tables, pdf_path, page_num, force_split=None):
    """NEW: on pages with TWO STATEMENTS printed side-by-side as
    columns (e.g. Consolidated Balance Sheet + Income Statement on one
    page), pdfplumber's native table detection can get confused by the
    dual-column grid and produce rows where the LABEL comes through
    fine (e.g. "Total Assets") but the numeric value cells come back
    completely empty -- even though the real numbers ARE there on the
    page at a valid position. This silently made every subtotal/total
    line "not found" downstream.

    Fix: for any row with a label but no values, look up that same
    label via the position-based extractor (which reads word
    coordinates directly, unaffected by pdfplumber's grid confusion)
    and patch the missing values in from there."""
    position_rows = None  # lazy-computed only if actually needed

    for table in tables:
        for row in table:
            if len(row) < 6:
                continue
            label = str(row[2]).strip() if row[2] else ""
            has_values = bool(str(row[4]).strip()) or bool(str(row[5]).strip())
            if not label or has_values:
                continue

            if position_rows is None:
                position_rows = extract_rows_by_position(pdf_path, page_num, force_split=force_split)

            for prow in position_rows:
                if len(prow) < 6:
                    continue
                if str(prow[2]).strip().lower() == label.lower():
                    row[4] = prow[4]
                    row[5] = prow[5]
                    break

    return tables


def extract_table_from_page(pdf_path, page_num, force_split=None):
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]
        tables = page.extract_tables()

        if tables and all(len(row) <= 1 for row in tables[0]):
            custom_settings = {
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
            }
            tables = page.extract_tables(table_settings=custom_settings)

        if not tables or all(len(row) <= 1 for row in (tables[0] if tables else [])):
            raw_text = page.extract_text() or ""
            if is_text_garbled(raw_text):
                return None, "garbled_font"

        if tables:
            tables = _patch_missing_values(tables, pdf_path, page_num, force_split=force_split)

        return tables, "ok"


def extract_table_for_range(pdf_path, start_page, end_page, multi_type=None):
    """multi_type: pass True/False when known (from
    output_page_ranges_v2.csv's "multi_type" column) to reliably tell
    the position-based fallback whether this range's pages genuinely
    have two statements sharing space -- avoiding a purely geometric
    guess that can't tell that case apart from a single statement whose
    own sections are just laid out in two visual columns.

    FIX: this used to try pdfplumber's NATIVE table detection first,
    only falling back to position-based extraction if a quality check
    caught obvious corruption. But pdfplumber's native table detection
    depends on precise character-positioning/font-metric data that can
    genuinely differ across platforms (Windows vs Linux) even with the
    identical pdfplumber version installed -- due to underlying
    font-rendering library differences -- occasionally producing
    corrupted column-splits on one machine that never showed up during
    testing on another. Position-based extraction (extract_by_position.py)
    works directly from word coordinates instead of pdfplumber's table
    grid algorithm, and has proven completely reliable and deterministic
    throughout this whole project -- so we now use it always, skipping
    native table detection (and its platform-dependent quality-check
    fallback) entirely."""
    all_rows = extract_rows_by_position_for_range(pdf_path, start_page, end_page, force_split=multi_type)
    if all_rows:
        return all_rows, "ok"
    return [], "no_rows_extracted"


def check_rotation(pdf_path, page_num):
    doc = fitz.open(pdf_path)
    page = doc[int(page_num)]
    return page.rotation


if __name__ == "__main__":
    ranges_df = pd.read_csv("output/output_page_ranges_v2.csv")
    statement_types = ["balance_sheet", "profit_and_loss", "cash_flow", "changes_in_equity"]
    summary = []

    for filename in ranges_df["filename"].unique():
        company_ranges = ranges_df[
            (ranges_df["filename"] == filename) &
            (ranges_df["type"].isin(statement_types))
        ]

        for _, row in company_ranges.iterrows():
            pdf_path = f"data/{filename}"
            try:
                rotation = check_rotation(pdf_path, row["start_page"])
                table, reason = extract_table_for_range(pdf_path, row["start_page"], row["end_page"])
                good_rows = sum(1 for r in table if len(r) >= 2)
                total_rows = len(table)

                if reason == "garbled_font":
                    status = "PROBLEM - garbled text (font encoding)"
                elif total_rows == 0:
                    status = "PROBLEM - no table found"
                elif good_rows == 0:
                    status = "PROBLEM - columns not separated"
                else:
                    status = "OK"

                summary.append({
                    "filename": filename, "type": row["type"],
                    "pages": f"{row['start_page']}-{row['end_page']}",
                    "rotation": rotation, "total_rows": total_rows,
                    "good_rows": good_rows, "status": status
                })
            except Exception as e:
                summary.append({
                    "filename": filename, "type": row["type"],
                    "pages": f"{row['start_page']}-{row['end_page']}",
                    "rotation": "ERROR", "total_rows": 0, "good_rows": 0,
                    "status": f"ERROR: {str(e)[:50]}"
                })

    summary_df = pd.DataFrame(summary)
    summary_df.to_csv("output/table_extraction_summary.csv", index=False)
    print(f"\nTotal ranges tested: {len(summary_df)}")
    print(f"OK: {(summary_df['status'] == 'OK').sum()}")
    print("\n=== Problem Breakdown ===")
    print(summary_df[summary_df["status"] != "OK"]["status"].value_counts())