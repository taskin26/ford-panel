#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_btmac_muzik_ekle.py  —  BLUETOOTH kimliği + MÜZİK izni
=====================================================================
29 Ekim 2026  (ford_guvenlik_ekle.py + ford_yetki_ince_ekle.py SONRASI)

İKİ EKSİĞİ KAPATIR:

1) BLUETOOTH'ta telefon-bazlı güvenlik:
   BT köprüsü (ford_btkomut.py) artık bağlı telefonun BT MAC'ini
   'X-Ford-Mac' başlığıyla yolluyor. Bu yama _g_mac'i, bu başlığı
   YALNIZCA localhost'tan (127.0.0.1 / ::1) gelince kabul edecek şekilde
   günceller. Böylece WiFi'de olduğu gibi BT'de de her telefon ayrı
   tanınır; izinler BT'de de çalışır. (LAN'daki başka biri başlığı
   taklit edemez: başlık yalnız köprüden/localhost'tan geçerli.)

2) MÜZİK izni (6. izin):
   İzin listesine 'muzik' eklenir, güvenlik listesinde Müzik çipi çıkar,
   /api/muzik POST (oynat/duraklat/sıradaki) bu izne bağlanır.
   ESKİ davranış korunur: önceden tanımlı telefonlarda müzik AÇIK kalır
   (kapatmak istersen çipten kapatırsın). Şifre kurulana kadar her şey
   açık (opt-in) — kurulumda kilitlenmezsin. GET /api/muzik (durum) açık.

GÜVENLİ: yedek + derleme + güvenli import (ford_* engelli) + geri alma;
    HTML saf metin-değişimi; idempotent.

KULLANIM (Pi'de):
    python3 ford_btmac_muzik_ekle.py
    sudo systemctl restart ford
    sudo systemctl restart ford-btkomut   # yeni köprü (MAC başlığı) için
"""

import os
import sys
import time
import py_compile
import importlib.util

WEB = "/home/ford/ford_web.py"
HTML = "/home/ford/ford_ekran.html"
ISARET = "FORD BTMAC MUZIK"

# ---- 1) _g_mac: X-Ford-Mac başlığına (yalnız localhost) güven ----
MAC_ESKI = '''def _g_mac(req):
    try:
        _ip = req.remote_addr or ""
        if YK is not None and _ip:
            return (YK.ip_den_mac(_ip) or "").upper()
    except Exception:
        pass
    return ""'''
MAC_YENI = '''def _g_mac(req):  # FORD BTMAC MUZIK
    try:
        _ip = req.remote_addr or ""
        _hdr = (req.headers.get("X-Ford-Mac") or "").strip().upper()
        if _hdr and _ip in ("127.0.0.1", "::1"):   # yalniz BT koprusu (localhost)
            return _hdr
        if YK is not None and _ip:
            return (YK.ip_den_mac(_ip) or "").upper()
    except Exception:
        pass
    return ""'''

# ---- 2a) izin listesine muzik ekle ----
IZIN_ESKI = '_G_IZINLER = ("kapi", "cam", "motor", "bagaj", "isik")'
IZIN_YENI = '_G_IZINLER = ("kapi", "cam", "motor", "bagaj", "isik", "muzik")  # FORD BTMAC MUZIK'

# ---- 2b) _g_yetki_coz: muzik eski kayitlarda ACIK kalsin ----
COZ_ESKI = '''def _g_yetki_coz(bilgi):
    """Bir telefon kaydindan izin sozlugu uretir. Once 'yetki', yoksa 'rol'."""
    _y = bilgi.get("yetki")
    if isinstance(_y, dict):
        return {k: bool(_y.get(k)) for k in _G_IZINLER}
    _rol = bilgi.get("rol", "misafir")
    try:
        _izin = getattr(FZ, "ROL_IZIN", {}).get(_rol, set())
    except Exception:
        _izin = set()
    return {k: (k in _izin) for k in _G_IZINLER}'''
COZ_YENI = '''def _g_yetki_coz(bilgi):  # FORD BTMAC MUZIK
    """Bir telefon kaydindan izin sozlugu uretir. Once 'yetki', yoksa 'rol'."""
    _y = bilgi.get("yetki")
    if isinstance(_y, dict):
        _r = {k: bool(_y.get(k)) for k in _G_IZINLER}
        if "muzik" not in _y:            # eski kayit: muzik anahtari yok -> acik birak
            _r["muzik"] = True
        return _r
    _rol = bilgi.get("rol", "misafir")
    try:
        _izin = getattr(FZ, "ROL_IZIN", {}).get(_rol, set())
    except Exception:
        _izin = set()
    _r = {k: (k in _izin) for k in _G_IZINLER}
    _r["muzik"] = True                   # rol'den turetilende muzik herkese acik (eski davranis)
    return _r'''

# ---- 2c) /api/muzik POST kapisi ----
MUZIK_ESKI = '''    def _muzik_komut():
        m = _MUZIK[0]
        if m is None:
            return jsonify({"ok": False, "hata": "muzik calar yok"})'''
MUZIK_YENI = '''    def _muzik_komut():
        # GUVENLIK: sifre kuruluysa muzik izni (opt-in).  FORD BTMAC MUZIK
        if _g_sifre_var() and not _g_yetki_oto(_g_mac(request)).get("muzik", False):
            return jsonify({"ok": False, "yetkisiz": True,
                            "hata": "Bu telefonun müzik yetkisi yok"})
        m = _MUZIK[0]
        if m is None:
            return jsonify({"ok": False, "hata": "muzik calar yok"})'''

# ---- 2d) güvenlik listesi JS: Müzik çipi ----
JS_ESKI = "var IZ=[['kapi','Kapı'],['cam','Cam'],['motor','Motor'],['bagaj','Bagaj'],['isik','Işık']];"
JS_YENI = "var IZ=[['kapi','Kapı'],['cam','Cam'],['motor','Motor'],['bagaj','Bagaj'],['isik','Işık'],['muzik','Müzik']];"


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
    print("Bluetooth kimliği + Müzik izni ekleniyor...")

    # ---- ford_web ----
    if not os.path.isfile(WEB):
        print("  ! ford_web.py yok"); sys.exit(1)
    src = open(WEB, encoding="utf-8").read()
    if "_g_yetki_coz" not in src or "_g_mac" not in src:
        print("  ! Önce ford_guvenlik_ekle.py + ford_yetki_ince_ekle.py uygulanmalı. DOKUNULMADI."); sys.exit(2)
    if ISARET in src:
        print("  = ford_web.py: zaten ekli.")
    else:
        orj = src
        adimlar = [("_g_mac", MAC_ESKI, MAC_YENI),
                   ("_G_IZINLER", IZIN_ESKI, IZIN_YENI),
                   ("_g_yetki_coz", COZ_ESKI, COZ_YENI),
                   ("/api/muzik kapisi", MUZIK_ESKI, MUZIK_YENI)]
        for ad, eski, yeni in adimlar:
            if eski not in src:
                print(f"  ! ford_web.py: '{ad}' çapası beklenen halde değil. DOKUNULMADI."); sys.exit(2)
            src = src.replace(eski, yeni, 1)
        yedek = WEB + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
        open(yedek, "w", encoding="utf-8").write(orj); open(WEB, "w", encoding="utf-8").write(src)
        try:
            py_compile.compile(WEB, doraise=True); _engelli_import(WEB)
        except Exception as e:
            open(WEB, "w", encoding="utf-8").write(orj)
            print("  ! ford_web.py: test patladı, GERİ ALINDI ->", type(e).__name__, str(e)[:140]); sys.exit(3)
        print("  ✓ ford_web.py: BT kimliği (X-Ford-Mac) + müzik izni + kapı.")

    # ---- ford_ekran: Müzik çipi ----
    if not os.path.isfile(HTML):
        print("  ! ford_ekran.html yok"); sys.exit(1)
    h = open(HTML, encoding="utf-8").read()
    if "['muzik','Müzik']" in h:
        print("  = ford_ekran.html: Müzik çipi zaten var.")
    elif JS_ESKI not in h:
        print("  ! ford_ekran.html: izin çipleri (ynListele) bulunamadı — önce ford_yetki_ince_ekle.py. DOKUNULMADI.")
    else:
        yeni = h.replace(JS_ESKI, JS_YENI, 1)
        yb = HTML + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
        open(yb, "w", encoding="utf-8").write(h); open(HTML, "w", encoding="utf-8").write(yeni)
        print("  ✓ ford_ekran.html: güvenlik listesine Müzik çipi eklendi.")

    print("TAMAM ✓  Şimdi:  sudo systemctl restart ford && sudo systemctl restart ford-btkomut")


if __name__ == "__main__":
    main()
