from pathlib import Path

import pytest

from video2psp.psp import (
    PSPVideoConverter,
    VideoConverterError,
    build_parser,
    default_output_path,
    escape_filter_value,
    parse_streams,
)

PROBE_DATA = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
         "r_frame_rate": "24000/1001"},
        {"codec_type": "audio", "codec_name": "aac", "channels": 6, "sample_rate": "48000",
         "tags": {"language": "jpn"}},
        {"codec_type": "audio", "codec_name": "ac3", "channels": 2, "sample_rate": "48000",
         "tags": {"language": "eng", "title": "Commentary"}},
        {"codec_type": "subtitle", "codec_name": "ass", "tags": {"language": "por"}},
        {"codec_type": "subtitle", "codec_name": "hdmv_pgs_subtitle"},
        {"codec_type": "data", "codec_name": "bin_data"},
    ],
    "format": {"duration": "1425.5"},
}


def test_parse_streams_groups_and_indexes_by_kind():
    info = parse_streams(PROBE_DATA)
    assert [t.index for t in info.video] == [0]
    assert [t.index for t in info.audio] == [0, 1]
    assert [t.index for t in info.subtitle] == [0, 1]
    assert info.video[0].fps == "23.98"
    assert info.audio[1].title == "Commentary"
    assert info.duration == 1425.5


def test_image_subtitles_are_flagged():
    info = parse_streams(PROBE_DATA)
    assert not info.subtitle[0].is_image_subtitle
    assert info.subtitle[1].is_image_subtitle
    assert "not supported" in info.subtitle[1].label()


def test_labels():
    info = parse_streams(PROBE_DATA)
    assert info.video[0].label() == "[0] h264, 1920x1080, 23.98fps"
    assert info.audio[1].label() == '[1] ac3, eng, "Commentary", 2ch, 48000Hz'


def test_escape_filter_value_matches_ffmpeg_docs_example():
    # Example from "Notes on filtergraph escaping" in the ffmpeg-filters docs
    raw = "this is a 'string': may contain one, or more, special characters"
    expected = r"this is a \\\'string\\\'\\: may contain one\, or more\, special characters"
    assert escape_filter_value(raw) == expected


def test_escape_filter_value_windows_path():
    assert escape_filter_value(r"C:\Videos\a.srt") == r"C\\:\\\\Videos\\\\a.srt"


def test_default_output_path_never_overwrites_input():
    assert default_output_path("movie.mkv") == Path("movie.mp4")
    assert default_output_path("movie.mp4") == Path("movie_psp.mp4")


def test_build_command_basic():
    cmd = PSPVideoConverter().build_ffmpeg_command("in.mkv", "out.mp4", 0, 1)
    assert cmd[0] == "ffmpeg"
    assert cmd[-1] == "out.mp4"
    assert "-stats" in cmd and "-progress" not in cmd
    assert cmd[cmd.index("-map") + 1] == "0:v:0"
    assert "0:a:1" in cmd
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert "-af" not in cmd
    assert "subtitles" not in cmd[cmd.index("-vf") + 1]


def test_build_command_progress_and_volume():
    cmd = PSPVideoConverter().build_ffmpeg_command(
        "in.mkv", "out.mp4", 0, 0, volume_factor=1.5, progress=True
    )
    assert cmd[cmd.index("-progress") + 1] == "pipe:1"
    assert "-nostats" in cmd and "-stats" not in cmd
    assert cmd[cmd.index("-af") + 1] == "volume=1.5"


def test_build_command_embedded_subtitle_with_apostrophe():
    cmd = PSPVideoConverter().build_ffmpeg_command("Ocean's 11.mkv", "out.mp4", 0, 0, subtitle_index=2)
    vf = cmd[cmd.index("-vf") + 1]
    assert vf.endswith(r",subtitles=filename=Ocean\\\'s 11.mkv:si=2")


def test_build_command_missing_external_subs():
    with pytest.raises(VideoConverterError):
        PSPVideoConverter().build_ffmpeg_command("in.mkv", "out.mp4", 0, 0, external_subs="nope.srt")


def test_parser_gui_without_input():
    args = build_parser().parse_args(["--gui"])
    assert args.gui and args.input_file is None
