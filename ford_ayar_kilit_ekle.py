#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_ayar_kilit_ekle.py  —  TUM Ayarlar ekranini yonetici sifresine kilitler
=====================================================================
29 Ekim 2026

SORUN: Role Testi, Sistem, vb. ayarlara herkes girip sistemi bozabiliyor/
    role tetikleyebiliyordu.

NE YAPAR: overlay-settings (Ayarlar) acilinca, yonetici sifresi kuruluysa
    ve bu oturumda giris yoksa, ekranin uzerine sifre kilidi biner. Dogru
    sifre -> acilir. Tek oturum (Guvenlik/Kullanicilar ile ayni _ynSifre).
    Sifre KURULANA KADAR acik (opt-in) - ilk sifreyi Guvenlik'ten koyarsin.

    Sadece ford_ekran.html (HTML/JS). mevcut /api/yonetici/durum+giris
    uclarini kullanir (once ford_guvenlik_ekle.py). Yedek + idempotent.

KULLANIM (Pi'de):
    python3 ford_ayar_kilit_ekle.py
    sudo systemctl restart ford
"""

import os
import sys
import time

HTML = "/home/ford/ford_ekran.html"
ISARET = "FORD AYAR KILIT"

ANCHOR_INNER = '<div class="settings-app-inner">'
OVERLAY = ANCHOR_INNER + '''
    <div id="ayar-kilit"><div class="ayk-kutu"><div style="font-size:44px">🔒</div>
      <div class="ayk-b">Ayarlar Kilitli</div>
      <div class="ayk-a">Bu bölüm yönetici şifresi ile açılır.</div>
      <input id="ayar-sifre" type="password" class="s-inp" placeholder="Yönetici şifresi">
      <button class="s-btn s-btn-p" onclick="ayarGiris()">Giriş</button></div></div>'''

ANCHOR_JS = 'function toggleBas(el){'
JS = '''/* FORD AYAR KILIT */
if(typeof _ynPost==='undefined'){window._ynPost=function(u,o){return fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o||{})}).then(function(r){return r.json();});};}
if(typeof _ynSifre==='undefined'){window._ynSifre=null;}
(function(){var st=document.createElement('style');st.textContent=
 '.settings-app-inner{position:relative}'+
 '#ayar-kilit{display:none;position:absolute;inset:0;z-index:70;background:rgba(8,20,34,.985);align-items:center;justify-content:center;padding:20px}'+
 '#ayar-kilit.ac{display:flex}'+
 '#ayar-kilit .ayk-kutu{max-width:340px;width:100%;text-align:center;background:#12304d;border:1px solid #1d3a5c;border-radius:14px;padding:24px}'+
 '#ayar-kilit .ayk-b{font-size:17px;font-weight:700;margin-top:6px}'+
 '#ayar-kilit .ayk-a{font-size:12.5px;color:#9fc0e4;margin:6px 0 14px}'+
 '#ayar-kilit input{margin-bottom:10px}';document.head.appendChild(st);})();
function ayarGiris(){var s=(document.getElementById('ayar-sifre')||{}).value||'';
 _ynPost('/api/yonetici/giris',{sifre:s}).then(function(d){ if(d.ok){_ynSifre=s;ayarKilitUygula();} else alert('Şifre yanlış'); });}
function ayarKilitUygula(){var ov=document.getElementById('ayar-kilit');if(!ov)return;
 fetch('/api/yonetici/durum').then(function(r){return r.ok?r.json():{sifre_var:false};}).then(function(d){
   if(d.sifre_var&&!_ynSifre){ov.classList.add('ac');var i=document.getElementById('ayar-sifre');if(i)i.value='';}else{ov.classList.remove('ac');}
 }).catch(function(){ov.classList.remove('ac');});}
window.addEventListener('load',function(){ setTimeout(function(){
   var ov=document.getElementById('overlay-settings');
   if(ov&&!ov._aykW){ov._aykW=1; try{new MutationObserver(function(){ if(ov.classList.contains('open')) ayarKilitUygula(); }).observe(ov,{attributes:true,attributeFilter:['class']});}catch(e){} }
   ayarKilitUygula();
 },1000); });
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
    if ANCHOR_INNER not in src or ANCHOR_JS not in src:
        print("HATA: çapa bulunamadı (settings-app-inner / toggleBas). DOKUNULMADI."); sys.exit(2)
    yeni = src.replace(ANCHOR_INNER, OVERLAY, 1).replace(ANCHOR_JS, JS + ANCHOR_JS, 1)
    yedek = HTML + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
    open(yedek, "w", encoding="utf-8").write(src)
    open(HTML, "w", encoding="utf-8").write(yeni)
    print("TAMAM ✓  Tüm Ayarlar kilitlendi. (yedek:", os.path.basename(yedek) + ")")
    print("Şimdi:  sudo systemctl restart ford")


if __name__ == "__main__":
    main()
