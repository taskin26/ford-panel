#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_yakinlik_dugme_ekle.py  —  Paneldeki "Yakınlık Kilidi" düğmesini CANLANDIRIR
=====================================================================
29 Ekim 2026

SORUN:
    Paneldeki "Yakınlık Kilidi" düğmesi (t_yakinlik_zorunlu) hiçbir şeye
    bağlı değildi (ford_faz3'te YAKINLIK_ZORUNLU sabit, düğme onu ezmiyordu).
    Açıp kapamak için SSH'dan yakinlik_ac.py / yakinlik_kapat.py gerekiyordu.

NE EKLER:
    1) ford_web.py  -> GET/POST /api/yakinlik
         POST {aktif:true/false}:
            - FZ.YAKINLIK_ZORUNLU = aktif        (CANLI, anında etki)
            - ford_faz3.py içindeki satırı güvenle değiştirir (KALICI,
              yeniden başlatınca da geçerli) — yakinlik_ac.py mantığı.
         GET: {"aktif": <su anki durum>}
    2) ford_ekran.html -> düğmenin onclick'ini yakinlikKilidiBas'a çevirir,
         küçük bir JS + açılışta durumu /api/yakinlik'ten senkron eder.

    BT / servis / eşleşme ayarlarına HİÇ dokunmaz.

GÜVENLİ:
    * Her dosyanın önce yedeğini alır.
    * ford_web.py: ekledikten sonra derler + güvenli import testi; hata
      olursa geri alır. ford_faz3.py'yi ÇALIŞMA ANINDA düzenler ama sadece
      "YAKINLIK_ZORUNLU = True/False" satırını (regex, tek satır) — ve o an
      yedek alıp derlemeyi doğrular, bozulursa geri yükler.
    * ford_ekran.html: çapa yoksa dokunmaz; saf metin-ekleme.
    * Idempotent.

KULLANIM (Pi'de):
    python3 ford_yakinlik_dugme_ekle.py
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
WEB_ISARET = "FORD YAKINLIK DUGME"
HTML_ISARET = "FORD YAKINLIK DUGME JS"

WEB_BLOK = r'''# === FORD YAKINLIK DUGME (otomatik eklendi) ===
import os as _yk_os, re as _yk_re
from flask import request as _yk_req, jsonify as _yk_json

def _yk_dosya():
    return _yk_os.path.join(_yk_os.path.dirname(_yk_os.path.abspath(__file__)), "ford_faz3.py")

def _yk_kalici_yaz(aktif):
    # ford_faz3.py'de SADECE modul-seviyesi 'YAKINLIK_ZORUNLU = True/False'
    # satirini degistir. Once yedek + derleme dogrulamasi; bozulursa geri al.
    _yol = _yk_dosya()
    try:
        _s = open(_yol, encoding="utf-8").read()
    except Exception:
        return False
    _yeni = _yk_re.sub(r'(?m)^YAKINLIK_ZORUNLU = (?:True|False)',
                       'YAKINLIK_ZORUNLU = ' + ('True' if aktif else 'False'),
                       _s, count=1)
    if _yeni == _s:
        return True   # zaten o deger ya da satir bulunamadi; canli ayar yeterli
    _yed = _yol + ".YKYEDEK"
    try:
        open(_yed, "w", encoding="utf-8").write(_s)
        open(_yol, "w", encoding="utf-8").write(_yeni)
        import py_compile as _pc
        _pc.compile(_yol, doraise=True)
        return True
    except Exception:
        try:
            open(_yol, "w", encoding="utf-8").write(_s)   # geri yukle
        except Exception:
            pass
        return False

@{APP}.route("/api/yakinlik")
def _yk_oku():
    return _yk_json({"aktif": bool(getattr(FZ, "YAKINLIK_ZORUNLU", False))})

@{APP}.route("/api/yakinlik", methods=["POST"])
def _yk_yaz():
    _d = _yk_req.get_json(silent=True) or {}
    _aktif = bool(_d.get("aktif"))
    try:
        setattr(FZ, "YAKINLIK_ZORUNLU", _aktif)   # CANLI etki
    except Exception:
        pass
    _kal = _yk_kalici_yaz(_aktif)                  # KALICI (restart sonrasi)
    return _yk_json({"ok": True, "aktif": _aktif, "kalici": _kal})
# === /FORD YAKINLIK DUGME ==='''

# HTML: dugmenin onclick'i
HTML_ESKI = 'data-key="t_yakinlik_zorunlu" onclick="toggleBas(this)"'
HTML_YENI = 'data-key="t_yakinlik_zorunlu" onclick="yakinlikKilidiBas(this)"'

# HTML: JS fonksiyonu (toggleBas'tan ONCE eklenir)
HTML_JS_ANCHOR = 'function toggleBas(el){'
HTML_JS = '''/* FORD YAKINLIK DUGME JS */
function yakinlikKilidiBas(el){
  el.classList.toggle('on');
  var aktif = el.classList.contains('on');
  fetch('/api/yakinlik',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({aktif:aktif})}).catch(function(){});
}
window.addEventListener('load', function(){
  setTimeout(function(){
    fetch('/api/yakinlik').then(function(r){return r.json();}).then(function(d){
      var el=document.querySelector('.toggle[data-key="t_yakinlik_zorunlu"]');
      if(el){ if(d&&d.aktif) el.classList.add('on'); else el.classList.remove('on'); }
    }).catch(function(){});
  }, 900);
});
'''


# ---------- ford_web.py ----------
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
            return i + 1, appvar
        ret_pat = re.compile(r'^' + re.escape(girinti) + r'return\s+' + re.escape(appvar) + r'\b')
        for k in range(i + 1, len(satirlar)):
            if ret_pat.match(satirlar[k]):
                return k, appvar
        return None, None
    return None, None


def _engelli_import(yol):
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
        print("  ! ford_web.py bulunamadı:", WEB); return False
    kaynak = open(WEB, encoding="utf-8").read()
    if WEB_ISARET in kaynak:
        print("  = ford_web.py: zaten ekli, atlandı."); return True
    satirlar = kaynak.splitlines(keepends=True)
    nokta, appvar = _web_plan(satirlar)
    if nokta is None:
        print("  ! ford_web.py: ekleme noktası bulunamadı, DOKUNULMADI."); return False
    blok = _blok_gir(appvar, "    ")  # fonksiyon govdesi girintisi
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
        print("  ! ford_web.py: test patladı, GERİ ALINDI ->", type(e).__name__, str(e)[:120]); return False
    print("  ✓ ford_web.py: /api/yakinlik eklendi. (yedek:", os.path.basename(yedek) + ")")
    return True


# ---------- ford_ekran.html ----------
def html_yama():
    if not os.path.isfile(HTML):
        print("  ! ford_ekran.html bulunamadı:", HTML); return False
    kaynak = open(HTML, encoding="utf-8").read()
    if HTML_ISARET in kaynak:
        print("  = ford_ekran.html: zaten ekli, atlandı."); return True
    if HTML_ESKI not in kaynak:
        print("  ! ford_ekran.html: yakınlık düğmesi (onclick) bulunamadı, DOKUNULMADI."); return False
    if HTML_JS_ANCHOR not in kaynak:
        print("  ! ford_ekran.html: toggleBas bulunamadı, DOKUNULMADI."); return False
    yeni = kaynak.replace(HTML_ESKI, HTML_YENI, 1)
    yeni = yeni.replace(HTML_JS_ANCHOR, HTML_JS + HTML_JS_ANCHOR, 1)
    yedek = HTML + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
    open(yedek, "w", encoding="utf-8").write(kaynak)
    open(HTML, "w", encoding="utf-8").write(yeni)
    print("  ✓ ford_ekran.html: düğme canlandırıldı. (yedek:", os.path.basename(yedek) + ")")
    return True


def main():
    global WEB, HTML
    if len(sys.argv) > 1: WEB = sys.argv[1]
    if len(sys.argv) > 2: HTML = sys.argv[2]
    print("FORD yakınlık düğmesi canlandırılıyor...")
    a = web_yama()
    b = html_yama()
    if a and b:
        print("TAMAM ✓  Şimdi:  sudo systemctl restart ford")
    else:
        print("UYARI: en az biri eklenemedi (yukarı bak). Sistem bozulmadı.")


if __name__ == "__main__":
    main()
