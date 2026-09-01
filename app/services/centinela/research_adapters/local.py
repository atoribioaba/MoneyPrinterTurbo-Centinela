from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Any, Callable

from .contracts import (
    OptionalRuntimeUnavailable,
    ResearchBundle,
    ResearchContext,
    ResearchDataError,
    ResearchDatum,
    ResearchSource,
)


class SkyfieldDE440Adapter:
    """Offline Skyfield adapter. It never invokes Skyfield's downloader."""

    def __init__(self, bsp_path: str | Path) -> None:
        self.bsp_path = Path(bsp_path)

    def _runtime(self):
        if not self.bsp_path.is_file():
            raise OptionalRuntimeUnavailable(
                "Skyfield requires a pre-downloaded local DE440/DE440s BSP file"
            )
        try:
            api = import_module("skyfield.api")
            almanac = import_module("skyfield.almanac")
            eclipselib = import_module("skyfield.eclipselib")
        except ImportError as exc:
            raise OptionalRuntimeUnavailable(
                "Skyfield is not installed in this frozen environment"
            ) from exc
        return api, almanac, eclipselib

    @staticmethod
    def _time(ts: Any, moment: datetime):
        if moment.tzinfo is None:
            raise ResearchDataError("Skyfield moment must be timezone-aware")
        return ts.from_datetime(moment.astimezone(timezone.utc))

    def position(
        self,
        context: ResearchContext,
        *,
        body: str,
        moment: datetime,
    ) -> ResearchBundle:
        context.require_research()
        api, _, _ = self._runtime()
        eph = api.load_file(str(self.bsp_path))
        ts = api.load.timescale(builtin=True)
        t = self._time(ts, moment)
        try:
            earth = eph["earth"]
            target = eph[body]
            apparent = earth.at(t).observe(target).apparent()
            ra, dec, distance = apparent.radec()
        except Exception as exc:
            raise ResearchDataError(f"Skyfield could not resolve body {body!r}") from exc
        source_id = "skyfield_de440"
        return ResearchBundle(
            data=(
                ResearchDatum(
                    fact_id=f"skyfield:{body}:ra_hours",
                    label_es=f"Ascensión recta de {body}",
                    value=float(ra.hours),
                    unit="hour",
                    source_id=source_id,
                ),
                ResearchDatum(
                    fact_id=f"skyfield:{body}:dec_deg",
                    label_es=f"Declinación de {body}",
                    value=float(dec.degrees),
                    unit="deg",
                    source_id=source_id,
                ),
                ResearchDatum(
                    fact_id=f"skyfield:{body}:distance_au",
                    label_es=f"Distancia geocéntrica de {body}",
                    value=float(distance.au),
                    unit="au",
                    source_id=source_id,
                ),
            ),
            sources=(
                ResearchSource(
                    source_id=source_id,
                    title=f"Skyfield + local {self.bsp_path.name}",
                    provider="Skyfield/JPL",
                    url="https://ssd.jpl.nasa.gov/planets/eph_export.html",
                    classification="LOCAL_DETERMINISTIC_EPHEMERIS",
                    license="Skyfield MIT; JPL ephemeris data",
                    primary_source=True,
                ),
            ),
        )

    def moon_phase(
        self,
        context: ResearchContext,
        *,
        moment: datetime,
    ) -> ResearchBundle:
        context.require_research()
        api, almanac, _ = self._runtime()
        eph = api.load_file(str(self.bsp_path))
        ts = api.load.timescale(builtin=True)
        t = self._time(ts, moment)
        degrees = float(almanac.moon_phase(eph, t).degrees)
        return ResearchBundle(
            data=(
                ResearchDatum(
                    fact_id="skyfield:moon:phase_deg",
                    label_es="Ángulo de fase lunar",
                    value=degrees,
                    unit="deg",
                    source_id="skyfield_de440",
                ),
            ),
            sources=(
                ResearchSource(
                    source_id="skyfield_de440",
                    title=f"Skyfield + local {self.bsp_path.name}",
                    provider="Skyfield/JPL",
                    url="https://ssd.jpl.nasa.gov/planets/eph_export.html",
                    classification="LOCAL_DETERMINISTIC_EPHEMERIS",
                    license="Skyfield MIT; JPL ephemeris data",
                    primary_source=True,
                ),
            ),
        )

    def lunar_eclipses(
        self,
        context: ResearchContext,
        *,
        start: datetime,
        end: datetime,
    ) -> ResearchBundle:
        context.require_research()
        if end <= start:
            raise ResearchDataError("lunar eclipse window must be increasing")
        api, _, eclipselib = self._runtime()
        eph = api.load_file(str(self.bsp_path))
        ts = api.load.timescale(builtin=True)
        t0 = self._time(ts, start)
        t1 = self._time(ts, end)
        times, kinds, _details = eclipselib.lunar_eclipses(t0, t1, eph)
        events = [
            {
                "utc": ti.utc_iso(),
                "kind": eclipselib.LUNAR_ECLIPSES[int(kind)],
            }
            for ti, kind in zip(times, kinds)
        ]
        return ResearchBundle(
            data=(
                ResearchDatum(
                    fact_id="skyfield:moon:lunar_eclipses",
                    label_es="Eclipses lunares en la ventana",
                    value=events,
                    source_id="skyfield_de440",
                ),
            ),
            sources=(
                ResearchSource(
                    source_id="skyfield_de440",
                    title=f"Skyfield + local {self.bsp_path.name}",
                    provider="Skyfield/JPL",
                    url="https://ssd.jpl.nasa.gov/planets/eph_export.html",
                    classification="LOCAL_DETERMINISTIC_EPHEMERIS",
                    license="Skyfield MIT; JPL ephemeris data",
                    primary_source=True,
                ),
            ),
        )


class SunPyLocalAdapter:
    """Local-only solar geometry; deliberately excludes Fido/network access."""

    def solar_orientation(
        self,
        context: ResearchContext,
        *,
        moment: datetime,
    ) -> ResearchBundle:
        context.require_research()
        if moment.tzinfo is None:
            raise ResearchDataError("SunPy moment must be timezone-aware")
        try:
            sun = import_module("sunpy.coordinates.sun")
            time_mod = import_module("astropy.time")
        except ImportError as exc:
            raise OptionalRuntimeUnavailable(
                "SunPy/Astropy are not installed in this frozen environment"
            ) from exc
        t = time_mod.Time(moment.astimezone(timezone.utc))
        try:
            b0 = float(sun.B0(t).to_value("deg"))
            l0 = float(sun.L0(t).to_value("deg"))
        except Exception as exc:
            raise ResearchDataError("SunPy local solar calculation failed") from exc
        return ResearchBundle(
            data=(
                ResearchDatum(
                    "sunpy:sun:b0_deg",
                    "Latitud heliográfica del centro del disco (B0)",
                    b0,
                    "sunpy_local",
                    "deg",
                ),
                ResearchDatum(
                    "sunpy:sun:l0_deg",
                    "Longitud de Carrington del centro del disco (L0)",
                    l0,
                    "sunpy_local",
                    "deg",
                ),
            ),
            sources=(
                ResearchSource(
                    "sunpy_local",
                    "SunPy local solar coordinates",
                    "SunPy",
                    "https://sunpy.org/",
                    "LOCAL_DETERMINISTIC_CALCULATION",
                    "BSD-2-Clause",
                    True,
                ),
            ),
        )


class PoliastroCompatibilityAdapter:
    """Compatibility probe only: poliastro is archived and not canonical for V1."""

    def require_runtime(self, context: ResearchContext) -> ResearchBundle:
        context.require_research()
        try:
            module = import_module("poliastro")
        except ImportError as exc:
            raise OptionalRuntimeUnavailable(
                "poliastro is not installed; archived runtime is not auto-installed"
            ) from exc
        return ResearchBundle(
            sources=(
                ResearchSource(
                    "poliastro_local",
                    f"poliastro {getattr(module, '__version__', 'unknown')}",
                    "poliastro",
                    "https://github.com/poliastro/poliastro",
                    "LOCAL_ARCHIVED_COMPATIBILITY",
                    "MIT",
                    False,
                ),
            ),
            warnings=(
                "poliastro is archived; Centinela does not make it a canonical dependency.",
            ),
        )


class StellariumStaticRendererAdapter:
    """Approved-callable bridge; no invented CLI and no shell execution."""

    def __init__(self, renderer: Callable[[dict[str, Any]], str] | None = None) -> None:
        self.renderer = renderer

    def render(self, context: ResearchContext, request: dict[str, Any]) -> str:
        context.require_research()
        if self.renderer is None:
            raise OptionalRuntimeUnavailable(
                "Stellarium renderer is not configured; no CLI is assumed"
            )
        output = Path(str(self.renderer(dict(request))))
        if not output.is_file() or output.suffix.lower() != ".png":
            raise ResearchDataError("Stellarium renderer must return an existing PNG")
        return str(output)
