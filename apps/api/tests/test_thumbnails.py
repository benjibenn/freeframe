"""Audio keeps waveform JSON in s3_key_thumbnail. Presigning it as an image gave
the board a broken picture for every audio file (assets.py already skips it)."""
from apps.api.models.asset import AssetType
from apps.api.services.thumbnails import thumbnail_key


def test_audio_has_no_image_thumbnail():
    assert thumbnail_key(AssetType.audio, "waveforms/a.json") is None


def test_images_and_videos_keep_theirs():
    assert thumbnail_key(AssetType.video, "thumbs/v.jpg") == "thumbs/v.jpg"
    assert thumbnail_key(AssetType.image, "thumbs/i.jpg") == "thumbs/i.jpg"


def test_blank_key_is_none():
    assert thumbnail_key(AssetType.image, "") is None
    assert thumbnail_key(AssetType.image, None) is None
