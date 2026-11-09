#!/usr/bin/env python3
"""Text-to-Speech GUI — Phase 2 (Tkinter)."""

import os
import pathlib
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import gui_theme
import tts
from parsers import extract_text
from render_cache import RenderCache, RenderKey
from translator import iter_translate
from tts import Playback, speak
from voices import (AUTO_DETECT, DEFAULT_LANG, DEFAULT_SOURCE, DEFAULT_VOICE,
                    LANGUAGES, get_language, needs_translation, source_languages,
                    source_name, voices_for_lang)

SUPPORTED_FILETYPES = [
    ("Documents", "*.txt *.pdf *.docx"),
    ("Text files", "*.txt"),
    ("PDF files", "*.pdf"),
    ("Word documents", "*.docx"),
    ("All files", "*.*"),
]

SHORTCUT_HINT = "Ctrl+Enter speak  ·  Ctrl+P pause  ·  Esc stop  ·  Ctrl+S save  ·  Ctrl+O open"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Text to Speech")
        self.minsize(660, 640)
        self.geometry(f"800x{min(900, self.winfo_screenheight() - 80)}")

        self._fonts = gui_theme.setup_fonts(self)
        self._theme = "light"
        self._palette = gui_theme.apply_theme(self, self._theme, self._fonts)

        self._file_path = tk.StringVar()
        self._file_name = tk.StringVar()
        self._voice = tk.StringVar(value=DEFAULT_VOICE)
        self._source = tk.StringVar(value=DEFAULT_SOURCE)
        self._output_path = tk.StringVar()
        self._status = tk.StringVar(value="Ready.")
        self._counts = tk.StringVar(value="0 words  ·  0 characters")
        self._translate_info = tk.StringVar()
        self._target_name = tk.StringVar()
        self._speed = tk.DoubleVar(value=1.0)
        self._volume = tk.DoubleVar(value=1.0)
        self._do_translate = tk.BooleanVar(value=False)

        # Comboboxes show names; these map them back to codes.
        self._lang_codes = {lang.name: code for code, lang in LANGUAGES.items()}
        self._source_codes = {name: code for code, name in source_languages()}
        self._voice_ids: dict[str, str] = {}  # combobox label -> voice id

        self._controller: Playback | None = None
        self._renders = RenderCache()  # last finished render, for instant Save

        self._build_ui()
        self._apply_widget_theme()
        self._bind_shortcuts()
        self._status.trace_add("write", self._on_status_changed)
        self._update_translate_controls()
        self._set_icon()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_icon(self):
        icon_path = pathlib.Path(__file__).parent / "assets" / "icon.png"
        if icon_path.exists():
            icon = tk.PhotoImage(file=str(icon_path))
            self.iconphoto(True, icon)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    # Rows of the main column. It uses grid rather than pack because only
    # grid lets one row (the text box) give up space when the window is too
    # short; pack would clip whatever was packed last, i.e. the buttons.
    ROW_HEADER, ROW_TEXT, ROW_VOICE, ROW_TRANSLATE, ROW_PREVIEW, ROW_OUTPUT, \
        ROW_ACTIONS, ROW_PROGRESS = range(8)

    def _card(self, parent, title: str, row: int):
        """A bordered section with a heading row. Returns (card, heading row)."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=(16, 12, 16, 14))
        card.grid(row=row, column=0, sticky="nsew", pady=(0, 10))
        head = ttk.Frame(card, style="Inner.TFrame")
        head.pack(fill="x", pady=(0, 8))
        ttk.Label(head, text=title, style="Heading.Card.TLabel").pack(side="left")
        return card, head

    def _build_ui(self):
        # Status bar first, so it keeps its place at the bottom when resizing.
        status_bar = ttk.Frame(self, style="Inner.TFrame")
        status_bar.pack(side="bottom", fill="x")
        self._status_label = ttk.Label(status_bar, textvariable=self._status,
                                       style="Status.TLabel")
        self._status_label.pack(side="left", fill="x", expand=True)
        ttk.Label(status_bar, text=SHORTCUT_HINT, style="Status.TLabel").pack(side="right")

        outer = ttk.Frame(self, padding=(20, 16, 20, 8))
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(self.ROW_TEXT, weight=1)  # the only row that flexes

        # --- Header ---
        header = ttk.Frame(outer)
        header.grid(row=self.ROW_HEADER, column=0, sticky="ew", pady=(0, 12))
        ttk.Label(header, text="Text to Speech", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Read, translate and save with Kokoro & Piper voices",
                  style="Subtitle.TLabel").pack(side="left", padx=(12, 0), pady=(6, 0))
        self._theme_btn = ttk.Button(header, style="Header.Ghost.TButton",
                                     command=self._toggle_theme)
        self._theme_btn.pack(side="right")

        self._build_text_card(outer)
        self._build_voice_card(outer)
        self._build_translate_card(outer)
        self._build_preview_card(outer)
        self._build_output_card(outer)
        self._build_actions(outer)

    def _build_text_card(self, parent):
        card, head = self._card(parent, "Text", self.ROW_TEXT)
        ttk.Button(head, text="Open file…", command=self._browse_file).pack(side="right")
        self._file_chip = ttk.Frame(head, style="Inner.TFrame")
        ttk.Label(self._file_chip, textvariable=self._file_name,
                  style="Chip.Card.TLabel").pack(side="left")
        ttk.Button(self._file_chip, text="✕", width=2, style="Ghost.TButton",
                   command=self._clear_file).pack(side="left", padx=(2, 0))

        box = ttk.Frame(card, style="Inner.TFrame")
        box.pack(fill="both", expand=True)
        self._text_box = tk.Text(box, height=6, wrap="word", undo=True,
                                 font=self._fonts["text"])
        scroll = ttk.Scrollbar(box, command=self._text_box.yview)
        self._text_box.configure(yscrollcommand=scroll.set)
        self._text_box.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._text_box.bind("<<Modified>>", self._on_text_modified)

        ttk.Label(card, textvariable=self._counts,
                  style="Muted.Card.TLabel").pack(anchor="w", pady=(6, 0))

    def _build_voice_card(self, parent):
        card, _ = self._card(parent, "Voice", self.ROW_VOICE)
        grid = ttk.Frame(card, style="Inner.TFrame")
        grid.pack(fill="x")
        grid.columnconfigure((1, 3), weight=1, uniform="col")

        ttk.Label(grid, text="Language", style="Card.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 10))
        self._lang_cb = ttk.Combobox(grid, values=list(self._lang_codes), state="readonly")
        self._lang_cb.set(LANGUAGES[DEFAULT_LANG].name)
        self._lang_cb.grid(row=0, column=1, sticky="ew", padx=(0, 18))
        self._lang_cb.bind("<<ComboboxSelected>>", self._on_lang_changed)

        ttk.Label(grid, text="Voice", style="Card.TLabel").grid(
            row=0, column=2, sticky="w", padx=(0, 10))
        self._voice_cb = ttk.Combobox(grid, state="readonly")
        self._voice_cb.grid(row=0, column=3, sticky="ew")
        self._voice_cb.bind("<<ComboboxSelected>>", self._on_voice_changed)
        self._update_voice_list(DEFAULT_LANG)

        self._speed_label = self._slider(grid, 1, 0, "Speed", self._speed, 0.5, 2.0,
                                         self._on_speed_changed, "1.0×")
        self._vol_label = self._slider(grid, 1, 2, "Volume", self._volume, 0.0, 1.0,
                                       self._on_volume_changed, "100%")

    def _slider(self, grid, row, col, label, variable, low, high, command, initial):
        ttk.Label(grid, text=label, style="Card.TLabel").grid(
            row=row, column=col, sticky="w", padx=(0, 10), pady=(12, 0))
        cell = ttk.Frame(grid, style="Inner.TFrame")
        cell.grid(row=row, column=col + 1, sticky="ew", pady=(12, 0),
                  padx=(0, 18) if col == 0 else 0)
        value = ttk.Label(cell, text=initial, width=5, anchor="e", style="Value.Card.TLabel")
        value.pack(side="right")
        scale = ttk.Scale(cell, from_=low, to=high, variable=variable,
                          orient="horizontal", command=command)
        scale.pack(side="left", fill="x", expand=True, padx=(0, 8))
        if label == "Volume":
            self._vol_slider = scale
        return value

    def _build_translate_card(self, parent):
        card, head = self._card(parent, "Translate", self.ROW_TRANSLATE)
        ttk.Checkbutton(head, text="Translate before speaking", variable=self._do_translate,
                        command=self._update_translate_controls).pack(side="right")

        row = ttk.Frame(card, style="Inner.TFrame")
        row.pack(fill="x")
        ttk.Label(row, text="From", style="Card.TLabel").pack(side="left", padx=(0, 10))
        self._source_cb = ttk.Combobox(row, values=list(self._source_codes),
                                       state="readonly", width=20)
        self._source_cb.set(source_name(DEFAULT_SOURCE))
        self._source_cb.pack(side="left")
        self._source_cb.bind("<<ComboboxSelected>>", self._on_source_changed)
        self._swap_btn = ttk.Button(row, text="⇄", width=3, style="Ghost.TButton",
                                    command=self._on_swap)
        self._swap_btn.pack(side="left", padx=8)
        ttk.Label(row, text="To", style="Card.TLabel").pack(side="left", padx=(0, 10))
        ttk.Label(row, textvariable=self._target_name,
                  style="Value.Card.TLabel").pack(side="left")
        ttk.Label(row, text="(the voice's language)",
                  style="Muted.Card.TLabel").pack(side="left", padx=(6, 0))

        self._translate_info_label = ttk.Label(card, textvariable=self._translate_info,
                                               style="Muted.Card.TLabel")
        self._translate_info_label.pack(anchor="w", pady=(8, 0))

    def _build_preview_card(self, parent):
        # Built now, shown (grid) only while a translation is displayed.
        self._preview_card, head = self._card(parent, "Translation", self.ROW_PREVIEW)
        ttk.Button(head, text="Copy", style="Ghost.TButton",
                   command=self._copy_preview).pack(side="right")
        self._preview_box = tk.Text(self._preview_card, height=3, wrap="word",
                                    state="disabled", font=self._fonts["text"])
        self._preview_box.pack(fill="both", expand=True)
        self._preview_card.grid_remove()  # remembers its grid options for later

    def _build_output_card(self, parent):
        self._output_card, head = self._card(parent, "Save to", self.ROW_OUTPUT)
        ttk.Button(head, text="Browse…", command=self._browse_output).pack(side="right")
        ttk.Entry(head, textvariable=self._output_path).pack(
            side="left", fill="x", expand=True, padx=(14, 8))

    def _build_actions(self, parent):
        bar = ttk.Frame(parent)
        bar.grid(row=self.ROW_ACTIONS, column=0, sticky="ew", pady=(2, 6))
        self._speak_btn = ttk.Button(bar, text="▶  Speak", style="Accent.TButton",
                                     command=self._on_speak)
        self._speak_btn.pack(side="left")
        self._pause_btn = ttk.Button(bar, text="❚❚  Pause", command=self._on_pause_resume,
                                     state="disabled")
        self._pause_btn.pack(side="left", padx=(8, 0))
        self._stop_btn = ttk.Button(bar, text="■  Stop", command=self._on_stop,
                                    state="disabled")
        self._stop_btn.pack(side="left", padx=(8, 0))
        self._save_btn = ttk.Button(bar, text="Save audio", command=self._on_save)
        self._save_btn.pack(side="right")

        self._progress = ttk.Progressbar(parent, mode="indeterminate")
        self._progress.grid(row=self.ROW_PROGRESS, column=0, sticky="ew", pady=(4, 6))
        self._progress.grid_remove()  # shown only while a job runs

    def _show_progress(self, running: bool):
        if running:
            self._progress.grid()
            self._progress.start(12)
        else:
            self._progress.stop()
            self._progress.grid_remove()

    # ------------------------------------------------------------------
    # Theme and shortcuts
    # ------------------------------------------------------------------

    def _apply_widget_theme(self):
        p = self._palette
        gui_theme.style_text(self._text_box, p)
        gui_theme.style_text(self._preview_box, p, readonly=True)
        for combobox in (self._lang_cb, self._voice_cb, self._source_cb):
            gui_theme.style_combobox_list(combobox, p)
        self._theme_btn.config(text="☾  Dark" if self._theme == "light" else "☀  Light")
        self._on_status_changed()

    def _toggle_theme(self):
        self._theme = "dark" if self._theme == "light" else "light"
        self._palette = gui_theme.apply_theme(self, self._theme, self._fonts)
        self._apply_widget_theme()

    def _bind_shortcuts(self):
        def via(button):
            def handler(_event):
                if button.instate(["!disabled"]):
                    button.invoke()
                return "break"  # e.g. stop Ctrl+Enter also inserting a newline
            return handler

        def open_file(_event):
            self._browse_file()
            return "break"  # Tk's Text binds Ctrl+O to "insert newline"

        bindings = {"<Control-Return>": via(self._speak_btn),
                    "<Control-s>": via(self._save_btn),
                    "<Control-p>": via(self._pause_btn),
                    "<Escape>": via(self._stop_btn),
                    "<Control-o>": open_file}
        for sequence, handler in bindings.items():
            # The text box gets its own copy so "break" beats its class bindings.
            self.bind(sequence, handler)
            self._text_box.bind(sequence, handler)

    def _on_status_changed(self, *_):
        message = self._status.get()
        if message.startswith("Error"):
            style = "Error.Status.TLabel"
        elif message.startswith(("Saved", "Done")):
            style = "Success.Status.TLabel"
        else:
            style = "Status.TLabel"
        self._status_label.configure(style=style)

    # ------------------------------------------------------------------
    # Playback state management
    # ------------------------------------------------------------------

    def _on_speed_changed(self, value):
        self._speed_label.config(text=f"{float(value):.1f}×")

    def _on_volume_changed(self, value):
        self._vol_label.config(text=f"{int(float(value) * 100)}%")
        if self._controller is not None:
            self._controller.set_volume(float(value))

    def _set_playback_active(self, active: bool):
        if active:
            self._speak_btn.config(state="disabled")
            self._save_btn.config(state="disabled")
            self._pause_btn.config(state="normal", text="❚❚  Pause")
            self._stop_btn.config(state="normal")
        else:
            self._speak_btn.config(state="normal")
            self._save_btn.config(state="normal")
            self._pause_btn.config(state="disabled", text="❚❚  Pause")
            self._stop_btn.config(state="disabled")
            self._show_progress(False)
            self._controller = None

    def _poll_playback(self):
        """Poll every 200ms to detect when playback finishes."""
        ctrl = self._controller
        if ctrl is None:
            return
        if not ctrl.is_finished:
            self.after(200, self._poll_playback)
            return
        if ctrl.error is not None:
            self._status.set("Error.")
            messagebox.showerror("Speech error", str(ctrl.error))
        else:
            self._status.set("Done.")
        self._set_playback_active(False)

    def _status_async(self, message: str):
        """Set the status bar from any thread."""
        self.after(0, lambda: self._status.set(message))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_text(job: dict) -> str:
        """Worker-thread step: parse the file (seconds for a big PDF) so the
        window stays responsive. Errors reach the user via _on_job_failed."""
        if not job["file"]:
            return job["text"]
        text = extract_text(job["file"])
        if not text.strip():
            raise ValueError("No readable text found in that file.")
        return text

    def _selected_lang_code(self) -> str:
        return self._lang_codes[self._lang_cb.get()]

    def _set_lang(self, code: str):
        self._lang_cb.set(LANGUAGES[code].name)
        self._on_lang_changed()

    def _set_source(self, code: str):
        self._source.set(code)
        self._source_cb.set(source_name(code))
        self._update_translate_controls()

    def _update_voice_list(self, lang_code: str):
        voices = voices_for_lang(lang_code)
        self._voice_ids = {f"{v.label}  ·  {v.engine.title()}": v.id for v in voices}
        self._voice_cb.config(values=list(self._voice_ids))
        current = self._voice.get()
        if current not in self._voice_ids.values():
            current = voices[0].id if voices else ""
        self._select_voice(current)

    def _select_voice(self, voice_id: str):
        self._voice.set(voice_id)
        for label, vid in self._voice_ids.items():
            if vid == voice_id:
                self._voice_cb.set(label)
                return
        self._voice_cb.set("")

    def _update_counts(self, content: str):
        if self._file_path.get():
            self._counts.set(f"Will read {self._file_name.get()} when you press Speak")
            return
        words, chars = len(content.split()), len(content)
        self._counts.set(f"{words:,} word{'s' * (words != 1)}  ·  "
                         f"{chars:,} character{'s' * (chars != 1)}")

    def _set_file(self, path: str):
        self._file_path.set(path)
        self._file_name.set(pathlib.Path(path).name if path else "")
        if path:
            self._file_chip.pack(side="right", padx=(0, 8))
        else:
            self._file_chip.pack_forget()

    def _update_translate_controls(self):
        """Enable/disable translation widgets and explain what will happen."""
        on = self._do_translate.get()
        source, target = self._source.get(), self._selected_lang_code()
        self._target_name.set(LANGUAGES[target].name)
        self._source_cb.state(["!disabled"] if on else ["disabled"])
        self._swap_btn.state(["!disabled"] if on and source != AUTO_DETECT else ["disabled"])

        warn = False
        if not on:
            info = "Off: text is read exactly as written."
        elif not needs_translation(target, source):
            info = f"The input is already {LANGUAGES[target].name}, so nothing will be translated."
            warn = True
        elif source == AUTO_DETECT:
            info = f"Detects the input language and translates to {LANGUAGES[target].name}. Needs Google Translate."
        else:
            info = f"{source_name(source)} text will be translated to {LANGUAGES[target].name}, then spoken."
        self._translate_info.set(info)
        self._translate_info_label.configure(
            style="Warn.Card.TLabel" if warn else "Muted.Card.TLabel")
        if not on:
            self._hide_preview()

    @staticmethod
    def _wants_translation(job: dict) -> bool:
        return job["translate"] and needs_translation(job["lang"], job["source"])

    def _segments(self, job: dict, text: str, collected: list[str]):
        """Text for speak(), translated lazily a piece at a time.

        Consumed on the synthesis thread, so the first translated paragraph
        is speaking while later ones are still being fetched. Every piece is
        appended to `collected` for the preview and the saved .txt.
        """
        if not self._wants_translation(job):
            yield text
            return

        def progress(done, total):
            self._status_async(f"Translating... ({done}/{total})" if total > 1
                               else "Translating...")

        self.after(0, lambda: self._show_preview(""))
        for piece in iter_translate(text, job["lang"], on_progress=progress,
                                    source=job["source"]):
            collected.append(piece)
            self.after(0, lambda p=piece: self._append_preview(p))
            yield piece

    def _gather_job(self) -> dict | None:
        """Snapshot every input on the Tk thread before starting a worker."""
        voice = self._voice.get()
        if not voice:
            messagebox.showwarning("No voice", "Choose a voice first.")
            return None
        file_path = self._file_path.get()
        text = "" if file_path else self._text_box.get("1.0", "end").strip()
        if not file_path and not text:
            messagebox.showwarning("No input", "Enter some text or open a file.")
            return None
        return {
            "file": file_path,
            "text": text,
            "lang": self._selected_lang_code(),
            "source": self._source.get(),
            "voice": voice,
            "speed": round(self._speed.get(), 1),
            "volume": self._volume.get(),
            "translate": self._do_translate.get(),
        }

    def _show_preview(self, text: str):
        self._preview_card.grid()
        self._preview_box.config(state="normal")
        self._preview_box.delete("1.0", "end")
        self._preview_box.insert("1.0", text)
        self._preview_box.config(state="disabled")

    def _append_preview(self, piece: str):
        self._preview_box.config(state="normal")
        if self._preview_box.get("1.0", "end-1c"):
            self._preview_box.insert("end", "\n\n")
        self._preview_box.insert("end", piece)
        self._preview_box.see("end")
        self._preview_box.config(state="disabled")

    def _hide_preview(self):
        self._preview_card.grid_remove()

    def _copy_preview(self):
        self.clipboard_clear()
        self.clipboard_append(self._preview_box.get("1.0", "end-1c"))
        self._status.set("Translation copied to the clipboard.")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_text_modified(self, _event=None):
        if self._text_box.edit_modified():
            content = self._text_box.get("1.0", "end-1c")
            if content.strip():
                self._set_file("")  # typing replaces a loaded file
            self._update_counts(content)
            self._text_box.edit_modified(False)

    def _on_lang_changed(self, _event=None):
        self._update_voice_list(self._selected_lang_code())
        self._update_translate_controls()

    def _on_source_changed(self, _event=None):
        self._source.set(self._source_codes[self._source_cb.get()])
        self._update_translate_controls()

    def _on_voice_changed(self, _event=None):
        self._voice.set(self._voice_ids.get(self._voice_cb.get(), ""))

    def _on_swap(self):
        """Swap "from" and "to": read Polish as English <-> English as Polish."""
        source = self._source.get()
        if source == AUTO_DETECT:
            return
        # The source list has one entry per language (e.g. a single English),
        # so map the current target onto it by translation code.
        google = get_language(self._selected_lang_code()).google_code
        new_source = next(code for code, _ in source_languages()
                          if code != AUTO_DETECT and get_language(code).google_code == google)
        self._set_source(new_source)
        self._set_lang(source)

    def _browse_file(self):
        path = filedialog.askopenfilename(filetypes=SUPPORTED_FILETYPES)
        if path:
            self._set_file(path)
            self._text_box.delete("1.0", "end")
            self._update_counts("")

    def _clear_file(self):
        self._set_file("")
        self._update_counts(self._text_box.get("1.0", "end-1c"))

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".wav", filetypes=[("WAV audio", "*.wav")])
        if path:
            self._output_path.set(path)

    def _on_speak(self):
        job = self._gather_job()
        if job is None:
            return
        output = self._output_path.get() or None
        self._set_busy(True)

        def do_speak():
            try:
                self._status_async("Loading...")
                text = self._load_text(job)
                key = self._render_key(job, text)
                render = self._renders.new_path()
                collected: list[str] = []
                # Audio also streams to a temp WAV, so a later Save with the
                # same inputs is a copy. speak() loads the voice itself,
                # overlapped with translation.
                ctrl = speak(self._segments(job, text, collected), voice=job["voice"],
                             speed=job["speed"], volume=job["volume"],
                             output_file=str(render), on_status=self._status_async)
            except Exception as e:
                self.after(0, lambda err=e: self._on_job_failed(err))
                return
            self.after(0, lambda: self._on_playback_started(ctrl))

            try:
                ctrl.wait()
            except Exception:
                return  # _poll_playback reports the error
            if ctrl.is_cancelled:
                return  # stopped: Playback already discarded the partial file
            self._renders.store(key, render, self._translated_text(job, collected))
            if output:
                try:
                    self._renders.export(key, output)
                except Exception as e:
                    self.after(0, lambda err=e: messagebox.showerror("Save error", str(err)))
                    return
                self._status_async(f"Saved to {output}")

        threading.Thread(target=do_speak, daemon=True).start()

    @classmethod
    def _render_key(cls, job: dict, text: str) -> RenderKey:
        return RenderKey(text=text, lang=job["lang"], voice=job["voice"],
                         speed=job["speed"], translate=cls._wants_translation(job),
                         source=job["source"])

    @classmethod
    def _translated_text(cls, job: dict, collected: list[str]) -> str | None:
        return "\n\n".join(collected) if cls._wants_translation(job) else None

    def _on_playback_started(self, ctrl: Playback):
        self._controller = ctrl
        ctrl.set_volume(self._volume.get())  # pick up slider moves since Speak
        self._set_playback_active(True)
        self.after(200, self._poll_playback)

    def _on_job_failed(self, error: Exception):
        self._status.set("Error.")
        self._set_busy(False)
        messagebox.showerror("Error", str(error))

    def _set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self._speak_btn.config(state=state)
        self._save_btn.config(state=state)
        self._show_progress(busy)

    def _on_pause_resume(self):
        if self._controller is None:
            return
        if self._controller.is_paused:
            self._controller.resume()
            self._pause_btn.config(text="❚❚  Pause")
            self._status.set("Playing...")
        else:
            self._controller.pause()
            self._pause_btn.config(text="▶  Resume")
            self._status.set("Paused.")

    def _on_stop(self):
        if self._controller:
            self._controller.stop()
        self._status.set("Stopped.")
        self._set_playback_active(False)

    def _on_save(self):
        output = self._output_path.get()
        if not output:
            path = filedialog.asksaveasfilename(
                defaultextension=".wav", filetypes=[("WAV audio", "*.wav")])
            if not path:
                return
            self._output_path.set(path)
            output = path

        job = self._gather_job()
        if job is None:
            return
        self._set_busy(True)

        def do_save():
            try:
                self._status_async("Loading...")
                text = self._load_text(job)  # cheap: parsers caches by mtime
                key = self._render_key(job, text)
                # Same inputs as the last Speak (or Save): copy, don't redo.
                reused = self._renders.export(key, output)
                if not reused:
                    render = self._renders.new_path()
                    collected: list[str] = []
                    speak(self._segments(job, text, collected), voice=job["voice"],
                          speed=job["speed"], output_file=str(render), play=False,
                          on_status=self._status_async).wait()
                    self._renders.store(key, render, self._translated_text(job, collected))
                    self._renders.export(key, output)
            except Exception as e:
                self.after(0, lambda err=e: self._on_job_failed(err))
                return
            what = "audio + translated text" if key.translate else "audio"
            msg = f"Saved {what} to {output}" + (" (reused last render)" if reused else "")
            self.after(0, lambda: (self._status.set(msg), self._set_busy(False)))

        threading.Thread(target=do_save, daemon=True).start()

    def _on_close(self):
        self.withdraw()  # disappear at once; shutdown below may take a moment
        # Stop every job (Speak *and* Save) and let synthesis threads leave
        # torch before Python tears down; exiting mid-call aborts the process.
        clean = tts.shutdown(timeout=5)
        self._renders.close()
        self.destroy()
        if not clean:
            # A thread is still in native code (e.g. downloading a model).
            # Skip interpreter teardown rather than crash during it.
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)


_SELFTEST_TEXT = {
    "a": "Hello.", "b": "Hello.", "j": "こんにちは。", "z": "你好。", "e": "Hola.",
    "f": "Bonjour.", "h": "नमस्ते।", "i": "Ciao.", "p": "Olá.",
    "pl": "Dzień dobry.", "ro": "Bună ziua.",
}


def selftest(report_path: str | None = None) -> int:
    """Synthesise one phrase per language without playing it.

    Exists so a frozen build can be checked for missing bundled data
    without clicking through the GUI: `TextToSpeech --selftest [report.txt]`.
    """
    import traceback
    from tts import synthesise
    from voices import default_voice_for_lang

    lines, failures = [], 0
    for code, lang in LANGUAGES.items():
        voice = default_voice_for_lang(code)
        try:
            audio, rate = synthesise(_SELFTEST_TEXT.get(code, "Hello."), voice=voice)
            ok = audio.size > 0
            lines.append(f"{'PASS' if ok else 'FAIL'}  {code:<3} {voice:<22} "
                         f"{audio.size / rate if ok else 0:.2f}s @ {rate} Hz")
            failures += not ok
        except Exception:
            failures += 1
            lines.append(f"FAIL  {code:<3} {voice:<22} "
                         + traceback.format_exc().strip().splitlines()[-1])
    report = "\n".join(lines) + f"\n{failures} failure(s)\n"
    print(report, end="")
    if report_path:
        pathlib.Path(report_path).write_text(report, encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        args = sys.argv[sys.argv.index("--selftest") + 1:]
        sys.exit(selftest(args[0] if args else None))
    app = App()
    app.mainloop()
