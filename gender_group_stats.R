#!/usr/bin/env Rscript
# gender_group_stats.R
# Group-level statistical tests for gender citation analysis.
#
# Usage: Rscript gender_group_stats.R <input.csv> <output_dir> <label> [paper_level.csv]
#
# Input CSV must have columns: citing_doi, citing_group, cited_group, SJR_scimago (may be NA)
# Optional paper-level CSV: cited_group, SJR_scimago, citation_count
# Outputs CSV files to output_dir:
#   <label>_chisq.csv        — chi-square test of independence
#   <label>_residuals.csv     — standardised Pearson residuals (long format)
#   <label>_anova.csv         — one-way ANOVA: prop cited target ~ citing_group
#   <label>_anova_tukey.csv   — Tukey HSD post-hoc pairwise comparisons
#   <label>_sjr_models.csv    — binary logistic regressions with SJR adjustment
#   <label>_paper_models.csv  — paper-level: does cited_group predict citations after SJR?

# No external packages required — base R only

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3) {
  stop("Usage: Rscript gender_group_stats.R <input.csv> <output_dir> <label> [paper_level.csv]")
}

input_csv  <- args[1]
output_dir <- args[2]
label      <- args[3]
paper_csv  <- if (length(args) >= 4) args[4] else NULL

df <- read.csv(input_csv, stringsAsFactors = FALSE)
stopifnot(all(c("citing_group", "cited_group") %in% colnames(df)))

# Ensure consistent factor levels
group_levels <- c("MM", "MW", "WM", "WW")
df$citing_group <- factor(df$citing_group, levels = group_levels)
df$cited_group  <- factor(df$cited_group, levels = group_levels)

# ── 1. Chi-square test of independence ────────────────────────────────────────

ct <- table(df$citing_group, df$cited_group)
chi_test <- chisq.test(ct)

# Cramér's V
k <- min(nrow(ct), ncol(ct))
n_total <- sum(ct)
cramers_v <- sqrt(chi_test$statistic / (n_total * (k - 1)))

chisq_df <- data.frame(
  chi_sq    = as.numeric(chi_test$statistic),
  df        = as.numeric(chi_test$parameter),
  p_value   = chi_test$p.value,
  cramers_v = as.numeric(cramers_v),
  n_total   = n_total
)

write.csv(chisq_df, file.path(output_dir, paste0(label, "_chisq.csv")),
          row.names = FALSE)

# ── 2. Standardised Pearson residuals ─────────────────────────────────────────

residuals_long <- expand.grid(
  citing_group = group_levels,
  cited_group  = group_levels,
  stringsAsFactors = FALSE
)

residuals_long$observed     <- as.vector(chi_test$observed)
residuals_long$expected     <- as.vector(chi_test$expected)
residuals_long$std_residual <- as.vector(chi_test$stdres)

write.csv(residuals_long, file.path(output_dir, paste0(label, "_residuals.csv")),
          row.names = FALSE)

# ── 2b. One-way ANOVA: proportion cited TARGET ~ citing_group ────────────

if ("citing_doi" %in% colnames(df)) {
  # Aggregate to paper level: for each citing paper, compute proportion of
  # its citation links going to each cited group
  paper_links <- table(df$citing_doi, df$cited_group)
  paper_totals <- rowSums(paper_links)

  # Build paper-level data frame with citing_group and proportion columns
  paper_props <- as.data.frame(paper_links / paper_totals)
  colnames(paper_props) <- c("citing_doi", "cited_target", "prop")

  # Get citing_group for each citing_doi (one unique value per doi)
  doi_group <- unique(df[, c("citing_doi", "citing_group")])
  paper_props <- merge(paper_props, doi_group, by = "citing_doi")

  anova_rows <- list()
  tukey_rows <- list()

  for (target in group_levels) {
    sub <- paper_props[paper_props$cited_target == target, ]
    sub$citing_group <- factor(sub$citing_group, levels = group_levels)

    fit <- aov(prop ~ citing_group, data = sub)
    sf <- summary(fit)[[1]]

    f_val <- sf["citing_group", "F value"]
    df1   <- sf["citing_group", "Df"]
    df2   <- sf["Residuals", "Df"]
    p_val <- sf["citing_group", "Pr(>F)"]

    # Eta-squared: SS_group / SS_total
    ss_group <- sf["citing_group", "Sum Sq"]
    ss_total <- ss_group + sf["Residuals", "Sum Sq"]
    eta_sq   <- ss_group / ss_total

    anova_rows[[target]] <- data.frame(
      cited_target = target,
      F            = f_val,
      df1          = df1,
      df2          = df2,
      p_value      = p_val,
      eta_sq       = eta_sq,
      stringsAsFactors = FALSE
    )

    # Tukey HSD if significant
    if (!is.na(p_val) && p_val < 0.05) {
      tk <- TukeyHSD(fit)$citing_group
      for (i in seq_len(nrow(tk))) {
        tukey_rows[[length(tukey_rows) + 1]] <- data.frame(
          cited_target = target,
          comparison   = rownames(tk)[i],
          diff         = tk[i, "diff"],
          lwr          = tk[i, "lwr"],
          upr          = tk[i, "upr"],
          p_adj        = tk[i, "p adj"],
          stringsAsFactors = FALSE
        )
      }
    }
  }

  anova_df <- do.call(rbind, anova_rows)
  write.csv(anova_df, file.path(output_dir, paste0(label, "_anova.csv")),
            row.names = FALSE)

  if (length(tukey_rows) > 0) {
    tukey_df <- do.call(rbind, tukey_rows)
  } else {
    tukey_df <- data.frame(
      cited_target = character(0), comparison = character(0),
      diff = numeric(0), lwr = numeric(0), upr = numeric(0),
      p_adj = numeric(0)
    )
  }
  write.csv(tukey_df, file.path(output_dir, paste0(label, "_anova_tukey.csv")),
            row.names = FALSE)
}

# ── 3. Binary logistic regressions with SJR adjustment ───────────────────────

# Filter to rows with non-NA SJR
if ("SJR_scimago" %in% colnames(df)) {
  df_sjr <- df[!is.na(df$SJR_scimago), ]
} else {
  df_sjr <- df[0, ]  # empty — will skip
}

sjr_rows <- list()

if (nrow(df_sjr) > 0) {
  # Set reference level to MM
  df_sjr$citing_group <- relevel(df_sjr$citing_group, ref = "MM")

  for (target in group_levels) {
    df_sjr[[paste0("cited_is_", target)]] <- as.integer(df_sjr$cited_group == target)
    outcome <- paste0("cited_is_", target)

    # Base model: citing_group only
    fml_base <- as.formula(paste(outcome, "~ citing_group"))
    fit_base <- glm(fml_base, data = df_sjr, family = binomial)

    # Adjusted model: citing_group + SJR
    fml_adj <- as.formula(paste(outcome, "~ citing_group + SJR_scimago"))
    fit_adj <- glm(fml_adj, data = df_sjr, family = binomial)

    # Null model (intercept only) for LR test of citing_group
    fml_null <- as.formula(paste(outcome, "~ 1"))
    fit_null <- glm(fml_null, data = df_sjr, family = binomial)

    # LR test: citing_group effect in base model
    lr_base <- anova(fit_null, fit_base, test = "Chisq")
    p_citing_base <- lr_base$`Pr(>Chi)`[2]

    # LR test: citing_group effect in adjusted model (compare null+SJR vs full)
    fml_sjr_only <- as.formula(paste(outcome, "~ SJR_scimago"))
    fit_sjr_only <- glm(fml_sjr_only, data = df_sjr, family = binomial)
    lr_adj <- anova(fit_sjr_only, fit_adj, test = "Chisq")
    p_citing_adj <- lr_adj$`Pr(>Chi)`[2]

    # LR test: does SJR improve fit? (base vs adjusted)
    lr_sjr <- anova(fit_base, fit_adj, test = "Chisq")
    p_sjr       <- lr_sjr$`Pr(>Chi)`[2]
    lr_chi_sq   <- lr_sjr$Deviance[2]
    lr_df_val   <- lr_sjr$Df[2]
    lr_p_value  <- lr_sjr$`Pr(>Chi)`[2]

    sjr_rows[[target]] <- data.frame(
      cited_group    = target,
      p_citing_base  = p_citing_base,
      p_citing_adj   = p_citing_adj,
      p_sjr          = p_sjr,
      lr_chi_sq      = lr_chi_sq,
      lr_df          = lr_df_val,
      lr_p_value     = lr_p_value,
      n              = nrow(df_sjr),
      stringsAsFactors = FALSE
    )
  }

  sjr_df <- do.call(rbind, sjr_rows)
} else {
  sjr_df <- data.frame(
    cited_group   = character(0),
    p_citing_base = numeric(0),
    p_citing_adj  = numeric(0),
    p_sjr         = numeric(0),
    lr_chi_sq     = numeric(0),
    lr_df         = numeric(0),
    lr_p_value    = numeric(0),
    n             = integer(0)
  )
}

write.csv(sjr_df, file.path(output_dir, paste0(label, "_sjr_models.csv")),
          row.names = FALSE)

# ── 4. Paper-level: does cited_group predict citations after controlling SJR? ─

if (!is.null(paper_csv)) {
  pdf <- read.csv(paper_csv, stringsAsFactors = FALSE)
  pdf$cited_group <- factor(pdf$cited_group, levels = group_levels)
  pdf_sjr <- pdf[!is.na(pdf$SJR_scimago) & !is.na(pdf$citation_count), ]

  if (nrow(pdf_sjr) > 0) {
    pdf_sjr$cited_group <- relevel(pdf_sjr$cited_group, ref = "MM")
    pdf_sjr$log_cite <- log1p(pdf_sjr$citation_count)

    # Model 1: cited_group only
    fit_group <- lm(log_cite ~ cited_group, data = pdf_sjr)
    # Model 2: SJR only
    fit_sjr   <- lm(log_cite ~ SJR_scimago, data = pdf_sjr)
    # Model 3: cited_group + SJR
    fit_both  <- lm(log_cite ~ cited_group + SJR_scimago, data = pdf_sjr)

    # LR / F-tests
    # Does cited_group matter without SJR?
    anova_group <- anova(lm(log_cite ~ 1, data = pdf_sjr), fit_group)
    # Does cited_group matter after controlling for SJR?
    anova_group_adj <- anova(fit_sjr, fit_both)
    # Does SJR matter after controlling for cited_group?
    anova_sjr_adj <- anova(fit_group, fit_both)

    # Extract coefficients for group effects from both models
    coef_group <- summary(fit_group)$coefficients
    coef_both  <- summary(fit_both)$coefficients

    # Build results: one row per cited_group showing effect with and without SJR
    paper_rows <- list()
    for (target in group_levels) {
      coef_name <- paste0("cited_group", target)
      if (target == "MM") {
        # Reference level
        est_base <- 0
        p_base   <- NA
        est_adj  <- 0
        p_adj    <- NA
      } else {
        est_base <- coef_group[coef_name, "Estimate"]
        p_base   <- coef_group[coef_name, "Pr(>|t|)"]
        est_adj  <- coef_both[coef_name, "Estimate"]
        p_adj    <- coef_both[coef_name, "Pr(>|t|)"]
      }

      paper_rows[[target]] <- data.frame(
        cited_group       = target,
        coef_base         = est_base,
        p_base            = p_base,
        coef_sjr_adjusted = est_adj,
        p_sjr_adjusted    = p_adj,
        stringsAsFactors  = FALSE
      )
    }

    paper_df <- do.call(rbind, paper_rows)

    # Add overall F-test results as attributes in extra columns on first row
    paper_df$f_group_only_p    <- NA
    paper_df$f_group_adj_p     <- NA
    paper_df$f_sjr_adj_p       <- NA
    paper_df$sjr_coef          <- NA
    paper_df$sjr_coef_p        <- NA
    paper_df$r2_group          <- NA
    paper_df$r2_sjr            <- NA
    paper_df$r2_both           <- NA
    paper_df$n                 <- NA

    paper_df$f_group_only_p[1] <- anova_group$`Pr(>F)`[2]
    paper_df$f_group_adj_p[1]  <- anova_group_adj$`Pr(>F)`[2]
    paper_df$f_sjr_adj_p[1]    <- anova_sjr_adj$`Pr(>F)`[2]
    paper_df$sjr_coef[1]       <- coef_both["SJR_scimago", "Estimate"]
    paper_df$sjr_coef_p[1]     <- coef_both["SJR_scimago", "Pr(>|t|)"]
    paper_df$r2_group[1]       <- summary(fit_group)$r.squared
    paper_df$r2_sjr[1]         <- summary(fit_sjr)$r.squared
    paper_df$r2_both[1]        <- summary(fit_both)$r.squared
    paper_df$n[1]              <- nrow(pdf_sjr)

    write.csv(paper_df, file.path(output_dir, paste0(label, "_paper_models.csv")),
              row.names = FALSE)

    # ── 5. SJR-adjusted over/undercitation using citation links ──────────────────
    #
    # Compute SJR-weighted baseline: fit Poisson model n_links ~ SJR to estimate
    # each paper's expected citation links from journal quality alone. Compare
    # observed citation proportions to these SJR-adjusted expected proportions.
    # This uses our dataset's actual citing patterns (not OpenAlex counts).

    if ("n_links" %in% colnames(pdf_sjr)) {
      # Fit Poisson model: how does SJR predict number of citation links?
      fit_links <- glm(n_links ~ SJR_scimago, data = pdf_sjr, family = poisson)

      # Predicted citation links from SJR alone
      n_hat <- predict(fit_links, type = "response")

      # Adjusted baseline: expected proportion of links per group given SJR
      adj_expected <- tapply(n_hat, pdf_sjr$cited_group, sum)
      adj_baseline <- adj_expected / sum(adj_expected)
      adj_baseline <- adj_baseline[group_levels]

      # Observed proportion of actual citation links
      obs_links <- tapply(pdf_sjr$n_links, pdf_sjr$cited_group, sum)
      obs_prop  <- obs_links / sum(obs_links)
      obs_prop  <- obs_prop[group_levels]

      # % deviation from SJR-adjusted baseline
      deviation_pct <- (obs_prop - adj_baseline) / adj_baseline * 100

      # Bootstrap SEs (resample papers, recompute deviations)
      set.seed(42)
      n_boot <- 1000
      boot_devs <- matrix(NA, nrow = n_boot, ncol = length(group_levels))

      for (b in seq_len(n_boot)) {
        idx <- sample(nrow(pdf_sjr), replace = TRUE)
        bdata <- pdf_sjr[idx, ]

        bfit <- tryCatch(
          glm(n_links ~ SJR_scimago, data = bdata, family = poisson),
          error = function(e) NULL
        )
        if (is.null(bfit)) next

        bn_hat <- predict(bfit, newdata = bdata, type = "response")
        badj   <- tapply(bn_hat, bdata$cited_group, sum)
        badj   <- badj / sum(badj)

        bobs <- tapply(bdata$n_links, bdata$cited_group, sum)
        bobs <- bobs / sum(bobs)

        for (g in seq_along(group_levels)) {
          grp <- group_levels[g]
          if (!is.na(badj[grp]) && badj[grp] > 0 && !is.na(bobs[grp])) {
            boot_devs[b, g] <- (bobs[grp] - badj[grp]) / badj[grp] * 100
          }
        }
      }

      se_pct <- apply(boot_devs, 2, sd, na.rm = TRUE)

      # Counts
      n_links_per_group <- as.integer(obs_links[group_levels])
      n_papers_per_group <- as.integer(table(pdf_sjr$cited_group)[group_levels])

      adj_df <- data.frame(
        cited_group   = group_levels,
        obs_prop      = as.numeric(obs_prop),
        adj_baseline  = as.numeric(adj_baseline),
        deviation_pct = as.numeric(deviation_pct),
        se_pct        = se_pct,
        n_links       = n_links_per_group,
        n_papers      = n_papers_per_group,
        stringsAsFactors = FALSE
      )

      write.csv(adj_df, file.path(output_dir, paste0(label, "_adjusted_deviations.csv")),
                row.names = FALSE)
    }

    # ── 6. Direct standardization: normalize to group proportions + SJR ───────────
    #
    # Use group proportions from all known-gender papers (including missing SJR),
    # and SJR-based expected links from the SJR subset.
    # Expected share for group g:
    #   adj_score_g = p_g * mean(n_hat | group g)
    #   adj_baseline = adj_score_g / sum(adj_score_g)
    #
    # This preserves target group proportions while scaling by SJR-linked intensity.

    if ("n_links" %in% colnames(pdf_sjr)) {
      # Group proportions from all known-gender papers
      p_g <- prop.table(table(pdf$cited_group))[group_levels]

      # SJR-only expected links from previous Poisson fit
      n_hat <- predict(fit_links, type = "response")
      mean_hat <- tapply(n_hat, pdf_sjr$cited_group, mean)
      mean_hat <- mean_hat[group_levels]

      adj_score <- p_g * mean_hat
      adj_baseline2 <- adj_score / sum(adj_score, na.rm = TRUE)

      obs_links2 <- tapply(pdf_sjr$n_links, pdf_sjr$cited_group, sum)
      obs_prop2  <- obs_links2 / sum(obs_links2)
      obs_prop2  <- obs_prop2[group_levels]

      deviation_pct2 <- (obs_prop2 - adj_baseline2) / adj_baseline2 * 100

      # Bootstrap SEs (resample papers, refit, recompute deviations)
      set.seed(42)
      n_boot <- 1000
      boot_devs <- matrix(NA, nrow = n_boot, ncol = length(group_levels))

      for (b in seq_len(n_boot)) {
        idx <- sample(nrow(pdf_sjr), replace = TRUE)
        bdata <- pdf_sjr[idx, ]

        bfit <- tryCatch(
          glm(n_links ~ SJR_scimago, data = bdata, family = poisson),
          error = function(e) NULL
        )
        if (is.null(bfit)) next

        bn_hat <- predict(bfit, newdata = bdata, type = "response")
        bmean_hat <- tapply(bn_hat, bdata$cited_group, mean)
        bmean_hat <- bmean_hat[group_levels]

        badj_score <- p_g * bmean_hat
        badj_base  <- badj_score / sum(badj_score, na.rm = TRUE)

        bobs_links <- tapply(bdata$n_links, bdata$cited_group, sum)
        bobs_prop  <- bobs_links / sum(bobs_links)
        bobs_prop  <- bobs_prop[group_levels]

        for (g in seq_along(group_levels)) {
          grp <- group_levels[g]
          if (!is.na(badj_base[grp]) && badj_base[grp] > 0 && !is.na(bobs_prop[grp])) {
            boot_devs[b, g] <- (bobs_prop[grp] - badj_base[grp]) / badj_base[grp] * 100
          }
        }
      }

      se_pct2 <- apply(boot_devs, 2, sd, na.rm = TRUE)

      n_links_per_group2 <- as.integer(obs_links2[group_levels])
      n_papers_per_group2 <- as.integer(table(pdf_sjr$cited_group)[group_levels])
      p_g_out <- as.numeric(p_g)

      adj_df2 <- data.frame(
        cited_group   = group_levels,
        obs_prop      = as.numeric(obs_prop2),
        adj_baseline  = as.numeric(adj_baseline2),
        deviation_pct = as.numeric(deviation_pct2),
        se_pct        = se_pct2,
        n_links       = n_links_per_group2,
        n_papers      = n_papers_per_group2,
        p_group_all   = p_g_out,
        mean_hat      = as.numeric(mean_hat),
        stringsAsFactors = FALSE
      )

      write.csv(adj_df2, file.path(output_dir, paste0(label, "_direct_adjusted_deviations.csv")),
                row.names = FALSE)
    }

  } else {
    # Write empty file
    write.csv(
      data.frame(cited_group = character(0)),
      file.path(output_dir, paste0(label, "_paper_models.csv")),
      row.names = FALSE
    )
  }
}

cat("R group stats complete for:", label, "\n")
