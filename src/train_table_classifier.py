import os
import re
import pandas as pd
from extract_st_id import extract_pages
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

ranges_df = pd.read_csv("output/output_page_ranges_v2.csv")
statement_types = ["balance_sheet", "profit_and_loss", "cash_flow", "changes_in_equity"]


def get_label(filename, page_num):
    company_ranges = ranges_df[
        (ranges_df["filename"] == filename) &
        (ranges_df["type"].isin(statement_types))
    ]
    for _, row in company_ranges.iterrows():
        if row["start_page"] <= page_num <= row["end_page"]:
            return 1
    return 0


def is_garbled(text):
    return bool(re.search(r"\(cid:", text))


def build_dataset():
    folder = "data"
    texts, labels, meta = [], [], []

    for filename in os.listdir(folder):
        if filename.lower().endswith(".pdf"):
            print(f"Reading: {filename} ...")
            pages = extract_pages(os.path.join(folder, filename))
            for page_num, text in pages.items():
                if text.strip():
                    texts.append(text)
                    labels.append(get_label(filename, page_num))
                    meta.append((filename, page_num))

    dataset_df = pd.DataFrame({
        "filename": [m[0] for m in meta],
        "page": [m[1] for m in meta],
        "text": texts,
        "label": labels
    })

    before = len(dataset_df)
    dataset_df = dataset_df[~dataset_df["text"].apply(is_garbled)]
    print(f"\nGarbled rows removed: {before - len(dataset_df)}")
    print(f"Total pages (after filtering): {len(dataset_df)}")
    print(f"Table pages (1): {dataset_df['label'].sum()}")
    print(f"Non-table pages (0): {(dataset_df['label'] == 0).sum()}")

    os.makedirs("output", exist_ok=True)
    dataset_df.to_csv("output/table_classifier_dataset.csv", index=False)
    print("Dataset saved to 'output/table_classifier_dataset.csv'!\n")

    return dataset_df


def train_model(dataset_df):
    X_train, X_test, y_train, y_test = train_test_split(
        dataset_df["text"], dataset_df["label"],
        test_size=0.2, random_state=42, stratify=dataset_df["label"]
    )

    vectorizer = TfidfVectorizer(max_features=1000, stop_words="english")
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)

    model = LogisticRegression(class_weight="balanced", max_iter=1000)
    model.fit(X_train_vec, y_train)

    predictions = model.predict(X_test_vec)

    print("=== Model Evaluation ===")
    print(classification_report(y_test, predictions, target_names=["not_table (0)", "table (1)"]))

    return model, vectorizer


if __name__ == "__main__":
    dataset_df = build_dataset()
    model, vectorizer = train_model(dataset_df)
    print("Training complete!")