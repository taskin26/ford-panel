#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_yetki_ince_ekle.py  —  Telefonlara ISIM + HER IZIN AYRI (ince yetki)
=====================================================================
29 Ekim 2026  (ford_guvenlik_ekle.py SONRASI uygulanir)

NE YAPAR:
  - Her telefona duzenlenebilir ISIM ("Esim Esra").
  - Rol yerine HER IZIN AYRI: Kapi / Cam / Motor / Bagaj / Isik (ac-kapa).
  - Komut kapisi bu izinlere gore karar verir (sohbet+durum herkese acik).
  - Geriye donuk: eski 'rol'lu telefonlar ROL_IZIN'den izne cevrilir.

GUVENLI: yedek + derleme + guvenli import (ford_* engelli) + geri alma;
    JS tek fonksiyon araligi degisimi; idempotent.

KULLANIM (Pi'de):
    python3 ford_yetki_ince_ekle.py
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
ISARET = "FORD YETKI INCE"

# ---- modul seviyesi yardimcilar (def basla'dan once) ----
MOD = r'''# === FORD YETKI INCE (otomatik eklendi) ===
_G_IZINLER = ("kapi", "cam", "motor", "bagaj", "isik")

def _g_yetki_coz(bilgi):
    """Bir telefon kaydindan izin sozlugu uretir. Once 'yetki', yoksa 'rol'."""
    _y = bilgi.get("yetki")
    if isinstance(_y, dict):
        return {k: bool(_y.get(k)) for k in _G_IZINLER}
    _rol = bilgi.get("rol", "misafir")
    try:
        _izin = getattr(FZ, "ROL_IZIN", {}).get(_rol, set())
    except Exception:
        _izin = set()
    return {k: (k in _izin) for k in _G_IZINLER}

def _g_yetki_oto(mac):
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
    return _g_yetki_coz(_tel[mac])
# === /FORD YETKI INCE ===
'''

# ---- yeni uclar (return app'ten once, 4 girinti) ----
UC = r'''# === FORD YETKI INCE UC (otomatik eklendi) ===
@{APP}.route("/api/yonetici/telefonlar2", methods=["POST"])
def _g_tel2():
    _v = request.get_json(silent=True) or {}
    if not _g_sifre_dogru(_v.get("sifre") or ""):
        return jsonify({"ok": False, "hata": "sifre yanlis"}), 403
    _benim = _g_mac(request)
    if _benim:
        _g_yetki_oto(_benim)
    _yd = _g_oku()
    _l = []
    for _mac, _b in _yd.get("telefonlar", {}).items():
        _l.append({"mac": _mac, "ad": _b.get("ad", _mac), "yetki": _g_yetki_coz(_b)})
    return jsonify({"ok": True, "telefonlar": _l, "benim_mac": _benim, "izinler": list(_G_IZINLER)})

@{APP}.route("/api/yonetici/ad", methods=["POST"])
def _g_ad():
    _v = request.get_json(silent=True) or {}
    if not _g_sifre_dogru(_v.get("sifre") or ""):
        return jsonify({"ok": False, "hata": "sifre yanlis"}), 403
    _mac = (_v.get("mac") or "").upper()
    _ad = (_v.get("ad") or "").strip()[:40]
    _yd = _g_oku()
    if _mac in _yd["telefonlar"] and _ad:
        _yd["telefonlar"][_mac]["ad"] = _ad
        _g_yaz(_yd)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "hata": "telefon yok ya da bos isim"})

@{APP}.route("/api/yonetici/yetki", methods=["POST"])
def _g_yetki_ayar():
    _v = request.get_json(silent=True) or {}
    if not _g_sifre_dogru(_v.get("sifre") or ""):
        return jsonify({"ok": False, "hata": "sifre yanlis"}), 403
    _mac = (_v.get("mac") or "").upper()
    _grup = (_v.get("grup") or "").strip()
    _deger = bool(_v.get("deger"))
    if _grup not in _G_IZINLER:
        return jsonify({"ok": False, "hata": "gecersiz izin"})
    _yd = _g_oku()
    if _mac in _yd["telefonlar"]:
        _b = _yd["telefonlar"][_mac]
        _yeni = _g_yetki_coz(_b)   # mevcut (rol'den turetilmis olabilir)
        _yeni[_grup] = _deger
        _b["yetki"] = _yeni        # artik acik izin sozlugu
        _b.pop("rol", None)        # role bagimliligi birak
        _g_yaz(_yd)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "hata": "telefon yok"})
# === /FORD YETKI INCE UC ==='''

# ---- /api/komut kapisi: rol -> ince izin ----
KOMUT_ESKI = '''        # GUVENLIK KAPISI: sifre kurulduysa rol kontrolu yap (opt-in).
        if _g_sifre_var():
            _rol = _g_rol_oto(_g_mac(request))
            _grup = getattr(FZ, "KOMUT_GRUP", {}).get(_kmt, "sohbet")
            if _grup not in ("sohbet", "durum") and not _g_izin(_rol, _kmt):
                return jsonify({"ok": False, "yetkisiz": True,
                                "hata": "Bu telefon '" + (_rol or "misafir") + "' - fiziksel komut yetkisi yok"})'''
KOMUT_YENI = '''        # GUVENLIK KAPISI: sifre kurulduysa INCE IZIN kontrolu (opt-in).
        if _g_sifre_var():
            _yt = _g_yetki_oto(_g_mac(request))
            _grup = getattr(FZ, "KOMUT_GRUP", {}).get(_kmt, "sohbet")
            if _grup not in ("sohbet", "durum") and not _yt.get(_grup, False):
                return jsonify({"ok": False, "yetkisiz": True,
                                "hata": "Bu telefonun '" + _grup + "' yetkisi yok"})'''

# ---- JS: ynListele'yi (ynRol'e kadar) isim+izin halvine cevir ----
JS_YENI = r'''function ynListele(){
  if(!window._ynCss){window._ynCss=1;var _st=document.createElement('style');_st.textContent='.yn-tel{border-bottom:1px solid rgba(255,255,255,.08);padding:8px 0 12px;margin-bottom:8px}.yn-izin{display:flex;flex-wrap:wrap;gap:6px;padding:8px 2px 2px}.yn-cip{font-size:12.5px;padding:8px 13px;border-radius:999px;border:1px solid #2c4f74;color:#9fc0e4;cursor:pointer;user-select:none}.yn-cip.on{background:#2e7d32;border-color:#43a047;color:#fff}';document.head.appendChild(_st);}
  _ynPost('/api/yonetici/telefonlar2',{sifre:_ynSifre}).then(function(d){
    if(!d.ok){_ynSifre=null;ynYenile();return;}
    var IZ=[['kapi','Kapı'],['cam','Cam'],['motor','Motor'],['bagaj','Bagaj'],['isik','Işık']];
    var kutu=document.getElementById('yn-kutu'); kutu.innerHTML='';
    (d.telefonlar||[]).forEach(function(t){
      var tel=document.createElement('div'); tel.className='yn-tel';
      var row=document.createElement('div'); row.className='s-row';
      row.innerHTML='<div class="sr-l"><div><div class="sr-lbl">'+_ynK(t.ad)+((t.mac===d.benim_mac)?' 📱':'')+'</div><div class="sr-desc">'+_ynK(t.mac)+'</div></div></div>';
      var bAd=document.createElement('button'); bAd.className='s-btn'; bAd.textContent='✏️ İsim'; bAd.onclick=function(){ynAd(t.mac,t.ad);};
      var bSil=document.createElement('button'); bSil.className='s-btn s-btn-d'; bSil.textContent='Sil'; bSil.onclick=function(){ynSil(t.mac);};
      row.appendChild(bAd); row.appendChild(bSil); tel.appendChild(row);
      var iz=document.createElement('div'); iz.className='yn-izin';
      IZ.forEach(function(p){
        var cip=document.createElement('span'); cip.className='yn-cip'+((t.yetki&&t.yetki[p[0]])?' on':''); cip.textContent=p[1];
        cip.onclick=function(){ynYetki(t.mac,p[0],cip);};
        iz.appendChild(cip);
      });
      tel.appendChild(iz); kutu.appendChild(tel);
    });
    if(!(d.telefonlar||[]).length){var e=document.createElement('div');e.className='gc-aciklama';e.textContent='Henüz telefon yok. Bir telefon komut verince burada belirir.';kutu.appendChild(e);}
    var sd=document.createElement('div'); sd.innerHTML='<div class="s-title" style="margin-top:14px">Şifre Değiştir</div><div class="s-row" style="flex-wrap:wrap;gap:8px"><input id="yn-e" type="password" class="s-inp" placeholder="Eski şifre"><input id="yn-n1" type="password" class="s-inp" placeholder="Yeni şifre"><input id="yn-n2" type="password" class="s-inp" placeholder="Yeni (tekrar)"><button class="s-btn" id="yn-bd">Değiştir</button><button class="s-btn" id="yn-bc">Çıkış</button></div>';
    kutu.appendChild(sd);
    document.getElementById('yn-bd').onclick=ynDegis;
    document.getElementById('yn-bc').onclick=function(){_ynSifre=null;ynYenile();};
  }).catch(function(){});
}
function ynAd(mac,eski){ var ad=prompt('İsim:',eski||''); if(ad===null)return; _ynPost('/api/yonetici/ad',{sifre:_ynSifre,mac:mac,ad:ad}).then(function(d){ if(d.ok)ynListele(); else alert(d.hata||'olmadı'); }); }
function ynYetki(mac,grup,el){ _ynPost('/api/yonetici/yetki',{sifre:_ynSifre,mac:mac,grup:grup,deger:!el.classList.contains('on')}).then(function(d){ if(d.ok){el.classList.toggle('on');} else alert(d.hata||'olmadı'); }); }
'''


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


def _appvar(src):
    m = re.search(r'(?m)^(\s*)([A-Za-z_]\w*)\s*=\s*Flask\s*\(', src)
    return m.group(2) if m else "app"


def main():
    global WEB, HTML
    if len(sys.argv) > 1: WEB = sys.argv[1]
    if len(sys.argv) > 2: HTML = sys.argv[2]
    print("İnce yetki (isim + her izin ayrı) ekleniyor...")

    # ---- ford_web ----
    if not os.path.isfile(WEB):
        print("  ! ford_web.py yok"); sys.exit(1)
    src = open(WEB, encoding="utf-8").read()
    if "_g_sifre_var" not in src:
        print("  ! Önce ford_guvenlik_ekle.py uygulanmalı. DOKUNULMADI."); sys.exit(2)
    if ISARET in src:
        print("  = ford_web.py: zaten ekli.")
    else:
        if "\ndef basla(" not in src or "\n    return app\n" not in src or KOMUT_ESKI not in src:
            print("  ! ford_web.py beklenen halde değil (guvenlik yaması tam mı?). DOKUNULMADI."); sys.exit(2)
        orj = src
        src = src.replace("\ndef basla(", "\n\n" + MOD + "\ndef basla(", 1)
        app = _appvar(src)
        uc = "\n".join(("    " + s) if s.strip() else s for s in UC.replace("{APP}", app).split("\n"))
        src = src.replace("\n    return app\n", "\n" + uc + "\n    return app\n", 1)
        src = src.replace(KOMUT_ESKI, KOMUT_YENI, 1)
        yedek = WEB + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
        open(yedek, "w", encoding="utf-8").write(orj); open(WEB, "w", encoding="utf-8").write(src)
        try:
            py_compile.compile(WEB, doraise=True); _engelli_import(WEB)
        except Exception as e:
            open(WEB, "w", encoding="utf-8").write(orj)
            print("  ! ford_web.py test patladı, GERİ ALINDI ->", type(e).__name__, str(e)[:140]); sys.exit(3)
        print("  ✓ ford_web.py: isim + ince izin uçları + kapı izne göre.")

    # ---- ford_ekran ----
    if not os.path.isfile(HTML):
        print("  ! ford_ekran.html yok"); sys.exit(1)
    h = open(HTML, encoding="utf-8").read()
    if "function ynYetki(mac,grup,el)" in h:
        print("  = ford_ekran.html: zaten ekli.")
    elif "function ynListele(){" not in h or "function ynRol(mac,rol){" not in h:
        print("  ! ford_ekran.html: ynListele/ynRol bulunamadı (guvenlik JS yok?). DOKUNULMADI.")
    else:
        yeni = re.sub(r'function ynListele\(\)\{.*?(?=function ynRol\(mac,rol\)\{)',
                      JS_YENI, h, count=1, flags=re.DOTALL)
        if yeni == h:
            print("  ! ford_ekran.html: ynListele değişmedi (anchor sorunu). DOKUNULMADI.")
        else:
            yb = HTML + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
            open(yb, "w", encoding="utf-8").write(h); open(HTML, "w", encoding="utf-8").write(yeni)
            print("  ✓ ford_ekran.html: liste isim + izin toggle'lı.")

    print("TAMAM ✓  Şimdi:  sudo systemctl restart ford")


if __name__ == "__main__":
    main()
