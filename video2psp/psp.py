import argparse
import subprocess
import json
import sys
import os


def ffprobe_streams(input_file: str) -> list[dict]:
    """
    Returns the information of all streams (video, audio, subtitles)
    in the file, using ffprobe in JSON format.
    """
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
            check=True
        )
        data = json.loads(result.stdout)
        return data.get('streams', [])
    except FileNotFoundError:
        print("Error: 'ffprobe' not found. Check if FFmpeg is in the PATH.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error: ffprobe returned a non-zero exit code.\n{e}")
        print("stderr:", e.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: Could not parse ffprobe output as JSON.")
        sys.exit(1)


def get_tracks_by_type(streams: list[dict]):
    """
    From the raw ffprobe data, returns 3 lists:
      - video_tracks
      - audio_tracks
      - subtitle_tracks

    Each item in the lists is a dictionary:
      {
        "index_in_type": 0,   # relative position (0,1,2...) within that type
        "codec_name": "h264",
        "language": "eng",
        "title": "..."
      }

    NOTE: We no longer store the global index. We will always use 'index_in_type'.
    """
    video_tracks = []
    audio_tracks = []
    subtitle_tracks = []

    # Counters to generate "index_in_type"
    v_count = 0
    a_count = 0
    s_count = 0

    for s in streams:
        codec_type = s.get("codec_type")
        codec_name = s.get("codec_name", "unknown")
        tags = s.get("tags", {})
        language = tags.get("language", "und")
        title = tags.get("title", "")

        if codec_type == "video":
            video_tracks.append({
                "index_in_type": v_count,
                "codec_name": codec_name,
                "language": language,
                "title": title
            })
            v_count += 1

        elif codec_type == "audio":
            audio_tracks.append({
                "index_in_type": a_count,
                "codec_name": codec_name,
                "language": language,
                "title": title
            })
            a_count += 1

        elif codec_type == "subtitle":
            subtitle_tracks.append({
                "index_in_type": s_count,
                "codec_name": codec_name,
                "language": language,
                "title": title
            })
            s_count += 1

    return video_tracks, audio_tracks, subtitle_tracks


def _choose_track_interactively(tracks: list[dict], track_type: str) -> int | None:
    """
    Asks the user which track (within that list) they want to use.
    Returns the chosen 'index_in_type' or None if the user does not choose (for subtitles).
    """
    if not tracks:
        return None

    if len(tracks) == 1:
        print(f"Only 1 {track_type.upper()} track detected. Selecting automatically.")
        return tracks[0]['index_in_type']

    print(f"\nAvailable {track_type.upper()} tracks ({len(tracks)}):")
    for t in tracks:
        i = t['index_in_type']
        print(f"  [{i}] codec={t['codec_name']}, lang={t['language']}, title={t['title']}")

    if track_type == 'subtitle':
        print("Type -1 or leave blank to choose NO subtitles.")

    while True:
        user_input = input(f"Select the {track_type} track index (0..{len(tracks)-1}"
                           + (", or -1 for none): " if track_type == 'subtitle' else "): "))
        user_input = user_input.strip()

        if track_type == 'subtitle' and user_input == '':
            user_input = '-1'  # if only enter is pressed

        try:
            idx = int(user_input)
            if track_type == 'subtitle' and idx == -1:
                return None
            if 0 <= idx < len(tracks):
                return idx
            else:
                print("Value out of range. Try again.")
        except ValueError:
            print("Invalid input. Try again.")


def build_ffmpeg_command(
    input_file: str,
    output_file: str,
    video_index: int,
    audio_index: int,
    subtitle_index: int | None = None,
    external_subs: str | None = None
) -> list[str]:
    
    """
    Generates an ffmpeg command that maps the relative video and audio:
       -map 0:v:<video_index>
       -map 0:a:<audio_index>

    Burns subtitles (either external or embedded).
    subtitle_index is the relative index among the subtitle tracks (0,1,2...).
    """
    cmd = [
        'ffmpeg',
        '-hide_banner',
        '-loglevel', 'error',
        '-stats',
        '-y',
        '-i', input_file
    ]

    cmd += ['-map', f'0:v:{video_index}']
    cmd += ['-map', f'0:a:{audio_index}']

    base_vf = "scale=480:-2"
    vf_filter = base_vf

    if external_subs:
        ext_sub_escaped = external_subs.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        vf_filter += f",subtitles='{ext_sub_escaped}'"
    elif subtitle_index is not None:
        input_escaped = input_file.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        vf_filter += f",subtitles='{input_escaped}:si={subtitle_index}'"

    cmd += [
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
        output_file
    ]

    return cmd


def print_title() -> None:
    print("+--------------------------------------------- +")
    print("| video2psp - A video converter for PSP format |")
    print("+--------------------------------------------- +")
    print("by Erick Ghuron\n")
    
    
def main():
    parser = argparse.ArgumentParser(
        description="Convert video to PSP MP4 with user-selected video, audio and subtitle tracks."
        )
                                     
    parser.add_argument("input_file", type=str, help="Input file")
    parser.add_argument("output_file", type=str, nargs='?', default=None,
                        help="Output file (optional, default = input + .mp4)")
    parser.add_argument("--video-track", type=int, default=None,
                        help="Relative index of the video track (0,1,2...)")
    parser.add_argument("--audio-track", type=int, default=None,
                        help="Relative index of the audio track (0,1,2...)")
    parser.add_argument("--subtitle-track", type=int, default=None,
                        help="Relative index of the subtitle track (0,1,2...) to burn.")
    parser.add_argument("--external-subs", type=str, default=None,
                        help="External subtitles (srt, ass) to burn into the video (takes priority over embedded).")

    print_title()
    
    args = parser.parse_args()

    input_file = args.input_file
    if not args.output_file:
        base, _ = os.path.splitext(input_file)
        output_file = base + ".mp4"
    else:
        output_file = args.output_file

    streams = ffprobe_streams(input_file)
    video_tracks, audio_tracks, subtitle_tracks = get_tracks_by_type(streams)

    if not video_tracks:
        print("Error: there are no VIDEO tracks in the file.")
        sys.exit(1)

    if not audio_tracks:
        print("Error: there are no AUDIO tracks in the file.")
        sys.exit(1)

    if args.video_track is None:
        video_index = _choose_track_interactively(video_tracks, "video")
    else:
        video_index = args.video_track
        if video_index < 0 or video_index >= len(video_tracks):
            print(f"Error: invalid video index {video_index}. Only {len(video_tracks)} tracks found.")
            sys.exit(1)

    if args.audio_track is None:
        audio_index = _choose_track_interactively(audio_tracks, "audio")
    else:
        audio_index = args.audio_track
        if audio_index < 0 or audio_index >= len(audio_tracks):
            print(f"Error: invalid audio index {audio_index}. Only {len(audio_tracks)} tracks found.")
            sys.exit(1)

    if args.external_subs:
        subtitle_index = None
    else:
        if not subtitle_tracks:
            subtitle_index = None
        else:
            if args.subtitle_track is None:
                subtitle_index = _choose_track_interactively(subtitle_tracks, "subtitle")
            else:
                st_idx = args.subtitle_track
                if 0 <= st_idx < len(subtitle_tracks):
                    subtitle_index = st_idx
                else:
                    print(f"Warning: invalid subtitle index {st_idx}. No subtitles will be burned.")
                    subtitle_index = None

    cmd = build_ffmpeg_command(
        input_file=input_file,
        output_file=output_file,
        video_index=video_index,
        audio_index=audio_index,
        subtitle_index=subtitle_index,
        external_subs=args.external_subs
    )

    print("\nRunning FFmpeg...")

    try:
        subprocess.run(cmd, check=True)
        print(f"\nFile generated: {output_file}")
    except subprocess.CalledProcessError as e:
        print("Failed to run ffmpeg:")
        print(e)


if __name__ == "__main__":
    main()
