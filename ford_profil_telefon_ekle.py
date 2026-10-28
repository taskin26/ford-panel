#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_profil_telefon_ekle.py  —  Kullanıcılar > Profil'e TANIMLI TELEFON
=====================================================================
29 Ekim 2026  (ford_guvenlik_ekle.py + ford_yetki_ince_ekle.py SONRASI)

SORUN (kullanıcının isteği):
    Kullanıcılar sekmesinde profil düzenlerken, RFID Kartı gibi, TANIMLI
    TELEFON da listelensin; profile bir telefon bağlanabilsin ki "hangi
    telefon kime ait" belli olsun ve o profilin izinleri gerçekten o
    telefona uygulansın.

NE YAPAR (sadece ford_ekran.html — HTML/JS):
    - Profil modalına "Tanımlı Telefon" bölümü (açılır liste) ekler.
    - Modal açılınca kayıtlı telefonları (/api/yonetici/telefonlar2) doldurur.
      (Kullanıcılar şifresiyle giriş yapılmışsa; yapılmadıysa uyarı yazar.)
    - KAYDET'e basınca, seçilen telefona:
        * profilin ADINI  (/api/yonetici/ad)
        * profildeki Kapı/Cam/Motor/Bagaj/Işık/Müzik izinlerini
          (/api/yonetici/yetki)
      yazar. Böylece güzel profil ekranı GERÇEK güvenlik defterini sürer.
    - Tamamen EK: her şey try/catch; başarısız olursa sessiz geçer,
      mevcut "Kaydet" davranışı AYNEN korunur. Bir şeyi bozmaz.

GÜVENLİ: yedek + saf metin-değişimi; idempotent.

KULLANIM (Pi'de):
    python3 ford_profil_telefon_ekle.py
    sudo systemctl restart ford
"""

import os
import sys
import time

HTML = "/home/ford/ford_ekran.html"
ISARET = "FORD PROFIL TELEFON"

# ---- 1) modal HTML: Yetkiler'den sonra "Tanımlı Telefon" ----
HTML_ESKI = '''        <div class="yetki-sira" id="pfYetki"></div>
      </div>'''
HTML_YENI = '''        <div class="yetki-sira" id="pfYetki"></div>
      </div>
      <div><!-- FORD PROFIL TELEFON -->
        <label class="alan-etiket">Tanımlı Telefon</label>
        <select class="metin-giris" id="pfTelefon"><option value="">— bu profile telefon bağla —</option></select>
        <div class="rfid-kod" id="pfTelNot" style="margin-top:6px">Kaydedince seçilen telefona bu profilin adı ve izinleri yazılır.</div>
      </div>'''

# ---- 2) JS (toggleBas çapasından önce eklenir) ----
JS_ANCHOR = 'function toggleBas(el){'
JS = r'''/* FORD PROFIL TELEFON */
function _pfSifre(){ return (typeof _ynSifre!=='undefined' && _ynSifre) ? _ynSifre : null; }
function _pfTelDoldur(){
  var sel=document.getElementById('pfTelefon'); if(!sel) return;
  var not=document.getElementById('pfTelNot');
  var s=_pfSifre();
  if(!s){ sel.innerHTML='<option value="">— önce Kullanıcılar şifresiyle giriş —</option>'; if(not)not.textContent='Telefon bağlamak için Kullanıcılar ekranında şifreyle giriş yapın.'; return; }
  var cur=''; try{ var u=kullaniciBul(_duzenlenen); cur=(u&&u.telMac)||''; }catch(e){}
  fetch('/api/yonetici/telefonlar2',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sifre:s})})
   .then(function(r){return r.json();}).then(function(d){
     if(!d||!d.ok){ sel.innerHTML='<option value="">— liste alınamadı —</option>'; return; }
     var h='<option value="">— bu profile telefon bağla —</option>';
     (d.telefonlar||[]).forEach(function(t){
       var ad=(t.ad||t.mac);
       h+='<option value="'+t.mac+'"'+((t.mac===cur)?' selected':'')+'>'+ad+' ('+t.mac+')</option>';
     });
     sel.innerHTML=h;
     if(not)not.textContent='Kaydedince seçilen telefona bu profilin adı ve izinleri yazılır.';
   }).catch(function(){});
}
function _pfTelKaydet(){
  var sel=document.getElementById('pfTelefon'); if(!sel) return;
  var mac=sel.value; if(!mac) return;
  var s=_pfSifre(); if(!s) return;
  var u; try{ u=kullaniciBul(_duzenlenen); }catch(e){}
  if(u){ u.telMac=mac; }
  var ad=''; try{ ad=document.getElementById('pfAd').value||''; }catch(e){}
  fetch('/api/yonetici/ad',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sifre:s,mac:mac,ad:ad})}).catch(function(){});
  var durum={};
  try{ document.querySelectorAll('#pfYetki .toggle').forEach(function(t){ durum[t.getAttribute('data-y')]=t.classList.contains('on'); }); }catch(e){}
  ['kapi','cam','motor','bagaj','isik','muzik'].forEach(function(g){
    fetch('/api/yonetici/yetki',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sifre:s,mac:mac,grup:g,deger:!!durum[g]})}).catch(function(){});
  });
}
window.addEventListener('load',function(){ setTimeout(function(){
  try{
    var pm=document.getElementById('profilModal');
    if(pm && !pm._pfW){ pm._pfW=1;
      new MutationObserver(function(){ if(pm.classList.contains('ac')) _pfTelDoldur(); })
        .observe(pm,{attributes:true,attributeFilter:['class']}); }
    if(typeof profilKaydet==='function' && !window._pfKW){ window._pfKW=1;
      var _opk=profilKaydet;
      window.profilKaydet=function(){ try{_pfTelKaydet();}catch(e){} return _opk.apply(this,arguments); }; }
  }catch(e){}
},1200); });
'''


def main():
    global HTML
    if len(sys.argv) > 1:
        HTML = sys.argv[1]
    print("Profil ekranına Tanımlı Telefon ekleniyor...")
    if not os.path.isfile(HTML):
        print("  ! ford_ekran.html yok:", HTML); sys.exit(1)
    src = open(HTML, encoding="utf-8").read()
    if ISARET in src:
        print("  = zaten ekli, atlandı."); sys.exit(0)
    if HTML_ESKI not in src or JS_ANCHOR not in src:
        print("  ! çapa bulunamadı (pfYetki / toggleBas). DOKUNULMADI."); sys.exit(2)
    if "function profilKaydet(" not in src or "function kullaniciBul(" not in src:
        print("  ! profil fonksiyonları bulunamadı (bu sürümde Kullanıcılar farklı). DOKUNULMADI."); sys.exit(2)
    yeni = src.replace(HTML_ESKI, HTML_YENI, 1).replace(JS_ANCHOR, JS + JS_ANCHOR, 1)
    yedek = HTML + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
    open(yedek, "w", encoding="utf-8").write(src)
    open(HTML, "w", encoding="utf-8").write(yeni)
    print("  ✓ ford_ekran.html: profil modalında Tanımlı Telefon. (yedek:",
          os.path.basename(yedek) + ")")
    print("TAMAM ✓  Şimdi:  sudo systemctl restart ford")


if __name__ == "__main__":
    main()
