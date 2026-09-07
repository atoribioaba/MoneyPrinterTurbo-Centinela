from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import PureWindowsPath


CANONICAL_REPOSITORY_ROOT = r"E:\Github\MoneyPrinterTurbo"
CANONICAL_MEDIA_ROOT = r"D:\ASTRONOMÍA\Medios"

WINDOWS_LEGACY_PATH_LIMIT = 260
WINDOWS_EXTENDED_PATH_LIMIT = 32_767
WINDOWS_COMPONENT_LIMIT = 255

_DRIVE_RE = re.compile(r"^[A-Za-z]:$")
_RESERVED_DEVICE_RE = re.compile(
    r"^(?:CON|PRN|AUX|NUL|CLOCK\$|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])$",
    re.IGNORECASE,
)
_INVALID_COMPONENT_CHARACTERS = frozenset('<>:"/\\|?*')


class WindowsPathContractError(ValueError):
    pass


class WindowsPathRole(str, Enum):
    REPOSITORY = "REPOSITORY"
    MEDIA_LIBRARY = "MEDIA_LIBRARY"


class StorageMedium(str, Enum):
    PENDING_PC = "PENDING_PC"
    UNKNOWN = "UNKNOWN"
    SSD = "SSD"
    HDD = "HDD"


def validate_windows_component(value: str, *, label: str = "path component") -> str:
    """Validate one component against Win32 portability and device-name rules."""

    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value or value in {".", ".."}:
        raise WindowsPathContractError(f"{label} is empty or traverses")
    if len(value) > WINDOWS_COMPONENT_LIMIT:
        raise WindowsPathContractError(f"{label} exceeds {WINDOWS_COMPONENT_LIMIT} characters")
    if value.endswith((" ", ".")):
        raise WindowsPathContractError(f"{label} ends with a Win32-unsafe character")
    if any(ord(character) < 32 for character in value):
        raise WindowsPathContractError(f"{label} contains a control character")
    if any(character in _INVALID_COMPONENT_CHARACTERS for character in value):
        raise WindowsPathContractError(f"{label} contains a Win32-unsafe character")

    device_stem = value.split(".", 1)[0].rstrip(" .")
    if _RESERVED_DEVICE_RE.fullmatch(device_stem):
        raise WindowsPathContractError(f"{label} is a reserved Windows device name")
    return value


def validate_absolute_windows_path(value: str, *, label: str = "path") -> str:
    """Return a canonical drive-absolute Windows path without filesystem access."""

    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value or value != value.strip():
        raise WindowsPathContractError(f"{label} is empty or padded with whitespace")

    path = PureWindowsPath(value)
    if not path.is_absolute() or not _DRIVE_RE.fullmatch(path.drive):
        raise WindowsPathContractError(
            f"{label} must be a local drive-absolute path, not UNC/device/drive-relative"
        )

    parts = path.parts[1:]
    if not parts:
        raise WindowsPathContractError(f"{label} must name a directory below the drive root")
    for part in parts:
        validate_windows_component(part, label=label)

    normalized = str(PureWindowsPath(path.drive.upper() + "\\", *parts))
    if len(normalized) > WINDOWS_EXTENDED_PATH_LIMIT:
        raise WindowsPathContractError(
            f"{label} exceeds the Windows extended path limit"
        )
    return normalized


def validate_relative_windows_path(value: str, *, label: str = "relative path") -> str:
    """Return a safe relative Windows path suitable for joining under a root."""

    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value or value != value.strip():
        raise WindowsPathContractError(f"{label} is empty or padded with whitespace")

    path = PureWindowsPath(value)
    if path.drive or path.root:
        raise WindowsPathContractError(f"{label} must not override its owning root")
    if not path.parts or any(part == ".." for part in path.parts):
        raise WindowsPathContractError(f"{label} contains traversal")
    for part in path.parts:
        validate_windows_component(part, label=label)
    return str(path)


@dataclass(frozen=True, slots=True)
class StorageEvidence:
    medium: StorageMedium = StorageMedium.PENDING_PC
    evidence_ref: str | None = None
    observed_on_physical_pc: bool = False

    def __post_init__(self) -> None:
        medium = StorageMedium(self.medium)
        object.__setattr__(self, "medium", medium)

        if medium is StorageMedium.PENDING_PC:
            if self.evidence_ref is not None or self.observed_on_physical_pc:
                raise ValueError("PENDING_PC storage cannot carry observed evidence")
            return

        if not self.observed_on_physical_pc:
            raise ValueError("SSD/HDD/UNKNOWN classification requires physical-PC evidence")
        if not isinstance(self.evidence_ref, str) or not self.evidence_ref.strip():
            raise ValueError("observed storage classification requires an evidence reference")
        if "\n" in self.evidence_ref or "\r" in self.evidence_ref:
            raise ValueError("storage evidence reference must be one line")

    @classmethod
    def observed(cls, medium: StorageMedium, *, evidence_ref: str) -> StorageEvidence:
        if StorageMedium(medium) is StorageMedium.PENDING_PC:
            raise ValueError("an observed storage medium cannot be PENDING_PC")
        return cls(
            medium=medium,
            evidence_ref=evidence_ref,
            observed_on_physical_pc=True,
        )


@dataclass(frozen=True, slots=True)
class WindowsRootBinding:
    role: WindowsPathRole
    path: str
    storage: StorageEvidence = field(default_factory=StorageEvidence)

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", WindowsPathRole(self.role))
        object.__setattr__(
            self,
            "path",
            validate_absolute_windows_path(self.path, label=f"{self.role.value} root"),
        )
        if not isinstance(self.storage, StorageEvidence):
            raise TypeError("storage must be StorageEvidence")

    @property
    def drive(self) -> str:
        return PureWindowsPath(self.path).drive.upper()

    @property
    def requires_long_path_support(self) -> bool:
        return len(self.path) >= WINDOWS_LEGACY_PATH_LIMIT

    def join(self, relative_path: str) -> str:
        relative = validate_relative_windows_path(relative_path)
        joined = str(PureWindowsPath(self.path) / PureWindowsPath(relative))
        if len(joined) > WINDOWS_EXTENDED_PATH_LIMIT:
            raise WindowsPathContractError("joined path exceeds the Windows extended path limit")
        return joined

    def with_observed_storage(
        self,
        medium: StorageMedium,
        *,
        evidence_ref: str,
    ) -> WindowsRootBinding:
        return replace(
            self,
            storage=StorageEvidence.observed(medium, evidence_ref=evidence_ref),
        )


@dataclass(frozen=True, slots=True)
class CentinelaWindowsPathContract:
    repository: WindowsRootBinding
    media_library: WindowsRootBinding

    def __post_init__(self) -> None:
        if self.repository.role is not WindowsPathRole.REPOSITORY:
            raise ValueError("repository binding has the wrong role")
        if self.media_library.role is not WindowsPathRole.MEDIA_LIBRARY:
            raise ValueError("media-library binding has the wrong role")

    @classmethod
    def canonical_pending_pc(cls) -> CentinelaWindowsPathContract:
        return cls(
            repository=WindowsRootBinding(
                role=WindowsPathRole.REPOSITORY,
                path=CANONICAL_REPOSITORY_ROOT,
            ),
            media_library=WindowsRootBinding(
                role=WindowsPathRole.MEDIA_LIBRARY,
                path=CANONICAL_MEDIA_ROOT,
            ),
        )
