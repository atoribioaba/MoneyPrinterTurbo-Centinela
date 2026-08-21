# F23 · Voice Studio

Version: `voice-studio-v0.1`.

F23 consumes the grounded F3 narration and the F22 sound-design lineage and
creates a deterministic voice-production plan.

V0.1 deliberately does **not** synthesize audio. It reuses MoneyPrinterTurbo's
existing TTS boundary rather than creating a second TTS stack.

Policy:

- Spanish locale from F3 is preserved.
- A male voice is preferred for this project, but the exact voice ID requires
  explicit human selection after local voice enumeration.
- `edge-tts` is a candidate already integrated by MoneyPrinterTurbo.
- The `edge-tts` client is LGPL-3.0; the remote speech service remains an
  external online service and must not be described as local/OSS.
- Native TTS word/sentence boundaries are the first timestamp source.
- No Whisper/faster-whisper run is triggered by F23.
- No network call, model download, TTS generation or publication occurs here.
