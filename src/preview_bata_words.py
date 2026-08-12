"""
preview_bata_words.py

Purpose: Extract words with their x-position from BATA's P&L page,
to reconstruct columns based on horizontal position instead of
pdfplumber's table-detection (which is failing on this tight layout).
"""
import pdfplumber

with pdfplumber.open(r"C:\Users\ASUS\Downloads\BATA Pakistan.pdf") as pdf:
    page = pdf.pages[89]
    words = page.extract_words()
    for w in words[:40]:
        print(round(w['x0']), '|', w['text'])