#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_btkomut.py  —  BLUETOOTH KÖPRÜSÜ (BlueZ D-Bus / pybluez YOK)
=====================================================================
28 Kasım 2026  —  GENEL KÖPRÜ sürümü

NE YAPAR
    Telefon/tablet (FORD Panel APK) --Bluetooth SPP--> buraya -->
    çalışan panelin KENDİ API uçlarına (localhost:8080).

    ARTIK SADECE KOMUT DEĞİL: paneldeki HER /api çağrısını taşır.
    Yani WiFi/internet OLMADAN Bluetooth ile:
       - araç komutları  (POST /api/komut)
       - durum okuma     (GET  /api/durum)
       - MÜZİK           (GET/POST /api/muzik, /api/muzik/...)
       - medya, ayarlar  (diğer tüm /api/* uçları)
    Müziğin SESİ Pi'den / araç hoparlöründen çıkar; buradan yalnızca
    KONTROL (oynat/duraklat/sıradaki, liste, yükle, sil) gider.

PROTOKOL  (APK <-> Pi)
    APK  ->  "REQ|<method>|<base64(yol)>|<base64(govde)>\\n"
    Pi   ->  "RES|<status>|<base64(yanit_govdesi)>\\n"
    (Geriye dönük: düz "KAPILARI_AC\\n" gelirse POST /api/komut yapılır.)

GEREKLİ (zaten kurulu): BlueZ 5.x + python3-dbus + python3-gi
    sudo apt-get install -y python3-dbus python3-gi

ÇALIŞTIRMA (systemd ile, User=root):
    sudo systemctl restart ford-btkomut
    sudo journalctl -u ford-btkomut -f
"""

import os
import sys
import json
import base64
import socket
import threading
import urllib.request
import urllib.error

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

PANEL = "http://127.0.0.1:8080"
SPP_UUID = "00001101-0000-1000-8000-00805f9b34fb"
PROFILE_PATH = "/org/ford/spp"
KANAL = 22  # APK yansıma denemeleri 1/22/3 ile uyumlu


def log(*a):
    print("[btkomut]", *a, flush=True)


# --------------------------------------------------------------------
#  Paneldeki HTTP ucuna isteği yönlendir
# --------------------------------------------------------------------
def http_istek(method, yol, govde):
    """Panelin localhost ucuna method+body ile gider. (status, metin) döner."""
    try:
        url = PANEL + yol
        data = govde.encode("utf-8") if govde else None
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.getcode(), r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode("utf-8", "ignore")
        except Exception:
            return e.code, "{}"
    except Exception as e:
        log("http hata:", yol, "->", str(e)[:80])
        return 0, json.dumps({"ok": False, "hata": str(e)[:80]})


def satir_isle(satir):
    """Gelen bir satırı işler, geri gönderilecek yanıtı döner (yoksa None)."""
    satir = (satir or "").strip()
    if not satir:
        return None

    if satir.startswith("REQ|"):
        # REQ|<method>|<b64yol>|<b64govde>
        parca = satir.split("|", 3)
        if len(parca) < 4:
            return "RES|400|" + base64.b64encode(b"{}").decode("ascii")
        method = (parca[1].strip().upper() or "GET")
        try:
            yol = base64.b64decode(parca[2]).decode("utf-8", "ignore")
        except Exception:
            yol = ""
        try:
            govde = base64.b64decode(parca[3]).decode("utf-8", "ignore")
        except Exception:
            govde = ""
        if not yol.startswith("/"):
            yol = "/" + yol
        status, yanit = http_istek(method, yol, govde)
        log(method, yol, "->", status, "(%dB)" % len(yanit))
        return "RES|" + str(status) + "|" + \
               base64.b64encode(yanit.encode("utf-8")).decode("ascii")

    # Geriye dönük uyumluluk: düz komut
    status, yanit = http_istek("POST", "/api/komut",
                               json.dumps({"komut": satir.upper()}))
    try:
        c = json.loads(yanit)
        if c.get("ok"):
            return "OK|" + satir.upper()
        return "RET|" + satir.upper() + "|" + str(c.get("hata", "?"))
    except Exception:
        return "RET|" + satir.upper()


# --------------------------------------------------------------------
#  Bir BT istemcisiyle konuşma döngüsü
# --------------------------------------------------------------------
def istemci_dongu(sock):
    try:
        sock.setblocking(True)
    except Exception:
        pass
    log("istemci baglandi")
    tampon = ""
    try:
        try:
            sock.sendall(b"FORD BT HAZIR\n")
        except Exception:
            pass
        while True:
            veri = sock.recv(4096)
            if not veri:
                break
            tampon += veri.decode("utf-8", "ignore")
            while "\n" in tampon:
                satir, tampon = tampon.split("\n", 1)
                yanit = satir_isle(satir)
                if yanit:
                    try:
                        sock.sendall((yanit + "\n").encode("utf-8"))
                    except Exception as e:
                        log("gonderilemedi:", e)
                        return
    except Exception as e:
        log("istemci koptu:", e)
    finally:
        try:
            sock.close()
        except Exception:
            pass
        log("istemci bitti")


# --------------------------------------------------------------------
#  BlueZ Profile1 (SPP sunucusu)
# --------------------------------------------------------------------
class Profil(dbus.service.Object):

    @dbus.service.method("org.bluez.Profile1", in_signature="", out_signature="")
    def Release(self):
        log("Release")

    @dbus.service.method("org.bluez.Profile1", in_signature="oha{sv}", out_signature="")
    def NewConnection(self, cihaz, fd, ozellikler):
        try:
            tfd = fd.take()
        except Exception:
            tfd = int(fd)
        sock = socket.fromfd(tfd, socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            os.close(tfd)   # fromfd dup'ladı; orijinali kapat
        except Exception:
            pass
        log("NewConnection:", str(cihaz))
        threading.Thread(target=istemci_dongu, args=(sock,), daemon=True).start()

    @dbus.service.method("org.bluez.Profile1", in_signature="o", out_signature="")
    def RequestDisconnection(self, cihaz):
        log("RequestDisconnection:", str(cihaz))


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    yonetici = dbus.Interface(
        bus.get_object("org.bluez", "/org/bluez"),
        "org.bluez.ProfileManager1")

    Profil(bus, PROFILE_PATH)

    secenekler = {
        "Name": "FordKomut",
        "Role": "server",
        "Channel": dbus.UInt16(KANAL),
        "RequireAuthentication": dbus.Boolean(False),
        "RequireAuthorization": dbus.Boolean(False),
    }
    yonetici.RegisterProfile(PROFILE_PATH, SPP_UUID, secenekler)
    log("SPP profili kaydedildi (kanal %d). Panel: %s  Hazir." % (KANAL, PANEL))

    try:
        GLib.MainLoop().run()
    except KeyboardInterrupt:
        log("kapaniyor.")


if __name__ == "__main__":
    main()
