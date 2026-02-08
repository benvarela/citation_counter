import os
import sys
import argparse
import subprocess
import tempfile

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

CITED_BY_PATH = "data/cited_by_info_gender.xlsx"
DATA_PATH = "data/data.xlsx"
OUTPUT_DIR = "data/plots"

# Constants
BIN_WIDTH = 0.2
MIN_BIN_N = 10
MALE_COLOR = "#4393c3"    # blue
FEMALE_COLOR = "#d6604d"  # red/pink

GROUP_COLOR_MM = "#4393c3"  # blue
GROUP_COLOR_MW = "#5ab4ac"  # teal
GROUP_COLOR_WM = "#9e9ac8"  # lavender
GROUP_COLOR_WW = "#d6604d"  # pink-red

GROUP_COLORS = {
    "MM": GROUP_COLOR_MM,
    "MW": GROUP_COLOR_MW,
    "WM": GROUP_COLOR_WM,
    "WW": GROUP_COLOR_WW,
}

GROUP_LABELS = {
    "MM": "Man First, Man Last",
    "MW": "Man First, Woman Last",
    "WM": "Woman First, Man Last",
    "WW": "Woman First, Woman Last",
}


def categorize_gender(prob_male):
    """Categorize a prob_male value into 'M', 'W', or 'U' (unknown)."""
    if pd.isna(prob_male) or prob_male == -1:
        return "U"
    if prob_male >= 0.7:
        return "M"
    if prob_male <= 0.3:
        return "W"
    return "U"


def load_data(cited_by_path, data_path):
    """Read both Excel files and return as DataFrames."""
    cited_by_df = pd.read_excel(cited_by_path, engine="openpyxl")
    data_df = pd.read_excel(data_path, engine="openpyxl")
    return cited_by_df, data_df


def _normalize_name(name):
    """Normalize an author name to a comparable form (lowercase, sorted parts)."""
    name = str(name).strip().lower()
    # Handle "Last,First" and "First Last" formats
    parts = [p.strip() for p in name.replace(",", " ").split() if p.strip()]
    return frozenset(parts)


def remove_self_citations(cited_by_df, data_df):
    """Remove rows from cited_by_df where a first/last author of the citing paper
    matches a first/last author of the cited paper (self-citations).

    Matching is done by comparing author names from cited_by_df (author_name column
    for rows where first_author or last_author is TRUE) against the first/last author
    names of the cited paper from data_df (firstlastauthor_openalex column).
    """
    before = len(cited_by_df)

    # Build a set of first/last author names per citing_doi
    fl_mask = (
        cited_by_df["first_author"].astype(str).str.strip().str.upper().eq("TRUE")
        | cited_by_df["last_author"].astype(str).str.strip().str.upper().eq("TRUE")
    )
    citing_authors = (
        cited_by_df[fl_mask]
        .groupby("citing_doi")["author_name"]
        .apply(lambda names: {_normalize_name(n) for n in names})
        .to_dict()
    )

    # Build a set of first/last author names per cited DOI from data_df
    cited_authors = {}
    for _, row in data_df.iterrows():
        doi = str(row["DOI"]).strip().lower()
        fl = str(row.get("firstlastauthor_openalex", ""))
        if pd.isna(fl) or fl == "nan":
            continue
        names = {_normalize_name(n) for n in fl.split(";") if n.strip()}
        cited_authors[doi] = names

    # Identify (citing_doi, cited_doi) pairs that are self-citations
    link = cited_by_df[["citing_doi", "cited_doi"]].drop_duplicates()
    self_cite_pairs = set()
    for _, row in link.iterrows():
        citing_doi = row["citing_doi"]
        cited_doi = str(row["cited_doi"]).strip().lower()
        citing_names = citing_authors.get(citing_doi, set())
        cited_names = cited_authors.get(cited_doi, set())
        if citing_names & cited_names:
            self_cite_pairs.add((citing_doi, row["cited_doi"]))

    # Remove all rows belonging to self-citation pairs
    if self_cite_pairs:
        remove_mask = cited_by_df.apply(
            lambda r: (r["citing_doi"], r["cited_doi"]) in self_cite_pairs, axis=1
        )
        cited_by_df = cited_by_df[~remove_mask].reset_index(drop=True)

    after = len(cited_by_df)
    total_links = len(link)
    pct_links = len(self_cite_pairs) / total_links * 100 if total_links else 0
    pct_rows = (before - after) / before * 100 if before else 0
    print(f"  Self-citations found: {len(self_cite_pairs)} / {total_links} "
          f"citation links ({pct_links:.1f}%)")
    print(f"  Rows removed: {before - after} / {before} ({pct_rows:.1f}%), "
          f"{after} rows remaining")
    return cited_by_df


def prepare_scatter_data(cited_by_df, data_df, author_filter_col, y_col):
    """Filter and merge data to produce x (prob_male from citing) and y (prob_male from cited) Series.

    Args:
        cited_by_df: DataFrame from cited_by_info_gender.xlsx (citing paper authors)
        data_df: DataFrame from data.xlsx (cited paper authors)
        author_filter_col: 'first_author' or 'last_author' column to filter on TRUE
        y_col: 'first_prob_male' or 'last_prob_male' from data.xlsx
    """
    # Filter cited_by_df where author_filter_col is TRUE (handle bool and string)
    col = cited_by_df[author_filter_col]
    if col.dtype == bool:
        mask = col
    else:
        mask = col.astype(str).str.strip().str.upper() == "TRUE"
    filtered = cited_by_df[mask].copy()

    # Case-insensitive DOI matching via .str.strip().str.lower()
    filtered["doi_key"] = filtered["cited_doi"].astype(str).str.strip().str.lower()
    data_copy = data_df.copy()
    data_copy["doi_key"] = data_copy["DOI"].astype(str).str.strip().str.lower()

    merged = filtered.merge(data_copy[["doi_key", y_col]], on="doi_key", how="inner")

    matched = len(merged)
    unmatched = len(filtered) - matched
    print(f"  DOI matching: {matched} matched, {unmatched} unmatched")

    x = merged["prob_male"]
    y = merged[y_col]

    # Drop rows where either value < 0 (sentinel for unknown) or NaN
    valid = (x >= 0) & (y >= 0) & x.notna() & y.notna()
    x = x[valid].reset_index(drop=True)
    y = y[valid].reset_index(drop=True)

    print(f"  After filtering invalid values: {len(x)} data points")
    return x, y


def run_r_stats(x, y, label, output_dir):
    """Write data to temp CSV, call R script, return paths to output CSVs."""
    r_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gender_citation_stats.R")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        tmp_csv = f.name
        pd.DataFrame({"p_citing": x, "p_cited": y}).to_csv(f, index=False)

    try:
        result = subprocess.run(
            ["Rscript", r_script, tmp_csv, output_dir, label],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  R script failed (exit {result.returncode}):")
            if result.stderr:
                print(result.stderr)
            return None
        if result.stdout:
            print(f"  {result.stdout.strip()}")
    finally:
        os.unlink(tmp_csv)

    return {
        "binned": os.path.join(output_dir, f"{label}_binned.csv"),
        "regression": os.path.join(output_dir, f"{label}_regression.csv"),
    }


def read_r_results(paths):
    """Read the R output CSVs into DataFrames."""
    return {
        "binned": pd.read_csv(paths["binned"]),
        "regression": pd.read_csv(paths["regression"]),
    }


def save_figure(fig, output_dir, filename):
    """Save figure as PNG (300dpi) and SVG, then close."""
    fig.savefig(os.path.join(output_dir, f"{filename}.png"), dpi=300, bbox_inches="tight")
    fig.savefig(os.path.join(output_dir, f"{filename}.svg"), bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {filename}.png and {filename}.svg")


def plot_binned_expectation(binned_df, reg_df, title, output_dir, filename):
    """Bar chart of binned E[p_cited] - baseline with SE error bars and linear fit."""
    fig, ax = plt.subplots(figsize=(8, 5))

    # Extract regression scalars
    p_bar = reg_df["p_bar"].iloc[0]
    intercept = reg_df["intercept"].iloc[0]
    slope = reg_df["slope"].iloc[0]
    pval = reg_df["slope_pvalue"].iloc[0]
    r2 = reg_df["r_squared"].iloc[0]
    male_overcite = reg_df["male_overcite_pct"].iloc[0]
    female_overcite = reg_df["female_overcite_pct"].iloc[0]

    colors = [MALE_COLOR if d > 0 else FEMALE_COLOR for d in binned_df["delta"]]

    # Bar chart from 0 to delta with SE error bars
    ax.bar(
        binned_df["bin_center"], binned_df["delta"],
        width=BIN_WIDTH * 0.8, color=colors, edgecolor="black", linewidth=0.5,
        yerr=binned_df["se"], capsize=4, ecolor="black",
    )

    # Overlay linear fit with 95% CI band (convert from p_cited space to % deviation)
    x_grid = reg_df["x_grid"].values
    y_fit = (reg_df["linear_fit"].values - p_bar) / p_bar * 100
    y_lower = (reg_df["linear_lower"].values - p_bar) / p_bar * 100
    y_upper = (reg_df["linear_upper"].values - p_bar) / p_bar * 100
    ax.fill_between(x_grid, y_lower, y_upper, alpha=0.2, color="green", label="95% CI")
    ax.plot(x_grid, y_fit, color="green", linewidth=1.5, linestyle="-", alpha=0.8, label="Linear fit")

    ax.axhline(0, color="gray", linestyle="--", linewidth=1, label="Gender-neutral baseline")
    ax.set_xlabel("P(male) of citing author")
    ax.set_ylabel("% deviation from baseline P(male) of cited author")
    ax.set_title(title)
    ax.legend(loc="upper left", fontsize=8)

    # Stats annotation (upper right)
    pval_str = f"{pval:.2e}" if pval < 0.001 else f"{pval:.4f}"
    stats_text = (
        f"Linear slope = {slope:.4f}\n"
        f"p = {pval_str}\n"
        f"R\u00b2 = {r2:.4f}"
    )
    ax.text(
        0.98, 0.98, stats_text,
        transform=ax.transAxes, fontsize=8,
        verticalalignment="top", horizontalalignment="right",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.9),
    )

    # Effect size annotation (lower left)
    effect_text = (
        f"100% male citer: {male_overcite:+.1f}% male cited\n"
        f"100% female citer: {female_overcite:+.1f}% male cited\n"
        f"Baseline (Included Papers Average Probability Male)\n"
        f"P(male) = {p_bar:.3f}"
    )
    ax.text(
        0.02, 0.02, effect_text,
        transform=ax.transAxes, fontsize=8,
        verticalalignment="bottom", horizontalalignment="left",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow", alpha=0.9),
    )

    save_figure(fig, output_dir, filename)



def prepare_group_data(cited_by_df, data_df):
    """Build a DataFrame of citing_group × cited_group for every citation link."""
    # --- Citing paper groups ---
    # Get first author prob_male per citing_doi
    first_mask = cited_by_df["first_author"].astype(str).str.strip().str.upper() == "TRUE"
    last_mask = cited_by_df["last_author"].astype(str).str.strip().str.upper() == "TRUE"

    citing_first = (
        cited_by_df[first_mask][["citing_doi", "prob_male"]]
        .rename(columns={"prob_male": "citing_first_prob"})
    )
    citing_last = (
        cited_by_df[last_mask][["citing_doi", "prob_male"]]
        .rename(columns={"prob_male": "citing_last_prob"})
    )

    # One row per citing_doi: take first occurrence if duplicates
    citing_first = citing_first.drop_duplicates(subset="citing_doi", keep="first")
    citing_last = citing_last.drop_duplicates(subset="citing_doi", keep="first")

    citing = citing_first.merge(citing_last, on="citing_doi", how="inner")
    citing["citing_first_gender"] = citing["citing_first_prob"].apply(categorize_gender)
    citing["citing_last_gender"] = citing["citing_last_prob"].apply(categorize_gender)
    citing["citing_group"] = citing["citing_first_gender"] + citing["citing_last_gender"]

    # Drop unknown
    citing = citing[~citing["citing_group"].str.contains("U")].copy()

    # --- Cited paper groups ---
    data_copy = data_df.copy()
    data_copy["cited_first_gender"] = data_copy["first_prob_male"].apply(categorize_gender)
    data_copy["cited_last_gender"] = data_copy["last_prob_male"].apply(categorize_gender)
    data_copy["cited_group"] = data_copy["cited_first_gender"] + data_copy["cited_last_gender"]
    data_copy = data_copy[~data_copy["cited_group"].str.contains("U")].copy()
    data_copy["doi_key"] = data_copy["DOI"].astype(str).str.strip().str.lower()

    # --- Merge on cited_doi ↔ DOI ---
    # Also need cited_doi from cited_by to link citing→cited
    link = cited_by_df[["citing_doi", "cited_doi"]].drop_duplicates()
    link["doi_key"] = link["cited_doi"].astype(str).str.strip().str.lower()

    merged = (
        citing[["citing_doi", "citing_group"]]
        .merge(link[["citing_doi", "doi_key"]], on="citing_doi", how="inner")
        .merge(data_copy[["doi_key", "cited_group"]], on="doi_key", how="inner")
    )

    print(f"\nGroup analysis: {len(merged)} citation links with known citing & cited groups")
    print(f"  Citing group counts: {merged['citing_group'].value_counts().to_dict()}")
    print(f"  Cited group counts:  {merged['cited_group'].value_counts().to_dict()}")

    return merged, data_copy


def compute_group_stats(merged_df, data_known_df):
    """Compute % over/undercitation for each citing group × cited group pair."""
    # Baseline: proportion of each cited group among all known-gender cited papers
    baseline = data_known_df["cited_group"].value_counts(normalize=True)

    rows = []
    for citing_grp in ["MM", "MW", "WM", "WW"]:
        subset = merged_df[merged_df["citing_group"] == citing_grp]
        n = len(subset)
        if n == 0:
            continue
        observed = subset["cited_group"].value_counts(normalize=True)

        for cited_grp in ["MM", "MW", "WM", "WW"]:
            p_base = baseline.get(cited_grp, 0)
            p_obs = observed.get(cited_grp, 0)
            if p_base == 0:
                continue
            deviation = (p_obs - p_base) / p_base * 100
            se = np.sqrt(p_obs * (1 - p_obs) / n) / p_base * 100
            rows.append({
                "citing_group": citing_grp,
                "cited_group": cited_grp,
                "n": n,
                "p_baseline": p_base,
                "p_observed": p_obs,
                "deviation_pct": deviation,
                "se_pct": se,
            })

    stats_df = pd.DataFrame(rows)
    print("\nGroup deviation stats:")
    for _, r in stats_df.iterrows():
        print(f"  {r['citing_group']} → {r['cited_group']}: "
              f"{r['deviation_pct']:+.1f}% (SE={r['se_pct']:.1f}%, n={r['n']})")
    return stats_df


def plot_group_bars(stats_df, output_dir):
    """Create one bar plot per citing group showing % deviation from baseline."""
    for citing_grp in ["MM", "MW", "WM", "WW"]:
        sub = stats_df[stats_df["citing_group"] == citing_grp]
        if sub.empty:
            continue

        fig, ax = plt.subplots(figsize=(7, 5))
        cited_groups = sub["cited_group"].values
        deviations = sub["deviation_pct"].values
        errors = sub["se_pct"].values
        n_citations = sub["n"].iloc[0]

        colors = [GROUP_COLORS[g] for g in cited_groups]
        x_pos = np.arange(len(cited_groups))

        ax.bar(x_pos, deviations, color=colors, edgecolor="black", linewidth=0.5,
               yerr=errors, capsize=5, ecolor="black")
        ax.axhline(0, color="gray", linestyle="--", linewidth=1)

        ax.set_xticks(x_pos)
        ax.set_xticklabels(cited_groups, fontsize=8)
        ax.set_ylabel("% Deviation from Baseline")
        ax.set_title(f"Citation Pattern: {citing_grp} Citing Group ({GROUP_LABELS[citing_grp]})")

        ax.text(
            0.98, 0.98, f"n = {n_citations} citations",
            transform=ax.transAxes, fontsize=9,
            verticalalignment="top", horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.9),
        )

        save_figure(fig, output_dir, f"gender_group_{citing_grp}")


def analyze_and_plot(cited_by_df, data_df, output_dir):
    """Run full analysis: 4 author-role combos × 3 plot types."""
    os.makedirs(output_dir, exist_ok=True)

    # Temp dir for R intermediate CSVs
    r_output_dir = tempfile.mkdtemp(prefix="gender_stats_")

    combos = [
        ("first_author", "first_prob_male", "first", "first"),
        ("last_author",  "first_prob_male", "last",  "first"),
        ("first_author", "last_prob_male",  "first", "last"),
        ("last_author",  "last_prob_male",  "last",  "last"),
    ]

    for author_filter_col, y_col, citing_role, cited_role in combos:
        label = f"{citing_role}_vs_{cited_role}"
        print(f"\nAnalyzing: citing {citing_role} author vs cited {cited_role} author")

        x, y = prepare_scatter_data(cited_by_df, data_df, author_filter_col, y_col)
        if len(x) < 10:
            print(f"  Skipping {label}: not enough data points ({len(x)})")
            continue

        paths = run_r_stats(x, y, label, r_output_dir)
        if paths is None:
            print(f"  Skipping {label}: R computation failed")
            continue

        results = read_r_results(paths)

        reg = results["regression"]
        p_bar = reg["p_bar"].iloc[0]
        slope = reg["slope"].iloc[0]
        r2 = reg["r_squared"].iloc[0]
        pval = reg["slope_pvalue"].iloc[0]
        male_oc = reg["male_overcite_pct"].iloc[0]
        female_oc = reg["female_overcite_pct"].iloc[0]
        print(f"  Stats: p_bar={p_bar:.4f}, slope={slope:.4f}, R²={r2:.4f}, p={pval:.2e}")
        print(f"  Effect: 100% male citer → {male_oc:+.1f}% male cited; "
              f"100% female citer → {female_oc:+.1f}% female cited")

        title_suffix = f"Citing {citing_role.title()} Author vs Cited {cited_role.title()} Author"

        plot_binned_expectation(
            results["binned"], reg,
            f"Binned Gender Expectation: {title_suffix}",
            output_dir, f"gender_binned_{citing_role}_vs_{cited_role}",
        )

        # Clean up R intermediate CSVs
        for p in paths.values():
            if os.path.exists(p):
                os.unlink(p)

    # Clean up temp dir
    try:
        os.rmdir(r_output_dir)
    except OSError:
        pass

    # --- Group-based over/undercitation analysis ---
    print("\n--- Group-based citation analysis ---")
    merged_groups, data_known = prepare_group_data(cited_by_df, data_df)
    if len(merged_groups) > 0:
        stats = compute_group_stats(merged_groups, data_known)
        if not stats.empty:
            plot_group_bars(stats, output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate gender citation analysis plots (binned, regression)"
    )
    parser.add_argument("--cited-by", default=CITED_BY_PATH, help="Path to cited_by_info_gender.xlsx")
    parser.add_argument("--data", default=DATA_PATH, help="Path to data.xlsx")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="Output directory for plots")
    args = parser.parse_args()

    print("Loading data...")
    cited_by_df, data_df = load_data(args.cited_by, args.data)
    print(f"  cited_by: {len(cited_by_df)} rows, data: {len(data_df)} rows")

    print("Removing self-citations...")
    cited_by_df = remove_self_citations(cited_by_df, data_df)

    analyze_and_plot(cited_by_df, data_df, args.output_dir)
    print("\nDone.")
