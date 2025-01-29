import argparse
import subprocess
import json
import sys
import os


def ffprobe_streams(input_file:str) -> list:
    """
    Return the streams information for the given file, as reported by ffprobe
    (JSON).
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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        output = result.stdout.decode('utf-8', errors='replace')
        return json.loads(output).get('streams', [])

    except FileNotFoundError:
        print("Error: 'ffprobe' not found. Make sure FFmpeg (with ffprobe) "
              "is installed and in PATH.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error: ffprobe returned a non-zero exit status.\n{e}")
        print("stderr:", e.stderr.decode('utf-8', errors='replace'))
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: Could not parse ffprobe output as JSON.")
        sys.exit(1)


def list_tracks(input_file: str) -> tuple[list, list]:
    """
    Return two lists: (audio_tracks, subtitle_tracks).
    Each is a list of dicts with keys: ff_index (int), codec, language, title.
    """
    streams = ffprobe_streams(input_file)

    audio_tracks = []
    subtitle_tracks = []

    for s in streams:
        ff_index = s.get('index')
        codec_type = s.get('codec_type')
        codec_name = s.get('codec_name', 'unknown')
        tags = s.get('tags', {})
        language = tags.get('language', 'und')  # 'und' = undefined
        title = tags.get('title', '')

        if codec_type == 'audio':
            audio_tracks.append({
                'ff_index': ff_index,
                'codec': codec_name,
                'language': language,
                'title': title
            })
        elif codec_type == 'subtitle':
            subtitle_tracks.append({
                'ff_index': ff_index,
                'codec': codec_name,
                'language': language,
                'title': title
            })

    return audio_tracks, subtitle_tracks


def build_ffmpeg_command(
        input_file:str,
        output_file:str,
        audio_track_index:str,
        subtitle_track_index:str = None,
        external_subs:str = None
        
) -> list[str]:
    """
    Build an ffmpeg command for PSP-compatible MP4 with chosen audio track
    (re-encoded), and optionally burn in a chosen subtitle track or external
    subtitle file.

    - audio_track_index (int): Ex: 1 significa '0:1' no ffmpeg.
    - subtitle_track_index (int): Ex: 2 significa '0:2', ou None para não usar.
    - external_subs (str): caminho para .srt/.ass externo; se setado,
      ignora legendas embutidas.
    """

    cmd = [
        'ffmpeg',
        '-hide_banner',
        '-loglevel', 'error',
        '-stats',
        '-y',  # Overwrite sem perguntar
        '-i', input_file
    ]

    # Mapeia o primeiro track de vídeo (geralmente 0:v:0)
    cmd += ['-map', '0:v:0']
    # Mapeia o track de áudio escolhido (0:a:<índiceGlobal>)
    cmd += ['-map', f'0:{audio_track_index}']

    # Filtro base para escalonar para resolução do PSP (largura=480, altura ajustada)
    base_vf = "scale=480:-2"

    vf_filter = base_vf  # padrão (sem legendas)

    if external_subs:
        # Legenda externa
        vf_filter = f"{base_vf},subtitles='{external_subs}'"
    elif subtitle_track_index is not None:
        audio_tracks, subtitle_tracks = list_tracks(input_file)

        sub_order = None
        for i, st in enumerate(subtitle_tracks):
            if st['ff_index'] == subtitle_track_index:
                sub_order = i
                break

        if sub_order is None:
            print("Warning: Could not find the specified subtitle track "
                  "among embedded subtitles.")
            print("Skipping subtitle burn-in.")
        else:
            vf_filter = f"{base_vf},subtitles='{input_file}:si={sub_order}'"

    cmd += ['-vf', vf_filter]

    # Configurações de encoding para PSP (H.264 baseline, ~768kbps, AAC 128kbps)
    cmd += [
        '-c:v', 'libx264',
        '-profile:v', 'baseline',
        '-level:v', '3.0',
        '-b:v', '768k',
        '-maxrate', '768k',
        '-bufsize', '2000k',
        '-r', '29.97',  # framerate PSP comum
        '-c:a', 'aac',
        '-b:a', '128k',
        '-ac', '2',  # stereo
        output_file
    ]

    return cmd


def main():
    parser = argparse.ArgumentParser(
        description="Convert video to PSP MP4 with user-selected audio and "
                    "subtitle tracks."
    )
    parser.add_argument(
        "input_file",
        type=str,
        help="Path to input video."
    )
    parser.add_argument(
        "output_file",
        type=str,
        nargs='?',
        default=None,
        help="Path to output PSP-compatible MP4."
    )
    parser.add_argument(
        "--audio-track",
        type=int,
        default=None,
        help="Global ffmpeg index of the audio track you want to use "
             "(e.g. 1 for '0:1')."
    )
    parser.add_argument(
        "--subtitle-track",
        type=int,
        default=None,
        help="Global ffmpeg index of an embedded subtitle track to burn in "
             "(e.g. 2 for '0:2')."
    )
    parser.add_argument(
        "--external-subs",
        help="Path to an external .srt/.ass file for burning into the video "
             "(overrides embedded).",
        default=None,
        type=str
    )

    args = parser.parse_args()

    input_file = args.input_file
    base, _ = os.path.splitext(input_file)
    output_file = args.output_file if args.output_file else f"{base}.mp4"
    audio_track_index = args.audio_track
    subtitle_track_index = args.subtitle_track
    external_subs = args.external_subs

    audio_tracks, subtitle_tracks = list_tracks(input_file)

    if not audio_tracks:
        print("Error: No audio tracks found in the input file. Exiting.")
        sys.exit(1)

    if audio_track_index is None:
        if len(audio_tracks) == 1:
            print('Detected 1 AUDIO track!')
            audio_track_index = audio_tracks[0]['ff_index']
        else:
            print(f"Detected ({len(audio_tracks)}) the following AUDIO tracks:")
            for i, t in enumerate(audio_tracks):
                print(
                    f"  [{i}]  ff_index=0:{t['ff_index']}, "
                    f"codec={t['codec']}, "
                    f"lang={t['language']}, "
                    f"title={t['title']}"
                )

            while True:
                user_choice = input(
                    f"Select which audio track (0 to {len(audio_tracks)-1}): "
                )
                try:
                    user_choice_int = int(user_choice)
                    if 0 <= user_choice_int < len(audio_tracks):
                        audio_track_index = audio_tracks[user_choice_int]['ff_index']
                        break
                    else:
                        print("Invalid choice. Try again.")
                except ValueError:
                    print("Invalid input. Try again.")

    if external_subs is None and subtitle_track_index is None:
        if subtitle_tracks:
            print("\nDetected the following SUBTITLE tracks:")
            for i, st in enumerate(subtitle_tracks):
                print(
                    f"  [{i}]  ff_index=0:{st['ff_index']}, "
                    f"codec={st['codec']}, lang={st['language']}, "
                    f"title={st['title']}"
                )
            print("Enter -1 (or leave blank) if you do not want to burn any "
                  "embedded subtitles.")

            while True:
                user_sub_choice = input(
                    f"Select which subtitle track (0 to {len(subtitle_tracks)-1} "
                    f"or -1): "
                )
                if user_sub_choice.strip() == '':
                    user_sub_choice = '-1'

                try:
                    user_sub_choice_int = int(user_sub_choice)
                    if user_sub_choice_int == -1:
                        subtitle_track_index = None
                        break
                    elif 0 <= user_sub_choice_int < len(subtitle_tracks):
                        subtitle_track_index = (
                            subtitle_tracks[user_sub_choice_int]['ff_index']
                        )
                        break
                    else:
                        print("Invalid choice. Try again.")
                except ValueError:
                    print("Invalid input. Try again.")
        else:
            print("\nNo embedded subtitle tracks found.")

    cmd = build_ffmpeg_command(
        input_file=input_file,
        output_file=output_file,
        audio_track_index=audio_track_index,
        subtitle_track_index=subtitle_track_index,
        external_subs=external_subs
    )

    print("\nRunning FFmpeg:")
    # print(" ".join(map(str, cmd)))

    try:
        subprocess.run(cmd, check=True)
        print(f"\nSuccessfully created PSP video: {output_file}")
    except subprocess.CalledProcessError as e:
        print("\nError: FFmpeg command failed.")
        print(e)


if __name__ == "__main__":
    main()
