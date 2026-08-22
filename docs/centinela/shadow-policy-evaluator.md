# F46 · Shadow Policy Evaluator

Version: `shadow-policy-evaluator-v0.1`.

F46 evaluates versioned F45 policies against supplied planning cases by calling
the real deterministic `CinematicDirector`. Baseline and candidate are compared
in shadow only.

No runtime state, project file, render, active policy or publication state is
changed. The supported policy parameter whitelist is revalidated independently
instead of trusting F45 blindly.
