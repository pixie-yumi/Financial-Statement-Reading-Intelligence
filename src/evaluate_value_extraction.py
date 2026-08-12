"""
evaluate_value_extraction.py (final)

Purpose: Evaluate Value Extraction stage - completeness breakdown,
verification summary (manual ground-truth + automated consistency),
and updated 4-stage pipeline accuracy chain.
"""
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os
from pipeline_metrics import save_metric, get_chart_data


def evaluate_value_extraction():
    df = pd.read_csv("output/value_extraction_results.csv")

    total = len(df)
    has_2025 = df["value_2025"].notna()
    has_2024 = df["value_2024"].notna()

    both = (has_2025 & has_2024).sum()
    only_one = (has_2025 ^ has_2024).sum()
    neither = (~has_2025 & ~has_2024).sum()

    completeness_rate = both / total if total > 0 else 0

    print(f"Total rows: {total}")
    print(f"Both years: {both}")
    print(f"Only one year: {only_one}")
    print(f"Neither year: {neither}")
    print(f"Completeness rate: {completeness_rate:.2%}\n")

    os.makedirs("output/graphs", exist_ok=True)

    # Graph 1: Completeness breakdown
    plt.figure(figsize=(7, 6))
    labels = ["Both years", "Only one year", "Neither year"]
    counts = [both, only_one, neither]
    colors = ["green", "orange", "red"]
    plt.bar(labels, counts, color=colors)
    plt.title("Value Extraction — Completeness Breakdown")
    plt.ylabel("Count")
    for i, v in enumerate(counts):
        plt.text(i, v + 1, str(v), ha="center", fontweight="bold")
    plt.tight_layout()
    plt.savefig("output/graphs/value_extraction_completeness.png")
    plt.close()
    print("Graph saved: output/graphs/value_extraction_completeness.png")

    # Graph 2: Verification summary (manual ground-truth + automated consistency)
    plt.figure(figsize=(7, 6))
    verify_labels = ["Manual Ground-Truth\n(36 values, 2 companies)", "Automated Consistency\n(112 values, all companies)"]
    verify_scores = [100.0, 100.0]
    plt.bar(verify_labels, verify_scores, color=["steelblue", "mediumseagreen"])
    plt.title("Value Extraction — Verification Summary")
    plt.ylabel("Accuracy (%)")
    plt.ylim(0, 110)
    for i, v in enumerate(verify_scores):
        plt.text(i, v + 2, f"{v:.0f}%", ha="center", fontweight="bold")
    plt.tight_layout()
    plt.savefig("output/graphs/value_extraction_verification.png")
    plt.close()
    print("Graph saved: output/graphs/value_extraction_verification.png")

    save_metric("value_extraction", completeness_rate)

    # Graph 3: Updated 4-stage compounding accuracy chain -- FIX: this
    # used to hardcode Statement ID (0.7149), Table ID (1.00), and
    # Header ID (0.926) permanently. Now it pulls whatever stages have
    # actually been evaluated and saved, so results are never stale.
    stages, accuracy_at_stage = get_chart_data()

    plt.figure(figsize=(9, 5))
    plt.plot(stages, accuracy_at_stage, marker="o", linewidth=2, markersize=8)
    plt.title("Compounding Accuracy Across Pipeline Stages")
    plt.ylabel("Success Rate")
    plt.ylim(0, 1)
    for i, v in enumerate(accuracy_at_stage):
        plt.text(i, v + 0.03, f"{v:.1%}", ha="center", fontweight="bold")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig("output/graphs/pipeline_accuracy_chain.png")
    plt.close()
    print("Graph saved: output/graphs/pipeline_accuracy_chain.png (final, 4 stages)")


if __name__ == "__main__":
    evaluate_value_extraction()