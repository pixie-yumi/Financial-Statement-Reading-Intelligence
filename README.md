# Financial Statement Reading Intelligence

A 4-stage pipeline for extracting structured financial data from Pakistani company annual reports, built during a Data Engineering internship at SBP.

## Current Status

This project currently covers correct identification and extraction of financial statements from raw PDFs — Statement Identification, Table Identification, Header Identification, and Value Extraction. Downstream analysis on top of the extracted data is not yet built.

## Pipeline Stages

1. **Statement Identification** — classifies each PDF page as Balance Sheet, Income Statement, Cash Flow, or other
2. **Table Identification** — locates and extracts the tabular data within identified statement pages
3. **Header Identification** — matches raw line-item labels to a standardized category set using fuzzy matching
4. **Value Extraction** — parses and cleans raw numeric strings into usable values, handling negatives, currency formatting, and edge cases

## Tech

Python, pdfplumber, rapidfuzz, regex, pandas
