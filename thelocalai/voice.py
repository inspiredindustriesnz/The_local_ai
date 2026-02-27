from __future__ import annotations

import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

log = logging.getLogger("thelocalai")

try:
    import numpy as np  # type: ignore
except Exception:
    np = None  # type: ignore


class TTS:
    def __init__(self):
        self.q: "queue.Queue[str]" = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def shutdown(self):
        self._stop.set()
        try:
            self.q.put_nowait("")
        except Exception:
            pass

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        for chunk in self._chunk(text, max_len=650):
            self.q.put(chunk)

    @staticmethod
    def _chunk(text: str, max_len: int = 650) -> list[str]:
        if len(text) <= max_len:
            return [text]
        parts: list[str] = []
        buf: list[str] = []
        cur = 0
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            s = sentence.strip()
            if not s:
                continue
            if cur + len(s) + 1 > max_len and buf:
                parts.append(" ".join(buf))
                buf = [s]
                cur = len(s)
            else:
                buf.append(s)
                cur += len(s) + 1
        if buf:
            parts.append(" ".join(buf))
        return parts

    def _worker(self):
        while not self._stop.is_set():
            try:
                text = self.q.get()
            except Exception:
                continue
            if self._stop.is_set():
                return
            text = (text or "").strip()
            if not text:
                continue
            try:
                if not self._speak_once(text):
                    log.warning("TTS: no backend succeeded for this utterance.")
            except Exception:
                log.exception("TTS: speak failed")

    def _speak_once(self, text: str) -> bool:
        try:
            import pyttsx3  # type: ignore

            engine = pyttsx3.init()
            engine.setProperty("rate", 165)
            engine.setProperty("volume", 1.0)
            engine.say(text)
            engine.runAndWait()
            try:
                engine.stop()
            except Exception:
                pass
            return True
        except Exception as e:
            log.warning("TTS pyttsx3 failed: %s", e)

        if os.name == "nt":
            try:
                safe = text.replace('"', "'")
                cmd = [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    'Add-Type -AssemblyName System.Speech; '
                    '$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                    f'$speak.Speak("{safe}");',
                ]
                subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception as e:
                log.warning("TTS PowerShell failed: %s", e)

        if sys.platform == "darwin":
            try:
                subprocess.run(["say", text], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception as e:
                log.warning("TTS say failed: %s", e)

        try:
            subprocess.run(["espeak", text], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            log.warning("TTS espeak failed: %s", e)

        return False


class SpeechToText:
    def __init__(self, model_dir: Path, *, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.model_dir = model_dir

        self.enabled = False
        self.listening = False

        self._rec = None
        self._stream = None
        self.in_q: "queue.Queue[str]" = queue.Queue()

        self._init_vosk()

    def _init_vosk(self) -> None:
        try:
            if np is None:
                raise RuntimeError("numpy not installed (required for mic audio conversion)")

            from vosk import KaldiRecognizer, Model  # type: ignore

            if not self.model_dir.exists():
                raise FileNotFoundError(f"Vosk model folder not found: {self.model_dir}")

            model = Model(str(self.model_dir))
            self._rec = KaldiRecognizer(model, self.sample_rate)
            self._rec.SetWords(False)
            self.enabled = True
        except Exception as e:
            self.enabled = False
            self._rec = None
            log.warning("STT: Vosk not available (%s). Mic disabled.", e)

    def start_listening(self) -> bool:
        if not self.enabled or self._rec is None:
            return False
        if self.listening:
            return True

        try:
            import sounddevice as sd  # type: ignore

            def callback(indata, frames, time_info, status):
                if status:
                    pass
                pcm = np.clip(indata[:, 0], -1.0, 1.0)
                pcm16 = (pcm * 32767).astype(np.int16).tobytes()

                if self._rec.AcceptWaveform(pcm16):
                    try:
                        obj = json.loads(self._rec.Result())
                        text = (obj.get("text") or "").strip()
                        if text:
                            self.in_q.put(text)
                    except Exception:
                        pass

            self._stream = sd.InputStream(
                channels=1,
                samplerate=self.sample_rate,
                dtype="float32",
                callback=callback,
                blocksize=0,
            )
            self._stream.start()
            self.listening = True
            return True
        except Exception as e:
            log.warning("STT: mic start failed: %s", e)
            self.listening = False
            return False

    def stop_listening(self) -> None:
        self.listening = False
        try:
            if self._stream:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None
