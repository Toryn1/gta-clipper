#!/usr/bin/env python3
"""
YouTube-Uploader (Shorts + lange Videos)
----------------------------------------
Lädt Videos als PRIVAT auf deinen YouTube-Kanal. Du prüfst sie in YouTube Studio
und stellst sie mit einem Klick auf "Öffentlich".

  Shorts:        alles aus  fertig/<streamer>/   (die zusammengeschnittenen Clips)
  Lange Videos:  alles aus  youtube_lang/         (dein eigenes Gameplay)

Titel/Beschreibung: Liegt neben einem Video eine gleichnamige .txt-Datei, wird sie benutzt:
    TITEL: Mein Titel
    TAGS: gta6, gta, gaming
    ---
    Beschreibung ab hier (mehrere Zeilen möglich)
Sonst wird ein Standard-Text mit Streamer-Credit erzeugt.

Schon hochgeladene Videos bekommen eine Datei "<video>.youtube.txt" mit dem Link
und werden nicht nochmal hochgeladen.

Einmalig nötig: client_secret.json (Google Cloud, siehe ANLEITUNG) in diesem Ordner.
Nur Python-Standardbibliothek.
"""

import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SECRET_FILE = os.path.join(HERE, "client_secret.json")
TOKEN_FILE = os.path.join(HERE, "youtube_token.json")
SHORTS_DIR = os.path.join(HERE, "fertig")
LONG_DIR = os.path.join(HERE, "youtube_lang")
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".mkv", ".webm")
SCOPE = "https://www.googleapis.com/auth/youtube.upload"
PORT = 8765
REDIRECT = f"http://127.0.0.1:{PORT}"

DEFAULT_TAGS_SHORT = ["gta6", "gta 6", "gtavi", "grand theft auto 6", "twitch", "shorts", "gaming", "clips"]
DEFAULT_TAGS_LONG = ["gta6", "gta 6", "gameplay", "gaming", "no commentary"]


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def notify(title, text):
    if sys.platform == "darwin":
        clean = lambda x: x.replace("\\", "").replace('"', "'")
        subprocess.run(["osascript", "-e", f'display notification "{clean(text)}" with title "{clean(title)}"'],
                       capture_output=True)


# ---------------------------------------------------------------- Login ---

def load_client():
    if not os.path.exists(SECRET_FILE):
        sys.exit("client_secret.json fehlt in diesem Ordner. Siehe ANLEITUNG (Teil YouTube).")
    with open(SECRET_FILE, encoding="utf-8") as f:
        data = json.load(f)
    c = data.get("installed") or data.get("web") or {}
    if not c.get("client_id"):
        sys.exit("client_secret.json ist ungültig. Bitte als 'Desktop-App' in Google Cloud neu herunterladen.")
    return c["client_id"], c.get("client_secret", "")


def post_form(url, fields):
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode(errors="replace")[:300]}


def login_browser(cid, csecret):
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state:
                got["code"] = q.get("code", [None])[0]
                got["error"] = q.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Fertig! Du kannst diesen Tab schliessen." if got.get("code") else "Login abgebrochen."
            self.wfile.write(f"<body style='font-family:sans-serif;padding:40px'><h2>{msg}</h2>".encode())

        def log_message(self, *a):
            pass

    try:
        srv = http.server.HTTPServer(("127.0.0.1", PORT), H)
    except OSError:
        sys.exit(f"Port {PORT} ist besetzt - läuft der Uploader schon in einem anderen Fenster?")
    srv.timeout = 1
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    log("Öffne Google-Login im Browser (YouTube-Kanal auswählen und erlauben)...")
    log(f"Falls sich nichts öffnet:\n  {url}")
    webbrowser.open(url)
    end = time.time() + 300
    while not (got.get("code") or got.get("error")) and time.time() < end:
        srv.handle_request()
    srv.server_close()
    if not got.get("code"):
        sys.exit(f"Kein Login erhalten ({got.get('error') or 'Zeit abgelaufen'}).")
    tok = post_form("https://oauth2.googleapis.com/token", {
        "code": got["code"], "client_id": cid, "client_secret": csecret, "redirect_uri": REDIRECT,
        "grant_type": "authorization_code", "code_verifier": verifier})
    if "access_token" not in tok:
        sys.exit(f"Login fehlgeschlagen: {tok}")
    save_token(tok)
    return tok["access_token"]


def save_token(tok):
    old = {}
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, encoding="utf-8") as f:
            old = json.load(f)
    if tok.get("refresh_token"):
        old["refresh_token"] = tok["refresh_token"]
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(old, f)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def get_access_token():
    cid, csecret = load_client()
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, encoding="utf-8") as f:
            rt = json.load(f).get("refresh_token")
        if rt:
            tok = post_form("https://oauth2.googleapis.com/token", {
                "client_id": cid, "client_secret": csecret, "refresh_token": rt, "grant_type": "refresh_token"})
            if "access_token" in tok:
                return tok["access_token"]
            log("Gespeicherter Login abgelaufen - bitte neu anmelden.")
    return login_browser(cid, csecret)


# --------------------------------------------------------------- Upload ---

def read_meta(video, kind):
    """Titel, Beschreibung, Tags aus <video>.txt oder Standard."""
    base = os.path.splitext(video)[0]
    txt = base + ".txt"
    streamer = os.path.basename(os.path.dirname(video)) if kind == "short" else ""
    name = os.path.basename(base)
    clean_name = re.sub(r"\s*\[[^\]]*\]$", "", re.sub(r"^\d{4}-\d{2}-\d{2} \d{2}-\d{2} - ", "", name)).strip()
    if kind == "short":
        title = f"{streamer} bei GTA 6 😂 #shorts #gta6"
        desc = (f"🎥 Credit: https://twitch.tv/{streamer}\n"
                f"Folgt {streamer} auf Twitch für mehr!\n\n#gta6 #gta #shorts #twitch #{streamer}")
        tags = DEFAULT_TAGS_SHORT + [streamer]
    else:
        title = clean_name or "GTA 6 Gameplay"
        desc = "GTA 6 Gameplay\n\n#gta6 #gta #gameplay"
        tags = list(DEFAULT_TAGS_LONG)
    if os.path.exists(txt):
        with open(txt, encoding="utf-8") as f:
            raw = f.read()
        head, _, body = raw.partition("---")
        m = re.search(r"^TITEL:\s*(.+)$", head, re.M)
        t = re.search(r"^TAGS:\s*(.+)$", head, re.M)
        if m:
            title = m.group(1).strip()
        if t:
            tags = [x.strip() for x in t.group(1).split(",") if x.strip()]
        if body.strip():
            desc = body.strip()
    title = title.replace("<", "").replace(">", "")[:100]
    desc = desc.replace("<", "").replace(">", "")[:4900]
    return title, desc, tags[:30]


def upload(token, path, title, desc, tags):
    size = os.path.getsize(path)
    meta = {"snippet": {"title": title, "description": desc, "tags": tags, "categoryId": "20"},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}}
    init = urllib.request.Request(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        data=json.dumps(meta).encode(), method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/*", "X-Upload-Content-Length": str(size)})
    with urllib.request.urlopen(init, timeout=60) as r:
        location = r.headers["Location"]
    with open(path, "rb") as f:
        put = urllib.request.Request(location, data=f, method="PUT",
                                     headers={"Content-Type": "video/*", "Content-Length": str(size)})
        with urllib.request.urlopen(put, timeout=max(600, size // 200_000)) as r:
            return json.loads(r.read())["id"]


def find_videos():
    todo = []
    if os.path.isdir(SHORTS_DIR):
        for root, _, files in os.walk(SHORTS_DIR):
            for f in sorted(files):
                if f.lower().endswith(VIDEO_EXT) and not f.startswith(".") and ".part." not in f:
                    todo.append((os.path.join(root, f), "short"))
    os.makedirs(LONG_DIR, exist_ok=True)
    for f in sorted(os.listdir(LONG_DIR)):
        if f.lower().endswith(VIDEO_EXT) and not f.startswith("."):
            todo.append((os.path.join(LONG_DIR, f), "long"))
    return [(p, k) for p, k in todo if not os.path.exists(os.path.splitext(p)[0] + ".youtube.txt")]


def main():
    os.chdir(HERE)
    todo = find_videos()
    if not todo:
        log("Nichts Neues zum Hochladen (fertig/ und youtube_lang/ sind schon erledigt).")
        return
    shorts = sum(1 for _, k in todo if k == "short")
    log(f"{len(todo)} Video(s) bereit: {shorts} Shorts, {len(todo) - shorts} lange Videos")
    token = get_access_token()
    ok = 0
    for i, (path, kind) in enumerate(todo, 1):
        title, desc, tags = read_meta(path, kind)
        log(f"[{i}/{len(todo)}] {'Short' if kind == 'short' else 'Langes Video'}: {title}")
        try:
            vid = upload(token, path, title, desc, tags)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            if e.code == 401:
                token = get_access_token()
                try:
                    vid = upload(token, path, title, desc, tags)
                except Exception as e2:
                    log(f"  Fehler: {e2}")
                    continue
            elif "quotaExceeded" in detail or "uploadLimitExceeded" in detail:
                log("  YouTube-Tageslimit erreicht - der Rest kommt beim nächsten Start (morgen).")
                break
            else:
                log(f"  Fehler {e.code}: {detail[:300]}")
                continue
        except Exception as e:
            log(f"  Fehler: {e}")
            continue
        link = f"https://studio.youtube.com/video/{vid}/edit"
        with open(os.path.splitext(path)[0] + ".youtube.txt", "w", encoding="utf-8") as f:
            f.write(f"https://youtu.be/{vid}\n{link}\n")
        log(f"  hochgeladen (privat): {link}")
        ok += 1
    log(f"Fertig: {ok} Video(s) als PRIVAT hochgeladen. Prüfen & veröffentlichen in YouTube Studio:")
    log("  https://studio.youtube.com  ->  Inhalte  ->  Sichtbarkeit auf 'Öffentlich'")
    if ok:
        notify("YouTube-Upload fertig", f"{ok} Video(s) privat hochgeladen - jetzt in YouTube Studio prüfen")


if __name__ == "__main__":
    main()
