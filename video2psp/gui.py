"""
video2psp GUI - a Tkinter wrapper around PSPVideoConverter.
"""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from fractions import Fraction
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from video2psp.psp import (
    DEFAULT_CRF,
    DEFAULT_PRESET,
    NO_WINDOW,
    PRESETS,
    MediaInfo,
    PSPVideoConverter,
    Track,
    VideoConverterError,
    check_trim,
    default_output_path,
    format_frame_rate,
    format_timestamp,
    output_frame_rate,
    parse_frame_rate,
    parse_timestamp,
    remove_partial_output,
)
from video2psp.theme import Theme, system_prefers_dark

VIDEO_FILETYPES = [
    ("Video files", "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v *.ts"),
    ("All files", "*.*"),
]
SUBTITLE_FILETYPES = [
    ("Subtitles", "*.srt *.ass *.ssa *.vtt"),
    ("All files", "*.*"),
]
FPS_SOURCE = "Source"
FPS_CHOICES = [FPS_SOURCE, "23.976", "24", "25", "29.97"]

ROW_PADY = 6
LABEL_PADX = (0, 14)
CARD_GAP = 14

# Segoe Fluent Icons (Windows 11) / Segoe MDL2 Assets (Windows 10) glyphs
ICON_SUN = ""
ICON_MOON = ""


def _parse_out_time(value: str) -> float:
    try:
        h, m, s = value.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except (ValueError, AttributeError):
        return 0.0


def _parse_speed(value: str) -> float | None:
    try:
        speed = float(value.rstrip("x"))
    except ValueError:  # "N/A" at the very start
        return None
    return speed if speed > 0 else None


def _format_eta(seconds: float) -> str:
    if seconds < 60:
        return "less than a minute left"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"about {minutes} min left"
    return f"about {minutes // 60} h {minutes % 60:02d} min left"


def _quality_label(crf: int) -> str:
    if crf <= 19:
        return "high quality, bigger file"
    if crf <= 25:
        return "balanced"
    return "smaller file, lower quality"


class PSPConverterGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.converter = PSPVideoConverter()

        self.video_tracks: list[Track] = []
        self.audio_tracks: list[Track] = []
        self.subtitle_tracks: list[Track] = []
        self.duration = 0.0

        self.proc: subprocess.Popen | None = None
        self._worker: threading.Thread | None = None
        self._cancel_requested = False
        self.output_user_edited = False
        self._analysis_token = 0
        self._loaded_input = ""
        self.msg_queue: "queue.Queue" = queue.Queue()

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.external_subs_var = tk.StringVar()
        self.start_var = tk.StringVar()
        self.end_var = tk.StringVar()
        self.volume_var = tk.DoubleVar(value=1.0)
        self.preset_var = tk.StringVar(value=DEFAULT_PRESET)
        self.crf_var = tk.DoubleVar(value=float(DEFAULT_CRF))
        self.fps_var = tk.StringVar(value=FPS_SOURCE)
        self.hwaccel_var = tk.BooleanVar(value=True)
        self.info_var = tk.StringVar(value="No video selected")
        self.trim_hint_var = tk.StringVar(value="leave empty to convert the whole video, e.g. 1:30 to 22:10")
        self.status_var = tk.StringVar(value="Select a video to get started.")

        self.theme = Theme(root)
        self._build_ui()
        self._apply_theme("dark" if system_prefers_dark() else "light")
        self._fit_window()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(150, self._poll_queue)

    # -- UI construction -------------------------------------------------

    def _build_ui(self) -> None:
        root = self.root
        root.title("video2psp")
        try:
            # Keep a reference: Tk drops images that Python garbage-collects.
            self._icon = tk.PhotoImage(file=str(Path(__file__).with_name("icon.png")))
            root.iconphoto(True, self._icon)
        except tk.TclError:
            pass
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root, padding=(24, 16, 18, 12))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="video2psp", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Convert videos to a PSP-compatible format", style="Subtitle.TLabel").grid(
            row=0, column=1, sticky="sw", padx=(12, 0), pady=(0, 4)
        )
        self.theme_btn = ttk.Button(header, style="Ghost.TButton", command=self._toggle_theme, width=3)
        self.theme_btn.grid(row=0, column=2, sticky="e")

        body = ttk.Frame(root, padding=(24, 0, 24, 0))
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1, uniform="column")
        body.columnconfigure(1, weight=1, uniform="column")
        body.rowconfigure(1, weight=1)

        # Files: input -> output -> which part of the video
        files = self._card(body, "Files", row=0, column=0, columnspan=2)
        files.columnconfigure(1, weight=1)
        input_entry, input_btn = self._file_row(files, 1, "Input video", self.input_var, self._browse_input)
        input_entry.bind("<Return>", lambda _e: self._load_input(self.input_var.get().strip()))
        input_entry.bind("<FocusOut>", lambda _e: self._load_input(self.input_var.get().strip()))
        ttk.Label(files, textvariable=self.info_var, style="Muted.TLabel").grid(
            row=2, column=1, columnspan=2, sticky="w", pady=(0, 2)
        )
        output_entry, output_btn = self._file_row(files, 3, "Output file", self.output_var, self._browse_output)
        output_entry.bind("<KeyRelease>", lambda _e: setattr(self, "output_user_edited", True))

        ttk.Label(files, text="Trim", style="Card.TLabel").grid(row=4, column=0, sticky="w", padx=LABEL_PADX, pady=ROW_PADY)
        trim = ttk.Frame(files, style="Card.TFrame")
        trim.grid(row=4, column=1, columnspan=2, sticky="ew", pady=ROW_PADY)
        start_entry = ttk.Entry(trim, textvariable=self.start_var, width=11)
        start_entry.pack(side="left")
        ttk.Label(trim, text="to", style="Muted.TLabel").pack(side="left", padx=8)
        end_entry = ttk.Entry(trim, textvariable=self.end_var, width=11)
        end_entry.pack(side="left")
        ttk.Label(trim, textvariable=self.trim_hint_var, style="Muted.TLabel").pack(side="left", padx=(14, 0))
        for var in (self.start_var, self.end_var):
            var.trace_add("write", lambda *_: self._update_trim_hint())

        # Tracks
        tracks = self._card(body, "Tracks", row=1, column=0)
        tracks.columnconfigure(1, weight=1)
        self.video_combo = self._combo_row(tracks, 1, "Video")
        self.audio_combo = self._combo_row(tracks, 2, "Audio")
        self.subtitle_combo = self._combo_row(tracks, 3, "Subtitle")
        subs_entry, subs_btn = self._file_row(
            tracks, 4, "External subtitle", self.external_subs_var, self._browse_external_subs
        )
        ttk.Label(tracks, text="Optional .srt/.ass file, used instead of the subtitle track", style="Muted.TLabel").grid(
            row=5, column=1, columnspan=2, sticky="w"
        )

        # Encoding: each control with its hint on the same row
        encoding = self._card(body, "Encoding", row=1, column=1)
        encoding.columnconfigure(2, weight=1)

        ttk.Label(encoding, text="Quality", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=LABEL_PADX, pady=(ROW_PADY, 0))
        crf_row = ttk.Frame(encoding, style="Card.TFrame")
        crf_row.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(ROW_PADY, 0))
        self.crf_scale = ttk.Scale(
            crf_row, from_=51, to=0, orient="horizontal", variable=self.crf_var, command=self._on_crf_change
        )
        self.crf_scale.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.crf_value_label = ttk.Label(crf_row, style="Value.TLabel", width=3, anchor="e")
        self.crf_value_label.pack(side="right")
        self.crf_hint = ttk.Label(encoding, style="Muted.TLabel")
        self.crf_hint.grid(row=2, column=1, columnspan=2, sticky="w", pady=(0, ROW_PADY))
        self._on_crf_change(str(DEFAULT_CRF))

        self.preset_combo = ttk.Combobox(encoding, state="readonly", values=PRESETS, textvariable=self.preset_var, width=11)
        self._setting_row(encoding, 3, "Speed", self.preset_combo, "slower = smaller file")

        self.fps_combo = ttk.Combobox(encoding, state="readonly", values=FPS_CHOICES, textvariable=self.fps_var, width=11)
        self.fps_hint = self._setting_row(encoding, 4, "Frame rate", self.fps_combo, "")
        self.fps_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_fps_hint())
        self.video_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_fps_hint())
        self._update_fps_hint()

        self.volume_spin = ttk.Spinbox(
            encoding, from_=0.1, to=5.0, increment=0.1, textvariable=self.volume_var, width=9, format="%.1f"
        )
        self._setting_row(encoding, 5, "Volume", self.volume_spin, "1.0 = original")

        hwaccel_check = ttk.Checkbutton(
            encoding, text="Hardware decoding (falls back to CPU automatically)",
            variable=self.hwaccel_var, style="Card.TCheckbutton",
        )
        hwaccel_check.grid(row=6, column=0, columnspan=3, sticky="w", pady=(ROW_PADY + 4, 0))

        # Footer: progress, status and actions
        self._footer_line = tk.Frame(root, height=1, bd=0)
        self._footer_line.grid(row=2, column=0, sticky="ew")
        footer = ttk.Frame(root, style="Card.TFrame", padding=(24, 12, 24, 14))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(footer, orient="horizontal", mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 10))
        ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel").grid(row=1, column=0, sticky="w")
        self.open_folder_btn = ttk.Button(footer, text="Open folder", command=self._open_output_folder, state="disabled")
        self.open_folder_btn.grid(row=1, column=1, padx=(0, 8))
        self.cancel_btn = ttk.Button(footer, text="Cancel", style="Danger.TButton", command=self._on_cancel, state="disabled")
        self.cancel_btn.grid(row=1, column=2, padx=(0, 8))
        self.convert_btn = ttk.Button(footer, text="Convert", style="Accent.TButton", command=self._start_conversion, state="disabled")
        self.convert_btn.grid(row=1, column=3)

        self._combos =[self.video_combo, self.audio_combo, self.subtitle_combo, self.preset_combo, self.fps_combo]
        # Everything the user can change, locked while a conversion runs
        self._inputs = [
            input_entry, input_btn, output_entry, output_btn, subs_entry, subs_btn,
            start_entry, end_entry, self.crf_scale, self.volume_spin, hwaccel_check,
        ]

    def _fit_window(self) -> None:
        """Size the window to its content, so nothing is cut off at any display scaling."""
        self.root.update_idletasks()
        width, height = max(self.root.winfo_reqwidth(), 960), self.root.winfo_reqheight()
        self.root.minsize(width, height)
        self.root.geometry(f"{width}x{height}")

    def _card(self, parent: ttk.Frame, title: str, row: int, column: int, columnspan: int = 1) -> ttk.Frame:
        if columnspan == 2:
            padx = (0, 0)
        else:
            padx = (0, CARD_GAP // 2) if column == 0 else (CARD_GAP // 2, 0)
        card = ttk.Frame(parent, style="CardBox.TFrame", padding=(18, 14, 18, 14))
        card.grid(row=row, column=column, columnspan=columnspan, sticky="nsew", padx=padx, pady=(0, CARD_GAP))
        ttk.Label(card, text=title, style="CardTitle.TLabel").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        return card

    def _file_row(self, parent: ttk.Frame, row: int, label_text: str, var: tk.StringVar,
                  command) -> tuple[ttk.Entry, ttk.Button]:
        ttk.Label(parent, text=label_text, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=ROW_PADY, padx=LABEL_PADX)
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", pady=ROW_PADY, padx=(0, 8))
        button = ttk.Button(parent, text="Browse...", command=command)
        button.grid(row=row, column=2, pady=ROW_PADY)
        return entry, button

    def _setting_row(self, parent: ttk.Frame, row: int, label_text: str, widget: ttk.Widget,
                     hint: str) -> ttk.Label:
        ttk.Label(parent, text=label_text, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=ROW_PADY, padx=LABEL_PADX)
        widget.grid(row=row, column=1, sticky="w", pady=ROW_PADY)
        hint_label = ttk.Label(parent, text=hint, style="Muted.TLabel")
        hint_label.grid(row=row, column=2, sticky="w", padx=(12, 0), pady=ROW_PADY)
        return hint_label

    def _combo_row(self, parent: ttk.Frame, row: int, label_text: str) -> ttk.Combobox:
        ttk.Label(parent, text=label_text, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=ROW_PADY, padx=LABEL_PADX)
        combo = ttk.Combobox(parent, state="disabled", width=10)
        combo.grid(row=row, column=1, columnspan=2, sticky="ew", pady=ROW_PADY)
        return combo

    # -- Theme -----------------------------------------------------------

    def _apply_theme(self, name: str) -> None:
        self.theme.apply(name)
        self.theme.style_dropdowns(self._combos)
        self._footer_line.configure(bg=self.theme.colors["border"])
        if self.theme.fonts["has_icons"]:
            self.theme_btn.configure(text=ICON_SUN if name == "dark" else ICON_MOON)
        else:
            self.theme_btn.configure(text="☀" if name == "dark" else "☾")

    def _toggle_theme(self) -> None:
        self._apply_theme("light" if self.theme.name == "dark" else "dark")

    # -- Callbacks ---------------------------------------------------------

    def _on_crf_change(self, value: str) -> None:
        crf = int(round(float(value)))
        self.crf_value_label.configure(text=str(crf))
        self.crf_hint.configure(text=f"CRF {crf}: {_quality_label(crf)}")

    def _selected_frame_rate(self) -> Fraction:
        choice = self.fps_var.get()
        requested = None if choice == FPS_SOURCE else parse_frame_rate(choice)
        video_index = self.video_combo.current()
        source = self.video_tracks[video_index].frame_rate if self.video_tracks and video_index >= 0 else None
        return output_frame_rate(source, requested)

    def _update_fps_hint(self) -> None:
        if not self.video_tracks:
            self.fps_hint.configure(text="max 29.97")
            return
        self.fps_hint.configure(text=f"output {format_frame_rate(self._selected_frame_rate())} fps")

    def _trim_range(self) -> tuple[float | None, float | None]:
        """Start/end from the trim fields (None when empty). Raises ValueError."""
        start_text, end_text = self.start_var.get().strip(), self.end_var.get().strip()
        start = parse_timestamp(start_text) if start_text else None
        end = parse_timestamp(end_text) if end_text else None
        return start, end

    def _update_trim_hint(self) -> None:
        try:
            start, end = self._trim_range()
        except ValueError:
            self.trim_hint_var.set("use seconds or [HH:]MM:SS, e.g. 90 or 1:30")
            return
        if start is None and end is None:
            self.trim_hint_var.set("leave empty to convert the whole video, e.g. 1:30 to 22:10")
            return
        stop = min(end, self.duration) if end is not None and self.duration > 0 else (end or self.duration)
        if stop and stop > (start or 0):
            self.trim_hint_var.set(f"output length {format_timestamp(round(stop - (start or 0)))}")
        elif stop:
            self.trim_hint_var.set("the end must be after the start")
        else:
            self.trim_hint_var.set("")

    def _browse_input(self) -> None:
        path = filedialog.askopenfilename(title="Select video", filetypes=VIDEO_FILETYPES)
        if path:
            self.input_var.set(path)
            self._load_input(path)

    def _load_input(self, path: str) -> None:
        if not path or path == self._loaded_input:
            return
        self._loaded_input = path
        if not self.output_user_edited:
            self.output_var.set(str(default_output_path(path)))
        self._reset_tracks()
        self.info_var.set("Analyzing...")
        self._set_status("Analyzing file...")

        self._analysis_token += 1
        token = self._analysis_token
        threading.Thread(target=self._analyze_worker, args=(path, token), daemon=True).start()

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save as", defaultextension=".mp4", filetypes=[("MP4", "*.mp4")]
        )
        if path:
            self.output_var.set(path)
            self.output_user_edited = True

    def _browse_external_subs(self) -> None:
        path = filedialog.askopenfilename(title="Select subtitle file", filetypes=SUBTITLE_FILETYPES)
        if path:
            self.external_subs_var.set(path)

    def _open_output_folder(self) -> None:
        output_file = self.output_var.get().strip()
        if not output_file:
            return
        folder = str(Path(output_file).parent)
        try:
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.run(["open", folder], check=False)
            else:
                subprocess.run(["xdg-open", folder], check=False)
        except OSError as e:
            messagebox.showerror("Error", f"Could not open folder: {e}")

    def _on_cancel(self) -> None:
        if self.proc and self.proc.poll() is None:
            self._cancel_requested = True
            self.proc.terminate()
            self._set_status("Cancelling...")

    def _on_close(self) -> None:
        """Closing mid-conversion would otherwise leave ffmpeg running in the
        background, writing a half-finished file."""
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Quit?", "A conversion is still running. Stop it and quit?"):
                return
            self._on_cancel()
            if self._worker is not None:
                # The worker waits for ffmpeg to exit and deletes the partial output.
                self._worker.join(timeout=10)
        self.root.destroy()

    # -- Analysis ------------------------------------------------------

    def _reset_tracks(self) -> None:
        self.video_tracks = []
        self.audio_tracks = []
        self.subtitle_tracks = []
        self.duration = 0.0
        for combo in (self.video_combo, self.audio_combo, self.subtitle_combo):
            combo.configure(state="disabled", values=[])
            combo.set("")
        self._update_fps_hint()
        self._update_trim_hint()
        self.convert_btn.configure(state="disabled")

    def _analyze_worker(self, input_file: str, token: int) -> None:
        try:
            info = self.converter.probe(input_file)
            if not info.video:
                raise VideoConverterError("No video track found in the file.")
            if not info.audio:
                raise VideoConverterError("No audio track found in the file.")
            self.msg_queue.put(("analyzed", (token, info)))
        except VideoConverterError as e:
            self.msg_queue.put(("analyze_error", (token, str(e))))
        except Exception as e:
            self.msg_queue.put(("analyze_error", (token, f"Unexpected error: {e}")))

    def _populate_tracks(self, info: MediaInfo) -> None:
        self.video_tracks = info.video
        self.audio_tracks = info.audio
        self.subtitle_tracks = info.subtitle
        self.duration = info.duration

        self.video_combo.configure(state="readonly", values=[t.label() for t in info.video])
        self.video_combo.current(0)

        self.audio_combo.configure(state="readonly", values=[t.label() for t in info.audio])
        self.audio_combo.current(0)

        if info.subtitle:
            values = ["None"] + [t.label() for t in info.subtitle]
            self.subtitle_combo.configure(state="readonly", values=values)
            self.subtitle_combo.current(0)
        else:
            self.subtitle_combo.configure(state="disabled", values=["No subtitles available"])
            self.subtitle_combo.current(0)

        video = info.video[0]
        details = [f"{video.width}x{video.height}", f"{video.fps} fps"]
        if info.duration > 0:
            details.append(format_timestamp(round(info.duration)))
        details.append(f"{len(info.audio)} audio, {len(info.subtitle)} subtitle track(s)")
        self.info_var.set("  ·  ".join(details))

        self._update_fps_hint()
        self._update_trim_hint()
        self.convert_btn.configure(state="normal")

    # -- Conversion ------------------------------------------------------

    def _start_conversion(self) -> None:
        input_file = self.input_var.get().strip()
        output_file = self.output_var.get().strip()

        if not input_file or not Path(input_file).exists():
            messagebox.showerror("Error", "Select a valid video file.")
            return
        if not self.video_tracks or not self.audio_tracks:
            messagebox.showerror("Error", "Wait for the file analysis to finish before converting.")
            return
        if not output_file:
            messagebox.showerror("Error", "Enter an output file.")
            return
        if Path(output_file).resolve() == Path(input_file).resolve():
            messagebox.showerror("Error", "The output file must be different from the input file.")
            return

        try:
            volume = float(self.volume_var.get())
            if volume <= 0:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror("Error", "Invalid volume. Use a number greater than 0.")
            return

        try:
            start, end = self._trim_range()
            check_trim(start, end, self.duration)
        except ValueError:
            messagebox.showerror("Error", "Invalid trim time. Use seconds or [HH:]MM:SS, e.g. 90 or 1:30.")
            return
        except VideoConverterError as e:
            messagebox.showerror("Error", str(e))
            return

        crf = int(round(self.crf_var.get()))
        video_index = self.video_combo.current()
        audio_index = self.audio_combo.current()

        subtitle_index: int | None = None
        external_subs = self.external_subs_var.get().strip() or None
        if not external_subs and self.subtitle_tracks and self.subtitle_combo.current() > 0:
            subtitle_index = self.subtitle_combo.current() - 1
            if self.subtitle_tracks[subtitle_index].is_image_subtitle:
                messagebox.showerror(
                    "Error",
                    "Image-based subtitles (PGS/VobSub) can't be burned.\n"
                    "Convert them to SRT and use the external subtitle field.",
                )
                return

        if Path(output_file).exists():
            if not messagebox.askyesno("Overwrite?", f"'{Path(output_file).name}' already exists. Overwrite?"):
                return

        try:
            cmd = self.converter.build_ffmpeg_command(
                input_file=input_file,
                output_file=output_file,
                video_index=video_index,
                audio_index=audio_index,
                subtitle_index=subtitle_index,
                external_subs=external_subs,
                volume_factor=volume,
                preset=self.preset_var.get(),
                crf=crf,
                frame_rate=self._selected_frame_rate(),
                hwaccel=self.hwaccel_var.get(),
                progress=True,
                start=start,
                end=end,
            )
        except VideoConverterError as e:
            messagebox.showerror("Error", str(e))
            return

        # Length of what will actually be encoded, for the progress bar
        stop = min(end, self.duration) if end is not None and self.duration > 0 else (end or self.duration)
        duration = max(stop - (start or 0), 0.0)

        self._cancel_requested = False
        self._set_converting(True)
        self.open_folder_btn.configure(state="disabled")
        self._set_status("Starting...")
        if duration > 0:
            self.progress.configure(mode="determinate", value=0)
        else:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)

        self._worker = threading.Thread(
            target=self._run_ffmpeg, args=(cmd, duration, output_file), daemon=True
        )
        self._worker.start()

    def _run_ffmpeg(self, cmd: list[str], duration: float, output_file: str) -> None:
        """Worker thread: always reports back to the UI, even on unexpected errors,
        so the window never gets stuck in the converting state."""
        self.proc = None
        try:
            kind, payload = self._run_ffmpeg_process(cmd, duration)
        except Exception as e:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
                self.proc.wait()
            kind, payload = "convert_error", f"Unexpected error: {e}"

        # Only clean up if ffmpeg actually started; otherwise the file at
        # output_file (if any) is one the user already had.
        if kind != "convert_done" and self.proc is not None:
            remove_partial_output(output_file)
        self.msg_queue.put((kind, payload))

    def _run_ffmpeg_process(self, cmd: list[str], duration: float) -> tuple[str, str | None]:
        try:
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1,
                encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
            )
        except FileNotFoundError:
            return "convert_error", "ffmpeg not found. Make sure it's installed and in your PATH."

        stderr_lines: list[str] = []

        def _drain_stderr() -> None:
            if self.proc is None or self.proc.stderr is None:
                return
            for line in self.proc.stderr:
                stderr_lines.append(line.rstrip())

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        # -progress prints key=value blocks, each ending with progress=continue|end
        elapsed, speed = 0.0, None
        if self.proc.stdout is not None:
            for line in self.proc.stdout:
                key, _, value = line.strip().partition("=")
                if key == "out_time":
                    elapsed = _parse_out_time(value)
                elif key == "speed":
                    speed = _parse_speed(value)
                elif key == "progress":
                    if duration > 0:
                        pct = min(100.0, elapsed / duration * 100)
                        eta = (duration - elapsed) / speed if speed else None
                        self.msg_queue.put(("progress", (pct, eta)))
                    else:
                        self.msg_queue.put(("progress", None))
                    if value == "end":
                        break

        returncode = self.proc.wait()
        stderr_thread.join(timeout=2)

        if self._cancel_requested:
            return "convert_cancelled", None
        if returncode == 0:
            return "convert_done", None
        tail = "\n".join(stderr_lines[-15:])
        return "convert_error", f"ffmpeg exited with code {returncode}.\n{tail}"

    def _set_converting(self, active: bool) -> None:
        self.convert_btn.configure(state="disabled" if active else "normal")
        self.cancel_btn.configure(state="normal" if active else "disabled")
        for widget in self._inputs:
            widget.state(["disabled"] if active else ["!disabled"])
        enabled = {
            self.video_combo: bool(self.video_tracks),
            self.audio_combo: bool(self.audio_tracks),
            self.subtitle_combo: bool(self.subtitle_tracks),
            self.preset_combo: True,
            self.fps_combo: True,
        }
        for combo, has_values in enabled.items():
            combo.configure(state="readonly" if has_values and not active else "disabled")

    # -- Shared helpers --------------------------------------------------

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _finish_progress(self, value: float) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", value=value)
        self._set_converting(False)

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()

                if kind == "analyzed":
                    token, info = payload
                    if token == self._analysis_token:
                        self._populate_tracks(info)
                        self._set_status("Ready to convert.")
                elif kind == "analyze_error":
                    token, message = payload
                    if token == self._analysis_token:
                        self._loaded_input = ""
                        self.info_var.set("Could not read this file")
                        self._set_status("Failed to analyze the file.")
                        messagebox.showerror("Error analyzing file", message)
                elif kind == "progress":
                    if payload is None:
                        self._set_status("Converting...")
                    else:
                        pct, eta = payload
                        self.progress.configure(value=pct)
                        status = f"Converting... {pct:.0f}%"
                        if eta is not None and pct < 100:
                            status += f"  ·  {_format_eta(eta)}"
                        self._set_status(status)
                elif kind == "convert_done":
                    self._finish_progress(100)
                    self._set_status(f"Done! Saved {Path(self.output_var.get()).name}")
                    self.open_folder_btn.configure(state="normal")
                elif kind == "convert_cancelled":
                    self._finish_progress(0)
                    self._set_status("Conversion cancelled.")
                elif kind == "convert_error":
                    self._finish_progress(0)
                    self._set_status("Conversion failed.")
                    messagebox.showerror("Conversion error", payload)
        except queue.Empty:
            pass
        finally:
            self.root.after(150, self._poll_queue)


def launch_gui() -> None:
    """Launch the video2psp GUI window."""
    if sys.platform == "win32":
        import ctypes
        # Show our own icon in the taskbar instead of python.exe's when run via `video2psp --gui`.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ghurone.video2psp")
    root = tk.Tk()
    PSPConverterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
