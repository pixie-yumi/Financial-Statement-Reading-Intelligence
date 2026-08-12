"""
diagnose_new_pdf.py

Purpose: Runs Statement ID's classify_page() logic across EVERY page of
a given PDF and prints what got matched, so we can see:
  1. Which pages got classified as balance_sheet/profit_and_loss/
     cash_flow/notes/other
  2. WHY a page got misclassified (e.g. a notes page mistakenly tagged
     as balance_sheet)
  3. Whether the REAL statement pages exist somewhere but got
     classified as "notes" or "other" instead

Reusable for any new PDF, not just one specific company -- pass the
path as a command-line argument, or it'll prompt for one.
"""
import sys
import os
import pandas as pd
from extract_st_id import extract_pages_full
from classify_full import classify_page, detect_version


def find_phrase_hits(pdf_path, phrases):
    """Directly searches every page's raw extracted text for the given
    phrases -- bypassing classify_page() entirely -- to find out WHERE
    a statement's real title actually exists in the document, and what
    classify_page() decided for that exact page. Useful when a
    statement never gets classified correctly anywhere, so we can see
    the real surrounding text instead of guessing."""
    pages = extract_pages_full(pdf_path)
    print(f"\n=== Searching raw text for: {phrases} ===\n")
    for page_num, page_data in sorted(pages.items()):
        text = page_data["text"]
        text_lower = text.lower()
        for phrase in phrases:
            if phrase in text_lower:
                labels = classify_page(text, page_data["bold_blocks"])
                idx = text_lower.find(phrase)
                context = text[max(0, idx - 40):idx + 120].replace("\n", " | ")
                print(f"  Page {page_num}: FOUND '{phrase}'")
                print(f"    classify_page() returned: {labels}")
                print(f"    Context: ...{context}...\n")


def find_page_by_number(pdf_path, distinctive_number):
    """When a statement's TITLE can't be found anywhere (as we just
    discovered for this PDF), locate it a different way: search for one
    of its actual, highly distinctive NUMBERS instead -- e.g. a Total
    Assets or Total Equity figure that's extremely unlikely to appear
    coincidentally anywhere else in the document. This pinpoints the
    real page regardless of whatever is wrong with the title text."""
    pages = extract_pages_full(pdf_path)
    print(f"\n=== Searching for distinctive number: '{distinctive_number}' ===\n")
    found_any = False
    for page_num, page_data in sorted(pages.items()):
        text = page_data["text"]
        if distinctive_number in text:
            found_any = True
            labels = classify_page(text, page_data["bold_blocks"])
            print(f"  Page {page_num}: FOUND '{distinctive_number}'")
            print(f"    classify_page() returned: {labels}")
            print(f"    First 200 chars of page text: {text[:200]!r}")
            print(f"    Bold blocks on this page: {page_data['bold_blocks'][:5]}")
            print()
    if not found_any:
        print(f"  Not found anywhere in the document -- double check the exact digits/formatting.")


def diagnose(pdf_path):
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        return

    print(f"Reading: {pdf_path} ...\n")
    pages = extract_pages_full(pdf_path)
    print(f"Total pages: {len(pages)}\n")

    rows = []
    for page_num, page_data in sorted(pages.items()):
        text = page_data["text"]
        labels = classify_page(text, page_data["bold_blocks"])
        version = detect_version(text)
        first_line = text.strip().split("\n")[0][:80] if text.strip() else "(empty page)"
        rows.append({
            "page": page_num, "labels": ", ".join(labels), "version": version,
            "first_line": first_line
        })

    df = pd.DataFrame(rows)

    print("=== Every page classified as balance_sheet / profit_and_loss / cash_flow ===\n")
    core = df[df["labels"].str.contains("balance_sheet|profit_and_loss|cash_flow", regex=True)]
    print(core.to_string(index=False))

    print("\n=== Full page-by-page classification ===\n")
    print(df.to_string(index=False))

    df.to_csv("output/new_pdf_diagnosis.csv", index=False)
    print("\nFull breakdown saved to: output/new_pdf_diagnosis.csv")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = input("Enter path to the PDF: ").strip().strip('"')
    diagnose(path)
    find_phrase_hits(path, [
        "statement of financial position",
        "statement of profit or loss",
        "statement of comprehensive income",
        "statement of cash flows",
    ])
    # Total Assets from the screenshot (9,037,276) -- a number this
    # specific won't appear anywhere else in the document by chance.
    find_page_by_number(path, "9,037,276")