import os
import argparse

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

CITED_BY_PATH = "data/cited_by_info_gender.xlsx"
DATA_PATH = "data/data.xlsx"
OUTPUT_DIR = "data/plots"


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


def plot_scatter_with_regression(x, y, title, xlabel, ylabel, output_dir, filename):
    """Create a scatter plot with linear regression line and R^2 value."""
    fig, ax = plt.subplots(figsize=(8, 6))

    ax.scatter(x, y, alpha=0.3, s=10)

    # Linear regression
    coeffs = np.polyfit(x, y, 1)
    poly = np.poly1d(coeffs)
    x_line = np.linspace(x.min(), x.max(), 100)
    ax.plot(x_line, poly(x_line), color="red", linewidth=2)

    # R^2
    y_pred = poly(x)
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot != 0 else 0

    ax.text(
        0.05, 0.95, f"$R^2 = {r_squared:.4f}$",
        transform=ax.transAxes, fontsize=12,
        verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.8),
    )

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)

    fig.savefig(os.path.join(output_dir, f"{filename}.png"), dpi=300, bbox_inches="tight")
    fig.savefig(os.path.join(output_dir, f"{filename}.svg"), bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {filename}.png and {filename}.svg")


def create_all_plots(cited_by_df, data_df, output_dir):
    """Generate all 4 scatter plots."""
    os.makedirs(output_dir, exist_ok=True)

    plots = [
        {
            "author_filter_col": "first_author",
            "y_col": "first_prob_male",
            "title": "Citing First Author vs Cited First Author",
            "xlabel": "Citing First Author prob_male",
            "ylabel": "Cited First Author prob_male",
            "filename": "citing_first_vs_cited_first",
        },
        {
            "author_filter_col": "last_author",
            "y_col": "first_prob_male",
            "title": "Citing Last Author vs Cited First Author",
            "xlabel": "Citing Last Author prob_male",
            "ylabel": "Cited First Author prob_male",
            "filename": "citing_last_vs_cited_first",
        },
        {
            "author_filter_col": "first_author",
            "y_col": "last_prob_male",
            "title": "Citing First Author vs Cited Last Author",
            "xlabel": "Citing First Author prob_male",
            "ylabel": "Cited Last Author prob_male",
            "filename": "citing_first_vs_cited_last",
        },
        {
            "author_filter_col": "last_author",
            "y_col": "last_prob_male",
            "title": "Citing Last Author vs Cited Last Author",
            "xlabel": "Citing Last Author prob_male",
            "ylabel": "Cited Last Author prob_male",
            "filename": "citing_last_vs_cited_last",
        },
    ]

    for p in plots:
        print(f"\nGenerating: {p['filename']}")
        x, y = prepare_scatter_data(
            cited_by_df, data_df, p["author_filter_col"], p["y_col"]
        )
        if len(x) < 2:
            print(f"  Skipping {p['filename']}: not enough data points ({len(x)})")
            continue
        plot_scatter_with_regression(
            x, y, p["title"], p["xlabel"], p["ylabel"], output_dir, p["filename"]
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate gender probability scatter plots"
    )
    parser.add_argument("--cited-by", default=CITED_BY_PATH, help="Path to cited_by_info_gender.xlsx")
    parser.add_argument("--data", default=DATA_PATH, help="Path to data.xlsx")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="Output directory for plots")
    args = parser.parse_args()

    print("Loading data...")
    cited_by_df, data_df = load_data(args.cited_by, args.data)
    print(f"  cited_by: {len(cited_by_df)} rows, data: {len(data_df)} rows")

    create_all_plots(cited_by_df, data_df, args.output_dir)
    print("\nDone.")
