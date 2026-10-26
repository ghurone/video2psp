"""
Look of the video2psp GUI: color palettes, fonts and ttk styles.

ttk can't draw rounded corners, so cards, buttons, fields, the slider, the
progress bar and the checkbox are image elements painted here (anti-aliased,
no image files). Switching themes repaints the same images in place, so every
widget picks up the new colors without being rebuilt.
"""

import math
import subprocess
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

THEMES = {
    "light": {
        "bg": "#f4f5f9",
        "card": "#ffffff",
        "border": "#e2e4ec",
        "field": "#ffffff",
        "field_border": "#d3d6e2",
        "text": "#1f2233",
        "muted": "#6b7089",
        "accent": "#4361ee",
        "accent_hover": "#3651d4",
        "accent_disabled": "#b4bdf3",
        "accent_disabled_text": "#ffffff",
        "button": "#eef0f7",
        "button_hover": "#e1e4f0",
        "disabled_bg": "#f2f3f8",
        "disabled_text": "#a6aabb",
        "error": "#d93d42",
        "error_bg": "#fde8e8",
        "error_bg_hover": "#fbd5d5",
        "trough": "#e3e5ee",
        "knob": "#ffffff",
    },
    "dark": {
        "bg": "#15161c",
        "card": "#1e1f27",
        "border": "#2b2d39",
        "field": "#262834",
        "field_border": "#383b4c",
        "text": "#e7e8ef",
        "muted": "#9195aa",
        "accent": "#5b76f5",
        "accent_hover": "#7189f7",
        "accent_disabled": "#323c6e",
        "accent_disabled_text": "#7c84a8",
        "button": "#2a2c39",
        "button_hover": "#353849",
        "disabled_bg": "#22232c",
        "disabled_text": "#5b5e70",
        "error": "#ff6b70",
        "error_bg": "#3b2026",
        "error_bg_hover": "#4b272e",
        "trough": "#33364a",
        "knob": "#e7e8ef",
    },
}

# Button style prefix -> palette keys for (normal, hover, disabled) fill and the color behind it
BUTTONS = {
    "": ("button", "button_hover", "disabled_bg", "card"),
    "Accent.": ("accent", "accent_hover", "accent_disabled", "card"),
    "Danger.": ("error_bg", "error_bg_hover", "disabled_bg", "card"),
    "Ghost.": ("bg", "button", "bg", "bg"),
}

CHECK_BOX = 18  # checkbox size; its image is wider to leave a gap before the label

IMAGE_SIZES = {
    "card": (28, 28),
    **{f"{prefix}button{state}": (20, 20) for prefix in BUTTONS for state in ("", "_hover", "_disabled")},
    "field": (20, 20),
    "field_hover": (20, 20),
    "field_focus": (20, 20),
    "field_disabled": (20, 20),
    "track": (12, 4),
    "knob": (18, 18),
    "knob_hover": (18, 18),
    "knob_disabled": (18, 18),
    "progress_trough": (12, 6),
    "progress_bar": (12, 6),
    **{f"check_{s}": (CHECK_BOX + 8, CHECK_BOX) for s in ("off", "off_hover", "on", "off_disabled", "on_disabled")},
}


def _command_output(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def system_prefers_dark() -> bool:
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            ) as key:
                return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
        except OSError:
            return False
    if sys.platform == "darwin":
        return _command_output(["defaults", "read", "-g", "AppleInterfaceStyle"]).strip() == "Dark"
    # GNOME and most GTK desktops
    scheme = _command_output(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
    if "dark" in scheme:
        return True
    return "dark" in _command_output(["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"]).lower()


def set_title_bar_dark(root: tk.Tk, dark: bool) -> None:
    """Match the Windows title bar to the theme (DWMWA_USE_IMMERSIVE_DARK_MODE)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
    except (AttributeError, OSError):
        pass


def pick_fonts(root: tk.Tk) -> dict:
    available = set(tkfont.families(root))

    def first(*families: str) -> str | None:
        return next((f for f in families if f in available), None)

    # Tk's points are pixels on macOS, so its UI text needs bigger numbers to match
    body, small, title = (13, 11, 22) if sys.platform == "darwin" else (10, 9, 18)
    icons = first("Segoe Fluent Icons", "Segoe MDL2 Assets")
    segoe = first("Segoe UI Variable Text", "Segoe UI")
    if segoe:
        # Windows: Segoe has real semibold faces, which look better than synthetic bold
        fonts = {
            "body": (segoe, body),
            "small": (segoe, small),
            "heading": (first("Segoe UI Variable Text Semibold", "Segoe UI Semibold") or segoe, body),
            "title": (first("Segoe UI Variable Display Semib", "Segoe UI Semibold") or segoe, title),
        }
    else:
        # macOS/Linux: the platform's own UI font (San Francisco, Cantarell, Ubuntu, DejaVu Sans...),
        # with bold headings. Font objects (not family names) also cover macOS' hidden system font.
        system = tkfont.nametofont("TkDefaultFont", root=root)

        def derive(size: int, weight: str = "normal") -> tkfont.Font:
            font = system.copy()
            font.configure(size=size, weight=weight)
            return font

        fonts = {
            "body": derive(body),
            "small": derive(small),
            "heading": derive(body, "bold"),
            "title": derive(title, "bold"),
        }
    if icons:
        fonts["icon"] = (icons, 12)
    else:
        # The ☀/☾ text fallback needs to be bigger than body text to read as an icon
        fonts["icon"] = tkfont.Font(root=root, font=fonts["body"])
        fonts["icon"].configure(size=body + 4)
    fonts["has_icons"] = icons is not None
    return fonts


# -- Painting ----------------------------------------------------------------

def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _coverage(distance: float) -> float:
    """How much of a pixel a shape covers, from the signed distance to its edge."""
    return min(max(0.5 - distance, 0.0), 1.0)


def _box_distance(x: float, y: float, w: float, h: float, r: float) -> float:
    """Signed distance from (x, y) to a w x h rounded rectangle at the origin."""
    qx = abs(x - w / 2) - (w / 2 - r)
    qy = abs(y - h / 2) - (h / 2 - r)
    return math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - r


def _segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _paint(image: tk.PhotoImage, shade) -> None:
    """Fill the image with shade(x, y) -> rgb, evaluated at each pixel center."""
    rows = []
    for y in range(image.height()):
        row = (shade(x + 0.5, y + 0.5) for x in range(image.width()))
        rows.append("{" + " ".join("#%02x%02x%02x" % rgb for rgb in row) + "}")
    image.put(" ".join(rows))


def _paint_box(image: tk.PhotoImage, radius: float, fill: str, behind: str,
               outline: str | None = None, outline_width: float = 1.0) -> None:
    w, h = image.width(), image.height()
    fill_rgb, behind_rgb = _rgb(fill), _rgb(behind)
    edge_rgb = _rgb(outline) if outline else fill_rgb

    def shade(x: float, y: float) -> tuple:
        d = _box_distance(x, y, w, h, radius)
        color = _mix(behind_rgb, edge_rgb, _coverage(d))
        return _mix(color, fill_rgb, _coverage(d + outline_width)) if outline else color

    _paint(image, shade)


def _paint_knob(image: tk.PhotoImage, c: dict, dot: str, dot_radius: float) -> None:
    size = image.width()
    center, outer = size / 2, size / 2 - 0.5
    card, ring, knob, dot_rgb = _rgb(c["card"]), _rgb(c["field_border"]), _rgb(c["knob"]), _rgb(dot)

    def shade(x: float, y: float) -> tuple:
        d = math.hypot(x - center, y - center)
        color = _mix(card, ring, _coverage(d - outer))
        color = _mix(color, knob, _coverage(d - (outer - 1)))
        return _mix(color, dot_rgb, _coverage(d - dot_radius))

    _paint(image, shade)


def _paint_check(image: tk.PhotoImage, c: dict, fill: str, outline: str | None, mark: str | None) -> None:
    box = CHECK_BOX
    card, fill_rgb = _rgb(c["card"]), _rgb(fill)
    edge_rgb = _rgb(outline) if outline else fill_rgb
    mark_rgb = _rgb(mark) if mark else None

    def shade(x: float, y: float) -> tuple:
        if x > box:
            return card
        d = _box_distance(x, y, box, box, 4)
        color = _mix(card, edge_rgb, _coverage(d))
        color = _mix(color, fill_rgb, _coverage(d + 1))
        if mark_rgb:
            stroke = min(_segment_distance(x, y, 4.5, 9.5, 7.5, 12.5),
                         _segment_distance(x, y, 7.5, 12.5, 13.5, 5.5))
            color = _mix(color, mark_rgb, _coverage(stroke - 1.0))
        return color

    _paint(image, shade)


# -- Theme ---------------------------------------------------------------------

class Theme:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.style = ttk.Style(root)
        self.style.theme_use("clam")
        self.fonts = pick_fonts(root)
        # Entries, comboboxes and spinboxes draw their text with Tk's named fonts,
        # not the ttk style font: make them match the rest of the UI
        body = tkfont.Font(root=root, font=self.fonts["body"]).actual()
        for name in ("TkDefaultFont", "TkTextFont"):
            tkfont.nametofont(name, root=root).configure(family=body["family"], size=body["size"])
        self.images = {
            name: tk.PhotoImage(master=root, width=w, height=h) for name, (w, h) in IMAGE_SIZES.items()
        }
        self.name = ""
        self.colors: dict = {}
        self._create_elements()

    def apply(self, name: str) -> None:
        self.name = name
        self.colors = THEMES[name]
        self._paint_images(self.colors)
        self._configure_styles(self.colors)
        self.root.configure(bg=self.colors["bg"])
        set_title_bar_dark(self.root, name == "dark")

    def _paint_images(self, c: dict) -> None:
        img = self.images
        _paint_box(img["card"], 10, c["card"], c["bg"], outline=c["border"])
        for prefix, (normal, hover, disabled, behind) in BUTTONS.items():
            for state, key in (("", normal), ("_hover", hover), ("_disabled", disabled)):
                _paint_box(img[f"{prefix}button{state}"], 6, c[key], c[behind])
        _paint_box(img["field"], 6, c["field"], c["card"], outline=c["field_border"])
        _paint_box(img["field_hover"], 6, c["field"], c["card"], outline=c["muted"])
        _paint_box(img["field_focus"], 6, c["field"], c["card"], outline=c["accent"], outline_width=1.6)
        _paint_box(img["field_disabled"], 6, c["disabled_bg"], c["card"], outline=c["border"])
        _paint_box(img["track"], 2, c["trough"], c["card"])
        _paint_knob(img["knob"], c, c["accent"], 4)
        _paint_knob(img["knob_hover"], c, c["accent_hover"], 5)
        _paint_knob(img["knob_disabled"], c, c["disabled_text"], 4)
        _paint_box(img["progress_trough"], 3, c["trough"], c["card"])
        _paint_box(img["progress_bar"], 3, c["accent"], c["trough"])
        _paint_check(img["check_off"], c, c["field"], c["field_border"], None)
        _paint_check(img["check_off_hover"], c, c["field"], c["muted"], None)
        _paint_check(img["check_on"], c, c["accent"], None, "#ffffff")
        _paint_check(img["check_off_disabled"], c, c["disabled_bg"], c["border"], None)
        _paint_check(img["check_on_disabled"], c, c["disabled_text"], None, c["disabled_bg"])

    def _create_elements(self) -> None:
        style, img = self.style, self.images

        style.element_create("Rounded.Card.border", "image", img["card"], border=10, sticky="nsew")
        style.layout("CardBox.TFrame", [("Rounded.Card.border", {"sticky": "nsew"})])

        for prefix in BUTTONS:
            name = f"{prefix}button"
            element = f"{prefix.rstrip('.') or 'Plain'}Rounded.Button.border"
            style.element_create(
                element, "image", img[name],
                ("disabled", img[f"{name}_disabled"]), ("pressed", img[f"{name}_hover"]),
                ("active", img[f"{name}_hover"]), border=7, padding=(8, 5), sticky="nsew",
            )
            style.layout(f"{prefix}TButton", [(element, {"sticky": "nsew", "children": [
                ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]}),
            ]})])

        field_states = (
            ("disabled", img["field_disabled"]), ("focus", img["field_focus"]), ("hover", img["field_hover"]),
        )
        for widget in ("Entry", "Combobox", "Spinbox"):
            style.element_create(
                f"Rounded.{widget}.field", "image", img["field"], *field_states,
                border=7, padding=(8, 5), sticky="nsew",
            )
        style.layout("TEntry", [("Rounded.Entry.field", {"sticky": "nsew", "children": [
            ("Entry.padding", {"sticky": "nsew", "children": [("Entry.textarea", {"sticky": "nsew"})]}),
        ]})])
        style.layout("TCombobox", [("Rounded.Combobox.field", {"sticky": "nsew", "children": [
            ("Combobox.downarrow", {"side": "right", "sticky": "ns"}),
            ("Combobox.padding", {"expand": "1", "sticky": "nsew", "children": [
                ("Combobox.textarea", {"sticky": "nsew"}),
            ]}),
        ]})])
        style.layout("TSpinbox", [("Rounded.Spinbox.field", {"sticky": "nsew", "children": [
            ("null", {"side": "right", "sticky": "", "children": [
                ("Spinbox.uparrow", {"side": "top", "sticky": "e"}),
                ("Spinbox.downarrow", {"side": "bottom", "sticky": "e"}),
            ]}),
            ("Spinbox.padding", {"sticky": "nsew", "children": [("Spinbox.textarea", {"sticky": "nsew"})]}),
        ]})])

        # A thin track with a round knob (no focus ring element: clam draws it as a box outline)
        style.element_create("Rounded.Scale.trough", "image", img["track"], border=(2, 0), sticky="ew")
        style.element_create(
            "Rounded.Scale.slider", "image", img["knob"],
            ("disabled", img["knob_disabled"]), ("pressed", img["knob_hover"]), ("active", img["knob_hover"]),
        )
        style.layout("Horizontal.TScale", [("Rounded.Scale.trough", {"sticky": "ew", "children": [
            ("Rounded.Scale.slider", {"side": "left", "sticky": ""}),
        ]})])

        style.element_create(
            "Rounded.Progressbar.trough", "image", img["progress_trough"], border=(3, 0), sticky="ew",
        )
        style.element_create(
            "Rounded.Progressbar.pbar", "image", img["progress_bar"], border=(3, 0), sticky="nsew",
        )
        style.layout("Horizontal.TProgressbar", [("Rounded.Progressbar.trough", {"sticky": "nsew", "children": [
            ("Rounded.Progressbar.pbar", {"side": "left", "sticky": "ns"}),
        ]})])

        style.element_create(
            "Rounded.Checkbutton.indicator", "image", img["check_off"],
            ("disabled selected", img["check_on_disabled"]), ("disabled", img["check_off_disabled"]),
            ("selected", img["check_on"]), ("active", img["check_off_hover"]),
        )
        style.layout("Card.TCheckbutton", [("Checkbutton.padding", {"sticky": "nsew", "children": [
            ("Rounded.Checkbutton.indicator", {"side": "left", "sticky": ""}),
            ("Checkbutton.label", {"side": "left", "sticky": "w"}),
        ]})])

    def _configure_styles(self, c: dict) -> None:
        style, fonts = self.style, self.fonts
        style.configure(
            ".", background=c["bg"], foreground=c["text"], font=fonts["body"],
            bordercolor=c["border"], lightcolor=c["border"], darkcolor=c["border"],
            troughcolor=c["trough"], selectbackground=c["accent"], selectforeground="#ffffff",
            insertcolor=c["text"], fieldbackground=c["field"],
        )
        style.configure("TFrame", background=c["bg"])
        style.configure("Card.TFrame", background=c["card"])
        style.configure("TLabel", background=c["bg"], foreground=c["text"])
        style.configure("Title.TLabel", font=fonts["title"])
        style.configure("Subtitle.TLabel", foreground=c["muted"])
        style.configure("Card.TLabel", background=c["card"])
        style.configure("CardTitle.TLabel", background=c["card"], font=fonts["heading"])
        style.configure("Muted.TLabel", background=c["card"], foreground=c["muted"], font=fonts["small"])
        style.configure("Value.TLabel", background=c["card"], font=fonts["heading"])
        style.configure("Status.TLabel", background=c["card"], foreground=c["muted"])

        # The arrow buttons inside fields are clam boxes: make them blend with the field
        arrow = {
            "background": c["field"], "bordercolor": c["field"], "lightcolor": c["field"],
            "darkcolor": c["field"], "arrowcolor": c["muted"], "arrowsize": 12,
        }
        disabled_arrow = [("disabled", c["disabled_bg"])]
        arrow_map = {
            "background": disabled_arrow, "bordercolor": disabled_arrow,
            "lightcolor": disabled_arrow, "darkcolor": disabled_arrow,
            "arrowcolor": [("disabled", c["disabled_text"]), ("active", c["text"])],
        }
        text_map = {"foreground": [("disabled", c["disabled_text"])]}
        style.configure("TEntry", foreground=c["text"], insertcolor=c["text"], padding=1)
        style.map("TEntry", **text_map)
        style.configure("TSpinbox", foreground=c["text"], insertcolor=c["text"], padding=1, **arrow)
        style.map("TSpinbox", **text_map, **arrow_map)
        style.configure("TCombobox", foreground=c["text"], padding=1, **arrow)
        style.map(
            "TCombobox", **arrow_map, foreground=[("disabled", c["disabled_text"])],
            # Readonly comboboxes would otherwise show their text as selected
            selectbackground=[("readonly", c["field"])],
            selectforeground=[("disabled", c["disabled_text"]), ("readonly", c["text"])],
        )

        # Same height as the fields next to them
        buttons = {
            "": (c["text"], c["disabled_text"], fonts["body"], (6, 1)),
            "Accent.": ("#ffffff", c["accent_disabled_text"], fonts["heading"], (16, 1)),
            "Danger.": (c["error"], c["disabled_text"], fonts["body"], (6, 1)),
            "Ghost.": (c["text"], c["disabled_text"], fonts["icon"], (0, 1)),
        }
        for prefix, (fg, disabled_fg, font, padding) in buttons.items():
            style.configure(f"{prefix}TButton", foreground=fg, font=font, padding=padding, anchor="center")
            style.map(f"{prefix}TButton", foreground=[("disabled", disabled_fg)])

        # clam repaints these widgets' background in other colors when active/disabled;
        # around the drawn images it has to stay the card color
        on_card = [("disabled", c["card"]), ("active", c["card"])]
        style.configure("Card.TCheckbutton", background=c["card"], foreground=c["text"])
        style.map("Card.TCheckbutton", background=on_card, foreground=[("disabled", c["disabled_text"])])
        style.configure("Horizontal.TScale", background=c["card"])
        style.map("Horizontal.TScale", background=on_card)
        style.configure("Horizontal.TProgressbar", background=c["card"])
        style.map("Horizontal.TProgressbar", background=on_card)

        # The dropdown lists are plain Tk listboxes, outside the ttk styles
        listbox = {"background": c["field"], "foreground": c["text"], "selectBackground": c["accent"],
                   "selectForeground": "#ffffff", "font": fonts["body"]}
        for option, value in listbox.items():
            self.root.option_add(f"*TCombobox*Listbox.{option}", value)

    def style_dropdowns(self, combos: list[ttk.Combobox]) -> None:
        """Recolor dropdown lists that already exist (option_add only affects new ones)."""
        c = self.colors
        for combo in combos:
            try:
                popdown = combo.tk.call("ttk::combobox::PopdownWindow", combo)
                combo.tk.call(
                    f"{popdown}.f.l", "configure", "-background", c["field"], "-foreground", c["text"],
                    "-selectbackground", c["accent"], "-selectforeground", "#ffffff",
                )
            except tk.TclError:
                pass
