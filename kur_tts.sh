#!/bin/bash
# FORD TTS kurulum - Pi'de TEK komutla:
#   - Piper (dogal Turkce neural ses) + Turkce ses modeli indirir
#   - espeak-ng (robotik yedek) kurar
#   - ford_tts.py servisini systemd ile surekli calistirir (reboot'ta da acilir)
#   - paneli (ford_ekran.html) gunceller
# ford_web'e / motora / Vosk'a DOKUNMAZ. 8090 portu ayri calisir.
# Piper inmezse sorun degil: espeak yedegiyle yine konusur.

HAM="https://raw.githubusercontent.com/taskin26/ford-panel/main"
HEDEF="/home/ford"
PIPER_SURUM="2023.11.14-2"
MODEL_KOK="https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium"

echo ">> 1/5  espeak-ng (yedek) kuruluyor..."
sudo apt-get update -y
sudo apt-get install -y espeak-ng

echo ">> 2/5  Piper indiriliyor (dogal Turkce ses)..."
A=$(uname -m)
case "$A" in
  aarch64|arm64)    PA=aarch64 ;;
  armv7l|armv6l|arm) PA=armv7l ;;
  x86_64|amd64)     PA=x86_64 ;;
  *) PA="" ;;
esac
if [ -n "$PA" ]; then
  mkdir -p "$HEDEF"
  if curl -fL "https://github.com/rhasspy/piper/releases/download/${PIPER_SURUM}/piper_linux_${PA}.tar.gz" -o /tmp/piper.tgz; then
    tar -xzf /tmp/piper.tgz -C "$HEDEF" && echo "   piper acildi ($PA)"
  else
    echo "   (piper indirilemedi - espeak yedegi kullanilacak)"
  fi
else
  echo "   (bilinmeyen islemci $A - espeak yedegi kullanilacak)"
fi

echo ">> 3/5  Turkce ses modeli indiriliyor (~60MB, biraz surebilir)..."
if [ -x "$HEDEF/piper/piper" ]; then
  curl -fL "$MODEL_KOK/tr_TR-dfki-medium.onnx"      -o "$HEDEF/piper/tr_TR-dfki-medium.onnx" \
    && curl -fL "$MODEL_KOK/tr_TR-dfki-medium.onnx.json" -o "$HEDEF/piper/tr_TR-dfki-medium.onnx.json" \
    && echo "   model indi" \
    || echo "   (model indirilemedi - espeak yedegi kullanilacak)"
fi

echo ">> 4/5  servis kuruluyor (ford_tts.py + systemd)..."
curl -fsSL "$HAM/ford_tts.py" -o "$HEDEF/ford_tts.py"
sudo tee /etc/systemd/system/ford-tts.service >/dev/null <<EOF
[Unit]
Description=FORD TTS (piper/espeak-ng)
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
sleep 2

echo ">> 5/5  panel guncelleniyor..."
curl -fsSL "$HAM/app/src/main/assets/ford_ekran.html" -o "$HEDEF/ford_ekran.html"

echo ""
echo ">> Motor durumu:"; curl -fsS "http://127.0.0.1:8090/" || echo "   (servis yaniti yok - 'systemctl status ford-tts')"
echo ">> Deneme sesi uretiliyor..."
curl -fsS "http://127.0.0.1:8090/tts?q=ford%20hazir%20kaptan" -o /tmp/ford_tts_test.wav \
  && echo "   TAMAM: /tmp/ford_tts_test.wav ($(wc -c </tmp/ford_tts_test.wav) byte)" \
  || echo "   (uyari: ses uretilemedi)"
echo ""
echo ">> BITTI. Teypte FORD'u kapat-ac, mikrofona bas, 'Merhaba Ford kapilari ac' de."
