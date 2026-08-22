# F38 · Association Analyzer

Version: `association-analyzer-v0.1`.

F38 calculates descriptive Spearman rank correlations between numeric F36
features and F37 normalized outcomes, separately for each platform.

Requirements:

- at least five joined content items for a feature/outcome pair;
- variance on both feature and outcome ranks;
- no cross-platform pooling.

V0.1 intentionally does not calculate p-values and does not label an
association statistically significant. Most importantly, an observed
correlation is never promoted to causality.
