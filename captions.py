#!/usr/bin/env python3
"""
Caption-Generator im Creator-Stil
---------------------------------
Erzeugt für jedes fertige Video eine eigene Caption-Datei (<video>.txt):

    TITEL: Hook-Zeile #shorts
    TAGS: gta6, ...
    ---
    Hook-Zeile

    Clip von <Streamer> - live auf Twitch: twitch.tv/<streamer>

    #gta6 #<streamer> ...

- Hooks wechseln sich ab, kürzlich benutzte werden nicht wiederholt.
- Hashtags rotieren (immer #gta6 + Streamer, dazu 3 wechselnde).
- Höchstens ein Emoji pro Caption, oft keins.
- Du kannst jede .txt jederzeit von Hand ändern. Schreibst du in die erste Zeile "SKIP",
  wird das Video nie hochgeladen.
"""

import json
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY = os.path.join(HERE, ".caption_verlauf.json")

# {s} = Streamer-Name. Kurz, direkt, wie ein Creator schreibt.
HOOKS = [
    "{s} war darauf nicht vorbereitet",
    "Niemand hat damit gerechnet",
    "Der Chat ist komplett eskaliert",
    "GTA 6, Tag 1. Genau so.",
    "Warte bis zum Ende",
    "Wie ist das überhaupt möglich?",
    "Die Reaktion sagt alles",
    "{s} hat den Moment seines Lebens",
    "Das war nicht geplant",
    "Ich kann nicht mehr",
    "Diese Physik ist einfach unreal",
    "{s} gegen GTA 6: 0:1",
    "Das passiert, wenn man GTA 6 unterschätzt",
    "Bester Moment des Streams",
    "Sowas sieht man nicht jeden Tag",
    "{s} hat es wirklich versucht",
    "Der Chat konnte es nicht glauben",
    "Rockstar, was ist das?",
    "Das musste geclippt werden",
    "Und plötzlich war alles anders",
    "Ein ganz normaler Tag in Vice City",
    "Vice City hat andere Pläne",
    "So schnell kann es gehen",
    "Keiner hat gesehen, was hinten passiert",
]

# höchstens eins, nur manchmal
EMOJIS = ["😭", "💀", "😂", "🔥", "👀"]

CREDIT_LINES = [
    "Clip von {S} – live auf Twitch: twitch.tv/{s}",
    "Credit: {S} auf Twitch → twitch.tv/{s}",
    "Ganzer Stream bei {S}: twitch.tv/{s}",
    "Folgt {S} für mehr: twitch.tv/{s}",
]

TAG_POOL = ["gtavi", "gta", "vicecity", "gaming", "twitch", "twitchclips", "clips",
            "gta6clips", "streamer", "rockstargames", "gta6gameplay", "funnymoments"]


def _load_history():
    try:
        with open(HISTORY, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"hooks": [], "credit": -1}


def _save_history(h):
    try:
        with open(HISTORY, "w", encoding="utf-8") as f:
            json.dump(h, f)
    except OSError:
        pass


def make_caption(streamer, display_name=None):
    """Gibt (titel, beschreibung, tags) zurück."""
    s = re.sub(r"[^A-Za-z0-9_]", "", streamer) or "streamer"
    S = display_name or s
    h = _load_history()

    recent = set(h.get("hooks", [])[-12:])
    choices = [x for x in HOOKS if x not in recent] or HOOKS
    hook_tpl = random.choice(choices)
    h["hooks"] = (h.get("hooks", []) + [hook_tpl])[-30:]

    hook = hook_tpl.format(s=S)
    if random.random() < 0.4:
        hook = f"{hook} {random.choice(EMOJIS)}"

    ci = (h.get("credit", -1) + 1) % len(CREDIT_LINES)
    h["credit"] = ci
    credit = CREDIT_LINES[ci].format(s=s, S=S)
    _save_history(h)

    extra = random.sample(TAG_POOL, 3)
    hashtags = " ".join(f"#{t}" for t in ["gta6", s.lower(), *extra, "shorts"])

    title = f"{hook} #shorts"
    if len(title) > 100:
        title = hook[:92] + " #shorts"
    desc = f"{hook}\n\n{credit}\n\n{hashtags}"
    tags = ["gta6", "gta 6", s, S, "gta 6 clips", "twitch clips", *extra]
    return title, desc, list(dict.fromkeys(tags))


def write_caption_file(video_path, streamer, display_name=None):
    """Legt <video>.txt an (überschreibt keine vorhandene, falls du sie bearbeitet hast)."""
    txt = os.path.splitext(video_path)[0] + ".txt"
    if os.path.exists(txt):
        return txt
    title, desc, tags = make_caption(streamer, display_name)
    with open(txt, "w", encoding="utf-8") as f:
        f.write(f"TITEL: {title}\nTAGS: {', '.join(tags)}\n---\n{desc}\n")
    return txt


if __name__ == "__main__":
    # Vorschau ohne etwas zu speichern:  python3 captions.py papaplatte
    import sys
    HISTORY = os.devnull
    for _ in range(3):
        t, d, _tags = make_caption(sys.argv[1] if len(sys.argv) > 1 else "papaplatte")
        print(f"TITEL: {t}\n{d}\n" + "-" * 50)
