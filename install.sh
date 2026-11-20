#!/usr/bin/env bash
# =============================================================================
#  WheelBridge Installer – alte PC-Lenkräder an Xbox One / Series (Raspberry Pi 4)
#  https://github.com/W0rkingChr1s/WheelBridge
#
#  Schnellinstallation:
#    curl -fsSL https://raw.githubusercontent.com/W0rkingChr1s/WheelBridge/main/install.sh | sudo bash
#
#  Aus einem Checkout:     sudo ./install.sh
#  Update:                 sudo wheelbridge update        (oder Installer erneut ausführen)
#  Deinstallation:         sudo wheelbridge uninstall     (oder ./install.sh --uninstall [--purge])
#
#  Der Installer ist idempotent: mehrfach ausführen schadet nicht.
# =============================================================================
set -Eeuo pipefail

WB_REPO="${WB_REPO:-https://github.com/W0rkingChr1s/WheelBridge.git}"
WB_BRANCH="${WB_BRANCH:-main}"

INSTALL_DIR="/opt/wheelbridge"
CONF_DIR="/etc/wheelbridge"
STATE_DIR="/var/lib/wheelbridge"
BIN="/usr/local/bin/wheelbridge"
UNIT="/etc/systemd/system/wheelbridge.service"
MODLOAD="/etc/modules-load.d/wheelbridge.conf"
BLACKLIST="/etc/modprobe.d/wheelbridge-no-xpad.conf"
BOOT_MARK="# wheelbridge: USB-C als Gadget (Xbox-Seite)"

ACTION="install"
ASSUME_YES=0
FORCE=0
LOCAL_SRC=""
ENABLE_SERVICE=1
PORT=""
PURGE=0
NEED_REBOOT=0

# ---------------------------------------------------------------------------
#  Ausgabe
# ---------------------------------------------------------------------------
if [[ -t 1 ]]; then
  C_B=$'\e[1m'; C_G=$'\e[32m'; C_Y=$'\e[33m'; C_R=$'\e[31m'; C_C=$'\e[36m'; C_0=$'\e[0m'
else
  C_B=""; C_G=""; C_Y=""; C_R=""; C_C=""; C_0=""
fi
step() { printf '\n%s==>%s %s%s%s\n' "$C_C" "$C_0" "$C_B" "$*" "$C_0"; }
ok()   { printf '  %s✓%s %s\n' "$C_G" "$C_0" "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '  %s!%s %s\n' "$C_Y" "$C_0" "$*"; }
die()  { printf '\n%s✗ Fehler:%s %s\n' "$C_R" "$C_0" "$*" >&2; exit 1; }
trap 'die "Abbruch in Zeile $LINENO (Befehl: $BASH_COMMAND)"' ERR

# Fragen funktionieren auch bei "curl | sudo bash" (liest von /dev/tty)
ask() {  # ask "Frage" default(y/n)
  local q="$1" def="${2:-n}" ans=""
  if (( ASSUME_YES )); then [[ "$def" == y ]]; return; fi
  if [[ -r /dev/tty ]]; then
    read -r -p "  ? $q [$( [[ $def == y ]] && echo J/n || echo j/N )] " ans </dev/tty || true
  fi
  ans="${ans:-$def}"
  [[ "$ans" =~ ^[JjYy] ]]
}

usage() {
  cat <<EOF
WheelBridge Installer

Aufruf: sudo ./install.sh [Optionen]

  -y, --yes            keine Rückfragen (Standardantworten)
      --local DIR      aus lokalem Verzeichnis installieren statt von GitHub
      --branch NAME    Git-Branch (Standard: $WB_BRANCH)
      --repo URL       Git-Repository (Standard: $WB_REPO)
      --port N         Port des Web-Dashboards (Standard: 8080)
      --no-service     Dienst nicht aktivieren/starten
      --force          auch auf nicht getesteter Hardware/OS installieren
      --uninstall      WheelBridge entfernen
      --purge          mit --uninstall: auch Konfiguration und Einstellungen löschen
  -h, --help           diese Hilfe

Umgebungsvariablen: WB_REPO, WB_BRANCH
EOF
}

while (($#)); do
  case "$1" in
    -y|--yes) ASSUME_YES=1 ;;
    --local) LOCAL_SRC="${2:?--local braucht ein Verzeichnis}"; shift ;;
    --branch) WB_BRANCH="${2:?}"; shift ;;
    --repo) WB_REPO="${2:?}"; shift ;;
    --port) PORT="${2:?}"; shift; [[ "$PORT" =~ ^[0-9]+$ ]] || die "--port erwartet eine Zahl" ;;
    --no-service) ENABLE_SERVICE=0 ;;
    --force) FORCE=1 ;;
    --uninstall) ACTION="uninstall" ;;
    --purge) PURGE=1 ;;
    --update) ACTION="install"; ASSUME_YES=1 ;;   # intern von "wheelbridge update"
    -h|--help) usage; exit 0 ;;
    *) die "Unbekannte Option: $1 (siehe --help)" ;;
  esac
  shift
done

# Läuft das Skript aus einem Checkout? Dann lokal installieren.
if [[ -z "$LOCAL_SRC" && -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  _self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -f "$_self_dir/bridge/main.py" && "$_self_dir" != "$INSTALL_DIR" ]]; then
    LOCAL_SRC="$_self_dir"
  fi
fi

[[ $EUID -eq 0 ]] || die "Bitte mit sudo ausführen:  sudo $0 $*"

boot_config() {
  if [[ -f /boot/firmware/config.txt ]]; then echo /boot/firmware/config.txt
  elif [[ -f /boot/config.txt ]]; then echo /boot/config.txt
  fi
}

have_systemd() { [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null; }

# =============================================================================
#  Deinstallation
# =============================================================================
uninstall() {
  step "WheelBridge wird entfernt"
  if have_systemd; then
    systemctl disable --now wheelbridge 2>/dev/null || true
    rm -f "$UNIT"; systemctl daemon-reload
    ok "Dienst gestoppt und entfernt"
  fi
  rm -f "$BIN" "$MODLOAD" "$BLACKLIST"
  ok "CLI, Modul-Autoload und xpad-Sperre entfernt"
  rm -rf "$INSTALL_DIR"
  ok "Programmdateien entfernt ($INSTALL_DIR)"

  local cfg; cfg="$(boot_config || true)"
  if [[ -n "$cfg" ]] && grep -qF "$BOOT_MARK" "$cfg"; then
    cp -a "$cfg" "$cfg.wheelbridge-uninstall.bak"
    sed -i "\|^$BOOT_MARK\$|,+1d" "$cfg"
    ok "dwc2-Overlay aus $cfg entfernt (Backup: $cfg.wheelbridge-uninstall.bak)"
    NEED_REBOOT=1
  fi

  if (( PURGE )); then
    rm -rf "$CONF_DIR" "$STATE_DIR"
    ok "Konfiguration und Einstellungen gelöscht"
  else
    info "Konfiguration bleibt erhalten: $CONF_DIR, $STATE_DIR  (komplett löschen: --purge)"
  fi
  (( NEED_REBOOT )) && warn "Neustart empfohlen, damit der USB-C-Port wieder normal arbeitet."
  printf '\n%sWheelBridge wurde entfernt.%s\n' "$C_G" "$C_0"
}

# =============================================================================
#  Installation
# =============================================================================
check_system() {
  step "System prüfen"
  local model=""
  [[ -r /proc/device-tree/model ]] && model="$(tr -d '\0' </proc/device-tree/model)"
  case "$model" in
    *"Raspberry Pi 4 Model"*)
      ok "Hardware: $model" ;;
    *"Raspberry Pi 400"*|*"Compute Module 4"*|*"Raspberry Pi 5"*|*"Zero 2"*)
      warn "Hardware: $model – nicht getestet. USB-Gadget-Betrieb kann abweichen."
      (( FORCE )) || ask "Trotzdem fortfahren?" n || die "Abgebrochen." ;;
    "")
      warn "Kein Raspberry Pi erkannt."
      (( FORCE )) || die "WheelBridge braucht einen Raspberry Pi 4 (USB-C mit Gadget-Modus). Zum Testen: --force" ;;
    *)
      warn "Hardware: $model – vermutlich ohne USB-Gadget-Port am richtigen Anschluss."
      (( FORCE )) || die "Nur Raspberry Pi 4 wird unterstützt. Zum Testen: --force" ;;
  esac

  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    case "${VERSION_CODENAME:-}" in
      bookworm|trixie) ok "Betriebssystem: ${PRETTY_NAME:-$ID}" ;;
      *) warn "Betriebssystem: ${PRETTY_NAME:-unbekannt} – getestet wird Raspberry Pi OS Bookworm." ;;
    esac
  fi

  command -v apt-get >/dev/null || die "apt-get fehlt – nur Debian/Raspberry Pi OS wird unterstützt."
  [[ -n "$(boot_config)" ]] || { (( FORCE )) || die "Keine /boot/firmware/config.txt gefunden."; warn "Keine Boot-Konfiguration gefunden (--force)"; }
  have_systemd || warn "systemd läuft nicht – Dienst wird nicht eingerichtet."
}

install_packages() {
  step "Pakete installieren"
  local pkgs=(python3 python3-evdev python3-usb usbutils curl ca-certificates)
  [[ -z "$LOCAL_SRC" ]] && pkgs+=(git)
  local missing=()
  for p in "${pkgs[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p"); done
  if ((${#missing[@]})); then
    info "Installiere: ${missing[*]}"
    DEBIAN_FRONTEND=noninteractive apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}" >/dev/null
    ok "Pakete installiert"
  else
    ok "Alle Pakete vorhanden"
  fi
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
    || die "Python >= 3.11 nötig (gefunden: $(python3 -V 2>&1)). Bitte Raspberry Pi OS Bookworm verwenden."
  ok "$(python3 -V)"
}

fetch_code() {
  step "Programm installieren nach $INSTALL_DIR"
  if [[ -n "$LOCAL_SRC" ]]; then
    [[ -f "$LOCAL_SRC/bridge/main.py" ]] || die "$LOCAL_SRC ist kein WheelBridge-Verzeichnis"
    rm -rf "$INSTALL_DIR.new"
    mkdir -p "$INSTALL_DIR.new"
    tar -C "$LOCAL_SRC" --exclude=.git --exclude='__pycache__' --exclude=settings.json -cf - . \
      | tar -C "$INSTALL_DIR.new" -xf -
    rm -rf "$INSTALL_DIR"; mv "$INSTALL_DIR.new" "$INSTALL_DIR"
    ok "Aus lokalem Verzeichnis kopiert: $LOCAL_SRC"
  elif [[ -d "$INSTALL_DIR/.git" ]]; then
    git -C "$INSTALL_DIR" remote set-url origin "$WB_REPO"
    git -C "$INSTALL_DIR" fetch -q --depth 1 origin "$WB_BRANCH"
    if ! git -C "$INSTALL_DIR" diff --quiet HEAD 2>/dev/null; then
      warn "Lokale Änderungen in $INSTALL_DIR werden überschrieben (Konfiguration liegt in $CONF_DIR und bleibt)."
    fi
    git -C "$INSTALL_DIR" reset -q --hard FETCH_HEAD
    ok "Aktualisiert auf $(git -C "$INSTALL_DIR" log -1 --format='%h %s')"
  else
    rm -rf "$INSTALL_DIR"
    git clone -q --depth 1 --branch "$WB_BRANCH" "$WB_REPO" "$INSTALL_DIR" \
      || die "Klonen fehlgeschlagen: $WB_REPO (Branch $WB_BRANCH)"
    ok "Geklont: $WB_REPO ($WB_BRANCH, $(git -C "$INSTALL_DIR" log -1 --format=%h))"
  fi
  find "$INSTALL_DIR" -name '__pycache__' -prune -exec rm -rf {} +
  chmod 755 "$INSTALL_DIR/install.sh" "$INSTALL_DIR/scripts/"*.sh 2>/dev/null || true
  python3 -m py_compile "$INSTALL_DIR"/bridge/*.py || die "Python-Dateien fehlerhaft"
  find "$INSTALL_DIR" -name '__pycache__' -prune -exec rm -rf {} +
  ok "Version $(cat "$INSTALL_DIR/VERSION" 2>/dev/null || echo '?')"
}

setup_config() {
  step "Konfiguration"
  install -d -m 755 "$CONF_DIR"
  install -d -m 700 "$STATE_DIR"
  local dist="$INSTALL_DIR/config.toml"
  if [[ ! -f "$CONF_DIR/config.toml" ]]; then
    install -m 644 "$dist" "$CONF_DIR/config.toml"
    ok "Angelegt: $CONF_DIR/config.toml"
  elif ! cmp -s "$dist" "$CONF_DIR/config.toml"; then
    install -m 644 "$dist" "$CONF_DIR/config.toml.dist"
    ok "Deine $CONF_DIR/config.toml bleibt unverändert"
    info "Neue Vorlage zum Vergleichen: $CONF_DIR/config.toml.dist"
  else
    ok "$CONF_DIR/config.toml ist aktuell"
  fi
  if [[ -n "$PORT" ]]; then
    sed -i -E "s/^port[[:space:]]*=.*/port = $PORT/" "$CONF_DIR/config.toml"
    ok "Dashboard-Port: $PORT"
  fi
  info "Änderungen aus dem Dashboard landen in $STATE_DIR/settings.json"
}

setup_boot() {
  step "USB-C-Port als Gadget einrichten (dwc2)"
  local cfg; cfg="$(boot_config || true)"
  if [[ -z "$cfg" ]]; then
    warn "Übersprungen – keine Boot-Konfiguration"; return
  fi
  if grep -qF "$BOOT_MARK" "$cfg"; then
    ok "Overlay bereits eingetragen ($cfg)"
  elif grep -qE '^[[:space:]]*dtoverlay=dwc2' "$cfg"; then
    if grep -qE '^[[:space:]]*dtoverlay=dwc2.*dr_mode=peripheral' "$cfg"; then
      ok "dwc2-Overlay bereits vorhanden ($cfg)"
    else
      warn "In $cfg steht bereits ein dwc2-Overlay ohne dr_mode=peripheral."
      info "Empfohlen: Zeile ersetzen durch  dtoverlay=dwc2,dr_mode=peripheral"
    fi
  else
    cp -a "$cfg" "$cfg.wheelbridge.bak"
    # nur einen [all]-Abschnitt öffnen, wenn der letzte Abschnitt ein anderer ist
    if [[ "$(grep -E '^[[:space:]]*\[' "$cfg" | tail -1 | tr -d '[:space:]')" == "[all]" ]]; then
      printf '%s\ndtoverlay=dwc2,dr_mode=peripheral\n' "$BOOT_MARK" >>"$cfg"
    else
      printf '\n[all]\n%s\ndtoverlay=dwc2,dr_mode=peripheral\n' "$BOOT_MARK" >>"$cfg"
    fi
    ok "Overlay eingetragen in $cfg (Backup: $cfg.wheelbridge.bak)"
    NEED_REBOOT=1
  fi

  install -d -m 755 "$(dirname "$MODLOAD")"
  printf '# WheelBridge: USB-Gadget\ndwc2\nlibcomposite\n' >"$MODLOAD"
  ok "Module beim Booten laden: dwc2, libcomposite"
  modprobe libcomposite 2>/dev/null || true

  if [[ ! -d /sys/class/udc ]] || [[ -z "$(ls -A /sys/class/udc 2>/dev/null)" ]]; then
    NEED_REBOOT=1
    info "USB-Gadget-Controller noch nicht aktiv – wird nach dem Neustart verfügbar."
  else
    ok "USB-Gadget-Controller aktiv: $(ls /sys/class/udc | head -1)"
  fi
}

setup_xpad() {
  step "xpad-Treiber sperren"
  install -d -m 755 "$(dirname "$BLACKLIST")"
  printf '# WheelBridge: der Xbox-Controller am Pi wird von WheelBridge selbst angesteuert\nblacklist xpad\n' >"$BLACKLIST"
  if lsmod 2>/dev/null | grep -q '^xpad'; then
    modprobe -r xpad 2>/dev/null && ok "xpad entladen und gesperrt" || { warn "xpad gesperrt, Entladen erst nach Neustart"; NEED_REBOOT=1; }
  else
    ok "xpad gesperrt"
  fi
}

install_cli() {
  step "Befehl 'wheelbridge' installieren"
  install -d -m 755 "$(dirname "$BIN")"
  install -m 755 "$INSTALL_DIR/scripts/wheelbridge" "$BIN"
  ok "$BIN  (Hilfe: wheelbridge help)"
}

setup_service() {
  step "Systemdienst"
  if ! have_systemd; then warn "Übersprungen – kein systemd"; return; fi
  cat >"$UNIT" <<EOF
[Unit]
Description=WheelBridge – Lenkrad an Xbox
Documentation=https://github.com/W0rkingChr1s/WheelBridge
After=sys-kernel-config.mount systemd-modules-load.service network.target
Wants=sys-kernel-config.mount

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/bridge/main.py -c $CONF_DIR/config.toml --settings $STATE_DIR/settings.json
Restart=on-failure
RestartSec=3
# root nötig: configfs, FunctionFS-Mount, USB-Zugriff, sysfs (Lenkwinkel)

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  ok "Dienst angelegt: $UNIT"
  if (( ENABLE_SERVICE )); then
    systemctl enable -q wheelbridge
    ok "Autostart beim Booten aktiviert"
    if (( NEED_REBOOT )); then
      info "Start erfolgt nach dem Neustart."
    else
      systemctl restart wheelbridge
      sleep 2
      systemctl is-active -q wheelbridge && ok "Dienst läuft" || warn "Dienst startet nicht – siehe: wheelbridge logs"
    fi
  else
    info "Nicht aktiviert (--no-service). Start manuell: sudo wheelbridge start"
  fi
}

summary() {
  local port ips
  port="$(sed -nE 's/^port[[:space:]]*=[[:space:]]*([0-9]+).*/\1/p' "$CONF_DIR/config.toml" | head -1)"
  port="${port:-8080}"
  ips="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+\.' || true)"

  printf '\n%s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n' "$C_G" "$C_0"
  printf '%s  WheelBridge ist installiert.%s\n' "$C_B" "$C_0"
  printf '%s━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━%s\n\n' "$C_G" "$C_0"
  echo "  Dashboard:"
  if [[ -n "$ips" ]]; then
    while read -r ip; do echo "    http://$ip:$port"; done <<<"$ips"
  fi
  echo "    http://$(hostname).local:$port"
  echo
  echo "  Nächste Schritte:"
  local n=1
  if (( NEED_REBOOT )); then echo "    $n. Neustart:  sudo reboot"; n=$((n+1)); fi
  echo "    $n. Lenkrad + Xbox-Controller (OHNE Akkus) an die USB-A-Ports des Pi"; n=$((n+1))
  echo "    $n. Dashboard öffnen und der Checkliste folgen (oder: wheelbridge doctor)"; n=$((n+1))
  echo "    $n. Erst dann: Xbox per USB-A→USB-C-Datenkabel an den USB-C-Port (über Splitter)"
  echo
  echo "  Nützlich:  wheelbridge doctor | logs | sniff | update | help"
  echo "  Anleitung: https://github.com/W0rkingChr1s/WheelBridge/blob/main/docs/INSTALL.md"
  echo

  if (( NEED_REBOOT )) && ask "Jetzt neu starten?" n; then
    echo "  Starte neu …"; sleep 1; reboot
  fi
}

main_install() {
  printf '%sWheelBridge Installer%s\n' "$C_B" "$C_0"
  check_system
  install_packages
  fetch_code
  setup_config
  setup_boot
  setup_xpad
  install_cli
  setup_service
  summary
}

case "$ACTION" in
  install) main_install ;;
  uninstall)
    ask "WheelBridge wirklich entfernen?" y || die "Abgebrochen."
    uninstall ;;
esac
