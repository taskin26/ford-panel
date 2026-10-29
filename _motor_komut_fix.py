#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_motor_komut_fix.py  —  ford_web.py'de MOTOR durumunu KOMUTA baglar.

Kullanim:
    python3 _motor_komut_fix.py  <girdi_ford_web.py>  <cikti_ford_web.py>

Yaptigi TEK sey:
  durum_topla() icindeki  "motor": <ne olursa olsun>,   satirini
  "motor": bool(sim.get("motor_calisiyor")),  yapar  (voltaji yok sayar).
  Ayrica ELM devir override satirini (sonuc["motor"] = _e["devir"] > 300)
  oldugu gibi birakir AMA yoruma dusurmez -> gercek motor calisirsa dogru
  gosterir, bench'te (ELM yok/devir 0) tetiklenmez.
Voltaja/kalibrasyona DOKUNMAZ.
"""
import re, sys, py_compile, time, os

def main():
    girdi, cikti = sys.argv[1], sys.argv[2]
    src = open(girdi, encoding="utf-8").read()

    # 1) "motor": <value>,  ->  komut bayragi
    pat = re.compile(r'("motor":\s*)(.+?)(,\s*\n)')
    m = pat.search(src)
    if not m:
        print("HATA: durum_topla icinde '\"motor\":' satiri bulunamadi."); sys.exit(2)
    eski_deger = m.group(2).strip()
    yeni = pat.sub(r'\1bool(sim.get("motor_calisiyor"))\3  # MOTOR KOMUT: voltaj degil, calistir/durdur', src, count=1)

    if yeni == src and 'bool(sim.get("motor_calisiyor"))' in eski_deger:
        print("  = motor zaten komut-bazli; degisiklik yok.")
    changed = (yeni != src)
    src = yeni

    # dogrula
    py_compile.compile.__self__ if False else None
    try:
        compile(src, cikti, "exec")
    except SyntaxError as e:
        print("HATA: cikti derlenmiyor:", e); sys.exit(3)

    open(cikti, "w", encoding="utf-8").write(src)
    print(f"  eski motor degeri : {eski_deger}")
    print(f"  yeni motor degeri : bool(sim.get(\"motor_calisiyor\"))")
    print(f"  degisti           : {changed}")
    print(f"  cikti             : {cikti}  ({len(src)} bayt)  OK")

if __name__ == "__main__":
    main()
