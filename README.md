# video2psp

**video2psp** is a Python CLI tool that converts videos to a PSP-compatible MP4 format, allowing you to select which audio and subtitle track to include (burned in) or optionally use an external subtitle file.

## Installation

1. Make sure you have [FFmpeg](https://ffmpeg.org/) (including `ffprobe`) installed and accessible in your system’s PATH.  
2. Clone or download this repository and run:
   ```bash
   pip install .
   ```
   This will install **video2psp** as a console command.

Or install using PyPI

```bash
pip install video2psp
```

## Usage

### GUI

Prefer a graphical interface? Run:
```bash
video2psp --gui
```
(`-g` also works), or launch `video2psp-gui` to open it without a terminal window. The GUI lets you pick the input/output files, choose tracks, and tweak volume/preset/CRF/frame rate without touching the terminal.

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