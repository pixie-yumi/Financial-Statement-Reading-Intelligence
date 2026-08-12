"""
check_mode1_all.py

Purpose: Runs Mode 1's exact underlying logic (list_raw_line_items --
the same function show_raw_statement calls) across EVERY company,
EVERY version (Consolidated/Unconsolidated/unknown), and all 3
statement types, in one pass -- instead of manually clicking through
the interactive CLI ~16 companies x up to 2 versions x 3 statements
(~90+ manual steps).

For each combination, reports:
  - how many line items were found
  - whether any items had a value but got skipped (rare, worth flagging)
  - whether it errored out entirely

Flags anything that looks wrong (0 items found, or a hard error) so you
can go investigate that ONE specific company/version/statement instead
of re-checking everything by eye.
"""
import pandas as pd
from query_engine import list_raw_line_items, RANGES_PATH, STATEMENT_TYPES


def get_versions_for_company(company_ranges):
    """Same logic as pick_version() in query_engine.py, but returns
    ALL versions worth checking instead of asking interactively."""
    available = set(company_ranges["version"].unique()) if "version" in company_ranges.columns else set()
    if available == {"unknown"} or not available:
        return ["unknown"]
    # check both real versions if present, skip "unknown" noise when
    # real versions exist (mirrors pick_version's own fallback logic)
    real_versions = [v for v in available if v in ("consolidated", "unconsolidated")]
    return real_versions if real_versions else ["unknown"]


def run_check():
    ranges_df = pd.read_csv(RANGES_PATH)
    companies = sorted(ranges_df["filename"].unique())

    results = []

    for company in companies:
        company_ranges = ranges_df[ranges_df["filename"] == company]
        versions = get_versions_for_company(company_ranges)

        for version in versions:
            version_ranges = company_ranges
            if version != "unknown" and "version" in company_ranges.columns:
                vspecific = company_ranges[company_ranges["version"] == version]
                if not vspecific.empty:
                    version_ranges = vspecific

            types_available = sorted(
                version_ranges[version_ranges["type"].isin(STATEMENT_TYPES)]["type"].unique()
            )

            for stype in types_available:
                try:
                    items, error = list_raw_line_items(company, stype, version)
                except Exception as e:
                    results.append({
                        "company": company, "version": version, "statement": stype,
                        "items_found": 0, "status": f"ERROR: {e}"
                    })
                    continue

                if error:
                    results.append({
                        "company": company, "version": version, "statement": stype,
                        "items_found": 0, "status": f"NO DATA: {error}"
                    })
                    continue

                count = len(items)
                both_years_count = sum(
                    1 for it in items if it["value_2025"] is not None and it["value_2024"] is not None
                )
                status = "OK" if count > 0 else "FLAG: zero items found"
                results.append({
                    "company": company, "version": version, "statement": stype,
                    "items_found": count, "both_years": both_years_count, "status": status
                })

    results_df = pd.DataFrame(results)
    results_df.to_csv("output/mode1_check_results.csv", index=False)

    total = len(results_df)
    ok_count = (results_df["status"] == "OK").sum()
    flagged = results_df[results_df["status"] != "OK"]

    print(f"Total company/version/statement combinations checked: {total}")
    print(f"OK: {ok_count}")
    print(f"Flagged: {len(flagged)}\n")

    if not flagged.empty:
        print("=== Flagged combinations (investigate these) ===")
        for _, row in flagged.iterrows():
            print(f"  {row['company']} | {row['version']} | {row['statement']} | {row['status']}")
    else:
        print("Nothing flagged -- every company/version/statement combination returned at least one line item.")

    print(f"\nFull breakdown saved to: output/mode1_check_results.csv")
    print("\n=== Item counts per combination ===")
    print(results_df[["company", "version", "statement", "items_found", "both_years"]].to_string(index=False))


if __name__ == "__main__":
    run_check()