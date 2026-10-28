#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_guvenlik_ekle.py  —  Telefon ROLLERI + SIFRELI YONETICI + komut kapisi
=====================================================================
29 Ekim 2026

ACIK (kapatiliyor):
    Paneli acan herkes "Bu Telefonu Tanit"la tam erisim aliyordu.

NE EKLER:
  1) ford_web.py (modul): telefon-rol defteri (yonetici.json) + sifre
     (hash'li) yardimcilari.  FZ.rol_izin_var_mi / ROL_IZIN / KOMUT_GRUP
     zaten var; onu kullanir.
  2) /api/komut KAPISI: istegi atan telefonun MAC'inden rolu bulunur
     (kayitta yoksa 'misafir' eklenir). sohbet+durum herkese acik;
     kapi/cam/bagaj/isik/motor icin rol YETMIYORSA reddedilir.
     GUVENLIK OPT-IN: sifre KURULANA KADAR kapi KAPALI (eski davranis),
     boylece kurulumdan once sistem kitlenmez.
  3) Yonetici uclari (sifreli): durum, sifre_kur, sifre_degistir, giris,
     telefonlar (liste), rol (ata), sil.
  4) Panel > Guvenlik sekmesine "Kullanici Yonetimi" arayuzu:
       - sifre yoksa: BELIRLE (iki kez)
       - sifre varsa: GIRIS
       - giriste: telefon listesi + rol secimi + Sil + Sifre Degistir
         (eski + yeni x2)

GUVENLI: her dosya yedeklenir; ford_web eklenince derlenir + guvenli
     import edilir (ford_* engelli), hata olursa GERI ALINIR; HTML saf
     metin-ekleme. Idempotent.

KULLANIM (Pi'de):
    python3 ford_guvenlik_ekle.py
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
WEB_ISARET = "FORD GUVENLIK"
HTML_ISARET = "FORD GUVENLIK JS"

# ---- ford_web: modul seviyesi yardimcilar (def basla'dan ONCE) ----
WEB_HELP = r'''# === FORD GUVENLIK (otomatik eklendi) ===
import os as _g_os, json as _g_json, hashlib as _g_hash, time as _g_time, binascii as _g_bin

def _g_yol():
    return _g_os.path.join(_g_os.path.dirname(_g_os.path.abspath(__file__)), "yonetici.json")

def _g_oku():
    try:
        with open(_g_yol(), encoding="utf-8") as _f:
            _d = _g_json.load(_f)
        if not isinstance(_d, dict):
            _d = {}
    except Exception:
        _d = {}
    _d.setdefault("telefonlar", {})
    return _d

def _g_yaz(_d):
    try:
        with open(_g_yol(), "w", encoding="utf-8") as _f:
            _g_json.dump(_d, _f, ensure_ascii=False)
        return True
    except Exception:
        return False

def _g_hashle(sifre, salt):
    return _g_hash.sha256((salt + "|" + (sifre or "")).encode("utf-8")).hexdigest()

def _g_sifre_var():
    return bool(_g_oku().get("hash"))

def _g_sifre_dogru(sifre):
    _d = _g_oku()
    if not _d.get("hash"):
        return False
    return _g_hashle(sifre or "", _d.get("salt", "")) == _d.get("hash")

def _g_sifre_kur(sifre):
    _d = _g_oku()
    if _d.get("hash"):
        return False
    if not sifre or len(sifre) < 4:
        return False
    _salt = _g_bin.hexlify(_g_os.urandom(8)).decode("ascii")
    _d["salt"] = _salt
    _d["hash"] = _g_hashle(sifre, _salt)
    return _g_yaz(_d)

def _g_sifre_degistir(eski, yeni):
    if not _g_sifre_dogru(eski):
        return False, "eski sifre yanlis"
    if not yeni or len(yeni) < 4:
        return False, "yeni sifre en az 4 karakter"
    _d = _g_oku()
    _salt = _g_bin.hexlify(_g_os.urandom(8)).decode("ascii")
    _d["salt"] = _salt
    _d["hash"] = _g_hashle(yeni, _salt)
    return _g_yaz(_d), "degistirildi"

def _g_mac(req):
    try:
        _ip = req.remote_addr or ""
        if YK is not None and _ip:
            return (YK.ip_den_mac(_ip) or "").upper()
    except Exception:
        pass
    return ""

def _g_rol_oto(mac):
    if not mac:
        return "misafir"
    _d = _g_oku()
    _tel = _d["telefonlar"]
    if mac not in _tel:
        _tel[mac] = {"ad": "Telefon-" + mac.replace(":", "")[-4:],
                     "rol": "misafir", "ilk": int(_g_time.time())}
        _g_yaz(_d)
    return _tel[mac].get("rol", "misafir")

def _g_izin(rol, komut):
    try:
        if hasattr(FZ, "rol_izin_var_mi"):
            return bool(FZ.rol_izin_var_mi(rol, komut))
    except Exception:
        pass
    _grup = getattr(FZ, "KOMUT_GRUP", {}).get(komut, "sohbet")
    return _grup in getattr(FZ, "ROL_IZIN", {}).get(rol or "misafir", set())
# === /FORD GUVENLIK ===
'''

# ---- ford_web: yonetici uclari (return app'ten ONCE, fonksiyon girintisi) ----
WEB_UC = r'''# === FORD GUVENLIK UC (otomatik eklendi) ===
@{APP}.route("/api/yonetici/durum")
def _g_durum():
    return jsonify({"sifre_var": _g_sifre_var()})

@{APP}.route("/api/yonetici/sifre_kur", methods=["POST"])
def _g_kur():
    _v = request.get_json(silent=True) or {}
    if _g_sifre_var():
        return jsonify({"ok": False, "hata": "sifre zaten var"})
    _ok = _g_sifre_kur((_v.get("sifre") or "").strip())
    return jsonify({"ok": bool(_ok), "hata": "" if _ok else "sifre en az 4 karakter"})

@{APP}.route("/api/yonetici/sifre_degistir", methods=["POST"])
def _g_degis():
    _v = request.get_json(silent=True) or {}
    _ok, _m = _g_sifre_degistir(_v.get("eski") or "", (_v.get("yeni") or "").strip())
    return jsonify({"ok": bool(_ok), "hata": "" if _ok else _m})

@{APP}.route("/api/yonetici/giris", methods=["POST"])
def _g_giris():
    _v = request.get_json(silent=True) or {}
    return jsonify({"ok": _g_sifre_dogru(_v.get("sifre") or "")})

@{APP}.route("/api/yonetici/telefonlar", methods=["POST"])
def _g_tel_liste():
    _v = request.get_json(silent=True) or {}
    if not _g_sifre_dogru(_v.get("sifre") or ""):
        return jsonify({"ok": False, "hata": "sifre yanlis"}), 403
    _benim = _g_mac(request)
    if _benim:
        _g_rol_oto(_benim)   # kendi telefonun listede gorunsun (sahip yapabilesin)
    _yd = _g_oku()
    _l = []
    for _mac, _b in _yd.get("telefonlar", {}).items():
        _l.append({"mac": _mac, "ad": _b.get("ad", _mac), "rol": _b.get("rol", "misafir")})
    return jsonify({"ok": True, "telefonlar": _l, "benim_mac": _benim,
                    "roller": list(getattr(FZ, "ROLLER", ("sahip", "tam", "sinirli", "misafir")))})

@{APP}.route("/api/yonetici/rol", methods=["POST"])
def _g_rol_ayar():
    _v = request.get_json(silent=True) or {}
    if not _g_sifre_dogru(_v.get("sifre") or ""):
        return jsonify({"ok": False, "hata": "sifre yanlis"}), 403
    _mac = (_v.get("mac") or "").upper()
    _rol = (_v.get("rol") or "").strip()
    if _rol not in getattr(FZ, "ROLLER", ("sahip", "tam", "sinirli", "misafir")):
        return jsonify({"ok": False, "hata": "gecersiz rol"})
    _yd = _g_oku()
    if _mac in _yd["telefonlar"]:
        _yd["telefonlar"][_mac]["rol"] = _rol
        _g_yaz(_yd)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "hata": "telefon yok"})

@{APP}.route("/api/yonetici/sil", methods=["POST"])
def _g_tel_sil():
    _v = request.get_json(silent=True) or {}
    if not _g_sifre_dogru(_v.get("sifre") or ""):
        return jsonify({"ok": False, "hata": "sifre yanlis"}), 403
    _mac = (_v.get("mac") or "").upper()
    _yd = _g_oku()
    if _mac in _yd["telefonlar"]:
        del _yd["telefonlar"][_mac]
        _g_yaz(_yd)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "hata": "telefon yok"})
# === /FORD GUVENLIK UC ==='''

# ---- ford_web: /api/komut KAPISI (eski blogu degistir) ----
KOMUT_ESKI = '''    @app.route("/api/komut", methods=["POST"])
    def _komut():
        veri = request.get_json(silent=True) or {}
        return jsonify(komut_calistir(veri.get("komut", "")))'''

KOMUT_YENI = '''    @app.route("/api/komut", methods=["POST"])
    def _komut():
        veri = request.get_json(silent=True) or {}
        _kmt = veri.get("komut", "")
        # GUVENLIK KAPISI: sifre kurulduysa rol kontrolu yap (opt-in).
        if _g_sifre_var():
            _rol = _g_rol_oto(_g_mac(request))
            _grup = getattr(FZ, "KOMUT_GRUP", {}).get(_kmt, "sohbet")
            if _grup not in ("sohbet", "durum") and not _g_izin(_rol, _kmt):
                return jsonify({"ok": False, "yetkisiz": True,
                                "hata": "Bu telefon '" + (_rol or "misafir") + "' - fiziksel komut yetkisi yok"})
        return jsonify(komut_calistir(_kmt))'''

# ---- ford_ekran.html: Guvenlik sekmesine arayuz + JS ----
HTML_ANCHOR_UI = '<div class="sub-sec" id="st-guvenlik">'
HTML_UI = HTML_ANCHOR_UI + '''
          <div class="s-title">👤 Kullanıcı Yönetimi</div>
          <div class="gc-aciklama">Yeni telefon <b>misafir</b> olur (kapı/cam/marş veremez). Buradan rol verip silebilirsin. Şifreyi sadece sen bilmelisin.</div>
          <div id="yn-kutu" class="s-group"></div>'''

HTML_JS_ANCHOR = 'function toggleBas(el){'
HTML_JS = '''/* FORD GUVENLIK JS */
var _ynSifre=null;
function _ynK(s){return (s||'').replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function _ynPost(u,o){return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o||{})}).then(function(r){return r.json();});}
function ynYenile(){
  fetch('/api/yonetici/durum').then(function(r){return r.json();}).then(function(d){
    var k=document.getElementById('yn-kutu'); if(!k)return;
    if(!d.sifre_var){
      k.innerHTML='<div class="s-row" style="flex-wrap:wrap;gap:8px"><input id="yn-s1" type="password" class="s-inp" placeholder="Yönetici şifresi (en az 4)"><input id="yn-s2" type="password" class="s-inp" placeholder="Şifre tekrar"><button class="s-btn s-btn-p" onclick="ynKur()">Şifre Belirle</button></div>';
    } else if(!_ynSifre){
      k.innerHTML='<div class="s-row" style="flex-wrap:wrap;gap:8px"><input id="yn-g" type="password" class="s-inp" placeholder="Yönetici şifresi"><button class="s-btn s-btn-p" onclick="ynGiris()">Giriş</button></div>';
    } else { ynListele(); }
  }).catch(function(){});
}
function ynKur(){
  var a=document.getElementById('yn-s1').value,b=document.getElementById('yn-s2').value;
  if(a!==b){alert('Şifreler aynı değil');return;}
  _ynPost('/api/yonetici/sifre_kur',{sifre:a}).then(function(d){ if(d.ok){_ynSifre=a;ynYenile();} else alert(d.hata||'olmadı'); });
}
function ynGiris(){
  var s=document.getElementById('yn-g').value;
  _ynPost('/api/yonetici/giris',{sifre:s}).then(function(d){ if(d.ok){_ynSifre=s;ynListele();} else alert('Şifre yanlış'); });
}
function ynListele(){
  _ynPost('/api/yonetici/telefonlar',{sifre:_ynSifre}).then(function(d){
    if(!d.ok){_ynSifre=null;ynYenile();return;}
    var h='';
    (d.telefonlar||[]).forEach(function(t){
      var benim=(t.mac===d.benim_mac)?' 📱':'';
      var ops=(d.roller||[]).map(function(r){return '<option value="'+r+'"'+(r===t.rol?' selected':'')+'>'+r+'</option>';}).join('');
      h+='<div class="s-row"><div class="sr-l"><div><div class="sr-lbl">'+_ynK(t.ad)+benim+'</div><div class="sr-desc">'+_ynK(t.mac)+'</div></div></div>'+
         '<select class="s-sel" onchange="ynRol(\\''+t.mac+'\\',this.value)">'+ops+'</select> '+
         '<button class="s-btn s-btn-d" onclick="ynSil(\\''+t.mac+'\\')">Sil</button></div>';
    });
    if(!(d.telefonlar||[]).length) h+='<div class="gc-aciklama">Henüz telefon yok. Bir telefon komut verince burada belirir.</div>';
    h+='<div class="s-title" style="margin-top:14px">Şifre Değiştir</div>'+
       '<div class="s-row" style="flex-wrap:wrap;gap:8px"><input id="yn-e" type="password" class="s-inp" placeholder="Eski şifre"><input id="yn-n1" type="password" class="s-inp" placeholder="Yeni şifre"><input id="yn-n2" type="password" class="s-inp" placeholder="Yeni (tekrar)"><button class="s-btn" onclick="ynDegis()">Değiştir</button><button class="s-btn" onclick="_ynSifre=null;ynYenile()">Çıkış</button></div>';
    document.getElementById('yn-kutu').innerHTML=h;
  }).catch(function(){});
}
function ynRol(mac,rol){ _ynPost('/api/yonetici/rol',{sifre:_ynSifre,mac:mac,rol:rol}).then(function(d){ if(!d.ok) alert(d.hata||'olmadı'); }); }
function ynSil(mac){ if(!confirm(mac+' silinsin mi?'))return; _ynPost('/api/yonetici/sil',{sifre:_ynSifre,mac:mac}).then(function(d){ if(d.ok) ynListele(); else alert(d.hata||'olmadı'); }); }
function ynDegis(){
  var e=document.getElementById('yn-e').value,n1=document.getElementById('yn-n1').value,n2=document.getElementById('yn-n2').value;
  if(n1!==n2){alert('Yeni şifreler aynı değil');return;}
  _ynPost('/api/yonetici/sifre_degistir',{eski:e,yeni:n1}).then(function(d){ if(d.ok){alert('Şifre değişti');_ynSifre=n1;ynListele();} else alert(d.hata||'olmadı'); });
}
window.addEventListener('load',function(){ setTimeout(ynYenile,1000); });
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


def web_yama():
    if not os.path.isfile(WEB):
        print("  ! ford_web.py yok:", WEB); return False
    src = open(WEB, encoding="utf-8").read()
    if WEB_ISARET in src:
        print("  = ford_web.py: zaten ekli, atlandı."); return True
    orj = src
    app = _appvar(src)

    # 1) modul yardimcilar  (def basla'dan once)
    if "\ndef basla(" not in src:
        print("  ! ford_web.py: 'def basla(' bulunamadı, DOKUNULMADI."); return False
    src = src.replace("\ndef basla(", "\n\n" + WEB_HELP + "\ndef basla(", 1)

    # 2) yonetici uclari  (return app'ten once, 4 girinti)
    uc = "\n".join(("    " + s) if s.strip() else s for s in WEB_UC.replace("{APP}", app).split("\n"))
    if "\n    return app\n" not in src:
        print("  ! ford_web.py: '    return app' bulunamadı, DOKUNULMADI."); return False
    src = src.replace("\n    return app\n", "\n" + uc + "\n    return app\n", 1)

    # 3) /api/komut kapisi
    if KOMUT_ESKI not in src:
        print("  ! ford_web.py: /api/komut blogu beklenen halde değil, DOKUNULMADI."); return False
    src = src.replace(KOMUT_ESKI, KOMUT_YENI, 1)

    yedek = WEB + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
    open(yedek, "w", encoding="utf-8").write(orj)
    open(WEB, "w", encoding="utf-8").write(src)
    try:
        py_compile.compile(WEB, doraise=True)
        _engelli_import(WEB)
    except Exception as e:
        open(WEB, "w", encoding="utf-8").write(orj)
        print("  ! ford_web.py: test patladı, GERİ ALINDI ->", type(e).__name__, str(e)[:140]); return False
    print("  ✓ ford_web.py: roller + /api/komut kapısı + yönetici uçları. (yedek:", os.path.basename(yedek) + ")")
    return True


def html_yama():
    if not os.path.isfile(HTML):
        print("  ! ford_ekran.html yok:", HTML); return False
    src = open(HTML, encoding="utf-8").read()
    if HTML_ISARET in src:
        print("  = ford_ekran.html: zaten ekli, atlandı."); return True
    if HTML_ANCHOR_UI not in src or HTML_JS_ANCHOR not in src:
        print("  ! ford_ekran.html: çapa bulunamadı, DOKUNULMADI."); return False
    yeni = src.replace(HTML_ANCHOR_UI, HTML_UI, 1)
    yeni = yeni.replace(HTML_JS_ANCHOR, HTML_JS + HTML_JS_ANCHOR, 1)
    yedek = HTML + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
    open(yedek, "w", encoding="utf-8").write(src)
    open(HTML, "w", encoding="utf-8").write(yeni)
    print("  ✓ ford_ekran.html: Kullanıcı Yönetimi arayüzü. (yedek:", os.path.basename(yedek) + ")")
    return True


def main():
    global WEB, HTML
    if len(sys.argv) > 1: WEB = sys.argv[1]
    if len(sys.argv) > 2: HTML = sys.argv[2]
    print("FORD güvenlik (rol + şifreli yönetici) ekleniyor...")
    a = web_yama(); b = html_yama()
    print("TAMAM ✓  Şimdi:  sudo systemctl restart ford" if (a and b)
          else "UYARI: en az biri eklenemedi (yukarı bak). Sistem bozulmadı.")


if __name__ == "__main__":
    main()
