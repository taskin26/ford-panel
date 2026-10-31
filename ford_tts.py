#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FORD TTS - Pi uzerinde espeak-ng ile Turkce konusma uretir.
Panel (ford_ekran.html) bu servisten sesi alir ve teybin MEDYA kanalindan
(araba kolonlarindan) calar. Teypte TTS motoru/internet GEREKMEZ.

Port: 8090   (ford_web zaten 8080'de; buna dokunmaz, ayri calisir.)
Adres ornegi:  http://10.42.0.1:8090/tts?q=kapilar%20acildi
Baglimlilik yok (sadece Python stdlib + sistemde 'espeak-ng').
"""
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8090

def uret(metin):
    """espeak-ng ile WAV ses uretir (stdout). Hata olursa bos doner."""
    metin = (metin or "").strip()[:300]
    if not metin:
        return b""
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
        if parca.path not in ("/tts", "/api/tts"):
            if parca.path in ("/", "/saglik"):
                self._gonder(b"FORD TTS calisiyor\n", "text/plain")
                return
            self.send_response(404); self.end_headers(); return
        q = urllib.parse.parse_qs(parca.query)
        metin = (q.get("q", [""]) or [""])[0]
        wav = uret(metin)
        if not wav:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return
        self._gonder(wav, "audio/wav")

    def _gonder(self, govde, tip):
        self.send_response(200)
        self.send_header("Content-Type", tip)
        self.send_header("Content-Length", str(len(govde)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(govde)
        except Exception:
            pass

    def log_message(self, *a):
        pass  # sessiz

if __name__ == "__main__":
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Isleyici)
    print("FORD TTS :%d espeak-ng ile hazir" % PORT)
    srv.serve_forever()
