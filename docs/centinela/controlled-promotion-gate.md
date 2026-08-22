# F50 · Controlled Promotion Gate

Version: `controlled-promotion-gate-v0.1`.

F50 accepts only F49 policies marked `ELIGIBLE_FOR_PROMOTION_REVIEW` and then
requires a second explicit human APPROVE/REJECT decision.

APPROVE produces an authorization record for a future activation phase. It does
not activate the policy, write runtime configuration, auto-apply changes,
execute rollback or publish content. Actual activation is intentionally deferred
to F51+.
