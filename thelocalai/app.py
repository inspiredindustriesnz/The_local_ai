from __future__ import annotations

import logging
import queue
import threading
import time
import traceback
from typing import Optional

import tkinter as tk
from tkinter import messagebox, simpledialog

from .chat_logic import ChatResult, generate_reply
from .config import APP_TITLE, DEFAULT_MODEL, DEFAULT_NUM_PREDICT, DEFAULT_TEMPERATURE, DEV_SESSION_MINUTES, GEN_WATCHDOG_SECONDS, MAX_USER_CHARS, THEME, VOSK_MODEL_DIR
from .db import db_connect, db_counts_fast
from .integrations import ollama_list_models
from .security import dev_auth_check_password, dev_auth_is_configured, dev_auth_set_password, release_single_instance_lock
from .ui_builder import build_ui, configure_ttk
from .voice import SpeechToText, TTS

log = logging.getLogger("thelocalai")


class TheLocalAIApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1100x820")
        self.root.configure(bg=THEME["bg"])

        self.closing = False
        self.is_processing = False
        self.q: "queue.Queue[ChatResult | Exception | tuple[str, str]]" = queue.Queue()

        self._dev_unlocked_until: Optional[float] = None
        self._dev_after: Optional[str] = None

        self.num_predict = DEFAULT_NUM_PREDICT
        self.temperature = DEFAULT_TEMPERATURE

        self._matrix_resize_after: Optional[str] = None
        self._telemetry_after: Optional[str] = None
        self._watchdog_after: Optional[str] = None

        self._last_llm_started: Optional[float] = None
        self._last_llm_ms: Optional[int] = None

        self.voice_enabled_var = tk.BooleanVar(value=False)
        self.mic_listen_var = tk.BooleanVar(value=False)
        self.tts: Optional[TTS] = None
        self.stt: Optional[SpeechToText] = None

        self.root.report_callback_exception = self._tk_report_callback_exception
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        configure_ttk()
        build_ui(self)
        self._dev_tick()

        self.refresh_models(initial=True)

        self.chat.write(f"* {APP_TITLE} - Offline AI Assistant (+ optional web learning)", "system")
        self.chat.write(f"* Default model: {DEFAULT_MODEL}", "system")
        self.chat.write("* Commands: web: <query> | learn: <topic> | kb: <query> | kbclear", "system")
        self.chat.write("* Extra: type `about` or `memorytopics`", "system")
        self.chat.write("* You can ask about local files/structure (e.g., `where is voice code?`).", "system")
        self.chat.write("* Enter to send. Shift+Enter for new line.", "system")
        self.chat.write("* Tip: You can select + copy chat text now (Ctrl+C).", "system")

        self.root.after(150, lambda: self.input.focus_set())
        self.root.after(80, self.poll)
        self.root.after(250, self._start_matrix)

        self._schedule_telemetry()
        self._schedule_watchdog()
        self.root.after(120, self._stt_poll)

    def _tk_report_callback_exception(self, exc, val, tb):
        log.error("Tkinter callback exception:\n%s", "".join(traceback.format_exception(exc, val, tb)))
        try:
            messagebox.showerror(APP_TITLE, f"An error occurred:\n{val}")
        except Exception:
            pass

    def _ensure_tts(self) -> bool:
        if self.tts is not None:
            return True
        try:
            self.tts = TTS()
            return True
        except Exception as e:
            self.tts = None
            self.chat.write(f"[VOICE] TTS failed to initialize: {e}", "error")
            return False

    def _toggle_tts_enabled(self):
        if self.voice_enabled_var.get():
            if not self._ensure_tts():
                self.voice_enabled_var.set(False)
                return
            self.chat.write("[VOICE] TTS enabled (assistant will speak every reply).", "system")
        else:
            self.chat.write("[VOICE] TTS disabled.", "system")

    def _ensure_stt(self) -> bool:
        if self.stt is not None:
            return self.stt.enabled
        self.stt = SpeechToText(VOSK_MODEL_DIR)
        if not self.stt.enabled:
            self.chat.write(
                "[VOICE] Mic (STT) unavailable. Fix steps:\n"
                "1) Install deps:\n"
                "   pip install vosk sounddevice numpy\n"
                "2) Download + unzip a Vosk model into:\n"
                f"   {VOSK_MODEL_DIR}\n"
                "   (folder must contain: conf/, am/, graph/ ...)\n"
                "\nTip: After fixing, restart the app.",
                "error",
            )
            return False
        self.chat.write(f"[VOICE] Mic (STT) ready. Vosk model: {VOSK_MODEL_DIR}", "system")
        return True

    def _toggle_mic_listen(self):
        if self.mic_listen_var.get():
            if not self._ensure_stt() or not self.stt:
                self.mic_listen_var.set(False)
                return
            if not self.stt.start_listening():
                self.mic_listen_var.set(False)
                self.chat.write("[VOICE] Failed to start microphone. Check mic permissions + sounddevice.", "error")
                return
            self.chat.write("[VOICE] Mic listening ON. Speak a sentence; it will auto-send.", "system")
        else:
            if self.stt:
                try:
                    self.stt.stop_listening()
                except Exception:
                    pass
            self.chat.write("[VOICE] Mic listening OFF.", "system")

    def _stt_poll(self):
        if self.closing:
            return
        if self.stt and self.stt.listening and not self.is_processing:
            try:
                while True:
                    text = self.stt.in_q.get_nowait().strip()
                    if not text:
                        continue
                    self.input.delete("1.0", tk.END)
                    self.input.insert("1.0", text)
                    self.on_send()
            except queue.Empty:
                pass
        self.root.after(120, self._stt_poll)

    def _on_matrix_resize(self, _evt=None):
        if self.closing:
            return
        if self._matrix_resize_after:
            try:
                self.matrix_canvas.after_cancel(self._matrix_resize_after)
            except Exception:
                pass
        self._matrix_resize_after = self.matrix_canvas.after(160, self._reset_matrix_safe)

    def _reset_matrix_safe(self):
        self._matrix_resize_after = None
        if not self.closing:
            self.matrix.reset()

    def _start_matrix(self):
        if not self.closing:
            self.root.update_idletasks()
            self.matrix.start()

    def _clear_chat(self):
        self.chat.clear()
        self.chat.write("* Chat cleared.", "system")

    def set_status(self, txt: str):
        self.status.set(txt)
        self.root.update_idletasks()

    def refresh_models(self, initial: bool = False):
        def _worker():
            models = ollama_list_models()
            if not models:
                self.q.put(("error", "Could not load models from Ollama. Is Ollama running?"))
                return
            self.q.put(("models", "|".join(models)))

        threading.Thread(target=_worker, daemon=True).start()
        if not initial:
            self.chat.write("* Refreshing model list...", "system")

    def _enter_send(self, _event):
        self.on_send()
        return "break"

    def _shift_enter(self, _event):
        self.input.insert(tk.INSERT, "\n")
        return "break"

    def on_send(self):
        if self.is_processing or self.closing:
            return
        message = self.input.get("1.0", tk.END).strip()
        if not message:
            return
        if len(message) > MAX_USER_CHARS:
            messagebox.showerror("Too long", f"Message too long (max {MAX_USER_CHARS}).")
            return

        self.input.delete("1.0", tk.END)
        self.chat.write(f"You: {message}", "user")
        self.chat.write(f"{APP_TITLE}: (thinking...)", "system")
        self.set_status("Thinking...")
        self.is_processing = True
        self.matrix.set_low_power(True)

        self._last_llm_started = time.perf_counter()
        model = self.model_var.get().strip() or DEFAULT_MODEL
        threading.Thread(target=self._worker_chat, args=(model, message), daemon=True).start()

    def _worker_chat(self, model: str, message: str):
        con = None
        try:
            if self.closing:
                return
            con = db_connect()
            self.q.put(generate_reply(con, model, message, num_predict=self.num_predict, temperature=self.temperature))
        except Exception as e:
            log.exception("Worker error")
            self.q.put(e)
        finally:
            if con:
                con.close()

    def poll(self):
        if self.closing:
            return

        for _ in range(10):
            try:
                item = self.q.get_nowait()
            except queue.Empty:
                break

            if isinstance(item, Exception):
                self.chat.write(f"[ERROR] {item}", "error")
                self._unlock_ui_after_task()
                continue

            if isinstance(item, tuple) and len(item) == 2:
                kind, payload = item
                if kind == "error":
                    self.chat.write(f"[ERROR] {payload}", "error")
                elif kind == "models":
                    models = payload.split("|") if payload else [DEFAULT_MODEL]
                    self.model_combo["values"] = models
                    if self.model_var.get() not in models:
                        self.model_var.set(DEFAULT_MODEL if DEFAULT_MODEL in models else models[0])
                    self.chat.write(f"* Models loaded: {len(models)}", "system")
                continue

            assert isinstance(item, ChatResult)
            if item.stored:
                self.chat.write(f"[MEMORY] {item.stored}", "system")

            txt = (item.assistant or "").strip()
            low = txt.lower()
            if ("don't have a voice" in low) or ("doesnt have a voice" in low) or ("doesn't have a voice" in low):
                txt = "Voice is handled by the app. If you enable 'Voice (TTS)', I can speak responses aloud. The model itself only outputs text."
            self.chat.write(f"{APP_TITLE}: {txt}", "assistant")

            if self.voice_enabled_var.get() and self._ensure_tts() and self.tts:
                self.tts.speak(txt)

            if self._last_llm_started is not None:
                self._last_llm_ms = int((time.perf_counter() - self._last_llm_started) * 1000)
                self._last_llm_started = None

            self._unlock_ui_after_task()

        self.root.after(80, self.poll)

    def _unlock_ui_after_task(self):
        self.is_processing = False
        self.matrix.set_low_power(False)
        self.set_status("Ready")

    def _schedule_telemetry(self):
        if self.closing:
            return
        self._update_telemetry()
        self._telemetry_after = self.root.after(700, self._schedule_telemetry)

    def _update_telemetry(self):
        qsize = self.q.qsize()
        threads = threading.active_count()
        mem_rows, kb_docs = db_counts_fast()
        fps = getattr(self.matrix, "fps", 0)
        avg_dt = getattr(self.matrix, "avg_dt_ms", 0.0)
        last_dt = getattr(self.matrix, "last_dt_ms", 0.0)
        llm_ms = self._last_llm_ms if self._last_llm_ms is not None else "-"
        proc_state = "YES" if self.is_processing else "NO"
        matrix_items = len(self.matrix_canvas.find_withtag("matrix"))

        voice_state = "OFF"
        if self.voice_enabled_var.get():
            voice_state = "TTS"
        if self.mic_listen_var.get():
            voice_state += "+MIC"

        age = "-"
        if self._last_llm_started is not None:
            age = f"{int(time.perf_counter() - self._last_llm_started)}s"

        self.tlm_text.set(
            "Telemetry\n"
            f"- Processing: {proc_state} (age: {age})\n"
            f"- Queue: {qsize}\n"
            f"- Threads: {threads}\n"
            f"- DB: memory={mem_rows}  kb_docs={kb_docs}\n"
            f"- Voice: {voice_state}\n"
            f"- Matrix: FPS={fps} | dt(avg/last)={avg_dt:.1f}/{last_dt:.1f} ms\n"
            f"- Matrix items: {matrix_items}\n"
            f"- Last LLM: {llm_ms} ms\n"
        )

    def _schedule_watchdog(self):
        if self.closing:
            return
        self._watchdog_tick()
        self._watchdog_after = self.root.after(1000, self._schedule_watchdog)

    def _watchdog_tick(self):
        if not self.is_processing or self._last_llm_started is None:
            return
        elapsed = time.perf_counter() - self._last_llm_started
        if elapsed > GEN_WATCHDOG_SECONDS:
            log.error("Watchdog: generation exceeded %ss, unlocking UI.", GEN_WATCHDOG_SECONDS)
            self.chat.write("[ERROR] Generation timed out / hung. UI unlocked. Check Ollama + logs.", "error")
            self._last_llm_started = None
            self._unlock_ui_after_task()

    def _dev_is_unlocked(self) -> bool:
        return self._dev_unlocked_until is not None and time.time() < self._dev_unlocked_until

    def _dev_tick(self):
        self.dev_state.set("DEV" if self._dev_is_unlocked() else "STOCK")
        if self._dev_after:
            self.root.after_cancel(self._dev_after)
        self._dev_after = self.root.after(1000, self._dev_tick)

    def lock_dev_mode(self):
        self._dev_unlocked_until = None
        self.dev_state.set("STOCK")
        self.chat.write("* Dev Mode locked.", "system")

    def unlock_dev_mode(self):
        if not dev_auth_is_configured():
            pw1 = simpledialog.askstring(APP_TITLE, "Set Dev Mode password:", show="*")
            if not pw1:
                return
            pw2 = simpledialog.askstring(APP_TITLE, "Confirm Dev Mode password:", show="*")
            if pw1 != pw2:
                messagebox.showerror(APP_TITLE, "Passwords do not match.")
                return
            dev_auth_set_password(pw1)
            self.chat.write("* Dev Mode password set.", "system")

        pw = simpledialog.askstring(APP_TITLE, "Enter Dev Mode password:", show="*")
        if not pw:
            return
        if not dev_auth_check_password(pw):
            messagebox.showerror(APP_TITLE, "Incorrect password.")
            return

        self._dev_unlocked_until = time.time() + (DEV_SESSION_MINUTES * 60)
        self.chat.write(f"* Dev Mode unlocked for {DEV_SESSION_MINUTES} minutes.", "system")
        self.dev_state.set("DEV")

    def on_close(self):
        self.closing = True

        for timer in [self._telemetry_after, self._watchdog_after, self._matrix_resize_after, self._dev_after]:
            try:
                if timer:
                    self.root.after_cancel(timer)
            except Exception:
                pass

        if self.stt:
            self.stt.stop_listening()
        if self.tts:
            self.tts.shutdown()
        self.matrix.stop()

        release_single_instance_lock()

        try:
            self.root.destroy()
        except Exception:
            self.root.quit()
