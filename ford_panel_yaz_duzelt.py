#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_panel_yaz_duzelt.py  —  Panelden ESP32 yazmayı GÜVENİLİR yapar
=====================================================================
29 Ekim 2026

SORUN:
    Panelden "ESP32'ye Yaz" sırasında, tarayıcı saniyede bir GIRIS
    sorduğu için (kapı/müşür durumu) seri porta giriyor; esptool stub
    yüklerken "serial noise or corruption" çıkıyordu. SSH'tan ford
    tamamen durdurulunca o sorgu da durduğundan sorunsuz yazıyor.

NE YAPAR:
  1) ford_web.py: _ESP_YAZILIYOR bayrağı. Flash sırasında _girisleri_oku
     porta HİÇ dokunmaz (önbellek döner). /api/esp32yaz/yaz bu bayrağı
     yazmadan ÖNCE kaldırır, suren GIRIS bitsin diye bekler, portu bırakır;
     bitince indirir.
  2) ford_esp32yaz.py: yükleme baud'u 115200 (yavaş=güvenli) + port
     bırakma beklemesi 0.6 -> 2.0 sn.

GÜVENLİ: yedek + py_compile + güvenli import (ford_* engelli) + hata olursa
    GERİ ALMA; idempotent.

KULLANIM (Pi'de):
    python3 ford_panel_yaz_duzelt.py
    echo '<sudo_sifren>' | sudo -S systemctl restart ford
"""

import os
import sys
import time
import py_compile
import importlib.util

WEB = "/home/ford/ford_web.py"
ISARET = "FORD PANEL YAZ DUZELT"

# flasher yolu otomatik bulunur (KART D değil, _fabrika vs. olabilir)
def _flasher_bul():
    import glob
    for k in ("/home/ford", "/home/ford/_fabrika", os.path.dirname(WEB)):
        g = glob.glob(os.path.join(k, "**", "ford_esp32yaz.py"), recursive=True)
        if g:
            return g[0]
    return None

# ---- ford_web parçaları ----
W_FLAG_ESKI = '_GIRIS_KILIT = threading.Lock()     # ayni anda tek GIRIS sorgusu'
W_FLAG_YENI = ('_GIRIS_KILIT = threading.Lock()     # ayni anda tek GIRIS sorgusu\n'
               '_ESP_YAZILIYOR = [False]   # FORD PANEL YAZ DUZELT: flash sirasinda GIRIS durur')

W_GUARD_ESKI = '''    with _GIRIS_KILIT:
        simdi = time.time()'''
W_GUARD_YENI = '''    with _GIRIS_KILIT:
        if _ESP_YAZILIYOR[0]:          # FORD PANEL YAZ DUZELT
            return _GIRIS_ONBELLEK["veri"]
        simdi = time.time()'''

W_UC_ESKI = '''        def _kapat():
            # Servis ayakta kaliyor, SADECE port birakiliyor.
            # kapat() once HEPSINI_KAPAT yolluyor - roleler birakilmis olur.
            esp.kapat()

        def _ac():
            return esp.bagla(port)'''
W_UC_YENI = '''        def _kapat():
            # FORD PANEL YAZ DUZELT: once GIRIS pollerini durdur, suren GIRIS
            # bitsin, sonra portu birak. Boylece flash sirasinda tarayici
            # seri porta hic dokunmaz (serial noise biter).
            _ESP_YAZILIYOR[0] = True
            time.sleep(1.5)
            esp.kapat()
            time.sleep(0.5)

        def _ac():
            try:
                return esp.bagla(port)
            finally:
                _ESP_YAZILIYOR[0] = False'''

# ---- flasher parçaları ----
Y_SLEEP_ESKI = '                time.sleep(0.6)'
Y_SLEEP_YENI = '                time.sleep(2.0)   # FORD PANEL YAZ DUZELT'
Y_BAUD_ESKI = '[ACLI, "upload", "-p", port, "--fqbn", FQBN, taslak]'
Y_BAUD_YENI = '[ACLI, "upload", "-p", port, "--fqbn", FQBN + ":UploadSpeed=115200", taslak]'


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
    print("Panelden ESP32 yazma düzeltmesi...")

    # ---- ford_web ----
    if not os.path.isfile(WEB):
        print("  ! ford_web.py yok:", WEB); sys.exit(1)
    src = open(WEB, encoding="utf-8").read()
    if ISARET in src:
        print("  = ford_web.py: zaten ekli.")
    else:
        for ad, eski in [("GIRIS kilidi", W_FLAG_ESKI), ("GIRIS okuma", W_GUARD_ESKI), ("yaz ucu", W_UC_ESKI)]:
            if eski not in src:
                print(f"  ! ford_web.py: '{ad}' çapası bulunamadı. DOKUNULMADI."); sys.exit(2)
        orj = src
        src = src.replace(W_FLAG_ESKI, W_FLAG_YENI, 1)
        src = src.replace(W_GUARD_ESKI, W_GUARD_YENI, 1)
        src = src.replace(W_UC_ESKI, W_UC_YENI, 1)
        yedek = WEB + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
        open(yedek, "w", encoding="utf-8").write(orj); open(WEB, "w", encoding="utf-8").write(src)
        try:
            py_compile.compile(WEB, doraise=True); _engelli_import(WEB)
        except Exception as e:
            open(WEB, "w", encoding="utf-8").write(orj)
            print("  ! ford_web.py testi patladı, GERİ ALINDI ->", type(e).__name__, str(e)[:140]); sys.exit(3)
        print("  ✓ ford_web.py: flash sırasında GIRIS durdurulur (çakışma biter).")

    # ---- flasher ----
    YAZ = _flasher_bul()
    if not YAZ:
        print("  ! ford_esp32yaz.py bulunamadı (flasher baud düşürülemedi, ama ford_web yeter).");
    else:
        ys = open(YAZ, encoding="utf-8").read()
        if "UploadSpeed=115200" in ys and "sleep(2.0)   # FORD PANEL YAZ DUZELT" in ys:
            print("  = flasher: zaten ekli.")
        else:
            orj = ys
            if Y_SLEEP_ESKI in ys: ys = ys.replace(Y_SLEEP_ESKI, Y_SLEEP_YENI, 1)
            if Y_BAUD_ESKI in ys:  ys = ys.replace(Y_BAUD_ESKI, Y_BAUD_YENI, 1)
            if ys != orj:
                yb = YAZ + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
                open(yb, "w", encoding="utf-8").write(orj); open(YAZ, "w", encoding="utf-8").write(ys)
                try:
                    py_compile.compile(YAZ, doraise=True)
                    print("  ✓ flasher:", os.path.basename(YAZ), "-> baud 115200 + bekleme 2sn.")
                except Exception as e:
                    open(YAZ, "w", encoding="utf-8").write(orj)
                    print("  ! flasher testi patladı, GERİ ALINDI ->", str(e)[:120])
            else:
                print("  ! flasher çapaları bulunamadı, dokunulmadı (ford_web yeter).")

    print("TAMAM ✓  Şimdi:  echo '<sifre>' | sudo -S systemctl restart ford")


if __name__ == "__main__":
    main()
