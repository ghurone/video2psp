"""
video2psp - A video converter for PSP format
Converts video files to PSP-compatible MP4 format with user-selected tracks.
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

PRESETS = [
    "ultrafast", "superfast", "veryfast", "faster",
    "fast", "medium", "slow", "slower", "veryslow",
]
DEFAULT_PRESET = "medium"
DEFAULT_CRF = 23

PSP_WIDTH = 480
PSP_HEIGHT = 272

# Bitmap subtitle codecs can't be rendered by the `subtitles` (libass) filter.
IMAGE_SUBTITLE_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}


class VideoConverterError(Exception):
    """Custom exception for video converter errors."""


@dataclass
class Track:
    """A single stream of a given type (video, audio or subtitle)."""
    kind: str
    index: int  # index among streams of the same kind (used in -map 0:v:N etc.)
    codec_name: str = "unknown"
    language: str = "und"
    title: str = ""
    width: int = 0
    height: int = 0
    fps: str = "unknown"
    channels: int = 0
    sample_rate: str = "unknown"

    @property
    def is_image_subtitle(self) -> bool:
        return self.kind == "subtitle" and self.codec_name in IMAGE_SUBTITLE_CODECS

    def label(self) -> str:
        """Human-readable one-line description, shared by CLI and GUI."""
        label = f"[{self.index}] {self.codec_name}"
        if self.language and self.language != "und":
            label += f", {self.language}"
        if self.title:
            label += f', "{self.title}"'
        if self.kind == "video":
            label += f", {self.width}x{self.height}, {self.fps}fps"
        elif self.kind == "audio":
            label += f", {self.channels}ch, {self.sample_rate}Hz"
        elif self.is_image_subtitle:
            label += " (image-based, not supported)"
        return label


@dataclass
class MediaInfo:
    """Tracks and duration of a media file, obtained from a single ffprobe call."""
    video: list[Track] = field(default_factory=list)
    audio: list[Track] = field(default_factory=list)
    subtitle: list[Track] = field(default_factory=list)
    duration: float = 0.0


def _parse_fps(rate: str) -> str:
    try:
        num, den = map(int, rate.split("/"))
        return f"{num / den:.2f}"
    except (ValueError, ZeroDivisionError):
        return "unknown"


def parse_streams(data: dict) -> MediaInfo:
    """Build a MediaInfo from ffprobe's JSON output (-show_streams -show_format)."""
    info = MediaInfo()
    by_kind = {"video": info.video, "audio": info.audio, "subtitle": info.subtitle}

    for stream in data.get("streams", []):
        tracks = by_kind.get(stream.get("codec_type"))
        if tracks is None:
            continue
        tags = stream.get("tags", {})
        tracks.append(Track(
            kind=stream["codec_type"],
            index=len(tracks),
            codec_name=stream.get("codec_name", "unknown"),
            language=tags.get("language", "und"),
            title=tags.get("title", ""),
            width=stream.get("width", 0),
            height=stream.get("height", 0),
            fps=_parse_fps(stream.get("r_frame_rate", "0/0")),
            channels=stream.get("channels", 0),
            sample_rate=stream.get("sample_rate", "unknown"),
        ))

    try:
        info.duration = float(data.get("format", {}).get("duration") or 0.0)
    except ValueError:
        info.duration = 0.0
    return info


def escape_filter_value(value: str) -> str:
    """
    Escape a value to be used as a filter option inside a filtergraph (-vf).

    FFmpeg applies two levels of unescaping: first the filtergraph parser,
    then the filter's option parser. Quoting with '...' can't represent an
    apostrophe, so we escape everything instead (see "Notes on filtergraph
    escaping" in the ffmpeg-filters docs).
    """
    for ch in "\\':":
        value = value.replace(ch, "\\" + ch)
    for ch in "\\'[],;":
        value = value.replace(ch, "\\" + ch)
    return value


def default_output_path(input_file: str | Path) -> Path:
    """Input path with .mp4 extension, never the input file itself."""
    input_path = Path(input_file)
    output = input_path.with_suffix(".mp4")
    if output.resolve() == input_path.resolve():
        output = input_path.with_name(f"{input_path.stem}_psp.mp4")
    return output


class PSPVideoConverter:
    """PSP Video Converter class to handle video conversion operations."""

    def probe(self, input_file: str) -> MediaInfo:
        """
        Returns tracks and duration of the file using a single ffprobe call.

        Raises:
            VideoConverterError: If ffprobe fails or file is not found
        """
        if not Path(input_file).exists():
            raise VideoConverterError(f"Input file does not exist: {input_file}")

        probe_cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            input_file,
        ]

        try:
            result = subprocess.run(
                probe_cmd, capture_output=True, text=True, check=True, timeout=30
            )
            return parse_streams(json.loads(result.stdout))
        except FileNotFoundError:
            raise VideoConverterError(
                "ffprobe not found. Please install FFmpeg and ensure it's in your PATH."
            )
        except subprocess.CalledProcessError as e:
            raise VideoConverterError(
                f"ffprobe failed with exit code {e.returncode}.\nError: {e.stderr}"
            )
        except subprocess.TimeoutExpired:
            raise VideoConverterError("ffprobe timed out after 30 seconds.")
        except json.JSONDecodeError:
            raise VideoConverterError("Could not parse ffprobe output as JSON.")

    def choose_track_interactively(self, tracks: list[Track], track_type: str) -> int | None:
        """
        Asks the user which track they want to use.

        Returns:
            Chosen track index or None for subtitles if user declines
        """
        if not tracks:
            return None

        if len(tracks) == 1 and track_type != "subtitle":
            print(f"Only 1 {track_type.upper()} track detected. Selecting automatically.")
            return tracks[0].index

        print(f"\nAvailable {track_type.upper()} tracks ({len(tracks)}):")
        for track in tracks:
            print(f"  {track.label()}")

        if track_type == "subtitle":
            print("Enter -1 or leave blank to choose NO subtitles.")

        max_idx = len(tracks) - 1
        prompt = f"Select the {track_type} track index (0-{max_idx}"
        if track_type == "subtitle":
            prompt += ", or -1 for none"
        prompt += "): "

        while True:
            user_input = input(prompt).strip()

            if track_type == "subtitle" and user_input in ("", "-1"):
                return None

            try:
                idx = int(user_input)
            except ValueError:
                print("Invalid input. Please enter a number.")
                continue
            if not 0 <= idx <= max_idx:
                print(f"Value out of range (0-{max_idx}). Try again.")
            elif tracks[idx].is_image_subtitle:
                print("Image-based subtitles can't be burned. Pick another track or -1.")
            else:
                return idx

    def build_ffmpeg_command(
        self,
        input_file: str,
        output_file: str,
        video_index: int,
        audio_index: int,
        subtitle_index: int | None = None,
        external_subs: str | None = None,
        volume_factor: float = 1.0,
        preset: str = DEFAULT_PRESET,
        crf: int = DEFAULT_CRF,
        progress: bool = False,
    ) -> list[str]:
        """
        Generates an ffmpeg command for PSP conversion.

        Args:
            input_file: Input video file path
            output_file: Output video file path
            video_index: Index of video track to use
            audio_index: Index of audio track to use
            subtitle_index: Index of subtitle track to burn (optional)
            external_subs: Path to external subtitle file (optional)
            volume_factor: Volume multiplication factor (default: 1.0)
            preset: libx264 encoding preset, trades speed for compression (default: medium)
            crf: Constant Rate Factor for quality-based encoding, lower is higher quality
                and larger file size (default: 23). -maxrate/-bufsize still cap the peak
                bitrate so the PSP's decoder buffer requirements are respected.
            progress: Emit machine-readable progress on stdout (-progress pipe:1)
                instead of the human-readable stats line.

        Returns:
            List of command arguments for ffmpeg
        """
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            *(["-progress", "pipe:1", "-nostats"] if progress else ["-stats"]),
            "-y",
            "-i", input_file,
            "-map", f"0:v:{video_index}",
            "-map", f"0:a:{audio_index}",
            "-vf", self._build_video_filter(input_file, subtitle_index, external_subs),
            "-c:v", "libx264",
            "-preset", preset,
            "-profile:v", "baseline",
            "-level:v", "3.0",
            "-pix_fmt", "yuv420p",
            "-crf", str(crf),
            "-maxrate", "768k",
            "-bufsize", "2000k",
            "-r", "30000/1001",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ac", "2",
            "-ar", "48000",
        ]

        if volume_factor != 1.0:
            cmd.extend(["-af", f"volume={volume_factor}"])

        cmd.extend(["-movflags", "+faststart", output_file])
        return cmd

    def _build_video_filter(
        self,
        input_file: str,
        subtitle_index: int | None,
        external_subs: str | None,
    ) -> str:
        """Build the -vf filter string, including subtitle burn-in if requested."""
        filters = [
            # Normalize anamorphic sources (e.g. DVDs) to square pixels first
            "scale=trunc(iw*sar/2)*2:ih",
            "setsar=1",
            f"scale={PSP_WIDTH}:{PSP_HEIGHT}:force_original_aspect_ratio=decrease:force_divisible_by=2",
            f"pad={PSP_WIDTH}:{PSP_HEIGHT}:(ow-iw)/2:(oh-ih)/2",
        ]

        if external_subs:
            if not Path(external_subs).exists():
                raise VideoConverterError(f"External subtitle file not found: {external_subs}")
            filters.append(f"subtitles=filename={escape_filter_value(external_subs)}")
        elif subtitle_index is not None:
            filters.append(
                f"subtitles=filename={escape_filter_value(input_file)}:si={subtitle_index}"
            )

        return ",".join(filters)

    def convert_video(
        self,
        input_file: str,
        output_file: str | None = None,
        video_track: int | None = None,
        audio_track: int | None = None,
        subtitle_track: int | None = None,
        external_subs: str | None = None,
        volume_factor: float = 1.0,
        preset: str = DEFAULT_PRESET,
        crf: int = DEFAULT_CRF,
    ) -> None:
        """
        Main conversion method.

        Args:
            input_file: Path to input video file
            output_file: Path to output file (optional)
            video_track: Video track index (optional, will prompt if not provided)
            audio_track: Audio track index (optional, will prompt if not provided)
            subtitle_track: Subtitle track index (optional)
            external_subs: External subtitle file path (optional)
            volume_factor: Volume multiplication factor (default: 1.0)
            preset: libx264 encoding preset, trades speed for compression (default: medium)
            crf: Constant Rate Factor for quality-based encoding (default: 23)
        """
        input_path = Path(input_file)
        if not input_path.exists():
            raise VideoConverterError(f"Input file does not exist: {input_file}")

        output_path = Path(output_file) if output_file else default_output_path(input_path)
        if output_path.resolve() == input_path.resolve():
            raise VideoConverterError("Output file must be different from the input file.")

        if output_path.exists():
            answer = input(f"Output file '{output_path}' already exists. Overwrite? [y/N]: ").strip().lower()
            if answer not in ("y", "yes"):
                raise VideoConverterError("Conversion cancelled: output file already exists.")

        print("Analyzing input file...")
        info = self.probe(input_file)

        if not info.video:
            raise VideoConverterError("No video tracks found in the input file.")
        if not info.audio:
            raise VideoConverterError("No audio tracks found in the input file.")

        video_index = self._select_track(info.video, video_track, "video")
        audio_index = self._select_track(info.audio, audio_track, "audio")

        subtitle_index = None
        if external_subs:
            print(f"Using external subtitles: {external_subs}")
        elif info.subtitle:
            if subtitle_track is None:
                subtitle_index = self.choose_track_interactively(info.subtitle, "subtitle")
            elif not 0 <= subtitle_track < len(info.subtitle):
                print(f"Warning: Invalid subtitle index {subtitle_track}. No subtitles will be used.")
            elif info.subtitle[subtitle_track].is_image_subtitle:
                raise VideoConverterError(
                    f"Subtitle track {subtitle_track} is image-based "
                    f"({info.subtitle[subtitle_track].codec_name}) and can't be burned. "
                    "Convert it to SRT and use --external-subs."
                )
            else:
                subtitle_index = subtitle_track

        if volume_factor != 1.0:
            print(f"Audio volume will be adjusted by factor: {volume_factor}")

        cmd = self.build_ffmpeg_command(
            input_file=input_file,
            output_file=str(output_path),
            video_index=video_index,
            audio_index=audio_index,
            subtitle_index=subtitle_index,
            external_subs=external_subs,
            volume_factor=volume_factor,
            preset=preset,
            crf=crf,
        )

        print("\nStarting conversion...")
        print(f"Output: {output_path}")

        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError:
            raise VideoConverterError(
                "ffmpeg not found. Please install FFmpeg and ensure it's in your PATH."
            )
        except subprocess.CalledProcessError as e:
            raise VideoConverterError(f"FFmpeg conversion failed with exit code {e.returncode}")
        print("\n✓ Conversion completed successfully!")
        print(f"Output file: {output_path}")

    def _select_track(self, tracks: list[Track], specified_index: int | None, track_type: str) -> int:
        """Select a track either from user specification or interactive choice."""
        if specified_index is not None:
            if 0 <= specified_index < len(tracks):
                return specified_index
            raise VideoConverterError(
                f"Invalid {track_type} track index {specified_index}. "
                f"Available range: 0-{len(tracks) - 1}"
            )

        selected = self.choose_track_interactively(tracks, track_type)
        if selected is None:
            raise VideoConverterError(f"No {track_type} track available to select.")
        return selected


def print_title() -> None:
    """Print application title and info."""
    print("+" + "-" * 50 + "+")
    print("|    video2psp - Video Converter for PSP Format    |")
    print("+" + "-" * 50 + "+")
    print("                                     by Erick Ghuron", end="\n\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert video files to PSP-compatible MP4 format with user-selected tracks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.ext
  %(prog)s input.ext output.mp4 --video-track 0 --audio-track 1
  %(prog)s input.ext --external-subs subtitles.srt
  %(prog)s input.ext --volume 1.5
  %(prog)s input.ext --volume 0.8 --audio-track 1
  %(prog)s input.ext --preset veryfast
  %(prog)s input.ext --crf 26
  %(prog)s --gui
        """
    )

    parser.add_argument(
        "-g", "--gui",
        action="store_true",
        help="Open the graphical interface"
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        help="Input video file path"
    )
    parser.add_argument(
        "output_file",
        nargs="?",
        help="Output file path (default: input filename with .mp4 extension)"
    )
    parser.add_argument(
        "--video-track",
        type=int,
        help="Video track index to use (0, 1, 2, ...)"
    )
    parser.add_argument(
        "--audio-track",
        type=int,
        help="Audio track index to use (0, 1, 2, ...)"
    )
    parser.add_argument(
        "--subtitle-track",
        type=int,
        help="Subtitle track index to burn into video (0, 1, 2, ...)"
    )
    parser.add_argument(
        "--external-subs",
        help="External subtitle file to burn into video (takes priority over embedded subtitles)"
    )
    parser.add_argument(
        "--volume",
        type=float,
        default=1.0,
        help="Volume multiplication factor (1.0 = original, 1.5 = 150%%, 0.5 = 50%%, default: 1.0)"
    )
    parser.add_argument(
        "--preset",
        choices=PRESETS,
        default=DEFAULT_PRESET,
        help="libx264 encoding preset, trades encoding speed for compression efficiency (default: medium)"
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=DEFAULT_CRF,
        help="Constant Rate Factor (0-51): lower means higher quality and larger file size, "
             "higher means smaller file and lower quality (default: 23)"
    )
    return parser


def main() -> None:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.gui:
        from video2psp.gui import launch_gui
        launch_gui()
        return

    if not args.input_file:
        parser.error("the following arguments are required: input_file")
    if args.volume <= 0:
        parser.error("--volume must be greater than 0")
    if not 0 <= args.crf <= 51:
        parser.error("--crf must be between 0 and 51")

    print_title()

    try:
        converter = PSPVideoConverter()
        converter.convert_video(
            input_file=args.input_file,
            output_file=args.output_file,
            video_track=args.video_track,
            audio_track=args.audio_track,
            subtitle_track=args.subtitle_track,
            external_subs=args.external_subs,
            volume_factor=args.volume,
            preset=args.preset,
            crf=args.crf
        )

    except VideoConverterError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
