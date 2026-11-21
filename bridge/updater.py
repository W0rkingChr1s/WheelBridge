"""Updater: prüft GitHub-Releases und stößt ein Update über den Installer an.

- Prüfung: GitHub-API /releases (inkl. Vorabversionen, konfigurierbar), Vergleich mit VERSION
- Update:  `install.sh --update --branch <tag>` als eigene systemd-Unit (systemd-run).
           Nötig, weil der Installer den WheelBridge-Dienst neu startet – ein Kindprozess
           des Dienstes würde dabei mit beendet.

Auch als Kommandozeile nutzbar (für `wheelbridge update`):
  python3 updater.py --latest-tag      -> gibt das neueste Release-Tag aus
  python3 updater.py --check           -> Status als JSON
"""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

log = logging.getLogger("updater")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REPO = "W0rkingChr1s/WheelBridge"
LOG_PATH = "/var/lib/wheelbridge/update.log"
UNIT = "wheelbridge-update"
_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-.]?([0-9A-Za-z.]+))?$")


def parse_version(text):
    """'v0.4.0' / '0.4.0' / '0.4.0-rc1' -> vergleichbares Tupel; None bei Unsinn.

    Eine Version ohne Suffix gilt als neuer als dieselbe mit Suffix (0.4.0 > 0.4.0-rc1).
    """
    m = _TAG_RE.match((text or "").strip())
    if not m:
        return None
    major, minor, patch, pre = m.groups()
    return (int(major), int(minor), int(patch), 0 if pre else 1, pre or "")


def local_version():
    try:
        with open(os.path.join(ROOT, "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


def fetch_releases(repo=DEFAULT_REPO, timeout=10):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases?per_page=20",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "WheelBridge-Updater"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def pick_latest(releases, include_prerelease=True):
    best = None
    for rel in releases:
        if rel.get("draft") or (rel.get("prerelease") and not include_prerelease):
            continue
        v = parse_version(rel.get("tag_name"))
        if v and (best is None or v > best[0]):
            best = (v, rel)
    return best[1] if best else None


class Updater:
    def __init__(self, cfg=None):
        cfg = cfg or {}
        self.repo = cfg.get("repo", DEFAULT_REPO)
        self.include_prerelease = cfg.get("include_prerelease", True)
        self.interval = max(1.0, float(cfg.get("check_interval_h", 12))) * 3600
        self.enabled = cfg.get("auto_check", True)
        self.lock = threading.Lock()
        self.state = {
            "current": local_version(), "latest": None, "available": False,
            "notes": "", "url": None, "published": None, "prerelease": False,
            "checked": None, "error": None, "running": False,
        }

    # ---- Prüfen ----------------------------------------------------------
    def check(self):
        try:
            rel = pick_latest(fetch_releases(self.repo), self.include_prerelease)
            with self.lock:
                self.state["current"] = local_version()
                self.state["checked"] = int(time.time())
                self.state["error"] = None
                if not rel:
                    self.state.update(latest=None, available=False, notes="", url=None)
                else:
                    cur, new = parse_version(self.state["current"]), parse_version(rel["tag_name"])
                    self.state.update(
                        latest=rel["tag_name"], notes=rel.get("body") or "", url=rel.get("html_url"),
                        published=rel.get("published_at"), prerelease=bool(rel.get("prerelease")),
                        available=bool(cur and new and new > cur),
                    )
            if self.state["available"]:
                log.info("Update verfügbar: %s -> %s", self.state["current"], self.state["latest"])
        except (urllib.error.URLError, OSError, ValueError) as e:
            with self.lock:
                self.state["checked"] = int(time.time())
                self.state["error"] = f"GitHub nicht erreichbar: {e}"
            log.warning("Update-Prüfung fehlgeschlagen: %s", e)
        return self.status()

    def start_auto_check(self):
        if not self.enabled:
            return

        def loop():
            time.sleep(30)            # erst nach dem Start prüfen (Netz kann noch fehlen)
            while True:
                self.check()
                time.sleep(self.interval)
        threading.Thread(target=loop, name="updater", daemon=True).start()

    def status(self):
        with self.lock:
            st = dict(self.state)
        st["running"] = self.is_running()
        return st

    # ---- Ausführen -------------------------------------------------------
    def is_running(self):
        if not shutil.which("systemctl") or not os.path.isdir("/run/systemd/system"):
            return False
        r = subprocess.run(["systemctl", "is-active", "--quiet", UNIT], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0

    def apply(self, tag=None):
        tag = tag or self.state.get("latest")
        if not tag or not parse_version(tag):
            raise ValueError("Kein gültiges Release zum Aktualisieren – erst prüfen.")
        if self.is_running():
            raise ValueError("Ein Update läuft bereits.")
        if not shutil.which("systemd-run"):
            raise ValueError("systemd-run fehlt – bitte per Kommandozeile aktualisieren: sudo wheelbridge update")
        src = os.path.join(ROOT, "install.sh")
        if not os.path.isfile(src):
            raise ValueError(f"Installer nicht gefunden: {src}")
        # Kopie ausführen, weil der Installer das Programmverzeichnis ersetzt
        tmp = "/tmp/wheelbridge-install-update.sh"
        shutil.copyfile(src, tmp)
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "w") as f:
            f.write(f"Update auf {tag} gestartet: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        subprocess.run(["systemctl", "reset-failed", UNIT], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cmd = ["systemd-run", f"--unit={UNIT}", "--collect", "--quiet",
               "--property=StandardOutput=append:" + LOG_PATH,
               "--property=StandardError=append:" + LOG_PATH,
               "--setenv=TERM=dumb",
               "bash", tmp, "--update", "--branch", tag]
        r = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            raise ValueError(f"Update konnte nicht gestartet werden: {r.stderr.strip() or r.returncode}")
        log.info("Update auf %s gestartet (Log: %s)", tag, LOG_PATH)
        return {"started": True, "tag": tag}

    @staticmethod
    def read_log(max_bytes=20000):
        try:
            with open(LOG_PATH, "rb") as f:
                f.seek(0, os.SEEK_END)
                f.seek(max(0, f.tell() - max_bytes))
                text = f.read().decode("utf-8", "replace")
            return re.sub(r"\x1b\[[0-9;]*m", "", text)    # Farbcodes des Installers entfernen
        except OSError:
            return ""


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="WheelBridge-Updater")
    ap.add_argument("--latest-tag", action="store_true", help="neuestes Release-Tag ausgeben")
    ap.add_argument("--check", action="store_true", help="Status als JSON ausgeben")
    ap.add_argument("--stable", action="store_true", help="Vorabversionen ignorieren")
    ap.add_argument("--repo", default=DEFAULT_REPO)
    a = ap.parse_args()
    u = Updater({"repo": a.repo, "include_prerelease": not a.stable})
    st = u.check()
    if st["error"]:
        print(st["error"], file=sys.stderr)
        sys.exit(2)
    if a.latest_tag:
        if not st["latest"]:
            print("Noch kein Release veröffentlicht.", file=sys.stderr)
            sys.exit(3)
        print(st["latest"])
    else:
        st.pop("notes", None)
        print(json.dumps(st, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _cli()
