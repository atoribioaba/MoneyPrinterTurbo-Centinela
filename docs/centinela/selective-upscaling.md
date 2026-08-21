# F26 · Selective Upscaling

Version: `selective-upscaling-v0.1`.

F26 decides **where an upscale may be worth testing**. It never performs the
upscale automatically.

Candidate engine for later A/B evaluation:
`Real-ESRGAN-ncnn-vulkan`.

- implementation license: MIT;
- model-weight license is conservatively recorded as `NO_VERIFICADA` until the
  exact local model file is selected and audited;
- no binary/model is downloaded by F26;
- no GPU/Vulkan run occurs;
- no frame is rendered.

Astronomy guardrail: super-resolution must not be used to invent stars,
planetary texture, lunar detail or deep-sky structure. Every candidate requires
A/B fidelity review against the source.
