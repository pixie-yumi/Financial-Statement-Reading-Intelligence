"""
verify_extraction_consistency.py

Purpose: Automated consistency check — re-extracts raw table cells for
every row in value_extraction_results.csv and re-applies clean_value(),
confirming the pipeline reproduces the same results reliably. This
validates internal consistency (no silent bugs), not ground-truth
correctness against the source PDF — that requires manual verification
(done separately for Attock Cement and Nishat, both 100% match).
"""
import pandas as pd
from extract_tables import extract_table_for_range
from value_extraction import clean_value, get_label_variants


def verify_all():
    from version_filter import filter_to_consolidated

    results_df = pd.read_csv("output/value_extraction_results.csv")
    ranges_df = pd.read_csv("output/output_page_ranges_v2.csv")
    ranges_df = filter_to_consolidated(ranges_df)

    company_tables = {}
    matches = 0
    mismatches = 0
    mismatch_details = []

    for _, row in results_df.iterrows():
        filename = row["filename"]
        stype = row["statement_type"]
        raw_label = row["raw_label"]

        cache_key = (filename, stype)
        if cache_key not in company_tables:
            # FIX: companies whose statements appear in MULTIPLE ranges
            # (e.g. Unconsolidated + Consolidated versions) were only
            # having their FIRST range re-extracted here (via
            # range_row.iloc[0]), while value_extraction.py correctly
            # combines ALL matching ranges into one table. Any row that
            # came from the second/third range was then reported as
            # "row not found on re-extraction" -- a false alarm from
            # this verification script itself, not a real pipeline bug.
            matching_ranges = ranges_df[
                (ranges_df["filename"] == filename) &
                (ranges_df["type"] == stype)
            ]
            if matching_ranges.empty:
                company_tables[cache_key] = []
                continue

            combined_table = []
            pdf_path = f"data/{filename}"
            for _, range_row in matching_ranges.iterrows():
                table, reason = extract_table_for_range(pdf_path, range_row["start_page"], range_row["end_page"])
                if reason == "ok" and table:
                    combined_table.extend(table)

            company_tables[cache_key] = combined_table

        table = company_tables[cache_key]

        # FIX: labels like "Long term deposits" (asset side AND
        # liability side), "Deferred taxation" (balance sheet AND a
        # note breakdown), or "Equity holders of the parent" (Statement
        # of Changes in Equity AND the P&L profit-attribution section)
        # genuinely appear MORE THAN ONCE in a real financial statement
        # with different values each time. header_identification.py
        # correctly told these apart using exact page position when it
        # first captured the value -- but re-searching here by label
        # text alone can't tell which occurrence is "the" one, so
        # grabbing only the FIRST match risked comparing against the
        # WRONG occurrence and reporting a false mismatch. Instead,
        # collect every row with a matching label and accept the check
        # as consistent if the original value matches ANY of them.
        candidate_rows = [
            r for r in table
            if len(r) >= 6 and raw_label in get_label_variants(r)
        ]

        if not candidate_rows:
            mismatches += 1
            mismatch_details.append((filename, raw_label, "row not found on re-extraction"))
            continue

        original_2025 = row["value_2025"] if pd.notna(row["value_2025"]) else None
        original_2024 = row["value_2024"] if pd.notna(row["value_2024"]) else None

        found_exact_match = False
        best_attempt = None
        for r in candidate_rows:
            recheck_2025 = clean_value(r[4] if len(r) > 4 else None)
            recheck_2024 = clean_value(r[5] if len(r) > 5 else None)
            if recheck_2025 == original_2025 and recheck_2024 == original_2024:
                found_exact_match = True
                break
            if best_attempt is None:
                best_attempt = (recheck_2025, recheck_2024)

        if found_exact_match:
            matches += 1
        else:
            mismatches += 1
            recheck_2025, recheck_2024 = best_attempt
            mismatch_details.append((filename, raw_label, f"got {recheck_2025}/{recheck_2024}, expected {original_2025}/{original_2024}"))

    total = matches + mismatches
    print(f"Total rows checked: {total}")
    print(f"Consistent (reproducible): {matches}")
    print(f"Inconsistent: {mismatches}")
    print(f"Consistency rate: {matches/total:.2%}" if total > 0 else "N/A")

    if mismatch_details:
        print("\n=== Mismatches ===")
        for f, label, detail in mismatch_details[:20]:
            print(f"{f} | {label} | {detail}")


if __name__ == "__main__":
    verify_all()