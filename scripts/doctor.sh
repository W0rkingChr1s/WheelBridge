#!/usr/bin/env bash
# WheelBridge – Systemcheck. Prüft alles, was für den Betrieb nötig ist, und gibt Lösungshinweise.
set -uo pipefail

DIR="${WB_DIR:-/opt/wheelbridge}"
CONF="${WB_CONF:-/etc/wheelbridge/config.toml}"

if [[ -t 1 ]]; then G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; B=$'\e[1m'; N=$'\e[0m'; else G=; Y=; R=; B=; N=; fi
FAIL=0; WARN=0
pass() { printf '  %s✓%s %s\n' "$G" "$N" "$1"; }
fail() { printf '  %s✗%s %s\n    → %s\n' "$R" "$N" "$1" "$2"; FAIL=$((FAIL+1)); }
note() { printf '  %s!%s %s\n    → %s\n' "$Y" "$N" "$1" "$2"; WARN=$((WARN+1)); }
section() { printf '\n%s%s%s\n' "$B" "$1" "$N"; }

printf '%sWheelBridge Doctor%s  (%s)\n' "$B" "$N" "$(cat "$DIR/VERSION" 2>/dev/null || echo 'Version ?')"

section "System"
model="$( { tr -d '\0' </proc/device-tree/model; } 2>/dev/null || true)"
case "$model" in
  *"Raspberry Pi 4 Model"*) pass "$model" ;;
  "") fail "Kein Raspberry Pi erkannt" "WheelBridge braucht einen Pi 4 (USB-C mit Gadget-Modus)" ;;
  *) note "$model" "Nicht getestet – unterstützt wird der Raspberry Pi 4" ;;
esac
if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
  pass "$(python3 -V)"
else
  fail "Python zu alt ($(python3 -V 2>&1))" "Raspberry Pi OS Bookworm (Python 3.11) verwenden"
fi
for mod in evdev usb; do
  python3 -c "import $mod" 2>/dev/null && pass "Python-Modul $mod" \
    || fail "Python-Modul $mod fehlt" "sudo apt install python3-$([[ $mod == usb ]] && echo usb || echo evdev)"
done
[[ -f "$CONF" ]] && pass "Konfiguration $CONF" || fail "Konfiguration fehlt: $CONF" "Installer erneut ausführen"

section "USB-Gadget (Xbox-Seite)"
cfg=/boot/firmware/config.txt; [[ -f $cfg ]] || cfg=/boot/config.txt
# nur Zeilen, die auf dem Pi 4 wirken (vor dem ersten Abschnitt, [all], [pi4])
dwc2="$(awk 'BEGIN { active = 1 }
  /^[[:space:]]*\[/ { s = tolower($0); gsub(/[][[:space:]]/, "", s); active = (s == "all" || s == "pi4"); next }
  active && /^[[:space:]]*dtoverlay=dwc2/ { print }' "$cfg" 2>/dev/null)"
if grep -q 'dr_mode=peripheral' <<<"$dwc2"; then
  pass "dwc2-Overlay in $cfg"
elif [[ -n "$dwc2" ]]; then
  note "dwc2-Overlay ohne dr_mode=peripheral" "Zeile in $cfg ändern zu: dtoverlay=dwc2,dr_mode=peripheral"
else
  fail "dwc2-Overlay fehlt" "Installer ausführen, dann sudo reboot"
fi
if [[ -n "$(ls -A /sys/class/udc 2>/dev/null)" ]]; then
  pass "Gadget-Controller aktiv: $(ls /sys/class/udc | head -1)"
else
  fail "Kein Gadget-Controller (/sys/class/udc leer)" "Neustart nach der Installation nötig: sudo reboot"
fi
[[ -d /sys/kernel/config/usb_gadget ]] && pass "configfs/libcomposite geladen" \
  || fail "libcomposite nicht geladen" "sudo modprobe libcomposite"

section "Treiber & Strom"
if lsmod 2>/dev/null | grep -q '^xpad'; then
  fail "xpad ist geladen und belegt den Controller" "sudo modprobe -r xpad (dauerhaft: Installer setzt die Sperre)"
else
  pass "xpad nicht geladen"
fi
if command -v vcgencmd >/dev/null; then
  t="$(vcgencmd get_throttled 2>/dev/null | sed -n 's/throttled=//p')"
  if [[ -n "$t" ]]; then
    v=$((t))
    if (( v & 0x1 )); then fail "Unterspannung JETZT" "Pi nicht über die Xbox versorgen – Splitter + 5,1 V/3 A-Netzteil"
    elif (( v & 0x10000 )); then note "Unterspannung seit dem Boot aufgetreten" "Netzteil/Splitter prüfen"
    else pass "Stromversorgung stabil"; fi
  fi
else
  note "vcgencmd fehlt – Stromversorgung nicht prüfbar" "sudo apt install libraspberrypi-bin"
fi

section "Geräte am Pi"
if command -v lsusb >/dev/null; then
  ctrl="$(lsusb -d 045e: 2>/dev/null | head -1)"
  [[ -n "$ctrl" ]] && pass "Microsoft-Gerät: ${ctrl#*ID }" \
    || fail "Kein Xbox-Controller am Pi" "Original-Controller per Datenkabel an USB-A – ohne Akkus!"
else
  note "lsusb fehlt" "sudo apt install usbutils"
fi
name="$(sed -nE 's/^name_match[[:space:]]*=[[:space:]]*"([^"]*)".*/\1/p' "$CONF" 2>/dev/null | head -1)"
name="${name:-G27}"
if grep -qi "^N: Name=.*$name" /proc/bus/input/devices 2>/dev/null; then
  pass "Lenkrad: $(grep -i "^N: Name=.*$name" /proc/bus/input/devices | head -1 | sed 's/N: Name=//; s/"//g')"
else
  fail "Kein Lenkrad mit \"$name\" im Namen" "Lenkrad an USB-A + eigenes Netzteil; anderer Name: name_match in $CONF"
fi

section "Dienst & Dashboard"
if systemctl is-active -q wheelbridge 2>/dev/null; then
  pass "Dienst läuft"
  port="$(sed -nE 's/^port[[:space:]]*=[[:space:]]*([0-9]+).*/\1/p' "$CONF" | head -1)"; port="${port:-8080}"
  if st="$(curl -fsS -m 3 "http://127.0.0.1:$port/api/status" 2>/dev/null)"; then
    pass "Dashboard antwortet auf Port $port"
    python3 - "$st" <<'EOF'
import json, sys
s = json.loads(sys.argv[1])
x = s["xbox"]
print(f"    Status: {s['stage']}")
print(f"    Xbox verbunden: {'ja' if x['enabled'] else 'nein'} | Handshake: {'ja' if x['auth_seen'] else 'nein'} | Lenkrad aktiv: {'ja' if x['armed'] else 'nein'}")
for k, v in s.get("errors", {}).items():
    if v:
        print(f"    Fehler ({k}): {v}")
EOF
  else
    fail "Dashboard antwortet nicht auf Port $port" "wheelbridge logs"
  fi
else
  if systemctl is-enabled -q wheelbridge 2>/dev/null; then
    fail "Dienst läuft nicht" "wheelbridge start  bzw.  wheelbridge logs"
  else
    note "Dienst nicht aktiviert" "sudo systemctl enable --now wheelbridge"
  fi
fi

echo
if (( FAIL )); then
  printf '%s%d Problem(e)%s, %d Hinweis(e). Oben beginnen – spätere Punkte hängen oft von früheren ab.\n' "$R" "$FAIL" "$N" "$WARN"
  exit 1
elif (( WARN )); then
  printf '%sAlles Wichtige ok%s, %d Hinweis(e).\n' "$G" "$N" "$WARN"
else
  printf '%sAlles ok.%s\n' "$G" "$N"
fi
