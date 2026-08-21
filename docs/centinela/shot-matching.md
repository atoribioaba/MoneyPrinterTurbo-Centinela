# F20 · Shot Matching

Version: `shot-matching-v0.1`.

F20 combines F9 measured representative-frame luma with F19 grade targets across
F8 adjacent scene edges. It does not analyze new frames.

When both adjacent shots are genuinely scored, F20 may produce a bounded
exposure-offset recommendation and colour-profile continuity instruction.
Placeholder pairs are no-op and failed analysis requires review.

No material replacement and no render occur here.
