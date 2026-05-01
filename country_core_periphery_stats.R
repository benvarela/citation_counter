#!/usr/bin/env Rscript
# country_core_periphery_stats.R
# Statistical tests comparing core vs periphery country groups.
#
# Usage: Rscript country_core_periphery_stats.R <input.csv> <output_dir> <label>
#
# Input CSV columns: country, value (numeric), group ("core" or "periphery")
#
# Outputs:
#   <label>_mwu.csv   — Mann-Whitney U test (non-parametric)
#   <label>_ttest.csv — Welch two-sample t-test (parametric supplement)

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3) {
  stop("Usage: Rscript country_core_periphery_stats.R <input.csv> <output_dir> <label>")
}

input_csv  <- args[1]
output_dir <- args[2]
label      <- args[3]

df <- read.csv(input_csv, stringsAsFactors = FALSE)
stopifnot(all(c("country", "value", "group") %in% colnames(df)))

df <- df[df$group %in% c("core", "periphery"), ]
df$value <- as.numeric(df$value)
df <- df[!is.na(df$value), ]

core_vals <- df$value[df$group == "core"]
peri_vals <- df$value[df$group == "periphery"]

n_core      <- length(core_vals)
n_periphery <- length(peri_vals)

# ── Section 1: Mann-Whitney U test ────────────────────────────────────────────

mwu_df <- data.frame(
  statistic      = NA_real_,
  p_value        = NA_real_,
  rank_biserial_r = NA_real_,
  n_core         = n_core,
  n_periphery    = n_periphery,
  stringsAsFactors = FALSE
)

if (n_core >= 2 && n_periphery >= 2) {
  mwu <- wilcox.test(core_vals, peri_vals, alternative = "two.sided", exact = FALSE)
  # Rank-biserial correlation: r = 1 - 2U / (n1 * n2)
  rbe <- 1 - 2 * mwu$statistic / (n_core * n_periphery)
  mwu_df$statistic       <- as.numeric(mwu$statistic)
  mwu_df$p_value         <- mwu$p.value
  mwu_df$rank_biserial_r <- as.numeric(rbe)
} else {
  warning("Insufficient data for Mann-Whitney U test (need n >= 2 per group)")
}

write.csv(mwu_df, file.path(output_dir, paste0(label, "_mwu.csv")), row.names = FALSE)

# ── Section 2: Welch two-sample t-test ────────────────────────────────────────

ttest_df <- data.frame(
  t           = NA_real_,
  df          = NA_real_,
  p_value     = NA_real_,
  mean_core   = mean(core_vals),
  mean_periphery = mean(peri_vals),
  cohens_d    = NA_real_,
  stringsAsFactors = FALSE
)

if (n_core >= 2 && n_periphery >= 2) {
  tt <- t.test(core_vals, peri_vals, var.equal = FALSE)

  # Cohen's d using pooled SD
  sd_pooled <- sqrt(((n_core - 1) * var(core_vals) + (n_periphery - 1) * var(peri_vals)) /
                    (n_core + n_periphery - 2))
  cohens_d <- if (sd_pooled > 0) {
    (mean(core_vals) - mean(peri_vals)) / sd_pooled
  } else {
    NA_real_
  }

  ttest_df$t        <- as.numeric(tt$statistic)
  ttest_df$df       <- as.numeric(tt$parameter)
  ttest_df$p_value  <- tt$p.value
  ttest_df$cohens_d <- cohens_d
} else {
  warning("Insufficient data for t-test (need n >= 2 per group)")
}

write.csv(ttest_df, file.path(output_dir, paste0(label, "_ttest.csv")), row.names = FALSE)

cat("R core/periphery stats complete for:", label, "\n")
cat("  Core n =", n_core, "| Periphery n =", n_periphery, "\n")
if (!is.na(mwu_df$p_value)) {
  cat("  Mann-Whitney U =", round(mwu_df$statistic, 1),
      "p =", signif(mwu_df$p_value, 4),
      "r_rb =", round(mwu_df$rank_biserial_r, 3), "\n")
}
