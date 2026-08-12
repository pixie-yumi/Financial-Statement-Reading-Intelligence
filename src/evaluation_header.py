"""
evaluate_header_id.py (v2 - final)

Purpose: Evaluate Header Identification stage - match confidence,
category breakdown, and updated cross-stage accuracy chain.
"""
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os
from pipeline_metrics import save_metric, get_chart_data


def evaluate_header_identification():
    matches_df = pd.read_csv("output/header_matches.csv")

    total_matched = len(matches_df)
    avg_confidence = matches_df["score"].mean()

    print(f"Total matched: {total_matched}")
    print(f"Average match confidence: {avg_confidence:.1f}%\n")

    print("=== Top matched categories ===")
    print(matches_df["matched_category"].value_counts().head(15))

    os.makedirs("output/graphs", exist_ok=True)

    # Graph 1: Top matched categories
    top_categories = matches_df["matched_category"].value_counts().head(15)
    plt.figure(figsize=(11, 6))
    top_categories.plot(kind="bar", color="steelblue")
    plt.title("Header Identification — Top Matched Categories")
    plt.ylabel("Count")
    plt.xlabel("Category")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig("output/graphs/header_id_top_categories.png")
    plt.close()
    print("\nGraph saved: output/graphs/header_id_top_categories.png")

    # Graph 2: Confidence score distribution
    plt.figure(figsize=(8, 6))
    plt.hist(matches_df["score"], bins=15, color="mediumseagreen", edgecolor="black")
    plt.title("Header Identification — Match Confidence Distribution")
    plt.xlabel("Fuzzy Match Score")
    plt.ylabel("Count")
    plt.axvline(avg_confidence, color="red", linestyle="--", label=f"Average: {avg_confidence:.1f}%")
    plt.legend()
    plt.tight_layout()
    plt.savefig("output/graphs/header_id_confidence_distribution.png")
    plt.close()
    print("Graph saved: output/graphs/header_id_confidence_distribution.png")

    save_metric("header_id", avg_confidence / 100)

    # Graph 3: Updated compounding accuracy chain -- FIX: this used to
    # hardcode Statement ID (0.7149) and Table ID (0.80) permanently,
    # even after both were re-tested with better results. Now it pulls
    # whatever stages have actually been evaluated and saved.
    stages, accuracy_at_stage = get_chart_data()

    plt.figure(figsize=(8, 5))
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
    print("Graph saved: output/graphs/pipeline_accuracy_chain.png (updated)")


if __name__ == "__main__":
    evaluate_header_identification()