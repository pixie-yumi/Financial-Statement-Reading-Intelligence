"""
extract_by_position.py

Purpose: Fallback table extraction using word x-positions when
pdfplumber's table-detection produces broken/merged columns. Groups
words into rows by y-position, then into columns by x-position
clustering. Filters out prose rows, splits embedded note-numbers from
values (e.g. "8 9,951,054,650" -> just "9,951,054,650"), and normalizes
output into the standard 6-column format expected by the rest of the
pipeline.
"""
import re
import pdfplumber


def is_prose_row(label, values):
    if not values and len(label) > 40:
        return True
    has_number = any(re.search(r'\d', v) for v in values)
    if values and not has_number:
        return True
    if len(label.split()) > 12 and not has_number:
        return True
    if "(cid:" in label or any("(cid:" in v for v in values):
        return True
    return False


def _looks_like_bare_report_year(v):
    """A bare 4-digit number matching a plausible report year (e.g.
    '2025', '2024') with no comma formatting."""
    core = v.strip().lstrip("(").rstrip(")")
    return bool(re.fullmatch(r'(19|20)\d{2}', core))


def is_year_contamination_row(values):
    """FIX: page furniture -- a column-header row (e.g. 'Rupees Note'
    sitting on the same line as the '2025'/'2024' year headers) or a
    footer/branding line (e.g. '292 ANNUAL 2025 REPORT') -- can end up
    with real label-looking text paired with the report's own year
    printed nearby, misread as if it were a genuine value. A real
    financial figure is never a bare 4-digit number matching a
    plausible year (1900s/2000s) with no comma -- actual amounts that
    size are always comma-formatted, or clearly outside that narrow
    range -- so a row whose ONLY values look like report years is
    reliably page furniture, not real data."""
    real_values = [v for v in values if v.strip()]
    if not real_values:
        return False
    return all(_looks_like_bare_report_year(v) for v in real_values)


def clean_merged_value(v):
    """If a note-number and the real value got merged together (e.g. '8 9,951,054,650'),
    keep only the real (comma-formatted or larger) number."""
    match = re.match(r'^\s*\d{1,3}(?:\.\d+)*\s+([\d,().\-]+)$', v.strip())
    if match:
        return match.group(1)

    # FIX: a "Rs." currency prefix (e.g. "Rs. 12.60" for a per-share
    # EPS value) gets clustered together with its number since they're
    # close together on the page. The combined string then fails the
    # numeric-value check (it contains letters from "Rs"), silently
    # discarding a genuine value. Strip the prefix so the number
    # underneath is recognized correctly.
    rs_match = re.match(r'^\s*Rs\.?\s*([\d,().\-]+)\s*$', v.strip(), re.IGNORECASE)
    if rs_match:
        return rs_match.group(1)

    return v


def _is_numeric_token(v):
    """A token can only be a real financial value if it contains NO
    letters at all -- just digits, commas, decimal points, minus signs,
    and parentheses. Without this check, a LABEL word that happens to
    end in punctuation (e.g. "Property," from "Property, plant and
    equipment") would have its comma mistaken for a thousands-separator
    and get treated as if it were itself a value -- corrupting the
    entire row."""
    core = v.strip().lstrip("(").rstrip(")")
    return bool(core) and not any(c.isalpha() for c in core)


def is_definitely_real_value(v):
    """Comma-formatted or 4+ digit numbers, or the '-' placeholder --
    unambiguously real financial values, never note references.

    FIX: small values wrapped in parentheses (e.g. "(475)" for a
    dividend payment) were being wrongly rejected, since 3-digit
    numbers without a comma normally look like note references. But
    parentheses ALWAYS mean "negative financial amount" in these
    reports -- a note reference is never shown in parentheses -- so a
    parenthesized number is unambiguously a real value regardless of
    its digit count."""
    v = v.strip()
    if v in ("-", ""):
        return True
    if not _is_numeric_token(v):
        return False
    if v.startswith("(") and v.endswith(")"):
        return True
    core = v.lstrip("(").rstrip(")")
    if "," in core:
        return True
    digits_only = core.replace(".", "").replace("-", "")
    return digits_only.isdigit() and len(digits_only) >= 4 and "." not in core


def is_possible_small_value(v):
    """A single-dot decimal with no comma (e.g. '6.02') -- could be a
    genuine small value like an EPS figure, OR a note sub-reference
    (e.g. '40.1', '4.1.1'). Only used as a FALLBACK when no
    unambiguous values were found on the row, since note sub-references
    look identical to small decimal values by format alone."""
    v = v.strip()
    if not _is_numeric_token(v):
        return False
    core = v.lstrip("(").rstrip(")")
    if core.count(".") != 1:
        return False
    whole, frac = core.split(".")
    return whole.replace("-", "").isdigit() and frac.isdigit()


def looks_like_real_value(v):
    """Distinguishes a genuine financial value ('55,384,267',
    '(409,085)', '-') from a bare note-number ('4', '20', '33') or
    stray contamination text (including label words that happen to end
    in punctuation, e.g. "Property,"). Used to find where a row's
    "values zone" STARTS (see _looks_like_value_start) -- broader than
    is_definitely_real_value, since at that stage we just need to know
    "numbers start here", not which specific token is the real value."""
    v = v.strip()
    if v in ("-", ""):
        return True
    if not _is_numeric_token(v):
        return False
    core = v.lstrip("(").rstrip(")")
    if "," in core or "." in core:
        return True
    digits_only = core.replace("-", "")
    return digits_only.isdigit() and len(digits_only) >= 4


def _looks_like_value_start(text):
    """A word marks the start of the 'values zone' for a row if it's
    either a genuine value, OR a short bare integer (1-3 digits) --
    almost always a note-number reference immediately preceding the
    real value (e.g. the "4" in "Property, plant and equipment 4
    55,384,267")."""
    if looks_like_real_value(text):
        return True
    core = text.lstrip("(").rstrip(")").replace("-", "")
    if core.isdigit() and 1 <= len(core) <= 3:
        return True
    # FIX: a standalone opening parenthesis is never part of a real
    # label -- it's the start of a negative value that got split into
    # its own word token by a font-rendering quirk (the digits and
    # closing paren follow as a separate/merged token right after).
    # Without this, the "(" gets silently absorbed into the label
    # instead of starting the values zone, and the value that's left
    # behind no longer starts with "(" -- so it loses its negative
    # sign entirely (e.g. "(282,788,556)" comes through as label
    # "...shares (" plus a bare positive "282,788,556)").
    if text.strip() == "(":
        return True
    return False


def normalize_row(parts):
    """Converts a fallback row into standard 6-column format: [_, _, label, note, val2025, val2024]

    FIX: decimal note-sub-references like "4.1.1" or "40.1" (very
    common in these reports, e.g. "Depreciation of operating fixed
    assets 4.1.1 5,114,568 4,967,334") were being wrongly picked as the
    REAL value, since they contain a dot and the old check treated any
    dot-containing token as a genuine value -- silently replacing the
    true comma-formatted amount with something like "6.10" or "40.10".

    Fix: prefer UNAMBIGUOUS values (comma-formatted or 4+ digit
    numbers) first. Only fall back to small single-dot decimals (which
    could be a genuine small value like an EPS figure, OR a note
    sub-reference) when no unambiguous values exist on the row at all
    -- e.g. a genuine EPS row has NOTHING else to prefer, so the small
    decimals are correctly used there."""
    label = parts[0] if parts else ""
    cleaned = [clean_merged_value(p) for p in parts[1:]]

    # FIX: a dash placeholder ("-" or "–", meaning "no value this
    # year") immediately followed by the REAL value for the other year
    # can get clustered together as one token (e.g. "– 27,734,821"),
    # since they're close together on the page. Left as one string,
    # neither the dash-prefix nor the whole merged string parses as a
    # valid number, and the real value gets silently discarded. Split
    # any such merged token into its two real parts.
    split_cleaned = []
    for v in cleaned:
        dash_split = re.match(r'^\s*[-–—]\s+([\d,().]+)\s*$', v)
        if dash_split:
            split_cleaned.append("-")
            split_cleaned.append(dash_split.group(1))
        else:
            split_cleaned.append(v)
    cleaned = split_cleaned

    definite_values = [v for v in cleaned if is_definitely_real_value(v)]
    if len(definite_values) >= 2:
        v2025, v2024 = definite_values[0], definite_values[1]
    elif len(definite_values) == 1:
        # FIX: a genuine small value under 1000 without comma
        # formatting (e.g. "607") fails is_definitely_real_value's
        # 4+-digit requirement, so it was being silently dropped
        # entirely whenever the OTHER year's value was a normal
        # comma-formatted number -- e.g. "Depreciation of right of use
        # assets 6 607 2,246" (note "6", then "607" for 2025, "2,246"
        # for 2024) was losing the "607" and even misplacing "2,246"
        # into the wrong year. The token immediately BEFORE the one
        # definite value in the row (not just anywhere in it) is the
        # most likely candidate for this -- a note-number reference
        # sits further back, right after the label, not adjacent to
        # the real value.
        idx = cleaned.index(definite_values[0])
        candidate = cleaned[idx - 1] if idx > 0 else None
        if candidate is not None and re.fullmatch(r'-?\d{3}', candidate.lstrip("(").rstrip(")")):
            v2025, v2024 = candidate, definite_values[0]
        else:
            v2025, v2024 = definite_values[0], ""
    else:
        small_values = [v for v in cleaned if is_possible_small_value(v)]
        if len(small_values) >= 2:
            v2025, v2024 = small_values[0], small_values[1]
        elif len(small_values) == 1:
            v2025, v2024 = small_values[0], ""
        else:
            v2025, v2024 = "", ""

    return ["", "", label, "", v2025, v2024]


def detect_column_split(words, page_width):
    """Detects if a page has TWO STATEMENTS printed side-by-side as
    columns (common for a Consolidated Balance Sheet + Income
    Statement sharing one page). Looks for a wide empty gap in word
    x-positions somewhere near the middle of the page, THEN verifies
    that content actually resumes with its OWN label-like text right
    after the gap.

    FIX: the gap alone isn't enough -- a completely normal
    SINGLE-column table also has a big gap between its label column and
    its value columns (e.g. "Property, plant and equipment" ... big gap
    ... "55,384,267"). That gap was being mistaken for a column split,
    corrupting perfectly fine single-column pages by chopping them into
    a fake "left half" (labels only) and "right half" (values only,
    with no labels) and processing them separately.

    The real distinguishing feature: on a genuine two-column page, the
    content RIGHT AFTER the gap is itself label-like TEXT (a second
    statement's own line-item names) -- not just more numbers. On a
    single-column page, whatever comes after the label-value gap is
    just the numeric value columns. So after finding a candidate gap,
    we check whether a meaningful share of the words immediately
    following it actually contain letters (i.e. look like the START of
    a new label column) rather than being purely numeric."""
    if not words:
        return None
    xs = sorted(set(round(w["x0"]) for w in words))
    mid_low, mid_high = page_width * 0.3, page_width * 0.7
    candidates = [x for x in xs if mid_low <= x <= mid_high]
    if len(candidates) < 2:
        return None
    gaps = [
        (candidates[i + 1] - candidates[i], (candidates[i] + candidates[i + 1]) / 2)
        for i in range(len(candidates) - 1)
    ]
    if not gaps:
        return None
    biggest_gap, split_point = max(gaps, key=lambda g: g[0])
    if biggest_gap <= page_width * 0.04:
        return None

    # Verify: does content right after the gap look like a fresh label
    # column (has real text), or is it just more numbers (a single
    # table's value columns)?
    near_split_words = [
        w for w in words
        if split_point <= w["x0"] <= split_point + 250
    ]
    if not near_split_words:
        return None
    text_like = sum(1 for w in near_split_words if any(c.isalpha() for c in w["text"]))
    if text_like / len(near_split_words) < 0.3:
        return None  # mostly numbers right after the gap -- single column, not a real split

    return split_point


# A gap this small between two consecutive word tokens is a
# font-rendering artifact (same family as the NETSOL "Profi t" kerning
# bug), not a real space -- e.g. a single value like "328,594,122"
# occasionally comes back from pdfplumber as TWO words, "3" and
# "28,594,122". Left with a space between them, clean_merged_value()'s
# note-number regex mistakes the leading "3" for a note reference and
# silently strips it, dropping the leading digit off the real value.
GLUE_THRESHOLD = 2  # points


def _join_cluster_words(cluster):
    """Joins a cluster's words into one string, using NO space when two
    consecutive words are close enough to be the same rendered number
    split apart by a font glitch, and a normal space otherwise (e.g. a
    genuine note-number followed by its value)."""
    parts = [cluster[0]["text"]]
    for prev_w, curr_w in zip(cluster, cluster[1:]):
        gap = curr_w["x0"] - prev_w["x1"]
        parts.append(curr_w["text"] if gap < GLUE_THRESHOLD else " " + curr_w["text"])
    return "".join(parts)


def _extract_rows_from_words(words, y_tolerance=3):
    """Given a set of words (already scoped to ONE column -- or the
    whole page, if it's single-column), groups them into rows by
    y-position and splits each row into label vs values DYNAMICALLY,
    based on where the first value/note-number-like token appears --
    rather than a fixed absolute x-position threshold.

    FIX: the old approach used a hardcoded "label if x0 < 350" rule.
    That was calibrated for a LEFT column starting near x0=0, but on a
    two-column page the RIGHT column's own labels can start at x0=600+
    (e.g. "Revenue from contracts with customers" at x0=659) -- so they
    got misclassified as "values" entirely, and Income Statement lines
    like Revenue, Cost of Sales, and Gross Profit were silently
    disappearing. Finding the label/value boundary dynamically (via the
    first value-like token) works correctly regardless of which column
    these words came from."""
    if not words:
        return []

    sorted_words = sorted(words, key=lambda w: w["top"])
    row_groups = []
    for w in sorted_words:
        # FIX: comparing against a FIXED first-word anchor (not a
        # continuously-updated running average) prevents small gaps
        # between many consecutive lines from "chain-drifting" into
        # one giant merged row.
        if row_groups and abs(w["top"] - row_groups[-1]["anchor_top"]) <= y_tolerance:
            row_groups[-1]["words"].append(w)
        else:
            row_groups.append({"anchor_top": w["top"], "words": [w]})

    result_rows = []
    row_data = []  # (label, clusters_with_x0) -- collected first for calibration

    for group in row_groups:
        row_words = sorted(group["words"], key=lambda w: w["x0"])

        # FIX: some PDFs (bank financial statements especially) print a
        # supplementary numeric column BEFORE the label -- e.g. JS
        # Bank shows a USD-equivalent figure to the LEFT of "Cash and
        # balances with treasury banks", in addition to the normal
        # Rupees columns on the right. Scanning strictly left-to-right
        # for "the first value-like token" used to hit that leading
        # number at index 0 immediately, making split_idx=0 and
        # swallowing the ENTIRE row -- including the real label -- into
        # "values", leaving every single line item with an empty label.
        # Anchoring the scan at the first word that actually contains a
        # letter (real label text always does) finds the true label
        # start correctly. Any purely-numeric tokens sitting before
        # that point are simply left out of both label and values --
        # this pipeline only ever needs ONE currency's figures (the
        # Rupees columns, matching every other company), so the extra
        # USD column is intentionally dropped, not misread. Every other
        # company's rows are completely unaffected, since their label
        # already legitimately starts at index 0.
        label_start_idx = 0
        for i, w in enumerate(row_words):
            if any(c.isalpha() for c in w["text"]):
                label_start_idx = i
                break

        scan_words = row_words[label_start_idx:]

        split_idx = len(scan_words)
        for i, w in enumerate(scan_words):
            # FIX: a bare "-" is normally a genuine "no value" placeholder
            # (e.g. a blank year column), but it's ALSO used as a plain
            # continuation marker before a word -- e.g. "Reserves -
            # capital" / "- revenue" (a sub-line continuing the
            # "Reserves" label from the row above, not repeating the
            # word "Reserves" itself). Treating that "-" as the start
            # of the values zone emptied the label entirely, silently
            # dropping the whole "- revenue" reserves line. If "-" is
            # immediately followed by an alphabetic WORD (not another
            # number), it's part of the label, not a value.
            # FIX: a hyphenated word (e.g. "stock-in-trade", "right-of-
            # use", "mark-up") fails .isalpha() since it contains
            # hyphens, not just letters -- so a label ending "- stock-
            # in-trade" wasn't recognized as a continuation, and the
            # "-" got wrongly treated as a value-start instead,
            # truncating the label right before it (e.g. "Reversal of
            # provison for slow moving" lost its "- stock-in-trade"
            # tail entirely). Checking for letters-and-internal-hyphens
            # instead of pure letters catches this without accepting
            # genuine value tokens (which contain digits/commas/parens,
            # never just letters and hyphens).
            if w["text"] == "-" and i + 1 < len(scan_words) and re.fullmatch(r"[A-Za-z]+(-[A-Za-z]+)*", scan_words[i + 1]["text"]):
                continue
            if _looks_like_value_start(w["text"]):
                split_idx = i
                break

        label_words = scan_words[:split_idx]
        value_words = scan_words[split_idx:]

        label = " ".join(w["text"] for w in label_words)

        clusters = []
        for w in value_words:
            if clusters and (w["x0"] - clusters[-1][-1]["x0"]) < 40:
                clusters[-1].append(w)
            else:
                clusters.append([w])

        # keep each cluster's own x0 (its first word's position) so we
        # can tell WHICH year-column a lone value belongs to later.
        # Also normalize Unicode dash variants (en-dash "–", em-dash
        # "—") to a plain ASCII "-" here -- some PDFs use these for the
        # "no value this year" placeholder instead of a regular hyphen,
        # and our value-recognition logic only checks for ASCII "-".
        clusters_with_x0 = [
            (c[0]["x0"], _join_cluster_words(c).replace("\u2013", "-").replace("\u2014", "-"))
            for c in clusters
        ]
        row_data.append((label, clusters_with_x0))

    # PASS 1: calibrate the typical x-position of the "2025" (left) and
    # "2024" (right) value columns, using rows that have BOTH values --
    # these unambiguously show where each column actually sits on this
    # specific page.
    left_xs = [c[0][0] for _, c in row_data if len(c) >= 2]
    right_xs = [c[1][0] for _, c in row_data if len(c) >= 2]
    typical_left_x = sorted(left_xs)[len(left_xs) // 2] if left_xs else None
    typical_right_x = sorted(right_xs)[len(right_xs) // 2] if right_xs else None

    # PASS 2: build final rows. A row with only ONE value is ambiguous
    # by count alone -- it could be the 2025 figure (2024 blank) OR the
    # 2024 figure (2025 blank, e.g. a line item that's new this year).
    #
    # FIX: previously we always assumed a lone value was for 2025 --
    # wrong whenever the blank year was 2025 itself and the ONLY
    # extractable text was the 2024 figure (this happens when the PDF
    # doesn't render an explicit "-" placeholder for the blank cell as
    # its own text token at all). Comparing the value's actual x-
    # position against the page's calibrated column positions tells us
    # which column it truly belongs to.
    for label, clusters_with_x0 in row_data:
        if len(clusters_with_x0) == 1 and typical_left_x is not None and typical_right_x is not None:
            value_x0, value_text = clusters_with_x0[0]
            if abs(value_x0 - typical_right_x) < abs(value_x0 - typical_left_x):
                values = ["", value_text]
            else:
                values = [value_text, ""]
        else:
            values = [v for _, v in clusters_with_x0]

        if not (label.strip() or values):
            continue
        if is_prose_row(label, values):
            continue
        if is_year_contamination_row(values):
            continue

        result_rows.append(normalize_row([label] + values))

    return result_rows


def extract_rows_by_position(pdf_path, page_num, x_tolerance=3, y_tolerance=3, force_split=None):
    """force_split: if True/False, this OVERRIDES the geometric
    detection entirely, using the reliable "does this page have 2+
    statement types" signal already computed during Statement ID
    (see classify_full.py's has_multi_type) instead of re-guessing
    from word positions, which can't reliably tell apart a genuine
    two-statement page from a single statement whose own sections are
    just laid out in two visual columns (e.g. Assets left / Equity &
    Liabilities right). If None, falls back to the geometric+text
    heuristic (used when this info isn't available, e.g. direct calls
    outside the normal pipeline)."""
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]
        words = page.extract_words(extra_attrs=["fontname"])
        page_width = page.width

    if not words:
        return []

    if force_split is True:
        xs = sorted(set(round(w["x0"]) for w in words))
        mid_low, mid_high = page_width * 0.3, page_width * 0.7
        candidates = [x for x in xs if mid_low <= x <= mid_high]
        gaps = [
            (candidates[i + 1] - candidates[i], (candidates[i] + candidates[i + 1]) / 2)
            for i in range(len(candidates) - 1)
        ] if len(candidates) >= 2 else []
        split_x = max(gaps, key=lambda g: g[0])[1] if gaps else None
    elif force_split is False:
        split_x = None
    else:
        split_x = detect_column_split(words, page_width)

    if split_x is None:
        return _extract_rows_from_words(words, y_tolerance)

    left_words = [w for w in words if w["x0"] < split_x]
    right_words = [w for w in words if w["x0"] >= split_x]

    return (
        _extract_rows_from_words(left_words, y_tolerance)
        + _extract_rows_from_words(right_words, y_tolerance)
    )


def extract_rows_by_position_for_range(pdf_path, start_page, end_page, force_split=None):
    """Multi-page range ke liye position-based extraction"""
    all_rows = []
    for page_num in range(int(start_page), int(end_page) + 1):
        rows = extract_rows_by_position(pdf_path, page_num, force_split=force_split)
        all_rows.extend(rows)
    return all_rows


if __name__ == "__main__":
    import os
    _here = os.path.dirname(os.path.abspath(__file__))
    _pdf_path = os.path.join(_here, "..", "sample_pdfs", "UBL.pdf")
    rows = extract_rows_by_position(_pdf_path, 42)
    for r in rows:
        print(r)