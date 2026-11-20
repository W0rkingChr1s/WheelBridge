# Changelog

Alle nennenswerten Änderungen an WheelBridge. Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [Unveröffentlicht]

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
