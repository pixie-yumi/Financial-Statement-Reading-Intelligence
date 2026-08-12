import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from extract_st_id import extract_pages_full
from classify_full import classify_page
import os

FILENAME_MAP = {
    "Engro Fertilizers": "Engro Annual 2025.pdf",
    "Gul Ahmed": "Gul Ahmed Annual 2025.pdf",
    "Systems Limited": "SYS.pdf",
    "UBL": "UBL 2025 ANNUAL.pdf",
    "MCB Bank": "MCB Limited.pdf",
    "PTCL": "PTCL.pdf",
    "Attock Cement": "Attock Cement.pdf",
    "Nishat Mills": "Nishat.pdf",
    "NETSOL": "NETSOL ANNUAL 2025.pdf",
    "Abbott Labs Pakistan": "Abbott Labs Pakistan.pdf",
    "Fauji Fertilizers": "Fauji Fertilizers.pdf",
    "Indus Motor": "Indus Motor.pdf",
    "K-Electric Limited": "K-electric LImited.pdf",
    "Lucky Cement Limited": "Lucky Cement Limited.pdf",
    "Mughal Iron and Steel": "Mughal Iron and Steel.pdf",
    "JS Bank Ltd": "JS BankLtd.pdf",
    "TPL Trackers Ltd": "TPL Tracker ltd.pdf",
    "Sapphire Textiles Limited": "Sapphire Textiles Limited.pdf",
}


def parse_range(range_str):
    range_str = str(range_str).replace("–", "-").strip()
    if range_str in ("NOT FOUND", "UNREADABLE", "nan", ""):
        return None
    parts = range_str.split("-")
    return int(parts[0].strip()), int(parts[1].strip())


def build_ground_truth(gt_excel_path):
    gt_df = pd.read_excel(gt_excel_path, sheet_name="Ground Truth")
    true_labels = {}

    for _, row in gt_df.iterrows():
        company = row["Company Name"]
        filename = FILENAME_MAP.get(company)
        if filename is None:
            print(f"WARNING: no filename mapping for '{company}', skipping")
            continue

        for col, label in [
            ("Balance Sheet Page Range", "balance_sheet"),
            ("Income Statement Page Range", "profit_and_loss"),
            ("Cash Flow Page Range", "cash_flow"),
        ]:
            parsed = parse_range(row[col])
            if parsed is None:
                continue
            start, end = parsed
            for p in range(start, end + 1):
                true_labels[(filename, p)] = label

    return true_labels


def run_evaluation():
    print("Starting evaluation...")
    gt_excel = "Consolidated_Financial_Statements_Master_v3.xlsx"
    pdf_folder = "data"

    print("Loading Ground Truth Excel...")
    true_labels = build_ground_truth(gt_excel)
    print(f"Ground Truth loaded: {len(true_labels)} labeled pages")

    y_true = []
    y_pred = []
    missing_files = []

    mapped_filenames = set(FILENAME_MAP.values())

    for filename in os.listdir(pdf_folder):
        if not filename.lower().endswith(".pdf"):
            continue
        if filename not in mapped_filenames:
            continue

        print(f"Processing: {filename} ...")
        pdf_path = os.path.join(pdf_folder, filename)
        try:
            pages = extract_pages_full(pdf_path)
        except Exception as e:
            missing_files.append((filename, str(e)))
            continue

        for page_num, page_data in pages.items():
            text = page_data["text"]
            bold_blocks = page_data["bold_blocks"]
            if not text.strip():
                continue

            key = (filename, page_num)
            true_label = true_labels.get(key, "other")

            predicted = classify_page(text, bold_blocks)
            pred_label = predicted[0] if predicted and predicted[0] != "other" else "other"

            y_true.append(true_label)
            y_pred.append(pred_label)

    print("\nAll files processed. Calculating metrics...")

    labels = ["balance_sheet", "profit_and_loss", "cash_flow", "notes", "other"]

    acc = accuracy_score(y_true, y_pred)
    print(f"\nOverall Accuracy: {acc:.2%}\n")

    from pipeline_metrics import save_metric
    save_metric("statement_id", acc)
    print(classification_report(y_true, y_pred, labels=labels, zero_division=0))

    if missing_files:
        print("\nFiles with errors (skipped):")
        for f, err in missing_files:
            print(f"  {f}: {err}")

    cm = confusion_matrix(y_true, y_pred, labels=labels)

    plt.figure(figsize=(9, 7))
    sns.heatmap(cm, annot=True, fmt="d", xticklabels=labels, yticklabels=labels, cmap="Blues")
    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.title("Statement Identification — Confusion Matrix (18 Companies)")
    plt.tight_layout()

    os.makedirs("output/graphs", exist_ok=True)
    plt.savefig("output/graphs/statement_id_confusion_matrix.png")
    plt.close()

    print("\nGraph saved: output/graphs/statement_id_confusion_matrix.png")
    print("DONE!")


if __name__ == "__main__":
    run_evaluation()