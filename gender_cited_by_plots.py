import os
import sys
import argparse
import subprocess
import tempfile

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import chi2_contingency, chisquare

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
    "MM": "Male First, Male Last",
    "MW": "Male First, Female Last",
    "WM": "Female First, Male Last",
    "WW": "Female First, Female Last",
}

# Figure dimensions for group bar plots (mm → inches)
GROUP_FIG_WIDTH_MM = 235
GROUP_FIG_HEIGHT_MM = 125
GROUP_FIG_WIDTH = GROUP_FIG_WIDTH_MM / 25.4
GROUP_FIG_HEIGHT = GROUP_FIG_HEIGHT_MM / 25.4
GROUP_BAR_EDGE_WIDTH = 2.0
GROUP_LINE_WIDTH = 3.0

POSTER_THEME = {
    "tick_fontsize": 12,
    "label_fontsize": 16,
    "font_family": "Arial",
    "spine_linewidth": 2.0,
    "grid": False,
}


def style_group_axes(ax):
    """Apply consistent poster-theme styling to group bar plot axes."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(POSTER_THEME["spine_linewidth"])
    ax.spines["bottom"].set_linewidth(POSTER_THEME["spine_linewidth"])
    ax.tick_params(width=POSTER_THEME["spine_linewidth"],
                   labelsize=POSTER_THEME["tick_fontsize"])
    ax.xaxis.label.set_fontsize(POSTER_THEME["label_fontsize"])
    ax.yaxis.label.set_fontsize(POSTER_THEME["label_fontsize"])
    ax.xaxis.label.set_fontfamily(POSTER_THEME["font_family"])
    ax.yaxis.label.set_fontfamily(POSTER_THEME["font_family"])
    ax.title.set_fontfamily(POSTER_THEME["font_family"])
    if not POSTER_THEME["grid"]:
        ax.grid(False)
    # Add vertical padding so n= annotations don't overlap spines
    ax.margins(y=0.15)

def display_group_code(code):
    """Display group codes with F instead of W for plot output."""
    return code.replace("W", "F")

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
        .merge(data_copy[["doi_key", "cited_group", "SJR_scimago"]], on="doi_key", how="inner")
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
            n_pair = int((subset["cited_group"] == cited_grp).sum())
            rows.append({
                "citing_group": citing_grp,
                "cited_group": cited_grp,
                "n_total": n,
                "n_pair": n_pair,
                "p_baseline": p_base,
                "p_observed": p_obs,
                "deviation_pct": deviation,
                "se_pct": se,
            })

    stats_df = pd.DataFrame(rows)
    print("\nGroup deviation stats:")
    for _, r in stats_df.iterrows():
        print(f"  {r['citing_group']} → {r['cited_group']}: "
              f"{r['deviation_pct']:+.1f}% (SE={r['se_pct']:.1f}%, n_pair={r['n_pair']}, n_total={r['n_total']})")
    return stats_df


def plot_group_bars(stats_df, output_dir):
    """Create one bar plot per citing group showing % deviation from baseline."""
    for citing_grp in ["MM", "MW", "WM", "WW"]:
        sub = stats_df[stats_df["citing_group"] == citing_grp]
        if sub.empty:
            continue

        fig, ax = plt.subplots(figsize=(GROUP_FIG_WIDTH, GROUP_FIG_HEIGHT))
        cited_groups = sub["cited_group"].values
        deviations = sub["deviation_pct"].values
        errors = sub["se_pct"].values
        n_pairs = sub["n_pair"].values
        n_total = sub["n_total"].iloc[0]

        colors = [GROUP_COLORS[g] for g in cited_groups]
        x_pos = np.arange(len(cited_groups))

        ax.bar(x_pos, deviations, color=colors, edgecolor="black",
               linewidth=GROUP_BAR_EDGE_WIDTH,
               yerr=errors, capsize=5, ecolor="black")
        ax.axhline(0, color="gray", linestyle="--", linewidth=GROUP_LINE_WIDTH)

        ax.set_xticks(x_pos)
        ax.set_xticklabels([display_group_code(g) for g in cited_groups])
        ax.set_xlabel("First and Last Author Genders")
        ax.set_ylabel("% Deviation from Baseline")
        ax.set_title(
            f"Citation Pattern: {display_group_code(citing_grp)} Citing Group ({GROUP_LABELS[citing_grp]})"
        )
        style_group_axes(ax)

        # Place n just above positive error bars and just below negative error bars
        for i, (x, dev, err, np_) in enumerate(zip(x_pos, deviations, errors, n_pairs)):
            y_anchor = dev + err if dev >= 0 else dev - err
            y_offset = 3 if dev >= 0 else -3
            va = "bottom" if dev >= 0 else "top"
            ax.annotate(
                f"n={np_}",
                (x, y_anchor),
                textcoords="offset points",
                xytext=(0, y_offset),
                ha="center",
                va=va,
                fontsize=POSTER_THEME["tick_fontsize"],
            )

        ax.text(
            0.98, 0.98, f"n = {n_total} total citations",
            transform=ax.transAxes, fontsize=POSTER_THEME["tick_fontsize"],
            verticalalignment="top", horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.9),
        )

        save_figure(fig, output_dir, f"gender_group_{citing_grp}")


def plot_overall_cited_group_bars(merged_df, data_known_df, output_dir):
    """Bar plot of unadjusted % over/undercitation by cited gender group (all citing groups combined)."""
    baseline = data_known_df["cited_group"].value_counts(normalize=True)
    n_total = len(merged_df)
    observed = merged_df["cited_group"].value_counts(normalize=True)

    groups = ["MM", "MW", "WM", "WW"]
    rows = []
    for grp in groups:
        p_base = baseline.get(grp, 0)
        p_obs = observed.get(grp, 0)
        if p_base == 0:
            continue
        deviation = (p_obs - p_base) / p_base * 100
        se = np.sqrt(p_obs * (1 - p_obs) / n_total) / p_base * 100
        n_links = int((merged_df["cited_group"] == grp).sum())
        rows.append({
            "cited_group": grp,
            "deviation_pct": deviation,
            "se_pct": se,
            "n_links": n_links,
        })

    df = pd.DataFrame(rows)

    overall_size = 120 / 25.4  # 120mm in inches
    overall_fontsize = 18
    fig, ax = plt.subplots(figsize=(overall_size, overall_size))

    cited_groups = df["cited_group"].values
    deviations = df["deviation_pct"].values
    errors = df["se_pct"].values
    counts = df["n_links"].values

    colors = [GROUP_COLORS[g] for g in cited_groups]
    x_pos = np.arange(len(cited_groups))

    ax.bar(x_pos, deviations, color=colors, edgecolor="black",
           linewidth=GROUP_BAR_EDGE_WIDTH,
           yerr=errors, capsize=5, ecolor="black")
    ax.axhline(0, color="gray", linestyle="--", linewidth=GROUP_LINE_WIDTH)

    ax.set_xticks(x_pos)
    ax.set_xticklabels([display_group_code(g) for g in cited_groups], fontsize=overall_fontsize)
    ax.set_xlabel("First and Last Author Genders", fontsize=overall_fontsize, fontweight="bold")
    ax.set_ylabel("% Deviation from Baseline", fontsize=overall_fontsize, fontweight="bold")
    style_group_axes(ax)
    ax.tick_params(labelsize=overall_fontsize)

    for i, (x, dev, err, n) in enumerate(zip(x_pos, deviations, errors, counts)):
        y_anchor = dev + err if dev >= 0 else dev - err
        y_offset = 3 if dev >= 0 else -3
        va = "bottom" if dev >= 0 else "top"
        ax.annotate(
            f"n={n}",
            (x, y_anchor),
            textcoords="offset points",
            xytext=(0, y_offset),
            ha="center",
            va=va,
            fontsize=overall_fontsize,
        )

    save_figure(fig, output_dir, "gender_group_overall")


def overall_cited_group_stats(merged_df, data_known_df, output_dir):
    """Chi-square tests for overall cited group over/undercitation with pairwise comparisons."""
    groups = ["MM", "MW", "WM", "WW"]
    baseline = data_known_df["cited_group"].value_counts(normalize=True)
    n_total = len(merged_df)
    obs_counts = merged_df["cited_group"].value_counts()

    observed = np.array([obs_counts.get(g, 0) for g in groups])
    expected_prop = np.array([baseline.get(g, 0) for g in groups])
    expected = expected_prop * n_total

    # 1. Overall chi-square goodness-of-fit
    chi2, gof_p = chisquare(observed, f_exp=expected)
    df_gof = len(groups) - 1

    lines = []
    lines.append("Overall Cited Gender Group Statistics")
    lines.append("=" * 50)
    lines.append(f"\nn = {n_total} total citation links\n")

    lines.append("Observed vs Expected counts:")
    for i, g in enumerate(groups):
        dev = (observed[i] - expected[i]) / expected[i] * 100
        lines.append(f"  {display_group_code(g)}: observed={observed[i]}, "
                      f"expected={expected[i]:.1f}, deviation={dev:+.1f}%")

    lines.append(f"\nChi-square goodness-of-fit test:")
    lines.append(f"  X² = {chi2:.2f}, df = {df_gof}, p = {gof_p:.2e}")

    # 2. Pairwise 2x2 chi-square tests
    from itertools import combinations
    pairs = list(combinations(range(len(groups)), 2))
    pair_labels = []
    pair_pvals = []

    for i, j in pairs:
        # 2x2 table: rows = group i vs group j, cols = observed vs "other"
        table = np.array([
            [observed[i], expected[i]],
            [observed[j], expected[j]],
        ])
        # Use observed counts for both groups in a 2x2 contingency
        # Compare ratio observed/expected between two groups
        obs_i, obs_j = observed[i], observed[j]
        exp_i, exp_j = expected[i], expected[j]
        # 2x2 table: rows = actual group, cols = observed/not-observed
        # More appropriate: test if obs_i/exp_i != obs_j/exp_j
        # Construct table: [obs_i, total_i - obs_i] vs [obs_j, total_j - obs_j]
        # where total = expected (under null)
        # Use a 2x2 contingency table of observed vs expected
        table = np.array([[obs_i, exp_i], [obs_j, exp_j]])
        chi2_pw, p_pw, _, _ = chi2_contingency(table, correction=False)
        pair_labels.append(f"{display_group_code(groups[i])} vs {display_group_code(groups[j])}")
        pair_pvals.append(p_pw)

    # 3. Holm-Bonferroni correction
    n_tests = len(pair_pvals)
    sorted_idx = np.argsort(pair_pvals)
    corrected_p = np.ones(n_tests)
    for rank, idx in enumerate(sorted_idx):
        corrected_p[idx] = min(pair_pvals[idx] * (n_tests - rank), 1.0)
    # Enforce monotonicity
    for rank in range(1, n_tests):
        idx = sorted_idx[rank]
        prev_idx = sorted_idx[rank - 1]
        corrected_p[idx] = max(corrected_p[idx], corrected_p[prev_idx])

    lines.append(f"\nPairwise comparisons (Holm-Bonferroni corrected):")
    lines.append(f"  {'Comparison':<16} {'Raw p':<14} {'Corrected p':<14} {'Sig'}")
    for k in range(n_tests):
        sig = "***" if corrected_p[k] < 0.001 else ("**" if corrected_p[k] < 0.01 else ("*" if corrected_p[k] < 0.05 else "ns"))
        lines.append(f"  {pair_labels[k]:<16} {pair_pvals[k]:<14.2e} {corrected_p[k]:<14.2e} {sig}")

    txt_path = os.path.join(output_dir, "gender_group_overall.txt")
    with open(txt_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Saved {txt_path}")
    for line in lines:
        print(f"  {line}")


def plot_sjr_adjusted_bars(output_dir, label="group"):
    """Bar plot of SJR-adjusted % over/undercitation by cited gender group."""
    csv_path = os.path.join(output_dir, f"{label}_adjusted_deviations.csv")
    if not os.path.exists(csv_path):
        print("  Skipping SJR-adjusted bar plot: CSV not found")
        return

    df = pd.read_csv(csv_path)
    if df.empty:
        print("  Skipping SJR-adjusted bar plot: no data")
        return

    fig, ax = plt.subplots(figsize=(GROUP_FIG_WIDTH, GROUP_FIG_HEIGHT))

    cited_groups = df["cited_group"].values
    deviations = df["deviation_pct"].values
    errors = df["se_pct"].values
    counts = df["n_links"].values

    colors = [GROUP_COLORS[g] for g in cited_groups]
    x_pos = np.arange(len(cited_groups))

    ax.bar(x_pos, deviations, color=colors, edgecolor="black",
           linewidth=GROUP_BAR_EDGE_WIDTH,
           yerr=errors, capsize=5, ecolor="black")
    ax.axhline(0, color="gray", linestyle="--", linewidth=GROUP_LINE_WIDTH)

    ax.set_xticks(x_pos)
    ax.set_xticklabels([display_group_code(g) for g in cited_groups])
    ax.set_xlabel("First and Last Author Genders")
    ax.set_ylabel("% Deviation from SJR-Adjusted Mean")
    ax.set_title("Over/Undercitation by Cited Gender Group\n(Adjusted for SJR)")
    style_group_axes(ax)

    # n= labels on bars
    for i, (x, dev, err, n) in enumerate(zip(x_pos, deviations, errors, counts)):
        y_anchor = dev + err if dev >= 0 else dev - err
        y_offset = 3 if dev >= 0 else -3
        va = "bottom" if dev >= 0 else "top"
        ax.annotate(
            f"n={n}",
            (x, y_anchor),
            textcoords="offset points",
            xytext=(0, y_offset),
            ha="center",
            va=va,
            fontsize=POSTER_THEME["tick_fontsize"],
        )

    n_total = int(df["n_links"].sum())
    ax.text(
        0.98, 0.98, f"n = {n_total} total citations",
        transform=ax.transAxes, fontsize=POSTER_THEME["tick_fontsize"],
        verticalalignment="top", horizontalalignment="right",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.9),
    )

    save_figure(fig, output_dir, "gender_group_sjr_adjusted")


def plot_direct_adjusted_bars(output_dir, label="group"):
    """Bar plot of direct-standardized % over/undercitation by cited gender group."""
    csv_path = os.path.join(output_dir, f"{label}_direct_adjusted_deviations.csv")
    if not os.path.exists(csv_path):
        print("  Skipping direct-standardized bar plot: CSV not found")
        return

    df = pd.read_csv(csv_path)
    if df.empty:
        print("  Skipping direct-standardized bar plot: no data")
        return

    fig, ax = plt.subplots(figsize=(GROUP_FIG_WIDTH, GROUP_FIG_HEIGHT))

    cited_groups = df["cited_group"].values
    deviations = df["deviation_pct"].values
    errors = df["se_pct"].values
    counts = df["n_links"].values

    colors = [GROUP_COLORS[g] for g in cited_groups]
    x_pos = np.arange(len(cited_groups))

    ax.bar(x_pos, deviations, color=colors, edgecolor="black",
           linewidth=GROUP_BAR_EDGE_WIDTH,
           yerr=errors, capsize=5, ecolor="black")
    ax.axhline(0, color="gray", linestyle="--", linewidth=GROUP_LINE_WIDTH)

    ax.set_xticks(x_pos)
    ax.set_xticklabels([display_group_code(g) for g in cited_groups])
    ax.set_xlabel("First and Last Author Genders")
    ax.set_ylabel("% Deviation from Direct-Standardized Mean")
    ax.set_title("Over/Undercitation by Cited Gender Group\n(Direct Standardized: Proportion + SJR)")
    style_group_axes(ax)

    for i, (x, dev, err, n) in enumerate(zip(x_pos, deviations, errors, counts)):
        y_anchor = dev + err if dev >= 0 else dev - err
        y_offset = 3 if dev >= 0 else -3
        va = "bottom" if dev >= 0 else "top"
        ax.annotate(
            f"n={n}",
            (x, y_anchor),
            textcoords="offset points",
            xytext=(0, y_offset),
            ha="center",
            va=va,
            fontsize=POSTER_THEME["tick_fontsize"],
        )

    n_total = int(df["n_links"].sum())
    ax.text(
        0.98, 0.98, f"n = {n_total} total citations",
        transform=ax.transAxes, fontsize=POSTER_THEME["tick_fontsize"],
        verticalalignment="top", horizontalalignment="right",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.9),
    )

    save_figure(fig, output_dir, "gender_group_direct_standardized")


def run_r_group_stats(merged_df, data_known_df, label, output_dir):
    """Write group data to temp CSV, call R script for group-level stats."""
    r_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gender_group_stats.R")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        tmp_csv = f.name
        merged_df[["citing_doi", "citing_group", "cited_group", "SJR_scimago"]].to_csv(f, index=False)

    # Paper-level CSV for Sections 4 & 5
    # Count citation links per cited paper from our dataset (merged_df)
    link_counts = merged_df.groupby("doi_key").size().reset_index(name="n_links")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        paper_csv = f.name
        paper_data = data_known_df[["doi_key", "cited_group", "SJR_scimago"]].copy()
        paper_data["citation_count"] = data_known_df["citationcount_openalex"]
        paper_data = paper_data.merge(link_counts, on="doi_key", how="left")
        paper_data["n_links"] = paper_data["n_links"].fillna(0).astype(int)
        paper_data.drop(columns=["doi_key"]).to_csv(f, index=False)

    try:
        result = subprocess.run(
            ["Rscript", r_script, tmp_csv, output_dir, label, paper_csv],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  R group stats failed (exit {result.returncode}):")
            if result.stderr:
                print(result.stderr)
            return None
        if result.stdout:
            print(f"  {result.stdout.strip()}")
    finally:
        os.unlink(tmp_csv)
        os.unlink(paper_csv)

    return {
        "chisq": os.path.join(output_dir, f"{label}_chisq.csv"),
        "residuals": os.path.join(output_dir, f"{label}_residuals.csv"),
        "anova": os.path.join(output_dir, f"{label}_anova.csv"),
        "anova_tukey": os.path.join(output_dir, f"{label}_anova_tukey.csv"),
        "sjr_models": os.path.join(output_dir, f"{label}_sjr_models.csv"),
        "paper_models": os.path.join(output_dir, f"{label}_paper_models.csv"),
        "adjusted_deviations": os.path.join(output_dir, f"{label}_adjusted_deviations.csv"),
        "direct_adjusted_deviations": os.path.join(output_dir, f"{label}_direct_adjusted_deviations.csv"),
    }


def print_group_stats_summary(paths):
    """Read R output CSVs and print formatted summary to stdout."""
    # Chi-square test
    chisq = pd.read_csv(paths["chisq"])
    row = chisq.iloc[0]
    p_str = f"{row['p_value']:.2e}" if row["p_value"] < 0.001 else f"{row['p_value']:.4f}"
    print(f"\n  Chi-square test of independence:")
    print(f"    X² = {row['chi_sq']:.2f}, df = {int(row['df'])}, "
          f"p = {p_str}, Cramér's V = {row['cramers_v']:.4f}, n = {int(row['n_total'])}")

    # Standardised residuals
    resid = pd.read_csv(paths["residuals"])
    print(f"\n  Standardised Pearson residuals (|z| > 2 flagged):")
    for _, r in resid.iterrows():
        flag = " ***" if abs(r["std_residual"]) > 2 else ""
        print(f"    {r['citing_group']} → {r['cited_group']}: "
              f"z = {r['std_residual']:+.2f} "
              f"(obs={int(r['observed'])}, exp={r['expected']:.1f}){flag}")

    # ANOVA: citing group → cited group proportions
    if "anova" in paths and os.path.exists(paths["anova"]):
        anova = pd.read_csv(paths["anova"])
        if len(anova) > 0:
            print(f"\n  One-way ANOVA (prop cited TARGET ~ citing_group):")
            print(f"    {'Target':<8} {'F':<10} {'df1':<6} {'df2':<8} {'p':<14} {'eta²':<10}")
            for _, r in anova.iterrows():
                p_str = f"{r['p_value']:.2e}" if r["p_value"] < 0.001 else f"{r['p_value']:.4f}"
                print(f"    {r['cited_target']:<8} {r['F']:<10.2f} {int(r['df1']):<6} "
                      f"{int(r['df2']):<8} {p_str:<14} {r['eta_sq']:.4f}")

    if "anova_tukey" in paths and os.path.exists(paths["anova_tukey"]):
        tukey = pd.read_csv(paths["anova_tukey"])
        sig_tukey = tukey[tukey["p_adj"] < 0.05]
        if len(sig_tukey) > 0:
            print(f"\n  Significant Tukey HSD pairs (p < 0.05):")
            for _, r in sig_tukey.iterrows():
                print(f"    {r['cited_target']}: {r['comparison']}: "
                      f"diff = {r['diff']:+.4f}, p = {r['p_adj']:.4f}")

    # SJR models
    sjr = pd.read_csv(paths["sjr_models"])
    if len(sjr) > 0:
        n_sjr = int(sjr["n"].iloc[0])
        print(f"\n  SJR-adjusted logistic regressions (n = {n_sjr} with SJR data):")
        print(f"    {'Cited':<8} {'p(citing|base)':<18} {'p(citing|adj)':<18} {'p(SJR improves)':<18}")
        for _, r in sjr.iterrows():
            def fmt_p(p):
                return f"{p:.2e}" if p < 0.001 else f"{p:.4f}"
            print(f"    {r['cited_group']:<8} {fmt_p(r['p_citing_base']):<18} "
                  f"{fmt_p(r['p_citing_adj']):<18} {fmt_p(r['p_sjr']):<18}")
    else:
        print("\n  SJR models: skipped (no SJR data available)")

    # Paper-level models
    if "paper_models" in paths and os.path.exists(paths["paper_models"]):
        paper = pd.read_csv(paths["paper_models"])
        if len(paper) > 0 and "coef_base" in paper.columns:
            row0 = paper.iloc[0]
            n_papers = int(row0["n"]) if pd.notna(row0["n"]) else 0
            print(f"\n  Paper-level citation models (log(citations+1) ~ cited_group + SJR, n = {n_papers}):")

            def fmt_p(p):
                if pd.isna(p):
                    return "ref"
                return f"{p:.2e}" if p < 0.001 else f"{p:.4f}"

            # Overall F-test results
            print(f"    F-test cited_group alone:      p = {fmt_p(row0['f_group_only_p'])}")
            print(f"    F-test cited_group after SJR:   p = {fmt_p(row0['f_group_adj_p'])}")
            print(f"    F-test SJR after cited_group:   p = {fmt_p(row0['f_sjr_adj_p'])}")
            print(f"    R² group-only: {row0['r2_group']:.4f}, "
                  f"SJR-only: {row0['r2_sjr']:.4f}, "
                  f"both: {row0['r2_both']:.4f}")

            # Per-group coefficients
            print(f"\n    {'Group':<8} {'coef(base)':<14} {'p(base)':<14} "
                  f"{'coef(+SJR)':<14} {'p(+SJR)':<14}")
            for _, r in paper.iterrows():
                coef_b = f"{r['coef_base']:+.3f}" if r['coef_base'] != 0 else "ref"
                coef_a = f"{r['coef_sjr_adjusted']:+.3f}" if r['coef_sjr_adjusted'] != 0 else "ref"
                print(f"    {r['cited_group']:<8} {coef_b:<14} {fmt_p(r['p_base']):<14} "
                      f"{coef_a:<14} {fmt_p(r['p_sjr_adjusted']):<14}")

    # SJR-adjusted deviations (citation links with SJR-weighted baseline)
    if "adjusted_deviations" in paths and os.path.exists(paths["adjusted_deviations"]):
        adj = pd.read_csv(paths["adjusted_deviations"])
        if len(adj) > 0 and "deviation_pct" in adj.columns:
            n_total = int(adj["n_links"].sum())
            print(f"\n  SJR-adjusted over/undercitation (n = {n_total} total citations):")
            print(f"    {'Group':<8} {'Obs %':<10} {'Adj Exp %':<12} {'Deviation':<12} {'SE':<10} {'Links':<8} {'Papers':<8}")
            for _, r in adj.iterrows():
                print(f"    {r['cited_group']:<8} {r['obs_prop']*100:.1f}%{'':<4} "
                      f"{r['adj_baseline']*100:.1f}%{'':<6} "
                      f"{r['deviation_pct']:+.1f}%{'':<6} "
                      f"{r['se_pct']:.1f}%{'':<4} "
                      f"{int(r['n_links']):<8} {int(r['n_papers'])}")

    # Direct-standardized deviations (group proportion + SJR)
    if "direct_adjusted_deviations" in paths and os.path.exists(paths["direct_adjusted_deviations"]):
        dadj = pd.read_csv(paths["direct_adjusted_deviations"])
        if len(dadj) > 0 and "deviation_pct" in dadj.columns:
            n_total = int(dadj["n_links"].sum())
            print(f"\n  Direct-standardized over/undercitation (n = {n_total} total citations):")
            print(f"    {'Group':<8} {'Obs %':<10} {'Adj Exp %':<12} {'Deviation':<12} {'SE':<10} {'Links':<8} {'Papers':<8}")
            for _, r in dadj.iterrows():
                print(f"    {r['cited_group']:<8} {r['obs_prop']*100:.1f}%{'':<4} "
                      f"{r['adj_baseline']*100:.1f}%{'':<6} "
                      f"{r['deviation_pct']:+.1f}%{'':<6} "
                      f"{r['se_pct']:.1f}%{'':<4} "
                      f"{int(r['n_links']):<8} {int(r['n_papers'])}")


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
            plot_overall_cited_group_bars(merged_groups, data_known, output_dir)
            overall_cited_group_stats(merged_groups, data_known, output_dir)

        # Group-level statistical tests
        group_stats_paths = run_r_group_stats(merged_groups, data_known, "group", output_dir)
        if group_stats_paths is not None:
            print_group_stats_summary(group_stats_paths)
            plot_sjr_adjusted_bars(output_dir, label="group")
            plot_direct_adjusted_bars(output_dir, label="group")


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
