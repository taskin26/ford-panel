#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FORD TTS - Pi uzerinde konusma uretir. Panel sesi buradan alir, teybin MEDYA
kanalindan (araba kolonlarindan) calar. Teypte TTS motoru/internet GEREKMEZ.

Oncelik: PIPER (dogal Turkce neural ses) -> yoksa espeak-ng (robotik yedek).
Port: 8090   (ford_web 8080'de; buna dokunmaz.)
Adres: http://10.42.0.1:8090/tts?q=kapilar%20acildi
Baglimlilik yok (Python stdlib; sistemde piper/espeak-ng calistirir).
"""
import glob
import os
import subprocess
import tempfile
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8090
PIPER_BIN = "/home/ford/piper/piper"

def piper_model():
    """Turkce piper modelini (.onnx) bulur, yoksa None."""
    for p in sorted(glob.glob("/home/ford/piper/*.onnx")):
        if p.endswith(".onnx"):
            return p
    return None

PIPER_MODEL = piper_model()

def uret(metin):
    """Metni WAV sese cevirir. Once piper, olmazsa espeak-ng."""
    metin = (metin or "").strip()[:300]
    if not metin:
        return b""
    # 1) PIPER - dogal Turkce
    if PIPER_MODEL and os.path.exists(PIPER_BIN):
        out = None
        try:
            fd, out = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            subprocess.run([PIPER_BIN, "-m", PIPER_MODEL, "-f", out],
                           input=metin.encode("utf-8"),
                           capture_output=True, timeout=25)
            with open(out, "rb") as f:
                data = f.read()
            if data:
                return data
        except Exception:
            pass
        finally:
            if out and os.path.exists(out):
                try: os.unlink(out)
                except Exception: pass
    # 2) ESPEAK-NG - robotik yedek
    try:
        r = subprocess.run(
            ["espeak-ng", "-v", "tr", "-s", "150", "-a", "190", "-p", "45",
             "--stdout", metin],
            capture_output=True, timeout=12)
        return r.stdout or b""
    except Exception:
        return b""

class Isleyici(BaseHTTPRequestHandler):
    def do_GET(self):
        parca = urllib.parse.urlparse(self.path)
        if parca.path in ("/", "/saglik"):
            bilgi = ("FORD TTS calisiyor | motor=%s\n"
                     % ("piper:" + os.path.basename(PIPER_MODEL) if PIPER_MODEL
                        else "espeak-ng")).encode("utf-8")
            self._gonder(bilgi, "text/plain"); return
        if parca.path not in ("/tts", "/api/tts"):
            self.send_response(404); self.end_headers(); return
        q = urllib.parse.parse_qs(parca.query)
        wav = uret((q.get("q", [""]) or [""])[0])
        if not wav:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers(); return
        self._gonder(wav, "audio/wav")

    def _gonder(self, govde, tip):
        self.send_response(200)
        self.send_header("Content-Type", tip)
        self.send_header("Content-Length", str(len(govde)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try: self.wfile.write(govde)
        except Exception: pass

    def log_message(self, *a):
        pass

if __name__ == "__main__":
    print("FORD TTS :%d  motor=%s" %
          (PORT, PIPER_MODEL or "espeak-ng"))
    ThreadingHTTPServer(("0.0.0.0", PORT), Isleyici).serve_forever()
