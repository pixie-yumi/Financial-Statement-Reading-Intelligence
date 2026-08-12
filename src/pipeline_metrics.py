"""
pipeline_metrics.py

Purpose: Shared helper so every evaluation script (evaluate_statement_id,
evaluate_table_id, evaluation_header, evaluate_value_extraction) reads
and writes to ONE shared metrics file, instead of each script hardcoding
guesses about what the OTHER stages scored.

Before this fix: each script had its own hardcoded list like
    accuracy_at_stage = [0.7149, 0.80, avg_confidence / 100]
where 0.7149 and 0.80 were stale numbers typed in once and never
updated -- so charts kept showing old results (e.g. Table ID frozen at
80% even after it was actually re-tested at 100%).

After this fix: each script writes its OWN real result here right after
computing it, and reads whatever earlier stages have already written
when building the compounding accuracy chart. Numbers can never go
stale, because every script pulls straight from this file, and every
script updates it the moment it re-runs.
"""
import json
import os

METRICS_PATH = "output/pipeline_metrics.json"


def load_metrics():
    if not os.path.exists(METRICS_PATH):
        return {}
    with open(METRICS_PATH, "r") as f:
        return json.load(f)


def save_metric(stage_key, value):
    """stage_key e.g. 'statement_id', 'table_id', 'header_id', 'value_extraction'
    value is a 0-1 float (success rate / accuracy / completeness)."""
    metrics = load_metrics()
    metrics[stage_key] = value
    os.makedirs("output", exist_ok=True)
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)


STAGE_LABELS = {
    "statement_id": "Statement ID",
    "table_id": "Table ID",
    "header_id": "Header ID\n(match confidence)",
    "value_extraction": "Value Extraction\n(completeness)",
}

# The order stages should appear in the compounding chart
STAGE_ORDER = ["statement_id", "table_id", "header_id", "value_extraction"]


def get_chart_data():
    """Returns (labels, values) for ONLY the stages that have actually
    been run and saved so far -- never fabricates a number for a stage
    that hasn't been computed yet."""
    metrics = load_metrics()
    labels, values = [], []
    for stage in STAGE_ORDER:
        if stage in metrics:
            labels.append(STAGE_LABELS[stage])
            values.append(metrics[stage])
    return labels, values