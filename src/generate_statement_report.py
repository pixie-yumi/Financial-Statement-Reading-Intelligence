"""
generate_statement_report.py

Purpose: Takes value_extraction_results.csv and prints a clean,
SECTION-ORGANIZED report for one company/year/version -- covering ALL
THREE main statements (Balance Sheet, Income Statement, Cash Flow),
each matching its standard real-world structure exactly, instead of a
flat unordered list of matched categories.

Any line item in a template that has NO matching data shows clearly as
"— not found —", so gaps are immediately visible (rather than just
silently missing from a flat CSV).
"""
import pandas as pd

# The exact standard structure, in order, matching a real Pakistani
# company balance sheet's table of contents / index.
BALANCE_SHEET_TEMPLATE = {
    "ASSETS": {
        "NON-CURRENT ASSETS": [
            ("property_plant_equipment", "Property, plant and equipment"),
            ("right_of_use_assets", "Right of use assets"),
            ("intangible_assets", "Intangible assets"),
            ("long_term_investment", "Long term investment"),
            ("long_term_loans", "Long term loans"),
            ("long_term_deposits_asset", "Long term deposits"),
            ("deferred_tax_assets", "Deferred taxation - net"),
            ("total_non_current_assets", "Total non-current assets"),
        ],
        "CURRENT ASSETS": [
            ("stores_spares_loose_tools", "Store, spares and loose tools"),
            ("inventories", "Stock-in-trade"),
            ("trade_receivables", "Trade debts"),
            ("other_receivables", "Loans, advances and other receivables"),
            ("prepayments", "Short term prepayments"),
            ("receivables_from_government", "Receivables from government"),
            ("short_term_investments", "Short term investment"),
            ("cash_and_bank", "Cash and bank balances"),
            ("total_current_assets", "Total current assets"),
        ],
    },
    "TOTAL": [
        ("total_assets", "Total Assets"),
    ],
    "EQUITY AND LIABILITIES": {
        "SHARE CAPITAL AND RESERVES": [
            ("share_capital", "Share capital"),
            ("reserves", "Reserves"),
            ("total_share_capital_and_reserves", "Total share capital and reserves"),
        ],
        "NON-CURRENT LIABILITIES": [
            ("long_term_borrowings", "Long term financing"),
            ("lease_liabilities", "Lease liability against right of use assets"),
            ("deferred_government_grant", "Deferred income - government grant"),
            ("employee_benefits", "Defined benefit plan - staff gratuity"),
            ("long_term_deposits_liability", "Long term deposits"),
            ("total_non_current_liabilities", "Total non-current liabilities"),
        ],
        "CURRENT LIABILITIES": [
            ("trade_payables", "Trade and other payables"),
            ("accrued_markup", "Accrued mark-up / profit"),
            ("short_term_borrowings", "Short term borrowings"),
            ("current_portion_non_current_liabilities", "Current portion of non-current liabilities"),
            ("unclaimed_dividend", "Unclaimed dividend"),
            ("unpaid_dividend", "Unpaid dividend"),
            ("taxation_net", "Taxation-net"),
            ("total_current_liabilities", "Total current liabilities"),
        ],
    },
    "GRAND TOTAL": [
        ("total_equity_and_liabilities", "Total Equity and Liabilities"),
    ],
    "OTHER": [
        ("contingencies_and_commitments", "Contingencies and Commitments"),
    ],
}

# Income Statement -- a flat, ordered list (no sub-sections needed,
# unlike the Balance Sheet).
INCOME_STATEMENT_TEMPLATE = {
    "INCOME STATEMENT": [
        ("revenue", "Revenue"),
        ("cost_of_sales", "Cost of sales"),
        ("gross_profit", "Gross profit"),
        ("distribution_costs", "Selling and distribution cost"),
        ("administrative_expenses", "Administrative cost"),
        ("other_expenses", "Other expense"),
        ("profit_from_operations", "Operating profit"),
        ("other_income", "Other income"),
        ("finance_cost", "Finance costs"),
        ("levies", "Levies"),
        ("profit_before_tax", "Profit before taxation"),
        ("income_tax_expense", "Taxation"),
        ("profit_for_the_year", "Profit for the year"),
        ("total_comprehensive_income", "Total comprehensive income"),
        ("eps", "Earnings per share - basic and diluted"),
    ],
}

# Cash Flow Statement -- grouped by the three standard activity
# sections (Operating / Investing / Financing).
CASH_FLOW_TEMPLATE = {
    "CASH FLOWS FROM OPERATING ACTIVITIES": [
        ("profit_before_tax", "Profit before taxation"),
    ],
    "ADJUSTMENTS FOR NON-CASH ITEMS": [
        ("depreciation_operating_fixed_assets", "Depreciation of operating fixed assets"),
        ("depreciation_rou_assets", "Depreciation of right of use assets"),
        ("amortisation_intangibles", "Amortisation of intangible assets"),
        ("employee_benefits_expense", "Expense recognised for defined benefit plan"),
        ("finance_cost", "Finance costs"),
        ("reversal_provision_stores_spares", "Reversal of provision for slow moving - stores and spares"),
        ("reversal_provision_stock_in_trade", "Reversal of provison for slow moving - stock-in-trade"),
        ("levies", "Levies"),
        ("unclaimed_liabilities_written_back", "Unclaimed liabilities written back"),
        ("dividend_income", "Dividend income"),
        ("government_grant_income", "Government grant recognised in income"),
        ("loss_reassessment_rou_lease", "Loss on reassessment of right of use asset and corresponding lease liability"),
        ("loss_disposal_fixed_assets", "Loss on disposal of operating fixed assets"),
        ("credit_loss_trade_debts", "Expected credit loss on trade debts"),
    ],
    "CHANGES IN WORKING CAPITAL": [
        ("stores_spares_loose_tools", "Store, spares and loose tools"),
        ("inventories", "Stock-in-trade"),
        ("trade_receivables", "Trade debts"),
        ("other_receivables", "Loans, advances and other receivables"),
        ("prepayments", "Short term prepayments"),
        ("receivables_from_government", "Receivables from government"),
        ("trade_payables", "Trade and other payables"),
        ("net_decrease_working_capital", "Net decrease in working capital"),
    ],
    "OPERATING (CONTINUED)": [
        ("cash_generated_from_operations", "Cash generated from operating activities"),
        ("employee_benefits", "Payment made to defined benefit plan"),
        ("finance_cost_paid", "Finance costs paid"),
        ("taxes_paid", "Levies and taxes paid"),
        ("net_cash_from_operations", "Net cash used in operating activities"),
    ],
    "CASH FLOWS FROM INVESTING ACTIVITIES": [
        ("capital_expenditure", "Payments for acquisition of property, plant and equipment"),
        ("acquisition_intangible_assets", "Payments for acquisition of intangible assets"),
        ("proceeds_disposal_fixed_assets", "Proceeds from disposal of operating fixed assets"),
        ("short_term_investment_made", "Short term investment made"),
        ("short_term_investment_redeemed", "Short term investment redeemed"),
        ("dividend_income", "Dividend income received"),
        ("long_term_loans", "Long term loans"),
        ("long_term_deposits", "Long term deposits"),
        ("cash_from_investing", "Net cash used in investing activities"),
    ],
    "CASH FLOWS FROM FINANCING ACTIVITIES": [
        ("long_term_borrowings", "Proceeds from long term financing"),
        ("repayment_long_term_financing", "Repayment of long term financing"),
        ("lease_liabilities", "Payments against lease liabilities"),
        ("short_term_borrowings", "Increase in short term borrowings - net"),
        ("dividend_paid", "Dividend paid"),
        ("cash_from_financing", "Net cash generated from financing activities"),
    ],
    "SUMMARY": [
        ("foreign_exchange_difference", "Exchange loss on translation"),
        ("net_change_in_cash", "Net decrease in cash and cash equivalents"),
        ("cash_at_beginning", "Cash and cash equivalents at the beginning of the year"),
        ("cash_and_equivalents_at_end", "Cash and cash equivalents at the end of the year"),
    ],
}

# Which template + display title goes with which statement_type in the
# underlying data.
STATEMENTS = [
    ("balance_sheet", "BALANCE SHEET", BALANCE_SHEET_TEMPLATE),
    ("profit_and_loss", "INCOME STATEMENT", INCOME_STATEMENT_TEMPLATE),
    ("cash_flow", "CASH FLOW STATEMENT", CASH_FLOW_TEMPLATE),
]


def format_value(v):
    if pd.isna(v):
        return "—"
    # FIX: EPS values are small decimals (e.g. 6.02), but the old
    # always-round-to-whole-number formatting displayed "6" instead --
    # losing the actual figure. Large financial amounts should stay as
    # whole numbers (they're already in '000s, decimals aren't
    # meaningful), but small values should keep their decimals.
    if abs(v) < 1000:
        return f"{v:,.2f}"
    return f"{v:,.0f}"


def make_line_item_printer(company_matches, year_col, statement_type, counters):
    """Returns a function that prints a list of (category, label) line
    items for ONE specific statement_type, handling the two known
    collision issues:
      1. The SAME category can match rows from a DIFFERENT statement
         type too (e.g. "inventories" also matches Cash Flow's
         "(increase)/decrease in stock-in-trade" delta line) -- so we
         always filter to this exact statement_type first.
      2. A column-merged page can occasionally produce a garbage row
         (a section header glued to a neighboring column's unrelated
         value) -- genuine labels are almost always short, so we
         prefer the SHORTEST raw_label among same-statement-type
         candidates.
    """
    def print_line_items(items, indent="  "):
        for category, label in items:
            counters["total"] += 1
            candidates = company_matches[
                (company_matches["category"] == category) &
                (company_matches["statement_type"] == statement_type)
            ]
            if candidates.empty:
                print(f"{indent}{label:<50} — not found —")
                continue

            best_row = candidates.loc[candidates["raw_label"].astype(str).str.len().idxmin()]
            value = best_row[year_col]
            print(f"{indent}{label:<50} {format_value(value)}")
            if not pd.isna(value):
                counters["found"] += 1

    return print_line_items


def print_template(template, print_line_items):
    for section, content in template.items():
        if isinstance(content, dict):
            print(f"{section}\n")
            for subsection, items in content.items():
                print(f"  {subsection}")
                print_line_items(items, indent="    ")
                print()
        else:
            print(f"{section}")
            print_line_items(content)
            print()


def generate_report(company, year, version, results_df, statements=None):
    """statements: optional list of statement_type keys to include
    (e.g. ["balance_sheet"]) -- defaults to ALL THREE (Balance Sheet,
    Income Statement, Cash Flow)."""
    company_matches = results_df[results_df["filename"].str.contains(company, case=False, na=False)]

    # FIX: companies without subsidiaries don't distinguish
    # Consolidated/Unconsolidated at all -- their data is tagged
    # "unknown" (their one and only set of statements). Without this
    # fallback, asking for "consolidated" on such a company filtered
    # everything out, showing every single line item as "not found"
    # even though the real data was sitting right there under
    # "unknown".
    if version and "version" in company_matches.columns:
        version_specific = company_matches[company_matches["version"] == version]
        if not version_specific.empty:
            company_matches = version_specific
        else:
            unknown_matches = company_matches[company_matches["version"] == "unknown"]
            if not unknown_matches.empty:
                company_matches = unknown_matches

    year_col = "value_2025" if str(year) == "2025" else "value_2024"

    print(f"\n{'=' * 60}")
    print(f"  {company} — {version.upper()} — {year}")
    print(f"{'=' * 60}\n")

    for stype, title, template in STATEMENTS:
        if statements and stype not in statements:
            continue

        print(f"{'#' * 60}")
        print(f"  {title}")
        print(f"{'#' * 60}\n")

        counters = {"found": 0, "total": 0}
        print_line_items = make_line_item_printer(company_matches, year_col, stype, counters)
        print_template(template, print_line_items)

        print(f"{'-' * 60}")
        pct = counters["found"] / counters["total"] if counters["total"] else 0
        print(f"{title} coverage: {counters['found']}/{counters['total']} line items have a value ({pct:.0%})")
        print(f"{'-' * 60}\n")

    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    results_df = pd.read_csv("output/value_extraction_results.csv")

    company = input("Company name (partial match ok): ").strip()
    year = input("Year (2025 or 2024): ").strip()
    version = input("Version (consolidated/unconsolidated, Enter for consolidated): ").strip().lower()
    version = version if version else "consolidated"

    generate_report(company, year, version, results_df)