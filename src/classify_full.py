import os
import csv
import re
import pandas as pd
from extract_st_id import extract_pages_full

KEYWORD_MAP = {
    "balance_sheet": [
        "statement of financial position",
        "balance sheet",
        "consolidated statement of financial position",
        "unconsolidated statement of financial position",
        "statement of assets and liabilities",
    ],
    "profit_and_loss": [
        "profit and loss account",
        "statement of profit or loss",
        "income statement",
        "consolidated statement of profit or loss",
        "unconsolidated statement of profit or loss",
        "statement of comprehensive income",
        "profit and loss statement",
    ],
    "cash_flow": [
        "cash flow statement",
        "statement of cash flows",
        "consolidated statement of cash flows",
        "unconsolidated statement of cash flows",
    ],
    "changes_in_equity": [
        "statement of changes in equity",
        "consolidated statement of changes in equity",
        "unconsolidated statement of changes in equity",
        "statement of changes in shareholders equity",
    ],
    "notes": [
        "notes to and forming part of",
        "notes to the financial statements",
        "notes to the unconsolidated financial statements",
        "notes to the consolidated financial statements",
        "notes forming part of the financial statements",
    ],
}

REPORT_INDICATORS = ["auditor's report", "independent auditor", "opinion", "we have audited"]


def _contains_phrase(text_with_spaces, text_nospace, phrase):
    """Matches a phrase against page text either normally, or with ALL
    whitespace removed from both sides. Some PDFs render body text with
    essentially NO space characters between words at all (seen in
    Crescent Cotton Mills: 'CONSOLIDATEDSTATEMENTOFFINANCIALPOSITION',
    with every word glued to the next one, not just an occasional
    kerning-glitch pair like the earlier "Profi t" case) -- silently
    breaking every space-sensitive keyword check, Statement ID
    included, even though the real title genuinely is present on the
    page. Checking the space-stripped version as a fallback catches
    this without weakening the normal check for every other PDF, which
    still matches on the first, ordinary try."""
    if phrase in text_with_spaces:
        return True
    return phrase.replace(" ", "") in text_nospace


def has_financial_data(page_text, min_numbers=25):
    """Checks whether the page has real financial data (enough numbers),
    not just a reference/TOC listing."""
    numbers = re.findall(r'\d{2,}', page_text)
    return len(numbers) >= min_numbers


def is_multi_year_summary(page_text):
    """Checks whether this is an 'X Years at a Glance' summary page,
    not a real statement."""
    text_lower = page_text.lower()
    if "years at a glance" in text_lower or "six years" in text_lower or "5 years" in text_lower:
        return True

    # NEW: some multi-year summary pages (e.g. a "Free Cash Flows"
    # highlights table) don't use any of those phrases at all -- they
    # just show a run of consecutive years as column headers (e.g.
    # "2025 2024 2023 2022 2021 2020"), often in "Rupees in Million"
    # rather than the "'000" used by the real single-year statements.
    # A real Balance Sheet/P&L/Cash Flow page only ever shows the
    # CURRENT and PRIOR year (2 columns) -- 5+ consecutive years is a
    # reliable sign this is a multi-year highlights table instead.
    years_found = sorted(set(int(y) for y in re.findall(r'\b(20[0-2]\d)\b', page_text[:400])))
    for i in range(len(years_found) - 4):
        window = years_found[i:i + 5]
        if window[-1] - window[0] == 4:  # 5 consecutive years
            return True

    return False


def is_analysis_summary_page(page_text):
    """'Financial Highlights' / 'Horizontal Analysis' / 'Vertical
    Analysis' pages often contain a BOLD 'Balance Sheet' or 'Cash Flow
    Statement' LABEL as part of a ratio table (not the actual
    statement), plus plenty of numbers -- so they slip past
    has_financial_data(). We exclude them explicitly.

    FIX: originally only checked the first 500 characters and a short
    keyword list. Lucky Cement's ratio-table page slipped through this
    check (contaminating our real balance_sheet data with percentage
    rows like "Total Equity & Liabilities 100.00 100.00") -- likely
    because its indicator phrase appeared further down the page, or
    used wording not in our list. Widened the scan window and keyword
    list to catch more variants."""
    text_lower = page_text[:2000].lower()
    indicators = [
        "financial highlights", "horizontal analysis", "vertical analysis",
        "graphical analysis", "financial ratios", "dupont analysis",
        "common size", "ratio analysis", "% of net sales", "as a % of",
        "years at a glance", "summary of financial",
    ]
    return any(ind in text_lower for ind in indicators)


def match_bold_blocks(bold_blocks):
    """NEW: check the page's bold-heading blocks against KEYWORD_MAP.
    Catches real statement headings that plain-text keyword matching
    misses -- either because two statements are printed side-by-side in
    columns (which scrambles extract_text()'s reading order) or because
    a heading is split across two lines, e.g. "UNCONSOLIDATED STATEMENT"
    / "OF FINANCIAL POSITION". This is a HIGH CONFIDENCE signal since
    it's based on actual font weight, not just keyword position in raw
    text."""
    # FIX: when TWO statements are printed side-by-side as columns AND
    # their headings each span two lines, merging bold lines can
    # SCRAMBLE the word order between the two columns -- e.g.
    # "CONSOLIDATED STATEMENT CONSOLIDATED STATEMENT OF PROFIT OR LOSS
    # OF FINANCIAL POSITION" instead of each heading staying intact.
    # This broke the exact-phrase check for "statement of financial
    # position" (the words "financial position" ended up separated from
    # "statement" by the other column's "profit or loss" text). As a
    # fallback, if the exact phrase doesn't match, we also check whether
    # a small set of DISTINCTIVE words for that statement type all
    # appear somewhere in the block, regardless of order -- much less
    # likely to produce a false positive than checking single generic
    # words, since these word pairs are specific enough on their own.
    DISTINCTIVE_WORDS = {
        "balance_sheet": ["financial", "position"],
        "profit_and_loss": ["profit", "loss"],
        "cash_flow": ["cash", "flows"],
        "changes_in_equity": ["changes", "equity"],
    }

    matched = []
    for block in bold_blocks:
        block_lower = block.lower()
        block_words = set(block_lower.split())

        for statement_type, keywords in KEYWORD_MAP.items():
            if statement_type == "notes":
                continue
            if statement_type in matched:
                continue

            exact_hit = any(kw in block_lower for kw in keywords)
            if exact_hit:
                matched.append(statement_type)
                continue

            distinctive = DISTINCTIVE_WORDS.get(statement_type)
            if distinctive and all(word in block_words for word in distinctive):
                matched.append(statement_type)

    return matched


def is_note_cross_reference(page_text):
    """A Notes page can genuinely mention a statement's title in
    passing -- e.g. "6.2 Amounts recognised in the statement of
    financial position" (a pension-fund disclosure note), or "51.1
    Non-controlling interest ... Summarised statement of financial
    position" (a subsidiary summary note) -- without actually BEING
    that statement. This wrongly got tagged as balance_sheet,
    contaminating real categories with the note's own sub-figures
    instead of the company's actual totals.

    Two reliable signals, neither of which appears on a genuine
    statement's own title page:
      1. The word "summarised"/"summary" right next to the statement
         phrase -- real statements are never called a "summary".
      2. A note-section-number pattern (e.g. "48.2", "51.1", or a bare
         "51 SOME TITLE") appearing somewhere before the statement
         phrase, within a generously wide window (the note's own
         heading and intervening disclosure text can push the actual
         phrase well past a tight character limit)."""
    window = page_text[:350]
    window_lower = window.lower()
    window_lower = re.sub(r'\bprofi\s+t\b', 'profit', window_lower)

    if re.search(r'summaris(e|ed|ing)|summariz(e|ed|ing)|summary\s+statement of', window_lower):
        return True

    # NEW: "balance sheet" is sometimes used as a descriptive term
    # inside a currency-risk disclosure note (e.g. "Net balance sheet
    # exposure"), not as the actual statement's title. Exclude that
    # specific usage pattern -- checked over a wider window since it
    # can appear well down the page, after several rows of disclosure
    # data.
    wide_window = page_text[:900].lower()
    if re.search(r'(net|off[\s-]?)\s*balance sheet\s*(exposure|item)', wide_window):
        return True

    match = re.search(
        r'statement of financial position|balance sheet|statement of profit or loss|'
        r'statement of comprehensive income|statement of cash flows|statement of changes in equity',
        window_lower
    )
    if match:
        before = window[:match.start()]
        if re.search(r'\d+(\.\d+)+\s*$', before) or re.search(r'\b\d{1,3}\s*$', before) or re.search(r'\b\d{1,3}\s+[A-Z][A-Z ]{3,}', before):
            return True
        # NEW: "Amount(s) recognised/recognized in [the] statement of
        # X" is always a note's own cross-reference sentence -- a real
        # statement is simply titled "STATEMENT OF X" on its own, never
        # embedded in a sentence describing what's recognised in it.
        if re.search(r'recognis(e|ed)|recogniz(e|ed)', before[-60:]):
            return True

    return False


def classify_page(page_text, bold_blocks=None):
    narrow = page_text[:250].lower()
    wide = page_text[:900].lower().replace("\n", " ")
    # FIX: some PDFs' text extraction inserts a stray space INSIDE a
    # word due to font kerning/glyph-spacing quirks (e.g. "Statement of
    # Profi t or Loss" instead of "...Profit or Loss"). This silently
    # broke the "statement of profit or loss" keyword match entirely,
    # since the extracted text no longer contained "profit" as one
    # continuous word.
    wide = re.sub(r'\bprofi\s+t\b', 'profit', wide)
    wide_nospace = re.sub(r'\s+', '', wide)

    if is_multi_year_summary(page_text):
        return ["other"]

    if is_analysis_summary_page(page_text):
        return ["other"]

    if is_note_cross_reference(page_text):
        return ["notes"]

    for kw in KEYWORD_MAP["notes"]:
        if _contains_phrase(wide, wide_nospace, kw):
            return ["notes"]

    if any(ind in narrow for ind in REPORT_INDICATORS):
        return ["other"]

    # NEW: check bold headings FIRST -- most reliable signal, based on
    # font weight + line grouping, not raw text order (which scrambles
    # on two-column statement pages)
    #
    # FIX (evaluation showed this caused a precision crash): checking
    # ALL bold blocks on the page let Notes-section pages slip through,
    # since Notes often have their OWN bold sub-headings mentioning a
    # statement by name (e.g. "31.2 Reconciliation to the Statement of
    # Cash Flows") -- and notes pages have plenty of numbers too, so
    # has_financial_data() alone didn't filter them out.
    #
    # Real statement titles ALWAYS appear near the TOP of their page.
    # Notes sub-headings can appear anywhere on a notes page. So we only
    # trust a bold match if it's among the first few bold blocks
    # (top-of-page), not buried further down the page.
    TOP_OF_PAGE_BLOCK_LIMIT = 3
    top_blocks = bold_blocks[:TOP_OF_PAGE_BLOCK_LIMIT] if bold_blocks else []
    bold_matched = match_bold_blocks(top_blocks)
    if bold_matched:
        if has_financial_data(page_text):
            return bold_matched
        return ["other"]

    matched = []
    for statement_type, keywords in KEYWORD_MAP.items():
        if statement_type == "notes":
            continue
        for kw in keywords:
            if _contains_phrase(wide, wide_nospace, kw):
                matched.append(statement_type)
                break

    # NEW: a Table of Contents page lists MULTIPLE statement names
    # together as index entries (e.g. "Statement of Financial Position
    # 136 / Statement of Profit or Loss 137 / Statement of Cash Flows
    # 140") -- a real statement page never mentions several OTHER
    # statement types by name like this. 3+ distinct matches together
    # is a reliable sign this is a TOC/index, not any real statement.
    if len(set(matched)) >= 3:
        return ["other"]

    if matched and not has_financial_data(page_text):
        return ["other"]

    if matched:
        return matched

    # NEW: catches a Balance Sheet's SECOND page (the Assets side) when
    # it doesn't repeat the statement's title -- only the FIRST page
    # (Equity & Liabilities, in these reports) carries "STATEMENT OF
    # FINANCIAL POSITION". The continuation page just starts straight
    # into "ASSETS" / "NON-CURRENT ASSETS" / "CURRENT ASSETS" headings,
    # which we deliberately don't treat as a keyword on its own (bare
    # "assets" appears too often elsewhere) -- but THIS SPECIFIC
    # pattern (an "ASSETS" heading immediately followed by its own
    # NON-CURRENT/CURRENT ASSETS sub-headings, near the top of the
    # page) is distinctive enough to trust.
    top = page_text[:200].upper()
    has_assets_heading = bool(re.search(r'\bASSETS\b', top))
    has_subheading = "NON-CURRENT ASSETS" in top or "CURRENT ASSETS" in top or "NON CURRENT ASSETS" in top
    if has_assets_heading and has_subheading and has_financial_data(page_text):
        return ["balance_sheet"]

    # NEW: the SYMMETRIC case -- some companies print Assets FIRST,
    # then Equity & Liabilities as the un-retitled continuation page
    # (opposite order from the case above). "EQUITY AND LIABILITIES"
    # immediately followed by "SHARE CAPITAL AND RESERVES" near the top
    # is just as distinctive a signal.
    has_equity_heading = "EQUITY AND LIABILITIES" in top
    has_equity_subheading = "SHARE CAPITAL AND RESERVES" in top or "SHARE CAPITAL" in top
    if has_equity_heading and has_equity_subheading and has_financial_data(page_text):
        return ["balance_sheet"]

    return ["other"]


def detect_version(page_text):
    """NEW: detects whether a page belongs to the 'Consolidated' or
    'Unconsolidated' version of the financial statements. Pakistani
    annual reports commonly print BOTH versions (Consolidated = parent
    + subsidiaries combined, Unconsolidated = standalone parent company
    only), so we need to know which is which to let downstream stages
    filter to just one version if requested."""
    text_lower = page_text[:600].lower()
    if "unconsolidated" in text_lower:
        return "unconsolidated"
    if "consolidated" in text_lower:
        return "consolidated"
    return "unknown"


def _has_clean_top_of_page_title(page_text, statement_type):
    """Checks if page_text has an UNINTERRUPTED statement title near
    its top -- a strong signal this page is genuinely the start of
    that statement, not a continuation whose match only came from a
    reconstructed/scrambled text scan further down the page. Newlines
    are replaced with spaces first, since a genuine title can
    legitimately wrap across a line break (e.g. "STATEMENT OF\nFINANCIAL
    POSITION"), but a note's embedded reference won't fall this close
    to the top.

    FIX: a fixed character-count window is fragile -- some scrambled
    table-header continuations (e.g. column headers interleaved before
    the phrase) can coincidentally land just inside a char-count
    window. Word-count is more robust: a genuine title has minimal
    preamble (company name, "Annual Report", a year) -- rarely more
    than ~6 words -- while a scrambled continuation has many
    intervening words before the phrase."""
    top = page_text[:200].lower().replace("\n", " ")
    top = re.sub(r'\bprofi\s+t\b', 'profit', top)
    for kw in KEYWORD_MAP.get(statement_type, []):
        idx = top.find(kw)
        if idx != -1:
            # FIX: some reports print a running page-number index strip
            # right before the real title (e.g. "97 98 99 100 101 102
            # 103 104 Annual Report 2022\nUnconsolidated Statement of
            # Financial Position") -- these bare numbers aren't real
            # preamble text and were wrongly pushing genuine titles past
            # the word-count threshold, causing them to be misread as
            # scrambled continuations. Only count actual WORD tokens.
            preamble_words = [w for w in top[:idx].split() if not w.replace(",", "").isdigit()]
            if len(preamble_words) <= 6:
                return True
    return False


def classify_pdf(pdf_path):
    pages = extract_pages_full(pdf_path)
    results = []
    prev_labels = []
    for page_num, page_data in sorted(pages.items()):
        labels = classify_page(page_data["text"], page_data["bold_blocks"])

        # FIX: a multi-page Note (e.g. a "Financial instruments by
        # categories" table spanning 2-3 pages) only carries its note
        # number on its FIRST page. Later continuation pages have no
        # such marker, so is_note_cross_reference() can't catch them --
        # and if their own scrambled/reconstructed text happens to
        # match a statement keyword, they get wrongly tagged as that
        # statement. If the PRECEDING page was "notes" and this page's
        # match isn't a clean, uninterrupted title at the very top,
        # treat it as a continuation of that same note instead.
        CORE_TYPES = {"balance_sheet", "profit_and_loss", "cash_flow", "changes_in_equity"}
        if prev_labels in (["notes"], ["other"]) and set(labels) & CORE_TYPES:
            if not any(_has_clean_top_of_page_title(page_data["text"], t) for t in labels if t in CORE_TYPES):
                labels = ["notes"]

        version = detect_version(page_data["text"])
        results.append({"page": page_num, "types": labels, "version": version})
        prev_labels = labels
    return results


def build_ranges_for_pages(filename, page_type_lists, page_versions):
    """NEW: the single, shared range-building logic -- extracted so
    BOTH the main batch script (processing all 17 companies from a
    saved CSV) AND query_engine.py's new-PDF flow (processing one
    freshly-uploaded PDF) use the EXACT SAME logic, including every fix
    made to it (single-page-gap bridging, multi_type detection,
    is_plausible length filtering). Before this, query_engine.py
    maintained its own separate, older copy of this logic that missed
    several of these fixes entirely for newly-uploaded PDFs."""
    ALL_STATEMENT_TYPES = ["balance_sheet", "profit_and_loss", "cash_flow", "changes_in_equity", "notes"]
    CORE_TYPES = {"balance_sheet", "profit_and_loss", "cash_flow", "changes_in_equity"}
    ranges = []

    for stype in ALL_STATEMENT_TYPES:
        pages_with_type = sorted(p for p, types in page_type_lists.items() if stype in types)
        if not pages_with_type:
            continue

        def version_for_range(start, end):
            versions_in_range = [
                page_versions.get(p, "unknown") for p in range(start, end + 1)
                if page_versions.get(p, "unknown") != "unknown"
            ]
            if not versions_in_range:
                return "unknown"
            return max(sorted(set(versions_in_range)), key=versions_in_range.count)

        def has_multi_type(start, end):
            for p in range(start, end + 1):
                types_here = set(page_type_lists.get(p, [])) & CORE_TYPES
                if len(types_here) >= 2:
                    return True
            return False

        def page_conflicts(page_num, this_stype):
            other_types = set(page_type_lists.get(page_num, [])) & CORE_TYPES
            other_types.discard(this_stype)
            return bool(other_types)

        range_start = pages_with_type[0]
        prev_page = pages_with_type[0]
        for p in pages_with_type[1:]:
            gap = p - prev_page
            if gap == 2 and not page_conflicts(prev_page + 1, stype):
                pass  # bridge the gap -- don't split the range
            elif gap > 1:
                ranges.append({
                    "filename": filename, "type": stype,
                    "start_page": range_start, "end_page": prev_page,
                    "version": version_for_range(range_start, prev_page),
                    "multi_type": has_multi_type(range_start, prev_page),
                })
                range_start = p
            prev_page = p
        ranges.append({
            "filename": filename, "type": stype,
            "start_page": range_start, "end_page": prev_page,
            "version": version_for_range(range_start, prev_page),
            "multi_type": has_multi_type(range_start, prev_page),
        })

    def is_plausible(r):
        length = r["end_page"] - r["start_page"] + 1
        if r["type"] == "notes":
            return True
        return length <= 5

    return [r for r in ranges if is_plausible(r)]


if __name__ == "__main__":
    import gc

    folder = "data"
    all_results = []

    for filename in os.listdir(folder):
        if filename.lower().endswith(".pdf"):
            print(f"Processing: {filename} ...")
            pdf_path = os.path.join(folder, filename)
            results = classify_pdf(pdf_path)

            # NEW: automatic retry, right here, instead of making the
            # person manually rerun the whole script -- some large
            # files consistently lose balance_sheet/profit_and_loss on
            # the first pass in a long batch (accumulated memory
            # pressure across many big PDFs). Retrying just THIS one
            # file, fresh, usually recovers it.
            types_found = {t for r in results for t in r["types"]}
            attempt = 1
            while ("balance_sheet" not in types_found or "profit_and_loss" not in types_found or "cash_flow" not in types_found) and attempt < 3:
                print(f"    Retrying {filename} (attempt {attempt + 1}) -- missing balance_sheet/profit_and_loss/cash_flow...")
                gc.collect()
                results = classify_pdf(pdf_path)
                types_found = {t for r in results for t in r["types"]}
                attempt += 1

            for r in results:
                if r["types"] == ["other"]:
                    continue
                all_results.append({
                    "filename": filename,
                    "page": r["page"],
                    "type": ", ".join(r["types"]),
                    "version": r["version"],
                })
            # NEW: force cleanup between FILES, not just between pages
            # within one file. Running through many large (200+ page)
            # annual reports back-to-back can accumulate memory
            # pressure that the existing per-page cleanup doesn't fully
            # release, occasionally causing a later large file (e.g.
            # the 8th file in a batch of 17) to silently lose some of
            # its detected statement types.
            del results
            gc.collect()

    os.makedirs("output", exist_ok=True)
    with open("output/output_classification_v2.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "page", "type", "version"])
        writer.writeheader()
        writer.writerows(all_results)

    print("Done! Result saved to 'output/output_classification_v2.csv'.")

    df = pd.read_csv("output/output_classification_v2.csv")

    # FIX: a single page can genuinely belong to TWO statement types at
    # once -- e.g. "Consolidated Statement of Changes in Equity" and
    # "Consolidated Statement of Cash Flows" printed side-by-side as two
    # columns on the same page (this is exactly what was happening in
    # Engro's report, and silently dropped changes_in_equity entirely).
    #
    # The OLD logic only looked at page_types[0] -- the first type in
    # the list -- when building contiguous ranges, so any statement
    # type that wasn't first on a shared page just vanished. The fix:
    # build ranges for EACH statement type independently, checking
    # whether that type is anywhere in the page's type list, not just
    # whether it's the first one.
    ALL_STATEMENT_TYPES = ["balance_sheet", "profit_and_loss", "cash_flow", "changes_in_equity", "notes"]

    ranges = []
    for filename in df["filename"].unique():
        company_df = df[df["filename"] == filename].sort_values("page")
        page_type_lists = {
            row["page"]: str(row["type"]).split(", ") for _, row in company_df.iterrows()
        }
        page_versions = {
            row["page"]: row["version"] for _, row in company_df.iterrows()
        }
        ranges.extend(build_ranges_for_pages(filename, page_type_lists, page_versions))

    ranges_df = pd.DataFrame(ranges)

    ranges_df.to_csv("output/output_page_ranges_v2.csv", index=False)
    print("Page ranges also saved to 'output/output_page_ranges_v2.csv'!")

    print("\n=== Quick Check: Statements found per company ===")
    for filename in ranges_df["filename"].unique():
        types_found = ranges_df[ranges_df["filename"] == filename]["type"].unique().tolist()
        print(f"{filename}: {types_found}")
        # NEW: every company should have balance_sheet, profit_and_loss,
        # AND cash_flow -- if any is missing, flag it loudly rather than
        # letting it pass silently, since this usually means something
        # went wrong during processing (e.g. a memory or resource issue
        # partway through a long batch run). UBL is a known exception --
        # its cash flow data genuinely isn't extractable from that
        # specific PDF (a confirmed, unfixable anomaly in that file),
        # so we don't warn about it every run.
        missing = [
            t for t in ("balance_sheet", "profit_and_loss", "cash_flow")
            if t not in types_found
        ]
        if missing and not ("UBL" in filename and missing == ["cash_flow"]):
            print(f"  ⚠️  WARNING: {filename} is missing {', '.join(missing)}! "
                  f"Try re-running classify_full.py again -- this can happen from a "
                  f"transient issue when processing many large PDFs in one batch.")