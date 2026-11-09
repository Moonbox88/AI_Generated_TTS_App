"""Light and dark themes for the Tkinter GUI, built on ttk's "clam" theme.

No extra dependency: "clam" ships with Tk and, unlike the native themes,
lets every colour be overridden. Plain tk widgets (Text) are not styled by
ttk, so they are themed separately with style_text().

Only Basic Multilingual Plane symbols are used for icons: Tk 8.6 cannot
display characters above U+FFFF (most emoji) and raises an error.
"""

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

PALETTES: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#f3f4f6", "card": "#ffffff", "border": "#e2e5e9",
        "text": "#1f2328", "muted": "#6b7280",
        "accent": "#4f46e5", "accent_hover": "#4338ca", "accent_text": "#ffffff",
        "field": "#ffffff", "field_border": "#d0d5dc", "select": "#c7d2fe",
        "hover": "#eef0f3", "trough": "#e5e7eb",
        "danger": "#c62828", "success": "#1a7f37",
    },
    "dark": {
        "bg": "#15171c", "card": "#1e2128", "border": "#2c3038",
        "text": "#e6e8eb", "muted": "#9aa1ab",
        "accent": "#818cf8", "accent_hover": "#a5b4fc", "accent_text": "#0f1117",
        "field": "#262a32", "field_border": "#3a3f4a", "select": "#3f3c8f",
        "hover": "#2c3038", "trough": "#2c3038",
        "danger": "#f87171", "success": "#4ade80",
    },
}


def setup_fonts(root: tk.Misc) -> dict[str, tkfont.Font]:
    """Slightly larger body text plus title/heading fonts in the same family."""
    base = tkfont.nametofont("TkDefaultFont")
    base.configure(size=10)
    tkfont.nametofont("TkTextFont").configure(size=10)
    family = base.actual("family")
    return {
        "title": tkfont.Font(root, family=family, size=16, weight="bold"),
        "heading": tkfont.Font(root, family=family, size=11, weight="bold"),
        "body": base,
        "button": tkfont.Font(root, family=family, size=10, weight="bold"),
        "text": tkfont.Font(root, family=family, size=11),
    }


def apply_theme(root: tk.Misc, name: str, fonts: dict[str, tkfont.Font]) -> dict[str, str]:
    """Configure every ttk style used by the app. Returns the palette."""
    p = PALETTES[name]
    style = ttk.Style(root)
    style.theme_use("clam")

    flat = {"lightcolor": p["card"], "darkcolor": p["card"]}

    style.configure(".", background=p["bg"], foreground=p["text"],
                    bordercolor=p["border"], focuscolor=p["accent"],
                    troughcolor=p["trough"], selectbackground=p["select"],
                    selectforeground=p["text"], font=fonts["body"])
    style.configure("TFrame", background=p["bg"])
    style.configure("Card.TFrame", background=p["card"], bordercolor=p["border"],
                    relief="solid", borderwidth=1, **flat)
    style.configure("Inner.TFrame", background=p["card"])

    style.configure("TLabel", background=p["bg"], foreground=p["text"])
    style.configure("Title.TLabel", font=fonts["title"])
    style.configure("Subtitle.TLabel", foreground=p["muted"])
    style.configure("Card.TLabel", background=p["card"])
    style.configure("Heading.Card.TLabel", font=fonts["heading"])
    style.configure("Muted.Card.TLabel", foreground=p["muted"])
    style.configure("Value.Card.TLabel", foreground=p["accent"], font=fonts["button"])
    style.configure("Chip.Card.TLabel", background=p["hover"], padding=(8, 2))
    style.configure("Warn.Card.TLabel", foreground=p["danger"])

    style.configure("Status.TLabel", background=p["card"], foreground=p["muted"],
                    padding=(12, 5))
    style.configure("Error.Status.TLabel", foreground=p["danger"])
    style.configure("Success.Status.TLabel", foreground=p["success"])

    # Buttons: neutral, accent (primary action) and ghost (icon-ish).
    style.configure("TButton", background=p["field"], foreground=p["text"],
                    bordercolor=p["field_border"], lightcolor=p["field"],
                    darkcolor=p["field"], padding=(12, 6), font=fonts["body"])
    style.map("TButton",
              background=[("disabled", p["card"]), ("active", p["hover"])],
              foreground=[("disabled", p["muted"])],
              lightcolor=[("active", p["hover"])], darkcolor=[("active", p["hover"])])
    style.configure("Accent.TButton", background=p["accent"], foreground=p["accent_text"],
                    bordercolor=p["accent"], lightcolor=p["accent"], darkcolor=p["accent"],
                    padding=(18, 7), font=fonts["button"])
    style.map("Accent.TButton",
              background=[("disabled", p["trough"]), ("active", p["accent_hover"])],
              foreground=[("disabled", p["muted"])],
              bordercolor=[("disabled", p["trough"]), ("active", p["accent_hover"])],
              lightcolor=[("disabled", p["trough"]), ("active", p["accent_hover"])],
              darkcolor=[("disabled", p["trough"]), ("active", p["accent_hover"])])
    style.configure("Ghost.TButton", background=p["card"], bordercolor=p["card"],
                    lightcolor=p["card"], darkcolor=p["card"], padding=(6, 3))
    style.map("Ghost.TButton",
              background=[("disabled", p["card"]), ("active", p["hover"])],
              bordercolor=[("active", p["hover"])],
              lightcolor=[("active", p["hover"])], darkcolor=[("active", p["hover"])])
    style.configure("Header.Ghost.TButton", background=p["bg"], bordercolor=p["bg"],
                    lightcolor=p["bg"], darkcolor=p["bg"])

    # Inputs.
    field = {"fieldbackground": p["field"], "background": p["field"],
             "foreground": p["text"], "bordercolor": p["field_border"],
             "lightcolor": p["field"], "darkcolor": p["field"],
             "insertcolor": p["text"], "padding": 5}
    style.configure("TEntry", **field)
    style.map("TEntry", bordercolor=[("focus", p["accent"])],
              lightcolor=[("focus", p["accent"])], darkcolor=[("focus", p["accent"])])
    style.configure("TCombobox", arrowcolor=p["text"], selectbackground=p["field"],
                    selectforeground=p["text"], **field)
    style.map("TCombobox",
              fieldbackground=[("readonly", p["field"]), ("disabled", p["card"])],
              foreground=[("disabled", p["muted"])],
              arrowcolor=[("disabled", p["muted"])],
              bordercolor=[("focus", p["accent"]), ("hover", p["accent"])],
              background=[("active", p["hover"])])
    style.configure("TCheckbutton", background=p["card"], foreground=p["text"],
                    indicatorbackground=p["field"], indicatorforeground=p["accent_text"],
                    indicatormargin=(0, 0, 6, 0), focuscolor=p["card"])
    style.map("TCheckbutton",
              indicatorbackground=[("selected", p["accent"])],
              background=[("active", p["card"])])

    style.configure("Vertical.TScrollbar", background=p["trough"], troughcolor=p["field"],
                    bordercolor=p["field"], arrowcolor=p["muted"],
                    lightcolor=p["trough"], darkcolor=p["trough"], gripcount=0)
    style.map("Vertical.TScrollbar", background=[("active", p["field_border"])])

    # Sliders and progress.
    style.configure("Horizontal.TScale", background=p["accent"], troughcolor=p["trough"],
                    bordercolor=p["card"], lightcolor=p["accent"], darkcolor=p["accent"],
                    gripcount=0, sliderthickness=14)
    style.map("Horizontal.TScale", background=[("active", p["accent_hover"])])
    style.configure("Horizontal.TProgressbar", background=p["accent"],
                    troughcolor=p["trough"], bordercolor=p["trough"],
                    lightcolor=p["accent"], darkcolor=p["accent"], thickness=4)

    # Combobox drop-down lists are classic Tk listboxes, styled via options
    # (for lists created later) ...
    for key, value in (("background", p["field"]), ("foreground", p["text"]),
                       ("selectBackground", p["accent"]),
                       ("selectForeground", p["accent_text"])):
        root.option_add(f"*TCombobox*Listbox.{key}", value)
    root.configure(background=p["bg"])
    return p


def style_combobox_list(combobox: ttk.Combobox, p: dict[str, str]) -> None:
    """... and directly, for lists that already exist (theme switch)."""
    try:
        popdown = combobox.tk.eval(f"ttk::combobox::PopdownWindow {combobox}")
        combobox.tk.call(f"{popdown}.f.l", "configure",
                         "-background", p["field"], "-foreground", p["text"],
                         "-selectbackground", p["accent"],
                         "-selectforeground", p["accent_text"])
    except tk.TclError:
        pass


def style_text(widget: tk.Text, p: dict[str, str], readonly: bool = False) -> None:
    widget.configure(
        background=p["card"] if readonly else p["field"],
        foreground=p["muted"] if readonly else p["text"],
        insertbackground=p["text"], selectbackground=p["select"],
        selectforeground=p["text"], relief="flat", borderwidth=0,
        highlightthickness=1, highlightbackground=p["field_border"],
        highlightcolor=p["accent"], padx=10, pady=8)
