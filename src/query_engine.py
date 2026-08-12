"""
query_engine.py

Purpose: Interactive query interface with two modes:
1. Query existing processed data
2. Process a brand-new PDF through the full pipeline, then query it
   immediately. Shows available line items as a numbered list so the
   user doesn't have to guess exact wording.
"""
import os
import re
import sys
import pandas as pd

# FIX: on Windows, Python's stdout defaults to the console's configured
# codepage (often cp1252 or similar), NOT UTF-8. Some labels extracted
# from PDFs contain non-ASCII characters (e.g. a Unicode dash variant
# instead of a plain ASCII "-"). When such bytes get encoded to the
# wrong codepage and rendered by certain Windows terminals, they can be
# misinterpreted as control characters (cursor movement), causing
# earlier text on the same line to be visually overwritten -- even
# though the underlying string is completely correct. Forcing UTF-8
# here fixes this at the source.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
from rapidfuzz import fuzz

from extract_st_id import extract_pages, extract_pages_full
from classify_full import classify_page, build_ranges_for_pages, detect_version
from extract_tables import extract_table_for_range
from header_identification import (
    SYNONYMS, match_label_best, is_junk_label, is_garbled,
    find_assets_section_start, find_total_assets_anchor, resolve_ambiguous_category,
)
from extract_by_position import is_prose_row
from value_extraction import clean_value
from generate_statement_report import generate_report


RESULTS_PATH = "output/value_extraction_results.csv"
RANGES_PATH = "output/output_page_ranges_v2.csv"
STATEMENT_TYPES = ["balance_sheet", "profit_and_loss", "cash_flow"]


def list_raw_line_items(filename, stype, version, ranges_path=RANGES_PATH):
    """NEW: lists EVERY genuine line item from a company's statement,
    exactly as worded in the PDF -- WITHOUT requiring it to match one
    of our known SYNONYMS categories first.

    Why: the categorized query (mode 1) only shows an item if it
    matched one of our ~100 predefined categories. Any real line item
    using wording we haven't added a synonym for simply doesn't show
    up at all -- silently. This function instead pulls the ACTUAL
    table for the right pages and lists every row that survives basic
    junk-filtering (prose/footer/garbled text), so it works for ANY
    company's exact wording, not just the ones we've already covered."""
    try:
        ranges_df = pd.read_csv(ranges_path)
    except Exception as e:
        return [], f"Could not load page ranges: {e}"

    company_ranges = ranges_df[
        (ranges_df["filename"].str.contains(filename, case=False, na=False)) &
        (ranges_df["type"] == stype)
    ]
    if company_ranges.empty:
        return [], f"No {stype} pages found for '{filename}'."

    if version and "version" in company_ranges.columns:
        version_specific = company_ranges[company_ranges["version"] == version]
        if not version_specific.empty:
            company_ranges = version_specific
        else:
            unknown_specific = company_ranges[company_ranges["version"] == "unknown"]
            if not unknown_specific.empty:
                company_ranges = unknown_specific

    real_filename = company_ranges.iloc[0]["filename"]
    # FIX: a newly-uploaded PDF (Option 2) can live anywhere on disk --
    # use its actual stored path if we have one, instead of always
    # assuming "data/{filename}" (which only applies to the 17
    # pre-processed companies and crashed with FileNotFoundError for
    # anything uploaded from elsewhere).
    if "full_path" in company_ranges.columns and pd.notna(company_ranges.iloc[0].get("full_path")):
        pdf_path = company_ranges.iloc[0]["full_path"]
    else:
        pdf_path = f"data/{real_filename}"

    items = []
    for _, range_row in company_ranges.iterrows():
        multi_type = range_row["multi_type"] if "multi_type" in range_row else None
        force_split = True if multi_type is True else None
        table, reason = extract_table_for_range(
            pdf_path, range_row["start_page"], range_row["end_page"], multi_type=force_split
        )
        if reason != "ok" or not table:
            continue

        for row in table:
            if len(row) < 6:
                continue
            label = str(row[2]).strip() if row[2] else ""
            # FIX: some PDF extractions can leave a stray carriage-
            # return or other control character embedded mid-string
            # (not just as a line terminator). In a terminal, a \r
            # moves the cursor back to column 0 and lets subsequent
            # characters overwrite what came before -- so a label like
            # "Long - term loans and advances\radvances" would visually
            # RENDER as just "advances" even though the real string is
            # complete. Stripping these out is a safe no-op if they
            # weren't there, and fixes display if they were.
            label = re.sub(r'[\r\x00-\x09\x0b-\x1f]', '', label)
            # FIX: normalize Unicode dash/hyphen variants (en-dash,
            # em-dash, non-breaking hyphen, etc.) to a plain ASCII "-".
            # Some Windows terminal codepages misinterpret these
            # specific byte sequences as control characters, causing
            # visual corruption even with UTF-8 stdout configured.
            label = re.sub(r'[\u2010\u2011\u2012\u2013\u2014\u2015]', '-', label)
            # FIX: some PDFs' font rendering inserts a stray space right
            # after the "fi" letter-pair (a common ligature glyph) --
            # e.g. "Profi t" instead of "Profit", "fi nal" instead of
            # "final". Collapsing "fi " + a following lowercase letter
            # back together fixes this without affecting genuine word
            # boundaries (a standalone word "fi" essentially never
            # appears in financial statement text).
            label = re.sub(r'fi (?=[a-z])', 'fi', label)
            label = re.sub(r'fl (?=[a-z])', 'fl', label)
            value_2025 = row[4] if len(row) > 4 else None
            value_2024 = row[5] if len(row) > 5 else None

            if not label:
                continue
            if label.strip().lower() == "note":
                continue
            if is_garbled(label):
                continue
            if is_junk_label(label):
                continue
            # NEW: when a page has BOTH cash_flow and changes_in_equity
            # printed side-by-side (common in Pakistani annual
            # reports), our column-split extracts BOTH halves but can't
            # yet tell which rows belong to which statement -- so
            # Changes in Equity's own rows (e.g. "Balance as at January
            # 01, 2024", "Total comprehensive income for the year")
            # were bleeding into the cash_flow listing. These have
            # distinctive phrasing that never appears in a genuine Cash
            # Flow statement, so we filter them out specifically when
            # listing cash_flow.
            if stype == "cash_flow" and re.match(
                r'^(balance as at|year ended|other comprehensive income)\b', label.strip().lower()
            ):
                continue
            if is_prose_row(label, [v for v in (value_2025, value_2024) if v]):
                continue
            if not (str(value_2025).strip() or str(value_2024).strip()):
                continue

            items.append({
                "raw_label": label,
                "value_2025": clean_value(value_2025),
                "value_2024": clean_value(value_2024),
            })

    return items, None


def load_results(path=RESULTS_PATH):
    try:
        if os.path.exists(path):
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame(columns=["filename", "statement_type", "version", "category", "raw_label", "value_2025", "value_2024"])


def show_available_categories(filename, results_df):
    company_data = results_df[results_df["filename"] == filename]
    categories = sorted(company_data["category"].unique())
    print(f"\nAvailable line items for {filename}:")
    for i, cat in enumerate(categories, 1):
        print(f"  {i}. {cat}")
    return categories


def ask_line_item(filename, results_df, version=None):
    company_data = results_df[results_df["filename"] == filename]

    # NEW: narrow to the chosen version first, so the numbered list only
    # shows line items that actually exist for THAT version -- avoids
    # picking a number that then can't be found (e.g. an item only
    # available Unconsolidated while querying Consolidated).
    #
    # FIX: companies without subsidiaries don't distinguish
    # Consolidated/Unconsolidated at all -- their data is tagged
    # "unknown" (their one and only set of statements). Fall back to
    # that instead of showing an empty/wrong list.
    if version and "version" in company_data.columns:
        version_filtered = company_data[company_data["version"] == version]
        if not version_filtered.empty:
            company_data = version_filtered
        else:
            unknown_filtered = company_data[company_data["version"] == "unknown"]
            if not unknown_filtered.empty:
                company_data = unknown_filtered

    statement_types = sorted(company_data["statement_type"].unique())
    if not statement_types:
        return None

    print(f"\nAvailable statements for {filename}:")
    for i, st in enumerate(statement_types, 1):
        print(f"  {i}. {st}")

    st_choice = input("\nPick a statement (number): ").strip()
    if st_choice.isdigit() and 1 <= int(st_choice) <= len(statement_types):
        chosen_statement = statement_types[int(st_choice) - 1]
    else:
        return st_choice  # agar galat type kiya, usay hi search-term maan lo

    filtered = company_data[company_data["statement_type"] == chosen_statement]
    categories = sorted(filtered["category"].unique())

    print(f"\nAvailable line items in {chosen_statement}:")
    for i, cat in enumerate(categories, 1):
        print(f"  {i}. {cat}")

    choice = input("\nPick a number (or type your own search term): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(categories):
        return categories[int(choice) - 1]
    return choice


def query(company, year, line_item, results_df, threshold=60, version=None):
    try:
        year_col = "value_2025" if str(year) == "2025" else "value_2024"
        company_matches = results_df[results_df["filename"].str.contains(company, case=False, na=False)]

        if company_matches.empty:
            return {"found": False, "message": f"No company matching '{company}' found."}

        # NEW: filter to the requested version (Consolidated /
        # Unconsolidated) if the person specified one. Both versions
        # are kept all the way through the pipeline now, tagged, so we
        # only narrow down to one at query time.
        #
        # FIX: many companies (ones without subsidiaries) don't
        # distinguish Consolidated/Unconsolidated at all -- they just
        # have ONE set of financial statements, tagged "unknown". If
        # the person specifically asks for "consolidated" or
        # "unconsolidated" for such a company, we used to fail entirely
        # ("No consolidated data found") even though the real data
        # exists right there under "unknown". Now we fall back to
        # "unknown" version data when the specifically-requested
        # version doesn't exist -- that IS the company's one and only
        # statement, so it's the correct answer, not a failure.
        searched_version = version
        if version and "version" in company_matches.columns:
            version_specific = company_matches[company_matches["version"] == version]
            if not version_specific.empty:
                company_matches = version_specific
            else:
                unknown_matches = company_matches[company_matches["version"] == "unknown"]
                if not unknown_matches.empty:
                    company_matches = unknown_matches
                else:
                    return {
                        "found": False,
                        "message": f"No {version} data found for '{company}' at all "
                                   f"(only the other version may be available).",
                    }

        # NEW: try an EXACT category match first (the numbered-list
        # selections pass the exact category name) -- this avoids fuzzy
        # matching ever picking an unrelated category when the real
        # thing just isn't in this version.
        exact_matches = company_matches[
            company_matches["category"].astype(str).str.lower() == line_item.lower()
        ]
        if not exact_matches.empty:
            best_row, best_score = exact_matches.iloc[0], 100.0
        else:
            best_row, best_score = None, 0
            for _, row in company_matches.iterrows():
                s1 = fuzz.partial_ratio(line_item.lower(), str(row["category"]).lower())
                s2 = fuzz.partial_ratio(line_item.lower(), str(row["raw_label"]).lower())
                score = max(s1, s2)
                if score > best_score:
                    best_score, best_row = score, row

        # NEW: raised the bar for fuzzy (non-exact) matches specifically
        # -- a low-confidence fuzzy hit within the right version is
        # still risky. Exact category matches always pass through at
        # 100%, untouched by this stricter bar.
        fuzzy_threshold = max(threshold, 75)
        if best_row is None or best_score < fuzzy_threshold:
            version_note = f" in the {searched_version} version" if searched_version else ""
            return {
                "found": False,
                "message": f"No confident match for '{line_item}'{version_note} for '{company}'. "
                           f"It may only exist in the other version, or under different wording.",
            }

        value = best_row[year_col]
        if pd.isna(value):
            return {"found": False, "message": f"'{best_row['raw_label']}' found, but no value for {year}."}

        return {
            "found": True, "company": best_row["filename"], "statement_type": best_row["statement_type"],
            "version": best_row.get("version", "unknown"),
            "category": best_row["category"], "raw_label": best_row["raw_label"], "year": year,
            "value": value, "match_confidence": round(best_score, 1),
        }
    except Exception as e:
        return {"found": False, "message": f"Query error: {e}"}


def print_result(result):
    if result["found"]:
        print(f"\n  Company: {result['company']}")
        print(f"  Statement: {result['statement_type']} ({result.get('version', 'unknown')})")
        print(f"  Line item: '{result['raw_label']}' ({result['category']})")
        print(f"  Year: {result['year']}")
        print(f"  Value: {result['value']:,.0f}")
        print(f"  Match confidence: {result['match_confidence']}%\n")
    else:
        print(f"\n  {result['message']}\n")


def build_ranges_for_new_pdf(pdf_path):
    """Uses the EXACT SAME range-building logic as the main pipeline
    (classify_full.py's build_ranges_for_pages) -- including every fix
    made to it (single-page-gap bridging for multi-page statements,
    multi_type column-split detection, Notes-page false-positive
    exclusion, Table-of-Contents detection, etc.) -- instead of a
    separate, older duplicated copy that missed these fixes for
    newly-uploaded PDFs."""
    try:
        pages = extract_pages_full(pdf_path)
    except Exception as e:
        print(f"  Could not read PDF: {e}")
        return []

    page_type_lists = {}
    page_versions = {}
    for page_num, page_data in sorted(pages.items()):
        try:
            labels = classify_page(page_data["text"], page_data["bold_blocks"])
        except Exception:
            labels = ["other"]
        page_type_lists[page_num] = labels
        try:
            page_versions[page_num] = detect_version(page_data["text"])
        except Exception:
            page_versions[page_num] = "unknown"

    return build_ranges_for_pages(os.path.basename(pdf_path), page_type_lists, page_versions)


def process_new_pdf(pdf_path):
    filename = os.path.basename(pdf_path)
    print(f"\nProcessing: {filename} ...")

    if not os.path.exists(pdf_path):
        print(f"  File not found: {pdf_path}\n")
        return None

    print("  Step 1/4: Statement Identification...")
    try:
        ranges = build_ranges_for_new_pdf(pdf_path)
    except Exception as e:
        print(f"  Statement Identification failed: {e}\n")
        return None

    relevant_ranges = [r for r in ranges if r["type"] in STATEMENT_TYPES]

    # NEW: append these freshly-computed ranges to the shared ranges
    # CSV too (not just the categorized results CSV) -- this is what
    # lets show_raw_statement()/list_raw_line_items() work for a
    # newly-uploaded PDF exactly the same way they already do for the
    # 17 pre-processed companies, instead of only supporting the
    # categorized (template-limited) view for new uploads.
    try:
        all_ranges_for_pdf = pd.DataFrame(ranges)
        if not all_ranges_for_pdf.empty:
            # FIX: previously list_raw_line_items always reconstructed
            # the PDF path as "data/{filename}", which only works for
            # the 17 pre-processed companies. A freshly-uploaded PDF
            # (Option 2) can be ANYWHERE on disk -- storing its real
            # full path here lets show_raw_statement()/
            # list_raw_line_items() find it correctly later instead of
            # crashing with FileNotFoundError.
            all_ranges_for_pdf["full_path"] = pdf_path
            if os.path.exists(RANGES_PATH):
                existing_ranges = pd.read_csv(RANGES_PATH)
                existing_ranges = existing_ranges[existing_ranges["filename"] != filename]
                combined_ranges = pd.concat([existing_ranges, all_ranges_for_pdf], ignore_index=True)
            else:
                combined_ranges = all_ranges_for_pdf
            combined_ranges.to_csv(RANGES_PATH, index=False)
    except Exception as e:
        print(f"  Warning: could not save page ranges: {e}")

    if not relevant_ranges:
        print("  No Balance Sheet / P&L / Cash Flow pages found in this PDF.")
        try:
            pages = extract_pages(pdf_path)
            readable = sum(1 for t in pages.values() if t.strip())
            print(f"  Diagnostic: {len(pages)} total pages, {readable} had readable text.")
            if readable < len(pages) * 0.5:
                print("  This PDF appears to be scanned/image-based (no extractable text).")
            else:
                print("  Text is readable, but no matching statement keywords were found.")
        except Exception:
            print("  Could not diagnose further.")
        return None

    print(f"  Found {len(relevant_ranges)} statement range(s): "
          f"{[(r['type'], r['start_page'], r['end_page']) for r in relevant_ranges]}")

    print("  Step 2/4: Table Identification...")
    new_results = []

    for range_info in relevant_ranges:
        stype = range_info["type"]
        # NEW: use the multi_type flag (computed the same way as the
        # main pipeline) to force column-splitting when this range
        # genuinely has two statement types sharing a page -- this was
        # previously ALWAYS None here, meaning new PDFs never got this
        # fix that Gul Ahmed and others needed.
        multi_type = range_info.get("multi_type")
        force_split = True if multi_type is True else None
        try:
            table, reason = extract_table_for_range(
                pdf_path, range_info["start_page"], range_info["end_page"], multi_type=force_split
            )
        except Exception as e:
            print(f"    Table extraction failed for {stype}: {e}")
            continue

        if reason != "ok" or not table:
            print(f"    No usable table found for {stype} ({reason}).")
            continue

        version = range_info.get("version", "unknown")

        # NEW: same Assets-section boundary detection used by the main
        # pipeline, so identically-worded asset-side vs liability-side
        # items (e.g. "Long term deposits", "Taxation - net") get
        # disambiguated correctly here too, not just for the 17
        # pre-processed companies.
        assets_start = find_assets_section_start(table) if stype == "balance_sheet" else None
        assets_end = find_total_assets_anchor(table) if stype == "balance_sheet" else None

        print(f"  Step 3/4: Header Identification ({stype})...")
        for row_index, row in enumerate(table):
            if len(row) < 6:
                continue
            try:
                matched, score, variant = match_label_best(row, SYNONYMS)
            except Exception:
                continue
            if not matched:
                continue

            if stype == "balance_sheet":
                matched = resolve_ambiguous_category(matched, variant, row_index, assets_start, assets_end)

            try:
                value_2025 = clean_value(row[4] if len(row) > 4 else None)
                value_2024 = clean_value(row[5] if len(row) > 5 else None)
            except Exception:
                value_2025, value_2024 = None, None

            new_results.append({
                "filename": filename, "statement_type": stype, "version": version, "category": matched,
                "raw_label": variant, "value_2025": value_2025, "value_2024": value_2024,
            })

    if not new_results:
        print("  No matched line items found for this PDF.\n")
        return None

    new_df = pd.DataFrame(new_results)
    new_df = new_df[new_df["value_2025"].notna() | new_df["value_2024"].notna()]

    if len(new_df) == 0:
        print("  No queryable data was extracted from this PDF.\n")
        return None

    try:
        existing_df = load_results()
        existing_df = existing_df[existing_df["filename"] != filename]
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        combined_df.to_csv(RESULTS_PATH, index=False)
    except Exception as e:
        print(f"  Warning: could not save results to CSV: {e}")

    print(f"\nDone! Extracted {len(new_df)} line items from {filename}.\n")
    return new_df


def show_raw_statement(company, stype, version):
    """Shows EVERY genuine line item actually present in the PDF for
    this statement + version -- exactly as worded in the PDF, with its
    real value. Nothing invented, nothing shown as '— not found —' --
    if it's not in the PDF, it's simply not in this list."""
    if stype == "changes_in_equity":
        print(
            "\n  Note: Statement of Changes in Equity has a different table "
            "structure than the other statements -- it usually has MANY "
            "value columns (one per equity component: share capital, "
            "each reserve, retained earnings, total), not just "
            "current-year/prior-year like the Balance Sheet, Income "
            "Statement, and Cash Flow. Our extraction is built around "
            "exactly 2 value columns, so this statement's line items "
            "can't be shown reliably here yet -- the underlying numbers "
            "would come out wrong or scrambled. This is a known gap, "
            "not something to trust for Changes in Equity specifically.\n"
        )
        return

    items, error = list_raw_line_items(company, stype, version)
    if error:
        print(f"\n  {error}\n")
        return
    if not items:
        print("\n  No line items found.\n")
        return

    print(f"\n=== {stype} ({version}) — every line item found in the PDF ===\n")
    for it in items:
        def fmt(v):
            if v is None:
                return "—"
            # FIX: small values (like EPS, e.g. 81.37) were being
            # rounded to whole numbers ("81") by always using zero
            # decimal places -- large financial amounts (already in
            # '000s) don't need decimals, but small per-share figures
            # do.
            if abs(v) < 1000:
                return f"{v:,.2f}"
            return f"{v:,.0f}"
        v2025 = fmt(it["value_2025"])
        v2024 = fmt(it["value_2024"])
        # NEW: print label and values on SEPARATE lines instead of one
        # long ~100-character line. A single long line gets silently
        # cut off (only the tail visible) in narrow terminal windows
        # (e.g. a default-width PowerShell window), making labels look
        # truncated even though the underlying data is complete. This
        # format stays readable regardless of terminal width.
        print(f"  {it['raw_label']}")
        print(f"      2025: {v2025:>18}   2024: {v2024:>18}")
    print()


def pick_version(company, ranges_path=RANGES_PATH):
    """Asks Consolidated/Unconsolidated -- but if this company's PDF
    doesn't actually distinguish the two at all (a standalone company
    with no subsidiaries prints just ONE set of statements, tagged
    "unknown"), skip the question entirely and use that single
    version instead of forcing a choice that doesn't apply."""
    try:
        ranges_df = pd.read_csv(ranges_path)
    except Exception:
        ranges_df = pd.DataFrame(columns=["filename", "version"])

    company_ranges = ranges_df[ranges_df["filename"].str.contains(company, case=False, na=False)]
    available_versions = set(company_ranges["version"].unique()) if not company_ranges.empty else set()

    if available_versions == {"unknown"} or not available_versions:
        print("\n(This company's statements aren't split into Consolidated/Unconsolidated -- using its one set of statements.)")
        return "unknown"

    version_choice = input("\nConsolidated or Unconsolidated? (c/u, Enter for Consolidated): ").strip().lower()
    return "unconsolidated" if version_choice.startswith("u") else "consolidated"


def pick_statement_type(company, version, ranges_path=RANGES_PATH):
    """Shows which statement types actually exist for this company +
    version, and lets the person pick one."""
    try:
        ranges_df = pd.read_csv(ranges_path)
    except Exception:
        return None

    company_ranges = ranges_df[
        (ranges_df["filename"].str.contains(company, case=False, na=False)) &
        (ranges_df["type"].isin(STATEMENT_TYPES))
    ]
    if version != "unknown":
        version_specific = company_ranges[company_ranges["version"] == version]
        if not version_specific.empty:
            company_ranges = version_specific
        else:
            company_ranges = company_ranges[company_ranges["version"] == "unknown"]

    types_available = sorted(company_ranges["type"].unique())
    if not types_available:
        return None

    print("\nAvailable statements:")
    for i, t in enumerate(types_available, 1):
        print(f"  {i}. {t}")

    choice = input("\nPick a statement (number): ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(types_available):
        return types_available[int(choice) - 1]
    return choice


def run_interactive():
    print("=== FinSight Query Engine ===\n")
    print("1. Pick an existing company")
    print("2. Upload a new PDF")
    print("Type 'quit' at any prompt to exit.\n")

    while True:
        try:
            mode = input("Choose mode (1 or 2): ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if mode.lower() == "quit":
            break

        if mode == "2":
            pdf_path = input("Enter path to the new PDF: ").strip().strip('"')
            if pdf_path.lower() == "quit":
                break

            new_df = process_new_pdf(pdf_path)
            if new_df is None or len(new_df) == 0:
                continue

            company = os.path.basename(pdf_path)

        elif mode == "1":
            results_df = load_results()
            companies = sorted(set(results_df["filename"]))
            print("\nAvailable companies:")
            for i, c in enumerate(companies, 1):
                print(f"  {i}. {c}")
            print()

            company_choice = input("Company number or name: ").strip()
            if company_choice.lower() == "quit":
                break

            if company_choice.isdigit() and 1 <= int(company_choice) <= len(companies):
                company = companies[int(company_choice) - 1]
            else:
                company = company_choice

        else:
            print("\n  Please type 1 or 2.\n")
            continue

        version = pick_version(company)
        if version is None:
            continue

        stype = pick_statement_type(company, version)
        if not stype:
            print("\n  No statements found for this company.\n")
            continue

        show_raw_statement(company, stype, version)


if __name__ == "__main__":
    run_interactive()