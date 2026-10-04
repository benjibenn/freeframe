"""Which stored thumbnail key is an image a list may show."""
from typing import Optional

from ..models.asset import AssetType


def thumbnail_key(asset_type, s3_key_thumbnail: Optional[str]) -> Optional[str]:
    """The thumbnail key, unless it is not an image.

    Audio stores waveform JSON in s3_key_thumbnail. Presigning that as an
    <img> gives a broken picture, so audio has no thumbnail here, the same as
    routers/assets.py.
    """
    if asset_type == AssetType.audio:
        return None
    return s3_key_thumbnail or None
