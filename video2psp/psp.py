"""
video2psp - A video converter for PSP format
Converts video files to PSP-compatible MP4 format with user-selected tracks.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class VideoConverterError(Exception):
    """Custom exception for video converter errors."""
    pass


class PSPVideoConverter:
    """PSP Video Converter class to handle video conversion operations."""
    
    def __init__(self):
        self.video_tracks = []
        self.audio_tracks = []
        self.subtitle_tracks = []
    
    def ffprobe_streams(self, input_file: str) -> List[Dict]:
        """
        Returns the information of all streams (video, audio, subtitles)
        in the file, using ffprobe in JSON format.
        
        Args:
            input_file: Path to the input video file
            
        Returns:
            List of stream dictionaries
            
        Raises:
            VideoConverterError: If ffprobe fails or file is not found
        """
        if not Path(input_file).exists():
            raise VideoConverterError(f"Input file does not exist: {input_file}")
        
        probe_cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            input_file
        ]
        
        try:
            result = subprocess.run(
                probe_cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30 
            )
            data = json.loads(result.stdout)
            return data.get('streams', [])
            
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
    
    def get_tracks_by_type(self, streams: List[Dict]) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """
        From the raw ffprobe data, returns 3 lists organized by type.
        
        Args:
            streams: List of stream dictionaries from ffprobe
            
        Returns:
            Tuple of (video_tracks, audio_tracks, subtitle_tracks)
        """
        video_tracks = []
        audio_tracks = []
        subtitle_tracks = []
        
        counters = {'video': 0, 'audio': 0, 'subtitle': 0}
        
        for stream in streams:
            codec_type = stream.get("codec_type")
            if codec_type not in counters:
                continue
                
            codec_name = stream.get("codec_name", "unknown")
            tags = stream.get("tags", {})
            language = tags.get("language", "und")
            title = tags.get("title", "")
            
            track_info = {
                "index_in_type": counters[codec_type],
                "codec_name": codec_name,
                "language": language,
                "title": title
            }
            
            if codec_type == "video":
                track_info.update({
                    "width": stream.get("width", 0),
                    "height": stream.get("height", 0),
                    "fps": self._get_fps(stream)
                })
                video_tracks.append(track_info)
            elif codec_type == "audio":
                track_info.update({
                    "channels": stream.get("channels", 0),
                    "sample_rate": stream.get("sample_rate", "unknown")
                })
                audio_tracks.append(track_info)
            elif codec_type == "subtitle":
                subtitle_tracks.append(track_info)
                
            counters[codec_type] += 1
        
        self.video_tracks = video_tracks
        self.audio_tracks = audio_tracks
        self.subtitle_tracks = subtitle_tracks
        
        return video_tracks, audio_tracks, subtitle_tracks
    
    def _get_fps(self, stream: Dict) -> str:
        """Extract FPS from stream data."""
        fps_str = stream.get("r_frame_rate", "0/0")
        try:
            if "/" in fps_str:
                num, den = map(int, fps_str.split("/"))
                if den != 0:
                    return f"{num/den:.2f}"
        except (ValueError, ZeroDivisionError):
            pass
        return "unknown"
    
    def choose_track_interactively(self, tracks: List[Dict], track_type: str) -> Optional[int]:
        """
        Asks the user which track they want to use.
        
        Args:
            tracks: List of available tracks
            track_type: Type of track ("video", "audio", "subtitle")
            
        Returns:
            Chosen track index or None for subtitles if user declines
        """
        if not tracks:
            return None
        
        if len(tracks) == 1 and track_type != 'subtitle':
            print(f"Only 1 {track_type.upper()} track detected. Selecting automatically.")
            return tracks[0]['index_in_type']
        
        print(f"\nAvailable {track_type.upper()} tracks ({len(tracks)}):")
        for track in tracks:
            idx = track['index_in_type']
            info = f"[{idx}] codec={track['codec_name']}, lang={track['language']}"
            
            if track['title']:
                info += f", title='{track['title']}'"
            
            if track_type == 'video':
                info += f", resolution={track['width']}x{track['height']}, fps={track['fps']}"
            elif track_type == 'audio':
                info += f", channels={track['channels']}, sample_rate={track['sample_rate']}"
                
            print(f"  {info}")
        
        if track_type == 'subtitle':
            print("Enter -1 or leave blank to choose NO subtitles.")
        
        max_idx = len(tracks) - 1
        while True:
            prompt = f"Select the {track_type} track index (0-{max_idx}"
            if track_type == 'subtitle':
                prompt += ", or -1 for none"
            prompt += "): "
            
            user_input = input(prompt).strip()
            
            if track_type == 'subtitle' and user_input in ('', '-1'):
                return None
            
            try:
                idx = int(user_input)
                if 0 <= idx <= max_idx:
                    return idx
                else:
                    print(f"Value out of range (0-{max_idx}). Try again.")
            except ValueError:
                print("Invalid input. Please enter a number.")
    
    def build_ffmpeg_command(
        self,
        input_file: str,
        output_file: str,
        video_index: int,
        audio_index: int,
        subtitle_index: Optional[int] = None,
        external_subs: Optional[str] = None
    ) -> List[str]:
        """
        Generates an ffmpeg command for PSP conversion.
        
        Args:
            input_file: Input video file path
            output_file: Output video file path
            video_index: Index of video track to use
            audio_index: Index of audio track to use
            subtitle_index: Index of subtitle track to burn (optional)
            external_subs: Path to external subtitle file (optional)
            
        Returns:
            List of command arguments for ffmpeg
        """
        cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            '-stats',
            '-y',  
            '-i', input_file
        ]
        
        cmd.extend(['-map', f'0:v:{video_index}'])
        cmd.extend(['-map', f'0:a:{audio_index}'])

        vf_filter = "scale=480:-2"  
        
        if external_subs:
            if not Path(external_subs).exists():
                raise VideoConverterError(f"External subtitle file not found: {external_subs}")
            ext_sub_escaped = self._escape_filter_string(external_subs)
            vf_filter += f",subtitles='{ext_sub_escaped}'"
        elif subtitle_index is not None:
            input_escaped = self._escape_filter_string(input_file)
            vf_filter += f",subtitles='{input_escaped}:si={subtitle_index}'"
        
        cmd.extend([
            '-vf', vf_filter,
            '-c:v', 'libx264',
            '-profile:v', 'baseline',
            '-level:v', '3.0',
            '-b:v', '768k',
            '-maxrate', '768k',
            '-bufsize', '2000k',
            '-r', '29.97',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ac', '2', 
            '-movflags', '+faststart', 
            output_file
        ])
        
        return cmd
    
    def _escape_filter_string(self, path: str) -> str:
        """Escape special characters for FFmpeg filter strings."""
        return path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    
    def convert_video(
        self,
        input_file: str,
        output_file: Optional[str] = None,
        video_track: Optional[int] = None,
        audio_track: Optional[int] = None,
        subtitle_track: Optional[int] = None,
        external_subs: Optional[str] = None
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
        """
        input_path = Path(input_file)
        if not input_path.exists():
            raise VideoConverterError(f"Input file does not exist: {input_file}")

        if not output_file:
            output_file = str(input_path.with_suffix('.mp4'))
        
        print("Analyzing input file...")
        streams = self.ffprobe_streams(input_file)
        video_tracks, audio_tracks, subtitle_tracks = self.get_tracks_by_type(streams)
        
        if not video_tracks:
            raise VideoConverterError("No video tracks found in the input file.")
        if not audio_tracks:
            raise VideoConverterError("No audio tracks found in the input file.")
        
        video_index = self._select_track(video_tracks, video_track, "video")
        audio_index = self._select_track(audio_tracks, audio_track, "audio")
        
        
        subtitle_index = None
        if external_subs:
            print(f"Using external subtitles: {external_subs}")
        elif subtitle_tracks:
            if subtitle_track is not None:
                if 0 <= subtitle_track < len(subtitle_tracks):
                    subtitle_index = subtitle_track
                else:
                    print(f"Warning: Invalid subtitle index {subtitle_track}. No subtitles will be used.")
            else:
                subtitle_index = self.choose_track_interactively(subtitle_tracks, "subtitle")
        
        
        cmd = self.build_ffmpeg_command(
            input_file=input_file,
            output_file=output_file,
            video_index=video_index,
            audio_index=audio_index,
            subtitle_index=subtitle_index,
            external_subs=external_subs
        )
        
        print("\nStarting conversion...")
        print(f"Output: {output_file}")
        
        try:
            subprocess.run(cmd, check=True)
            print(f"\n✓ Conversion completed successfully!")
            print(f"Output file: {output_file}")
        except subprocess.CalledProcessError as e:
            raise VideoConverterError(f"FFmpeg conversion failed with exit code {e.returncode}")
    
    def _select_track(self, tracks: List[Dict], specified_index: Optional[int], track_type: str) -> int:
        """Select a track either from user specification or interactive choice."""
        if specified_index is not None:
            if 0 <= specified_index < len(tracks):
                return specified_index
            else:
                raise VideoConverterError(
                    f"Invalid {track_type} track index {specified_index}. "
                    f"Available range: 0-{len(tracks)-1}"
                )
        
        return self.choose_track_interactively(tracks, track_type)


def print_title() -> None:
    """Print application title and info."""
    print("+" + "-" * 50 + "+")
    print("|    video2psp - Video Converter for PSP Format    |")
    print("+" + "-" * 50 + "+")
    print("                                     by Erick Ghuron", end="\n\n")

def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Convert video files to PSP-compatible MP4 format with user-selected tracks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.ext
  %(prog)s input.ext output.mp4 --video-track 0 --audio-track 1
  %(prog)s input.ext --external-subs subtitles.srt
        """
    )
    
    parser.add_argument(
        "input_file",
        help="Input video file path"
    )
    parser.add_argument(
        "output_file",
        nargs='?',
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
    
    print_title()
    
    try:
        args = parser.parse_args()
        
        converter = PSPVideoConverter()
        converter.convert_video(
            input_file=args.input_file,
            output_file=args.output_file,
            video_track=args.video_track,
            audio_track=args.audio_track,
            subtitle_track=args.subtitle_track,
            external_subs=args.external_subs
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
