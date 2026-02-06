#!/usr/bin/env Rscript
# gender_citation_stats.R
# Compute binned expectations, regression, and heatmap statistics for gender citation analysis.
#
# Usage: Rscript gender_citation_stats.R <input.csv> <output_dir> <label>
#
# Input CSV must have columns: p_citing, p_cited
# Outputs three CSV files to output_dir:
#   <label>_binned.csv   — binned expectation deltas with bootstrap CIs
#   <label>_regression.csv — regression grid + summary statistics
#   <label>_heatmap.csv  — 2D histogram log2(observed/expected)

suppressPackageStartupMessages({
  library(boot)
  library(dplyr)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3) {
  stop("Usage: Rscript gender_citation_stats.R <input.csv> <output_dir> <label>")
}

input_csv  <- args[1]
output_dir <- args[2]
label      <- args[3]

N_BINS      <- 10
N_BOOTSTRAP <- 2000
HEATMAP_GRID <- 20
GRID_POINTS  <- 200

df <- read.csv(input_csv, stringsAsFactors = FALSE)
stopifnot(all(c("p_citing", "p_cited") %in% colnames(df)))

p_bar <- mean(df$p_cited)

# ── 1. Binned expectations with bootstrap CIs ──────────────────────────────

# Create bins using quantiles of p_citing
breaks <- quantile(df$p_citing, probs = seq(0, 1, length.out = N_BINS + 1), na.rm = TRUE)
# Ensure unique breaks (can happen with ties)
breaks <- unique(breaks)
n_actual_bins <- length(breaks) - 1

df$bin <- cut(df$p_citing, breaks = breaks, include.lowest = TRUE, labels = FALSE)

delta_stat <- function(data, indices) {
  mean(data[indices]) - p_bar
}

binned_results <- data.frame(
  bin_center = numeric(0),
  bin_n      = integer(0),
  delta      = numeric(0),
  ci_lower   = numeric(0),
  ci_upper   = numeric(0)
)

for (b in seq_len(n_actual_bins)) {
  subset_cited <- df$p_cited[df$bin == b]
  n_b <- length(subset_cited)
  if (n_b < 2) next

  bin_center <- (breaks[b] + breaks[b + 1]) / 2
  delta_val  <- mean(subset_cited) - p_bar

  boot_out <- boot(subset_cited, delta_stat, R = N_BOOTSTRAP)
  ci <- tryCatch(
    boot.ci(boot_out, type = "perc", conf = 0.95)$percent[4:5],
    error = function(e) c(NA, NA)
  )

  binned_results <- rbind(binned_results, data.frame(
    bin_center = bin_center,
    bin_n      = n_b,
    delta      = delta_val,
    ci_lower   = ci[1],
    ci_upper   = ci[2]
  ))
}

write.csv(binned_results, file.path(output_dir, paste0(label, "_binned.csv")),
          row.names = FALSE)

# ── 2. Regression analysis ──────────────────────────────────────────────────

# Linear model
lm_lin  <- lm(p_cited ~ p_citing, data = df)
lm_sum  <- summary(lm_lin)
slope   <- coef(lm_lin)[2]
slope_se <- lm_sum$coefficients[2, 2]
slope_pvalue <- lm_sum$coefficients[2, 4]
r_squared <- lm_sum$r.squared
slope_ci <- confint(lm_lin, "p_citing", level = 0.95)

# Quadratic model
lm_quad <- lm(p_cited ~ p_citing + I(p_citing^2), data = df)
quad_coeff <- coef(lm_quad)[3]

# Prediction grid
x_grid <- seq(min(df$p_citing), max(df$p_citing), length.out = GRID_POINTS)
newdata <- data.frame(p_citing = x_grid)

lin_pred  <- predict(lm_lin, newdata, interval = "confidence", level = 0.95)
quad_pred <- predict(lm_quad, newdata)

reg_df <- data.frame(
  x_grid       = x_grid,
  linear_fit   = lin_pred[, "fit"],
  linear_lower = lin_pred[, "lwr"],
  linear_upper = lin_pred[, "upr"],
  quad_fit     = quad_pred,
  # Repeat scalar stats on every row for easy reading in Python
  slope          = slope,
  slope_se       = slope_se,
  slope_ci_lower = slope_ci[1],
  slope_ci_upper = slope_ci[2],
  slope_pvalue   = slope_pvalue,
  r_squared      = r_squared,
  p_bar          = p_bar,
  quad_coeff     = quad_coeff
)

write.csv(reg_df, file.path(output_dir, paste0(label, "_regression.csv")),
          row.names = FALSE)

# ── 3. Heatmap: 2D histogram with log2(observed/expected) ──────────────────

x_edges <- seq(0, 1, length.out = HEATMAP_GRID + 1)
y_edges <- seq(0, 1, length.out = HEATMAP_GRID + 1)

# 2D histogram
h <- hist2d_manual <- matrix(0, nrow = HEATMAP_GRID, ncol = HEATMAP_GRID)
x_bin <- findInterval(df$p_citing, x_edges, all.inside = TRUE)
y_bin <- findInterval(df$p_cited, y_edges, all.inside = TRUE)
for (i in seq_len(nrow(df))) {
  h[x_bin[i], y_bin[i]] <- h[x_bin[i], y_bin[i]] + 1
}

n_total <- nrow(df)
row_margin <- rowSums(h)
col_margin <- colSums(h)

heatmap_results <- data.frame(
  x_mid    = numeric(0),
  y_mid    = numeric(0),
  log2_ratio = numeric(0),
  observed = numeric(0),
  expected = numeric(0)
)

for (i in seq_len(HEATMAP_GRID)) {
  for (j in seq_len(HEATMAP_GRID)) {
    x_mid <- (x_edges[i] + x_edges[i + 1]) / 2
    y_mid <- (y_edges[j] + y_edges[j + 1]) / 2
    obs   <- h[i, j]
    exp_val <- (row_margin[i] * col_margin[j]) / n_total

    if (exp_val > 0 && obs > 0) {
      log2_r <- log2(obs / exp_val)
    } else {
      log2_r <- NA
    }

    heatmap_results <- rbind(heatmap_results, data.frame(
      x_mid      = x_mid,
      y_mid      = y_mid,
      log2_ratio = log2_r,
      observed   = obs,
      expected   = exp_val
    ))
  }
}

write.csv(heatmap_results, file.path(output_dir, paste0(label, "_heatmap.csv")),
          row.names = FALSE)

cat("R stats complete for:", label, "\n")
