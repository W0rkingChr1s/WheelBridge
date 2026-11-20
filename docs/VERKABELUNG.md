# Verkabelung

> Das Web-Dashboard (Tab **Anleitung**) zeigt dasselbe als Diagramm und führt mit einer Live-Checkliste durch die Inbetriebnahme.

```
                       ┌──────────────┐
  Pi-Netzteil ─Strom──▶│  USB-C-      │
  (5,1 V / 3 A)        │  Splitter    │──USB-C──▶ ┌─────────────────────┐
                       │ Daten│Strom  │           │  Raspberry Pi 4     │
  Xbox One X ─USB-A→C─▶│              │           │                     │
  (Datenkabel)         └──────────────┘           │  USB-A ──▶ Xbox-Controller (ohne Akkus!)
                                                  │  USB-A ──▶ Logitech G27 ◀── G27-Netzteil
                                                  └─────────────────────┘          ▲
                                                                     Pedale ─DB9───┤
                                                                     Shifter ─DB9──┘
```

## Die drei Regeln

1. **Nur der USB-C-Port des Pi kann zur Xbox.** Die USB-A-Buchsen hängen an einem reinen Host-Controller und können sich nicht als Gerät ausgeben. **Kein USB-A-auf-USB-A-Kabel!** Solche Kabel sind nicht spezifiziert, verbinden zwei 5-V-Quellen direkt und können Ports beschädigen.
2. **Den Pi nicht aus der Xbox versorgen.** Ein Xbox-Port liefert etwa 0,9 A, der Pi 4 braucht bis 3 A. Ein Splitter trennt Daten (Xbox) und Strom (Netzteil). Unterspannung zeigt das Dashboard an (`vcgencmd get_throttled`).
3. **Keine Akkus im Controller.** Sonst verbindet er sich per Funk direkt mit der Xbox, und die Brücke wird umgangen.

## Einkaufsliste

| Teil | Hinweis |
|---|---|
| Raspberry Pi 4 (≥ 2 GB) + microSD ≥ 8 GB | Pi OS Lite 64 Bit (Bookworm) |
| Offizielles Pi-4-Netzteil 5,1 V / 3 A | |
| USB-C-Daten/Strom-Splitter für Pi-Gadget-Betrieb | Datenzweig darf VBUS **nicht** zum Pi durchreichen |
| USB-A-auf-USB-C-**Datenkabel** | Viele billige Kabel sind reine Ladekabel |
| Original-Xbox-Controller (One oder Series) + Datenkabel | Micro-USB (One) bzw. USB-C (Series) |
| G27 mit Netzteil, Pedalen, Shifter | |

**Alternative ohne Splitter:** Pi über GPIO 2/4 (5 V) und 6 (GND) versorgen, dazu ein Datenkabel mit getrennter roter VBUS-Ader. Das umgeht die Polyfuse des Pi, also nur, wenn du weißt, was du tust.

## Reihenfolge beim Anschließen

1. Pi mit Netzteil starten, Lenkrad (mit Netzteil) und Controller (ohne Akkus) anstecken.
2. Dashboard öffnen (`http://<pi-ip>:8080`). Die Checkliste muss bis „Xbox-Schnittstelle bereit“ grün sein.
3. Erst jetzt das Datenkabel von der Xbox an den Splitter stecken und die Xbox einschalten.
