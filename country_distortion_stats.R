#!/usr/bin/env Rscript
# country_distortion_stats.R
# Statistical tests for country-level citation distortion analysis (Gomez-inspired).
#
# Usage: Rscript country_distortion_stats.R <scores.csv> <output_dir> <label> [period.csv]
#
# Input CSVs:
#   scores.csv:   country, mean_distortion, se, n_citing
#   period.csv:   country, early, late (optional)
#
# Outputs:
#   <label>_distortion_ttest.csv    — one-sample t-tests per country (Holm-corrected)
#   <label>_distortion_stability.csv — Pearson r + paired t-test

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3) {
  stop("Usage: Rscript country_distortion_stats.R <scores.csv> <output_dir> <label> [period.csv]")
}

scores_csv <- args[1]
output_dir <- args[2]
label      <- args[3]
period_csv <- if (length(args) >= 4 && nchar(args[4]) > 0) args[4] else ""

scores <- read.csv(scores_csv, stringsAsFactors = FALSE)

# ── Section 1: One-sample t-tests per country ────────────────────────────────
# Test whether mean distortion differs from 0 for each country.
# Since we have the mean, SE, and n from the distortion matrix columns,
# we can reconstruct the t-statistic: t = mean / SE, df = n - 1

ttest_results <- data.frame(
  country         = scores$country,
  mean_distortion = scores$mean_distortion,
  se              = scores$se,
  n_citing        = scores$n_citing,
  stringsAsFactors = FALSE
)

# Compute t-stat and p-value
ttest_results$t_stat <- ifelse(
  ttest_results$se > 0,
  ttest_results$mean_distortion / ttest_results$se,
  NA
)
ttest_results$df <- ttest_results$n_citing - 1
ttest_results$p_raw <- ifelse(
  !is.na(ttest_results$t_stat) & ttest_results$df > 0,
  2 * pt(abs(ttest_results$t_stat), df = ttest_results$df, lower.tail = FALSE),
  NA
)

# Holm correction
valid_p <- !is.na(ttest_results$p_raw)
ttest_results$p_adjusted <- NA
ttest_results$p_adjusted[valid_p] <- p.adjust(ttest_results$p_raw[valid_p], method = "holm")
ttest_results$significant <- ifelse(
  !is.na(ttest_results$p_adjusted) & ttest_results$p_adjusted < 0.05, "yes", "no"
)

write.csv(ttest_results,
          file.path(output_dir, paste0(label, "_distortion_ttest.csv")),
          row.names = FALSE)

# ── Section 2: Stability tests ────────────────────────────────────────────────
# Pearson correlation + paired t-test between early and late periods

stability_results <- data.frame(
  test = character(0), statistic = numeric(0), p_value = numeric(0),
  stringsAsFactors = FALSE
)

if (nchar(period_csv) > 0 && file.exists(period_csv)) {
  pdf <- read.csv(period_csv, stringsAsFactors = FALSE)

  if (nrow(pdf) >= 3 && "early" %in% colnames(pdf) && "late" %in% colnames(pdf)) {
    # Pearson correlation
    cor_test <- cor.test(pdf$early, pdf$late, method = "pearson")
    stability_results <- rbind(stability_results, data.frame(
      test = "pearson_r",
      statistic = cor_test$estimate,
      p_value = cor_test$p.value
    ))

    # Paired t-test
    t_test <- t.test(pdf$early, pdf$late, paired = TRUE)
    stability_results <- rbind(stability_results, data.frame(
      test = "paired_ttest",
      statistic = t_test$statistic,
      p_value = t_test$p.value
    ))
  }
}

write.csv(stability_results,
          file.path(output_dir, paste0(label, "_distortion_stability.csv")),
          row.names = FALSE)

cat("R distortion stats complete for:", label, "\n")
