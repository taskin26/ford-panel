#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_web_muzik_ekle.py  —  ford_web.py'ye MÜZİK YÖNETİMİ uçlarını ekler
=====================================================================
28 Kasım 2026  (v2 — fabrika-fonksiyon düzeltmesi)

NE EKLER (ford_web.py'ye, mevcut hiçbir şeyi bozmadan):
    GET  /muzik              -> yönetim sayfası (muzik.html)
    GET  /api/muzik/liste    -> MUZIK klasöründeki MP3'leri listeler
    POST /api/muzik/yukle    -> çoklu MP3 yükler (multipart, alan adı "dosya")
    POST /api/muzik/sil      -> JSON {"ad": "sarki.mp3"} tek dosya siler

NEDEN v2:
    ford_web.py'de Flask uygulaması bir FONKSİYONUN İÇİNDE kuruluyor
    (app = Flask(...) girintili, en sonda 'return app'). Route'lar bu
    fonksiyonun içine, 'return app'ten HEMEN ÖNCE, doğru girintiyle
    eklenmeli. (v1 modül seviyesine ekliyordu -> NameError: app.)

GÜVENLİ:
    * Önce ford_web.py.YEDEK-<zaman> yedeği alır.
    * Zaten eklenmişse tekrar eklemez.
    * Ekledikten sonra hem DERLER hem IMPORT eder; biri patlarsa yedeği
      geri yükler, hiçbir şey değiştirmez.

KULLANIM (Pi'de):
    python3 ford_web_muzik_ekle.py                 # /home/ford/ford_web.py
    sudo systemctl restart ford
"""

import os
import re
import sys
import time
import py_compile
import importlib.util

ISARET = "FORD MUZIK YONETIM"

# Sütun 0'da yazılı şablon. Fonksiyon içine eklerken her satırın başına
# fonksiyonun girintisi (ör. 4 boşluk) eklenir.
BLOK = r'''# === FORD MUZIK YONETIM (otomatik eklendi) ===
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
# === /FORD MUZIK YONETIM ==='''


def _blok_uret(appvar, girinti):
    """Şablonu appvar ile doldurur ve her satırı 'girinti' ile öteler."""
    govde = BLOK.replace("{APP}", appvar)
    satirlar = govde.split("\n")
    otelenmis = []
    for s in satirlar:
        otelenmis.append((girinti + s) if s.strip() else s)  # boş satırı öteleme
    return "\n".join(otelenmis)


def ekleme_plani(satirlar):
    """
    (indeks, appvar, girinti, 'once'/'sonra') döner.
    - Fabrika fonksiyonu (app = Flask(...) girintili, en sonda 'return app'):
      'return app' satırının ÖNÜNE, fonksiyon girintisiyle.
    - Modül seviyesi (app = Flask(...) girintisiz): Flask ifadesinin SONRASINA,
      sütun 0'da.
    """
    flask_pat = re.compile(r'^(\s*)([A-Za-z_]\w*)\s*=\s*Flask\s*\(')
    for i, l in enumerate(satirlar):
        m = flask_pat.match(l)
        if not m:
            continue
        girinti, appvar = m.group(1), m.group(2)

        if girinti == "":
            # modül seviyesi -> Flask ifadesinin bittiği satırdan sonra, sütun 0
            denge, j, baslo = 0, i, False
            while j < len(satirlar):
                for ch in satirlar[j]:
                    if ch == '(':
                        denge += 1; baslo = True
                    elif ch == ')':
                        denge -= 1
                if baslo and denge <= 0:
                    break
                j += 1
            return j + 1, appvar, "", "sonra"

        # fonksiyon içi -> ayni girintide 'return appvar' bul, ONUN ÖNÜNE
        ret_pat = re.compile(r'^' + re.escape(girinti) + r'return\s+' + re.escape(appvar) + r'\b')
        for k in range(i + 1, len(satirlar)):
            if ret_pat.match(satirlar[k]):
                return k, appvar, girinti, "once"
        # return bulunamadıysa fonksiyon sonuna düşmek riskli; vazgeç
        return None, None, None, None
    return None, None, None, None


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
    nokta, appvar, girinti, konum = ekleme_plani(satirlar)
    if nokta is None:
        print("HATA: Flask app ekleme noktası bulunamadı. ford_web.py beklenenden farklı.")
        print("Bana dosyayı gönder, elle ekleyeyim.")
        sys.exit(2)

    blok = _blok_uret(appvar, girinti)
    if not satirlar[nokta - 1].endswith("\n"):
        satirlar[nokta - 1] += "\n"

    if konum == "sonra":
        yeni = "".join(satirlar[:nokta]) + blok + "\n" + "".join(satirlar[nokta:])
    else:  # 'once' -> 'return app' satırının önüne
        yeni = "".join(satirlar[:nokta]) + blok + "\n" + "".join(satirlar[nokta:])

    yedek = yol + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
    with open(yedek, "w", encoding="utf-8") as f:
        f.write(kaynak)
    with open(yol, "w", encoding="utf-8") as f:
        f.write(yeni)

    # 1) Derleme
    try:
        py_compile.compile(yol, doraise=True)
    except py_compile.PyCompileError as e:
        with open(yol, "w", encoding="utf-8") as f:
            f.write(kaynak)
        print("HATA: sözdizimi bozuldu, GERİ ALINDI. Dosyaya dokunulmadı.")
        print("Ayrıntı:", str(e)[:300], "| yedek:", yedek)
        sys.exit(3)

    # 2) Gerçek import denemesi (NameError gibi çalışma-anı hatalarını yakalar).
    #    GÜVENLİK: test sırasında 'ford_*' kardeş modülleri ENGELLENİR ki
    #    donanıma (nmcli, bluetooth, GPIO...) dokunan modüller YÜKLENMESİN.
    #    ford_web bu modülleri zaten try/except ile opsiyonel yüklüyor.
    class _Engel:
        def find_spec(self, ad, yol2=None, hedef=None):
            if ad.startswith("ford_") and ad != "_ford_web_test":
                raise ModuleNotFoundError("test engeli: " + ad, name=ad)
            return None
    engel = _Engel()
    sys.meta_path.insert(0, engel)
    try:
        spec = importlib.util.spec_from_file_location("_ford_web_test", yol)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:
        with open(yol, "w", encoding="utf-8") as f:
            f.write(kaynak)
        print("HATA: import patladı, GERİ ALINDI. Dosyaya dokunulmadı.")
        print("Ayrıntı:", type(e).__name__, str(e)[:200], "| yedek:", yedek)
        sys.exit(4)
    finally:
        try:
            sys.meta_path.remove(engel)
        except ValueError:
            pass

    print("TAMAM ✓  Müzik yönetimi eklendi:", yol)
    print("  app değişkeni :", appvar, "| konum:", konum, "| girinti:", repr(girinti))
    print("  yedek         :", yedek)
    print("Şimdi:  sudo systemctl restart ford")


if __name__ == "__main__":
    main()
