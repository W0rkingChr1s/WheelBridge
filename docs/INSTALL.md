# Installation

Diese Anleitung führt dich von einer leeren SD-Karte bis zum Lenkrad an der Xbox. Rechne mit etwa 20 Minuten.

- [1. Was du brauchst](#1-was-du-brauchst)
- [2. Raspberry Pi OS vorbereiten](#2-raspberry-pi-os-vorbereiten)
- [3. WheelBridge installieren](#3-wheelbridge-installieren)
- [4. Erster Start und Kalibrierung](#4-erster-start-und-kalibrierung)
- [5. An die Xbox anschließen](#5-an-die-xbox-anschließen)
- [6. Update, Deinstallation, Befehle](#6-update-deinstallation-befehle)
- [7. Was der Installer am System ändert](#7-was-der-installer-am-system-ändert)
- [8. Fehlersuche](#8-fehlersuche)

---

## 1. Was du brauchst

| Teil | Hinweis |
|---|---|
| **Raspberry Pi 4** (2 GB reichen) | Andere Modelle sind nicht getestet. Der Pi 400 und der Pi 5 verhalten sich am USB-C-Port anders. |
| microSD-Karte ≥ 8 GB | |
| Offizielles Pi-4-Netzteil 5,1 V / 3 A | |
| **USB-C-Daten/Strom-Splitter** | trennt Daten (Xbox) und Strom (Netzteil), siehe [Verkabelung](VERKABELUNG.md) |
| USB-A-auf-USB-C-**Datenkabel** | Xbox → Splitter. Viele billige Kabel sind reine Ladekabel. |
| **Original-Xbox-Controller** (One oder Series) + Datenkabel | nur für den Sicherheits-Handshake. **Die Akkus kommen raus.** |
| Lenkrad, z. B. Logitech G27, mit Netzteil | |

> ⚠️ **Kein USB-A-auf-USB-A-Kabel.** Nur der USB-C-Port des Pi kann sich gegenüber der Xbox als Gerät ausgeben. Die USB-A-Buchsen können das nicht.

## 2. Raspberry Pi OS vorbereiten

1. Öffne den [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
2. Wähle **Raspberry Pi 4** → **Raspberry Pi OS Lite (64-bit)**. Eine Desktop-Version ist nicht nötig.
3. In den Einstellungen (Zahnrad bzw. „Einstellungen bearbeiten“):
   - Hostname, z. B. `wheelbridge`
   - Benutzer und Passwort
   - WLAN (oder später ein LAN-Kabel)
   - **SSH aktivieren**
4. Flashen, Karte in den Pi stecken, den Pi **mit dem Netzteil** starten (noch ohne Xbox).
5. Per SSH verbinden:
   ```bash
   ssh <benutzer>@wheelbridge.local
   ```

## 3. WheelBridge installieren

### Schnellinstallation (empfohlen)

```bash
curl -fsSL https://raw.githubusercontent.com/W0rkingChr1s/WheelBridge/main/install.sh | sudo bash
```

Der Installer prüft das System, installiert die Abhängigkeiten, richtet alles ein und fragt am Ende, ob er neu starten soll. **Der Neustart ist bei der Erstinstallation nötig**, weil der USB-C-Port erst danach im Gadget-Modus läuft.

> Lieber erst lesen, dann ausführen? Gute Idee:
> ```bash
> curl -fsSLO https://raw.githubusercontent.com/W0rkingChr1s/WheelBridge/main/install.sh
> less install.sh
> sudo bash install.sh
> ```

### Aus einem Git-Checkout

```bash
git clone https://github.com/W0rkingChr1s/WheelBridge.git
cd WheelBridge
sudo ./install.sh
```

Liegt `install.sh` in einem Checkout, installiert er automatisch aus diesem Verzeichnis. So kannst du eigene Änderungen testen.

### Installer-Optionen

| Option | Wirkung |
|---|---|
| `-y`, `--yes` | keine Rückfragen |
| `--port N` | Port des Dashboards (Standard 8080) |
| `--branch NAME` | anderer Git-Branch, z. B. `dev` |
| `--local DIR` | aus lokalem Verzeichnis installieren |
| `--no-service` | Dienst nicht automatisch starten |
| `--force` | auf nicht getesteter Hardware oder einem anderen OS installieren |
| `--uninstall [--purge]` | entfernen, mit `--purge` auch Konfiguration |

Beispiel mit Optionen beim Pipe-Aufruf:

```bash
curl -fsSL https://raw.githubusercontent.com/W0rkingChr1s/WheelBridge/main/install.sh | sudo bash -s -- -y --port 8000
```

## 4. Erster Start und Kalibrierung

Nach dem Neustart läuft WheelBridge als Dienst.

1. **Lenkrad** (mit eigenem Netzteil) und **Xbox-Controller** (ohne Akkus, per Kabel) an die USB-A-Ports des Pi stecken.
2. Das Dashboard aufrufen. Die Adresse zeigt dir:
   ```bash
   wheelbridge url
   ```
   In der Regel ist das `http://wheelbridge.local:8080`.
3. Im Tab **Übersicht** die Checkliste von oben nach unten durchgehen. Alles bis **„Xbox-Schnittstelle bereit“** muss grün sein.
   Im Terminal geht dasselbe mit:
   ```bash
   wheelbridge doctor
   ```
4. Im Tab **Mapping**:
   - jedes Pedal einmal durchtreten und der richtigen Achse die Rolle *Gas*, *Bremse* oder *Kupplung* geben
   - ist der Balken ohne Treten voll, **Inv.** anhaken (beim G27 normal)
   - Knöpfe drücken und einem Xbox-Knopf oder Gang zuweisen
5. Im Tab **Live** prüfen, ob alles stimmt.
6. Im Tab **Einstellungen** den Lenkwinkel einstellen. 270–360° ist ein guter Start.

Tipp fürs Handy am Rig: Dashboard öffnen → „Zum Home-Bildschirm“. Dann hast du WheelBridge als App-Icon.

## 5. An die Xbox anschließen

1. Netzteil an den **Strom**-Eingang des Splitters.
2. Xbox-Kabel (USB-A → USB-C) an den **Daten**-Eingang des Splitters.
3. Den Splitter-Ausgang in den **USB-C-Port des Pi**.
4. Die Xbox einschalten.

Die Checkliste sollte jetzt **„Mit Xbox verbunden“ → „Handshake mit Controller“ → „Lenkrad-Eingaben aktiv“** durchlaufen.

**Im Spiel (z. B. Forza):** Erweiterte Steuerung → **innere Lenk-Deadzone auf 0**, äußere auf 100. Die Kupplung auf den Knopf legen, den du unter *Einstellungen → Kupplung als Knopf* gewählt hast (Standard LB).

## 6. Update, Deinstallation, Befehle

```bash
wheelbridge update               # neueste Version von GitHub; Konfiguration bleibt erhalten
wheelbridge uninstall            # entfernen, Konfiguration bleibt
wheelbridge uninstall --purge    # alles entfernen
```

| Befehl | Zweck |
|---|---|
| `wheelbridge doctor` | Systemcheck mit Lösungshinweisen |
| `wheelbridge url` | Adresse des Dashboards |
| `wheelbridge status` / `logs` | Dienststatus, Log live |
| `wheelbridge start` / `stop` / `restart` | Dienst steuern |
| `wheelbridge run -v` | im Vordergrund mit Debug-Ausgabe (stoppt den Dienst) |
| `wheelbridge sniff [datei]` | mit Mitschnitt aller Xbox-Pakete, wichtig für Bug-Reports |
| `wheelbridge probe [--usb]` | Lenkrad-Codes bzw. Controller-Descriptors im Terminal |
| `wheelbridge config` | `config.toml` bearbeiten |
| `wheelbridge reset` | Dashboard-Einstellungen verwerfen |
| `wheelbridge version` | Version und Commit |

## 7. Was der Installer am System ändert

Volle Transparenz, alles wird bei der Deinstallation zurückgenommen:

| Pfad | Inhalt |
|---|---|
| `/opt/wheelbridge/` | Programm (Git-Checkout) |
| `/etc/wheelbridge/config.toml` | deine Konfiguration. **Wird bei Updates nie überschrieben**, neue Vorlagen landen als `config.toml.dist` daneben. |
| `/var/lib/wheelbridge/settings.json` | Änderungen aus dem Dashboard (überschreiben `config.toml`) |
| `/boot/firmware/config.txt` | eine markierte Zeile `dtoverlay=dwc2,dr_mode=peripheral` (Backup: `config.txt.wheelbridge.bak`) |
| `/etc/modules-load.d/wheelbridge.conf` | lädt `dwc2` und `libcomposite` beim Booten |
| `/etc/modprobe.d/wheelbridge-no-xpad.conf` | sperrt `xpad`, damit der Treiber den Controller nicht belegt |
| `/etc/systemd/system/wheelbridge.service` | Dienst (läuft als root, nötig für USB-Gadget und configfs) |
| `/usr/local/bin/wheelbridge` | Kommandozeile |
| Pakete | `python3-evdev`, `python3-usb`, `usbutils`, `git`, `curl` |

> 🔒 **Das Dashboard hat keine Anmeldung.** Betreib es nur im Heimnetz. Für mehr Abschottung setzt du in `/etc/wheelbridge/config.toml` `bind = "127.0.0.1"` und greifst per SSH-Tunnel zu: `ssh -L 8080:localhost:8080 <benutzer>@wheelbridge.local`.

## 8. Fehlersuche

Fang immer mit `wheelbridge doctor` an. Spätere Probleme hängen oft von früheren ab.

| Symptom | Lösung |
|---|---|
| `doctor`: „Kein Gadget-Controller“ | Neustart nach der Installation vergessen → `sudo reboot` |
| Pi startet neu oder hängt, sobald die Xbox dran ist | Unterspannung: der Pi zieht Strom aus der Xbox → Splitter richtig herum anschließen |
| „Kein Xbox-Controller am Pi“ | Ladekabel statt Datenkabel? Mit `lsusb` prüfen, ob `045e:` auftaucht |
| Controller verbindet sich direkt mit der Xbox | Akkus raus |
| „Mit Xbox verbunden“ fehlt | Kabel bzw. Splitter-Richtung, Datenkabel, anderen Xbox-Port probieren |
| Verbunden, aber kein Handshake | Im Log viele `Controller write: [Errno 110]`? Dann hängt der Controller: **USB-Kabel des Controllers kurz abziehen** (ein Software-Reset reicht dafür nicht). Sonst: Dashboard → „Controller neu anmelden“, `wheelbridge logs` |
| Bricht nach dem Handshake ab | `wheelbridge sniff` laufen lassen, Log an ein Issue hängen |
| Lenkrad nicht gefunden | eigenes Netzteil am Lenkrad? Anderes Modell → `name_match` in der Config |
| Lenkung zappelt in der Mitte | Gamma erhöhen; Deadzone im Spiel prüfen |

**Bug melden:** [Issue anlegen](https://github.com/W0rkingChr1s/WheelBridge/issues) mit der Ausgabe von `wheelbridge doctor`, `wheelbridge version` und, falls es die Xbox-Verbindung betrifft, dem Mitschnitt aus `wheelbridge sniff`.
