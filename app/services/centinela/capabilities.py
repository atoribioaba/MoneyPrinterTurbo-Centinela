"""Provider capability definitions for Centinela Edition."""

from enum import Enum


class ProviderKind(str, Enum):
    """High-level provider execution semantics."""

    SEARCHABLE = "searchable"
    GENERATIVE = "generative"
    LOCAL = "local"


class ProviderCapability(str, Enum):
    """Capabilities that a material or generation provider can expose."""

    SEARCH = "search"
    DOWNLOAD = "download"
    GENERATE = "generate"

    LOCAL = "local"
    REMOTE = "remote"

    VIDEO = "video"
    IMAGE = "image"
    AUDIO = "audio"

    LICENSE_METADATA = "license_metadata"
    PROGRESS = "progress"
    CANCEL = "cancel"
