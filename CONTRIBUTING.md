# Mitmachen

Schön, dass du helfen willst! WheelBridge ist ein Bastelprojekt. Am wertvollsten sind **Testberichte mit echter Hardware**.

## Testberichte & Bugs

Bitte die [Issue-Vorlage](https://github.com/W0rkingChr1s/WheelBridge/issues/new/choose) nutzen und anhängen:

- `wheelbridge version` und `wheelbridge doctor`
- bei Problemen mit der Xbox-Verbindung: den Mitschnitt aus `wheelbridge sniff`
- Lenkrad, Controller-Modell, Konsole

Funktioniert es mit deinem Lenkrad? Dann ist das ebenfalls ein Issue wert, damit wir eine Kompatibilitätsliste aufbauen können.

## Code

```bash
git clone https://github.com/W0rkingChr1s/WheelBridge.git
cd WheelBridge
pip install evdev pyusb            # bzw. apt install python3-evdev python3-usb
python3 -m unittest discover -s tests -v
shellcheck -S warning install.sh scripts/wheelbridge scripts/doctor.sh
```

Auf dem Pi installiert `sudo ./install.sh` direkt aus deinem Checkout.

**Konventionen**
- Nur die Python-Standardbibliothek plus `python3-evdev` und `python3-usb`, damit alles mit Debian-Paketen läuft.
- Das Dashboard ist eine einzelne HTML-Datei ohne Build-Schritt und ohne CDNs (der Pi ist oft offline).
- Kommentare, Logs und Oberfläche auf Deutsch.
- Unix-Zeilenenden (erzwungen über `.gitattributes`, geprüft in der CI).
- Neue Logik möglichst mit einem Test in `tests/` absichern. Hardwarezugriffe gehören in `wheel.py`, `controller.py` oder `ffs.py`, damit der Rest testbar bleibt.
