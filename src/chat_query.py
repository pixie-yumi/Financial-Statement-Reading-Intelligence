"""
chat_query.py

Purpose: A lightweight, chat-style front-end over the EXISTING query()
function in query_engine.py. Not a real LLM chatbot -- just a small
parser that pulls (company, year, line_item) out of a natural-language
question, then calls the same rule-based lookup logic already used by
the numbered-list mode. Keeps FinSight's whole identity as a
rule-based NLP pipeline, no external API calls needed.

Only searches the CATEGORIZED results (RESULTS_PATH) for now -- not
the raw/uncategorized line items.
"""
import re
from rapidfuzz import fuzz

from query_engine import load_results, query, print_result

YEAR_PATTERN = re.compile(r"\b(2024|2025)\b")

FILLER_WORDS = {
    "what", "was", "were", "is", "the", "for", "in", "of", "a", "an",
    "did", "how", "much", "value", "line", "item", "please", "show",
    "me", "tell", "and", "to", "on", "at",
}


def extract_year(text):
    match = YEAR_PATTERN.search(text)
    return match.group(1) if match else None


def extract_company(text, results_df, threshold=60):
    """Fuzzy-matches against known filenames, same style as query()'s
    own company matching -- but scans the whole sentence since the
    question is natural language, not just a company name."""
    companies = results_df["filename"].unique()
    best_company, best_score = None, 0

    for company in companies:
        clean_name = company.replace(".pdf", "")
        score = fuzz.partial_ratio(clean_name.lower(), text.lower())
        if score > best_score:
            best_score, best_company = score, clean_name

    if best_score >= threshold:
        return best_company, best_score
    return None, 0


def extract_line_item(text, company_text, year):
    """Whatever's left after removing the matched company name, the
    year, and common filler words is treated as the line item."""
    cleaned = text.lower()
    if company_text:
        cleaned = cleaned.replace(company_text.lower(), "")
    if year:
        cleaned = cleaned.replace(year, "")

    words = re.findall(r"[a-zA-Z]+", cleaned)
    kept = [w for w in words if w not in FILLER_WORDS]
    return " ".join(kept).strip()


def parse_question(text, results_df):
    year = extract_year(text)
    company, company_score = extract_company(text, results_df)
    line_item = extract_line_item(text, company or "", year or "")
    return company, year, line_item


def run_chat():
    print("=== FinSight Chat Query (beta) ===")
    print("Ask things like: 'what was revenue for Abbott Labs in 2025'")
    print("Type 'quit' to exit.\n")

    results_df = load_results()
    if results_df.empty:
        print("No processed data found. Run the main pipeline first.\n")
        return

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if question.lower() == "quit":
            break
        if not question:
            continue

        company, year, line_item = parse_question(question, results_df)

        if not company:
            print("  Couldn't figure out which company you mean. Try including the company name more clearly.\n")
            continue
        if not year:
            print("  Couldn't figure out which year you mean (I only know 2024 / 2025 right now).\n")
            continue
        if not line_item:
            print("  Couldn't figure out which line item you're asking about.\n")
            continue

        result = query(company, year, line_item, results_df)
        print_result(result)


if __name__ == "__main__":
    run_chat()