"""
eval_query.py

Purpose: Accuracy evaluation for query(). Runs a fixed test set of
(company, year, stype, line_item) -> expected outcome pairs and
reports overall accuracy, plus saves a bar chart alongside the main
pipeline's other evaluation graphs. This is the evaluation layer for
the chatbot/dashboard query feature -- mirrors the same rigor as the
main pipeline's stage-by-stage accuracy metrics.

Run with: python eval_query.py
"""
import matplotlib.pyplot as plt

from query_engine import load_results, query

results_df = load_results()

# Each test case: (company, year, stype, line_item, expected_found, expected_value_or_None)
# expected_value is only checked when expected_found is True.
TEST_CASES = [
    # --- Balance sheet: exact/near-exact category matches ---
    ("Abbott Labs", "2025", "balance_sheet", "total assets", True, 46816196.0),
    ("Abbott Labs", "2025", "balance_sheet", "revenue", True, 28572553.0),
    ("Attock Cement", "2025", "balance_sheet", "total assets", True, 50421714.0),
    ("Engro", "2025", "balance_sheet", "total assets", True, 199166075.0),
    ("Fauji Fertilizers", "2025", "balance_sheet", "total assets", True, 613298162.0),
    ("Indus Motor", "2025", "balance_sheet", "total assets", True, 184774378.0),
    ("Nishat", "2025", "balance_sheet", "total assets", True, 300268877.0),

    # --- Cash flow: exact/near-exact matches ---
    ("Abbott Labs", "2025", "cash_flow", "taxes paid", True, -5019980.0),
    ("Abbott Labs", "2025", "cash_flow", "dividend paid", True, -971563.0),
    ("Abbott Labs", "2025", "cash_flow", "finance cost paid", True, -9201.0),
    ("Abbott Labs", "2025", "cash_flow", "interest income received", True, 535097.0),
    ("Abbott Labs", "2025", "cash_flow", "cash generated from operations", True, 16074607.0),

    # --- Fuzzy / imprecise phrasing (should still resolve correctly) ---
    ("Abbott Labs", "2025", "cash_flow", "cash generated", True, 16074607.0),
    ("Abbott Labs", "2025", "cash_flow", "taxes", True, -5019980.0),
    ("Abbott Labs", "2025", "balance_sheet", "assets total", True, 46816196.0),

    # --- Negative cases: wrong statement type should correctly reject ---
    ("Abbott Labs", "2025", "cash_flow", "total assets", False, None),
    ("Abbott Labs", "2025", "balance_sheet", "dividend paid", False, None),
    ("Attock Cement", "2025", "cash_flow", "total assets", False, None),

    # --- Negative cases: nonsense / nonexistent line items ---
    ("Abbott Labs", "2025", "balance_sheet", "zzz not a real line item", False, None),
    ("Abbott Labs", "2025", "cash_flow", "unicorn profits", False, None),

    # --- Negative cases: nonexistent company ---
    ("Totally Fake Company", "2025", "balance_sheet", "revenue", False, None),
    ("Made Up Corp", "2025", "cash_flow", "total assets", False, None),

    # --- Year variation ---
    ("Abbott Labs", "2024", "balance_sheet", "total assets", True, 37651158.0),
    ("Abbott Labs", "2024", "cash_flow", "dividend paid", True, -1030464.0),
]


def plot_results(passed, failed, accuracy):
    fig, ax = plt.subplots(figsize=(5, 5))
    labels = ["Passed", "Failed"]
    values = [passed, failed]
    colors = ["#2ecc71", "#e74c3c"]

    ax.bar(labels, values, color=colors)
    ax.set_title(f"Query Layer Accuracy: {accuracy:.1f}%")
    ax.set_ylabel("Number of Test Cases")
    for i, v in enumerate(values):
        ax.text(i, v + 0.3, str(v), ha="center", fontweight="bold")

    plt.tight_layout()
    plt.savefig("output/graphs/query_eval_accuracy.png", dpi=150)
    print("Saved chart to output/graphs/query_eval_accuracy.png")


def run_eval():
    passed = 0
    failed = 0
    failures = []

    for company, year, stype, line_item, expected_found, expected_value in TEST_CASES:
        result = query(company, year, line_item, results_df, stype=stype)

        ok = result["found"] == expected_found
        if ok and expected_found and expected_value is not None:
            ok = result.get("value") == expected_value

        if ok:
            passed += 1
        else:
            failed += 1
            failures.append({
                "company": company, "year": year, "stype": stype, "line_item": line_item,
                "expected_found": expected_found, "expected_value": expected_value,
                "actual_found": result["found"], "actual_value": result.get("value"),
                "message": result.get("message", ""),
            })

    total = passed + failed
    accuracy = (passed / total * 100) if total else 0

    print(f"=== Query Accuracy Eval ===\n")
    print(f"Total test cases: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Accuracy: {accuracy:.1f}%\n")

    if failures:
        print("--- Failures ---")
        for f in failures:
            print(f"  {f['company']} | {f['stype']} | '{f['line_item']}'")
            print(f"    expected: found={f['expected_found']}, value={f['expected_value']}")
            print(f"    actual:   found={f['actual_found']}, value={f['actual_value']}")
            if f["message"]:
                print(f"    message:  {f['message']}")
            print()

    plot_results(passed, failed, accuracy)
    return accuracy


if __name__ == "__main__":
    run_eval()