# Financial Statement Reading Intelligence

**[Live Demo](https://financial-statement-reading-intelligence-v7fqcifx3rxwqzhkbsch8.streamlit.app/)** — click through a company's financials or ask questions in natural language.

A 4-stage pipeline for extracting structured financial data from Pakistani company annual reports, built during an internship at SBP. Includes an interactive dashboard and natural-language query layer on top of the extracted data.

## Current Status

This project covers correct identification and extraction of financial statements from raw PDFs — Statement Identification, Table Identification, Header Identification, and Value Extraction — plus a query layer for asking questions about the extracted data in plain English.

## Pipeline Stages

1. **Statement Identification** — classifies each PDF page as Balance Sheet, Income Statement, Cash Flow, or other
2. **Table Identification** — locates and extracts the tabular data within identified statement pages
3. **Header Identification** — matches raw line-item labels to a standardized category set using fuzzy matching
4. **Value Extraction** — parses and cleans raw numeric strings into usable values, handling negatives, currency formatting, and edge cases

## Query Layer

A rule-based natural-language query interface sits on top of the extracted data — ask things like *"what was revenue for Abbott Labs in 2025"* and get a direct answer, without writing a filter or scrolling a spreadsheet. Built with `rapidfuzz` for fuzzy line-item matching, evaluated on a 24-case test suite: **91.7% accuracy**, with documented failure modes around word-order sensitivity and semantically-similar-but-opposite line items (e.g. "dividend paid" vs. "unclaimed dividend").

## Tech

Python, pdfplumber, PyMuPDF, rapidfuzz, regex, pandas, Streamlit
