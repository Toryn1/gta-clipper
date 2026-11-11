#!/usr/bin/env python3
"""
GTA 6 Auto-Clipper
------------------
Liest anonym den Chat der grössten GTA-6-Streams mit. Wenn der Chat plötzlich
explodiert (viele Nachrichten, KEKW/LUL/WTF-Spam, "clip it!"), erstellt das
Script automatisch einen Twitch-Clip der letzten ~30 Sekunden.

Nur Python-Standardbibliothek, nichts zu installieren (yt-dlp nur optional).
Speichert nichts ausser den Clips selbst (nur wenn du --download nutzt).

Beispiele:
  python autoclipper.py                       # Top 10 GTA-6-Streams, alle Sprachen
  python autoclipper.py --top 15 --lang de    # Top 15 deutsche Streams
  python autoclipper.py --channels papaplatte,trymacs
  python autoclipper.py --dry-run             # nur anzeigen, keine Clips erstellen (zum Testen)
  python autoclipper.py --download            # Clips gleich mit yt-dlp runterladen
"""

import argparse
import http.server
import json
import os
import random
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from collections import deque
from datetime import datetime

# Optional: Client-ID hier fest eintragen (oder --client-id / Umgebungsvariable TWITCH_CLIENT_ID)
CLIENT_ID = "p25ksqdjsh9napr9swapfaehfio7db"

REDIRECT = "http://localhost:3000"
SCOPE = "clips:edit"
GAME_NAME = "Grand Theft Auto VI"

# Wörter/Emotes, die auf einen Highlight-Moment hindeuten
HYPE_RE = re.compile(
    r"\b(KEKW|OMEGALUL|LULW?|ICANT|LMF?AO+|LOL+|WTF+|POG\w*|HOLY|NO\s?WAY|W|L|XD+|HAHA\w*|"
    r"JAJA\w*|SHEESH|BRUH+|AYO+|DIESOFCRINGE|Sadge|monkaS|monkaW|Aware|Clueless|NAHH+)\b"
    r"|💀|😂|🤣|😭|\?{3,}|!{3,}",
    re.IGNORECASE,
)
CLIP_RE = re.compile(r"\bclip\w*\b", re.IGNORECASE)


def now_str():
    return datetime.now().strftime("%H:%M:%S")


def log(msg):
    print(f"[{now_str()}] {msg}", flush=True)


# ---------------------------------------------------------------- Login ----

LOGIN_PAGE = b"""<!doctype html><meta charset=utf-8><title>Auto-Clipper Login</title>
<body style="font-family:system-ui,sans-serif;background:#0e0e10;color:#eee;padding:40px">
<h2>GTA 6 Auto-Clipper</h2><p id=m>Einen Moment...</p><script>
const p=new URLSearchParams(location.hash.slice(1)), t=p.get('access_token');
history.replaceState(null,'','/');
if(t){fetch('/token?t='+encodeURIComponent(t)).then(()=>{
  document.getElementById('m').textContent='Fertig! Du kannst diesen Tab schliessen und zum Terminal zurueck.'})}
else{document.getElementById('m').textContent='Kein Login erhalten: '+
  (new URLSearchParams(location.search).get('error_description')||'unbekannter Fehler')}
</script>"""


def get_token(client_id):
    """Öffnet den Twitch-Login im Browser und fängt das Token auf localhost:3000 ab."""
    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path == "/token":
                got["t"] = urllib.parse.parse_qs(u.query).get("t", [None])[0]
                self.send_response(204)
                self.end_headers()
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(LOGIN_PAGE)

        def log_message(self, *a):
            pass

    try:
        srv = http.server.HTTPServer(("127.0.0.1", 3000), Handler)
    except OSError:
        sys.exit("Port 3000 ist besetzt. Läuft noch der Clip-Finder-Server? Kurz stoppen (Strg+C), "
                 "einloggen, danach kannst du ihn wieder starten.")
    srv.timeout = 1
    url = "https://id.twitch.tv/oauth2/authorize?" + urllib.parse.urlencode(
        {"client_id": client_id, "redirect_uri": REDIRECT, "response_type": "token", "scope": SCOPE})
    log("Öffne Twitch-Login im Browser...")
    log(f"Falls sich nichts öffnet, diesen Link aufrufen:\n  {url}")
    webbrowser.open(url)
    deadline = time.time() + 300
    while not got.get("t") and time.time() < deadline:
        srv.handle_request()
    srv.server_close()
    if not got.get("t"):
        sys.exit("Kein Login innerhalb von 5 Minuten. Abbruch.")
    return got["t"]


# ------------------------------------------------------------ Twitch API ---

class Twitch:
    def __init__(self, client_id):
        self.cid = client_id
        self.token = None
        self.user = None
        self.login()

    def login(self):
        self.token = get_token(self.cid)
        req = urllib.request.Request("https://id.twitch.tv/oauth2/validate",
                                     headers={"Authorization": "OAuth " + self.token})
        with urllib.request.urlopen(req, timeout=15) as r:
            info = json.loads(r.read())
        self.user = info.get("login")
        if SCOPE not in info.get("scopes", []):
            sys.exit("Dem Login fehlt die Berechtigung 'clips:edit'. Bitte neu starten und zustimmen.")
        log(f"Eingeloggt als {self.user}")

    def req(self, method, path, params=None, _retry=True):
        url = "https://api.twitch.tv/helix/" + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        r = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None,
                                   headers={"Client-Id": self.cid, "Authorization": "Bearer " + self.token})
        try:
            with urllib.request.urlopen(r, timeout=15) as resp:
                body = resp.read()
                return resp.status, (json.loads(body) if body else {})
        except urllib.error.HTTPError as e:
            if e.code == 401 and _retry:
                log("Login abgelaufen, bitte im Browser neu bestätigen...")
                self.login()
                return self.req(method, path, params, _retry=False)
            try:
                data = json.loads(e.read())
            except Exception:
                data = {}
            return e.code, data
        except (urllib.error.URLError, socket.timeout) as e:
            return 0, {"message": str(e)}

    def game_id(self, name):
        s, d = self.req("GET", "games", {"name": name})
        if s == 200 and d.get("data"):
            return d["data"][0]["id"], d["data"][0]["name"]
        s, d = self.req("GET", "search/categories", {"query": name, "first": 5})
        if s == 200 and d.get("data"):
            return d["data"][0]["id"], d["data"][0]["name"]
        sys.exit(f"Spiel '{name}' nicht gefunden.")

    def top_streams(self, game_id, n, lang=None, exclude=()):
        params = {"game_id": game_id, "first": 100, "type": "live"}
        if lang:
            params["language"] = lang
        s, d = self.req("GET", "streams", params)
        if s != 200:
            log(f"Konnte Streams nicht laden ({s}): {d.get('message', '')}")
            return {}
        out = {}
        for st in d.get("data", []):
            if st["user_login"].lower() in exclude:
                continue
            out[st["user_login"].lower()] = {"id": st["user_id"], "viewers": st["viewer_count"]}
            if len(out) >= n:
                break
        return out

    def users(self, logins):
        s, d = self.req("GET", "users", {"login": logins})
        if s != 200:
            sys.exit(f"Konnte Kanäle nicht laden ({s}): {d.get('message', '')}")
        return {u["login"].lower(): {"id": u["id"], "viewers": None} for u in d.get("data", [])}

    def create_clip(self, broadcaster_id):
        return self.req("POST", "clips", {"broadcaster_id": broadcaster_id})


# ------------------------------------------------------------- Chat (IRC) --

class Chat:
    """Anonymer Twitch-Chat-Leser (kein Login nötig, schreibt nie etwas in den Chat)."""
    LINE_RE = re.compile(r"^:\S+ PRIVMSG #(\S+) :(.*)$")

    def __init__(self):
        self.channels = set()
        self.sock = None
        self.buf = ""
        self.connect()

    def _send(self, line):
        self.sock.sendall((line + "\r\n").encode("utf-8"))

    def connect(self):
        while True:
            try:
                self.sock = socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=10)
                self.sock.settimeout(1.0)
                self._send("PASS SCHMOOPIIE")
                self._send(f"NICK justinfan{random.randint(10000, 99999)}")
                self.buf = ""
                for ch in list(self.channels):
                    self._send(f"JOIN #{ch}")
                    time.sleep(0.6)
                return
            except OSError as e:
                log(f"Chat-Verbindung fehlgeschlagen ({e}), neuer Versuch in 10s...")
                time.sleep(10)

    def join(self, ch):
        if ch not in self.channels:
            self.channels.add(ch)
            self._send(f"JOIN #{ch}")
            time.sleep(0.6)  # Twitch-Limit für Joins

    def part(self, ch):
        if ch in self.channels:
            self.channels.discard(ch)
            self._send(f"PART #{ch}")

    def read(self):
        """Gibt alle neuen (kanal, nachricht)-Paare zurück, wartet max. 1 Sekunde."""
        try:
            data = self.sock.recv(65536)
        except socket.timeout:
            return []
        except OSError:
            data = b""
        if not data:
            log("Chat-Verbindung getrennt, verbinde neu...")
            self.connect()
            return []
        self.buf += data.decode("utf-8", errors="replace")
        *lines, self.buf = self.buf.split("\r\n")
        out = []
        for line in lines:
            if line.startswith("PING"):
                self._send("PONG" + line[4:])
                continue
            m = self.LINE_RE.match(line)
            if m:
                out.append((m.group(1).lower(), m.group(2)))
        return out


# --------------------------------------------------------- Hype-Erkennung --

class Detector:
    """
    Pro Kanal: zählt einen "Hype-Score" im gleitenden Fenster (Standard 10s).
    Jede Nachricht = 1 Punkt, Hype-Wörter/Emotes = +1 Punkt.
    Vergleicht mit dem normalen Chat-Tempo des Kanals (langsam mitlaufender Durchschnitt).
    """

    def __init__(self, window=10, factor=2.2, min_score=20, clip_votes=4, cooldown=90, warmup=60):
        self.window, self.factor, self.min_score = window, factor, min_score
        self.clip_votes, self.cooldown, self.warmup = clip_votes, cooldown, warmup
        self.events = deque()
        self.baseline = None
        self.started = time.time()
        self.last_clip = 0.0
        self.alpha = 0.02  # ~50 Sekunden Gedächtnis

    def add(self, t, msg):
        score = 1.0 + (1.0 if HYPE_RE.search(msg) else 0.0)
        self.events.append((t, score, bool(CLIP_RE.search(msg))))

    def tick(self, now):
        while self.events and self.events[0][0] < now - self.window:
            self.events.popleft()
        score = sum(e[1] for e in self.events)
        votes = sum(1 for e in self.events if e[2])
        if self.baseline is None:
            self.baseline = score
        base = max(self.baseline, 3.0)
        ready = now - self.started >= self.warmup
        hot = ready and score >= self.min_score and score >= base * self.factor
        voted = ready and votes >= self.clip_votes
        if not hot:
            self.baseline = self.baseline * (1 - self.alpha) + score * self.alpha
        if (hot or voted) and now - self.last_clip >= self.cooldown:
            self.last_clip = now
            reason = (f"Chat x{score / base:.1f} ({score:.0f} vs. normal {base:.0f})" if hot
                      else f"{votes}x 'clip' im Chat")
            return True, reason
        return False, ""


# ------------------------------------------------------------------ Main ---

def download(url, channel, outdir):
    time.sleep(20)  # Twitch braucht ein paar Sekunden, bis der Clip fertig ist
    tmpl = os.path.join(outdir, f"{channel} - %(title)s [%(id)s].%(ext)s")
    r = subprocess.run(["yt-dlp", "-q", "--no-warnings", "-o", tmpl, url], capture_output=True, text=True)
    if r.returncode == 0:
        log(f"  heruntergeladen: {channel} ({url})")
    else:
        log(f"  Download fehlgeschlagen für {url}: {r.stderr.strip()[:200]}")


def main():
    ap = argparse.ArgumentParser(description="GTA 6 Auto-Clipper")
    ap.add_argument("--client-id", default=os.environ.get("TWITCH_CLIENT_ID", CLIENT_ID))
    ap.add_argument("--game", default=GAME_NAME)
    ap.add_argument("--top", type=int, default=10, help="Anzahl grösste Streams (Standard 10, max. ~20)")
    ap.add_argument("--lang", default=None, help="Sprache der Streams, z.B. de oder en")
    ap.add_argument("--channels", default=None, help="Feste Kanäle, kommagetrennt (statt --top)")
    ap.add_argument("--exclude", default="", help="Kanäle, die ignoriert werden sollen, kommagetrennt")
    ap.add_argument("--factor", type=float, default=2.2, help="Wie viel lauter als normal der Chat sein muss")
    ap.add_argument("--min-score", type=float, default=20, help="Mindest-Score im Fenster (gegen kleine Chats)")
    ap.add_argument("--clip-votes", type=int, default=4, help="Ab so vielen 'clip'-Nachrichten wird geclippt")
    ap.add_argument("--cooldown", type=int, default=90, help="Sekunden Pause pro Kanal nach einem Clip")
    ap.add_argument("--dry-run", action="store_true", help="Nur anzeigen, keine Clips erstellen")
    ap.add_argument("--download", action="store_true", help="Clips automatisch mit yt-dlp runterladen")
    ap.add_argument("--out", default="clips", help="Ordner für Downloads")
    a = ap.parse_args()

    if not a.client_id:
        a.client_id = input("Twitch Client-ID: ").strip()
    if a.download:
        if not shutil.which("yt-dlp"):
            sys.exit("--download braucht yt-dlp (https://github.com/yt-dlp/yt-dlp). Installieren oder ohne --download starten.")
        os.makedirs(a.out, exist_ok=True)

    tw = Twitch(a.client_id)
    game_id, game_name = tw.game_id(a.game)
    log(f"Spiel: {game_name} (ID {game_id})")
    exclude = {x.strip().lower() for x in a.exclude.split(",") if x.strip()}

    def pick_channels():
        if a.channels:
            return tw.users([c.strip().lower() for c in a.channels.split(",") if c.strip()])
        return tw.top_streams(game_id, min(a.top, 20), a.lang, exclude)

    chat = Chat()
    targets, dets = {}, {}

    def refresh():
        nonlocal targets
        new = pick_channels()
        if not new and not targets:
            log("Gerade keine passenden Live-Streams gefunden, versuche es in 2 Min. nochmal.")
        for ch in set(targets) - set(new):
            chat.part(ch)
            dets.pop(ch, None)
            log(f"- verlasse {ch}")
        for ch, info in new.items():
            if ch not in targets:
                chat.join(ch)
                dets[ch] = Detector(factor=a.factor, min_score=a.min_score,
                                    clip_votes=a.clip_votes, cooldown=a.cooldown)
                v = f" ({info['viewers']:,} Zuschauer)".replace(",", "'") if info.get("viewers") else ""
                log(f"+ beobachte {ch}{v}")
        targets = new

    refresh()
    log("Läuft! Die ersten 60 Sekunden lernt das Script das normale Chat-Tempo. Stoppen mit Strg+C.")
    if a.dry_run:
        log("TESTMODUS: Es werden keine echten Clips erstellt.")

    made, last_tick, last_status = 0, 0.0, time.time()
    last_refresh = time.time()
    msgs = 0
    try:
        while True:
            for ch, msg in chat.read():
                d = dets.get(ch)
                if d:
                    d.add(time.time(), msg)
                    msgs += 1
            now = time.time()
            if now - last_tick >= 1:
                last_tick = now
                for ch, d in list(dets.items()):
                    trig, reason = d.tick(now)
                    if not trig:
                        continue
                    if a.dry_run:
                        log(f"*** WÜRDE CLIPPEN: {ch} | {reason}")
                        made += 1
                        continue
                    s, data = tw.create_clip(targets[ch]["id"])
                    if s == 202 and data.get("data"):
                        cid = data["data"][0]["id"]
                        url = f"https://clips.twitch.tv/{cid}"
                        made += 1
                        log(f"*** CLIP #{made}: {ch} | {reason}\n    {url}")
                        if a.download:
                            threading.Thread(target=download, args=(url, ch, a.out), daemon=True).start()
                    elif s == 403:
                        log(f"Clip bei {ch} nicht erlaubt (Streamer hat Clips eingeschränkt, z.B. nur für Follower/Subs).")
                    elif s == 404:
                        log(f"{ch} ist offline.")
                    elif s == 429:
                        log("Zu viele Clips in kurzer Zeit (Twitch-Limit). Kurz Pause...")
                    else:
                        log(f"Clip bei {ch} fehlgeschlagen ({s}): {data.get('message', '')}")
            if now - last_status >= 60:
                log(f"Status: {len(dets)} Kanäle, {msgs} Chat-Nachrichten/Min., {made} Clips bisher")
                msgs, last_status = 0, now
            if not a.channels and (now - last_refresh >= 600 or (not targets and now - last_refresh >= 120)):
                last_refresh = now
                refresh()
    except KeyboardInterrupt:
        log(f"Beendet. {made} Clips in dieser Sitzung.")


if __name__ == "__main__":
    main()
