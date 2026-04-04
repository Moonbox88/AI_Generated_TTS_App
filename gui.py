#!/usr/bin/env python3
"""Text-to-Speech GUI — Phase 2 (Tkinter)."""

import pathlib
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from main import LANGUAGES, VOICES
from parsers import extract_text
from translator import needs_translation, translate
from tts import DEFAULT_LANG, DEFAULT_VOICE, PlaybackController, speak

SUPPORTED_FILETYPES = [
    ("Documents", "*.txt *.pdf *.docx"),
    ("Text files", "*.txt"),
    ("PDF files", "*.pdf"),
    ("Word documents", "*.docx"),
    ("All files", "*.*"),
]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Text to Speech")
        self.resizable(True, True)
        self.minsize(540, 520)

        self._file_path = tk.StringVar()
        self._voice = tk.StringVar(value=DEFAULT_VOICE)
        self._lang = tk.StringVar(value=DEFAULT_LANG)
        self._output_path = tk.StringVar()
        self._status = tk.StringVar(value="Ready.")
        self._speed = tk.DoubleVar(value=1.0)
        self._volume = tk.DoubleVar(value=1.0)
        self._do_translate = tk.BooleanVar(value=False)

        self._controller: PlaybackController | None = None
        self._synthesising = False

        self._build_ui()
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

    def _build_ui(self):
        pad = {"padx": 10, "pady": 5}

        # --- Text input ---
        text_frame = ttk.LabelFrame(self, text="Text input")
        text_frame.pack(fill="both", expand=True, **pad)

        self._text_box = tk.Text(text_frame, height=10, wrap="word", undo=True)
        self._text_box.pack(fill="both", expand=True, padx=5, pady=5)
        self._text_box.bind("<<Modified>>", self._on_text_modified)

        # --- File input ---
        file_frame = ttk.LabelFrame(self, text="Or load a file (.txt / .pdf / .docx)")
        file_frame.pack(fill="x", **pad)

        self._file_label = ttk.Label(file_frame, textvariable=self._file_path,
                                     foreground="grey", width=50, anchor="w")
        self._file_label.pack(side="left", padx=5, pady=5)
        ttk.Button(file_frame, text="Browse", command=self._browse_file).pack(side="right", padx=5, pady=5)
        ttk.Button(file_frame, text="Clear", command=self._clear_file).pack(side="right", pady=5)

        # --- Options ---
        options_frame = ttk.LabelFrame(self, text="Options")
        options_frame.pack(fill="x", **pad)

        # Row 0: Language + Voice
        ttk.Label(options_frame, text="Language:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        lang_values = [f"{k} — {v}" for k, v in LANGUAGES.items()]
        self._lang_cb = ttk.Combobox(options_frame, values=lang_values, state="readonly", width=24)
        self._lang_cb.current(0)
        self._lang_cb.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self._lang_cb.bind("<<ComboboxSelected>>", self._on_lang_changed)

        ttk.Label(options_frame, text="Voice:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self._voice_cb = ttk.Combobox(options_frame, textvariable=self._voice, state="readonly", width=18)
        self._voice_cb.grid(row=0, column=3, padx=5, pady=5, sticky="w")
        self._update_voice_list("a")

        # Row 1: Speed slider
        ttk.Label(options_frame, text="Speed:").grid(row=1, column=0, padx=5, pady=4, sticky="w")
        speed_frame = ttk.Frame(options_frame)
        speed_frame.grid(row=1, column=1, columnspan=3, padx=5, sticky="ew")
        ttk.Label(speed_frame, text="0.5x").pack(side="left")
        self._speed_slider = ttk.Scale(speed_frame, from_=0.5, to=2.0, variable=self._speed,
                                       orient="horizontal", length=200,
                                       command=lambda v: self._speed_label.config(
                                           text=f"{float(v):.1f}x"))
        self._speed_slider.pack(side="left", padx=4)
        ttk.Label(speed_frame, text="2.0x").pack(side="left")
        self._speed_label = ttk.Label(speed_frame, text="1.0x", width=5)
        self._speed_label.pack(side="left", padx=6)

        # Row 2: Volume slider
        ttk.Label(options_frame, text="Volume:").grid(row=2, column=0, padx=5, pady=4, sticky="w")
        vol_frame = ttk.Frame(options_frame)
        vol_frame.grid(row=2, column=1, columnspan=3, padx=5, sticky="ew")
        ttk.Label(vol_frame, text="0%").pack(side="left")
        self._vol_label = ttk.Label(vol_frame, text="100%", width=5)
        self._vol_slider = ttk.Scale(vol_frame, from_=0.0, to=1.0, variable=self._volume,
                                     orient="horizontal", length=200,
                                     command=lambda v: self._vol_label.config(
                                         text=f"{int(float(v) * 100)}%"))
        self._vol_slider.set(1.0)
        self._vol_slider.pack(side="left", padx=4)
        ttk.Label(vol_frame, text="100%").pack(side="left")
        self._vol_label.pack(side="left", padx=6)

        # Row 3: Translate checkbox
        self._translate_chk = ttk.Checkbutton(
            options_frame, text="Translate from English",
            variable=self._do_translate, command=self._on_translate_toggled)
        self._translate_chk.grid(row=3, column=0, columnspan=2, padx=5, pady=2, sticky="w")

        # Row 4: Output file
        ttk.Label(options_frame, text="Save to:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(options_frame, textvariable=self._output_path, width=30).grid(
            row=4, column=1, columnspan=2, padx=5, pady=5, sticky="ew")
        ttk.Button(options_frame, text="Browse", command=self._browse_output).grid(
            row=4, column=3, padx=5, pady=5)

        options_frame.columnconfigure(1, weight=1)

        # --- Translation preview ---
        self._preview_frame = ttk.LabelFrame(self, text="Translated text (preview)")
        self._preview_box = tk.Text(self._preview_frame, height=4, wrap="word",
                                    state="disabled", foreground="grey")
        self._preview_box.pack(fill="both", expand=True, padx=5, pady=5)

        # --- Action buttons ---
        self._btn_frame = ttk.Frame(self)
        self._btn_frame.pack(pady=8)

        self._speak_btn = ttk.Button(self._btn_frame, text="Speak", width=12, command=self._on_speak)
        self._speak_btn.grid(row=0, column=0, padx=6)

        self._pause_btn = ttk.Button(self._btn_frame, text="Pause", width=12,
                                     command=self._on_pause_resume, state="disabled")
        self._pause_btn.grid(row=0, column=1, padx=6)

        self._stop_btn = ttk.Button(self._btn_frame, text="Stop", width=12,
                                    command=self._on_stop, state="disabled")
        self._stop_btn.grid(row=0, column=2, padx=6)

        self._save_btn = ttk.Button(self._btn_frame, text="Save to file", width=12,
                                    command=self._on_save)
        self._save_btn.grid(row=0, column=3, padx=6)

        # --- Status bar ---
        ttk.Label(self, textvariable=self._status, anchor="w",
                  relief="sunken", padding=(6, 2)).pack(fill="x", side="bottom")

    # ------------------------------------------------------------------
    # Playback state management
    # ------------------------------------------------------------------

    def _set_playback_active(self, active: bool):
        if active:
            self._speak_btn.config(state="disabled")
            self._save_btn.config(state="disabled")
            self._pause_btn.config(state="normal", text="Pause")
            self._stop_btn.config(state="normal")
        else:
            self._speak_btn.config(state="normal")
            self._save_btn.config(state="normal")
            self._pause_btn.config(state="disabled", text="Pause")
            self._stop_btn.config(state="disabled")
            self._controller = None

    def _poll_playback(self):
        """Poll every 200ms to detect when playback finishes naturally."""
        if self._controller is None:
            return
        if not self._controller.is_playing and not self._controller.is_paused:
            self.after(0, lambda: self._status.set("Done."))
            self.after(0, lambda: self._set_playback_active(False))
        else:
            self.after(200, self._poll_playback)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_text(self) -> str | None:
        file_path = self._file_path.get()
        if file_path:
            try:
                return extract_text(file_path)
            except (FileNotFoundError, ValueError) as e:
                messagebox.showerror("File error", str(e))
                return None
        text = self._text_box.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("No input", "Enter some text or load a file.")
            return None
        return text

    def _selected_lang_code(self) -> str:
        return self._lang_cb.get().split(" — ")[0]

    def _update_voice_list(self, lang_code: str):
        filtered = [v for v in VOICES if v.startswith(lang_code)]
        self._voice_cb.config(values=filtered)
        if self._voice.get() not in filtered:
            self._voice.set(filtered[0] if filtered else "")

    def _get_final_text(self, lang: str) -> str | None:
        text = self._get_text()
        if not text:
            return None
        if self._do_translate.get() and needs_translation(lang):
            self.after(0, lambda: self._status.set("Translating..."))
            text = translate(text, lang)
            self.after(0, lambda: self._show_preview(text))
        return text

    def _show_preview(self, text: str):
        self._preview_frame.pack(fill="x", padx=10, pady=5, before=self._btn_frame)
        self._preview_box.config(state="normal")
        self._preview_box.delete("1.0", "end")
        self._preview_box.insert("1.0", text)
        self._preview_box.config(state="disabled")

    def _hide_preview(self):
        self._preview_frame.pack_forget()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_text_modified(self, _event=None):
        if self._text_box.edit_modified():
            if self._text_box.get("1.0", "end").strip():
                self._file_path.set("")
                self._file_label.config(foreground="grey")
            self._text_box.edit_modified(False)

    def _on_lang_changed(self, _event=None):
        lang = self._selected_lang_code()
        self._update_voice_list(lang)
        if needs_translation(lang):
            self._translate_chk.state(["!disabled"])
        else:
            self._do_translate.set(False)
            self._translate_chk.state(["disabled"])
            self._hide_preview()

    def _on_translate_toggled(self):
        if not self._do_translate.get():
            self._hide_preview()

    def _browse_file(self):
        path = filedialog.askopenfilename(filetypes=SUPPORTED_FILETYPES)
        if path:
            self._file_path.set(path)
            self._file_label.config(foreground="black")
            self._text_box.delete("1.0", "end")

    def _clear_file(self):
        self._file_path.set("")
        self._file_label.config(foreground="grey")

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".wav", filetypes=[("WAV audio", "*.wav")])
        if path:
            self._output_path.set(path)

    def _on_speak(self):
        lang = self._selected_lang_code()
        voice = self._voice.get()
        speed = round(self._speed.get(), 1)
        volume = self._volume.get()
        output = self._output_path.get() or None

        def do_speak():
            text = self._get_final_text(lang)
            if not text:
                return
            self.after(0, lambda: self._status.set("Synthesising..."))
            ctrl = speak(text, voice=voice, lang=lang, speed=speed,
                         volume=volume, output_file=output)
            self._controller = ctrl
            self.after(0, lambda: self._status.set("Playing..."))
            self.after(0, lambda: self._set_playback_active(True))
            self.after(200, self._poll_playback)

        threading.Thread(target=do_speak, daemon=True).start()

    def _on_pause_resume(self):
        if self._controller is None:
            return
        if self._controller.is_paused:
            self._controller.resume()
            self._pause_btn.config(text="Pause")
            self._status.set("Playing...")
            self.after(200, self._poll_playback)
        else:
            self._controller.pause()
            self._pause_btn.config(text="Resume")
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

        lang = self._selected_lang_code()
        voice = self._voice.get()
        speed = round(self._speed.get(), 1)
        volume = self._volume.get()

        def do_save():
            text = self._get_final_text(lang)
            if not text:
                return
            self.after(0, lambda: self._status.set("Saving..."))
            speak(text, voice=voice, lang=lang, speed=speed,
                  volume=volume, output_file=output)
            if self._do_translate.get() and needs_translation(lang):
                txt_path = output.rsplit(".", 1)[0] + ".txt"
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(text)
                self.after(0, lambda: self._status.set(f"Saved audio + translated text to {output}"))
            else:
                self.after(0, lambda: self._status.set(f"Saved to {output}"))

        threading.Thread(target=do_save, daemon=True).start()

    def _on_close(self):
        if self._controller:
            self._controller.stop()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
