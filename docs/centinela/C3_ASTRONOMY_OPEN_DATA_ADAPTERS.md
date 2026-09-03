# C3 Astronomy Open Data Adapters v0.1

Base integration target:

`8fbd493c389d16ecb91e38dbea940fe429c427c6`

Working branch:

`centinela-c3/astronomy-open-data-adapters-v0.1`

## Security invariants

- `AUTO_PUBLICATION = FALSE` is preserved in every new `StageBinding` and manifest.
- The ordinary `CentinelaControlCenter` remains network-disabled.
- `C3ResearchControlCenter` is an explicit opt-in and creates a
  `ProductionSpine(..., allow_network_adapters=True)`.
- The only new network binding is `SpineStage.RESEARCH`.
- `SCRIPT`, `SCENES`, `MEDIA`, `AUDIO`, `VIDEO_BASE`, `REVIEW_PREP` and
  `PUBLICATION_PACKAGE` receive persisted artifacts; they do not receive network clients.
- The HTTP transport checks `ResearchContext.phase == RESEARCH` before calling
  `requests`.
- Remote transport is HTTPS-only, has a strict host allowlist, rejects URL
  credentials and redirects, bounds response/download sizes, and fails closed.
- `pyproject.toml` and `uv.lock` are unchanged.
- No new auto-publication capability is registered.
- Existing loopback API hardening is untouched.

## Architecture

```text
C3ResearchControlCenter
        |
        v
ProductionSpine(RESEARCH network explicitly allowed)
        |
        v
C3ExternalResearchFactLockAdapter
        |
        +--> Astronomy Core deterministic Fact Lock
        |
        +--> C3AstronomyResearchRouter
                |
                +--> local optional adapters
                |      Skyfield + local DE440/DE440s
                |      SunPy local solar geometry
                |      poliastro compatibility probe only
                |      Stellarium approved renderer bridge
                |
                +--> remote RESEARCH-only adapters
                       Wikimedia Commons
                       Wikidata
                       NASA APOD / EPIC
                       NASA Exoplanet Archive
                       Minor Planet Center
                       MAST (HST/JWST)
                       ESO TAP
                       ESA Gaia TAP
        |
        v
sealed fact_lock
external_research_bundle
provenance_manifest
licenses_manifest
        |
        v
Writer Room (no external research client)
        |
        v
downstream production
```

## Important source semantics

### Skyfield / JPL DE440

The adapter deliberately uses `skyfield.api.load_file()` with a pre-existing local
BSP file. It never calls Skyfield's automatic downloader. DE440s is appropriate for
modern Centinela dates and is much smaller than full DE440/DE441, but installing
Skyfield or downloading a BSP remains a separate, explicit dependency/model action.

### SunPy

The adapter is local-only. It imports `sunpy.coordinates.sun` and calculates solar
orientation quantities from a supplied timestamp. It does not expose SunPy Fido or
other network discovery.

### poliastro

`poliastro` is archived upstream. Centinela therefore exposes only a compatibility
probe and does not make it canonical or install it automatically.

### Stellarium

Stellarium Web Engine is a JavaScript/WebGL renderer, not a Python CLI contract.
Centinela therefore does not invent command-line flags. The bridge accepts only a
separately reviewed local renderer callable and requires an existing PNG result.

### Wikimedia Commons

Search uses MediaWiki `imageinfo` + `extmetadata` and reuses Centinela's existing
Wikimedia licence normalizer/decision logic. Unknown or ambiguous rights stay
`REVIEW` and are not publication-eligible.

### Wikidata

Wikidata is secondary/corroborative evidence in Centinela. The adapter accepts only
validated `Q...` and `P...` identifiers, not arbitrary SPARQL. Facts remain
`NO_VERIFICADO` for publication until an appropriate primary source is present.

In particular, Wikidata is **not** treated as the IAU authority for official
astronomical names.

### NASA

APOD and EPIC are queried only during RESEARCH. APOD's documented `copyright` field
is used as a conservative rights signal. EPIC discovery remains rights-review gated.

The NASA API key is read from `NASA_API_KEY` when present and is never written to
artifacts. `DEMO_KEY` is the fallback for low-volume development.

### NASA Exoplanet Archive

Only a fixed Planetary Systems Composite Parameters lookup is exposed. Arbitrary
ADQL from a user is not accepted by this adapter.

### Minor Planet Center

The connector uses the documented `get-obs` endpoint with one designation and
`ADES_DF`. The designation is validated before transport.

### Hubble / JWST

HST and JWST are not ESO missions. Their programmatic archive is MAST/STScI.
Centinela therefore uses a dedicated MAST CAOM discovery adapter and does not
mislabel HST/JWST media as ESO.

### ESO / ESA

ESO uses its public TAP service. ESA's v0.1 adapter targets the documented public
Gaia TAP service. TAP discovery rows remain `REVIEW` until per-item rights and
download provenance have been resolved.

## MediaResolver bridge

Selected remote media can be downloaded only through
`download_and_seal_media()` during RESEARCH. The function:

1. enforces `ResearchContext.RESEARCH`;
2. performs a bounded HTTPS download through the allowlisted transport;
3. computes SHA-256;
4. writes `<filename>.astromedia.json`;
5. maps accepted Wikimedia licences to `VERIFIED_LICENSE`;
6. maps ambiguous rights to `UNVERIFIED`.

AstroMedia already understands this sidecar convention. Therefore the existing
AstroMedia/MediaResolver/MaterialSelector chain remains the only media-selection
authority.

## Example

```python
from app.services.centinela.research_adapters import C3ResearchControlCenter

center = C3ResearchControlCenter(
    register_default_media=True,
    register_default_av=True,
)

payload = {
    "subject": "Fases de Venus",
    "astronomy_request": {...existing AstronomyContextRequest payload...},
    "external_research": {
        "wikimedia": {"query": "phases of Venus", "limit": 4},
        "nasa_exoplanet": {"planet_name": "Proxima Cen b"},
        "mpc": {"designation": "Bennu"},
    },
}

# The external clients exist only inside the RESEARCH binding.
# The Writer Room receives the sealed Fact Lock produced by RESEARCH.
```

## CI / mocking

`test/services/test_c3_astronomy_research_adapters.py` contains no live network
dependency. Remote adapters receive `FakeTransport` instances. The real transport
itself is monkeypatched to prove that non-RESEARCH phases fail *before* a network
call can occur.

The test suite covers:

- network phase rejection;
- host allowlist rejection;
- Wikimedia accepted/unknown licences;
- Wikidata identifier validation and secondary-source semantics;
- NASA APOD and EPIC mocked responses;
- NASA Exoplanet Archive mocked TAP;
- MAST HST/JWST mocked discovery;
- MPC mocked observations;
- ESO/ESA mocked TAP;
- missing local Skyfield BSP;
- no assumed Stellarium CLI;
- deterministic provenance/license manifests;
- AstroMedia sidecar sealing;
- StageBinding flags (`invokes_network=True`, `invokes_render=False`,
  `auto_publication=False`).

## Dependency decision

This change intentionally leaves `pyproject.toml` and `uv.lock` byte-for-byte
untouched.

Skyfield and SunPy adapters are optional runtime gates until a separate local
dependency review approves exact versions and updates `uv.lock`. `poliastro` is not
recommended as a new canonical dependency because upstream is archived. Stellarium
integration similarly remains an explicit local renderer bridge rather than an
automatic install.
