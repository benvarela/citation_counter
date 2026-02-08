#!/usr/bin/env Rscript
# gender_citation_stats.R
# Compute binned expectations and regression statistics for gender citation analysis.
#
# Usage: Rscript gender_citation_stats.R <input.csv> <output_dir> <label>
#
# Input CSV must have columns: p_citing, p_cited
# Outputs two CSV files to output_dir:
#   <label>_binned.csv   — binned expectation deltas with bootstrap CIs
#   <label>_regression.csv — regression grid + summary statistics

# No external packages required — base R only

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3) {
  stop("Usage: Rscript gender_citation_stats.R <input.csv> <output_dir> <label>")
}

input_csv  <- args[1]
output_dir <- args[2]
label      <- args[3]

BIN_WIDTH   <- 0.2
MIN_BIN_N   <- 10
N_BOOTSTRAP <- 2000
GRID_POINTS  <- 200

df <- read.csv(input_csv, stringsAsFactors = FALSE)
stopifnot(all(c("p_citing", "p_cited") %in% colnames(df)))

p_bar <- mean(df$p_cited)
field_p_male <- mean(df$p_citing)  # proxy for field gender composition

# ── 1. Binned expectations with standard error ─────────────────────────────

# Create fixed-width bins across [0, 1]
breaks <- seq(0, 1, by = BIN_WIDTH)
df$bin <- cut(df$p_citing, breaks = breaks, include.lowest = TRUE, labels = FALSE)
n_actual_bins <- length(breaks) - 1

binned_results <- data.frame(
  bin_center = numeric(0),
  bin_n      = integer(0),
  delta      = numeric(0),
  se         = numeric(0)
)

for (b in seq_len(n_actual_bins)) {
  subset_cited <- df$p_cited[df$bin == b]
  n_b <- length(subset_cited)
  if (n_b < MIN_BIN_N) next

  bin_center <- (breaks[b] + breaks[b + 1]) / 2
  delta_val  <- (mean(subset_cited) - p_bar) / p_bar * 100   # % deviation from baseline
  se_val     <- sd(subset_cited) / sqrt(n_b) / p_bar * 100   # SE in same % units

  binned_results <- rbind(binned_results, data.frame(
    bin_center = bin_center,
    bin_n      = n_b,
    delta      = delta_val,
    se         = se_val
  ))
}

write.csv(binned_results, file.path(output_dir, paste0(label, "_binned.csv")),
          row.names = FALSE)

# ── 2. Regression analysis ──────────────────────────────────────────────────

# Linear model
lm_lin  <- lm(p_cited ~ p_citing, data = df)
lm_sum  <- summary(lm_lin)
intercept <- coef(lm_lin)[1]
slope   <- coef(lm_lin)[2]
slope_se <- lm_sum$coefficients[2, 2]
slope_pvalue <- lm_sum$coefficients[2, 4]
r_squared <- lm_sum$r.squared
slope_ci <- confint(lm_lin, "p_citing", level = 0.95)

# Effect sizes: predicted over/under-citation at extremes vs baseline
pred_at_1 <- intercept + slope  # predicted p_cited when p_citing = 1 (100% male citer)
pred_at_0 <- intercept          # predicted p_cited when p_citing = 0 (100% female citer)
male_overcite_pct  <- (pred_at_1 - p_bar) / p_bar * 100          # % more male cited by 100% male citer
female_overcite_pct <- (pred_at_0 - p_bar) / p_bar * 100  # % deviation in male cited by 100% female citer
# Adjusted overcitation: how much more males are cited vs expected given field gender ratio
# field_p_male is the expected fraction if citations were gender-blind
baseline_overcite_pct <- (p_bar / field_p_male - 1) * 100

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
  intercept      = intercept,
  slope          = slope,
  slope_se       = slope_se,
  slope_ci_lower = slope_ci[1],
  slope_ci_upper = slope_ci[2],
  slope_pvalue   = slope_pvalue,
  r_squared      = r_squared,
  p_bar          = p_bar,
  field_p_male   = field_p_male,
  quad_coeff     = quad_coeff,
  male_overcite_pct   = male_overcite_pct,
  female_overcite_pct = female_overcite_pct,
  baseline_overcite_pct = baseline_overcite_pct
)

write.csv(reg_df, file.path(output_dir, paste0(label, "_regression.csv")),
          row.names = FALSE)

cat("R stats complete for:", label, "\n")
