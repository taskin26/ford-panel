#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_yedek_ekle.py  —  Panele "Yedeği İndir" özelliği ekler
=====================================================================
28 Kasım 2026

NE EKLER:
  1) ford_web.py  -> GET /api/yedek/indir
       Tüm /home/ford (kod + ayar + MÜZİK + _fabrika) + systemd servis
       dosyalarını TEK .tar.gz olarak AKITARAK indirtir (geçici dosya
       yok, RAM'i doldurmaz). SD kart bozulsa bile buradan kurtarılır.
  2) ford_ekran.html -> Sistem sekmesi, Fabrika'nın altına "💾 Yedeği İndir"
       butonu (PC/tablet tarayıcısından tıklayıp indirirsin).

GÜVENLİ:
  * Her dosyanın ÖNCE yedeğini alır (.YEDEK-<zaman>).
  * ford_web.py: ekledikten sonra DERLER + IMPORT eder (ford_* kardeş
    modüller engellenir, donanıma dokunulmaz); hata olursa GERİ ALIR.
  * ford_ekran.html: çapa (anchor) bulunamazsa dokunmaz; ekleme saf
    metin-ekleme olduğu için içerik bozulmaz.
  * İki kez çalıştırmak zararsız (idempotent).

KULLANIM (Pi'de):
    python3 ford_yedek_ekle.py
    sudo systemctl restart ford
"""

import os
import re
import sys
import time
import py_compile
import importlib.util

WEB = "/home/ford/ford_web.py"
HTML = "/home/ford/ford_ekran.html"
WEB_ISARET = "FORD YEDEK INDIR"
HTML_ISARET = "FORD YEDEK BUTON"

# --- ford_web.py'ye eklenecek uç (sütun 0 şablon; fonksiyona girintiyle eklenir) ---
WEB_BLOK = r'''# === FORD YEDEK INDIR (otomatik eklendi) ===
import os as _y_os, time as _y_time, tarfile as _y_tar
from flask import Response as _y_Resp

@{APP}.route("/api/yedek/indir")
def _y_indir():
    _kok = "/home/ford"
    _adlar = []
    for _d, _alt, _dosyalar in _y_os.walk(_kok):
        if "__pycache__" in _d:
            continue
        for _f in _dosyalar:
            if _f.endswith(".pyc"):
                continue
            _adlar.append(_y_os.path.join(_d, _f))
    for _s in ("/etc/systemd/system/ford.service",
               "/etc/systemd/system/ford-btkomut.service"):
        if _y_os.path.exists(_s):
            _adlar.append(_s)

    class _Akis:
        def __init__(self):
            self.b = b""
        def write(self, v):
            self.b += v
            return len(v)
        def al(self):
            v = self.b
            self.b = b""
            return v

    def _uret():
        _a = _Akis()
        with _y_tar.open(fileobj=_a, mode="w:gz") as _t:
            for _yol in _adlar:
                try:
                    _t.add(_yol, arcname=_yol.lstrip("/"), recursive=False)
                except Exception:
                    pass
                _v = _a.al()
                if _v:
                    yield _v
        _v = _a.al()
        if _v:
            yield _v

    _ad = "ford_yedek_" + _y_time.strftime("%Y%m%d_%H%M") + ".tar.gz"
    _r = _y_Resp(_uret(), mimetype="application/gzip")
    _r.headers["Content-Disposition"] = 'attachment; filename="' + _ad + '"'
    return _r
# === /FORD YEDEK INDIR ==='''

# --- ford_ekran.html'e eklenecek buton (fbSonuc'tan sonra) ---
HTML_ANCHOR = '<div class="gc-durum" id="fbSonuc"></div>'
HTML_BLOK = '''
        <!-- FORD YEDEK BUTON -->
        <div class="s-title">💾 Yedek (PC'ye indir)</div>
        <div class="gc-aciklama">
          Tüm sistemi (kodlar, ayarlar, <b>müzikler</b>, servisler) tek dosyada indirir.
          SD kart bozulsa bile buradan kurtarırsın. <b>Bilgisayarın tarayıcısından</b> aç, indir, flash belleğe at.
        </div>
        <div class="fb-dugme">
          <a class="s-btn s-btn-p" href="/api/yedek/indir" download>💾 Yedeği İndir</a>
        </div>
        <!-- /FORD YEDEK BUTON -->'''


# ====================  ford_web.py yaması  ====================
def _blok_gir(appvar, girinti):
    govde = WEB_BLOK.replace("{APP}", appvar)
    return "\n".join((girinti + s) if s.strip() else s for s in govde.split("\n"))


def _web_plan(satirlar):
    flask_pat = re.compile(r'^(\s*)([A-Za-z_]\w*)\s*=\s*Flask\s*\(')
    for i, l in enumerate(satirlar):
        m = flask_pat.match(l)
        if not m:
            continue
        girinti, appvar = m.group(1), m.group(2)
        if girinti == "":
            return i + 1, appvar, "", "sonra"
        ret_pat = re.compile(r'^' + re.escape(girinti) + r'return\s+' + re.escape(appvar) + r'\b')
        for k in range(i + 1, len(satirlar)):
            if ret_pat.match(satirlar[k]):
                return k, appvar, girinti, "once"
        return None, None, None, None
    return None, None, None, None


def _engelli_import(yol):
    """ford_* kardeş modülleri engelleyerek güvenli import testi."""
    class _E:
        def find_spec(self, ad, y=None, h=None):
            if ad.startswith("ford_") and ad != "_fw_test":
                raise ModuleNotFoundError("engel: " + ad, name=ad)
            return None
    e = _E()
    sys.meta_path.insert(0, e)
    try:
        spec = importlib.util.spec_from_file_location("_fw_test", yol)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        try:
            sys.meta_path.remove(e)
        except ValueError:
            pass


def web_yama():
    if not os.path.isfile(WEB):
        print("  ! ford_web.py bulunamadı:", WEB)
        return False
    kaynak = open(WEB, encoding="utf-8").read()
    if WEB_ISARET in kaynak:
        print("  = ford_web.py: zaten ekli, atlandı.")
        return True
    satirlar = kaynak.splitlines(keepends=True)
    nokta, appvar, girinti, konum = _web_plan(satirlar)
    if nokta is None:
        print("  ! ford_web.py: Flask app noktası bulunamadı, DOKUNULMADI.")
        return False
    blok = _blok_gir(appvar, girinti)
    if not satirlar[nokta - 1].endswith("\n"):
        satirlar[nokta - 1] += "\n"
    yeni = "".join(satirlar[:nokta]) + blok + "\n" + "".join(satirlar[nokta:])
    yedek = WEB + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
    open(yedek, "w", encoding="utf-8").write(kaynak)
    open(WEB, "w", encoding="utf-8").write(yeni)
    try:
        py_compile.compile(WEB, doraise=True)
        _engelli_import(WEB)
    except Exception as e:
        open(WEB, "w", encoding="utf-8").write(kaynak)
        print("  ! ford_web.py: test patladı, GERİ ALINDI ->", type(e).__name__, str(e)[:120])
        return False
    print("  ✓ ford_web.py: /api/yedek/indir eklendi. (yedek:", os.path.basename(yedek) + ")")
    return True


# ====================  ford_ekran.html yaması  ====================
def html_yama():
    if not os.path.isfile(HTML):
        print("  ! ford_ekran.html bulunamadı:", HTML)
        return False
    kaynak = open(HTML, encoding="utf-8").read()
    if HTML_ISARET in kaynak:
        print("  = ford_ekran.html: zaten ekli, atlandı.")
        return True
    if HTML_ANCHOR not in kaynak:
        print("  ! ford_ekran.html: çapa (fbSonuc) bulunamadı, DOKUNULMADI.")
        return False
    yeni = kaynak.replace(HTML_ANCHOR, HTML_ANCHOR + HTML_BLOK, 1)
    # güvenlik: sadece ekleme olmalı (uzunluk tam blok kadar artmalı)
    if len(yeni) != len(kaynak) + len(HTML_BLOK):
        print("  ! ford_ekran.html: beklenmeyen fark, DOKUNULMADI.")
        return False
    yedek = HTML + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
    open(yedek, "w", encoding="utf-8").write(kaynak)
    open(HTML, "w", encoding="utf-8").write(yeni)
    print("  ✓ ford_ekran.html: Yedek butonu eklendi. (yedek:", os.path.basename(yedek) + ")")
    return True


def main():
    global WEB, HTML
    if len(sys.argv) > 1:
        WEB = sys.argv[1]
    if len(sys.argv) > 2:
        HTML = sys.argv[2]
    print("FORD yedek özelliği ekleniyor...")
    a = web_yama()
    b = html_yama()
    if a and b:
        print("TAMAM ✓  Şimdi:  sudo systemctl restart ford")
    else:
        print("UYARI: en az biri eklenemedi (yukarı bak). Sistem bozulmadı.")


if __name__ == "__main__":
    main()
