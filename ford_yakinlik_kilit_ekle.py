#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_yakinlik_kilit_ekle.py  —  Yakinlik Kilidi toggle'ini SIFREYE baglar
=====================================================================
29 Ekim 2026

SORUN: Guvenlik'teki "Yakinlik Kilidi" toggle sifresizdi; misafir
    yakinlik guvenligini kapatabiliyordu.

NE YAPAR (ford_guvenlik_ekle.py + ford_yakinlik_dugme_ekle.py SONRASI):
    - /api/yakinlik POST: sifre kuruluysa gecerli yonetici sifresi ister.
    - yakinlikKilidiBas(): once yonetici girisi (oturumda _ynSifre) ister;
      sifreyi yollar, basarisizsa toggle'i geri alir.

GUVENLI: yedek + derleme + guvenli import (ford_* engelli) + geri alma;
    HTML saf metin-degisimi. Idempotent.

KULLANIM (Pi'de):
    python3 ford_yakinlik_kilit_ekle.py
    sudo systemctl restart ford
"""

import os
import sys
import time
import py_compile
import importlib.util

WEB = "/home/ford/ford_web.py"
HTML = "/home/ford/ford_ekran.html"
ISARET = "FORD YAKINLIK KILIT"

# ford_web: _yk_yaz icine sifre kontrolu ekle
WEB_ESKI = '''        _d = _yk_req.get_json(silent=True) or {}
        _aktif = bool(_d.get("aktif"))'''
WEB_YENI = '''        _d = _yk_req.get_json(silent=True) or {}
        if _g_sifre_var() and not _g_sifre_dogru(_d.get("sifre") or ""):  # FORD YAKINLIK KILIT
            return _yk_json({"ok": False, "hata": "yonetici sifresi gerekli"}), 403
        _aktif = bool(_d.get("aktif"))'''

# ford_ekran: yakinlikKilidiBas'i sifreli yap
HTML_ESKI = '''function yakinlikKilidiBas(el){
  el.classList.toggle('on');
  var aktif = el.classList.contains('on');
  fetch('/api/yakinlik',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({aktif:aktif})}).catch(function(){});
}'''
HTML_YENI = '''function yakinlikKilidiBas(el){ /* FORD YAKINLIK KILIT */
  if(typeof _ynSifre==='undefined' || !_ynSifre){ alert('Önce Yönetici girişi yapın (yukarıdaki Giriş).'); return; }
  el.classList.toggle('on');
  var aktif = el.classList.contains('on');
  var _p=(typeof _ynPost==='function')?_ynPost('/api/yakinlik',{aktif:aktif,sifre:_ynSifre}):fetch('/api/yakinlik',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({aktif:aktif,sifre:_ynSifre})}).then(function(r){return r.json();});
  _p.then(function(d){ if(!d||!d.ok){ el.classList.toggle('on'); alert((d&&d.hata)||'olmadı'); } }).catch(function(){ el.classList.toggle('on'); });
}'''


def _engelli_import(yol):
    class _E:
        def find_spec(self, ad, y=None, h=None):
            if ad.startswith("ford_") and ad != "_fw_test":
                raise ModuleNotFoundError("engel: " + ad, name=ad)
            return None
    e = _E(); sys.meta_path.insert(0, e)
    try:
        spec = importlib.util.spec_from_file_location("_fw_test", yol)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    finally:
        try: sys.meta_path.remove(e)
        except ValueError: pass


def main():
    global WEB, HTML
    if len(sys.argv) > 1: WEB = sys.argv[1]
    if len(sys.argv) > 2: HTML = sys.argv[2]
    print("Yakınlık toggle şifreye bağlanıyor...")

    # ford_web
    if not os.path.isfile(WEB):
        print("  ! ford_web.py yok:", WEB); sys.exit(1)
    wsrc = open(WEB, encoding="utf-8").read()
    if ISARET in wsrc:
        print("  = ford_web.py: zaten ekli.")
    else:
        if "_g_sifre_var" not in wsrc:
            print("  ! Önce ford_guvenlik_ekle.py uygulanmalı (sifre uclari yok). DOKUNULMADI."); sys.exit(2)
        if WEB_ESKI not in wsrc:
            print("  ! ford_web.py: /api/yakinlik bloğu beklenen halde değil. DOKUNULMADI."); sys.exit(2)
        wyeni = wsrc.replace(WEB_ESKI, WEB_YENI, 1)
        yb = WEB + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
        open(yb, "w", encoding="utf-8").write(wsrc); open(WEB, "w", encoding="utf-8").write(wyeni)
        try:
            py_compile.compile(WEB, doraise=True); _engelli_import(WEB)
        except Exception as e:
            open(WEB, "w", encoding="utf-8").write(wsrc)
            print("  ! ford_web.py: test patladı, GERİ ALINDI ->", type(e).__name__, str(e)[:120]); sys.exit(3)
        print("  ✓ ford_web.py: /api/yakinlik artık şifre istiyor.")

    # ford_ekran
    if not os.path.isfile(HTML):
        print("  ! ford_ekran.html yok:", HTML); sys.exit(1)
    hsrc = open(HTML, encoding="utf-8").read()
    if "FORD YAKINLIK KILIT" in hsrc and "yakinlikKilidiBas(el){ /* FORD YAKINLIK KILIT */" in hsrc:
        print("  = ford_ekran.html: zaten ekli.")
    elif HTML_ESKI not in hsrc:
        print("  ! ford_ekran.html: yakinlikKilidiBas beklenen halde değil. DOKUNULMADI.")
    else:
        hyeni = hsrc.replace(HTML_ESKI, HTML_YENI, 1)
        hb = HTML + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
        open(hb, "w", encoding="utf-8").write(hsrc); open(HTML, "w", encoding="utf-8").write(hyeni)
        print("  ✓ ford_ekran.html: yakınlık toggle girişsiz çalışmaz.")

    print("TAMAM ✓  Şimdi:  sudo systemctl restart ford")


if __name__ == "__main__":
    main()
