"""
test_clean_value.py

Purpose: Quick test for the clean_value() function — verifies that raw
numeric strings from extracted tables (with commas, brackets for
negatives, and dashes for empty values) get converted correctly into
clean Python numbers, before applying this logic to the full Value
Extraction pipeline.
"""


def clean_value(raw):
    """Extracts a clean numeric value from the raw string"""
    if not raw or raw.strip() in ("-", ""):
        return None

    raw = raw.strip().replace(",", "")

    is_negative = raw.startswith("(") and raw.endswith(")")
    if is_negative:
        raw = raw[1:-1]

    try:
        value = float(raw)
        return -value if is_negative else value
    except ValueError:
        return None


if __name__ == "__main__":
    test_values = ["37,340,023", "(48,022)", "-", "", "1,234.56", "abc"]
    print("Testing clean_value():\n")
    for v in test_values:
        print(f"'{v}' -> {clean_value(v)}")