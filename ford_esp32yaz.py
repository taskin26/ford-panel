#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_esp32yaz.py  —  ESP32'yi PANELDEN derle ve yaz
====================================================
11 Ekim 2026

NEDEN VAR
    ESP32'nin yazilimini her degistirdigimizde karti kutudan sokup
    laptopa goturmek gerekiyordu. Bu modul derlemeyi ve yazmayi
    Pi'ye tasiyor - telefondaki panelden iki dugme.

NASIL CALISIR
    Pi'ye arduino-cli ve ESP32 cekirdegi BIR KEZ kurulur (~1.5 GB).
    Sonrasinda:  .ino dosyasini panelden yukle  ->  "ESP32'ye Yaz"

WIFI DUSMUYOR
    Ilk akla gelen cozum "ford servisini durdur, yaz, baslat"ti.
    Ama FORD agini o servis ayakta tutuyor - durdugu anda telefon
    baglantisi kopuyor ve ne olup bittigini goremiyorsun.
    Bunun yerine servis AYAKTA kaliyor, sadece ESP32'nin seri portu
    gecici olarak birakiliyor. Yazma bitince port geri aciliyor.
    Panel boylece butun islem boyunca ayakta kalip ilerlemeyi gosteriyor.

KURULUM INTERNET ISTER
    arduino-cli ve cekirdek indirilecek. Pi ev agina bagliyken yap.
    Araçta, kendi aginda calisirken kurulum YAPILAMAZ - ama yazma
    islemi internet istemez, o her yerde calisir.

GUVENLIK
    Yazmadan once ESP32'ye HEPSINI_KAPAT gidiyor (kapat() bunu
    zaten yapiyor), yani roleler birakilmis oluyor. Yazma sirasinda
    ESP32 resetlenir; acilista setup() tum roleleri pasife cekiyor.
"""

import os
import platform
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.request

KOK      = os.path.dirname(os.path.abspath(__file__))
ARD_KOK  = os.path.join(KOK, "arduino")
ACLI     = os.path.join(ARD_KOK, "arduino-cli")
VERI     = os.path.join(ARD_KOK, "veri")
INDIRME  = os.path.join(ARD_KOK, "indirme")
TASLAK   = os.path.join(ARD_KOK, "ford_esp32")     # .ino buraya kopyalanir
INO_ADI  = "ford_esp32.ino"
INO_KOK  = os.path.join(KOK, INO_ADI)              # panelden yuklenen dosya

FQBN     = "esp32:esp32:esp32"
ESP_INDEX = "https://espressif.github.io/arduino-esp32/package_esp32_index.json"
ACLI_SURUM = "1.1.1"

# arduino-cli surumleri - Pi'nin mimarisine gore secilir
ACLI_URL = {
    "aarch64": f"https://github.com/arduino/arduino-cli/releases/download/"
               f"v{ACLI_SURUM}/arduino-cli_{ACLI_SURUM}_Linux_ARM64.tar.gz",
    "armv7l":  f"https://github.com/arduino/arduino-cli/releases/download/"
               f"v{ACLI_SURUM}/arduino-cli_{ACLI_SURUM}_Linux_ARMv7.tar.gz",
    "armv6l":  f"https://github.com/arduino/arduino-cli/releases/download/"
               f"v{ACLI_SURUM}/arduino-cli_{ACLI_SURUM}_Linux_ARMv6.tar.gz",
    "x86_64":  f"https://github.com/arduino/arduino-cli/releases/download/"
               f"v{ACLI_SURUM}/arduino-cli_{ACLI_SURUM}_Linux_64bit.tar.gz",
}

SATIR_SINIR = 60          # ekranda kac satir tutulsun


# ====================================================================
#  DURUM  -  panel bunu saniyede bir okur
# ====================================================================
_D = {
    "asama":     "",        # kurulum / derleme / yazma / bitti
    "mesaj":     "",
    "satirlar":  [],
    "calisiyor": False,
    "basarili":  None,
    "baslangic": 0.0,
}
_KILIT = threading.Lock()


def _yaz(satir, asama=None, mesaj=None):
    with _KILIT:
        if asama is not None:
            _D["asama"] = asama
        if mesaj is not None:
            _D["mesaj"] = mesaj
        if satir:
            for s in str(satir).rstrip().splitlines():
                s = s.strip()
                if s:
                    _D["satirlar"].append(s[:200])
            del _D["satirlar"][:-SATIR_SINIR]
    if satir:
        print(f"[esp32yaz] {str(satir).strip()[:160]}")


def durum():
    with _KILIT:
        d = dict(_D)
        d["satirlar"] = list(_D["satirlar"])
    d["kurulu"] = kurulu_mu()
    d["ino_var"] = os.path.exists(INO_KOK)
    if d["baslangic"]:
        d["gecen"] = int(time.time() - d["baslangic"])
    else:
        d["gecen"] = 0
    return d


def _bitir(basarili, mesaj):
    with _KILIT:
        _D["calisiyor"] = False
        _D["basarili"] = bool(basarili)
        _D["asama"] = "bitti"
        _D["mesaj"] = mesaj
    print(f"[esp32yaz] BITTI  basarili={basarili}  {mesaj}")


def _basla(asama, mesaj):
    """Yeni bir is baslatir. Zaten calisiyorsa False doner."""
    with _KILIT:
        if _D["calisiyor"]:
            return False
        _D.update({"asama": asama, "mesaj": mesaj, "satirlar": [],
                   "calisiyor": True, "basarili": None,
                   "baslangic": time.time()})
    return True


# ====================================================================
#  YARDIMCILAR
# ====================================================================
def _platform_tam_mi():
    """ESP32 cekirdegi GERCEKTEN kurulmus mu?

    Sadece klasorun varligina bakmak yetmiyor: o klasor ilk dosya
    iner inmez olusuyordu ve kurulum daha surerken sistem "hazir"
    saniyordu. Platform tanimi ve en az bir derleyici araci aranir;
    ikisi de kurulumun EN SONUNDA yerine oturuyor.
    """
    import glob
    p = os.path.join(VERI, "packages", "esp32")
    if not os.path.isdir(p):
        return False
    if not glob.glob(os.path.join(p, "hardware", "esp32", "*", "platform.txt")):
        return False
    return bool(glob.glob(os.path.join(p, "tools", "*", "*", "bin")))


def kurulu_mu():
    """arduino-cli ve ESP32 cekirdegi hazir mi?

    Basarili kurulumdan sonra bir isaret dosyasi birakiliyor; sonraki
    sorgular ucuza o dosyaya bakiyor. Isaret yoksa (ornegin isaret
    eklenmeden once kurulmus bir sistem) derinlemesine bakilir ve
    tamsa isaret o anda yazilir.
    """
    if not os.path.exists(ACLI):
        return False
    if os.path.exists(ISARET):
        return True
    if _platform_tam_mi():
        try:
            with open(ISARET, "w", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M"))
        except Exception:
            pass
        return True
    return False


def _calistir(komut, zaman_asimi=3600, ortam=None):
    """Komutu calistirir, ciktisini satir satir panele yazar.

    Doner: (cikis_kodu, tum_cikti)
    """
    _yaz("$ " + " ".join(str(k) for k in komut))
    ort = dict(os.environ)
    ort["ARDUINO_DIRECTORIES_DATA"] = VERI
    ort["ARDUINO_DIRECTORIES_DOWNLOADS"] = INDIRME
    ort["ARDUINO_DIRECTORIES_USER"] = os.path.join(ARD_KOK, "kullanici")
    if ortam:
        ort.update(ortam)
    try:
        p = subprocess.Popen([str(k) for k in komut],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             text=True, bufsize=1, env=ort)
    except FileNotFoundError:
        _yaz("komut bulunamadi: " + str(komut[0]))
        return 127, ""
    tum = []
    t0 = time.time()
    try:
        for satir in p.stdout:
            tum.append(satir)
            # Indirme yuzdeleri cok satir uretiyor, sadece anlamlilari al
            s = satir.strip()
            if s and not s.startswith("Downloading") or len(tum) % 20 == 0:
                _yaz(s)
            if time.time() - t0 > zaman_asimi:
                p.kill()
                _yaz("zaman asimi")
                return 124, "".join(tum)
    except Exception as e:
        _yaz(f"okuma hatasi: {e}")
    p.wait()
    return p.returncode, "".join(tum)


# ====================================================================
#  KURULUM
# ====================================================================
def _indir(url, hedef):
    _yaz(f"indiriliyor: {url.rsplit('/', 1)[-1]}")
    try:
        with urllib.request.urlopen(url, timeout=120) as c, \
                open(hedef, "wb") as f:
            shutil.copyfileobj(c, f)
        mb = os.path.getsize(hedef) / 1048576.0
        _yaz(f"indi: {mb:.1f} MB")
        return True
    except Exception as e:
        _yaz(f"indirilemedi: {e}")
        return False


def _kur_is():
    try:
        os.makedirs(ARD_KOK, exist_ok=True)
        os.makedirs(VERI, exist_ok=True)

        mimari = platform.machine()
        url = ACLI_URL.get(mimari)
        if not url:
            _bitir(False, f"bilinmeyen mimari: {mimari}")
            return

        if not os.path.exists(ACLI):
            _yaz("", "kurulum", "arduino-cli indiriliyor")
            tgz = os.path.join(ARD_KOK, "acli.tgz")
            if not _indir(url, tgz):
                _bitir(False, "arduino-cli indirilemedi - internet var mi?")
                return
            _yaz("acilityor...")
            with tarfile.open(tgz) as t:
                for u in t.getmembers():
                    if os.path.basename(u.name) == "arduino-cli":
                        u.name = "arduino-cli"
                        t.extract(u, ARD_KOK)
                        break
            os.chmod(ACLI, 0o755)
            try:
                os.remove(tgz)
            except Exception:
                pass
            _yaz("arduino-cli kuruldu")

        _yaz("", "kurulum", "paket listesi aliniyor")
        k, _ = _calistir([ACLI, "core", "update-index",
                          "--additional-urls", ESP_INDEX], 600)
        if k != 0:
            _bitir(False, "paket listesi alinamadi - internet baglantisi yok")
            return

        _yaz("", "kurulum", "ESP32 cekirdegi kuruluyor (1-1.5 GB, uzun surer)")
        k, _ = _calistir([ACLI, "core", "install", "esp32:esp32",
                          "--additional-urls", ESP_INDEX], 3600)
        if k != 0:
            _bitir(False, "cekirdek kurulamadi - yer ya da baglanti sorunu")
            return

        if not kurulu_mu():
            _bitir(False, "kurulum tamamlanmis gorunmuyor")
            return
        _bitir(True, "Kurulum tamam. Artik ESP32'yi panelden yazabilirsin.")
    except Exception as e:
        _yaz(f"beklenmeyen hata: {e}")
        _bitir(False, str(e))


def kur_baslat():
    if not _basla("kurulum", "baslatiliyor"):
        return False, "zaten bir islem suruyor"
    threading.Thread(target=_kur_is, daemon=True).start()
    return True, "kurulum basladi"


# ====================================================================
#  DERLE VE YAZ
# ====================================================================
def _taslagi_hazirla():
    """arduino-cli .ino'nun kendi adinda bir klasorde olmasini ister."""
    os.makedirs(TASLAK, exist_ok=True)
    hedef = os.path.join(TASLAK, INO_ADI)
    shutil.copy2(INO_KOK, hedef)
    return TASLAK


def _yaz_is(port, port_kapat, port_ac):
    kapatildi = False
    try:
        if not kurulu_mu():
            _bitir(False, "once derleyiciyi kur")
            return
        if not os.path.exists(INO_KOK):
            _bitir(False, f"{INO_ADI} yuklu degil - once panelden yukle")
            return

        _yaz("", "derleme", "derleniyor (1-2 dakika surebilir)")
        taslak = _taslagi_hazirla()
        k, cikti = _calistir([ACLI, "compile", "--fqbn", FQBN, taslak], 1800)
        if k != 0:
            # Derleyici hatasinin son satirlari en aciklayici olani
            son = [s for s in cikti.strip().splitlines() if s.strip()][-6:]
            _yaz("---- derleme hatasi ----")
            for s in son:
                _yaz(s)
            _bitir(False, "DERLEME HATASI - yazilimda hata var, ESP32'ye dokunulmadi")
            return
        _yaz("derleme tamam")

        # ---- seri portu birak ----
        # Servis ayakta kaliyor, sadece port birakiliyor: WiFi dusmuyor.
        _yaz("", "yazma", "seri port birakiliyor")
        if port_kapat:
            try:
                port_kapat()
                kapatildi = True
                time.sleep(0.6)
            except Exception as e:
                _yaz(f"port kapatilamadi: {e}")

        k, _ = _calistir([ACLI, "upload", "-p", port, "--fqbn", FQBN, taslak], 600)
        if k != 0:
            _bitir(False, "YAZMA HATASI - ESP32 eski yazilimla calismaya devam ediyor")
            return
        _yaz("yazma tamam")
        _bitir(True, "ESP32 guncellendi.")
    except Exception as e:
        _yaz(f"beklenmeyen hata: {e}")
        _bitir(False, str(e))
    finally:
        # Ne olursa olsun portu geri ac - yoksa sistem ESP32'siz kalir
        if kapatildi and port_ac:
            time.sleep(1.5)
            for deneme in range(3):
                try:
                    if port_ac():
                        _yaz("seri port geri acildi")
                        break
                except Exception as e:
                    _yaz(f"port acilamadi ({deneme + 1}/3): {e}")
                time.sleep(2.0)
            else:
                _yaz("! Seri port acilamadi - sistemi yeniden baslat")


def yaz_baslat(port, port_kapat=None, port_ac=None):
    if not port:
        return False, "seri port bilinmiyor"
    if not _basla("derleme", "baslatiliyor"):
        return False, "zaten bir islem suruyor"
    threading.Thread(target=_yaz_is, args=(port, port_kapat, port_ac),
                     daemon=True).start()
    return True, "derleme basladi"


# ====================================================================
#  ELLE TEST
# ====================================================================
if __name__ == "__main__":
    import sys
    print("kurulu mu :", kurulu_mu())
    print("ino var mi:", os.path.exists(INO_KOK))
    print("mimari    :", platform.machine())
    if len(sys.argv) > 1 and sys.argv[1] == "kur":
        kur_baslat()
        while durum()["calisiyor"]:
            d = durum()
            print(f"  [{d['asama']}] {d['mesaj']}  ({d['gecen']} sn)")
            time.sleep(3)
        print(durum()["mesaj"])
