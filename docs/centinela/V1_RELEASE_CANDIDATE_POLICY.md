# Centinela V1 Release Candidate policy

## Objective

Converge the historical/cloud branch stack into **one explicit V1 release-candidate lineage** after physical-PC preservation and reconciliation.

## Non-negotiable rules

- Never merge every historical Draft PR mechanically.
- Preserve evidence branches until reconciliation is complete.
- Current physical-PC reconciliation target remains C20 `2c6267c8d9ad3d144ebe6db73189a34c63656ce0`.
- PR #69 is an optional post-C20 improvement line and does not replace C20 before reconciliation.
- No default-branch change before real Golden + Review + F58 + explicit human approval.
- No force-push/destructive cleanup as part of consolidation.
- `AUTO_PUBLICATION=FALSE`.

## RC creation prerequisites

1. read-only PC preflight reviewed;
2. exact local committed state preserved remotely;
3. stash and untracked work preserved separately;
4. local ↔ C20 differences classified;
5. current cloud line and historical evidence mapped;
6. no unresolved ambiguity about which FactLock/MaterialSelector/Review/publication implementation is authoritative.

## RC construction

Create one dedicated RC branch only after prerequisites pass.

Integrate by **resulting contract and code necessity**, not PR number or chronology.

For every imported delta:
- state source branch/commit;
- explain why it is needed;
- targeted tests first;
- full regression after batch;
- preserve provenance in release notes.

## Required single authorities

The RC must have exactly one effective authority for:
- FactLock;
- scientific status/provenance;
- MaterialSelector;
- Review state machine;
- publication authorization;
- ProjectManifest/ArtifactStore lineage;
- final delivery manifest.

Parallel historical implementations may remain in Git history but must not compete at runtime.

## Required V1 evidence

- clean explicit RC SHA;
- Windows targeted + full tests;
- AstroMedia real evidence;
- F57 real evidence;
- GPU/CUDA proof where used;
- NVENC + libx264 fallback proof;
- LLM/TTS/subtitle evidence;
- VIDEO_BASE/master/social real outputs;
- Golden E2E;
- Review 7/7;
- manual Publication Package;
- final Windows SBOM/OSS audit;
- recovery drill;
- F58 readiness;
- human freeze approval.

## Historical PR cleanup

Only after RC evidence is accepted:
- mark older PRs as merged-by-result, superseded, historical evidence or rejected;
- close obsolete Drafts without deleting valuable branches until backup policy permits;
- update Issues #3/#5/#67/#68;
- document the new canonical branch/SHA;
- decide explicitly whether/when to change the repository default branch.

## Release/freeze

`READY_FOR_HUMAN_FREEZE_APPROVAL` is not itself a freeze.

Freeze requires a separate explicit human decision. Publication remains separate again.

`GENERAR → REVISAR → APROBAR → PUBLICAR`.
