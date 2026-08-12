"""
header_identification.py 

Purpose: Match row labels to standard categories using fuzzy matching.
"""
import re
import pandas as pd
from rapidfuzz import fuzz
from extract_tables import extract_table_for_range
from version_filter import filter_to_consolidated


SYNONYMS = {
    # FIX: "Property, Plant & Equipment" (a line item) and "Total
    # Non-Current Assets" (its subtotal) used to share ONE category
    # ("fixed_assets"), so when a table had both rows, they'd collide --
    # whichever matched first/highest would silently win, meaning asking
    # for "Fixed Assets" could return the wrong one. Split into two
    # distinct categories so each row's true identity is preserved, and
    # the query layer can specifically pick which one it means.
    "property_plant_equipment": [
        "property plant and equipment",
        "fixed assets property plant and equipment",
    ],
    "total_non_current_assets": [
        "total non-current assets",
        "total non current assets",
        "fixed assets",  # when someone just says "fixed assets" colloquially, they usually mean this total
    ],
    "long_term_investment": ["long term investment", "long term investments"],
    "inventories": ["inventories", "stock in trade"],
    "trade_receivables": ["trade receivables", "trade debts"],
    "other_receivables": ["other receivables"],
    "cash_and_bank": ["cash and bank balances", "cash and cash equivalents"],
    "total_assets": ["total assets"],
    "share_capital": ["share capital", "issued subscribed and paid-up capital", "issued subscribed and paid up capital"],
    "unappropriated_profit": ["unappropriated profit"],
    "long_term_loans": ["long term loans"],
    "trade_payables": ["trade and other payables"],
    "short_term_borrowings": ["short term borrowings"],
    "reserves": ["reserves", "capital reserves", "revenue reserves"],
    "lease_liabilities": ["lease liabilities", "lease liability against right of use assets", "lease liability", "payments in respect of leases", "lease rentals paid"],
    "deferred_tax_liabilities": ["deferred tax liabilities", "deferred taxation"],
    "intangible_assets": ["intangible assets"],
    "right_of_use_assets": ["right of use assets", "right-of-use assets"],
    "employee_benefits": ["employee benefit obligations", "retirement benefits", "staff gratuity", "defined benefit plan", "gratuity", "deferred employee benefits", "current portion of deferred employee benefits"],
    "provision_for_taxation": ["provision for taxation"],
    "unclaimed_dividend": ["unclaimed dividend"],
    "unpaid_dividend": ["unpaid dividend"],
    "unpaid_dividend": ["unpaid dividend"],

    "revenue": ["revenue from contracts with customers", "net sales", "turnover net", "revenue", "net turnover", "sales net"],
    "cost_of_sales": ["cost of sales"],
    "gross_profit": ["gross profit"],
    "distribution_costs": ["distribution costs", "distribution cost", "selling and distribution expenses"],
    "administrative_expenses": ["administrative expenses"],
    "other_expenses": ["other expenses"],
    "other_income": ["other income"],
    "profit_from_operations": ["profit from operations", "operating profit"],
    "finance_cost": ["finance cost", "finance costs"],
    "profit_before_tax": ["profit before income tax", "profit before taxation", "profit before revenue tax income tax and levy", "profit loss before income tax and levies"],
    "income_tax_expense": ["income tax expense", "taxation"],
    "profit_for_the_year": ["profit for the year", "profit after taxation", "profit after tax"],
    "total_comprehensive_income": ["total comprehensive income"],
    "eps": ["earnings per share"],
    "levies": ["levies", "final taxes levy", "final tax levy", "levy"],

    "cash_generated_from_operations": ["cash generated from operating activities", "cash generated from operations"],
    "net_cash_from_operations": [
        "net cash used in operating activities",
        "net cash generated from operating activities",
        "net cash flow from operating activities",
        "net cash flow used in operating activities",
        "net cash flow from used in operating activities",
    ],
    "finance_cost_paid": ["finance costs paid", "finance cost paid"],
    "repayment_long_term_financing": ["repayment of long term financing", "repayment of long-term financing"],
    "cash_at_beginning": ["cash and cash equivalents at the beginning of the year", "cash and cash equivalents at beginning of the year"],
    "proceeds_disposal_fixed_assets": ["proceeds from disposal of operating fixed assets", "proceeds from disposal of property and equipment"],
    "acquisition_intangible_assets": ["payments for acquisition of intangible assets", "purchase development of intangibles"],
    "short_term_investment_made": ["short term investment made"],
    "short_term_investment_redeemed": ["short term investment redeemed"],
    "depreciation_rou_assets": ["depreciation of right of use assets", "depreciation on right of use assets"],
    "reversal_provision_stores_spares": ["reversal of provision for slow moving stores and spares"],
    "reversal_provision_stock_in_trade": ["reversal of provison for slow moving stock in trade", "reversal of provision for slow moving stock in trade"],
    "unclaimed_liabilities_written_back": ["unclaimed liabilities written back"],
    "government_grant_income": ["government grant recognised in income", "government grant recognized in income"],
    "loss_reassessment_rou_lease": ["loss on reassessment of right of use asset and corresponding lease liability"],
    "loss_disposal_fixed_assets": ["loss on disposal of operating fixed assets"],
    "credit_loss_trade_debts": ["expected credit loss on trade debts"],
    "employee_benefits_expense": ["expense recognised for defined benefit plan", "expense recognized for defined benefit plan"],
    "net_decrease_working_capital": ["net decrease in working capital", "net increase in working capital"],
    "cash_from_operations": [
        "cash flow from operating activities",
    ],
    "cash_from_investing": [
        "cash flow from investing activities",
        "net cash flow from investing activities",
        "net cash used in investing activities",
        "net cash generated from investing activities",
        "net cash flow from used in investing activities",
    ],
    "cash_from_financing": [
        "cash flow from financing activities",
        "net cash flow from financing activities",
        "net cash used in financing activities",
        "net cash generated from financing activities",
        "net cash flow from used in financing activities",
    ],
    "dividend_paid": ["dividend paid"],

    # --- NEW: expanded coverage, common across Pakistani annual reports ---

    # Balance Sheet -- totals/subtotals (benefit from the general
    # "total_" priority rules above)
    "total_current_assets": ["total current assets"],
    "total_current_liabilities": ["total current liabilities"],
    "total_non_current_liabilities": ["total non-current liabilities", "total non current liabilities"],
    "total_liabilities": ["total liabilities"],
    "total_equity": ["total equity", "total shareholders equity", "total shareholders' equity"],
    "total_equity_and_liabilities": ["total equity and liabilities"],

    # Balance Sheet -- additional line items
    "long_term_borrowings": ["long term borrowings", "long term finances", "borrowings"],
    "short_term_investments": ["short term investments"],
    "long_term_deposits": ["long term deposits"],
    "advances_deposits_prepayments": ["advances deposits and prepayments", "advances, deposits and prepayments"],
    "sales_tax_payable": ["sales tax payable"],
    "accrued_markup": ["accrued mark-up", "accrued markup", "accrued interest and mark-up"],
    "contract_liabilities": ["contract liabilities"],
    "surplus_on_revaluation": ["surplus on revaluation of property plant and equipment", "surplus on revaluation of fixed assets"],

    # P&L -- additional line items
    "other_operating_expenses": ["other operating expenses"],
    "share_of_profit_of_associates": ["share of profit of associates", "share of profit from associates"],
    "workers_profit_participation_fund": ["workers profit participation fund", "workers' profit participation fund"],
    "workers_welfare_fund": ["workers welfare fund", "workers' welfare fund"],
    "non_controlling_interest": ["non-controlling interest", "non controlling interest", "minority interest"],
    "diluted_eps": ["diluted earnings per share"],

    # Cash Flow -- additional lines
    "net_change_in_cash": [
        "net increase in cash and cash equivalents",
        "net decrease in cash and cash equivalents",
        "net increase decrease in cash and cash equivalents",
    ],
    "cash_and_equivalents_at_end": [
        "cash and cash equivalents at end of the year",
        "cash and cash equivalents at the end of the year",
    ],

    # --- NEW ROUND 2: added after checking real unmatched output ---
    "prepayments": ["short term prepayments", "prepayments", "advance payments"],
    "current_portion_non_current_liabilities": [
        "current portion of non-current liabilities",
        "current maturity of non-current liabilities",
    ],
    "stores_spares_loose_tools": ["stores spares and loose tools", "store spares and loose tools"],
    "depreciation_operating_fixed_assets": ["depreciation of operating fixed assets", "depreciation on operating fixed assets"],
    "amortisation_intangibles": ["amortisation of intangible assets", "amortization of intangible assets"],
    "depreciation_amortisation": [
        "depreciation on right of use assets",
        "depreciation expense",
        "depreciation on property and equipment",
        "depreciation on non-banking assets",
        "amortisation",
        "amortization",
    ],
    "taxation_net": ["taxation net", "taxation - net"],

    # --- NEW ROUND 3: high-frequency items found across MANY companies
    # in real unmatched output (banks, textiles, cement, tech, motors,
    # utilities) ---
    "loans_and_advances": ["loans and advances"],
    "deferred_revenue": ["deferred revenue"],
    "current_maturity_long_term_debt": [
        "current portion of long-term loan",
        "current portion of long term financing",
        "current maturity of long-term financing",
        "current portion of non-current liabilities",
    ],
    "stores_and_spares": ["stores and spares", "store and spares"],
    "investment_property": ["investment property"],
    "deferred_government_grant": ["deferred government grant", "deferred income government grant"],
    "dividend_income": ["dividend income", "dividend received", "dividends received"],
    "contingencies_and_commitments": ["contingencies and commitments"],

    # Banking-specific line items (banks have a very different chart of
    # accounts from manufacturing/textile companies -- several of the
    # 17 companies are banks, e.g. JS Bank, MCB, UBL)
    "cash_and_balances_with_banks": ["cash and balances with treasury banks"],
    "lendings_to_financial_institutions": ["lendings to financial institutions"],
    "bills_payable": ["bills payable"],
    "borrowings_from_fis": ["borrowings from financial institutions", "borrowings"],
    "net_markup_income": ["net mark-up interest income", "net markup interest income"],
    "fee_and_commission_income": ["fee and commission income"],
    "credit_loss_allowance": ["credit loss allowance and write offs net", "credit loss allowance and write-offs net", "allowance for ecl"],

    # --- NEW ROUND 4: more high-frequency cash-flow items found across
    # almost every single company ---
    "taxes_paid": [
        "taxes and levies paid", "taxes and levy paid", "income taxes paid",
        "income tax paid", "levy and income tax paid", "taxes paid",
        "income tax and levies net",
    ],
    "capital_expenditure": ["fixed capital expenditure", "capital expenditure incurred", "payments for acquisition of property plant and equipment"],
    "foreign_exchange_difference": [
        "net foreign exchange difference", "effect of exchange rate changes",
        "net foreign exchange differences", "exchange loss on translation",
        "exchange gain on translation", "exchange gain loss on translation of foreign subsidiaries",
        "exchange differences on translation of foreign operations",
    ],
    "interest_income_received": [
        "interest received", "interest income received", "profit received",
        "mark-up received", "markup received",
    ],
    "investment_in_subsidiary": ["investment in subsidiary", "investment in subsidiary companies"],

    # --- NEW ROUND 5: more high-frequency items found across many
    # companies (Due from/to related parties, deferred tax assets,
    # short term deposits, contract assets, derivatives, etc.) ---
    "due_from_related_parties": ["due from related parties"],
    "due_to_related_parties": ["due to related parties"],
    "deferred_tax_assets": ["deferred tax asset", "deferred tax assets"],
    "short_term_deposits": ["short term deposits", "short-term deposits"],
    "tax_refund_due_from_government": ["tax refunds due from government", "taxation receivable"],
    "contract_assets": ["contract assets", "long term contract assets"],
    "derivative_financial_instruments": ["derivative financial instruments", "derivative financial assets"],
    "investment_in_associates": ["investment in associates"],
    "capital_work_in_progress": ["capital work in progress"],
    "long_term_advances_deposits": ["long term advances and deposits", "long term loans advances and deposits", "decrease increase in long term advances"],

    # --- NEW: exact cross-check against a real balance sheet's full
    # index of headings/line items -- these two were the only genuine
    # gaps found ---
    "receivables_from_government": ["receivables from government"],
    "total_share_capital_and_reserves": ["total share capital and reserves"],
    "equity_attributable_to_parent": ["equity attributable to equity holders of the holding company", "equity attributable to owners of the holding company", "equity attributable to shareholders of the parent"],
    "security_deposits": ["security deposits"],
    "exploration_evaluation_assets": ["exploration and evaluation assets", "exploration and evaluation expenditure"],
    "compensated_absences_paid": ["accumulating compensated absences paid"],
    "investment_in_shares_certificates": ["investments in shares and certificates"],
    "proceeds_sale_equity_instrument": ["proceeds from sale of equity instrument"],
    "investment_bond_purchase": ["purchase of pakistan investment bond", "purchase of treasury bills", "purchase of investment bond"],
    "investment_bond_proceeds": ["proceeds from sale of pakistan investment bond", "proceeds from sale of treasury bills", "proceeds from sale of investment bond"],
    "mutual_fund_purchase": ["purchase of mutual fund units"],
    "mutual_fund_proceeds": ["proceeds from sale of mutual fund units"],
    "divestment_proceeds": ["proceeds received against divestment of associate", "proceeds from divestment"],
    "term_deposit_movement": ["encashment placement in term deposits", "placement encashment in term deposits"],
    "export_refinance_obtained": ["export refinance loan obtained"],
    "export_refinance_repaid": ["export refinance loan repaid"],
    "other_long_term_liability": ["other long term liability", "other long term liabilities"],
    "research_development_expenses": ["research development expenses", "research and development expenses"],
    "impairment_losses_financial_assets": ["impairment losses on financial assets"],
    "receipts_long_term_receivables": ["receipts against long term receivables"],
    "acquisition_of_subsidiary": ["acquisition of subsidiary"],
    "proceeds_exercise_share_options": ["proceeds from exercise of share options"],
    "other_components_of_equity": ["other components of equity"],
    "profit_continuing_operations": ["profit loss from continuing operations"],
    "loss_discontinued_operations": ["loss from discontinued operations", "profit from discontinued operations"],
    "gain_disposal_subsidiary": ["gain on disposal of subsidiary", "loss on disposal of subsidiary"],
}

GENERIC_BLOCKLIST = {
    # FIX: "advances", "investments", "net assets", and "total income"
    # were removed from this list -- they're all legitimate standalone
    # line items in bank/financial-institution balance sheets and P&Ls
    # (e.g. JS Bank's balance sheet literally has a row labeled just
    # "Investments" worth Rs 581,458,618 thousand, and a row labeled
    # just "Advances" worth Rs 542,341,772 thousand -- both completely
    # real, not section-header junk). Blocking them by exact wording
    # was silently dropping genuine high-value line items across every
    # bank we tested (JS Bank, MCB), confirmed against the real PDFs.
    "assets", "liabilities", "deposits", "turnover",
    "asset", "liability", "current assets", "current liabilities",
}


def is_garbled(text):
    return bool(re.search(r"\(cid:", text))


def is_junk_label(label):
    # NEW: normalize hidden unicode whitespace (non-breaking spaces,
    # zero-width characters) that PDF extraction sometimes produces.
    # Without this, a value like "#NAME?\xa0" or "#NAME?\u200b" could
    # slip past our "#NAME?" checks below, since plain .replace(" ", "")
    # only removes regular ASCII spaces.
    label = label.replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")

    label_clean = label.strip()
    if label_clean == "#NAME?":
        return True
    label_lower = label_clean.lower().replace(" ", "")
    if "#name" in label_lower or "#ref" in label_lower or "#value" in label_lower:
        return True
    if not re.search(r"[a-zA-Z]{4,}", label):
        return True
    if label_clean.lower() in GENERIC_BLOCKLIST:
        return True
    # comma-formatted large numbers (e.g. "120,864") glued to label - summary-table row
    big_numbers = re.findall(r'\d{1,3}(?:,\d{3})+', label)
    if len(big_numbers) >= 2:
        return True

    # NEW: page-footer junk that slipped through -- e.g.
    # "179 | Gul Ahmed Textile Mills Limited" (page number + company
    # name, repeated on every page) and "As at June 30, 2025" (a date
    # caption, not a line item). Neither is a real financial statement
    # row, but both had enough letters to pass the checks above.
    if re.match(r'^\d+\s*\|', label_clean):
        return True
    if re.match(r'^as\s+at\s+\w+', label_clean.lower()):
        return True
    if re.match(r'^for\s+the\s+year\s+ended', label_clean.lower()):
        return True
    # NEW: column-header captions like "(Amounts in thousand) Note" or
    # "( Amounts in thousand except for earnings per share) Note" --
    # these describe the TABLE, not a line item, and their "values"
    # (accidentally captured years like "2024"/"2025") are meaningless.
    if re.match(r'^\(?\s*a\s*mounts?\s+in\s+(thousand|million|rupees)', label_clean.lower()):
        return True
    # NEW: page-footer taglines that repeat across every page (e.g.
    # "driven leadership annual report", "annual report") -- these
    # slipped through since they're plain lowercase words with 4+
    # letters and no other junk pattern matched.
    if re.search(r'\bannual report\b', label_clean.lower()) and len(label_clean.split()) <= 6:
        return True
    # NEW: some PDFs have a font/extraction glitch that duplicates
    # every letter (e.g. "AANNNNUUAALL RREEPPOORRTT" instead of "ANNUAL
    # REPORT") -- a real financial label never has almost every
    # character doubled like this.
    letters_only = re.sub(r'[^A-Za-z]', '', label_clean)
    if len(letters_only) >= 8:
        doubled = sum(1 for i in range(0, len(letters_only) - 1, 2) if letters_only[i] == letters_only[i + 1])
        if doubled / (len(letters_only) // 2) > 0.7:
            return True

    # NEW ROUND 3: broader page-footer patterns without a "|" separator
    # -- e.g. "60 United Bank Limited", "197 198 Annual Report 2022"
    # (page numbers followed by company/report name, no punctuation).
    label_lower_spaced = label_clean.lower()
    if re.match(r'^\d+(\s+\d+)*\s+[A-Za-z]', label_clean) and (
        "annual report" in label_lower_spaced or re.search(r'limited$|company$', label_lower_spaced)
    ):
        return True

    # NEW ROUND 3: signature-block junk -- director/officer name lines
    # and titles that repeat at the bottom of every statement page
    # (e.g. "Chief Executive Officer Director", "Chief Financial Officer
    # President/Chief Executive"). These have plenty of letters so they
    # slipped past the earlier checks.
    SIGNATURE_TERMS = ["chief executive", "chief financial officer", "director", "chairman", "president"]
    signature_hits = sum(1 for term in SIGNATURE_TERMS if term in label_lower_spaced)
    if signature_hits >= 2:
        return True

    # NEW ROUND 4 (Issue 1 defense-in-depth): a ratio/percentage-analysis
    # table row (e.g. "Total Equity & Liabilities 100.00 100.00") has
    # its label text glued to 2+ small decimal numbers under 100 --
    # real financial statement labels never look like this (real values
    # use comma-formatted thousands, not bare "58.15 82.02"). Even if
    # such a page slips past the Statement ID filter, this catches it
    # here as a second line of defense.
    percent_like_numbers = re.findall(r'\b\d{1,3}\.\d{2}\b', label_clean)
    if len(percent_like_numbers) >= 2 and all(float(n) <= 100 for n in percent_like_numbers):
        return True

    # NEW ROUND 4 (Issue 2): truncated word fragments from table-column
    # splitting -- e.g. "l assets" and "l liabilities" instead of the
    # real "Total assets" / "Total liabilities" (the "Tota" got cut off
    # by a column boundary during extraction). A real line item never
    # starts with a single stray lowercase letter followed by a space.
    if re.match(r'^[a-z]\s+\w', label_clean):
        return True

    return False


def check_term_conflict(label, category):
    label_lower = label.lower()
    if "short" in label_lower and "long_term" in category:
        return True
    if "long" in label_lower and "short_term" in category:
        return True
    if "after" in label_lower and category == "profit_before_tax":
        return True

    # NEW: "Unclaimed dividend" and "Unpaid dividend" are two genuinely
    # DIFFERENT line items (they were being fuzzy-matched into one
    # category, silently hiding whichever one didn't win), so make sure
    # each one only matches its own category.
    if category == "unclaimed_dividend" and "unpaid" in label_lower:
        return True
    if category == "unpaid_dividend" and "unclaimed" in label_lower:
        return True

    if "proceeds" in label_lower and category == "repayment_long_term_financing":
        return True
    if "repayment" in label_lower and category == "long_term_borrowings":
        return True
    if "loss" in label_lower and category == "proceeds_disposal_fixed_assets":
        return True
    # NEW: "Net current assets / Working capital" is a Financial
    # Highlights summary-table METRIC (a snapshot ratio), not the Cash
    # Flow statement's "Net decrease/increase in working capital" line
    # -- they share the words "net" and "working capital" but are
    # conceptually completely different things.
    if "net current assets" in label_lower and category == "net_decrease_working_capital":
        return True
    # NEW: "Revenue" (the Income Statement's top line) was being
    # fuzzy-matched to "reserves" via that category's own "revenue
    # reserves" synonym, since they share the word "revenue". A
    # genuine reserves line always has the word "reserve" in it
    # somewhere -- bare "Revenue" never does.
    if category == "reserves" and "reserve" not in label_lower:
        return True
    # NEW: "- revenue" (a continuation of "Reserves - capital / -
    # revenue", i.e. revenue reserves) was matching the Income
    # Statement's "revenue" category because of the bare "revenue"
    # synonym added for P&L's top line. A label starting with "-" is a
    # continuation marker from the row above, never a real standalone
    # Income Statement heading.
    if category == "revenue" and label.strip().startswith("-"):
        return True
    # NEW: "Total equity" (equity-only subtotal) and "Total Equity and
    # Liabilities" (the grand total, matching Total Assets) are
    # different figures -- one used to swallow the other since both
    # contain "total equity".
    if category == "total_equity" and "liabilit" in label_lower:
        return True
    if category == "total_equity_and_liabilities" and "liabilit" not in label_lower:
        return True
    # NEW: "Authorised capital" is a nominal ceiling/limit on how much
    # share capital COULD be issued, not the actual paid-up capital
    # that belongs in the real balance sheet figure. "Issued,
    # subscribed and paid-up capital" is the real share_capital value.
    if category == "share_capital" and ("authoris" in label_lower or "authoriz" in label_lower):
        return True

    # GENERAL RULE 1: any category starting with "total_" represents a
    # subtotal/total line. If the row's label doesn't actually contain
    # the word "total", it's almost certainly a DIFFERENT (non-total)
    # line item that just shares wording with the total's synonym
    # phrase (e.g. plain "Current assets" vs "Total current assets").
    # This generalizes what used to be hand-written just for
    # total_non_current_assets -- now it auto-applies to every
    # "total_*" category we add, present or future.
    KNOWN_COLLOQUIAL_TOTALS = {"total_non_current_assets": "fixed assets"}
    if category.startswith("total_") and "total" not in label_lower:
        allowed_prefix = KNOWN_COLLOQUIAL_TOTALS.get(category)
        if not (allowed_prefix and label_lower.strip().startswith(allowed_prefix)):
            return True

    # GENERAL RULE 2: "current" vs "non-current" mismatch, for ANY
    # category name (not hand-written per category) -- e.g. a
    # "total_current_liabilities" category shouldn't grab a "Total
    # non-current liabilities" row and vice versa.
    category_is_non_current = "non_current" in category
    label_says_non_current = "non-current" in label_lower or "non current" in label_lower
    label_says_plain_current = "current" in label_lower and not label_says_non_current

    if category_is_non_current and label_says_plain_current:
        return True
    if not category_is_non_current and "current" in category and label_says_non_current:
        return True

    # GENERAL RULE 3: assets vs liabilities mismatch -- a category name
    # ending in "_assets" shouldn't match a label that's clearly about
    # liabilities, and vice versa.
    #
    # FIX: this was too aggressive -- "Lease liability AGAINST RIGHT OF
    # USE ASSETS" is a completely normal, standard label for a real
    # liability (lease_liabilities), but it legitimately mentions
    # "assets" because it's describing what the lease relates to. The
    # rule was blocking this correct match entirely. Categories that
    # commonly co-occur with "assets" in their own normal wording are
    # exempted from this specific check.
    ASSETS_MENTION_EXEMPT = {"lease_liabilities", "right_of_use_assets"}
    if category not in ASSETS_MENTION_EXEMPT:
        if category.endswith("_assets") and "liabilit" in label_lower:
            return True
        if category.endswith("_liabilities") and re.search(r'\bassets?\b', label_lower):
            return True

    # Specific to total_non_current_assets: depreciation/amortisation
    # note-lines embed the phrase "fixed assets" but are a completely
    # different P&L/note line, not the balance-sheet subtotal.
    if category == "total_non_current_assets":
        if "depreciation" in label_lower or "amorti" in label_lower:
            return True

    return False


def clean_mojibake(text):
    """FIX: several companies' PDFs (Fauji, Nishat, UBL, NETSOL,
    Sapphire, MCB) have text extracted with a UTF-8 decoding mismatch,
    producing garbled sequences like "â€™" instead of an apostrophe, or
    "â€“" instead of a dash (e.g. "Directorsâ€™ Report" is really
    "Directors' Report"). This silently wrecked fuzzy-match quality on
    every label containing an apostrophe or dash in these reports.
    Replacing the common mis-decoded sequences with their real
    characters fixes this across all affected companies at once."""
    replacements = {
        "â€™": "'", "â€˜": "'",
        "â€œ": '"', "â€\x9d": '"',
        "â€“": "-", "â€”": "-",
        "â€¦": "...",
        "â€": "'",  # leftover fragment after other replacements
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def get_label_variants(row):
    parts = [p.strip() for p in row[:3] if p and p.strip()]
    parts = [clean_mojibake(p) for p in parts]
    spaced = " ".join(parts)
    no_space = "".join(parts)
    return list({spaced, no_space})


def normalize_text(text):
    """FIX: many PDFs (Fauji, Lucky Cement, MCB, Nishat, NETSOL,
    Sapphire, SYS) have mojibake encoding artifacts -- e.g. "â€™"
    instead of an apostrophe, "â€“" instead of a dash. This happens when
    UTF-8 bytes get misread as Latin-1/Windows-1252 during PDF text
    extraction. These broken characters were silently killing fuzzy
    match scores across many companies, since our synonym lists use
    plain ASCII punctuation. Normalize both to plain ASCII before
    comparing."""
    replacements = {
        "â€™": "'", "â€˜": "'", "â€œ": '"', "â€\x9d": '"',
        "â€“": "-", "â€”": "-", "â€¦": "...",
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def match_label_best(row, synonyms_dict, threshold=78, tie_margin=2.0):
    value_2025 = row[4].strip() if len(row) > 4 and row[4] else ""
    value_2024 = row[5].strip() if len(row) > 5 and row[5] else ""

    if not value_2025 and not value_2024:
        return None, 0, None

    label_check = str(row[2]).strip() if len(row) > 2 and row[2] else ""
    # NEW: "- revenue" / "- capital" (a short, dash-prefixed
    # continuation of the row above, e.g. "Reserves - capital" / "-
    # revenue") is always a Reserves breakdown sub-line in these
    # reports, never a standalone Income Statement or other category
    # match -- its own text is too short/ambiguous to fuzzy-match
    # correctly on its own.
    stripped_check = label_check.lstrip("-").strip().lower()
    if label_check.startswith("-") and stripped_check in ("revenue", "capital") and len(label_check) < 15:
        return "reserves", 95.0, label_check

    variants = get_label_variants(row)
    best_match, best_score, best_variant, best_full, best_synonym_len = None, 0, None, 0, 0

    for variant in variants:
        if len(variant.strip()) < 5:
            continue
        if is_garbled(variant):
            continue
        if is_junk_label(variant):
            continue

        for standard_name, synonym_list in synonyms_dict.items():
            if check_term_conflict(variant, standard_name):
                continue

            for synonym in synonym_list:
                variant_norm = normalize_text(variant.lower())
                synonym_norm = normalize_text(synonym.lower())
                partial = fuzz.partial_ratio(variant_norm, synonym_norm)
                full = fuzz.ratio(variant_norm, synonym_norm)
                combined = (partial * 0.6) + (full * 0.4)
                synonym_len = len(synonym)

                # PRIORITY / TIE-BREAK CHAIN -- this is exactly what
                # caused the old "Fixed Assets" vs "PP&E" mix-up: a
                # generic/partial match nudging out the truly correct
                # category. Three levels, in order:
                #   1. Clear win: combined score meaningfully higher ->
                #      always replaces the current best.
                #   2. Near-tie, more EXACT: scores are close, but this
                #      candidate's full (exact) ratio is higher -> real
                #      wording similarity beats mere substring overlap.
                #   3. Near-tie, more SPECIFIC: scores AND full-ratio are
                #      both close -> prefer the longer/more specific
                #      synonym text, since a short generic phrase
                #      ("assets") is more likely a coincidental partial
                #      match than a long precise one ("total non-current
                #      assets").
                is_clear_win = combined > best_score + tie_margin
                is_near_tie_more_exact = (
                    combined > best_score - tie_margin and full > best_full + tie_margin
                )
                is_near_tie_more_specific = (
                    combined > best_score - tie_margin
                    and full > best_full - tie_margin
                    and synonym_len > best_synonym_len
                )

                if is_clear_win or is_near_tie_more_exact or is_near_tie_more_specific:
                    best_score, best_match, best_variant, best_full, best_synonym_len = (
                        combined, standard_name, variant, full, synonym_len
                    )

    if best_score >= threshold:
        return best_match, best_score, best_variant
    return None, best_score, best_variant


def find_total_assets_anchor(table):
    """Scans a balance_sheet table for the row that's the GRAND 'Total
    Assets' line (not 'Total non-current assets' or 'Total current
    assets' -- those are sub-totals). Returns its row index, or None.

    FIX: this alone isn't reliable for disambiguating asset-side vs
    liability-side items -- some companies print the Equity &
    Liabilities section on an EARLIER page than the Assets section
    (reversed from the usual Assets-first order). In that layout, ALL
    of the Liabilities section's rows come BEFORE the "Total Assets"
    anchor (which only appears once the Assets page is reached),
    causing a genuine liability like "Deferred taxation" to be wrongly
    treated as asset-side. See find_assets_section_start for the fix
    used by resolve_ambiguous_category."""
    for i, row in enumerate(table):
        if not row or len(row) < 3 or not row[2]:
            continue
        label = str(row[2]).strip().lower()
        if "current" in label:
            continue  # skip "total non-current assets" / "total current assets"
        if "total" in label and "asset" in label:
            return i
    return None


def find_assets_section_start(table):
    """NEW: finds the row that's the standalone "ASSETS" section
    header -- a much more reliable boundary marker than "Total Assets"
    position, since it works regardless of whether a company prints
    Assets before or after Equity & Liabilities. Everything from this
    row onward (until the table ends, or a new non-asset section
    header appears) is the Assets side; everything before it is
    Liabilities & Equity."""
    for i, row in enumerate(table):
        if not row or len(row) < 3 or not row[2]:
            continue
        label = str(row[2]).strip().upper()
        if label in ("ASSETS", "NON-CURRENT ASSETS") and i > 0:
            # NON-CURRENT ASSETS only counts as the section start if we
            # haven't already seen a bare "ASSETS" header (some reports
            # skip straight to "NON-CURRENT ASSETS" without a separate
            # "ASSETS" line).
            return i
    return None


def resolve_ambiguous_category(matched, variant, row_index, assets_start, assets_end):
    """For categories that use IDENTICAL wording on both the Assets
    side and Liabilities side of a balance sheet, use the row's
    position relative to the Assets section boundaries to pick the
    correct specific category.

    FIX: previously this only checked position relative to "Total
    Assets" (assuming Assets always comes BEFORE Liabilities on the
    page). Some companies print Liabilities & Equity FIRST, then
    Assets on a later page -- in that layout, every Liabilities-side
    row would incorrectly count as "before Total Assets" = asset-side.
    Now we check whether the row falls INSIDE the Assets section
    (between its "ASSETS" header and its "Total Assets" line) --this
    works regardless of which section comes first physically."""
    variant_lower = variant.lower()

    def is_asset_side():
        if assets_start is not None and assets_end is not None and assets_start <= assets_end:
            return assets_start <= row_index <= assets_end
        # Fall back to the old "before Total Assets" heuristic if we
        # couldn't find a reliable ASSETS section header.
        return assets_end is not None and row_index < assets_end

    if matched == "long_term_deposits":
        if assets_end is None:
            return matched  # no anchor -- can't disambiguate, keep generic
        return "long_term_deposits_asset" if is_asset_side() else "long_term_deposits_liability"

    if matched in ("deferred_tax_assets", "deferred_tax_liabilities"):
        # If the label ITSELF already says "asset" or "liabilit", trust
        # that -- it's not actually ambiguous wording.
        if "asset" in variant_lower or "liabilit" in variant_lower:
            return matched
        if assets_end is None:
            return matched
        return "deferred_tax_assets" if is_asset_side() else "deferred_tax_liabilities"

    if matched in ("income_tax_expense", "taxation_net") and variant_lower.strip() in ("taxation", "taxation net", "taxation - net"):
        # NEW: bare "Taxation - net" appears with IDENTICAL wording on
        # BOTH the Current Assets side (a tax refund/prepayment
        # receivable) and the Current Liabilities side (tax payable) --
        # two genuinely different things, disambiguated the same way
        # as long_term_deposits/deferred_tax above.
        if assets_end is None:
            return matched
        return "tax_refund_receivable" if is_asset_side() else "income_tax_expense"

    return matched


if __name__ == "__main__":
    ranges_df = pd.read_csv("output/output_page_ranges_v2.csv")
    # FIX: this used to read ranges_df as-is, pulling in BOTH
    # Consolidated and Unconsolidated ranges for any company that
    # reports both (e.g. Engro Fertilizers, Abbott Labs) -- doubling
    # up every line item with two genuinely different, both-correct
    # numbers under the same label. verify_extraction_consistency.py
    # already filtered to consolidated-only, so it was silently
    # comparing against the wrong version half the time and reporting
    # false "inconsistent" results. Applying the same shared filter
    # here brings this script in line with the rest of the pipeline.
    ranges_df = filter_to_consolidated(ranges_df)
    statement_types = ["balance_sheet", "profit_and_loss", "cash_flow"]

    results = []
    unmatched_labels = []

    for filename in ranges_df["filename"].unique():
        company_ranges = ranges_df[
            (ranges_df["filename"] == filename) &
            (ranges_df["type"].isin(statement_types))
        ]

        for _, range_row in company_ranges.iterrows():
            pdf_path = f"data/{filename}"
            multi_type = range_row["multi_type"] if "multi_type" in range_row else None
            # NEW: only use multi_type as a POSITIVE override (force
            # split when Statement ID confirmed 2+ statement types on
            # this page). When it's False/unknown, we let the
            # geometric+text-verified detection in extract_by_position.py
            # decide -- that detection has since been proven reliable
            # (it correctly handles single-statement pages whose OWN
            # sections are split into two visual columns too, like a
            # Cash Flow statement with Operating on the left and
            # Investing/Financing on the right).
            force_split = True if multi_type is True else None
            table, reason = extract_table_for_range(pdf_path, range_row["start_page"], range_row["end_page"], multi_type=force_split)

            if reason != "ok" or not table:
                continue

            # NEW: keep BOTH Consolidated and Unconsolidated versions,
            # tagged, instead of guessing which one to drop upstream.
            # This lets the person choose which version they want at
            # query time -- more reliable than a heuristic filter,
            # since it never risks silently picking the wrong one.
            version = range_row["version"] if "version" in range_row else "unknown"

            # NEW: find BOTH the Assets section start (the "ASSETS"
            # header) and end (the "Total Assets" line) -- ONLY for
            # balance_sheet -- this is what lets us tell apart
            # identically-worded asset-side vs liability-side items,
            # correctly, regardless of whether Assets or
            # Liabilities+Equity is printed first on the page.
            assets_start = find_assets_section_start(table) if range_row["type"] == "balance_sheet" else None
            assets_end = find_total_assets_anchor(table) if range_row["type"] == "balance_sheet" else None

            for row_index, row in enumerate(table):
                if len(row) < 6:
                    continue
                matched, score, variant = match_label_best(row, SYNONYMS)

                if matched and range_row["type"] == "balance_sheet":
                    matched = resolve_ambiguous_category(matched, variant, row_index, assets_start, assets_end)

                if matched:
                    results.append({
                        "filename": filename,
                        "statement_type": range_row["type"],
                        "version": version,
                        "raw_label": variant,
                        "matched_category": matched,
                        "score": round(score, 1),
                        # NEW: capture the raw value strings HERE, at the
                        # exact moment of matching -- instead of just
                        # recording the label text and making
                        # value_extraction.py re-search for a row with
                        # that same label later. That re-search broke
                        # whenever TWO rows shared an identical label
                        # (e.g. "Long term deposits" appears once on the
                        # Assets side and once on the Liabilities side
                        # with different values) -- it would always find
                        # the FIRST matching row, so both the asset and
                        # liability entries silently got the SAME
                        # (wrong, for one of them) value. Recording the
                        # value immediately removes any ambiguity.
                        "raw_value_2025": row[4] if len(row) > 4 else None,
                        "raw_value_2024": row[5] if len(row) > 5 else None,
                    })
                elif score > 0:
                    unmatched_labels.append({
                        "filename": filename,
                        "statement_type": range_row["type"],
                        "version": version,
                        "raw_label": variant,
                        "best_score": round(score, 1)
                    })

    results_df = pd.DataFrame(results)
    unmatched_df = pd.DataFrame(unmatched_labels)

    results_df.to_csv("output/header_matches.csv", index=False)
    unmatched_df.to_csv("output/header_unmatched.csv", index=False)

    print(f"Total matched rows: {len(results_df)}")
    print(f"Total unmatched rows: {len(unmatched_df)}")
    print(f"Average match confidence: {results_df['score'].mean():.1f}%")