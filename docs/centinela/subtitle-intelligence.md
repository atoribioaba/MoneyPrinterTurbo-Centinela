# F25 · Subtitle Intelligence

Version: `subtitle-intelligence-v0.1`.

F25 follows the project rule: if narration is born from TTS, use the TTS timing
metadata before invoking speech recognition.

Priority:

1. native TTS WordBoundary/SentenceBoundary timing;
2. only if native timing is unavailable and a later explicit fallback is
   approved, evaluate `faster-whisper`;
3. never download or run Whisper automatically.

`faster-whisper` is retained as an MIT-licensed fallback candidate and supports
word-level timestamps, but F25 V0.1 does not instantiate it.

Project formatting target: at most two lines, approximately 32 characters per
line. This is an editorial target, not a platform requirement.
