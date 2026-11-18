#!/usr/bin/env python3
"""
YouTube-Uploader (Shorts + lange Videos)
----------------------------------------
Lädt Videos als PRIVAT auf deinen YouTube-Kanal. Du prüfst sie in YouTube Studio
und stellst sie mit einem Klick auf "Öffentlich".

  Shorts:        alles aus  fertig/<streamer>/   (die zusammengeschnittenen Clips)
  Lange Videos:  alles aus  youtube_lang/         (dein eigenes Gameplay)

Regeln (oben im Code einstellbar): max. 3 Shorts + 1 langes Video pro Tag, max. 1 Short pro
Streamer und Tag, neueste zuerst. Schreib "SKIP" in die erste Zeile der .txt, um ein Video
auszulassen.

  python3 youtube_upload.py            # nach Regeln, privat, mit empfohlenen Zeiten
  python3 youtube_upload.py --planen   # zusätzlich automatisch zu den Zeiten veröffentlichen
  python3 youtube_upload.py --alle     # Regeln ignorieren (alles hochladen)

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
SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
PORT = 8765
REDIRECT = f"http://127.0.0.1:{PORT}"

# ======================= UPLOAD-REGELN (hier anpassen) =======================
MAX_SHORTS_PRO_TAG = 3        # so viele Shorts lädt der Uploader pro Tag höchstens hoch
MAX_LANG_PRO_TAG = 1          # lange Videos pro Tag
MAX_PRO_STREAMER_PRO_TAG = 1  # Abwechslung: max. 1 Short pro Streamer und Tag
POST_ZEITEN = ["12:00", "16:00", "19:00", "22:00"]  # empfohlene Veröffentlichungszeiten
NEUESTE_ZUERST = True         # frische Clips zuerst (wichtig in der Release-Woche)
TAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
# ============================================================================

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
    if kind == "short" and not os.path.exists(txt):
        try:
            sys.path.insert(0, HERE)
            import captions
            captions.write_caption_file(video, streamer)  # liest Sprache/Spiel aus <video>.info.json
        except Exception:
            pass
    if kind == "short":
        title = f"{streamer} bei GTA 6 #shorts"
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
        raw = raw.split("=== TIKTOK ===")[0]
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


def upload(token, path, title, desc, tags, publish_at=None):
    size = os.path.getsize(path)
    status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    if publish_at:
        status["publishAt"] = publish_at  # YouTube veröffentlicht dann automatisch zu dieser Zeit
    meta = {"snippet": {"title": title, "description": desc, "tags": tags, "categoryId": "20"},
            "status": status}
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


def api_get(token, path, params):
    url = "https://www.googleapis.com/youtube/v3/" + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def channel_name(token):
    """Name des Kanals, auf den hochgeladen wird."""
    try:
        items = api_get(token, "channels", {"part": "snippet", "mine": "true"}).get("items", [])
        return items[0]["snippet"]["title"] if items else "(kein Kanal gefunden)"
    except Exception as e:
        return f"(unbekannt: {e})"


def video_info(token, vid):
    try:
        items = api_get(token, "videos", {"part": "snippet,status", "id": vid}).get("items", [])
        if not items:
            return "Video nicht gefunden"
        st, sn = items[0]["status"], items[0]["snippet"]
        extra = st.get("rejectionReason") or st.get("failureReason") or ""
        return (f"Kanal: {sn.get('channelTitle')} | Upload: {st.get('uploadStatus')} | "
                f"Sichtbarkeit: {st.get('privacyStatus')} {extra}").strip()
    except Exception as e:
        return f"(Status unbekannt: {e})"


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


def is_skip(path):
    txt = os.path.splitext(path)[0] + ".txt"
    if os.path.exists(txt):
        with open(txt, encoding="utf-8") as f:
            return f.readline().strip().upper().startswith("SKIP")
    return False


def uploaded_today():
    """Zählt heutige Uploads anhand der .youtube.txt-Marker."""
    today = datetime.now().date()
    shorts, longs, streamers = 0, 0, set()
    for root, _, files in os.walk(HERE):
        for f in files:
            if f.endswith(".youtube.txt"):
                p = os.path.join(root, f)
                if datetime.fromtimestamp(os.path.getmtime(p)).date() == today:
                    if os.path.abspath(root).startswith(os.path.abspath(LONG_DIR)):
                        longs += 1
                    else:
                        shorts += 1
                        streamers.add(os.path.basename(root))
    return shorts, longs, streamers


def apply_rules(todo, ignore_limits=False):
    todo = [(p, k) for p, k in todo if not is_skip(p)]
    todo.sort(key=lambda x: os.path.getmtime(x[0]), reverse=NEUESTE_ZUERST)
    if ignore_limits:
        return todo
    s_done, l_done, used = uploaded_today()
    per = {}
    for st in used:
        per[st] = per.get(st, 0) + 1
    picked, s_left, l_left = [], MAX_SHORTS_PRO_TAG - s_done, MAX_LANG_PRO_TAG - l_done
    for p, k in todo:
        if k == "short":
            st = os.path.basename(os.path.dirname(p))
            if s_left <= 0 or per.get(st, 0) >= MAX_PRO_STREAMER_PRO_TAG:
                continue
            per[st] = per.get(st, 0) + 1
            s_left -= 1
        else:
            if l_left <= 0:
                continue
            l_left -= 1
        picked.append((p, k))
    log(f"Regeln: heute schon {s_done}/{MAX_SHORTS_PRO_TAG} Shorts und {l_done}/{MAX_LANG_PRO_TAG} lange Videos.")
    return picked


def next_slots(n):
    """Nächste freie Posting-Zeiten ab jetzt (heute, sonst morgen)."""
    from datetime import timedelta
    now = datetime.now()
    slots, day = [], 0
    while len(slots) < n and day < 7:
        for t in POST_ZEITEN:
            hh, mm = map(int, t.split(":"))
            dt = (now + timedelta(days=day)).replace(hour=hh, minute=mm, second=0, microsecond=0)
            if dt > now + timedelta(minutes=20):
                slots.append(dt)
                if len(slots) == n:
                    break
        day += 1
    return slots


def main():
    os.chdir(HERE)
    planen = "--planen" in sys.argv
    todo = apply_rules(find_videos(), ignore_limits="--alle" in sys.argv)
    if not todo:
        log("Heute nichts mehr hochzuladen: Tageslimit erreicht oder keine neuen Videos. Morgen geht es weiter.")
        return
    shorts = sum(1 for _, k in todo if k == "short")
    log(f"{len(todo)} Video(s) bereit: {shorts} Shorts, {len(todo) - shorts} lange Videos")
    token = get_access_token()
    ok = 0
    slots = next_slots(len(todo))
    plan = []
    for i, (path, kind) in enumerate(todo, 1):
        title, desc, tags = read_meta(path, kind)
        slot = slots[i - 1] if i - 1 < len(slots) else None
        publish_at = slot.astimezone().isoformat() if (planen and slot) else None
        log(f"[{i}/{len(todo)}] {'Short' if kind == 'short' else 'Langes Video'}: {title}")
        try:
            vid = upload(token, path, title, desc, tags, publish_at)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            if e.code == 401:
                token = get_access_token()
                try:
                    vid = upload(token, path, title, desc, tags, publish_at)
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
            if slot:
                f.write(f"{'geplant' if planen else 'empfohlen'}: {slot:%d.%m. %H:%M}\n")
        log(f"  hochgeladen (privat): {link}")
        if slot:
            plan.append(f"{TAGE[slot.weekday()]} {slot:%H:%M}  {title}")
        ok += 1
    if planen:
        log(f"Fertig: {ok} Video(s) hochgeladen und GEPLANT. YouTube veröffentlicht sie automatisch:")
    else:
        log(f"Fertig: {ok} Video(s) als PRIVAT hochgeladen. Prüfen & veröffentlichen in YouTube Studio")
        log("  (https://studio.youtube.com -> Inhalte -> Sichtbarkeit 'Öffentlich'), am besten zu diesen Zeiten:")
    for line in plan:
        log(f"  {line}")
    if ok:
        notify("YouTube-Upload fertig", f"{ok} Video(s) privat hochgeladen - jetzt in YouTube Studio prüfen")


if __name__ == "__main__":
    main()
