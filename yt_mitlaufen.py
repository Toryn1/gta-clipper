#!/usr/bin/env python3
"""
YouTube läuft mit
-----------------
Schaut jede Minute, welche Clips Claude für TikTok ausgewählt hat (Marker <video>.tiktok.txt),
und lädt genau diese PRIVAT auf alle verbundenen YouTube-Kanäle hoch.
Titel/Beschreibung kommen aus <video>.txt (YouTube-Teil).
Du bekommst pro Upload eine Mac-Mitteilung und stellst das Video in YouTube Studio auf "Öffentlich".

Limit: höchstens MAX_PRO_TAG Uploads pro Kanal und Tag.
"""

import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
import youtube_upload as yt  # noqa: E402

MAX_PRO_TAG = 10
FERTIG = os.path.join(HERE, "fertig")


def chosen_videos():
    """Videos mit .tiktok.txt-Marker (= von Claude ausgewählt), älteste zuerst."""
    out = []
    for root, _, files in os.walk(FERTIG):
        for f in files:
            if f.endswith(".tiktok.txt"):
                base = os.path.join(root, f[: -len(".tiktok.txt")])
                for ext in (".mp4", ".mov"):
                    if os.path.exists(base + ext):
                        out.append(base + ext)
    return sorted(out, key=os.path.getmtime)


def uploads_today():
    today = datetime.now().date()
    n = 0
    for root, _, files in os.walk(FERTIG):
        for f in files:
            if f.endswith(yt.MARKER):
                p = os.path.join(root, f)
                if datetime.fromtimestamp(os.path.getmtime(p)).date() == today:
                    with open(p, encoding="utf-8") as fh:
                        if fh.read(5) == "https":
                            n += 1
    return n


def main():
    if not os.path.exists(yt.SECRET_FILE):
        sys.exit("client_secret.json fehlt - erst YouTube einrichten.")
    kanaele = yt.connected_channels()
    if not kanaele:
        sys.exit("Noch kein YouTube-Kanal verbunden. Erst 'YouTube POSTEN - StableRonaldo' bzw. "
                 "'YouTube Kanal 2 VERBINDEN' starten.")
    tokens, namen = {}, {}
    for k in kanaele:
        yt.set_kanal(k)
        tokens[k] = (yt.get_access_token(), time.time())
        namen[k] = yt.channel_name(tokens[k][0])
        yt.log(f"Kanal {k}: {namen[k]}")
    yt.log("Läuft mit: Sobald Claude einen Clip für TikTok auswählt, kommt er hier privat auf YouTube.")
    yt.log("Stoppen mit Ctrl + C.")
    start = time.time()
    while True:
        for k in kanaele:
            yt.set_kanal(k)
            # Login alle 45 Min. auffrischen (Google-Zugang gilt 1 Std.)
            if time.time() - tokens[k][1] > 45 * 60:
                tokens[k] = (yt.get_access_token(), time.time())
            for v in chosen_videos():
                base = os.path.splitext(v)[0]
                if os.path.exists(base + yt.MARKER):
                    continue
                # Clips der letzten 3 Stunden nachholen, ältere nicht
                if os.path.getmtime(base + ".tiktok.txt") < start - 3 * 3600:
                    open(base + yt.MARKER, "w").write("übersprungen (vor dem Start ausgewählt)\n")
                    continue
                if uploads_today() >= MAX_PRO_TAG:
                    break
                title, desc, tags = yt.read_meta(v, "short")
                try:
                    vid = yt.upload(tokens[k][0], v, title, desc, tags)
                except Exception as e:
                    yt.log(f"Kanal {k}: Fehler bei {os.path.basename(v)}: {e}")
                    continue
                link = f"https://studio.youtube.com/video/{vid}/edit"
                with open(base + yt.MARKER, "w", encoding="utf-8") as f:
                    f.write(f"https://youtu.be/{vid}\n{link}\n")
                yt.log(f"Kanal {k} ({namen[k]}): privat hochgeladen - {title}\n    {link}")
                yt.notify(f"YouTube {namen[k]}: bereit zum Posten",
                          f"{title[:60]} - in Studio auf Öffentlich stellen")
        time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        yt.log("Beendet.")
