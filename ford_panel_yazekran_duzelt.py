#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_panel_yazekran_duzelt.py  —  ESP32'ye Yaz: CANLI LOG + buton geri açılır
=====================================================================
29 Ekim 2026

SORUN (kullanicinin dogru teshisi):
    Flash GERCEKTEN oluyor, ama panel:
      - canli log'u (SSH'deki "Writing..." satirlarini) gostermiyor,
      - is bitince "ESP32'ye Yaz" butonu tekrar aktiflesmiyor (gri kaliyor).
    Boylece "yazmiyor" saniliyor.

NE YAPAR (sadece ford_ekran.html — JS):
    eyYaz()'i KENDI ICINDE calisan saglam bir surumle degistirir:
      - basinca log kutusunu acar,
      - her saniye /api/esp32yaz/durum sorar, satirlari (log) cizer,
      - durum satirini (derleniyor/yaziliyor/bitti) gunceller,
      - is bitince (calisiyor=false) butonu KENDI aktifler,
      - 5 dk guvenlik zamanlayicisi: ne olursa olsun buton acilir
        (asla sonsuza gri kalmaz).

GUVENLI: yedek + saf metin-degisimi; idempotent. ford_web'e DOKUNMAZ.
    (Statik HTML; ford yeniden baslatmaya gerek yok, sayfa yenilemek yeter.)

KULLANIM (Pi'de):
    python3 ford_panel_yazekran_duzelt.py
    # panelde sayfayi yenile
"""

import os
import sys
import time

HTML = "/home/ford/ford_ekran.html"
ISARET = "FORD YAZEKRAN DUZELT"

ESKI = '''async function eyYaz(){
  if(!confirm('ESP32 yeniden yazılacak.\\n\\nÖnce derlenir — derlemede hata ' +
              'çıkarsa ESP32\\'ye hiç dokunulmaz.\\nİşlem sırasında röleler ' +
              'bırakılır ve ESP32 yeniden başlar.\\n\\nDevam?')) return;
  const b = document.getElementById('eyYazBtn');
  if(b){ b.disabled = true; b.style.opacity = '.5'; }
  try{
    await fetch('/api/esp32yaz/yaz', {method:'POST'});
  }catch(e){}
  setTimeout(eySor, 400);
}'''

YENI = '''async function eyYaz(){ /* FORD YAZEKRAN DUZELT */
  if(!confirm('ESP32 yeniden yazılacak.\\n\\nÖnce derlenir — derlemede hata ' +
              'çıkarsa ESP32\\'ye hiç dokunulmaz.\\nİşlem sırasında röleler ' +
              'bırakılır ve ESP32 yeniden başlar.\\n\\nDevam?')) return;
  var b = document.getElementById('eyYazBtn');
  var kayit = document.getElementById('eyKayit');
  var durum = document.getElementById('eyDurum');
  if(b){ b.disabled = true; b.style.opacity = '.5'; }
  if(kayit){ kayit.style.display=''; kayit.textContent='Başlatılıyor… (derleme 1-2 dk sürebilir)'; }
  if(durum){ durum.textContent='⏳ Başlatılıyor…'; durum.style.color=''; }
  try{ await fetch('/api/esp32yaz/yaz', {method:'POST'}); }catch(e){}
  var t0 = Date.now();
  if(window._eyTik){ clearInterval(window._eyTik); }
  function _bitir(){ if(window._eyTik){clearInterval(window._eyTik);window._eyTik=null;} if(b){b.disabled=false;b.style.opacity='';} }
  window._eyTik = setInterval(async function(){
    try{
      var r = await fetch('/api/esp32yaz/durum', {cache:'no-store'});
      var d = await r.json();
      if(d && d.satirlar && d.satirlar.length && kayit){
        kayit.style.display='';
        var altta = kayit.scrollTop + kayit.clientHeight >= kayit.scrollHeight - 30;
        kayit.textContent = d.satirlar.join('\\n');
        if(altta) kayit.scrollTop = kayit.scrollHeight;
      }
      if(durum && d){
        if(d.calisiyor){ var ad={kurulum:'Kuruluyor',derleme:'Derleniyor',yazma:'Yazılıyor'};
          durum.textContent='⏳ '+(ad[d.asama]||d.asama||'')+' — '+(d.mesaj||'')+'  ('+(d.gecen||0)+' sn)'; durum.style.color=''; }
        else if(d.asama==='bitti'){ durum.textContent=(d.basarili?'✓ ':'✕ ')+(d.mesaj||''); durum.style.color=d.basarili?'':'#ff6666'; }
      }
      if(d && !d.calisiyor){ _bitir(); }
    }catch(e){}
    if(Date.now()-t0 > 300000){ _bitir(); }   /* 5 dk guvenlik: butonu her halukarda ac */
  }, 1000);
}'''


def main():
    global HTML
    if len(sys.argv) > 1:
        HTML = sys.argv[1]
    print("ESP32'ye Yaz ekranı (canlı log + buton) düzeltiliyor...")
    if not os.path.isfile(HTML):
        print("  ! ford_ekran.html yok:", HTML); sys.exit(1)
    src = open(HTML, encoding="utf-8").read()
    if ISARET in src:
        print("  = zaten ekli, atlandı."); sys.exit(0)
    if ESKI not in src:
        print("  ! eyYaz() çapası beklenen halde değil (sürüm farklı olabilir). DOKUNULMADI.")
        print("    -> bana bu satırı gönder:  grep -n 'async function eyYaz' <ford_ekran.html>")
        sys.exit(2)
    yeni = src.replace(ESKI, YENI, 1)
    yedek = HTML + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
    open(yedek, "w", encoding="utf-8").write(src)
    open(HTML, "w", encoding="utf-8").write(yeni)
    print("  ✓ ford_ekran.html: canlı log + buton kendi açılır (5 dk güvenlik).")
    print("     (yedek:", os.path.basename(yedek) + ")")
    print("TAMAM ✓  Panelde sayfayı YENİLE (ford'u yeniden başlatmaya gerek yok).")


if __name__ == "__main__":
    main()
