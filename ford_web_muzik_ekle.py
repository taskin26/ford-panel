#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_web_muzik_ekle.py  —  ford_web.py'ye MÜZİK YÖNETİMİ uçlarını ekler
=====================================================================
28 Kasım 2026

NE EKLER (ford_web.py'ye, mevcut hiçbir şeyi bozmadan):
    GET  /muzik              -> yönetim sayfası (muzik.html)
    GET  /api/muzik/liste    -> MUZIK klasöründeki MP3'leri listeler
    POST /api/muzik/yukle    -> çoklu MP3 yükler (multipart, alan adı "dosya")
    POST /api/muzik/sil      -> JSON {"ad": "sarki.mp3"} tek dosya siler

GÜVENLİ:
    * Önce ford_web.py.YEDEK-<zaman> yedeği alır.
    * Zaten eklenmişse tekrar eklemez (işaret satırına bakar).
    * Ekledikten sonra sözdizimini derleyerek DOĞRULAR; hata olursa
      yedeği geri yükler ve hiçbir şey değiştirmez.

KULLANIM (Pi'de):
    python3 ford_web_muzik_ekle.py                 # /home/ford/ford_web.py
    python3 ford_web_muzik_ekle.py /yol/ford_web.py
    sudo systemctl restart ford
"""

import os
import re
import sys
import time
import py_compile

ISARET = "FORD MUZIK YONETIM"

BLOK = r'''
# === FORD MUZIK YONETIM (otomatik eklendi) ===
import os as _m_os
from flask import request as _m_req, jsonify as _m_json, send_file as _m_send
_M_KLASOR = "/home/ford/MUZIK"
_M_IZIN = (".mp3", ".wav", ".m4a", ".ogg", ".flac")
_M_SAYFA = "/home/ford/muzik.html"

def _m_tara():
    try:
        _g = globals()
        if "_MUZIK" in _g and _g["_MUZIK"] and hasattr(_g["_MUZIK"][0], "tara"):
            _g["_MUZIK"][0].tara()
    except Exception:
        pass

@{APP}.route("/muzik")
def _m_sayfa():
    return _m_send(_M_SAYFA)

@{APP}.route("/api/muzik/liste")
def _m_liste():
    try:
        _l = []
        if _m_os.path.isdir(_M_KLASOR):
            for _f in sorted(_m_os.listdir(_M_KLASOR)):
                _p = _m_os.path.join(_M_KLASOR, _f)
                if _m_os.path.isfile(_p) and _f.lower().endswith(_M_IZIN):
                    _l.append({"ad": _f, "boyut": _m_os.path.getsize(_p)})
        return _m_json({"ok": True, "dosyalar": _l})
    except Exception as _e:
        return _m_json({"ok": False, "hata": str(_e)}), 500

@{APP}.route("/api/muzik/yukle", methods=["POST"])
def _m_yukle():
    try:
        _m_os.makedirs(_M_KLASOR, exist_ok=True)
        _n = 0
        for _f in _m_req.files.getlist("dosya"):
            _ad = _m_os.path.basename((_f.filename or "").strip())
            _ad = _ad.replace("/", "_").replace("\\", "_")
            if not _ad or not _ad.lower().endswith(_M_IZIN):
                continue
            _f.save(_m_os.path.join(_M_KLASOR, _ad))
            _n += 1
        _m_tara()
        return _m_json({"ok": True, "adet": _n})
    except Exception as _e:
        return _m_json({"ok": False, "hata": str(_e)}), 500

@{APP}.route("/api/muzik/sil", methods=["POST"])
def _m_sil():
    try:
        _d = _m_req.get_json(force=True, silent=True) or {}
        _ad = _m_os.path.basename(str(_d.get("ad", "")))
        _p = _m_os.path.join(_M_KLASOR, _ad)
        if _ad and _m_os.path.isfile(_p) and _ad.lower().endswith(_M_IZIN):
            _m_os.remove(_p)
            _m_tara()
            return _m_json({"ok": True})
        return _m_json({"ok": False, "hata": "dosya yok"}), 404
    except Exception as _e:
        return _m_json({"ok": False, "hata": str(_e)}), 500
# === /FORD MUZIK YONETIM ===
'''


def bul_ekleme_noktasi(satirlar):
    """(indeks, app_degisken_adi) döner. Blok bu indeksin ÖNÜNE eklenir."""
    flask_pat = re.compile(r'^(\s*)([A-Za-z_]\w*)\s*=\s*Flask\s*\(')
    route_pat = re.compile(r'^\s*@([A-Za-z_]\w*)\.route\b')

    # 1) 'app = Flask(' bul -> ifadenin bittiği satırdan SONRASINI döndür
    for i, l in enumerate(satirlar):
        m = flask_pat.match(l)
        if m:
            appvar = m.group(2)
            # parantez dengesini takip et (çok satırlı Flask(...) olabilir)
            denge = 0
            j = i
            baslo = False
            while j < len(satirlar):
                for ch in satirlar[j]:
                    if ch == '(':
                        denge += 1; baslo = True
                    elif ch == ')':
                        denge -= 1
                if baslo and denge <= 0:
                    break
                j += 1
            return j + 1, appvar

    # 2) Flask( bulunamazsa ilk @app.route'un ÖNÜNE ekle (app zaten tanımlı)
    for i, l in enumerate(satirlar):
        m = route_pat.match(l)
        if m:
            return i, m.group(1)

    return None, None


def main():
    yol = sys.argv[1] if len(sys.argv) > 1 else "/home/ford/ford_web.py"
    if not os.path.isfile(yol):
        print("HATA: bulunamadı:", yol)
        print("Doğru yolu ver:  python3 ford_web_muzik_ekle.py /home/ford/ford_web.py")
        sys.exit(1)

    with open(yol, "r", encoding="utf-8") as f:
        kaynak = f.read()

    if ISARET in kaynak:
        print("Zaten eklenmiş (işaret bulundu). Değişiklik yapılmadı:", yol)
        sys.exit(0)

    satirlar = kaynak.splitlines(keepends=True)
    nokta, appvar = bul_ekleme_noktasi(satirlar)
    if nokta is None:
        print("HATA: Flask app / @route bulunamadı. ford_web.py beklenenden farklı.")
        print("Elle ekleme için yardım isteyebilirsin.")
        sys.exit(2)

    blok = BLOK.replace("{APP}", appvar)
    if not satirlar[nokta - 1].endswith("\n"):
        satirlar[nokta - 1] += "\n"
    yeni = "".join(satirlar[:nokta]) + blok + "\n" + "".join(satirlar[nokta:])

    yedek = yol + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
    with open(yedek, "w", encoding="utf-8") as f:
        f.write(kaynak)

    with open(yol, "w", encoding="utf-8") as f:
        f.write(yeni)

    # Doğrula; bozuksa geri al
    try:
        py_compile.compile(yol, doraise=True)
    except py_compile.PyCompileError as e:
        with open(yol, "w", encoding="utf-8") as f:
            f.write(kaynak)
        print("HATA: eklenince sözdizimi bozuldu, GERİ ALINDI. Dosyaya dokunulmadı.")
        print("Ayrıntı:", str(e)[:300])
        print("(yedek yine de duruyor:", yedek, ")")
        sys.exit(3)

    print("TAMAM ✓  Müzik yönetimi eklendi:", yol)
    print("  app değişkeni :", appvar)
    print("  yedek         :", yedek)
    print("Şimdi:  sudo systemctl restart ford")


if __name__ == "__main__":
    main()
