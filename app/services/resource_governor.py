from __future__ import annotations

import threading
import time
from contextlib import contextmanager

from app.models.video_base import ResourceClass


class ResourceGovernorError(RuntimeError):
    pass


class ResourceGovernor:
    """Small in-process scheduler for the 16 GB RAM / 6 GB VRAM target machine.

    V0.1 deliberately does not inspect CUDA directly. It prevents known-heavy Centinela
    components from overlapping. Future phases can add live RAM/VRAM telemetry without
    changing the public acquire() contract.
    """

    def __init__(self):
        self._condition = threading.Condition(threading.RLock())
        self._active = {resource_class: 0 for resource_class in ResourceClass}

    def snapshot(self) -> dict[str, int]:
        with self._condition:
            return {key.value: value for key, value in self._active.items()}

    def _can_acquire(self, resource_class: ResourceClass) -> bool:
        total = sum(self._active.values())
        exclusive = self._active[ResourceClass.EXCLUSIVE]
        heavy = self._active[ResourceClass.HEAVY]
        medium = self._active[ResourceClass.MEDIUM]

        if resource_class == ResourceClass.LIGHT:
            return exclusive == 0
        if resource_class == ResourceClass.MEDIUM:
            return exclusive == 0 and heavy == 0 and medium == 0
        if resource_class in {ResourceClass.HEAVY, ResourceClass.EXCLUSIVE}:
            return total == 0
        return False

    @contextmanager
    def acquire(
        self,
        component: str,
        resource_class: ResourceClass,
        timeout_seconds: float = 300.0,
    ):
        resource_class = ResourceClass(resource_class)
        deadline = time.monotonic() + max(0.1, float(timeout_seconds))

        with self._condition:
            while not self._can_acquire(resource_class):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ResourceGovernorError(
                        f"resource timeout for {component} ({resource_class.value})"
                    )
                self._condition.wait(timeout=min(remaining, 1.0))
            self._active[resource_class] += 1

        try:
            yield
        finally:
            with self._condition:
                self._active[resource_class] -= 1
                self._condition.notify_all()


governor = ResourceGovernor()
