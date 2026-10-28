#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_kullanici_kilit_ekle.py  —  "Kullanıcılar" sekmesine YONETICI SIFRE KILIDI
=====================================================================
29 Ekim 2026

SORUN:
    Ayarlar > Kullanıcılar sekmesi sifresiz aciktı; misafir bile girip
    rol/yetki degistirebiliyordu.

NE YAPAR:
    sp-kullanici paneline bir KILIT katmani ekler. Yonetici sifresi
    kuruluysa ve bu oturumda giris yapilmadiysa sekme uzerine sifre
    ekrani biner. Dogru sifre -> acilir. (Guvenlik > Kullanici Yonetimi
    ile AYNI sifre ve ayni oturum; birinde giris yapinca digeri de acilir.)

    Sadece ford_ekran.html (HTML/JS). Backend'e dokunmaz; mevcut
    /api/yonetici/durum ve /api/yonetici/giris uclarini kullanir
    (onlar ford_guvenlik_ekle.py ile gelir - once onu uygula).

GUVENLI: yedek alir, saf metin-ekleme, idempotent.

KULLANIM (Pi'de):
    python3 ford_kullanici_kilit_ekle.py
    sudo systemctl restart ford
"""

import os
import sys
import time

HTML = "/home/ford/ford_ekran.html"
ISARET = "FORD KULLANICI KILIT"

ANCHOR_PANEL = '<div class="s-panel active" id="sp-kullanici">'
OVERLAY = ANCHOR_PANEL + '''
        <div id="kul-kilit"><div class="kul-kutu"><div style="font-size:42px">🔒</div>
          <div class="kul-b">Yönetici Girişi</div>
          <div class="kul-a">Bu bölüm şifre ile korunuyor.</div>
          <input id="kul-sifre" type="password" class="s-inp" placeholder="Yönetici şifresi">
          <button class="s-btn s-btn-p" onclick="kulGiris()">Giriş</button></div></div>'''

ANCHOR_JS = 'function toggleBas(el){'
JS = '''/* FORD KULLANICI KILIT */
if(typeof _ynPost==='undefined'){window._ynPost=function(u,o){return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o||{})}).then(function(r){return r.json();});};}
if(typeof _ynSifre==='undefined'){window._ynSifre=null;}
(function(){var st=document.createElement('style');st.textContent=
 '#sp-kullanici{position:relative}'+
 '#kul-kilit{display:none;position:absolute;inset:0;z-index:60;background:rgba(8,20,34,.975);align-items:center;justify-content:center;padding:20px}'+
 '#kul-kilit.ac{display:flex}'+
 '#kul-kilit .kul-kutu{max-width:340px;width:100%;text-align:center;background:#12304d;border:1px solid #1d3a5c;border-radius:14px;padding:22px}'+
 '#kul-kilit .kul-b{font-size:16px;font-weight:700;margin-top:6px}'+
 '#kul-kilit .kul-a{font-size:12.5px;color:#9fc0e4;margin:6px 0 14px}'+
 '#kul-kilit input{margin-bottom:10px}';
 document.head.appendChild(st);})();
function kulGiris(){var s=(document.getElementById('kul-sifre')||{}).value||'';
 _ynPost('/api/yonetici/giris',{sifre:s}).then(function(d){ if(d.ok){_ynSifre=s;kulKilitUygula();if(typeof kullanicilariCiz==='function')kullanicilariCiz();} else alert('Şifre yanlış'); });}
function kulKilitUygula(){var ov=document.getElementById('kul-kilit');if(!ov)return;
 fetch('/api/yonetici/durum').then(function(r){return r.ok?r.json():{sifre_var:false};}).then(function(d){
   if(d.sifre_var&&!_ynSifre){ov.classList.add('ac');}else{ov.classList.remove('ac');}
 }).catch(function(){ov.classList.remove('ac');});}
window.addEventListener('load',function(){ setTimeout(function(){
   if(typeof showSPanel==='function'&&!showSPanel._kulW){var o=showSPanel;window.showSPanel=function(n,el){o(n,el);if(n==='kullanici')kulKilitUygula();};window.showSPanel._kulW=1;}
   kulKilitUygula();
 },1100); });
'''


def main():
    global HTML
    if len(sys.argv) > 1:
        HTML = sys.argv[1]
    if not os.path.isfile(HTML):
        print("HATA: ford_ekran.html yok:", HTML); sys.exit(1)
    src = open(HTML, encoding="utf-8").read()
    if ISARET in src:
        print("Zaten ekli, atlandı:", HTML); sys.exit(0)
    if ANCHOR_PANEL not in src or ANCHOR_JS not in src:
        print("HATA: çapa bulunamadı (sp-kullanici / toggleBas). DOKUNULMADI."); sys.exit(2)
    yeni = src.replace(ANCHOR_PANEL, OVERLAY, 1).replace(ANCHOR_JS, JS + ANCHOR_JS, 1)
    yedek = HTML + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
    open(yedek, "w", encoding="utf-8").write(src)
    open(HTML, "w", encoding="utf-8").write(yeni)
    print("TAMAM ✓  Kullanıcılar sekmesi kilitlendi. (yedek:", os.path.basename(yedek) + ")")
    print("Şimdi:  sudo systemctl restart ford")


if __name__ == "__main__":
    main()
