# F48 · Canary Monitor

Version: `canary-monitor-v0.1`.

F48 ingests explicit observations from a human-launched canary and evaluates
operational/scientific/publication guardrail thresholds deterministically.

The default V0.1 thresholds are zero-tolerance. The phase is descriptive only:
it neither launches a canary nor executes rollback, and it never converts the
observations into a quality-improvement or causal claim.
