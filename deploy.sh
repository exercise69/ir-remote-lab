#!/bin/zsh
# Bringt das IR-Labor auf den QT Py (Laufwerk CIRCUITPY).
#   ./deploy.sh          Dateien kopieren, fehlende Bibliotheken installieren
# Das Board startet danach von selbst neu (Auto-Reload).
set -e
cd "${0:A:h}"
DST=/Volumes/CIRCUITPY

if [[ ! -d $DST ]]; then
  echo "CIRCUITPY ist nicht eingehaengt – Board per USB anschliessen." >&2
  exit 1
fi

# Bibliotheken passend zur CircuitPython-Version auf dem Board (.mpy)
for lib in adafruit_httpserver adafruit_sdcard adafruit_ntp; do
  if [[ ! -e $DST/lib/$lib && ! -e $DST/lib/$lib.mpy ]]; then
    echo "Installiere $lib ..."
    .venv/bin/circup --path $DST install $lib
  fi
done

mkdir -p $DST/web $DST/sd
# -X: keine macOS-Zusatzdateien (._*) aufs Board; code.py zuletzt, damit der
# Neustart erst kommt, wenn alles da ist
cp -X web/index.html $DST/web/index.html
cp -X ir_lab.py $DST/ir_lab.py
# Sicherung der gelernten Codes: das Board nimmt sie, wenn die SD-Karte fehlt
[[ -f captures/codes.json ]] && cp -X captures/codes.json $DST/codes.json
cp -X code.py $DST/code.py
sync
echo "Fertig. Die Adresse der Webseite steht in der seriellen Konsole (Zeile 'Webseite:')."
