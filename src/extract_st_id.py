import pdfplumber
import os

def extract_pages(pdf_path):
    """Returns a dict: {page_number: page_text}"""
    page_texts = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            page_texts[i] = text
    return page_texts


# ---------------------------------------------------------------------
# NEW: bold-heading extraction (fixes "statement always missing" bug)
#
# WHY: plain extract_text() reads a page in flat reading order. When a
# page has TWO STATEMENTS SIDE BY SIDE as columns (very common in
# Pakistani annual reports -- e.g. Balance Sheet and Income Statement
# printed next to each other), extract_text() can interleave the two
# columns' words, breaking multi-word headings like "statement of
# financial position" into a scrambled order that keyword matching
# never finds -- even though the statement genuinely is on that page.
#
# Fix: read WORD-LEVEL position + font data directly. Real headings in
# these PDFs use a BOLD font variant (e.g. "Montserrat-Bold") even when
# printed at the SAME size as body text -- plain text extraction can't
# see this at all. We also merge consecutive bold lines into one block,
# since headings are often split across two lines (e.g.
# "UNCONSOLIDATED STATEMENT" / "OF FINANCIAL POSITION").
# ---------------------------------------------------------------------

def _is_bold_fontname(fontname):
    return "bold" in fontname.lower()


def _group_words_into_lines(words):
    lines = {}
    for w in words:
        top = round(w["top"], 1)
        lines.setdefault(top, []).append(w)
    sorted_lines = []
    for top in sorted(lines.keys()):
        line_words = sorted(lines[top], key=lambda w: w["x0"])
        text = " ".join(w["text"] for w in line_words)
        bold_count = sum(1 for w in line_words if _is_bold_fontname(w["fontname"]))
        is_bold_line = bold_count >= len(line_words) / 2
        sorted_lines.append({"text": text, "is_bold": is_bold_line})
    return sorted_lines


def extract_page_bold_blocks(page):
    """Given a single pdfplumber page object, return text blocks made of
    consecutive bold lines (our best signal for real headings)."""
    words = page.extract_words(extra_attrs=["size", "fontname"])
    lines = _group_words_into_lines(words)

    blocks = []
    current_block = []
    for line in lines:
        if line["is_bold"] and line["text"].strip():
            current_block.append(line["text"].strip())
        else:
            if current_block:
                blocks.append(" ".join(current_block))
                current_block = []
    if current_block:
        blocks.append(" ".join(current_block))
    return blocks


def extract_pages_full(pdf_path):
    """Returns {page_number: {"text": ..., "bold_blocks": [...]}} --
    same page numbering as extract_pages(), plus bold-heading blocks
    for more reliable statement detection.

    NOTE: flushes each page's internal cache after processing, and runs
    periodic garbage collection. Without this, pdfplumber accumulates
    rendering data per page and can run out of memory on large annual
    reports (200+ pages), even though smaller PDFs work fine."""
    import gc
    result = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            bold_blocks = extract_page_bold_blocks(page)
            result[i] = {"text": text, "bold_blocks": bold_blocks}
            page.flush_cache()
            if i % 50 == 0:
                gc.collect()
    return result


if __name__ == "__main__":
    data_folder = "data"
    pdf_files = [f for f in os.listdir(data_folder) if f.endswith(".pdf")]

    print(f"Found {len(pdf_files)} PDFs: {pdf_files}\n")

    all_results = {}

    for pdf_file in pdf_files:
        pdf_path = os.path.join(data_folder, pdf_file)
        print(f"Extracting: {pdf_file} ...")
        pages = extract_pages(pdf_path)
        all_results[pdf_file] = pages

        # count how many pages actually have text vs empty/scanned
        non_empty = sum(1 for t in pages.values() if t.strip())
        print(f"  -> {len(pages)} total pages, {non_empty} pages with readable text\n")

    print("=" * 50)
    print("DONE. Summary:")
    for pdf_file, pages in all_results.items():
        non_empty = sum(1 for t in pages.values() if t.strip())
        print(f"{pdf_file}: {len(pages)} pages ({non_empty} readable)")