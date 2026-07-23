import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
import boto3
from botocore.config import Config
from .base import BaseTranscoder, TranscodeJob, TranscodeResult, VideoMetadata


class FFmpegTranscoder(BaseTranscoder):
    def __init__(self, s3_client, bucket: str, s3_endpoint: str = None):
        self.s3 = s3_client
        self.bucket = bucket
        self.s3_endpoint = s3_endpoint
    
    def _get_presigned_url(self, s3_key: str, expires_in: int = 7200) -> str:
        """Generate a presigned URL for streaming input to FFmpeg."""
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": s3_key},
            ExpiresIn=expires_in,
        )

    async def get_video_metadata(self, s3_key: str) -> VideoMetadata:
        """Get video metadata using streaming (no full download)."""
        input_url = self._get_presigned_url(s3_key)
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-select_streams", "v:0", input_url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        fps_parts = stream.get("r_frame_rate", "30/1").split("/")
        fps = float(fps_parts[0]) / float(fps_parts[1])
        return VideoMetadata(
            duration_seconds=float(stream.get("duration", 0)),
            width=int(stream.get("width", 0)),
            height=int(stream.get("height", 0)),
            fps=fps,
        )

    async def generate_thumbnails(self, s3_key: str, count: int) -> list[str]:
        """Generate thumbnails at 1 per 10 seconds using streaming input."""
        input_url = self._get_presigned_url(s3_key)
        thumb_dir = tempfile.mkdtemp()
        try:
            cmd = self._build_thumb_cmd(input_url, f"{thumb_dir}/thumb_%04d.jpg")
            subprocess.run(cmd, capture_output=True, check=True, timeout=600)
            return [str(p) for p in sorted(Path(thumb_dir).glob("thumb_*.jpg"))]
        finally:
            shutil.rmtree(thumb_dir, ignore_errors=True)

    async def generate_waveform(self, s3_key: str) -> dict:
        """Generate waveform data for audio visualization using streaming."""
        input_url = self._get_presigned_url(s3_key)
        # Simplified waveform: just return peak data (full waveform extraction is complex)
        return {"samples": [], "peak": 1.0, "source": s3_key}

    async def transcode(self, job: TranscodeJob) -> TranscodeResult:
        """
        Transcode video using streaming input from S3.
        FFmpeg reads directly from presigned URL - no full download needed.
        Only output files are written to disk, reducing disk usage by ~2/3.
        """
        work_dir = Path(tempfile.mkdtemp(prefix=f"transcode_{job.version_id}_"))
        
        # Generate presigned URL for streaming input (2 hour expiry for large files)
        input_url = self._get_presigned_url(job.input_s3_key, expires_in=7200)

        try:
            # 1. Probe the source. Keep ALL streams (not just v:0) so we can read
            #    the video codec and detect whether an audio track exists — both
            #    drive the remux fast-path decision below.
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", input_url],
                capture_output=True, text=True, timeout=120,
            )
            video_codec, has_audio = self._parse_probe(probe.stdout)

            hls_dir = work_dir / "hls"
            hls_dir.mkdir()

            # 2. Build the ffmpeg command. An already-H.264 source is copied
            #    verbatim into a single HLS rendition (seconds, not minutes);
            #    anything else re-encodes the full libx264 quality ladder.
            ffmpeg_cmd, variant_dirs = self._build_ffmpeg_cmd(
                input_url, job.qualities, hls_dir, video_codec, has_audio
            )
            for name in variant_dirs:
                (hls_dir / name).mkdir(exist_ok=True)

            # Timeout scales with expected duration - 4 hours for very large files
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True, timeout=14400)

            # 4. Upload HLS files to S3
            uploaded_keys = []
            for f in hls_dir.rglob("*"):
                if f.is_file():
                    relative = f.relative_to(hls_dir)
                    s3_key = f"{job.output_s3_prefix}/{relative}"
                    content_type, cache_control = self._get_content_type(f.name)
                    self.s3.upload_file(
                        str(f), self.bucket, s3_key,
                        ExtraArgs={"ContentType": content_type, "CacheControl": cache_control},
                    )
                    uploaded_keys.append(s3_key)

            # 5. Generate and upload thumbnail (using streaming URL)
            thumb_path = work_dir / "thumb_0001.jpg"
            thumb_cmd = self._build_thumb_cmd(
                input_url, work_dir / "thumb_%04d.jpg", single_frame=True,
            )
            subprocess.run(thumb_cmd, check=True, capture_output=True)
            thumbnail_key = f"{job.output_s3_prefix}/thumbnail.jpg"
            if thumb_path.exists():
                self.s3.upload_file(
                    str(thumb_path), self.bucket, thumbnail_key,
                    ExtraArgs={"ContentType": "image/jpeg", "CacheControl": "max-age=86400"},
                )

            return TranscodeResult(
                success=True,
                hls_prefix=job.output_s3_prefix,
                thumbnail_keys=[thumbnail_key],
            )

        except subprocess.CalledProcessError as e:
            # str(e) is just "returned non-zero exit status N" — the actual reason is in
            # ffmpeg's stderr (captured but otherwise discarded). Surface its tail so
            # failures are diagnosable instead of an opaque exit code.
            stderr = e.stderr
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", "replace")
            tail = " | ".join((stderr or "").strip().splitlines()[-15:])
            return TranscodeResult(success=False, error=f"{e}: {tail}" if tail else str(e))
        except Exception as e:
            return TranscodeResult(success=False, error=str(e))
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    @staticmethod
    def _build_thumb_cmd(input_url, out_pattern, single_frame=False):
        """Thumbnail extraction.

        format=yuvj420p forces full-range 8-bit before the mjpeg encoder:
        ffmpeg >=7 hard-errors on limited-range YUV (most camera video) and
        mjpeg cannot take 10-bit HEVC input at all.

        The poster thumbnail (single_frame) grabs the first frame directly —
        on ffmpeg >=7 the fps=0.1 sampler emits zero frames for clips shorter
        than its 10s interval, which fails the whole transcode task.
        """
        vf = "format=yuvj420p" if single_frame else "fps=0.1,format=yuvj420p"
        cmd = ["ffmpeg", "-y", "-i", str(input_url), "-vf", vf, "-q:v", "2"]
        if single_frame:
            cmd += ["-frames:v", "1"]
        cmd.append(str(out_pattern))
        return cmd

    QUALITY_MAP = {
        "1080p": ("1920:1080", 20),
        "720p": ("1280:720", 22),
        "360p": ("640:360", 26),
    }

    @staticmethod
    def _parse_probe(probe_json: str) -> tuple[Optional[str], bool]:
        """Extract (video_codec, has_audio) from ffprobe JSON.

        Returns (None, False) on any parse failure so callers fall back to the
        safe full re-encode path instead of remuxing an unknown/absent codec.
        """
        try:
            streams = json.loads(probe_json).get("streams", [])
        except (ValueError, TypeError, AttributeError):
            return None, False
        video_codec = None
        has_audio = False
        for s in streams:
            kind = s.get("codec_type")
            if kind == "video" and video_codec is None:
                video_codec = s.get("codec_name")
            elif kind == "audio":
                has_audio = True
        return video_codec, has_audio

    @classmethod
    def _build_ffmpeg_cmd(cls, input_url, qualities, hls_dir, video_codec, has_audio):
        """Return (ffmpeg_cmd, variant_dir_names).

        Fast path: an already-H.264 source is copied into a single HLS rendition.
        Otherwise the full libx264 ladder is re-encoded.
        """
        if video_codec == "h264":
            return cls._build_remux_cmd(input_url, hls_dir, has_audio), ["source"]
        return cls._build_ladder_cmd(input_url, qualities, hls_dir)

    @staticmethod
    def _build_remux_cmd(input_url, hls_dir, has_audio):
        """Single-rendition HLS by copying the H.264 video stream untouched.

        Audio is re-encoded to AAC (cheap) so the mpegts segments are uniformly
        playable regardless of the source's original audio codec.
        """
        hls_dir = Path(hls_dir)
        cmd = ["ffmpeg", "-y", "-i", str(input_url), "-c:v", "copy"]
        if has_audio:
            cmd += ["-c:a", "aac"]
        cmd += [
            "-f", "hls",
            "-hls_time", "2",
            "-hls_playlist_type", "vod",
            "-hls_flags", "independent_segments",
            "-hls_segment_type", "mpegts",
            "-master_pl_name", "master.m3u8",
            "-var_stream_map", "v:0,a:0,name:source" if has_audio else "v:0,name:source",
            "-hls_segment_filename", str(hls_dir / "%v" / "seg_%03d.ts"),
            str(hls_dir / "%v" / "playlist.m3u8"),
        ]
        return cmd

    @classmethod
    def _build_ladder_cmd(cls, input_url, qualities, hls_dir):
        """Full re-encode into a 1080/720/360 libx264 HLS ladder."""
        hls_dir = Path(hls_dir)
        qualities = [q for q in qualities if q in cls.QUALITY_MAP]

        # Use force_original_aspect_ratio=decrease to preserve aspect ratio,
        # then pad to even dimensions required by libx264.
        split_outputs = "".join(f"[v{i}]" for i in range(len(qualities)))
        filter_complex = f"[v:0]split={len(qualities)}{split_outputs};"
        filter_complex += ";".join(
            f"[v{i}]scale={cls.QUALITY_MAP[q][0]}:force_original_aspect_ratio=decrease,pad=ceil(iw/2)*2:ceil(ih/2)*2[{q}]"
            for i, q in enumerate(qualities)
        )

        cmd = [
            "ffmpeg", "-y",
            "-threads", "2",  # limit per-process threads so 3 concurrent workers share 4 cores
            "-i", str(input_url),
            "-filter_complex", filter_complex,
        ]
        for i, quality in enumerate(qualities):
            _, crf = cls.QUALITY_MAP[quality]
            cmd += [
                "-map", f"[{quality}]", "-map", "a:0",
                f"-c:v:{i}", "libx264", "-crf", str(crf), "-preset", "veryfast",
                "-force_key_frames", "expr:gte(t,n_forced*2)",
            ]
        cmd += [
            "-f", "hls",
            "-hls_time", "2",
            "-hls_playlist_type", "vod",
            "-hls_flags", "independent_segments",
            "-hls_segment_type", "mpegts",
            "-master_pl_name", "master.m3u8",
            "-var_stream_map", " ".join(f"v:{i},a:{i}" for i in range(len(qualities))),
            "-hls_segment_filename", str(hls_dir / "%v" / "seg_%03d.ts"),
            str(hls_dir / "%v" / "playlist.m3u8"),
        ]
        return cmd, qualities

    @staticmethod
    def _get_content_type(filename: str) -> tuple[str, str]:
        ext = Path(filename).suffix.lower()
        MAP = {
            ".m3u8": ("application/vnd.apple.mpegurl", "no-cache"),
            ".ts": ("video/mp2t", "max-age=31536000"),
            ".jpg": ("image/jpeg", "max-age=86400"),
        }
        return MAP.get(ext, ("application/octet-stream", "no-cache"))
