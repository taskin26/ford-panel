#!/bin/bash
# FORD TTS kurulum - Pi'de TEK komutla:
#   - espeak-ng (Turkce, cevrimdisi konusma motoru) kurar
#   - ford_tts.py servisini indirir, systemd ile surekli calistirir (reboot'ta da acilir)
#   - paneli (ford_ekran.html) gunceller
# ford_web'e / motor koduna / Vosk'a DOKUNMAZ. 8090 portu ayri calisir.
set -e
HAM="https://raw.githubusercontent.com/taskin26/ford-panel/main"
HEDEF="/home/ford"

echo ">> 1/4  espeak-ng kuruluyor..."
sudo apt-get update -y
sudo apt-get install -y espeak-ng

echo ">> 2/4  ford_tts.py indiriliyor..."
curl -fsSL "$HAM/ford_tts.py" -o "$HEDEF/ford_tts.py"

echo ">> 3/4  servis kuruluyor (systemd)..."
sudo tee /etc/systemd/system/ford-tts.service >/dev/null <<EOF
[Unit]
Description=FORD TTS (espeak-ng)
After=network.target

[Service]
ExecStart=/usr/bin/python3 $HEDEF/ford_tts.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable ford-tts >/dev/null 2>&1 || true
sudo systemctl restart ford-tts

echo ">> 4/4  panel guncelleniyor..."
curl -fsSL "$HAM/app/src/main/assets/ford_ekran.html" -o "$HEDEF/ford_ekran.html"

echo ""
echo ">> Deneme sesi:"
curl -fsS "http://127.0.0.1:8090/tts?q=ford%20hazir" -o /tmp/ford_tts_test.wav && \
  echo "   /tmp/ford_tts_test.wav uretildi ($(wc -c </tmp/ford_tts_test.wav) byte)" || \
  echo "   (uyari: servis yaniti alinamadi, 'systemctl status ford-tts' bak)"
echo ""
echo ">> BITTI. Teypte FORD'u kapat-ac, mikrofona bas, 'Merhaba Ford kapilari ac' de."
