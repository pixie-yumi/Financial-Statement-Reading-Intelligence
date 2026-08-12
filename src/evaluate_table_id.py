import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os
from pipeline_metrics import save_metric, get_chart_data


def evaluate_table_identification():
    summary_df = pd.read_csv("output/table_extraction_summary.csv")

    total = len(summary_df)
    ok_count = (summary_df["status"] == "OK").sum()
    success_rate = ok_count / total

    print(f"Total ranges tested: {total}")
    print(f"OK: {ok_count}")
    print(f"Success rate: {success_rate:.2%}\n")

    print("=== Problem Breakdown ===")
    problems = summary_df[summary_df["status"] != "OK"]["status"].value_counts()
    print(problems)

    save_metric("table_id", success_rate)

    os.makedirs("output/graphs", exist_ok=True)

    # Graph 1: Status Breakdown Bar Chart
    status_counts = summary_df["status"].value_counts()
    colors = ["green" if s == "OK" else "red" for s in status_counts.index]

    plt.figure(figsize=(10, 6))
    status_counts.plot(kind="bar", color=colors)
    plt.title("Table Identification — Extraction Status Breakdown")
    plt.ylabel("Count")
    plt.xlabel("Status")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig("output/graphs/table_id_status_breakdown.png")
    plt.close()
    print("\nGraph saved: output/graphs/table_id_status_breakdown.png")

    # Graph 2: Compounding Accuracy Chain -- FIX: this used to hardcode
    # Statement ID as 0.7149 permanently. Now it pulls whatever stages
    # have ACTUALLY been evaluated and saved so far, so it's never stale.
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
    print("Graph saved: output/graphs/pipeline_accuracy_chain.png")


if __name__ == "__main__":
    evaluate_table_identification()