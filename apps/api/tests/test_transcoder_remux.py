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


def test_poster_thumbnail_grabs_first_frame_without_fps_sampler():
    # Two ffmpeg >=7 regressions killed every process_asset task (2026-07):
    # 1. fps=0.1 emits ZERO frames for clips shorter than its 10s interval,
    #    so the poster must take the first frame directly, and
    # 2. the mjpeg encoder hard-errors on limited-range YUV (what nearly all
    #    camera video uses) and can't take 10-bit HEVC — so the chain must
    #    convert to full-range 8-bit (yuvj420p) before encoding.
    cmd = FFmpegTranscoder._build_thumb_cmd(
        "http://input", "/tmp/thumb_%04d.jpg", single_frame=True,
    )
    vf = cmd[cmd.index("-vf") + 1]
    assert "fps=" not in vf
    assert "format=yuvj420p" in vf
    assert cmd[cmd.index("-frames:v") + 1] == "1"


def test_thumbnail_strip_samples_at_10s_with_full_range_conversion():
    # The scrub strip wants one frame per 10s for the whole clip (no -frames:v
    # cap) but still needs the yuvj420p conversion for the mjpeg encoder.
    cmd = FFmpegTranscoder._build_thumb_cmd("http://input", "/tmp/thumb_%04d.jpg")
    assert "-frames:v" not in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "fps=0.1" in vf
    assert "format=yuvj420p" in vf


def test_non_h264_source_uses_full_libx264_ladder():
    cmd, variant_dirs = FFmpegTranscoder._build_ffmpeg_cmd(
        "http://input", ["1080p", "720p", "360p"], "/tmp/hls",
        video_codec="vp9", has_audio=True,
    )
    # Unknown codec must fall back to a real re-encode of all three rungs.
    assert cmd.count("libx264") == 3
    assert "-filter_complex" in cmd
    assert variant_dirs == ["1080p", "720p", "360p"]


def test_ladder_without_audio_omits_audio_mapping():
    # An unconditional `-map a:0` aborts ffmpeg with "Stream map 'a:0'
    # matches no streams" on audio-less sources (e.g. screen recordings),
    # failing the whole transcode. The remux path already respects
    # has_audio; the ladder must too.
    cmd, variant_dirs = FFmpegTranscoder._build_ffmpeg_cmd(
        "http://input", ["1080p", "720p", "360p"], "/tmp/hls",
        video_codec="hevc", has_audio=False,
    )
    assert "a:0" not in cmd
    vsm = cmd[cmd.index("-var_stream_map") + 1]
    assert vsm == "v:0 v:1 v:2"
    assert variant_dirs == ["1080p", "720p", "360p"]
