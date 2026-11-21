# Changelog

Alle nennenswerten Änderungen an WheelBridge. Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [Unveröffentlicht]

### Behoben
- **Controller hing nach dem Verbinden mit der Xbox** (alle Schreibzugriffe mit `Errno 110`, kein Handshake). Ursache: Die Bridge schickte dem bereits vom Kernel konfigurierten Controller erneut `SET_CONFIGURATION`. Der Xbox-One-S-Controller (045e:02ea, FW 3.01) nimmt danach genau ein Paket an und blockiert, bis er stromlos war. Am echten Gerät mit usbmon und einer Xbox-Simulation eingegrenzt.
  - Kein erneutes `SET_CONFIGURATION` mehr, wenn das Gerät schon konfiguriert ist
  - Audio-Interface des Controllers wird wie bei xpad deaktiviert (`SET_INTERFACE 1/0`)
  - Keine USB-Resets mehr. Wo nötig, setzt die Bridge den Controller per GIP zurück (`POWER 0x07`), wie die Xbox selbst. `reset_on_enable` bleibt standardmäßig an, löst jetzt aber diesen GIP-Reset aus: Ohne ihn meldet sich ein Controller aus einer vorherigen Sitzung nicht neu, und die Xbox wartet ewig auf sein ANNOUNCE.

### Getestet
- **Erster erfolgreicher Durchlauf an echter Hardware** (Raspberry Pi 4, Trixie, Xbox-One-S-Controller 045e:02ea, Logitech G27): ANNOUNCE → IDENTIFY → POWER/LED → AUTH-Handshake über den echten Controller → Xbox liest Geräteinfos (0x1e), dann stehende Sitzung.
- Installer und `doctor` werten `dtoverlay=dwc2` jetzt abschnittsweise aus. Die `config.txt` von Raspberry Pi OS 13 (Trixie) enthält standardmäßig `[cm5] dtoverlay=dwc2,dr_mode=host`. Das wurde fälschlich als „Overlay schon vorhanden“ erkannt, und der Gadget-Modus wurde nie aktiviert.

### Geplant
- Erster Test an echter Xbox-Hardware, ggf. vollständige USB-Descriptors (Audio/Bulk-Interfaces)
- Guide-Knopf auf das Lenkrad legen
- Profile für weitere Lenkräder (G25, G29, DFGT)

## [0.3.0] – 2026-11-20

Erste öffentliche Version. **Experimentell.** Getestet sind Protokoll-Logik, Mapping, Dashboard und Installer, aber noch nicht der Betrieb an einer Xbox.

### Hinzugefügt
- **Bridge:** Raspberry Pi 4 als USB-Gadget (FunctionFS) mit geklonter Identität eines Original-Controllers. Der gesamte GIP-Verkehr wird roh durchgereicht, inklusive Auth-Handshake. Die Input-Reports werden durch Lenkraddaten ersetzt.
- **Lenkrad:** Logitech G27 via evdev/lg4ff mit Hardware-Lenkwinkel, Zentrierfeder und Rumble → Vibration; Kupplung als Knopf, H-Shifter als sequentielle Schaltung.
- **Web-Dashboard:** Live-Checkliste, Live-Ansicht, Mapping-Assistent, Einstellungen, Verkabelungsanleitung, Log. Keine externen Abhängigkeiten, als Homescreen-App installierbar.
- **Installer:** Einzeiler für Installation, Update und Deinstallation; idempotent, lässt die Konfiguration bei Updates unangetastet.
- **CLI** `wheelbridge` mit `doctor`-Systemcheck, `sniff`-Paketmitschnitt und `probe`.
- **Doku:** Installationsanleitung, Verkabelung, Branding.

[Unveröffentlicht]: https://github.com/W0rkingChr1s/WheelBridge/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/W0rkingChr1s/WheelBridge/releases/tag/v0.3.0
