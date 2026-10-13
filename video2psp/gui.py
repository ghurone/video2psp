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
    PRESETS,
    MediaInfo,
    PSPVideoConverter,
    Track,
    VideoConverterError,
    default_output_path,
    format_frame_rate,
    output_frame_rate,
    parse_frame_rate,
)

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

LABEL_PADY = 10
LABEL_PADX = (0, 16)

COLORS = {
    "bg": "#f4f5f9",
    "card": "#ffffff",
    "border": "#e2e4ec",
    "text": "#1f2233",
    "muted": "#6b7089",
    "accent": "#4361ee",
    "accent_hover": "#3651d4",
    "accent_disabled": "#a9b4f5",
    "error": "#e5484d",
    "error_bg": "#fde8e8",
    "error_bg_hover": "#fbd5d5",
}


def _apply_style(root: tk.Tk) -> None:
    root.configure(bg=COLORS["bg"])
    style = ttk.Style(root)
    style.theme_use("clam")

    default_font = ("Segoe UI", 10)
    bold_font = ("Segoe UI", 11, "bold")
    title_font = ("Segoe UI", 17, "bold")

    style.configure(".", background=COLORS["bg"], foreground=COLORS["text"], font=default_font)
    style.configure("TFrame", background=COLORS["bg"])
    style.configure("Card.TFrame", background=COLORS["card"])
    style.configure("Card.TLabel", background=COLORS["card"], foreground=COLORS["text"])
    style.configure("Muted.TLabel", background=COLORS["card"], foreground=COLORS["muted"])
    style.configure("StatusMuted.TLabel", background=COLORS["bg"], foreground=COLORS["muted"])
    style.configure("Header.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=title_font)
    style.configure("SubHeader.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=default_font)
    style.configure("CardTitle.TLabel", background=COLORS["card"], foreground=COLORS["text"], font=bold_font)

    style.configure("Card.TCheckbutton", background=COLORS["card"], foreground=COLORS["text"])
    style.map("Card.TCheckbutton", background=[("active", COLORS["card"])])

    style.configure("TEntry", fieldbackground="#ffffff", padding=6)
    style.configure("TCombobox", fieldbackground="#ffffff", padding=6)
    style.configure("TSpinbox", fieldbackground="#ffffff", padding=6, arrowsize=14)

    style.configure(
        "TButton", background="#eef0f7", foreground=COLORS["text"],
        padding=(12, 8), relief="flat", font=default_font, borderwidth=0
    )
    style.map("TButton", background=[("active", "#e2e5f2"), ("disabled", "#f2f3f8")])

    style.configure(
        "Accent.TButton", background=COLORS["accent"], foreground="#ffffff",
        padding=(16, 9), relief="flat", font=bold_font, borderwidth=0
    )
    style.map(
        "Accent.TButton",
        background=[("disabled", COLORS["accent_disabled"]), ("active", COLORS["accent_hover"])],
        foreground=[("disabled", "#ffffff")],
    )

    style.configure(
        "Danger.TButton", background=COLORS["error_bg"], foreground=COLORS["error"],
        padding=(12, 8), relief="flat", font=default_font, borderwidth=0
    )
    style.map(
        "Danger.TButton",
        background=[("active", COLORS["error_bg_hover"]), ("disabled", "#f2f3f8")],
        foreground=[("disabled", COLORS["muted"])],
    )

    style.configure(
        "Horizontal.TProgressbar", background=COLORS["accent"], troughcolor="#e9ebf3",
        bordercolor="#e9ebf3", lightcolor=COLORS["accent"], darkcolor=COLORS["accent"], thickness=10
    )


def _parse_out_time(value: str) -> float:
    try:
        h, m, s = value.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    except (ValueError, AttributeError):
        return 0.0


# Windows/macOS report wheel motion via <MouseWheel>; X11 (Linux) uses buttons 4/5.
WHEEL_EVENTS = ("<MouseWheel>", "<Button-4>", "<Button-5>")


def _wheel_units(event: tk.Event) -> int:
    if event.num == 4:
        return -1
    if event.num == 5:
        return 1
    if sys.platform == "darwin":
        return -event.delta
    return int(-event.delta / 120)


class PSPConverterGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.converter = PSPVideoConverter()

        self.video_tracks: list[Track] = []
        self.audio_tracks: list[Track] = []
        self.subtitle_tracks: list[Track] = []
        self.duration = 0.0

        self.proc: subprocess.Popen | None = None
        self._cancel_requested = False
        self.output_user_edited = False
        self._analysis_token = 0
        self.msg_queue: "queue.Queue" = queue.Queue()

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.external_subs_var = tk.StringVar()
        self.volume_var = tk.DoubleVar(value=1.0)
        self.preset_var = tk.StringVar(value=DEFAULT_PRESET)
        self.crf_var = tk.DoubleVar(value=float(DEFAULT_CRF))
        self.fps_var = tk.StringVar(value=FPS_SOURCE)
        self.hwaccel_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Select a video to get started.")

        _apply_style(root)
        self._build_ui()
        self.root.after(150, self._poll_queue)

    # -- UI construction -------------------------------------------------

    def _build_ui(self) -> None:
        root = self.root
        root.title("video2psp")
        root.geometry("720x780")
        root.minsize(680, 480)

        actions = ttk.Frame(root, style="TFrame", padding=(20, 10, 20, 20))
        actions.pack(side="bottom", fill="x")
        self.open_folder_btn = ttk.Button(actions, text="Open folder", command=self._open_output_folder, state="disabled")
        self.open_folder_btn.pack(side="left")
        self.cancel_btn = ttk.Button(actions, text="Cancel", style="Danger.TButton", command=self._on_cancel, state="disabled")
        self.cancel_btn.pack(side="right", padx=(10, 0))
        self.convert_btn = ttk.Button(actions, text="Convert", style="Accent.TButton", command=self._start_conversion, state="disabled")
        self.convert_btn.pack(side="right")

        ttk.Separator(root, orient="horizontal").pack(side="bottom", fill="x")

        canvas = tk.Canvas(root, bg=COLORS["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        scroll_frame = ttk.Frame(canvas, style="TFrame")
        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

        def _on_frame_configure(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event) -> None:
            canvas.itemconfigure(canvas_window, width=event.width)

        scroll_frame.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event) -> None:
            canvas.yview_scroll(_wheel_units(event), "units")

        for sequence in WHEEL_EVENTS:
            canvas.bind_all(sequence, _on_mousewheel)
        self._canvas = canvas

        header = ttk.Frame(scroll_frame, style="TFrame", padding=(20, 20, 20, 10))
        header.pack(fill="x")
        ttk.Label(header, text="video2psp", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            header, text="Convert videos to a PSP-compatible format",
            style="SubHeader.TLabel"
        ).pack(anchor="w")

        body = ttk.Frame(scroll_frame, style="TFrame")
        body.pack(fill="both", expand=True)

        files = self._card(body, "Files")
        self._file_row(files, 1, "Input video", self.input_var, self._browse_input)
        output_entry = self._file_row(files, 2, "Output file", self.output_var, self._browse_output)
        output_entry.bind("<KeyRelease>", lambda _e: setattr(self, "output_user_edited", True))
        files.columnconfigure(1, weight=1)

        tracks = self._card(body, "Tracks")
        ttk.Label(tracks, text="Video", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=LABEL_PADY, padx=LABEL_PADX)
        self.video_combo = ttk.Combobox(tracks, state="disabled")
        self.video_combo.grid(row=1, column=1, columnspan=2, sticky="ew", pady=LABEL_PADY)

        ttk.Label(tracks, text="Audio", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=LABEL_PADY, padx=LABEL_PADX)
        self.audio_combo = ttk.Combobox(tracks, state="disabled")
        self.audio_combo.grid(row=2, column=1, columnspan=2, sticky="ew", pady=LABEL_PADY)

        ttk.Label(tracks, text="Subtitle", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=LABEL_PADY, padx=LABEL_PADX)
        self.subtitle_combo = ttk.Combobox(tracks, state="disabled")
        self.subtitle_combo.grid(row=3, column=1, columnspan=2, sticky="ew", pady=LABEL_PADY)

        self._file_row(tracks, 4, "External subtitle (optional)", self.external_subs_var, self._browse_external_subs)
        tracks.columnconfigure(1, weight=1)

        settings = self._card(body, "Encoding settings")
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Volume", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=LABEL_PADY, padx=LABEL_PADX)
        self.volume_spin = ttk.Spinbox(
            settings, from_=0.1, to=5.0, increment=0.1, textvariable=self.volume_var, width=8
        )
        self.volume_spin.grid(row=1, column=1, sticky="w", pady=LABEL_PADY)
        ttk.Label(settings, text="1.0 = original, 1.5 = 150%", style="Muted.TLabel").grid(
            row=1, column=2, sticky="w", padx=(16, 0)
        )

        ttk.Label(settings, text="Preset (speed)", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=LABEL_PADY, padx=LABEL_PADX)
        self.preset_combo = ttk.Combobox(
            settings, state="readonly", values=PRESETS, textvariable=self.preset_var, width=12
        )
        self.preset_combo.grid(row=2, column=1, sticky="w", pady=LABEL_PADY)
        ttk.Label(settings, text="faster = larger file", style="Muted.TLabel").grid(
            row=2, column=2, sticky="w", padx=(16, 0)
        )

        ttk.Label(settings, text="Quality (CRF)", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=LABEL_PADY, padx=LABEL_PADX)
        crf_frame = ttk.Frame(settings, style="Card.TFrame")
        crf_frame.grid(row=3, column=1, columnspan=2, sticky="ew", pady=LABEL_PADY)
        self.crf_scale = ttk.Scale(
            crf_frame, from_=0, to=51, orient="horizontal",
            variable=self.crf_var, command=self._on_crf_change
        )
        self.crf_scale.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.crf_value_label = ttk.Label(crf_frame, text=str(DEFAULT_CRF), style="Card.TLabel", width=3)
        self.crf_value_label.pack(side="right")

        ttk.Label(settings, text="Frame rate", style="Card.TLabel").grid(row=4, column=0, sticky="w", pady=LABEL_PADY, padx=LABEL_PADX)
        self.fps_combo = ttk.Combobox(
            settings, state="readonly", values=FPS_CHOICES, textvariable=self.fps_var, width=12
        )
        self.fps_combo.grid(row=4, column=1, sticky="w", pady=LABEL_PADY)
        self.fps_hint = ttk.Label(settings, text="keeps the video's rate (max 29.97)", style="Muted.TLabel")
        self.fps_hint.grid(row=4, column=2, sticky="w", padx=(16, 0))
        self.fps_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_fps_hint())
        self.video_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_fps_hint())

        ttk.Checkbutton(
            settings, text="Hardware decoding (faster, falls back to CPU automatically)",
            variable=self.hwaccel_var, style="Card.TCheckbutton",
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=LABEL_PADY)

        progress_card = self._card(body, "Progress")
        progress_card.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress_card, orient="horizontal", mode="determinate", maximum=100)
        self.progress.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        ttk.Label(progress_card, textvariable=self.status_var, style="Muted.TLabel").grid(
            row=2, column=0, columnspan=3, sticky="w"
        )
        self.log_text = tk.Text(
            progress_card, height=6, bg="#f8f9fc", fg=COLORS["text"], relief="flat",
            state="disabled", font=("Consolas", 9), wrap="word", bd=0
        )
        self.log_text.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))

        self._prevent_wheel_hijack()

    def _prevent_wheel_hijack(self) -> None:
        """Comboboxes/Spinbox/Scale normally consume the mouse wheel to change
        their own value; redirect it to scroll the page instead, since that's
        what users expect while hovering over the settings form."""
        canvas = self._canvas

        def _scroll_and_break(event) -> str:
            canvas.yview_scroll(_wheel_units(event), "units")
            return "break"

        for widget in (
            self.video_combo, self.audio_combo, self.subtitle_combo,
            self.preset_combo, self.volume_spin, self.crf_scale, self.fps_combo,
        ):
            for sequence in WHEEL_EVENTS:
                widget.bind(sequence, _scroll_and_break)

    def _card(self, parent: tk.Widget, title: str) -> ttk.Frame:
        outer = ttk.Frame(parent, style="TFrame", padding=(20, 0, 20, 14))
        outer.pack(fill="x")
        border = tk.Frame(outer, bg=COLORS["card"], highlightbackground=COLORS["border"], highlightthickness=1, bd=0)
        border.pack(fill="x")
        inner = ttk.Frame(border, style="Card.TFrame", padding=16)
        inner.pack(fill="both", expand=True)
        ttk.Label(inner, text=title, style="CardTitle.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        return inner

    def _file_row(self, parent: ttk.Frame, row: int, label_text: str, var: tk.StringVar, command) -> ttk.Entry:
        ttk.Label(parent, text=label_text, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=LABEL_PADY, padx=LABEL_PADX)
        entry = ttk.Entry(parent, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew", pady=LABEL_PADY, padx=(0, 8))
        ttk.Button(parent, text="Browse...", command=command).grid(row=row, column=2, pady=LABEL_PADY)
        return entry

    # -- Callbacks ---------------------------------------------------------

    def _on_crf_change(self, value: str) -> None:
        rounded = int(round(float(value)))
        self.crf_value_label.configure(text=str(rounded))

    def _selected_frame_rate(self) -> Fraction:
        choice = self.fps_var.get()
        requested = None if choice == FPS_SOURCE else parse_frame_rate(choice)
        video_index = self.video_combo.current()
        source = self.video_tracks[video_index].frame_rate if self.video_tracks and video_index >= 0 else None
        return output_frame_rate(source, requested)

    def _update_fps_hint(self) -> None:
        if not self.video_tracks:
            self.fps_hint.configure(text="keeps the video's rate (max 29.97)")
            return
        self.fps_hint.configure(text=f"output: {format_frame_rate(self._selected_frame_rate())} fps")

    def _browse_input(self) -> None:
        path = filedialog.askopenfilename(title="Select video", filetypes=VIDEO_FILETYPES)
        if not path:
            return
        self.input_var.set(path)
        if not self.output_user_edited:
            self.output_var.set(str(default_output_path(path)))
        self._reset_tracks()
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

        self._update_fps_hint()
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
        if Path(output_file).exists():
            if not messagebox.askyesno("Overwrite?", f"'{Path(output_file).name}' already exists. Overwrite?"):
                return

        try:
            volume = float(self.volume_var.get())
            if volume <= 0:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror("Error", "Invalid volume. Use a number greater than 0.")
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
            )
        except VideoConverterError as e:
            messagebox.showerror("Error", str(e))
            return

        self._cancel_requested = False
        self._set_converting(True)
        self._log(f"Starting conversion: {Path(input_file).name} -> {Path(output_file).name}")
        if self.duration > 0:
            self.progress.configure(mode="determinate", value=0)
        else:
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)

        threading.Thread(target=self._run_ffmpeg, args=(cmd, self.duration), daemon=True).start()

    def _run_ffmpeg(self, cmd: list[str], duration: float) -> None:
        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
            )
        except FileNotFoundError:
            self.msg_queue.put(("convert_error", "ffmpeg not found. Make sure it's installed and in your PATH."))
            return

        stderr_lines: list[str] = []

        def _drain_stderr() -> None:
            if self.proc is None or self.proc.stderr is None:
                return
            for line in self.proc.stderr:
                stderr_lines.append(line.rstrip())

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        if self.proc.stdout is not None:
            for line in self.proc.stdout:
                line = line.strip()
                if line.startswith("out_time="):
                    elapsed = _parse_out_time(line.split("=", 1)[1])
                    pct = min(100.0, (elapsed / duration) * 100) if duration > 0 else None
                    self.msg_queue.put(("progress", pct))
                elif line == "progress=end":
                    break

        returncode = self.proc.wait()
        stderr_thread.join(timeout=2)

        if self._cancel_requested:
            self.msg_queue.put(("convert_cancelled", None))
        elif returncode == 0:
            self.msg_queue.put(("convert_done", None))
        else:
            tail = "\n".join(stderr_lines[-15:])
            self.msg_queue.put(("convert_error", f"ffmpeg exited with code {returncode}.\n{tail}"))

    def _set_converting(self, active: bool) -> None:
        self.convert_btn.configure(state="disabled" if active else "normal")
        self.cancel_btn.configure(state="normal" if active else "disabled")
        combo_state = "disabled" if active else "readonly"
        if self.video_tracks:
            self.video_combo.configure(state=combo_state)
        if self.audio_tracks:
            self.audio_combo.configure(state=combo_state)
        if self.subtitle_tracks:
            self.subtitle_combo.configure(state=combo_state)

    # -- Shared helpers --------------------------------------------------

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()

                if kind == "analyzed":
                    token, info = payload
                    if token == self._analysis_token:
                        self._populate_tracks(info)
                        self._set_status(
                            f"Found {len(info.video)} video track(s), {len(info.audio)} audio track(s), "
                            f"{len(info.subtitle)} subtitle track(s)."
                        )
                elif kind == "analyze_error":
                    token, message = payload
                    if token == self._analysis_token:
                        messagebox.showerror("Error analyzing file", message)
                        self._set_status("Failed to analyze the file.")
                elif kind == "progress":
                    if payload is not None:
                        self.progress.configure(value=payload)
                        self._set_status(f"Converting... {payload:.0f}%")
                    else:
                        self._set_status("Converting...")
                elif kind == "convert_done":
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=100)
                    self._set_status("Conversion complete!")
                    self._log("Conversion completed successfully.")
                    self._set_converting(False)
                    self.open_folder_btn.configure(state="normal")
                elif kind == "convert_cancelled":
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=0)
                    self._set_status("Conversion cancelled.")
                    self._log("Conversion cancelled by user.")
                    self._set_converting(False)
                elif kind == "convert_error":
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=0)
                    self._set_status("Conversion failed.")
                    self._log(f"Error: {payload}")
                    messagebox.showerror("Conversion error", payload)
                    self._set_converting(False)
        except queue.Empty:
            pass
        finally:
            self.root.after(150, self._poll_queue)


def launch_gui() -> None:
    """Launch the video2psp GUI window."""
    root = tk.Tk()
    PSPConverterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
