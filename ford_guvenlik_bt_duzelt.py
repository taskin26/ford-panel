#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ford_guvenlik_bt_duzelt.py  —  Güvenlik ekranı BLUETOOTH'ta yanlış durum düzeltmesi
=====================================================================
29 Ekim 2026  (ford_guvenlik_ekle.py SONRASI)

SORUN (BT modunda):
    Güvenlik sekmesi açılışta BİR KEZ durum soruyordu. BT'de o an SPP
    bağlantısı daha kurulmamışsa köprü boş '{}' döndürüyor; panel bunu
    "şifre yok" sanıp "Şifre Belirle" gösteriyor. Aynı boş yanıt girişte
    de "Şifre yanlış" dedirtiyordu — oysa şifre doğru.

DÜZELTME (sadece ford_ekran.html — HTML/JS):
    1) Güvenlik sekmesi her AÇILDIĞINDA durum yeniden sorulur (showSubTab).
    2) ynYenile: yanıt boş/eksikse ('sifre_var' alanı yoksa) "şifre yok"
       VARSAYMAZ; "Bağlanıyor…" yazıp birkaç kez tekrar dener.
    3) ynGiris / ynKur: boş yanıtı "Şifre yanlış" sanmaz; "Bağlantı hazır
       değil, tekrar dene" der. Gerçekten yanlışsa yine uyarır.

NOT: WiFi'de  sudo systemctl restart ford  sonrası geçerli. BT için APK
    yeniden derlenmeli (gömülü panel güncellensin).

GÜVENLİ: yedek + saf metin-değişimi; idempotent.

KULLANIM (Pi'de):
    python3 ford_guvenlik_bt_duzelt.py
    sudo systemctl restart ford
"""

import os
import sys
import time

HTML = "/home/ford/ford_ekran.html"
ISARET = "FORD GUVENLIK BT"

# ---- 1) showSubTab: Güvenlik açılınca durum yenile ----
HOOK_ESKI = "  if(id === 'st-role') roleListeYukle();"
HOOK_YENI = ("  if(id === 'st-role') roleListeYukle();\n"
             "  if(id === 'st-guvenlik' && typeof ynYenile==='function') ynYenile(); /* FORD GUVENLIK BT */")

# ---- 2) ynYenile: boş yanıtı varsayma, tekrar dene ----
YEN_ESKI = '''function ynYenile(){
  fetch('/api/yonetici/durum').then(function(r){return r.json();}).then(function(d){
    var k=document.getElementById('yn-kutu'); if(!k)return;
    if(!d.sifre_var){
      k.innerHTML='<div class="s-row" style="flex-wrap:wrap;gap:8px"><input id="yn-s1" type="password" class="s-inp" placeholder="Yönetici şifresi (en az 4)"><input id="yn-s2" type="password" class="s-inp" placeholder="Şifre tekrar"><button class="s-btn s-btn-p" onclick="ynKur()">Şifre Belirle</button></div>';
    } else if(!_ynSifre){
      k.innerHTML='<div class="s-row" style="flex-wrap:wrap;gap:8px"><input id="yn-g" type="password" class="s-inp" placeholder="Yönetici şifresi"><button class="s-btn s-btn-p" onclick="ynGiris()">Giriş</button></div>';
    } else { ynListele(); }
  }).catch(function(){});
}'''
YEN_YENI = '''function ynYenile(_t){ /* FORD GUVENLIK BT */
  fetch('/api/yonetici/durum').then(function(r){return r.json();}).then(function(d){
    var k=document.getElementById('yn-kutu'); if(!k)return;
    if(!d || !('sifre_var' in d)){ /* BT henuz hazir degil -> varsayma, tekrar dene */
      k.innerHTML='<div class="gc-aciklama">Bağlanıyor…</div>';
      if((_t||0)<6) setTimeout(function(){ynYenile((_t||0)+1);},900);
      return;
    }
    if(!d.sifre_var){
      k.innerHTML='<div class="s-row" style="flex-wrap:wrap;gap:8px"><input id="yn-s1" type="password" class="s-inp" placeholder="Yönetici şifresi (en az 4)"><input id="yn-s2" type="password" class="s-inp" placeholder="Şifre tekrar"><button class="s-btn s-btn-p" onclick="ynKur()">Şifre Belirle</button></div>';
    } else if(!_ynSifre){
      k.innerHTML='<div class="s-row" style="flex-wrap:wrap;gap:8px"><input id="yn-g" type="password" class="s-inp" placeholder="Yönetici şifresi"><button class="s-btn s-btn-p" onclick="ynGiris()">Giriş</button></div>';
    } else { ynListele(); }
  }).catch(function(){ var k=document.getElementById('yn-kutu'); if(k && (_t||0)<6){k.innerHTML='<div class="gc-aciklama">Bağlanıyor…</div>';setTimeout(function(){ynYenile((_t||0)+1);},900);} });
}'''

# ---- 3a) ynGiris: boş yanıtı 'yanlış' sanma ----
GIR_ESKI = '''function ynGiris(){
  var s=document.getElementById('yn-g').value;
  _ynPost('/api/yonetici/giris',{sifre:s}).then(function(d){ if(d.ok){_ynSifre=s;ynListele();} else alert('Şifre yanlış'); });
}'''
GIR_YENI = '''function ynGiris(){ /* FORD GUVENLIK BT */
  var s=document.getElementById('yn-g').value;
  _ynPost('/api/yonetici/giris',{sifre:s}).then(function(d){
    if(d && d.ok){_ynSifre=s;ynListele();}
    else if(!d || !('ok' in d)){ alert('Bağlantı hazır değil, bir saniye sonra tekrar deneyin.'); }
    else { alert('Şifre yanlış'); }
  });
}'''

# ---- 3b) ynKur: boş yanıtı 'olmadı' sanma ----
KUR_ESKI = '''function ynKur(){
  var a=document.getElementById('yn-s1').value,b=document.getElementById('yn-s2').value;
  if(a!==b){alert('Şifreler aynı değil');return;}
  _ynPost('/api/yonetici/sifre_kur',{sifre:a}).then(function(d){ if(d.ok){_ynSifre=a;ynYenile();} else alert(d.hata||'olmadı'); });
}'''
KUR_YENI = '''function ynKur(){ /* FORD GUVENLIK BT */
  var a=document.getElementById('yn-s1').value,b=document.getElementById('yn-s2').value;
  if(a!==b){alert('Şifreler aynı değil');return;}
  _ynPost('/api/yonetici/sifre_kur',{sifre:a}).then(function(d){
    if(d && d.ok){_ynSifre=a;ynYenile();}
    else if(!d || !('ok' in d)){ alert('Bağlantı hazır değil, bir saniye sonra tekrar deneyin.'); }
    else { alert(d.hata||'olmadı'); }
  });
}'''


def main():
    global HTML
    if len(sys.argv) > 1:
        HTML = sys.argv[1]
    print("Güvenlik ekranı BT durum düzeltmesi...")
    if not os.path.isfile(HTML):
        print("  ! ford_ekran.html yok:", HTML); sys.exit(1)
    src = open(HTML, encoding="utf-8").read()
    if ISARET in src:
        print("  = zaten ekli, atlandı."); sys.exit(0)
    if "function ynYenile(){" not in src:
        print("  ! ynYenile bulunamadı — önce ford_guvenlik_ekle.py. DOKUNULMADI."); sys.exit(2)

    adimlar = [("showSubTab kancası", HOOK_ESKI, HOOK_YENI),
               ("ynYenile", YEN_ESKI, YEN_YENI),
               ("ynGiris", GIR_ESKI, GIR_YENI),
               ("ynKur", KUR_ESKI, KUR_YENI)]
    for ad, eski, yeni in adimlar:
        if eski not in src:
            print(f"  ! '{ad}' çapası beklenen halde değil. DOKUNULMADI."); sys.exit(2)
    yeni_src = src
    for ad, eski, yeni in adimlar:
        yeni_src = yeni_src.replace(eski, yeni, 1)

    yedek = HTML + ".YEDEK-" + time.strftime("%Y%m%d-%H%M%S")
    open(yedek, "w", encoding="utf-8").write(src)
    open(HTML, "w", encoding="utf-8").write(yeni_src)
    print("  ✓ ford_ekran.html: Güvenlik durumu sekme açılınca yenilenir + boş yanıt varsayılmaz.")
    print("     (yedek:", os.path.basename(yedek) + ")")
    print("TAMAM ✓  WiFi:  sudo systemctl restart ford   |   BT:  APK yeniden derle")


if __name__ == "__main__":
    main()
