import os
import sys
import argparse
import subprocess
import tempfile

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from scipy.stats import chi2_contingency
import pycountry

CITED_BY_PATH = "data/cited_by_info_gender.xlsx"
DATA_PATH = "data/data.xlsx"
OUTPUT_DIR = "data/plots"
MIN_PAPERS = 10

# Figure dimensions (mm → inches)
FIG_WIDTH_MM = 235
FIG_HEIGHT_MM = 125
FIG_WIDTH = FIG_WIDTH_MM / 25.4
FIG_HEIGHT = FIG_HEIGHT_MM / 25.4
BAR_EDGE_WIDTH = 2.0
LINE_WIDTH = 3.0

POSTER_THEME = {
    "tick_fontsize": 12,
    "label_fontsize": 16,
    "font_family": "Arial",
    "spine_linewidth": 2.0,
    "grid": False,
}

# ── Core / Periphery classification ──────────────────────────────────────────
# Manually curated lists of core (high-income, high-output science nations) and
# periphery countries, encoded as ISO 3166-1 alpha-2 codes.

CORE_ISO2 = {
    "AU", "AT", "BE", "CA", "CN", "DK", "FI", "FR", "DE", "GR", "GL", "IS", "IE",
    "IL", "IT", "JP", "LI", "LU", "MC", "NL", "NZ", "NO", "PT", "SG", "KR", "ES",
    "SE", "CH", "TW", "GB", "US",
}

PERIPHERY_ISO2 = {
    "AF", "AX", "AL", "DZ", "AG", "AR", "AM", "AW", "AZ", "BS", "BH", "BD", "BY",
    "BZ", "BJ", "BM", "BT", "BO", "BA", "BW", "BR", "VG", "BN", "BG", "BF", "BI",
    "KH", "CM", "CV", "KY", "TD", "CL", "CO", "CR", "HR", "CU", "CW", "CY", "CZ",
    "CD", "DM", "DO", "EC", "EG", "SV", "ER", "EE", "ET", "FJ", "PF", "GA", "GM",
    "GE", "GH", "GI", "GD", "GP", "GT", "GN", "GW", "GY", "HU", "IN", "ID", "IR",
    "IQ", "CI", "JM", "JO", "KZ", "KE", "XK", "KW", "KG", "LA", "LV", "LB", "LS",
    "LR", "LY", "LT", "MO", "MK", "MG", "MW", "MY", "MV", "ML", "MT", "MR", "MU",
    "MX", "MD", "MN", "ME", "MS", "MA", "MZ", "MM", "NA", "NP", "NC", "NI", "NE",
    "NG", "KP", "OM", "PK", "PS", "PA", "PG", "PY", "PE", "PH", "PL", "QA", "CG",
    "RE", "RO", "RU", "KN", "LC", "VC", "WS", "SA", "SN", "RS", "SL", "SX", "SK",
    "SI", "SO", "ZA", "SS", "LK", "SD", "SR", "SZ", "SY", "TJ", "TZ", "TH", "TG",
    "TT", "TN", "TR", "TM", "UG", "UA", "AE", "UY", "UZ", "VE", "VN", "YE", "ZM",
    "ZW",
}

_CP_COLORS = {"core": "#d6604d", "periphery": "#4393c3", "unknown": "#aaaaaa"}


def get_core_periphery(iso2: str) -> str:
    """Classify a country ISO2 code as 'core', 'periphery', or 'unknown'."""
    if iso2 in CORE_ISO2:
        return "core"
    if iso2 in PERIPHERY_ISO2:
        return "periphery"
    return "unknown"


def style_group_axes(ax):
    """Apply consistent poster-theme styling to axes."""
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
    ax.margins(y=0.15)


def load_data(cited_by_path, data_path):
    """Read both Excel files and return as DataFrames."""
    cited_by_df = pd.read_excel(cited_by_path, engine="openpyxl")
    data_df = pd.read_excel(data_path, engine="openpyxl")
    return cited_by_df, data_df


def load_population_data(path="data/UN_POPULATIONS_ADJUSTED_SHEET.xlsx"):
    """Load UN population estimates. Returns dict: (ISO2, year_int) -> population_total."""
    df = pd.read_excel(path, sheet_name="Estimates", engine="openpyxl",
                       usecols=["ISO2", "Year", "Total"])
    df = df.dropna(subset=["ISO2", "Year", "Total"])
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["Year"])
    return {(row["ISO2"], int(row["Year"])): row["Total"] for _, row in df.iterrows()}


def get_population(country_code, year, pop_lookup):
    """Return population total for (country_code, year). Returns NaN if not found."""
    if pd.isna(year) or pd.isna(country_code):
        return np.nan
    return pop_lookup.get((country_code, int(year)), np.nan)


def save_figure(fig, output_dir, filename):
    """Save figure as PNG (300dpi) and SVG, then close."""
    fig.savefig(os.path.join(output_dir, f"{filename}.png"), dpi=300, bbox_inches="tight")
    fig.savefig(os.path.join(output_dir, f"{filename}.svg"), bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {filename}.png and {filename}.svg")


def iso2_to_country_name(code):
    """Convert an ISO 3166-1 alpha-2 code to a full country name. Returns the code if not found."""
    try:
        return pycountry.countries.get(alpha_2=code).name
    except AttributeError:
        return code


def _normalize_name(name):
    """Normalize an author name to a comparable form (lowercase, sorted parts)."""
    name = str(name).strip().lower()
    parts = [p.strip() for p in name.replace(",", " ").split() if p.strip()]
    return frozenset(parts)


def remove_self_citations(cited_by_df, data_df):
    """Remove rows where a first/last author of the citing paper matches one on the cited paper."""
    before = len(cited_by_df)

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

    cited_authors = {}
    for _, row in data_df.iterrows():
        doi = str(row["DOI"]).strip().lower()
        fl = str(row.get("firstlastauthor_openalex", ""))
        if pd.isna(fl) or fl == "nan":
            continue
        names = {_normalize_name(n) for n in fl.split(";") if n.strip()}
        cited_authors[doi] = names

    link = cited_by_df[["citing_doi", "cited_doi"]].drop_duplicates()
    self_cite_pairs = set()
    for _, row in link.iterrows():
        citing_doi = row["citing_doi"]
        cited_doi = str(row["cited_doi"]).strip().lower()
        citing_names = citing_authors.get(citing_doi, set())
        cited_names = cited_authors.get(cited_doi, set())
        if citing_names & cited_names:
            self_cite_pairs.add((citing_doi, row["cited_doi"]))

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


# ── Plot 1: Country Affiliation Summary ──────────────────────────────────────

def parse_cited_countries(data_df):
    """Parse authorcountries_openalex into list column + n_countries category."""
    df = data_df.copy()
    df["country_list"] = df["authorcountries_openalex"].apply(
        lambda x: [c.strip() for c in str(x).split(",") if c.strip() and c.strip() != "nan"]
        if pd.notna(x) else []
    )
    df["n_countries"] = df["country_list"].apply(len)
    return df


def prepare_country_affiliation_data(data_df, min_papers):
    """Build per-country rows with stacked counts by author composition (Domestic/International)."""
    df = parse_cited_countries(data_df)
    # Exclude papers with no country info
    df = df[df["n_countries"] > 0].copy()

    df["n_cat"] = df["n_countries"].apply(lambda n: "Domestic only" if n == 1 else "International")

    # Explode: each paper counted once per country
    rows = []
    for _, row in df.iterrows():
        for country in row["country_list"]:
            rows.append({"country": country, "n_cat": row["n_cat"]})
    exploded = pd.DataFrame(rows)

    # Filter by min_papers
    country_counts = exploded["country"].value_counts()
    valid_countries = country_counts[country_counts >= min_papers].index
    exploded = exploded[exploded["country"].isin(valid_countries)]

    # Pivot to get stacked counts
    pivot = exploded.groupby(["country", "n_cat"]).size().unstack(fill_value=0)
    for col in ["Domestic only", "International"]:
        if col not in pivot.columns:
            pivot[col] = 0
    pivot = pivot[["Domestic only", "International"]]
    pivot["total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("total", ascending=False).reset_index()

    return pivot


def plot_country_affiliation(affil_df, output_dir):
    """Stacked bar chart: papers per country, stacked by author composition."""
    fig, ax = plt.subplots(figsize=(max(FIG_WIDTH, len(affil_df) * 0.5), FIG_HEIGHT))

    x = np.arange(len(affil_df))
    colors = {"Domestic only": "#2a9d8f", "International": "#4393c3"}

    bottom = np.zeros(len(affil_df))
    for cat, color in colors.items():
        vals = affil_df[cat].values.astype(float)
        ax.bar(x, vals, bottom=bottom, color=color, edgecolor="black",
               linewidth=0.5, label=cat)
        bottom += vals

    ax.set_xticks(x)
    ax.set_xticklabels([iso2_to_country_name(c) for c in affil_df["country"].values],
                       rotation=45, ha="right", fontsize=POSTER_THEME["tick_fontsize"])
    ax.set_ylabel("Number of Papers")
    ax.set_title("Papers per Country by Author Composition")
    ax.legend(title="Author composition")
    style_group_axes(ax)

    save_figure(fig, output_dir, "country_affiliation")


def prepare_country_affiliation_per_capita(data_df, min_papers, pop_lookup):
    """Build per-country weighted sums (1/population) stacked by n_countries.

    Each paper-country pair is weighted by 1/pop(country, year). Values are
    scaled by 1e6 so the y-axis reads as 'papers per million people'.
    Only countries that pass the raw min_papers threshold are included.
    """
    df = parse_cited_countries(data_df)
    df = df[df["n_countries"] > 0].copy()
    df["Publication_Year"] = pd.to_numeric(df.get("Publication_Year"), errors="coerce")
    df["n_cat"] = df["n_countries"].apply(lambda n: "Domestic only" if n == 1 else "International")

    # Determine which countries pass the raw min_papers threshold
    raw_rows = []
    for _, row in df.iterrows():
        for country in row["country_list"]:
            raw_rows.append(country)
    country_counts = pd.Series(raw_rows).value_counts()
    valid_countries = set(country_counts[country_counts >= min_papers].index)

    # Build weighted rows
    rows = []
    skipped = 0
    for _, row in df.iterrows():
        year = row["Publication_Year"]
        for country in row["country_list"]:
            if country not in valid_countries:
                continue
            pop = get_population(country, year, pop_lookup)
            if np.isnan(pop) or pop <= 0:
                skipped += 1
                continue
            rows.append({"country": country, "n_cat": row["n_cat"], "weight": 1e6 / pop})

    if skipped:
        print(f"  Per-capita affiliation: {skipped} paper-country rows skipped (missing population)")

    if not rows:
        return pd.DataFrame()

    exploded = pd.DataFrame(rows)
    pivot = exploded.groupby(["country", "n_cat"])["weight"].sum().unstack(fill_value=0)
    for col in ["Domestic only", "International"]:
        if col not in pivot.columns:
            pivot[col] = 0.0
    pivot = pivot[["Domestic only", "International"]]
    pivot["total"] = pivot.sum(axis=1)
    pivot = pivot.sort_values("total", ascending=False).reset_index()
    return pivot


def plot_country_affiliation_per_capita(affil_df, output_dir):
    """Stacked bar chart: per-capita papers per country (papers per million people)."""
    if affil_df.empty:
        print("  Skipping per-capita affiliation plot: no data")
        return

    fig, ax = plt.subplots(figsize=(max(FIG_WIDTH, len(affil_df) * 0.5), FIG_HEIGHT))

    x = np.arange(len(affil_df))
    colors = {"Domestic only": "#2a9d8f", "International": "#4393c3"}

    bottom = np.zeros(len(affil_df))
    for cat, color in colors.items():
        vals = affil_df[cat].values.astype(float)
        ax.bar(x, vals, bottom=bottom, color=color, edgecolor="black",
               linewidth=0.5, label=cat)
        bottom += vals

    ax.set_xticks(x)
    ax.set_xticklabels([iso2_to_country_name(c) for c in affil_df["country"].values],
                       rotation=45, ha="right", fontsize=POSTER_THEME["tick_fontsize"])
    ax.set_ylabel("Papers per Million People")
    ax.set_title("Papers per Capita by Country by Author Composition")
    ax.legend(title="Author composition")
    style_group_axes(ax)

    save_figure(fig, output_dir, "country_affiliation_per_capita")


# ── International Collaboration → Publications Analysis ───────────────────────

def prepare_country_intl_stats(data_df, min_papers, pop_lookup):
    """Country-level stats for international collaboration vs publication rate.

    Each paper is classified as international (≥2 countries) or domestic (1 country).
    0-country papers are discarded. Returns one row per country with:
      country, total_pubs, intl_pubs, intl_rate, population,
      pubs_per_capita, log_total_pubs, log_pubs_per_capita
    """
    df = parse_cited_countries(data_df)
    df = df[df["n_countries"] > 0].copy()
    df["international"] = (df["n_countries"] >= 2).astype(int)
    df["Publication_Year"] = pd.to_numeric(df.get("Publication_Year"), errors="coerce")

    # Build one row per paper-country (each paper counted once per country it belongs to)
    rows = []
    for _, row in df.iterrows():
        for country in row["country_list"]:
            rows.append({
                "country": country,
                "international": row["international"],
                "year": row["Publication_Year"],
            })
    if not rows:
        return pd.DataFrame()
    exploded = pd.DataFrame(rows)

    # Filter by min_papers
    counts = exploded["country"].value_counts()
    valid_countries = counts[counts >= min_papers].index
    exploded = exploded[exploded["country"].isin(valid_countries)]

    results = []
    for country, grp in exploded.groupby("country"):
        total_pubs = len(grp)
        intl_pubs = int(grp["international"].sum())
        intl_rate = intl_pubs / total_pubs

        median_year = int(grp["year"].dropna().median()) if grp["year"].notna().any() else None
        pop = get_population(country, median_year, pop_lookup) if (pop_lookup and median_year) else np.nan
        pubs_per_capita = total_pubs / pop if (not np.isnan(pop) and pop > 0) else np.nan

        results.append({
            "country": country,
            "total_pubs": total_pubs,
            "intl_pubs": intl_pubs,
            "intl_rate": intl_rate,
            "population": pop,
            "pubs_per_capita": pubs_per_capita,
            "log_total_pubs": np.log(total_pubs),
            "log_pubs_per_capita": np.log(pubs_per_capita) if not np.isnan(pubs_per_capita) else np.nan,
        })

    return pd.DataFrame(results).sort_values("total_pubs", ascending=False).reset_index(drop=True)


def run_r_affiliation_stats(country_df, output_dir):
    """Write country-level CSV and call country_affiliation_stats.R."""
    r_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "country_affiliation_stats.R")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        tmp_csv = f.name
        country_df.to_csv(f, index=False)

    try:
        result = subprocess.run(
            ["Rscript", r_script, tmp_csv, output_dir],
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

    return os.path.join(output_dir, "country_affiliation_r_stats.txt")


# ── Plot 2: Country Self-Citation Analysis ────────────────────────────────────

def parse_citing_country(cited_by_df):
    """Clean author_countries column in cited_by data, drop NaN rows."""
    df = cited_by_df.copy()
    df["citing_country"] = df["author_countries"].apply(
        lambda x: str(x).strip() if pd.notna(x) and str(x).strip() != "nan" else None
    )
    before = len(df)
    df = df.dropna(subset=["citing_country"]).reset_index(drop=True)
    print(f"  Citing country: {len(df)} / {before} rows with valid country")
    return df


def filter_countries_by_threshold(data_df, min_papers):
    """Return country codes with >= min_papers papers in data.xlsx."""
    df = parse_cited_countries(data_df)
    df = df[df["n_countries"] > 0]
    # Explode countries
    all_countries = []
    for countries in df["country_list"]:
        all_countries.extend(countries)
    counts = pd.Series(all_countries).value_counts()
    valid = counts[counts >= min_papers].index.tolist()
    print(f"  Countries with >= {min_papers} papers: {len(valid)}")
    return valid


def prepare_self_citation_data(cited_by_df, data_df, top_countries):
    """Merge citing/cited data and flag self-citations (country match)."""
    # Parse cited paper countries
    data_parsed = parse_cited_countries(data_df)
    data_parsed["doi_key"] = data_parsed["DOI"].astype(str).str.strip().str.lower()

    # Parse citing author country
    cb = parse_citing_country(cited_by_df)
    cb["doi_key"] = cb["cited_doi"].astype(str).str.strip().str.lower()

    # Merge to get cited paper's country list
    merged = cb.merge(
        data_parsed[["doi_key", "country_list", "SJR_scimago"]],
        on="doi_key", how="inner"
    )

    # Filter: only rows where citing_country is in top_countries
    merged = merged[merged["citing_country"].isin(top_countries)].copy()

    # Flag self-citation: citing author's country is in cited paper's country list
    merged["is_self_cite"] = merged.apply(
        lambda r: 1 if r["citing_country"] in r["country_list"] else 0, axis=1
    )

    print(f"  Self-citation data: {len(merged)} rows, "
          f"{merged['is_self_cite'].sum()} self-cites "
          f"({merged['is_self_cite'].mean()*100:.1f}%)")
    return merged


def compute_self_citation_rates(self_cite_df):
    """Per-country self-cite rate with SE."""
    grouped = self_cite_df.groupby("citing_country").agg(
        n_total=("is_self_cite", "count"),
        n_self=("is_self_cite", "sum"),
    ).reset_index()
    grouped["self_rate"] = grouped["n_self"] / grouped["n_total"]
    grouped["se"] = np.sqrt(grouped["self_rate"] * (1 - grouped["self_rate"]) / grouped["n_total"])
    grouped = grouped.sort_values("self_rate", ascending=False).reset_index(drop=True)
    return grouped


def plot_self_citation_bars(rates_df, output_dir, suffix):
    """Bar plot of self-citation rates per country, colored by core/periphery."""
    from matplotlib.patches import Patch

    fig, ax = plt.subplots(figsize=(max(FIG_WIDTH, len(rates_df) * 0.5), FIG_HEIGHT))

    x = np.arange(len(rates_df))
    colors = [_CP_COLORS[get_core_periphery(c)] for c in rates_df["citing_country"]]

    ax.bar(x, rates_df["self_rate"].values * 100, color=colors,
           edgecolor="black", linewidth=0.5,
           yerr=rates_df["se"].values * 100, capsize=3, ecolor="black")

    overall_rate = rates_df["n_self"].sum() / rates_df["n_total"].sum() * 100
    median_rate = rates_df["self_rate"].median() * 100
    h_overall = ax.axhline(overall_rate, color="gray", linestyle="--", linewidth=LINE_WIDTH,
                           label=f"Overall rate: {overall_rate:.1f}%")
    h_median = ax.axhline(median_rate, color="#e08020", linestyle=":", linewidth=LINE_WIDTH,
                          label=f"Median country rate: {median_rate:.1f}%")

    ax.set_xticks(x)
    ax.set_xticklabels([iso2_to_country_name(c) for c in rates_df["citing_country"].values],
                       rotation=45, ha="right", fontsize=POSTER_THEME["tick_fontsize"])
    ax.set_ylabel("Self-Citation Rate (%)")
    label_text = "with author self-cites" if "with_self" in suffix else "author self-cites removed"
    ax.set_title(f"Country Self-Citation Rate ({label_text})")

    cp_handles = [Patch(facecolor=_CP_COLORS[g], edgecolor="black", label=g.capitalize())
                  for g in ("core", "periphery", "unknown")]
    ax.legend(handles=[h_overall, h_median] + cp_handles, loc="upper right", fontsize=8)
    style_group_axes(ax)

    # n= labels above bars
    for i, (xi, rate, se, n) in enumerate(zip(
            x, rates_df["self_rate"], rates_df["se"], rates_df["n_total"])):
        ax.annotate(f"n={n}", (xi, (rate + se) * 100),
                    textcoords="offset points", xytext=(0, 3),
                    ha="center", va="bottom", fontsize=8)

    save_figure(fig, output_dir, f"country_self_citation_rate_{suffix}")


def compute_country_matrix(self_cite_df, top_countries):
    """Row-normalized country-to-country citation proportions."""
    # Filter to rows where citing country is in top_countries
    df = self_cite_df[self_cite_df["citing_country"].isin(top_countries)].copy()

    # Explode cited countries: each citing row contributes to all cited countries
    rows = []
    for _, r in df.iterrows():
        for cited_country in r["country_list"]:
            if cited_country in top_countries:
                rows.append({
                    "citing_country": r["citing_country"],
                    "cited_country": cited_country,
                })
    if not rows:
        return pd.DataFrame()

    pair_df = pd.DataFrame(rows)
    ct = pd.crosstab(pair_df["citing_country"], pair_df["cited_country"])

    # Ensure all top countries appear as both rows and columns
    for c in top_countries:
        if c not in ct.columns:
            ct[c] = 0
        if c not in ct.index:
            ct.loc[c] = 0
    ct = ct.loc[sorted(ct.index), sorted(ct.columns)]

    # Row-normalize
    row_sums = ct.sum(axis=1)
    normalized = ct.div(row_sums, axis=0).fillna(0)

    return normalized


def plot_country_heatmap(matrix_df, output_dir, suffix):
    """Heatmap of country-to-country citation proportions."""
    if matrix_df.empty:
        print("  Skipping heatmap: no data")
        return

    n = len(matrix_df)
    fig_size = max(8, n * 0.6)
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))

    cmap = plt.cm.YlOrRd
    im = ax.imshow(matrix_df.values, cmap=cmap, aspect="auto", vmin=0)

    ax.set_xticks(np.arange(n))
    ax.set_yticks(np.arange(n))
    ax.set_xticklabels([iso2_to_country_name(c) for c in matrix_df.columns],
                       rotation=45, ha="right", fontsize=POSTER_THEME["tick_fontsize"])
    ax.set_yticklabels([iso2_to_country_name(c) for c in matrix_df.index],
                       fontsize=POSTER_THEME["tick_fontsize"])

    # Annotate cells
    for i in range(n):
        for j in range(n):
            val = matrix_df.values[i, j]
            color = "white" if val > 0.5 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    color=color, fontsize=max(6, 10 - n // 5))

    ax.set_xlabel("Cited Paper Country")
    ax.set_ylabel("Citing Author Country")
    label_text = "with author self-cites" if "with_self" in suffix else "author self-cites removed"
    ax.set_title(f"Country-to-Country Citation Proportions ({label_text})")

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Proportion of Citations")

    save_figure(fig, output_dir, f"country_citation_matrix_{suffix}")


# ── Mixed Model: International Collaboration → Citations ──────────────────────

def prepare_mixed_model_data(data_df, pop_lookup=None):
    """Compute cites_per_year, parse countries, explode by country, categorize n_countries."""
    df = parse_cited_countries(data_df)
    df = df[df["n_countries"] > 0].copy()

    # Compute cites_per_year
    df["cites_per_year"] = df["citationcount_openalex"] / (2026 - df["Publication_Year"] + 1)

    # Categorize n_countries
    df["n_countries_cat"] = df["n_countries"].apply(
        lambda n: "1" if n == 1 else ("2" if n == 2 else "3+")
    )

    # Explode: one row per country per paper
    rows = []
    for _, row in df.iterrows():
        for country in row["country_list"]:
            entry = {
                "country": country,
                "n_countries_cat": row["n_countries_cat"],
                "cites_per_year": row["cites_per_year"],
                "SJR_scimago": row.get("SJR_scimago", np.nan),
                "n_authors": row.get("authorcount_openalex", np.nan),
            }
            if pop_lookup is not None:
                entry["population"] = get_population(country, row.get("Publication_Year"), pop_lookup)
            rows.append(entry)
    exploded = pd.DataFrame(rows)
    exploded["log_n_authors"] = np.log1p(exploded["n_authors"])

    if pop_lookup is not None and "population" in exploded.columns:
        exploded["log_population"] = np.log(exploded["population"])
        n_with_pop = exploded["log_population"].notna().sum()
        print(f"  Population data: {n_with_pop} / {len(exploded)} rows matched")

    # Drop rows with missing cites_per_year
    exploded = exploded.dropna(subset=["cites_per_year"]).reset_index(drop=True)

    print(f"  Mixed model data: {len(exploded)} rows, "
          f"{exploded['country'].nunique()} countries, "
          f"{exploded['SJR_scimago'].notna().sum()} with SJR")
    return exploded


def run_r_mixed_model(data_df, label, output_dir, pop_lookup=None):
    """Write paper-level CSV, call R script with 4th arg for mixed model."""
    r_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "country_citation_stats.R")

    mm_df = prepare_mixed_model_data(data_df, pop_lookup=pop_lookup)
    if mm_df.empty:
        print("  No data for mixed model — skipping")
        return None

    # Write the mixed-model CSV
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        mm_csv = f.name
        mm_df.to_csv(f, index=False)

    # We also need a dummy self-citation CSV (sections 1-3 need it) —
    # pass a minimal CSV so sections 1-3 run harmlessly
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        dummy_csv = f.name
        pd.DataFrame({
            "citing_country": ["dummy"],
            "is_self_cite": [0],
            "SJR_scimago": [np.nan],
        }).to_csv(f, index=False)

    try:
        result = subprocess.run(
            ["Rscript", r_script, dummy_csv, output_dir, label, mm_csv],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  R mixed model failed (exit {result.returncode}):")
            if result.stderr:
                print(result.stderr)
            return None
        if result.stdout:
            print(f"  {result.stdout.strip()}")
    finally:
        os.unlink(mm_csv)
        os.unlink(dummy_csv)

    return {
        "mixed_model": os.path.join(output_dir, f"{label}_mixed_model.csv"),
        "mixed_model_summary": os.path.join(output_dir, f"{label}_mixed_model_summary.csv"),
        "predictions": os.path.join(output_dir, f"{label}_mixed_model_predictions.csv"),
    }


def print_mixed_model_summary(paths):
    """Read and display mixed model results."""
    if paths is None:
        return

    if os.path.exists(paths["mixed_model"]):
        coefs = pd.read_csv(paths["mixed_model"])
        if not coefs.empty:
            print(f"\n  Mixed model coefficients:")
            for _, r in coefs.iterrows():
                p_str = f"{r['p_value']:.2e}" if pd.notna(r['p_value']) and r['p_value'] < 0.001 else (
                    f"{r['p_value']:.4f}" if pd.notna(r['p_value']) else "NA")
                print(f"    [{r['model']}] {r['term']}: "
                      f"est={r['estimate']:.4f}, SE={r['std_error']:.4f}, "
                      f"t={r['t_value']:.2f}, p={p_str}")

    if os.path.exists(paths["mixed_model_summary"]):
        summary = pd.read_csv(paths["mixed_model_summary"])
        print(f"\n  Mixed model summary:")
        for _, r in summary.iterrows():
            print(f"    {r['metric']}: {r['value']}")


def plot_predicted_means(paths, output_dir):
    """Point + CI plot of predicted CPY per n_countries_cat, dodged by model."""
    if paths is None or "predictions" not in paths:
        return
    pred_path = paths["predictions"]
    if not os.path.exists(pred_path):
        print("  No predictions CSV found — skipping predicted means plot")
        return

    df = pd.read_csv(pred_path)
    if df.empty:
        return

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))

    models = df["model"].unique()
    colors = {"base": "#4393c3", "adjusted": "#f4a582", "full": "#d6604d"}
    n_models = len(models)
    dodge = 0.2
    cats = ["1", "2", "3+"]
    x_base = np.arange(len(cats))

    for j, model in enumerate(models):
        mdf = df[df["model"] == model]
        # Align to cat order
        mdf = mdf.set_index("n_countries_cat").reindex(cats).reset_index()
        x = x_base + (j - (n_models - 1) / 2) * dodge
        color = colors.get(model, "gray")
        ax.errorbar(x, mdf["predicted_cpy"],
                     yerr=[mdf["predicted_cpy"] - mdf["ci_lower"],
                           mdf["ci_upper"] - mdf["predicted_cpy"]],
                     fmt="o", color=color, capsize=4, capthick=2,
                     markersize=8, linewidth=2, label=model)

    ax.set_xticks(x_base)
    ax.set_xticklabels(cats)
    ax.set_xlabel("Number of Countries")
    ax.set_ylabel("Predicted Citations per Year")
    ax.legend(title="Model")
    style_group_axes(ax)

    save_figure(fig, output_dir, "collab_citations_predicted_means")


# ── Distortion Analysis (Gomez-inspired) ──────────────────────────────────────

def compute_paper_share(data_df, top_countries):
    """Fractional paper share per country (paper with N countries = 1/N each)."""
    df = parse_cited_countries(data_df)
    df = df[df["n_countries"] > 0].copy()

    shares = {}
    total_fractions = 0.0
    for _, row in df.iterrows():
        countries_on_paper = [c for c in row["country_list"] if c in top_countries]
        if not countries_on_paper:
            continue
        frac = 1.0 / len(countries_on_paper)
        for c in countries_on_paper:
            shares[c] = shares.get(c, 0.0) + frac
        total_fractions += 1.0  # each paper contributes 1.0 total

    # Normalize to proportions
    if total_fractions > 0:
        shares = {c: v / total_fractions for c, v in shares.items()}
    return shares


def compute_paper_share_sjr_adjusted(data_df, top_countries):
    """SJR-weighted fractional paper share per country.

    Each paper's contribution is weighted by its SJR. Papers without SJR are
    excluded. A country on a high-SJR paper gets more expected share than one
    on a low-SJR paper.
    """
    df = parse_cited_countries(data_df)
    df = df[df["n_countries"] > 0].copy()
    df = df[pd.to_numeric(df["SJR_scimago"], errors="coerce").notna()].copy()
    df["SJR_scimago"] = pd.to_numeric(df["SJR_scimago"])

    if df.empty:
        return {}

    shares = {}
    total_weight = 0.0
    for _, row in df.iterrows():
        countries_on_paper = [c for c in row["country_list"] if c in top_countries]
        if not countries_on_paper:
            continue
        sjr = row["SJR_scimago"]
        frac = sjr / len(countries_on_paper)
        for c in countries_on_paper:
            shares[c] = shares.get(c, 0.0) + frac
        total_weight += sjr

    if total_weight > 0:
        shares = {c: v / total_weight for c, v in shares.items()}
    return shares


def compute_paper_share_population_adjusted(data_df, top_countries, pop_lookup):
    """Population-adjusted paper share per country.

    Each paper is exploded (one row per country). Each row's weight is
    1 / population(country, year). Rows with missing population are skipped.
    Returns dict: country -> normalized share.
    """
    df = parse_cited_countries(data_df)
    df = df[df["n_countries"] > 0].copy()
    df["Publication_Year"] = pd.to_numeric(df.get("Publication_Year"), errors="coerce")

    shares = {}
    total_weight = 0.0
    skipped = 0

    for _, row in df.iterrows():
        year = row["Publication_Year"]
        for country in row["country_list"]:
            if country not in top_countries:
                continue
            pop = get_population(country, year, pop_lookup)
            if np.isnan(pop) or pop <= 0:
                skipped += 1
                continue
            w = 1.0 / pop
            shares[country] = shares.get(country, 0.0) + w
            total_weight += w

    if total_weight > 0:
        shares = {c: v / total_weight for c, v in shares.items()}

    print(f"  Population-adjusted shares: {len(shares)} countries, {skipped} rows skipped (missing pop)")
    return shares


def compute_distortion_matrix(obs_matrix, paper_shares):
    """Observed citation proportions minus expected (paper share). Returns DataFrame."""
    expected = np.array([paper_shares.get(c, 0.0) for c in obs_matrix.columns])
    distortion = obs_matrix.values - expected[np.newaxis, :]
    return pd.DataFrame(distortion, index=obs_matrix.index, columns=obs_matrix.columns)


def compute_country_distortion_scores(distortion_matrix):
    """Mean distortion per country (as cited) across all citing countries, with SE."""
    scores = []
    for col in distortion_matrix.columns:
        vals = distortion_matrix[col].values
        scores.append({
            "country": col,
            "mean_distortion": vals.mean(),
            "se": vals.std(ddof=1) / np.sqrt(len(vals)) if len(vals) > 1 else 0.0,
            "n_citing": len(vals),
        })
    scores_df = pd.DataFrame(scores).sort_values("mean_distortion", ascending=False)
    return scores_df


def compute_period_distortion(self_cite_df, top_countries, paper_shares):
    """Split citations into early/late halves, compute distortion per country per period."""
    df = self_cite_df[self_cite_df["citing_country"].isin(top_countries)].copy()
    if "year" not in df.columns:
        return pd.DataFrame()

    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df.dropna(subset=["year"])
    median_year = df["year"].median()

    results = []
    for period, mask in [("early", df["year"] < median_year),
                          ("late", df["year"] >= median_year)]:
        period_df = df[mask]
        # Explode and compute proportions
        rows = []
        for _, r in period_df.iterrows():
            for cited_c in r["country_list"]:
                if cited_c in top_countries:
                    rows.append({"cited_country": cited_c})
        if not rows:
            continue
        pair_df = pd.DataFrame(rows)
        cited_counts = pair_df["cited_country"].value_counts()
        total = cited_counts.sum()
        for c in top_countries:
            obs = cited_counts.get(c, 0) / total if total > 0 else 0
            exp = paper_shares.get(c, 0.0)
            results.append({
                "country": c,
                "period": period,
                "distortion": obs - exp,
            })

    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results).pivot(index="country", columns="period", values="distortion").dropna()


def compute_temporal_inequality(self_cite_df, top_countries, paper_shares):
    """Gini coefficient of citation shares per year (observed vs expected)."""
    df = self_cite_df[self_cite_df["citing_country"].isin(top_countries)].copy()
    if "year" not in df.columns:
        return pd.DataFrame()

    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df = df.dropna(subset=["year"])
    df["year"] = df["year"].astype(int)

    def gini(values):
        v = np.array(values, dtype=float)
        if v.sum() == 0 or len(v) < 2:
            return 0.0
        v = np.sort(v)
        n = len(v)
        idx = np.arange(1, n + 1)
        return (2 * np.sum(idx * v) - (n + 1) * np.sum(v)) / (n * np.sum(v))

    results = []
    for year in sorted(df["year"].unique()):
        year_df = df[df["year"] == year]
        # Explode
        cited_list = []
        for _, r in year_df.iterrows():
            for c in r["country_list"]:
                if c in top_countries:
                    cited_list.append(c)
        if not cited_list:
            continue
        cited_counts = pd.Series(cited_list).value_counts()
        total = cited_counts.sum()
        obs_shares = np.array([cited_counts.get(c, 0) / total for c in top_countries])
        exp_shares = np.array([paper_shares.get(c, 0.0) for c in top_countries])

        results.append({
            "year": year,
            "gini_observed": gini(obs_shares),
            "gini_expected": gini(exp_shares),
            "n_citations": total,
        })

    return pd.DataFrame(results)


# ── Distortion Plotting ──────────────────────────────────────────────────────

def _distortion_label(suffix):
    """Build human-readable label from suffix."""
    base = "with author self-cites" if "with_self" in suffix else "author self-cites removed"
    if "sjr_adj" in suffix:
        base += ", SJR-adjusted"
    elif "pop_adj" in suffix:
        base += ", population-adjusted"
    return base


def plot_distortion_heatmap(distortion_matrix, output_dir, suffix):
    """Diverging heatmap: red=overcited, blue=undercited."""
    if distortion_matrix.empty:
        print("  Skipping distortion heatmap: no data")
        return

    n = len(distortion_matrix)
    fig_size = max(8, n * 0.6)
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))

    vmax = max(abs(distortion_matrix.values.min()), abs(distortion_matrix.values.max()))
    im = ax.imshow(distortion_matrix.values, cmap="RdBu_r", aspect="auto",
                   vmin=-vmax, vmax=vmax)

    ax.set_xticks(np.arange(n))
    ax.set_yticks(np.arange(n))
    ax.set_xticklabels([iso2_to_country_name(c) for c in distortion_matrix.columns],
                       rotation=45, ha="right", fontsize=POSTER_THEME["tick_fontsize"])
    ax.set_yticklabels([iso2_to_country_name(c) for c in distortion_matrix.index],
                       fontsize=POSTER_THEME["tick_fontsize"])

    for i in range(n):
        for j in range(n):
            val = distortion_matrix.values[i, j]
            color = "white" if abs(val) > vmax * 0.6 else "black"
            ax.text(j, i, f"{val:+.3f}", ha="center", va="center",
                    color=color, fontsize=max(6, 10 - n // 5))

    ax.set_xlabel("Cited Paper Country")
    ax.set_ylabel("Citing Author Country")
    ax.set_title(f"Citation Distortion (obs - expected) ({_distortion_label(suffix)})")

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Distortion (obs - paper share)")

    save_figure(fig, output_dir, f"country_distortion_matrix_{suffix}")


def plot_distortion_bars(scores_df, output_dir, suffix):
    """Bar chart of mean distortion per country, colored by core/periphery."""
    from matplotlib.patches import Patch

    if scores_df.empty:
        return

    fig, ax = plt.subplots(figsize=(max(FIG_WIDTH, len(scores_df) * 0.5), FIG_HEIGHT))

    x = np.arange(len(scores_df))
    colors = [_CP_COLORS[get_core_periphery(c)] for c in scores_df["country"]]

    ax.bar(x, scores_df["mean_distortion"].values * 100, color=colors,
           edgecolor="black", linewidth=0.5,
           yerr=scores_df["se"].values * 100, capsize=3, ecolor="black")
    ax.axhline(0, color="black", linewidth=1.0)

    median_distortion = scores_df["mean_distortion"].median() * 100
    h_median = ax.axhline(median_distortion, color="#e08020", linestyle=":", linewidth=LINE_WIDTH,
                          label=f"Median distortion: {median_distortion:+.2f}%")

    ax.set_xticks(x)
    ax.set_xticklabels([iso2_to_country_name(c) for c in scores_df["country"].values],
                       rotation=45, ha="right", fontsize=POSTER_THEME["tick_fontsize"])
    ax.set_ylabel("% Deviation from Baseline")
    ax.set_title(f"Country Citation Distortion Scores ({_distortion_label(suffix)})")

    cp_handles = [Patch(facecolor=_CP_COLORS[g], edgecolor="black", label=g.capitalize())
                  for g in ("core", "periphery", "unknown")]
    ax.legend(handles=[h_median] + cp_handles, loc="upper right", fontsize=8)
    style_group_axes(ax)

    save_figure(fig, output_dir, f"country_distortion_scores_{suffix}")


def plot_stability_scatter(period_df, output_dir, suffix):
    """Scatter: early vs late distortion with identity line, labeled, Pearson r."""
    if period_df.empty or "early" not in period_df.columns or "late" not in period_df.columns:
        return

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_WIDTH))  # square

    ax.scatter(period_df["early"], period_df["late"], s=60, c="#2166ac",
               edgecolors="black", linewidth=0.5, zorder=5)

    # Label points
    for country, row in period_df.iterrows():
        ax.annotate(iso2_to_country_name(country), (row["early"], row["late"]),
                    textcoords="offset points", xytext=(5, 5),
                    fontsize=8, zorder=6)

    # Identity line
    lims = [min(period_df[["early", "late"]].min().min(), 0),
            max(period_df[["early", "late"]].max().max(), 0)]
    margin = (lims[1] - lims[0]) * 0.1
    lims = [lims[0] - margin, lims[1] + margin]
    ax.plot(lims, lims, "--", color="gray", linewidth=1.0, zorder=1)
    ax.set_xlim(lims)
    ax.set_ylim(lims)

    # Pearson r
    from scipy.stats import pearsonr
    r, p = pearsonr(period_df["early"], period_df["late"])
    ax.text(0.05, 0.95, f"r = {r:.3f}, p = {p:.3f}",
            transform=ax.transAxes, fontsize=12, va="top",
            fontfamily=POSTER_THEME["font_family"])

    ax.set_xlabel("Distortion (Early Period)")
    ax.set_ylabel("Distortion (Late Period)")
    ax.set_title(f"Distortion Stability: Early vs. Late ({_distortion_label(suffix)})")
    style_group_axes(ax)

    save_figure(fig, output_dir, f"country_distortion_stability_{suffix}")


def plot_inequality_trends(ineq_df, output_dir, suffix):
    """Gini over time: observed vs expected from paper share."""
    if ineq_df.empty:
        return

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))

    ax.plot(ineq_df["year"], ineq_df["gini_observed"], "o-", color="#d6604d",
            linewidth=LINE_WIDTH, markersize=6, label="Observed")
    ax.plot(ineq_df["year"], ineq_df["gini_expected"], "s--", color="#4393c3",
            linewidth=LINE_WIDTH, markersize=6, label="Expected (paper share)")

    ax.set_xlabel("Year")
    ax.set_ylabel("Gini Coefficient")
    ax.set_title(f"Citation Inequality Over Time ({_distortion_label(suffix)})")
    ax.legend()
    style_group_axes(ax)

    save_figure(fig, output_dir, f"country_citation_inequality_{suffix}")


def plot_distortion_choropleth(scores_df, output_dir, suffix):
    """World map colored by distortion score. Requires geopandas."""
    try:
        import geopandas as gpd
    except ImportError:
        print("  Skipping choropleth: geopandas not installed")
        return

    try:
        world = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
    except (AttributeError, Exception):
        # geopandas >= 1.0 removed built-in datasets
        try:
            import geodatasets
            world = gpd.read_file(geodatasets.data.naturalearth.land110)
        except Exception:
            print("  Skipping choropleth: naturalearth dataset not available")
            return

    # Map ISO_A2 codes (our country codes) to geometry
    scores_map = scores_df.set_index("country")["mean_distortion"].to_dict()
    world["distortion"] = world["iso_a2"].map(scores_map)

    fig, ax = plt.subplots(figsize=(15, 8))

    # Plot base map
    world.plot(ax=ax, color="#f0f0f0", edgecolor="black", linewidth=0.3)

    # Plot countries with data
    has_data = world.dropna(subset=["distortion"])
    if has_data.empty:
        plt.close(fig)
        print("  Skipping choropleth: no country codes matched")
        return

    vmax = max(abs(has_data["distortion"].min()), abs(has_data["distortion"].max()))
    has_data.plot(ax=ax, column="distortion", cmap="RdBu_r",
                  vmin=-vmax, vmax=vmax, edgecolor="black", linewidth=0.3,
                  legend=True, legend_kwds={"label": "Citation Distortion", "shrink": 0.6})

    ax.set_axis_off()
    ax.set_title(f"Global Citation Distortion ({_distortion_label(suffix)})",
                 fontsize=POSTER_THEME["label_fontsize"],
                 fontfamily=POSTER_THEME["font_family"])

    save_figure(fig, output_dir, f"country_distortion_map_{suffix}")


# ── Distortion R Stats Orchestration ──────────────────────────────────────────

def run_r_distortion_stats(distortion_scores, period_df, label, output_dir):
    """Write CSVs and call country_distortion_stats.R."""
    r_script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "country_distortion_stats.R")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        scores_csv = f.name
        distortion_scores.to_csv(f, index=False)

    period_csv = ""
    if not period_df.empty:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            period_csv = f.name
            period_df.reset_index().to_csv(f, index=False)

    try:
        result = subprocess.run(
            ["Rscript", r_script, scores_csv, output_dir, label, period_csv],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  R distortion stats failed (exit {result.returncode}):")
            if result.stderr:
                print(result.stderr)
            return None
        if result.stdout:
            print(f"  {result.stdout.strip()}")
    finally:
        os.unlink(scores_csv)
        for path in [period_csv]:
            if path and os.path.exists(path):
                os.unlink(path)

    return {
        "ttest": os.path.join(output_dir, f"{label}_distortion_ttest.csv"),
        "stability": os.path.join(output_dir, f"{label}_distortion_stability.csv"),
    }


def print_distortion_stats_summary(paths):
    """Read and print R distortion stats output."""
    if paths is None:
        return

    if os.path.exists(paths["ttest"]):
        tt = pd.read_csv(paths["ttest"])
        sig = tt[tt["significant"] == "yes"] if "significant" in tt.columns else pd.DataFrame()
        print(f"\n  One-sample t-tests on distortion ({len(sig)}/{len(tt)} significant after Holm):")
        for _, r in tt.iterrows():
            flag = " *" if r.get("significant") == "yes" else ""
            p_str = f"{r['p_adjusted']:.4f}" if pd.notna(r.get("p_adjusted")) else "NA"
            print(f"    {r['country']}: mean={r['mean_distortion']:.4f}, "
                  f"t={r.get('t_stat', 'NA')}, p_adj={p_str}{flag}")

    if os.path.exists(paths["stability"]):
        stab = pd.read_csv(paths["stability"])
        print(f"\n  Stability tests (early vs. late):")
        for _, r in stab.iterrows():
            print(f"    {r['test']}: {r['statistic']:.4f}, p={r['p_value']:.4f}")


# ── Core / Periphery Analysis ─────────────────────────────────────────────────

def plot_core_periphery_comparison(df, country_col, value_col, ylabel, output_dir, suffix):
    """Side-by-side boxplot comparing core vs periphery countries with jitter."""
    from scipy.stats import mannwhitneyu
    from matplotlib.patches import Patch

    df = df.copy()
    df["group"] = df[country_col].apply(get_core_periphery)
    df = df[df["group"].isin(["core", "periphery"])]
    if df.empty:
        print(f"  Skipping core/periphery comparison for {suffix}: no data")
        return

    groups = ["core", "periphery"]
    group_data = [df[df["group"] == g][value_col].dropna().values for g in groups]

    fig, ax = plt.subplots(figsize=(FIG_WIDTH * 0.5, FIG_HEIGHT))

    bp = ax.boxplot(group_data, patch_artist=True, widths=0.4,
                    medianprops={"color": "black", "linewidth": 2.0})
    for patch, group in zip(bp["boxes"], groups):
        patch.set_facecolor(_CP_COLORS[group])
        patch.set_alpha(0.7)

    rng = np.random.default_rng(42)
    for i, (gdata, group) in enumerate(zip(group_data, groups)):
        jitter = rng.uniform(-0.1, 0.1, size=len(gdata))
        ax.scatter(np.full(len(gdata), i + 1) + jitter, gdata,
                   color=_CP_COLORS[group], alpha=0.6, s=30, zorder=3)

    title_suffix = ""
    if len(group_data[0]) >= 2 and len(group_data[1]) >= 2:
        stat, p = mannwhitneyu(group_data[0], group_data[1], alternative="two-sided")
        n1, n2 = len(group_data[0]), len(group_data[1])
        rbe = 1 - 2 * stat / (n1 * n2)
        p_str = f"p = {p:.2e}" if p < 0.001 else f"p = {p:.4f}"
        title_suffix = f"\nMann-Whitney U: {p_str}, r_rb = {rbe:.2f}"

    ax.set_xticks([1, 2])
    ax.set_xticklabels(["Core", "Periphery"], fontsize=POSTER_THEME["tick_fontsize"])
    ax.set_ylabel(ylabel)
    ax.set_title(f"Core vs Periphery: {ylabel}{title_suffix}")
    style_group_axes(ax)

    save_figure(fig, output_dir, f"country_core_periphery_{suffix}")


def plot_selfcite_vs_distortion(rates_df, scores_df, output_dir, suffix):
    """Scatter of self-citation rate vs distortion score, colored by core/periphery."""
    merged = rates_df.rename(columns={"citing_country": "country"}).merge(
        scores_df[["country", "mean_distortion"]], on="country", how="inner"
    )
    if merged.empty:
        print("  Skipping self-cite vs distortion scatter: no matched data")
        return

    merged["group"] = merged["country"].apply(get_core_periphery)

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))

    for group in ["core", "periphery", "unknown"]:
        sub = merged[merged["group"] == group]
        if sub.empty:
            continue
        ax.scatter(sub["self_rate"] * 100, sub["mean_distortion"] * 100,
                   color=_CP_COLORS[group], label=group.capitalize(),
                   s=60, alpha=0.8, zorder=3)

    median_sr = merged["self_rate"].median() * 100
    median_dist = merged["mean_distortion"].median() * 100
    ax.axvline(median_sr, color="gray", linestyle="--", linewidth=1.0,
               label=f"Median self-cite: {median_sr:.1f}%")
    ax.axhline(median_dist, color="#e08020", linestyle=":", linewidth=1.0,
               label=f"Median distortion: {median_dist:+.2f}%")
    ax.axhline(0, color="black", linewidth=0.8)

    for _, row in merged.iterrows():
        ax.annotate(row["country"],
                    (row["self_rate"] * 100, row["mean_distortion"] * 100),
                    textcoords="offset points", xytext=(4, 2),
                    fontsize=7, color=_CP_COLORS[row["group"]])

    ax.set_xlabel("Self-Citation Rate (%)")
    ax.set_ylabel("Mean Distortion (% deviation from baseline)")
    ax.set_title(f"Self-Citation Rate vs Distortion Score ({_distortion_label(suffix)})")
    ax.legend(loc="best", fontsize=8)
    style_group_axes(ax)

    save_figure(fig, output_dir, f"country_selfcite_vs_distortion_{suffix}")


def run_r_core_periphery_stats(df, label, output_dir):
    """Write temp CSV (country, value, group) and call country_core_periphery_stats.R."""
    r_script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "country_core_periphery_stats.R")
    if not os.path.exists(r_script):
        print(f"  Skipping core/periphery R stats: {r_script} not found")
        return None

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        tmp_csv = f.name
        df.to_csv(f, index=False)

    try:
        result = subprocess.run(
            ["Rscript", r_script, tmp_csv, output_dir, label],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"  R core/periphery stats failed (exit {result.returncode}):")
            if result.stderr:
                print(result.stderr)
            return None
        if result.stdout:
            print(f"  {result.stdout.strip()}")
    finally:
        os.unlink(tmp_csv)

    return {
        "mwu": os.path.join(output_dir, f"{label}_mwu.csv"),
        "ttest": os.path.join(output_dir, f"{label}_ttest.csv"),
    }


def print_core_periphery_stats_summary(paths):
    """Read and print R core/periphery stats output."""
    if paths is None:
        return
    if os.path.exists(paths["mwu"]):
        mwu = pd.read_csv(paths["mwu"])
        row = mwu.iloc[0]
        p_str = f"{row['p_value']:.2e}" if row["p_value"] < 0.001 else f"{row['p_value']:.4f}"
        print(f"\n  Mann-Whitney U (core vs periphery):")
        print(f"    U = {row['statistic']:.1f}, p = {p_str}, "
              f"rank-biserial r = {row['rank_biserial_r']:.3f}, "
              f"n_core = {int(row['n_core'])}, n_periphery = {int(row['n_periphery'])}")
    if os.path.exists(paths["ttest"]):
        tt = pd.read_csv(paths["ttest"])
        row = tt.iloc[0]
        p_str = f"{row['p_value']:.2e}" if row["p_value"] < 0.001 else f"{row['p_value']:.4f}"
        print(f"\n  Two-sample t-test (core vs periphery):")
        print(f"    t = {row['t']:.3f}, df = {row['df']:.1f}, p = {p_str}, "
              f"mean_core = {row['mean_core']:.4f}, mean_periphery = {row['mean_periphery']:.4f}, "
              f"Cohen's d = {row['cohens_d']:.3f}")


def run_distortion_analysis(self_cite_df, data_df, top_countries, output_dir, suffix,
                            paper_shares=None):
    """Run all distortion analyses for a given variant (with_self or no_self).

    Returns the distortion scores DataFrame, or None if no data.
    """
    print(f"\n--- Citation Distortion Analysis ({suffix}) ---")

    # 1. Paper shares and distortion matrix
    if paper_shares is None:
        paper_shares = compute_paper_share(data_df, top_countries)
    print(f"  Paper shares computed for {len(paper_shares)} countries")

    matrix = compute_country_matrix(self_cite_df, top_countries)
    if matrix.empty:
        print("  No citation matrix — skipping distortion analysis")
        return None

    distortion = compute_distortion_matrix(matrix, paper_shares)
    plot_distortion_heatmap(distortion, output_dir, suffix)

    scores = compute_country_distortion_scores(distortion)
    plot_distortion_bars(scores, output_dir, suffix)
    print(f"  Distortion scores: sum = {scores['mean_distortion'].sum():.4f} (should be ~0)")

    # Save scores CSV
    scores.to_csv(os.path.join(output_dir, f"country_distortion_scores_{suffix}.csv"), index=False)

    # 2. Stability scatter
    period_df = compute_period_distortion(self_cite_df, top_countries, paper_shares)
    if not period_df.empty:
        plot_stability_scatter(period_df, output_dir, suffix)

    # 3. Citation inequality
    ineq_df = compute_temporal_inequality(self_cite_df, top_countries, paper_shares)
    if not ineq_df.empty:
        plot_inequality_trends(ineq_df, output_dir, suffix)

    # 4. Choropleth
    plot_distortion_choropleth(scores, output_dir, suffix)

    # 5. R statistics
    r_paths = run_r_distortion_stats(scores, period_df, f"distortion_{suffix}", output_dir)
    print_distortion_stats_summary(r_paths)

    return scores


# ── R Stats Orchestration ─────────────────────────────────────────────────────

def run_r_country_stats(self_cite_df, label, output_dir):
    """Write temp CSV, call R script, return paths to output CSVs."""
    r_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "country_citation_stats.R")

    # Prepare CSV: citing_country, is_self_cite, SJR_scimago
    export_df = self_cite_df[["citing_country", "is_self_cite", "SJR_scimago"]].copy()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        tmp_csv = f.name
        export_df.to_csv(f, index=False)

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
        "chisq": os.path.join(output_dir, f"{label}_chisq.csv"),
        "binomial": os.path.join(output_dir, f"{label}_binomial.csv"),
        "logistic": os.path.join(output_dir, f"{label}_logistic.csv"),
        "logistic_summary": os.path.join(output_dir, f"{label}_logistic_summary.csv"),
    }


def print_country_stats_summary(paths):
    """Read and print R output CSVs."""
    # Chi-square
    if os.path.exists(paths["chisq"]):
        chisq = pd.read_csv(paths["chisq"])
        row = chisq.iloc[0]
        p_str = f"{row['p_value']:.2e}" if row["p_value"] < 0.001 else f"{row['p_value']:.4f}"
        print(f"\n  Chi-square test of independence:")
        print(f"    X² = {row['chi_sq']:.2f}, df = {int(row['df'])}, "
              f"p = {p_str}, Cramér's V = {row['cramers_v']:.4f}, n = {int(row['n_total'])}")

    # Binomial tests
    if os.path.exists(paths["binomial"]):
        binom = pd.read_csv(paths["binomial"])
        sig = binom[binom["significant"] == "yes"]
        sig_med = binom[binom.get("significant_vs_median", pd.Series(dtype=str)) == "yes"] \
            if "significant_vs_median" in binom.columns else pd.DataFrame()
        median_rate = binom["median_rate"].iloc[0] if "median_rate" in binom.columns else None
        median_str = f" | median={median_rate:.3f}" if median_rate is not None else ""
        print(f"\n  Per-country binomial tests vs overall rate "
              f"({len(sig)} / {len(binom)} significant){median_str}:")
        for _, r in binom.iterrows():
            flag_overall = " *" if r["significant"] == "yes" else ""
            flag_median = " †" if "significant_vs_median" in r and r["significant_vs_median"] == "yes" else ""
            med_p = f", p_med={r['p_adjusted_vs_median']:.4f}{flag_median}" \
                if "p_adjusted_vs_median" in r else ""
            print(f"    {r['country']}: rate={r['self_rate']:.3f} vs overall={r['overall_rate']:.3f}, "
                  f"p_adj={r['p_adjusted']:.4f}{flag_overall}{med_p}")
        if median_rate is not None:
            print(f"  (* = sig vs overall rate, † = sig vs median rate {median_rate:.3f})")

    # Logistic regression
    if os.path.exists(paths["logistic"]):
        logistic = pd.read_csv(paths["logistic"])
        print(f"\n  Logistic regression coefficients (top terms):")
        for _, r in logistic.head(15).iterrows():
            p_str = f"{r['p_value']:.2e}" if r["p_value"] < 0.001 else f"{r['p_value']:.4f}"
            print(f"    {r['term']}: OR={r['odds_ratio']:.3f}, p={p_str}")

    if os.path.exists(paths["logistic_summary"]):
        summary = pd.read_csv(paths["logistic_summary"])
        print(f"\n  Logistic regression summary:")
        for _, r in summary.iterrows():
            print(f"    {r['metric']}: {r['value']}")


# ── Main Orchestrator ─────────────────────────────────────────────────────────

def analyze_and_plot(cited_by_df, data_df, output_dir, min_papers=MIN_PAPERS):
    """Run full country citation analysis."""
    os.makedirs(output_dir, exist_ok=True)

    # --- Load population data ---
    print("\n--- Loading population data ---")
    try:
        pop_lookup = load_population_data()
        print(f"  Loaded {len(pop_lookup)} (country, year) population entries")
    except Exception as e:
        print(f"  Warning: could not load population data ({e}) — skipping population analyses")
        pop_lookup = None

    # --- Plot 1: Country affiliation ---
    print("\n--- Country Affiliation Summary ---")
    affil_df = prepare_country_affiliation_data(data_df, min_papers)
    if not affil_df.empty:
        plot_country_affiliation(affil_df, output_dir)
        print(f"  Top countries: {', '.join(affil_df['country'].head(10).tolist())}")
    else:
        print("  No countries with enough papers for affiliation plot")

    if pop_lookup is not None:
        affil_pc_df = prepare_country_affiliation_per_capita(data_df, min_papers, pop_lookup)
        plot_country_affiliation_per_capita(affil_pc_df, output_dir)

    # --- International collaboration → publications analysis ---
    print("\n--- International Collaboration → Publications Analysis ---")
    country_intl_df = prepare_country_intl_stats(data_df, min_papers, pop_lookup)
    if not country_intl_df.empty:
        txt_path = run_r_affiliation_stats(country_intl_df, output_dir)
        if txt_path:
            print(f"  R stats written to {txt_path}")
    else:
        print("  No country data for international collaboration analysis")

    # --- Mixed model: international collaboration → citation rate ---
    print("\n--- Mixed Model: International Collaboration → Citations ---")
    mm_paths = run_r_mixed_model(data_df, "collab_citations", output_dir, pop_lookup=pop_lookup)
    print_mixed_model_summary(mm_paths)
    plot_predicted_means(mm_paths, output_dir)

    # Get valid countries for self-citation analysis
    top_countries = filter_countries_by_threshold(data_df, min_papers)
    if not top_countries:
        print("  No countries with enough papers — skipping self-citation analysis")
        return

    # --- With self-citations ---
    print("\n--- Country Self-Citation (with author self-cites) ---")
    self_cite_df = prepare_self_citation_data(cited_by_df, data_df, top_countries)
    if len(self_cite_df) > 0:
        rates = compute_self_citation_rates(self_cite_df)
        plot_self_citation_bars(rates, output_dir, "with_self")

        matrix = compute_country_matrix(self_cite_df, top_countries)
        plot_country_heatmap(matrix, output_dir, "with_self")

        r_paths = run_r_country_stats(self_cite_df, "country_with_self", output_dir)
        if r_paths:
            print_country_stats_summary(r_paths)

    # --- Remove author self-citations ---
    print("\n--- Removing author self-citations ---")
    cited_by_no_self = remove_self_citations(cited_by_df, data_df)

    print("\n--- Country Self-Citation (author self-cites removed) ---")
    self_cite_no_self = prepare_self_citation_data(cited_by_no_self, data_df, top_countries)
    if len(self_cite_no_self) > 0:
        rates_no_self = compute_self_citation_rates(self_cite_no_self)
        plot_self_citation_bars(rates_no_self, output_dir, "no_self")

        matrix_no_self = compute_country_matrix(self_cite_no_self, top_countries)
        plot_country_heatmap(matrix_no_self, output_dir, "no_self")

        r_paths_no_self = run_r_country_stats(self_cite_no_self, "country_no_self", output_dir)
        if r_paths_no_self:
            print_country_stats_summary(r_paths_no_self)

    # --- Distortion analysis (Gomez-inspired) ---
    distortion_scores_with_self = None
    if len(self_cite_df) > 0:
        distortion_scores_with_self = run_distortion_analysis(
            self_cite_df, data_df, top_countries, output_dir, "with_self")
    if len(self_cite_no_self) > 0:
        run_distortion_analysis(self_cite_no_self, data_df, top_countries,
                                output_dir, "no_self")

    # --- SJR-adjusted distortion analysis ---
    sjr_shares = compute_paper_share_sjr_adjusted(data_df, top_countries)
    sjr_scores_with_self = None
    if sjr_shares:
        if len(self_cite_df) > 0:
            sjr_scores_with_self = run_distortion_analysis(
                self_cite_df, data_df, top_countries,
                output_dir, "with_self_sjr_adj", paper_shares=sjr_shares)
        if len(self_cite_no_self) > 0:
            run_distortion_analysis(self_cite_no_self, data_df, top_countries,
                                    output_dir, "no_self_sjr_adj",
                                    paper_shares=sjr_shares)
    else:
        print("\n  No SJR data available — skipping SJR-adjusted distortion")

    # --- Population-adjusted distortion analysis ---
    if pop_lookup is not None:
        pop_shares = compute_paper_share_population_adjusted(data_df, top_countries, pop_lookup)
        if pop_shares:
            if len(self_cite_df) > 0:
                run_distortion_analysis(self_cite_df, data_df, top_countries,
                                        output_dir, "with_self_pop_adj",
                                        paper_shares=pop_shares)
            if len(self_cite_no_self) > 0:
                run_distortion_analysis(self_cite_no_self, data_df, top_countries,
                                        output_dir, "no_self_pop_adj",
                                        paper_shares=pop_shares)
        else:
            print("\n  No population shares computed — skipping population-adjusted distortion")

    # --- Core / Periphery Analysis ---
    # Use SJR-adjusted scores if available, otherwise fall back to unadjusted.
    cp_scores = sjr_scores_with_self if sjr_scores_with_self is not None else distortion_scores_with_self
    cp_suffix = "with_self_sjr_adj" if sjr_scores_with_self is not None else "with_self"

    rates_for_cp = rates if len(self_cite_df) > 0 else pd.DataFrame()

    if not rates_for_cp.empty:
        print("\n--- Core / Periphery: Self-Citation Rates ---")
        plot_core_periphery_comparison(
            rates_for_cp, "citing_country", "self_rate",
            "Self-Citation Rate", output_dir, "selfcite_with_self")
        cp_selfcite_df = rates_for_cp[["citing_country", "self_rate"]].copy()
        cp_selfcite_df = cp_selfcite_df.rename(columns={"citing_country": "country", "self_rate": "value"})
        cp_selfcite_df["group"] = cp_selfcite_df["country"].apply(get_core_periphery)
        cp_selfcite_df = cp_selfcite_df[cp_selfcite_df["group"].isin(["core", "periphery"])]
        r_cp_selfcite = run_r_core_periphery_stats(cp_selfcite_df, "selfcite_with_self", output_dir)
        print_core_periphery_stats_summary(r_cp_selfcite)

    if cp_scores is not None and not cp_scores.empty:
        print(f"\n--- Core / Periphery: Distortion Scores ({cp_suffix}) ---")
        plot_core_periphery_comparison(
            cp_scores, "country", "mean_distortion",
            "Mean Distortion Score", output_dir, f"distortion_{cp_suffix}")
        cp_dist_df = cp_scores[["country", "mean_distortion"]].copy()
        cp_dist_df = cp_dist_df.rename(columns={"mean_distortion": "value"})
        cp_dist_df["group"] = cp_dist_df["country"].apply(get_core_periphery)
        cp_dist_df = cp_dist_df[cp_dist_df["group"].isin(["core", "periphery"])]
        r_cp_dist = run_r_core_periphery_stats(cp_dist_df, f"distortion_{cp_suffix}", output_dir)
        print_core_periphery_stats_summary(r_cp_dist)

        if not rates_for_cp.empty:
            plot_selfcite_vs_distortion(rates_for_cp, cp_scores, output_dir, cp_suffix)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate country citation analysis plots and statistics"
    )
    parser.add_argument("--cited-by", default=CITED_BY_PATH, help="Path to cited_by_info_gender.xlsx")
    parser.add_argument("--data", default=DATA_PATH, help="Path to data.xlsx")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="Output directory for plots")
    parser.add_argument("--min-papers", type=int, default=MIN_PAPERS,
                        help="Minimum papers for a country to be included (default: 10)")
    args = parser.parse_args()

    print("Loading data...")
    cited_by_df, data_df = load_data(args.cited_by, args.data)
    print(f"  cited_by: {len(cited_by_df)} rows, data: {len(data_df)} rows")

    analyze_and_plot(cited_by_df, data_df, args.output_dir, args.min_papers)
    print("\nDone.")
