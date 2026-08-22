# F49 · Rollback Decision Gate

Version: `rollback-decision-gate-v0.1`.

F49 is the automatic decision gate, not an automatic actuator. A monitored
breach deterministically emits `ROLLBACK_REQUIRED`; clean evidence emits only
`ELIGIBLE_FOR_PROMOTION_REVIEW`.

Rollback metadata comes from F45. If the policy has no previous version, the
decision points back to the baseline default. No runtime configuration is
written and neither rollback nor promotion is executed.
