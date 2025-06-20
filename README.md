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

With the tool installed, simply run:
```bash
video2psp <input_video> <output_video> [options]
```
- If you do **not** specify `--video-track`, `--audio-track` or `--subtitle-track`, the script will prompt you to pick which tracks to use.  
- To skip prompts, you can set them explicitly, for example:
  ```bash
  video2psp movie.mkv out.mp4 --video-track 0 --audio-track 0 --subtitle-track 1
  ```
- To burn an external subtitle file instead of an embedded track:
  ```bash
  video2psp movie.mkv out.mp4 --external-subs subs.srt
  ```
  
## Notes & Limitations

- The **PSP** typically supports H.264 Baseline Level 3.0 with AAC audio.  
- Resolution is scaled to **480 pixels wide** (height adjusted automatically) to match PSP screen specs.  
- Only **one** video and audio track is included, and **one** subtitle track can be burned.  
- For image-based subtitles (like PGS or VobSub), you need to convert them to a text format (e.g., SRT) before burning.

Feel free to contribute or customize further. Enjoy converting videos for your PSP!