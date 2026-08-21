# F15 · WanGP Backend Audit + Adapter Contract

Version: `wangp-backend-v0.1`

F15 audits `E:\IA\WanGP` without launching WanGP, importing its runtime,
contacting the network, fetching Git remotes or downloading model weights.

## Upstream snapshot verified before F15

As of 2026-08-21, the official WanGP repository documents:

- WanGP v12.53 dated 2026-08-16;
- Python API in `shared/api.py`;
- headless queue processing with `wgp.py --process ...`;
- `--dry-run` validation;
- support for selected low-VRAM workloads down to 6 GB;
- support for RTX 20xx-class NVIDIA GPUs.

The **local audit outranks this upstream snapshot** for what is actually
installed on this machine.

## Adapter priority

1. `PYTHON_API` if local `shared/api.py` exists.
2. `HEADLESS_CLI` if local `--process` contract exists.
3. `WEBUI_ONLY`.
4. `UNAVAILABLE`.

F15 does not import or execute the WanGP runtime to make this decision.

## Hardware probe

F15 may run:

- local environment Python diagnostics;
- `import torch` in the WanGP environment;
- `torch.cuda.is_available()`;
- `nvidia-smi`.

It loads no generative model.

## Model inventory

F15 inventories model-like files under known model directories by:

- path;
- extension;
- byte size.

It does **not** hash multi-GB weight files.

## Licensing

If the local license text contains WanGP custom-license/restricted-commercial
language, F15 classifies the software as:

`SOURCE_AVAILABLE`

rather than automatically calling it open source.

Model/checkpoint licenses remain a separate decision and must be reviewed
before choosing a model.

## No model selection

F15 deliberately leaves:

- model;
- quantization;
- resolution;
- steps;
- guidance;
- offload profile

unselected.

No multi-GB download is authorized by F15.
