"""
version_filter.py

Purpose: Shared helper for Header Identification / Value Extraction /
Query Engine so they all filter to CONSOLIDATED-only statement ranges
the same way, instead of pulling both Consolidated AND Unconsolidated
versions (which was doubling up every line item).

Logic: for each (filename, statement type) group, if ANY range is
tagged "consolidated", keep ONLY those consolidated ranges. If a
company never had a clear consolidated/unconsolidated split (e.g. it
only reports one set of statements, or our detection couldn't tell),
we keep whatever ranges exist rather than silently dropping the
company's data.
"""


def filter_to_consolidated(ranges_df):
    if "version" not in ranges_df.columns:
        # Older ranges CSV without version info -- nothing to filter on
        return ranges_df

    keep_indices = []
    for (filename, stype), group in ranges_df.groupby(["filename", "type"]):
        consolidated_rows = group[group["version"] == "consolidated"]
        if not consolidated_rows.empty:
            keep_indices.extend(consolidated_rows.index.tolist())
        else:
            # No consolidated version found for this company/statement --
            # keep everything available (e.g. unconsolidated-only or
            # unknown) so we don't lose the company's data entirely.
            keep_indices.extend(group.index.tolist())

    return ranges_df.loc[keep_indices]