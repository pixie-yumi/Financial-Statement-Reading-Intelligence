"""
diagnose_jsbank.py

Purpose: JS Bank Ltd came back with ZERO items across all 6
company/version/statement combinations in check_mode1_all.py -- unlike
every other company, which had at least some gaps but never total
failure. This pulls apart WHY, range by range:
  1. What ranges does Statement ID actually think exist for JS Bank?
  2. For each range, what does table extraction actually return
     (status "ok", "garbled_font", or "no_rows_extracted")?
  3. If it's "ok" but items still came back empty, sample a few raw
     rows to see what's getting filtered out and why.
"""
import pandas as pd
from extract_tables import extract_table_for_range
from extract_st_id import extract_pages

RANGES_PATH = "output/output_page_ranges_v2.csv"


def dump_raw_words(pdf_path, page_num):
    """Bypasses ALL row-grouping/clustering logic entirely -- shows
    EVERY word pdfplumber extracts from this page, with its exact x0
    and top position, sorted reading-order (top then x0). This tells
    us whether line-item labels exist ANYWHERE on the page (just at an
    unexpected position) or are genuinely missing from extraction."""
    import pdfplumber
    print(f"\n=== RAW WORD DUMP: page {page_num} ===\n")
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]
        words = page.extract_words()
        print(f"Total words extracted: {len(words)}\n")
        for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
            print(f"  top={w['top']:.1f}  x0={w['x0']:.1f}  text={w['text']!r}")


def diagnose():
    ranges_df = pd.read_csv(RANGES_PATH)
    js_ranges = ranges_df[ranges_df["filename"].str.contains("JS Bank", case=False, na=False)]

    if js_ranges.empty:
        print("No ranges found for JS Bank at all in output_page_ranges_v2.csv -- "
              "Statement ID never identified ANY statement pages for this PDF. "
              "That's the root cause right there -- worth checking Step 1, not table extraction.")
        return

    STATEMENT_TYPES = ["balance_sheet", "profit_and_loss", "cash_flow"]
    js_ranges = js_ranges[js_ranges["type"].isin(STATEMENT_TYPES)]

    print(f"Found {len(js_ranges)} relevant range(s) for JS Bank (excluding notes/changes_in_equity):\n")
    print(js_ranges[["filename", "type", "version", "start_page", "end_page"]].to_string(index=False))
    print()

    filename = js_ranges.iloc[0]["filename"]
    pdf_path = f"data/{filename}"

    for _, r in js_ranges.iterrows():
        stype, version = r["type"], r.get("version", "unknown")
        start, end = r["start_page"], r["end_page"]
        multi_type = r["multi_type"] if "multi_type" in r and pd.notna(r["multi_type"]) else None
        force_split = True if multi_type is True else None

        print(f"--- {stype} ({version}), pages {start}-{end} ---")
        try:
            table, reason = extract_table_for_range(pdf_path, start, end, multi_type=force_split)
        except Exception as e:
            print(f"  CRASHED: {e}\n")
            continue

        print(f"  Extraction status: {reason}")
        print(f"  Rows returned: {len(table) if table else 0}")

        if reason != "ok" or not table:
            # show raw text from the first page in this range so we can
            # see what it actually looks like
            print(f"  Raw text sample from page {start}:")
            try:
                pages = extract_pages(pdf_path)
                sample = (pages.get(int(start), "") or "")[:500]
                print(f"  {sample!r}")
            except Exception as e:
                print(f"  Could not read raw text: {e}")
        else:
            print("  All rows (raw, unfiltered):")
            for row in table:
                print(f"    {row}")

        print()


if __name__ == "__main__":
    diagnose()
    # NEW: dump raw words for JS Bank's balance_sheet (unconsolidated,
    # page 60) specifically -- the clearest, smallest example of every
    # row missing its label -- bypassing row-grouping entirely so we
    # can see whether the real labels exist anywhere on the page.
    dump_raw_words("data/JS BankLtd.pdf", 60)