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

    # Generative visual capabilities are deliberately finer-grained than
    # IMAGE/VIDEO. A provider declaring VIDEO does not automatically gain
    # text-to-video or image-to-video execution semantics.
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_VIDEO = "image_to_video"
    TEXT_TO_VIDEO = "text_to_video"
    UPSCALE = "upscale"
    LOCAL_INFERENCE = "local_inference"

    LICENSE_METADATA = "license_metadata"
    PROGRESS = "progress"
    CANCEL = "cancel"
