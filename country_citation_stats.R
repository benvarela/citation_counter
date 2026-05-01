#!/usr/bin/env Rscript
# country_citation_stats.R
# Statistical tests for country-level self-citation analysis.
#
# Usage: Rscript country_citation_stats.R <input.csv> <output_dir> <label>
#
# Input CSV columns: citing_country, is_self_cite (0/1), SJR_scimago (may be NA)
#
# Outputs:
#   <label>_chisq.csv          — chi-square test of independence
#   <label>_binomial.csv       — per-country binomial tests (Holm corrected)
#   <label>_logistic.csv       — logistic regression coefficients
#   <label>_logistic_summary.csv — model fit and LR test summaries

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3) {
  stop("Usage: Rscript country_citation_stats.R <input.csv> <output_dir> <label>")
}

input_csv  <- args[1]
output_dir <- args[2]
label      <- args[3]

df <- read.csv(input_csv, stringsAsFactors = FALSE)
stopifnot(all(c("citing_country", "is_self_cite") %in% colnames(df)))

df$citing_country <- as.factor(df$citing_country)
df$is_self_cite <- as.integer(df$is_self_cite)

# ── Section 1: Chi-square test ────────────────────────────────────────────────

ct <- table(df$citing_country, df$is_self_cite)

# Only run if table has at least 2 rows and 2 columns
if (nrow(ct) >= 2 && ncol(ct) >= 2) {
  chi_result <- chisq.test(ct)
  n_total <- sum(ct)
  k <- min(nrow(ct), ncol(ct))
  cramers_v <- sqrt(chi_result$statistic / (n_total * (k - 1)))

  chisq_df <- data.frame(
    chi_sq    = as.numeric(chi_result$statistic),
    df        = as.numeric(chi_result$parameter),
    p_value   = chi_result$p.value,
    cramers_v = as.numeric(cramers_v),
    n_total   = n_total
  )
} else {
  chisq_df <- data.frame(
    chi_sq = NA, df = NA, p_value = NA, cramers_v = NA, n_total = nrow(df)
  )
}

write.csv(chisq_df, file.path(output_dir, paste0(label, "_chisq.csv")),
          row.names = FALSE)

# ── Section 2: Per-country binomial tests ─────────────────────────────────────
# Tests each country's self-citation rate against:
#   (a) the pooled overall rate across all citations
#   (b) the median country-level self-citation rate

overall_rate <- mean(df$is_self_cite)
countries <- levels(df$citing_country)

# Pre-compute per-country rates to derive the median
per_country_rates <- sapply(countries, function(c) {
  sub <- df[df$citing_country == c, ]
  if (nrow(sub) == 0) return(NA_real_)
  sum(sub$is_self_cite) / nrow(sub)
})
median_rate <- median(per_country_rates, na.rm = TRUE)

binom_results <- data.frame(
  country      = character(0),
  n_total      = integer(0),
  n_self       = integer(0),
  self_rate    = numeric(0),
  overall_rate = numeric(0),
  median_rate  = numeric(0),
  p_raw        = numeric(0),
  p_raw_vs_median = numeric(0),
  stringsAsFactors = FALSE
)

for (c in countries) {
  sub <- df[df$citing_country == c, ]
  n_total <- nrow(sub)
  n_self  <- sum(sub$is_self_cite)
  if (n_total == 0) next

  bt_overall <- binom.test(n_self, n_total, p = overall_rate)
  bt_median  <- binom.test(n_self, n_total, p = median_rate)
  binom_results <- rbind(binom_results, data.frame(
    country         = c,
    n_total         = n_total,
    n_self          = n_self,
    self_rate       = n_self / n_total,
    overall_rate    = overall_rate,
    median_rate     = median_rate,
    p_raw           = bt_overall$p.value,
    p_raw_vs_median = bt_median$p.value,
    stringsAsFactors = FALSE
  ))
}

# Holm-Bonferroni correction for both sets of tests
binom_results$p_adjusted            <- p.adjust(binom_results$p_raw, method = "holm")
binom_results$significant           <- ifelse(binom_results$p_adjusted < 0.05, "yes", "no")
binom_results$p_adjusted_vs_median  <- p.adjust(binom_results$p_raw_vs_median, method = "holm")
binom_results$significant_vs_median <- ifelse(binom_results$p_adjusted_vs_median < 0.05, "yes", "no")

write.csv(binom_results, file.path(output_dir, paste0(label, "_binomial.csv")),
          row.names = FALSE)

# ── Section 3: Logistic regression ────────────────────────────────────────────

# Use rows with non-NA SJR
df_sjr <- df[!is.na(df$SJR_scimago), ]

logistic_df <- data.frame(
  term       = character(0),
  estimate   = numeric(0),
  std_error  = numeric(0),
  z_value    = numeric(0),
  p_value    = numeric(0),
  odds_ratio = numeric(0),
  stringsAsFactors = FALSE
)

summary_rows <- list()

if (nrow(df_sjr) > 50 && length(unique(df_sjr$citing_country)) >= 2) {
  # Set reference level to most-cited country
  country_counts <- table(df_sjr$citing_country)
  ref_country <- names(which.max(country_counts))
  df_sjr$citing_country <- relevel(factor(df_sjr$citing_country), ref = ref_country)

  # Full model: country + SJR
  fit_full <- tryCatch(
    glm(is_self_cite ~ citing_country + SJR_scimago, data = df_sjr, family = binomial),
    error = function(e) NULL
  )

  if (!is.null(fit_full)) {
    coefs <- summary(fit_full)$coefficients
    logistic_df <- data.frame(
      term       = rownames(coefs),
      estimate   = coefs[, 1],
      std_error  = coefs[, 2],
      z_value    = coefs[, 3],
      p_value    = coefs[, 4],
      odds_ratio = exp(coefs[, 1]),
      stringsAsFactors = FALSE
    )
    rownames(logistic_df) <- NULL

    # Model fit
    summary_rows <- append(summary_rows, list(
      data.frame(metric = "n_observations", value = as.character(nrow(df_sjr))),
      data.frame(metric = "n_countries", value = as.character(length(unique(df_sjr$citing_country)))),
      data.frame(metric = "reference_country", value = ref_country),
      data.frame(metric = "AIC_full", value = as.character(round(AIC(fit_full), 2))),
      data.frame(metric = "deviance_full", value = as.character(round(deviance(fit_full), 2))),
      data.frame(metric = "null_deviance", value = as.character(round(fit_full$null.deviance, 2)))
    ))

    # LR test: country effect (full vs SJR-only)
    fit_sjr_only <- tryCatch(
      glm(is_self_cite ~ SJR_scimago, data = df_sjr, family = binomial),
      error = function(e) NULL
    )
    if (!is.null(fit_sjr_only)) {
      lr_country <- anova(fit_sjr_only, fit_full, test = "Chisq")
      summary_rows <- append(summary_rows, list(
        data.frame(metric = "LR_country_chisq",
                   value = as.character(round(lr_country$Deviance[2], 2))),
        data.frame(metric = "LR_country_df",
                   value = as.character(lr_country$Df[2])),
        data.frame(metric = "LR_country_p",
                   value = as.character(signif(lr_country$`Pr(>Chi)`[2], 4)))
      ))
    }

    # LR test: SJR effect (full vs country-only)
    fit_country_only <- tryCatch(
      glm(is_self_cite ~ citing_country, data = df_sjr, family = binomial),
      error = function(e) NULL
    )
    if (!is.null(fit_country_only)) {
      lr_sjr <- anova(fit_country_only, fit_full, test = "Chisq")
      summary_rows <- append(summary_rows, list(
        data.frame(metric = "LR_SJR_chisq",
                   value = as.character(round(lr_sjr$Deviance[2], 2))),
        data.frame(metric = "LR_SJR_df",
                   value = as.character(lr_sjr$Df[2])),
        data.frame(metric = "LR_SJR_p",
                   value = as.character(signif(lr_sjr$`Pr(>Chi)`[2], 4)))
      ))
    }
  }
} else {
  summary_rows <- append(summary_rows, list(
    data.frame(metric = "status", value = "skipped_insufficient_data")
  ))
}

write.csv(logistic_df, file.path(output_dir, paste0(label, "_logistic.csv")),
          row.names = FALSE)

if (length(summary_rows) > 0) {
  summary_df <- do.call(rbind, summary_rows)
} else {
  summary_df <- data.frame(metric = character(0), value = character(0))
}
write.csv(summary_df, file.path(output_dir, paste0(label, "_logistic_summary.csv")),
          row.names = FALSE)

cat("R country stats complete for:", label, "\n")

# ── Section 4: Mixed model — international collaboration → citations ─────────
# Optional: if a 4th arg (paper-level CSV) is provided, fit mixed models.
# Columns: country, n_countries_cat, cites_per_year, SJR_scimago

if (length(args) >= 4) {
  mixed_csv <- args[4]
  mdf <- read.csv(mixed_csv, stringsAsFactors = FALSE)
  stopifnot(all(c("country", "n_countries_cat", "cites_per_year") %in% colnames(mdf)))

  mdf$country <- as.factor(mdf$country)
  mdf$n_countries_cat <- factor(mdf$n_countries_cat, levels = c("1", "2", "3+"))
  mdf$log_cpy <- log1p(mdf$cites_per_year)

  if (!requireNamespace("lme4", quietly = TRUE)) {
    stop("lme4 package is required for mixed model analysis")
  }
  if (!requireNamespace("lmerTest", quietly = TRUE)) {
    stop("lmerTest package is required for mixed model p-values")
  }

  library(lme4)
  library(lmerTest)

  coef_rows <- list()
  summary_rows_mm <- list()

  n_obs <- nrow(mdf)
  n_groups <- length(unique(mdf$country))
  summary_rows_mm <- append(summary_rows_mm, list(
    data.frame(metric = "n_obs_all", value = as.character(n_obs)),
    data.frame(metric = "n_groups_all", value = as.character(n_groups))
  ))

  # --- Null model ---
  fit_null <- tryCatch(
    lmer(log_cpy ~ 1 + (1 | country), data = mdf, REML = FALSE),
    error = function(e) { cat("  Null model failed:", e$message, "\n"); NULL }
  )

  # --- Base model: n_countries_cat ---
  fit_base <- tryCatch(
    lmer(log_cpy ~ n_countries_cat + (1 | country), data = mdf, REML = FALSE),
    error = function(e) { cat("  Base model failed:", e$message, "\n"); NULL }
  )

  if (!is.null(fit_base)) {
    coefs_base <- summary(fit_base)$coefficients
    for (i in seq_len(nrow(coefs_base))) {
      coef_rows <- append(coef_rows, list(data.frame(
        model     = "base",
        term      = rownames(coefs_base)[i],
        estimate  = coefs_base[i, "Estimate"],
        std_error = coefs_base[i, "Std. Error"],
        t_value   = coefs_base[i, "t value"],
        p_value   = if ("Pr(>|t|)" %in% colnames(coefs_base)) coefs_base[i, "Pr(>|t|)"] else NA,
        stringsAsFactors = FALSE
      )))
    }

    # ICC from base model
    vc <- as.data.frame(VarCorr(fit_base))
    var_country <- vc[vc$grp == "country", "vcov"]
    var_resid <- vc[vc$grp == "Residual", "vcov"]
    icc <- var_country / (var_country + var_resid)

    summary_rows_mm <- append(summary_rows_mm, list(
      data.frame(metric = "ICC_base", value = as.character(round(icc, 4))),
      data.frame(metric = "var_country_base", value = as.character(round(var_country, 4))),
      data.frame(metric = "var_residual_base", value = as.character(round(var_resid, 4)))
    ))
  }

  # LR test: null vs base (effect of n_countries)
  if (!is.null(fit_null) && !is.null(fit_base)) {
    lr_test <- anova(fit_null, fit_base)
    chi_sq <- lr_test$Chisq[2]
    lr_df <- lr_test$Df[2]
    lr_p <- lr_test$`Pr(>Chisq)`[2]
    summary_rows_mm <- append(summary_rows_mm, list(
      data.frame(metric = "LR_ncountries_chisq", value = as.character(round(chi_sq, 4))),
      data.frame(metric = "LR_ncountries_df", value = as.character(lr_df)),
      data.frame(metric = "LR_ncountries_p", value = as.character(signif(lr_p, 4)))
    ))
  }

  # --- Adjusted model: n_countries_cat + SJR (non-NA rows only) ---
  mdf_sjr <- mdf[!is.na(mdf$SJR_scimago), ]
  n_obs_sjr <- nrow(mdf_sjr)
  n_groups_sjr <- length(unique(mdf_sjr$country))

  summary_rows_mm <- append(summary_rows_mm, list(
    data.frame(metric = "n_obs_sjr", value = as.character(n_obs_sjr)),
    data.frame(metric = "n_groups_sjr", value = as.character(n_groups_sjr))
  ))

  if (n_obs_sjr > 50 && n_groups_sjr >= 2) {
    fit_base_sjr <- tryCatch(
      lmer(log_cpy ~ n_countries_cat + (1 | country), data = mdf_sjr, REML = FALSE),
      error = function(e) { cat("  Base (SJR subset) failed:", e$message, "\n"); NULL }
    )

    fit_adj <- tryCatch(
      lmer(log_cpy ~ n_countries_cat + SJR_scimago + (1 | country), data = mdf_sjr, REML = FALSE),
      error = function(e) { cat("  Adjusted model failed:", e$message, "\n"); NULL }
    )

    if (!is.null(fit_adj)) {
      coefs_adj <- summary(fit_adj)$coefficients
      for (i in seq_len(nrow(coefs_adj))) {
        coef_rows <- append(coef_rows, list(data.frame(
          model     = "adjusted",
          term      = rownames(coefs_adj)[i],
          estimate  = coefs_adj[i, "Estimate"],
          std_error = coefs_adj[i, "Std. Error"],
          t_value   = coefs_adj[i, "t value"],
          p_value   = if ("Pr(>|t|)" %in% colnames(coefs_adj)) coefs_adj[i, "Pr(>|t|)"] else NA,
          stringsAsFactors = FALSE
        )))
      }

      vc_adj <- as.data.frame(VarCorr(fit_adj))
      var_country_adj <- vc_adj[vc_adj$grp == "country", "vcov"]
      var_resid_adj <- vc_adj[vc_adj$grp == "Residual", "vcov"]
      icc_adj <- var_country_adj / (var_country_adj + var_resid_adj)

      summary_rows_mm <- append(summary_rows_mm, list(
        data.frame(metric = "ICC_adjusted", value = as.character(round(icc_adj, 4))),
        data.frame(metric = "var_country_adjusted", value = as.character(round(var_country_adj, 4))),
        data.frame(metric = "var_residual_adjusted", value = as.character(round(var_resid_adj, 4)))
      ))
    }

    # LR test: base vs adjusted on SJR subset (effect of SJR)
    if (!is.null(fit_base_sjr) && !is.null(fit_adj)) {
      lr_sjr <- anova(fit_base_sjr, fit_adj)
      summary_rows_mm <- append(summary_rows_mm, list(
        data.frame(metric = "LR_SJR_chisq", value = as.character(round(lr_sjr$Chisq[2], 4))),
        data.frame(metric = "LR_SJR_df", value = as.character(lr_sjr$Df[2])),
        data.frame(metric = "LR_SJR_p", value = as.character(signif(lr_sjr$`Pr(>Chisq)`[2], 4)))
      ))
    }

    # --- Full model: n_countries_cat + SJR + log_n_authors ---
    fit_full_mm <- NULL
    if ("log_n_authors" %in% colnames(mdf_sjr)) {
      mdf_full <- mdf_sjr[!is.na(mdf_sjr$log_n_authors), ]
      n_obs_full <- nrow(mdf_full)
      summary_rows_mm <- append(summary_rows_mm, list(
        data.frame(metric = "n_obs_full", value = as.character(n_obs_full))
      ))

      if (n_obs_full > 50) {
        fit_adj_full_subset <- tryCatch(
          lmer(log_cpy ~ n_countries_cat + SJR_scimago + (1 | country),
               data = mdf_full, REML = FALSE),
          error = function(e) { cat("  Adj (full subset) failed:", e$message, "\n"); NULL }
        )

        fit_full_mm <- tryCatch(
          lmer(log_cpy ~ n_countries_cat + SJR_scimago + log_n_authors + (1 | country),
               data = mdf_full, REML = FALSE),
          error = function(e) { cat("  Full model failed:", e$message, "\n"); NULL }
        )

        if (!is.null(fit_full_mm)) {
          coefs_full <- summary(fit_full_mm)$coefficients
          for (i in seq_len(nrow(coefs_full))) {
            coef_rows <- append(coef_rows, list(data.frame(
              model     = "full",
              term      = rownames(coefs_full)[i],
              estimate  = coefs_full[i, "Estimate"],
              std_error = coefs_full[i, "Std. Error"],
              t_value   = coefs_full[i, "t value"],
              p_value   = if ("Pr(>|t|)" %in% colnames(coefs_full)) coefs_full[i, "Pr(>|t|)"] else NA,
              stringsAsFactors = FALSE
            )))
          }

          vc_full <- as.data.frame(VarCorr(fit_full_mm))
          var_country_full <- vc_full[vc_full$grp == "country", "vcov"]
          var_resid_full <- vc_full[vc_full$grp == "Residual", "vcov"]
          icc_full <- var_country_full / (var_country_full + var_resid_full)

          summary_rows_mm <- append(summary_rows_mm, list(
            data.frame(metric = "ICC_full", value = as.character(round(icc_full, 4))),
            data.frame(metric = "var_country_full", value = as.character(round(var_country_full, 4))),
            data.frame(metric = "var_residual_full", value = as.character(round(var_resid_full, 4)))
          ))
        }

        # LR test: adjusted vs full (effect of log_n_authors)
        if (!is.null(fit_adj_full_subset) && !is.null(fit_full_mm)) {
          lr_authors <- anova(fit_adj_full_subset, fit_full_mm)
          summary_rows_mm <- append(summary_rows_mm, list(
            data.frame(metric = "LR_authors_chisq",
                       value = as.character(round(lr_authors$Chisq[2], 4))),
            data.frame(metric = "LR_authors_df",
                       value = as.character(lr_authors$Df[2])),
            data.frame(metric = "LR_authors_p",
                       value = as.character(signif(lr_authors$`Pr(>Chisq)`[2], 4)))
          ))
        }

        # --- Population model: full model + log_population ---
        if ("log_population" %in% colnames(mdf_full)) {
          mdf_pop <- mdf_full[is.finite(mdf_full$log_population), ]
          n_obs_pop <- nrow(mdf_pop)
          summary_rows_mm <- append(summary_rows_mm, list(
            data.frame(metric = "n_obs_pop", value = as.character(n_obs_pop))
          ))

          if (n_obs_pop > 50) {
            fit_pop_mm <- tryCatch(
              lmer(log_cpy ~ n_countries_cat + SJR_scimago + log_n_authors + log_population + (1 | country),
                   data = mdf_pop, REML = FALSE),
              error = function(e) { cat("  Population model failed:", e$message, "\n"); NULL }
            )

            if (!is.null(fit_pop_mm)) {
              coefs_pop <- summary(fit_pop_mm)$coefficients
              for (i in seq_len(nrow(coefs_pop))) {
                coef_rows <- append(coef_rows, list(data.frame(
                  model     = "pop_model",
                  term      = rownames(coefs_pop)[i],
                  estimate  = coefs_pop[i, "Estimate"],
                  std_error = coefs_pop[i, "Std. Error"],
                  t_value   = coefs_pop[i, "t value"],
                  p_value   = if ("Pr(>|t|)" %in% colnames(coefs_pop)) coefs_pop[i, "Pr(>|t|)"] else NA,
                  stringsAsFactors = FALSE
                )))
              }

              vc_pop <- as.data.frame(VarCorr(fit_pop_mm))
              var_country_pop <- vc_pop[vc_pop$grp == "country", "vcov"]
              var_resid_pop <- vc_pop[vc_pop$grp == "Residual", "vcov"]
              icc_pop <- var_country_pop / (var_country_pop + var_resid_pop)

              summary_rows_mm <- append(summary_rows_mm, list(
                data.frame(metric = "ICC_pop_model", value = as.character(round(icc_pop, 4))),
                data.frame(metric = "AIC_pop_model", value = as.character(round(AIC(fit_pop_mm), 2))),
                data.frame(metric = "var_country_pop_model", value = as.character(round(var_country_pop, 4))),
                data.frame(metric = "var_residual_pop_model", value = as.character(round(var_resid_pop, 4)))
              ))

              # LR test: full vs pop_model (effect of log_population)
              if (!is.null(fit_full_mm)) {
                fit_full_pop_subset <- tryCatch(
                  lmer(log_cpy ~ n_countries_cat + SJR_scimago + log_n_authors + (1 | country),
                       data = mdf_pop, REML = FALSE),
                  error = function(e) NULL
                )
                if (!is.null(fit_full_pop_subset)) {
                  lr_pop <- anova(fit_full_pop_subset, fit_pop_mm)
                  summary_rows_mm <- append(summary_rows_mm, list(
                    data.frame(metric = "LR_population_chisq",
                               value = as.character(round(lr_pop$Chisq[2], 4))),
                    data.frame(metric = "LR_population_df",
                               value = as.character(lr_pop$Df[2])),
                    data.frame(metric = "LR_population_p",
                               value = as.character(signif(lr_pop$`Pr(>Chisq)`[2], 4)))
                  ))
                }
              }
            }
          }
        }
      }
    }

    # --- Predicted means per n_countries_cat for each model ---
    pred_rows <- list()
    cats <- c("1", "2", "3+")

    # Helper: compute predicted means at mean covariates, RE=0
    compute_preds <- function(fit, model_name, newdata_base) {
      rows_out <- list()
      for (cat in cats) {
        nd <- newdata_base
        nd$n_countries_cat <- factor(cat, levels = c("1", "2", "3+"))
        pred <- predict(fit, newdata = nd, re.form = NA)
        # SE via variance of fixed effects
        fe_form <- formula(fit, fixed.only = TRUE)
        rhs <- delete.response(terms(fe_form))
        X <- model.matrix(rhs, nd)
        vcov_mat <- as.matrix(vcov(fit))
        se <- sqrt(diag(X %*% vcov_mat %*% t(X)))
        rows_out <- append(rows_out, list(data.frame(
          model = model_name,
          n_countries_cat = cat,
          predicted_cpy = expm1(pred),
          ci_lower = expm1(pred - 1.96 * se),
          ci_upper = expm1(pred + 1.96 * se),
          stringsAsFactors = FALSE
        )))
      }
      return(rows_out)
    }

    # Base model predictions (on SJR subset for comparability)
    if (!is.null(fit_base_sjr)) {
      nd_base <- data.frame(country = levels(mdf_sjr$country)[1])
      pred_rows <- append(pred_rows, compute_preds(fit_base_sjr, "base", nd_base))
    }

    # Adjusted model predictions
    if (!is.null(fit_adj)) {
      nd_adj <- data.frame(
        country = levels(mdf_sjr$country)[1],
        SJR_scimago = mean(mdf_sjr$SJR_scimago, na.rm = TRUE)
      )
      pred_rows <- append(pred_rows, compute_preds(fit_adj, "adjusted", nd_adj))
    }

    # Full model predictions
    if (!is.null(fit_full_mm) && "log_n_authors" %in% colnames(mdf_sjr)) {
      mdf_full_pred <- mdf_sjr[!is.na(mdf_sjr$log_n_authors), ]
      nd_full <- data.frame(
        country = levels(mdf_full_pred$country)[1],
        SJR_scimago = mean(mdf_full_pred$SJR_scimago, na.rm = TRUE),
        log_n_authors = mean(mdf_full_pred$log_n_authors, na.rm = TRUE)
      )
      pred_rows <- append(pred_rows, compute_preds(fit_full_mm, "full", nd_full))
    }

    if (length(pred_rows) > 0) {
      pred_df <- do.call(rbind, pred_rows)
      write.csv(pred_df,
                file.path(output_dir, paste0(label, "_mixed_model_predictions.csv")),
                row.names = FALSE)
    }
  } else {
    summary_rows_mm <- append(summary_rows_mm, list(
      data.frame(metric = "adjusted_status", value = "skipped_insufficient_sjr_data")
    ))
  }

  # Write outputs
  if (length(coef_rows) > 0) {
    coef_df <- do.call(rbind, coef_rows)
  } else {
    coef_df <- data.frame(model = character(0), term = character(0),
                          estimate = numeric(0), std_error = numeric(0),
                          t_value = numeric(0), p_value = numeric(0))
  }
  write.csv(coef_df, file.path(output_dir, paste0(label, "_mixed_model.csv")),
            row.names = FALSE)

  if (length(summary_rows_mm) > 0) {
    summary_mm_df <- do.call(rbind, summary_rows_mm)
  } else {
    summary_mm_df <- data.frame(metric = character(0), value = character(0))
  }
  write.csv(summary_mm_df, file.path(output_dir, paste0(label, "_mixed_model_summary.csv")),
            row.names = FALSE)

  cat("R mixed model complete for:", label, "\n")
}
