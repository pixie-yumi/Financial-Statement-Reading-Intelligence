import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

stages = ["Statement ID", "Table ID", "Header ID", "Value Extraction", "Simple Average", "End-to-End\n(compounded)"]
per_stage = [0.715, 1.00, 0.926, 0.737]
simple_avg = sum(per_stage) / len(per_stage)
compounded = per_stage[0] * per_stage[1] * per_stage[2] * per_stage[3]

values = per_stage + [simple_avg, compounded]
colors = ["steelblue"] * 4 + ["gray", "darkred"]

plt.figure(figsize=(11, 5.5))
bars = plt.bar(stages, values, color=colors)
plt.title("Per-Stage vs Overall Success Rate (Two Ways to Measure)")
plt.ylabel("Rate")
plt.ylim(0, 1.05)
for bar, v in zip(bars, values):
    plt.text(bar.get_x() + bar.get_width()/2, v + 0.02, f"{v:.1%}", ha="center", fontweight="bold")
plt.tight_layout()

os.makedirs("output/graphs", exist_ok=True)
plt.savefig("output/graphs/overall_end_to_end.png")
plt.close()
print(f"Simple average: {simple_avg:.1%}")
print(f"Compounded: {compounded:.1%}")