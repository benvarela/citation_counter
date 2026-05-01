#!/usr/bin/env Rscript
# country_affiliation_stats.R
# Bivariate OLS regressions and correlations:
#   outcome ~ intl_rate (proportion of papers that are international)
# across four outcome variants, at the country level.
#
# Usage: Rscript country_affiliation_stats.R <country_csv> <output_dir>
#
# Input CSV columns:
#   country, total_pubs, intl_pubs, intl_rate, population,
#   pubs_per_capita, log_total_pubs, log_pubs_per_capita
#
# Output:
#   <output_dir>/country_affiliation_r_stats.txt

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript country_affiliation_stats.R <country_csv> <output_dir>")
}

csv_path   <- args[1]
output_dir <- args[2]
out_file   <- file.path(output_dir, "country_affiliation_r_stats.txt")

df <- read.csv(csv_path, stringsAsFactors = FALSE)

fmt_p <- function(p) {
  if (is.na(p)) return("NA")
  if (p < 0.001) return("<0.001")
  formatC(p, digits = 3, format = "f")
}

fmt_n <- function(x, digits = 4) formatC(x, digits = digits, format = "f")

run_model <- function(outcome_col, label, df_sub) {
  df_sub <- df_sub[is.finite(df_sub[[outcome_col]]) & is.finite(df_sub$intl_rate), ]
  n <- nrow(df_sub)

  lines <- character(0)
  lines <- c(lines, paste0("=== Model: ", label, " ~ International Rate ==="))
  lines <- c(lines, paste0("N = ", n))

  if (n < 3) {
    lines <- c(lines, "  Insufficient data (N < 3) — skipped", "")
    return(lines)
  }

  # OLS
  fit <- lm(as.formula(paste0("`", outcome_col, "` ~ intl_rate")), data = df_sub)
  s   <- summary(fit)
  cf  <- s$coefficients

  intercept_est <- cf["(Intercept)", "Estimate"]
  intercept_se  <- cf["(Intercept)", "Std. Error"]
  intercept_p   <- cf["(Intercept)", "Pr(>|t|)"]
  slope_est     <- cf["intl_rate",   "Estimate"]
  slope_se      <- cf["intl_rate",   "Std. Error"]
  slope_p       <- cf["intl_rate",   "Pr(>|t|)"]

  f_stat <- s$fstatistic
  f_val  <- if (!is.null(f_stat)) f_stat["value"] else NA
  f_df1  <- if (!is.null(f_stat)) f_stat["numdf"]  else NA
  f_df2  <- if (!is.null(f_stat)) f_stat["dendf"]  else NA
  f_p    <- if (!is.null(f_stat)) pf(f_val, f_df1, f_df2, lower.tail = FALSE) else NA

  lines <- c(lines,
    paste0("Intercept : ", fmt_n(intercept_est),
           " (SE=", fmt_n(intercept_se), ", p=", fmt_p(intercept_p), ")"),
    paste0("intl_rate : ", fmt_n(slope_est),
           " (SE=", fmt_n(slope_se), ", p=", fmt_p(slope_p), ")"),
    paste0("R\u00b2 = ", fmt_n(s$r.squared, 3),
           ", F(", f_df1, ",", f_df2, ") = ", fmt_n(f_val, 2),
           ", p = ", fmt_p(f_p))
  )

  # Pearson correlation
  pearson <- tryCatch(
    cor.test(df_sub$intl_rate, df_sub[[outcome_col]], method = "pearson"),
    error = function(e) NULL
  )
  if (!is.null(pearson)) {
    lines <- c(lines,
      paste0("Pearson r = ", fmt_n(pearson$estimate, 3),
             ", p = ", fmt_p(pearson$p.value))
    )
  }

  # Spearman correlation
  spearman <- tryCatch(
    cor.test(df_sub$intl_rate, df_sub[[outcome_col]], method = "spearman", exact = FALSE),
    error = function(e) NULL
  )
  if (!is.null(spearman)) {
    lines <- c(lines,
      paste0("Spearman r = ", fmt_n(spearman$estimate, 3),
             ", p = ", fmt_p(spearman$p.value))
    )
  }

  c(lines, "")
}

# --- Run all four models ---

models <- list(
  list(col = "log_pubs_per_capita", label = "log(Publications per Capita)",
       subset = df[!is.na(df$pubs_per_capita), ]),
  list(col = "pubs_per_capita",     label = "Publications per Capita",
       subset = df[!is.na(df$pubs_per_capita), ]),
  list(col = "log_total_pubs",      label = "log(Total Publications)",
       subset = df),
  list(col = "total_pubs",          label = "Total Publications",
       subset = df)
)

header <- c(
  "Country-Level Analysis: International Collaboration vs Publication Output",
  paste0("Generated: ", format(Sys.time(), "%Y-%m-%d %H:%M:%S")),
  paste0("Predictor: intl_rate = proportion of papers with \u22652 countries"),
  ""
)

all_lines <- header
for (m in models) {
  all_lines <- c(all_lines, run_model(m$col, m$label, m$subset))
}

writeLines(all_lines, out_file)
cat("R affiliation stats complete. Output:", out_file, "\n")
