# video2psp

**video2psp** converts videos to a PSP-compatible MP4 format, with a graphical interface and a command-line tool. You choose which audio and subtitle track to include (subtitles are burned in), or use an external subtitle file, and can trim the video to just the part you want.

## Installation

### Windows (no install needed)

Download `video2psp-gui-<version>-windows.zip` from the [latest release](https://github.com/ghurone/video2psp/releases/latest), extract it and run `video2psp-gui.exe`. FFmpeg is already included.

Windows SmartScreen may warn about an unrecognized app the first time; click **More info → Run anyway**.

### Linux and macOS

video2psp needs **Python 3.11+**, **FFmpeg** (with `ffprobe` and the `libx264` encoder) and **Tkinter** for the GUI. Install them with your package manager, then install video2psp with [pipx](https://pipx.pypa.io/), which keeps it in its own environment (plain `pip install` is blocked on many recent distros):

| System | Dependencies |
|---|---|
| Debian / Ubuntu / Mint | `sudo apt install ffmpeg python3-tk pipx` |
| Fedora | Enable [RPM Fusion](https://rpmfusion.org/Configuration), then `sudo dnf install ffmpeg python3-tkinter pipx` (Fedora's own `ffmpeg-free` has no `libx264`) |
| Arch / Manjaro | `sudo pacman -S ffmpeg tk python-pipx` |
| macOS ([Homebrew](https://brew.sh/)) | `brew install ffmpeg python-tk pipx` |

```bash
pipx ensurepath          # once, so the commands are found (then reopen the terminal)
pipx install video2psp
video2psp-gui            # or: video2psp <input_video> for the CLI
```

To update later: `pipx upgrade video2psp`.

To check that your FFmpeg can encode for the PSP, `ffmpeg -hide_banner -encoders | grep libx264` should print a line.

### Windows with Python

If you prefer the Python package over the standalone release, install FFmpeg (e.g. `winget install Gyan.FFmpeg`) and run:

```bash
pip install video2psp
```

### From source

Clone this repository and run `pip install .` in it.

## Usage

### GUI

Prefer a graphical interface? Run:
```bash
video2psp --gui
```
(`-g` also works), or launch `video2psp-gui` to open it without a terminal window. The GUI lets you pick the input/output files, trim the video, choose tracks, and tweak quality/speed/frame rate/volume without touching the terminal. It follows the Windows light/dark setting, and the button in the top-right corner switches between them.

### CLI

With the tool installed, simply run:
```bash
video2psp <input_video> [output_video] [options]
```
- If `output_video` is omitted, the output is saved next to the input with an `.mp4` extension.
- If you do **not** specify `--video-track`, `--audio-track` or `--subtitle-track`, the script will prompt you to pick which tracks to use.  
- To skip prompts, you can set them explicitly, for example:
  ```bash
  video2psp movie.mkv out.mp4 --video-track 0 --audio-track 0 --subtitle-track 1
  ```
- To burn an external subtitle file instead of an embedded track:
  ```bash
  video2psp movie.mkv out.mp4 --external-subs subs.srt
  ```
- To convert only part of the video, give a start and/or end time (seconds, `MM:SS` or `HH:MM:SS`). Burned-in subtitles stay in sync:
  ```bash
  video2psp movie.mkv out.mp4 --start 1:30 --end 22:10
  ```
- To adjust audio volume (e.g. 150%):
  ```bash
  video2psp movie.mkv out.mp4 --volume 1.5
  ```
- To trade encoding speed for compression efficiency (default: `medium`):
  ```bash
  video2psp movie.mkv out.mp4 --preset veryfast
  ```
  Available presets (slowest/best compression to fastest): `veryslow`, `slower`, `slow`, `medium`, `fast`, `faster`, `veryfast`, `superfast`, `ultrafast`.
- To control video quality/file size via CRF (0-51, lower = higher quality and larger file, default: `23`):
  ```bash
  video2psp movie.mkv out.mp4 --crf 26
  ```
  Video is encoded at a constant quality target rather than a fixed bitrate, so simple scenes take up less space; `-maxrate`/`-bufsize` still cap the peak bitrate to respect the PSP's decoder buffer limits.
- The output keeps the source frame rate by default (max 29.97 fps, the PSP limit; higher rates are divided evenly, e.g. 59.94 → 29.97, 50 → 25). To pick one yourself:
  ```bash
  video2psp movie.mkv out.mp4 --fps 23.976
  ```
- Hardware (GPU) decoding is on by default and falls back to the CPU automatically when unavailable. If it causes problems on your machine, turn it off:
  ```bash
  video2psp movie.mkv out.mp4 --no-hwaccel
  ```
  
## Notes & Limitations

- The **PSP** typically supports H.264 Baseline Level 3.0 with AAC audio.  
- Resolution is scaled to fit within **480x272** (PSP screen size), preserving aspect ratio and padding with black bars as needed.  
- Only **one** video and audio track is included, and **one** subtitle track can be burned.  
- For image-based subtitles (like PGS or VobSub), you need to convert them to a text format (e.g., SRT) before burning.
- If no output file is given and the input is already an `.mp4`, the output is saved as `<name>_psp.mp4` so the original is never overwritten.
- 10-bit sources and anamorphic videos (e.g. DVDs) are converted to 8-bit and square pixels automatically.

Feel free to contribute or customize further. Enjoy converting videos for your PSP!

## License

video2psp is licensed under the [GNU General Public License v3.0 or later](LICENSE). The Windows release bundles FFmpeg builds from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/), which are also distributed under the GPL.
