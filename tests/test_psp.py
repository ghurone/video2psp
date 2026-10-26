import subprocess
from fractions import Fraction
from pathlib import Path

import pytest

from video2psp.psp import (
    PSPVideoConverter,
    VideoConverterError,
    build_parser,
    default_output_path,
    escape_filter_value,
    format_frame_rate,
    format_timestamp,
    output_frame_rate,
    parse_frame_rate,
    parse_streams,
    parse_timestamp,
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


NTSC_FILM = Fraction(24000, 1001)
NTSC = Fraction(30000, 1001)


@pytest.mark.parametrize("source, expected", [
    (NTSC_FILM, NTSC_FILM),                # film stays film
    (Fraction(25), Fraction(25)),          # PAL stays PAL
    (NTSC, NTSC),
    (Fraction(60000, 1001), NTSC),         # 59.94 -> 29.97
    (Fraction(50), Fraction(25)),          # 50 -> 25, not 29.97
    (Fraction(60), NTSC),                  # 60 -> 30 -> capped to 29.97
    (Fraction(30), NTSC),
    (None, NTSC),                          # unknown source rate
])
def test_output_frame_rate_from_source(source, expected):
    assert output_frame_rate(source) == expected


def test_output_frame_rate_user_choice_wins():
    assert output_frame_rate(Fraction(60), Fraction(25)) == 25
    assert output_frame_rate(NTSC_FILM, Fraction(30)) == NTSC


def test_parse_and_format_frame_rate():
    assert parse_frame_rate("23.976") == NTSC_FILM
    assert parse_frame_rate("24000/1001") == NTSC_FILM
    assert parse_frame_rate(" 25 ") == 25
    assert format_frame_rate(NTSC_FILM) == "23.976"
    assert format_frame_rate(NTSC) == "29.97"
    assert format_frame_rate(Fraction(25)) == "25"
    for bad in ("abc", "0", "-5", "1/0"):
        with pytest.raises(ValueError):
            parse_frame_rate(bad)


def test_build_command_frame_rate_and_hwaccel():
    converter = PSPVideoConverter()
    cmd = converter.build_ffmpeg_command("in.mkv", "out.mp4", 0, 0, frame_rate=NTSC_FILM)
    assert cmd[cmd.index("-r") + 1] == "24000/1001"
    assert cmd[cmd.index("-hwaccel") + 1] == "auto"
    assert cmd.index("-hwaccel") < cmd.index("-i")

    cmd = converter.build_ffmpeg_command("in.mkv", "out.mp4", 0, 0, hwaccel=False)
    assert "-hwaccel" not in cmd


@pytest.fixture
def probed_converter(monkeypatch, tmp_path):
    """A converter whose probe returns PROBE_DATA, plus an existing input file."""
    converter = PSPVideoConverter()
    monkeypatch.setattr(converter, "probe", lambda _f: parse_streams(PROBE_DATA))
    input_file = tmp_path / "in.mkv"
    input_file.touch()
    return converter, str(input_file), str(tmp_path / "out.mp4")


@pytest.mark.parametrize("subtitle_track, message", [
    (5, "Invalid subtitle track index 5"),
    (1, "image-based"),
])
def test_bad_subtitle_track_is_an_error(probed_converter, subtitle_track, message):
    converter, input_file, output_file = probed_converter
    with pytest.raises(VideoConverterError, match=message):
        converter.convert_video(
            input_file, output_file, video_track=0, audio_track=0, subtitle_track=subtitle_track
        )


def test_subtitle_track_without_subtitles_is_an_error(monkeypatch, probed_converter):
    converter, input_file, output_file = probed_converter
    no_subs = {**PROBE_DATA, "streams": [s for s in PROBE_DATA["streams"] if s["codec_type"] != "subtitle"]}
    monkeypatch.setattr(converter, "probe", lambda _f: parse_streams(no_subs))
    with pytest.raises(VideoConverterError, match="no subtitle tracks"):
        converter.convert_video(input_file, output_file, video_track=0, audio_track=0, subtitle_track=0)


def test_failed_conversion_removes_partial_output(monkeypatch, probed_converter):
    converter, input_file, output_file = probed_converter

    def fake_ffmpeg(cmd, check):
        Path(cmd[-1]).write_bytes(b"half a video")
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "run", fake_ffmpeg)
    with pytest.raises(VideoConverterError):
        converter.convert_video(input_file, output_file, video_track=0, audio_track=0, subtitle_track=0)
    assert not Path(output_file).exists()


def test_parser_fps_and_hwaccel_defaults():
    args = build_parser().parse_args(["in.mkv"])
    assert args.fps == "source" and args.hwaccel is True
    args = build_parser().parse_args(["in.mkv", "--fps", "25", "--no-hwaccel"])
    assert args.fps == "25" and args.hwaccel is False


@pytest.mark.parametrize("text, seconds", [
    ("90", 90), ("1:30", 90), ("01:02:03.5", 3723.5), (" 0:00:05 ", 5),
])
def test_parse_timestamp(text, seconds):
    assert parse_timestamp(text) == seconds


@pytest.mark.parametrize("bad", ["", "abc", "1:60", "-5", "1:2:3:4", "inf", "1::2"])
def test_parse_timestamp_rejects(bad):
    with pytest.raises(ValueError):
        parse_timestamp(bad)


def test_format_timestamp():
    assert format_timestamp(0) == "00:00:00"
    assert format_timestamp(3723.5) == "01:02:03.5"
    assert format_timestamp(1425.25) == "00:23:45.25"


def test_build_command_trim():
    cmd = PSPVideoConverter().build_ffmpeg_command("in.mkv", "out.mp4", 0, 0, start=90, end=120)
    assert cmd[cmd.index("-ss") + 1] == "90.000"
    assert cmd.index("-ss") < cmd.index("-i") < cmd.index("-t")
    assert cmd[cmd.index("-t") + 1] == "30.000"

    cmd = PSPVideoConverter().build_ffmpeg_command("in.mkv", "out.mp4", 0, 0, end=60)
    assert "-ss" not in cmd and cmd[cmd.index("-t") + 1] == "60.000"


def test_trimmed_subtitles_keep_original_timing():
    cmd = PSPVideoConverter().build_ffmpeg_command("in.mkv", "out.mp4", 0, 0, subtitle_index=0, start=90)
    vf = cmd[cmd.index("-vf") + 1]
    assert vf.endswith(",setpts=PTS+90.000/TB,subtitles=filename=in.mkv:si=0,setpts=PTS-STARTPTS")

    cmd = PSPVideoConverter().build_ffmpeg_command("in.mkv", "out.mp4", 0, 0, start=90)
    assert "setpts" not in cmd[cmd.index("-vf") + 1]


@pytest.mark.parametrize("start, end, message", [
    (2000, None, "past the end"),
    (60, 30, "after the start"),
])
def test_bad_trim_is_an_error(probed_converter, start, end, message):
    converter, input_file, output_file = probed_converter
    with pytest.raises(VideoConverterError, match=message):
        converter.convert_video(
            input_file, output_file, video_track=0, audio_track=0, subtitle_track=0, start=start, end=end
        )


def test_parser_trim():
    args = build_parser().parse_args(["in.mkv", "--start", "1:30", "--end", "120"])
    assert args.start == 90 and args.end == 120
    with pytest.raises(SystemExit):
        build_parser().parse_args(["in.mkv", "--start", "1:75"])
