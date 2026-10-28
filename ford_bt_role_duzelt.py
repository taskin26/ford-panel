#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_bt_role_duzelt.py  —  BLUETOOTH'ta komut/röle engellenmesini düzeltir
=====================================================================
29 Ekim 2026  (ford_btmac_muzik_ekle.py SONRASI)

SORUN (benim hatam):
    BT kimliği eklenince, BT'den bağlanan telefon (eşleşmiş = senin
    onayladığın telefon) "tanınmayan misafir" sayılıp İZİNSİZ kaydediliyor,
    şifre kuruluysa röleyi tetikleyemiyordu.

MANTIK:
    BT köprüsü Pi'ye 127.0.0.1'den ulaşır. BT'ye bağlanmak için telefonun
    ÖNCE Pi ile EŞLEŞMESİ gerekir — eşleştirmeyi zaten SEN yapıyorsun. Yani
    BT'den gelen telefon = sahip onaylı. Bu yüzden BT'den gelen TANINMAYAN
    telefon artık TAM izinli kaydedilir (engellenmez). İstersen listeden
    kısarsın. WiFi'de tanınmayan telefon yine 'misafir' (katı) kalır —
    çünkü ağda eşleşme şartı yok.

NE DEĞİŞİR (sadece ford_web.py):
    - _g_yetki_oto(mac, bt=False): yeni telefon bt ise TAM izinle açılır.
    - _g_yetki_istek(req): BT (localhost) isteğini sahip-onaylı sayar.
    - /api/komut ve /api/muzik kapıları bu yeni mantığı kullanır.

GÜVENLİ: yedek + derleme + güvenli import + geri alma; idempotent.
    APK YENİDEN DERLEME GEREKMEZ (tamamen sunucu tarafı).

KULLANIM (Pi'de):
    python3 ford_bt_role_duzelt.py
    sudo systemctl restart ford
"""

import os
import sys
import time
import py_compile
import importlib.util

WEB = "/home/ford/ford_web.py"
ISARET = "FORD BT ROLE DUZELT"

OTO_ESKI = '''def _g_yetki_oto(mac):
    """Telefonu (gerekirse izinsiz misafir olarak) kaydeder, izin sozlugu doner."""
    if not mac:
        return {k: False for k in _G_IZINLER}
    _d = _g_oku()
    _tel = _d["telefonlar"]
    if mac not in _tel:
        _tel[mac] = {"ad": "Telefon-" + mac.replace(":", "")[-4:],
                     "yetki": {k: False for k in _G_IZINLER},
                     "ilk": int(_g_time.time())}
        _g_yaz(_d)
    return _g_yetki_coz(_tel[mac])'''
OTO_YENI = '''def _g_yetki_oto(mac, bt=False):  # FORD BT ROLE DUZELT
    """Telefonu kaydeder, izin sozlugu doner. BT (eslesmis=sahip onayli) -> tam izin."""
    if not mac:
        return {k: bool(bt) for k in _G_IZINLER}
    _d = _g_oku()
    _tel = _d["telefonlar"]
    if mac not in _tel:
        _tel[mac] = {"ad": ("BT Telefon-" if bt else "Telefon-") + mac.replace(":", "")[-4:],
                     "yetki": {k: bool(bt) for k in _G_IZINLER},
                     "ilk": int(_g_time.time())}
        _g_yaz(_d)
    return _g_yetki_coz(_tel[mac])

def _g_yetki_istek(req):  # FORD BT ROLE DUZELT
    """Istek sahibinin izinleri. BT koprusunden (localhost) gelen taninmayan
    telefon ESLESMIS/sahip-onayli sayilir -> engellenmez. WiFi'de misafir."""
    _mac = _g_mac(req)
    try:
        _ip = req.remote_addr or ""
    except Exception:
        _ip = ""
    _bt = _ip in ("127.0.0.1", "::1")
    if _bt and not _mac:
        _mac = "BT-ORTAK"
    return _g_yetki_oto(_mac, _bt)'''

KOMUT_ESKI = '            _yt = _g_yetki_oto(_g_mac(request))'
KOMUT_YENI = '            _yt = _g_yetki_istek(request)  # FORD BT ROLE DUZELT'

MUZIK_ESKI = '        if _g_sifre_var() and not _g_yetki_oto(_g_mac(request)).get("muzik", False):'
MUZIK_YENI = '        if _g_sifre_var() and not _g_yetki_istek(request).get("muzik", False):  # FORD BT ROLE DUZELT'


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
    global WEB
    if len(sys.argv) > 1: WEB = sys.argv[1]
    print("Bluetooth röle/komut düzeltmesi...")
    if not os.path.isfile(WEB):
        print("  ! ford_web.py yok"); sys.exit(1)
    src = open(WEB, encoding="utf-8").read()
    if "_g_yetki_oto" not in src:
        print("  ! Önce ford_yetki_ince_ekle.py uygulanmalı. DOKUNULMADI."); sys.exit(2)
    if ISARET in src:
        print("  = zaten ekli, atlandı."); sys.exit(0)
    for ad, eski in [("_g_yetki_oto", OTO_ESKI), ("/api/komut kapisi", KOMUT_ESKI),
                     ("/api/muzik kapisi", MUZIK_ESKI)]:
        if eski not in src:
            print(f"  ! '{ad}' çapası beklenen halde değil (btmac_muzik yaması tam mı?). DOKUNULMADI."); sys.exit(2)
    orj = src
    src = src.replace(OTO_ESKI, OTO_YENI, 1).replace(KOMUT_ESKI, KOMUT_YENI, 1).replace(MUZIK_ESKI, MUZIK_YENI, 1)
    yedek = WEB + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
    open(yedek, "w", encoding="utf-8").write(orj); open(WEB, "w", encoding="utf-8").write(src)
    try:
        py_compile.compile(WEB, doraise=True); _engelli_import(WEB)
    except Exception as e:
        open(WEB, "w", encoding="utf-8").write(orj)
        print("  ! test patladı, GERİ ALINDI ->", type(e).__name__, str(e)[:140]); sys.exit(3)
    print("  ✓ ford_web.py: BT'den gelen telefon artık engellenmez (eşleşmiş=onaylı).")
    print("TAMAM ✓  Şimdi:  sudo systemctl restart ford   (APK derlemeye GEREK YOK)")


if __name__ == "__main__":
    main()
