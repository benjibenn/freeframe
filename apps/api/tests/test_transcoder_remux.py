"""Tests for the H.264 remux fast-path in the FFmpeg transcoder.

Why this matters: re-encoding a full libx264 ladder for every upload is the
single most expensive operation in the app (minutes of CPU per clip). When the
source is *already* H.264, we can copy the video stream untouched into a
single-rendition HLS output in seconds. These tests pin the decision logic and
the command shape so the fast path can't silently regress into a full re-encode
(or vice-versa) when someone edits the ffmpeg wiring.
"""
import json

from packages.transcoder.ffmpeg_transcoder import FFmpegTranscoder


# --- probe parsing: decides whether the fast path is even eligible ---

def test_parse_probe_detects_h264_and_audio():
    probe = json.dumps({"streams": [
        {"codec_type": "video", "codec_name": "h264"},
        {"codec_type": "audio", "codec_name": "aac"},
    ]})
    assert FFmpegTranscoder._parse_probe(probe) == ("h264", True)


def test_parse_probe_reports_missing_audio():
    # A video with no audio track must be handled without assuming a:0 exists.
    probe = json.dumps({"streams": [
        {"codec_type": "video", "codec_name": "vp9"},
    ]})
    assert FFmpegTranscoder._parse_probe(probe) == ("vp9", False)


def test_parse_probe_malformed_falls_back_safely():
    # A garbage/empty probe must not crash and must NOT report h264 — otherwise
    # we'd trigger a copy on an unknown codec and produce a broken stream.
    assert FFmpegTranscoder._parse_probe("not json at all") == (None, False)


# --- command building: fast path vs full ladder ---

def test_h264_source_is_remuxed_not_reencoded():
    cmd, variant_dirs = FFmpegTranscoder._build_ffmpeg_cmd(
        "http://input", ["1080p", "720p", "360p"], "/tmp/hls",
        video_codec="h264", has_audio=True,
    )
    # Video stream copied verbatim — the whole point of the fast path.
    assert "-c:v" in cmd and cmd[cmd.index("-c:v") + 1] == "copy"
    assert "libx264" not in cmd
    # Audio re-encoded to AAC for uniform mpegts/HLS compatibility.
    assert "-c:a" in cmd and cmd[cmd.index("-c:a") + 1] == "aac"
    # Single rendition; player still gets a master playlist.
    assert variant_dirs == ["source"]
    assert "-master_pl_name" in cmd and cmd[cmd.index("-master_pl_name") + 1] == "master.m3u8"


def test_h264_source_without_audio_omits_audio_mapping():
    cmd, variant_dirs = FFmpegTranscoder._build_ffmpeg_cmd(
        "http://input", [], "/tmp/hls", video_codec="h264", has_audio=False,
    )
    assert "-c:a" not in cmd
    assert "v:0,name:source" in cmd  # var_stream_map has no audio track
    assert variant_dirs == ["source"]


def test_non_h264_source_uses_full_libx264_ladder():
    cmd, variant_dirs = FFmpegTranscoder._build_ffmpeg_cmd(
        "http://input", ["1080p", "720p", "360p"], "/tmp/hls",
        video_codec="vp9", has_audio=True,
    )
    # Unknown codec must fall back to a real re-encode of all three rungs.
    assert cmd.count("libx264") == 3
    assert "-filter_complex" in cmd
    assert variant_dirs == ["1080p", "720p", "360p"]
