import os
import sys
import argparse
import subprocess
import tempfile

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

CITED_BY_PATH = "data/cited_by_info_gender.xlsx"
DATA_PATH = "data/data.xlsx"
OUTPUT_DIR = "data/plots"

# Constants
N_BINS = 10
N_BOOTSTRAP = 2000
HEATMAP_GRID = 20
MALE_COLOR = "#4393c3"    # blue
FEMALE_COLOR = "#d6604d"  # red/pink


def load_data(cited_by_path, data_path):
    """Read both Excel files and return as DataFrames."""
    cited_by_df = pd.read_excel(cited_by_path, engine="openpyxl")
    data_df = pd.read_excel(data_path, engine="openpyxl")
    return cited_by_df, data_df


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
        "heatmap": os.path.join(output_dir, f"{label}_heatmap.csv"),
    }


def read_r_results(paths):
    """Read the 3 R output CSVs into DataFrames."""
    return {
        "binned": pd.read_csv(paths["binned"]),
        "regression": pd.read_csv(paths["regression"]),
        "heatmap": pd.read_csv(paths["heatmap"]),
    }


def save_figure(fig, output_dir, filename):
    """Save figure as PNG (300dpi) and SVG, then close."""
    fig.savefig(os.path.join(output_dir, f"{filename}.png"), dpi=300, bbox_inches="tight")
    fig.savefig(os.path.join(output_dir, f"{filename}.svg"), bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {filename}.png and {filename}.svg")


def plot_binned_expectation(binned_df, p_bar, title, output_dir, filename):
    """Error bar plot of binned E[p_cited] - baseline with bootstrap CIs."""
    fig, ax = plt.subplots(figsize=(8, 5))

    colors = [MALE_COLOR if d > 0 else FEMALE_COLOR for d in binned_df["delta"]]
    ci_lower = binned_df["delta"] - binned_df["ci_lower"]
    ci_upper = binned_df["ci_upper"] - binned_df["delta"]

    ax.errorbar(
        binned_df["bin_center"], binned_df["delta"],
        yerr=[ci_lower, ci_upper],
        fmt="o", markersize=6, capsize=4,
        color="black", ecolor="gray",
    )
    # Color the markers
    for i, (xc, yc, c) in enumerate(zip(binned_df["bin_center"], binned_df["delta"], colors)):
        ax.plot(xc, yc, "o", color=c, markersize=6, zorder=5)

    ax.axhline(0, color="gray", linestyle="--", linewidth=1, label="gender-neutral baseline")
    ax.set_xlabel("P(male) of citing author")
    ax.set_ylabel("E[P(male) of cited author] \u2212 baseline")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=9)
    ax.annotate(
        f"baseline P(male) = {p_bar:.3f}",
        xy=(0.98, 0.02), xycoords="axes fraction",
        ha="right", va="bottom", fontsize=9,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
    )

    save_figure(fig, output_dir, filename)


def plot_regression_trend(reg_df, title, output_dir, filename):
    """Linear + quadratic regression with confidence band and stats annotation."""
    fig, ax = plt.subplots(figsize=(8, 5))

    # Confidence band for linear fit
    ax.fill_between(
        reg_df["x_grid"], reg_df["linear_lower"], reg_df["linear_upper"],
        alpha=0.2, color="red", label="95% CI (linear)",
    )
    # Linear fit
    ax.plot(reg_df["x_grid"], reg_df["linear_fit"], color="red", linewidth=2, label="Linear fit")
    # Quadratic fit
    ax.plot(reg_df["x_grid"], reg_df["quad_fit"], color="purple", linewidth=1.5,
            linestyle="--", label="Quadratic fit")

    # Baseline
    p_bar = reg_df["p_bar"].iloc[0]
    ax.axhline(p_bar, color="gray", linestyle="--", linewidth=1, alpha=0.7, label=f"Baseline ({p_bar:.3f})")

    ax.set_xlabel("P(male) of citing author")
    ax.set_ylabel("P(male) of cited author")
    ax.set_title(title)
    ax.legend(loc="upper left", fontsize=8)

    # Stats text box
    slope = reg_df["slope"].iloc[0]
    slope_ci_l = reg_df["slope_ci_lower"].iloc[0]
    slope_ci_u = reg_df["slope_ci_upper"].iloc[0]
    pval = reg_df["slope_pvalue"].iloc[0]
    r2 = reg_df["r_squared"].iloc[0]

    pval_str = f"{pval:.2e}" if pval < 0.001 else f"{pval:.4f}"
    stats_text = (
        f"\u03b2\u2081 = {slope:.4f}\n"
        f"95% CI [{slope_ci_l:.4f}, {slope_ci_u:.4f}]\n"
        f"p = {pval_str}\n"
        f"R\u00b2 = {r2:.4f}"
    )
    ax.text(
        0.98, 0.98, stats_text,
        transform=ax.transAxes, fontsize=9,
        verticalalignment="top", horizontalalignment="right",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.9),
    )

    save_figure(fig, output_dir, filename)


def plot_heatmap(heatmap_df, title, output_dir, filename):
    """2D heatmap of log2(observed/expected) with diverging colormap."""
    fig, ax = plt.subplots(figsize=(7, 6))

    # Pivot to 2D grid
    x_vals = sorted(heatmap_df["x_mid"].unique())
    y_vals = sorted(heatmap_df["y_mid"].unique())
    nx, ny = len(x_vals), len(y_vals)

    grid = np.full((ny, nx), np.nan)
    x_idx = {v: i for i, v in enumerate(x_vals)}
    y_idx = {v: i for i, v in enumerate(y_vals)}

    for _, row in heatmap_df.iterrows():
        xi = x_idx[row["x_mid"]]
        yi = y_idx[row["y_mid"]]
        grid[yi, xi] = row["log2_ratio"]

    # Symmetric color limits
    valid_vals = grid[~np.isnan(grid)]
    if len(valid_vals) > 0:
        vmax = max(abs(valid_vals.min()), abs(valid_vals.max()))
    else:
        vmax = 1.0
    vmin = -vmax

    # Set NaN (empty cells) to gray via set_bad
    cmap = plt.cm.RdBu_r.copy()
    cmap.set_bad(color="0.85")

    # Compute cell edges from midpoints
    dx = x_vals[1] - x_vals[0] if nx > 1 else 0.05
    dy = y_vals[1] - y_vals[0] if ny > 1 else 0.05
    x_edges = [v - dx / 2 for v in x_vals] + [x_vals[-1] + dx / 2]
    y_edges = [v - dy / 2 for v in y_vals] + [y_vals[-1] + dy / 2]

    mesh = ax.pcolormesh(
        x_edges, y_edges, grid,
        cmap=cmap, vmin=vmin, vmax=vmax,
    )
    cbar = fig.colorbar(mesh, ax=ax, label="log\u2082(observed / expected)")

    ax.set_xlabel("P(male) of citing author")
    ax.set_ylabel("P(male) of cited author")
    ax.set_title(title)

    save_figure(fig, output_dir, filename)


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

        p_bar = results["regression"]["p_bar"].iloc[0]
        slope = results["regression"]["slope"].iloc[0]
        r2 = results["regression"]["r_squared"].iloc[0]
        pval = results["regression"]["slope_pvalue"].iloc[0]
        print(f"  Stats: p_bar={p_bar:.4f}, slope={slope:.4f}, R²={r2:.4f}, p={pval:.2e}")

        title_suffix = f"Citing {citing_role.title()} Author vs Cited {cited_role.title()} Author"

        plot_binned_expectation(
            results["binned"], p_bar,
            f"Binned Gender Expectation: {title_suffix}",
            output_dir, f"gender_binned_{citing_role}_vs_{cited_role}",
        )
        plot_regression_trend(
            results["regression"],
            f"Regression Trend: {title_suffix}",
            output_dir, f"gender_regression_{citing_role}_vs_{cited_role}",
        )
        plot_heatmap(
            results["heatmap"],
            f"Gender Citation Heatmap: {title_suffix}",
            output_dir, f"gender_heatmap_{citing_role}_vs_{cited_role}",
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate gender citation analysis plots (binned, regression, heatmap)"
    )
    parser.add_argument("--cited-by", default=CITED_BY_PATH, help="Path to cited_by_info_gender.xlsx")
    parser.add_argument("--data", default=DATA_PATH, help="Path to data.xlsx")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="Output directory for plots")
    args = parser.parse_args()

    print("Loading data...")
    cited_by_df, data_df = load_data(args.cited_by, args.data)
    print(f"  cited_by: {len(cited_by_df)} rows, data: {len(data_df)} rows")

    analyze_and_plot(cited_by_df, data_df, args.output_dir)
    print("\nDone.")
