#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_btkomut.py  —  BLUETOOTH KOMUT KÖPRÜSÜ
=====================================================================
27 Ekim 2026

NE YAPAR
    Telefon/tablet (FORD Panel APK) --Bluetooth SPP--> buraya -->
    çalışan panelin kendi /api/komut ucuna (localhost:8080).
    Yani WiFi/internet OLMADAN, Bluetooth ile araç komutu.

    ford_web'e HİÇ dokunmaz. Mevcut sistemi aynen kullanır:
    gelen "KAPILARI_AC" -> POST {"komut":"KAPILARI_AC"} -> role + ses.

GÜVENLİK
    Komutu panel işliyor; panel zaten IZINLI_KOMUTLAR dışını reddeder.
    Bağlantı için telefon Pi ile ÖNCEDEN eşleştirilmiş olmalı.

KURULUM (bir kerelik)
    sudo apt-get install -y libbluetooth-dev bluez
    pip3 install pybluez2 --break-system-packages
    # Pi'yi eşleşmeye açık yap:
    bluetoothctl
       power on
       discoverable on
       pairable on
       agent on
       default-agent
       quit
    # Telefondan Pi ('ford') ile eşleştir.

ÇALIŞTIRMA
    python3 ford_btkomut.py
    # Otomatik başlasın istiyorsan en alttaki systemd notuna bak.
"""

import sys
import time
import json
import urllib.request

try:
    import bluetooth  # pybluez / pybluez2
except Exception as e:
    print("PyBluez bulunamadı. Kurmak için:")
    print("  sudo apt-get install -y libbluetooth-dev bluez")
    print("  pip3 install pybluez2 --break-system-packages")
    print("Ayrıntı:", e)
    sys.exit(1)

PANEL_UC = "http://127.0.0.1:8080/api/komut"
SPP_UUID = "00001101-0000-1000-8000-00805F9B34FB"


def komut_isle(komut):
    """Komutu çalışan panele POST eder, kısa cevap döner."""
    komut = (komut or "").strip().upper()
    if not komut:
        return "RET|bos"
    try:
        govde = json.dumps({"komut": komut}).encode("utf-8")
        istek = urllib.request.Request(
            PANEL_UC, data=govde,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(istek, timeout=8) as r:
            cevap = json.loads(r.read().decode("utf-8"))
        if cevap.get("ok"):
            return "OK|" + komut
        return "RET|" + komut + "|" + str(cevap.get("hata", "?"))
    except Exception as e:
        return "HATA|" + komut + "|" + str(e)[:60]


def istemci_isle(sock, adres):
    print("[bt] bağlandı:", adres)
    tampon = ""
    try:
        sock.send("FORD BT HAZIR\n")
    except Exception:
        pass
    try:
        while True:
            veri = sock.recv(1024)
            if not veri:
                break
            tampon += veri.decode("utf-8", "ignore")
            while "\n" in tampon:
                satir, tampon = tampon.split("\n", 1)
                satir = satir.strip()
                if not satir:
                    continue
                print("[bt] komut:", satir)
                cevap = komut_isle(satir)
                print("[bt]   ->", cevap)
                sock.send(cevap + "\n")
    except Exception as e:
        print("[bt] istemci koptu:", e)
    finally:
        try:
            sock.close()
        except Exception:
            pass
    print("[bt] bağlantı bitti:", adres)


def main():
    sunucu = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
    sunucu.bind(("", bluetooth.PORT_ANY))
    sunucu.listen(1)
    kanal = sunucu.getsockname()[1]
    try:
        bluetooth.advertise_service(
            sunucu, "FordKomut",
            service_id=SPP_UUID,
            service_classes=[SPP_UUID, bluetooth.SERIAL_PORT_CLASS],
            profiles=[bluetooth.SERIAL_PORT_PROFILE])
    except Exception as e:
        print("[bt] servis ilanı yapılamadı (yine de dinliyor):", e)

    print("=" * 52)
    print(f"  FORD Bluetooth komut köprüsü hazır (kanal {kanal}).")
    print("  Telefonu Pi ile eşleştir, APK'dan 'Bluetooth'a Bağlan'.")
    print("=" * 52)

    while True:
        try:
            istemci, adres = sunucu.accept()
            istemci_isle(istemci, adres)
        except KeyboardInterrupt:
            print("\n[bt] kapanıyor.")
            break
        except Exception as e:
            print("[bt] accept hatası:", e)
            time.sleep(1)

    try:
        sunucu.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()


# =====================================================================
# OTOMATİK BAŞLATMA (isteğe bağlı) — Pi açılınca kendi çalışsın
# =====================================================================
#   sudo nano /etc/systemd/system/ford-bt.service
#   ----------------------------------------------------------------
#   [Unit]
#   Description=FORD Bluetooth komut köprüsü
#   After=bluetooth.service ford.service
#   Wants=bluetooth.service
#
#   [Service]
#   ExecStart=/usr/bin/python3 /home/ford/ford_btkomut.py
#   WorkingDirectory=/home/ford
#   Restart=always
#   RestartSec=5
#   User=ford
#
#   [Install]
#   WantedBy=multi-user.target
#   ----------------------------------------------------------------
#   sudo systemctl enable --now ford-bt.service
#   sudo journalctl -u ford-bt -f      # izlemek için
