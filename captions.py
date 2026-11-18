#!/usr/bin/env python3
"""
Caption-Generator im Creator-Stil (Deutsch + Englisch, YouTube + TikTok)
------------------------------------------------------------------------
Erzeugt für jedes fertige Video eine Caption-Datei <video>.txt:

    TITEL: Hook #shorts                 <- YouTube-Titel
    TAGS: gta6, ...                     <- YouTube-Tags
    ---
    YouTube-Beschreibung (Hook, Credit, Hashtags)

    === TIKTOK ===
    TikTok-Caption (Hook, Credit, 4-5 TikTok-Hashtags)

- Sprache folgt dem Stream: deutsche Streams -> Deutsch, alle anderen -> Englisch.
- Spiel folgt dem Clip: GTA 6 bekommt GTA-Hooks und GTA-Hashtags, andere Spiele neutrale.
- Hooks wechseln sich ab, kürzlich benutzte werden nicht wiederholt.
- Höchstens ein Emoji, oft keins.
- Du kannst jede .txt von Hand ändern. "SKIP" in Zeile 1 = nie posten.

Sprache und Spiel liest das Script aus <clip>.info.json (schreibt der Auto-Clipper).
"""

import json
import os
import random
import re

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY = os.path.join(HERE, ".caption_verlauf.json")

# {s} = Streamer
HOOKS = {
    ("de", "gta"): [
        "{s} war darauf nicht vorbereitet",
        "Niemand hat damit gerechnet",
        "Der Chat ist komplett eskaliert",
        "GTA 6, Tag 1. Genau so.",
        "Warte bis zum Ende",
        "Wie ist das überhaupt möglich?",
        "Die Reaktion sagt alles",
        "Das war nicht geplant",
        "Diese Physik ist einfach unreal",
        "{s} gegen GTA 6: 0:1",
        "Das passiert, wenn man GTA 6 unterschätzt",
        "Bester Moment des Streams",
        "Sowas sieht man nicht jeden Tag",
        "Der Chat konnte es nicht glauben",
        "Rockstar, was ist das?",
        "Das musste geclippt werden",
        "Und plötzlich war alles anders",
        "Ein ganz normaler Tag in Vice City",
        "Vice City hat andere Pläne",
        "So schnell kann es gehen",
    ],
    ("en", "gta"): [
        "{s} was not ready for this",
        "Nobody saw that coming",
        "Chat completely lost it",
        "GTA 6, day one. Exactly like this.",
        "Wait for the end",
        "How is that even possible?",
        "The reaction says it all",
        "That was not the plan",
        "This physics is unreal",
        "{s} vs GTA 6: 0-1",
        "This is what happens when you underestimate GTA 6",
        "Best moment of the stream",
        "You don't see this every day",
        "Chat couldn't believe it",
        "Rockstar, what is this?",
        "This had to be clipped",
        "And suddenly everything changed",
        "Just a normal day in Vice City",
        "Vice City had other plans",
        "That escalated quickly",
    ],
    ("de", "other"): [
        "{s} war darauf nicht vorbereitet",
        "Niemand hat damit gerechnet",
        "Der Chat ist komplett eskaliert",
        "Warte bis zum Ende",
        "Die Reaktion sagt alles",
        "Bester Moment des Streams",
        "Das musste geclippt werden",
        "So schnell kann es gehen",
        "Das war nicht geplant",
        "Sowas sieht man nicht jeden Tag",
    ],
    ("en", "other"): [
        "{s} was not ready for this",
        "Nobody saw that coming",
        "Chat completely lost it",
        "Wait for the end",
        "The reaction says it all",
        "Best moment of the stream",
        "This had to be clipped",
        "That escalated quickly",
        "That was not the plan",
        "You don't see this every day",
    ],
}

EMOJIS = ["😭", "💀", "😂", "🔥", "👀"]

CREDITS = {
    "de": [
        "Clip von {S} – live auf Twitch: twitch.tv/{s}",
        "Credit: {S} auf Twitch → twitch.tv/{s}",
        "Ganzer Stream bei {S}: twitch.tv/{s}",
        "Folgt {S} für mehr: twitch.tv/{s}",
    ],
    "en": [
        "Clip by {S} – live on Twitch: twitch.tv/{s}",
        "Credit: {S} on Twitch → twitch.tv/{s}",
        "Full stream at {S}: twitch.tv/{s}",
        "Follow {S} for more: twitch.tv/{s}",
    ],
}

# YouTube: mehr Tags erlaubt, rotiert
YT_POOL = {
    "gta": ["gtavi", "gta", "vicecity", "gaming", "twitch", "twitchclips", "clips",
            "gta6clips", "rockstargames", "gta6gameplay", "luciaandjason"],
    "other": ["gaming", "twitch", "twitchclips", "clips", "streamer", "funnymoments"],
}

# TikTok: 4-5 Hashtags sind ideal (Spiel-Kern + Streamer + 1 wechselnder + FYP)
TT_CORE = {"gta": ["gta6", "gtavi"], "other": []}
TT_ROTATE = {
    "gta": ["vicecity", "luciaandjason", "gta6clips", "rockstargames", "twitchclips"],
    "other": ["twitchclips", "gaming", "streamer", "clips"],
}
TT_FYP = {"de": "fürdich", "en": "fyp"}


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


def _game_tag(game):
    t = re.sub(r"[^a-z0-9]", "", (game or "").lower())
    return t or "gaming"


def is_gta(game):
    g = (game or "").lower()
    return "grand theft auto vi" in g or "gta 6" in g or "gta6" in g or "gta vi" in g


def norm_lang(lang):
    return "de" if (lang or "").lower().startswith("de") else "en"


def make_caption(streamer, display_name=None, lang="de", game="Grand Theft Auto VI"):
    """Gibt dict mit yt_title, yt_desc, yt_tags, tiktok zurück."""
    s = re.sub(r"[^A-Za-z0-9_]", "", streamer) or "streamer"
    S = display_name or s
    lang = norm_lang(lang)
    kind = "gta" if is_gta(game) else "other"
    h = _load_history()

    pool = HOOKS[(lang, kind)]
    recent = set(h.get("hooks", [])[-12:])
    choices = [x for x in pool if x not in recent] or pool
    tpl = random.choice(choices)
    h["hooks"] = (h.get("hooks", []) + [tpl])[-30:]
    hook = tpl.format(s=S)
    if random.random() < 0.35:
        hook = f"{hook} {random.choice(EMOJIS)}"

    ci = (h.get("credit", -1) + 1) % len(CREDITS[lang])
    h["credit"] = ci
    credit = CREDITS[lang][ci].format(s=s, S=S)
    _save_history(h)

    game_tags = ["gta6"] if kind == "gta" else [_game_tag(game)]

    # YouTube
    extra = random.sample(YT_POOL[kind], 3)
    yt_hashtags = " ".join(f"#{t}" for t in dict.fromkeys([*game_tags, s.lower(), *extra, "shorts"]))
    yt_title = f"{hook} #shorts"
    if len(yt_title) > 100:
        yt_title = hook[:92] + " #shorts"
    yt_desc = f"{hook}\n\n{credit}\n\n{yt_hashtags}"
    base_tags = (["gta6", "gta 6", "gta 6 clips"] if kind == "gta" else [game or "gaming"])
    yt_tags = list(dict.fromkeys([*base_tags, s, S, "twitch clips", *extra]))

    # TikTok
    tt_tags = [*(TT_CORE[kind] or game_tags), s.lower(), random.choice(TT_ROTATE[kind]), TT_FYP[lang]]
    tt_hashtags = " ".join(f"#{t}" for t in dict.fromkeys(tt_tags))
    tiktok = f"{hook}\n\n{credit}\n\n{tt_hashtags}"

    return {"yt_title": yt_title, "yt_desc": yt_desc, "yt_tags": yt_tags, "tiktok": tiktok}


def read_info(path):
    """Liest <video>.info.json (Sprache, Spiel, Streamer), falls vorhanden."""
    p = os.path.splitext(path)[0] + ".info.json"
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_caption_file(video_path, streamer, display_name=None, lang=None, game=None):
    """Legt <video>.txt an (überschreibt keine vorhandene, falls du sie bearbeitet hast)."""
    txt = os.path.splitext(video_path)[0] + ".txt"
    if os.path.exists(txt):
        return txt
    info = read_info(video_path)
    lang = lang or info.get("lang") or "de"
    game = game or info.get("game") or "Grand Theft Auto VI"
    c = make_caption(streamer, display_name or info.get("display_name"), lang, game)
    with open(txt, "w", encoding="utf-8") as f:
        f.write(f"TITEL: {c['yt_title']}\nTAGS: {', '.join(c['yt_tags'])}\n---\n{c['yt_desc']}\n"
                f"\n=== TIKTOK ===\n{c['tiktok']}\n")
    return txt


def tiktok_caption(video_path):
    """TikTok-Text aus der .txt (für die TikTok-Entwürfe)."""
    txt = os.path.splitext(video_path)[0] + ".txt"
    if not os.path.exists(txt):
        return None
    raw = open(txt, encoding="utf-8").read()
    if "=== TIKTOK ===" in raw:
        return raw.split("=== TIKTOK ===", 1)[1].strip()
    return None


if __name__ == "__main__":
    # Vorschau ohne etwas zu speichern:  python3 captions.py papaplatte de
    import sys
    HISTORY = os.devnull
    who = sys.argv[1] if len(sys.argv) > 1 else "papaplatte"
    lg = sys.argv[2] if len(sys.argv) > 2 else "de"
    for _ in range(2):
        c = make_caption(who, lang=lg)
        print(f"YOUTUBE  TITEL: {c['yt_title']}\n{c['yt_desc']}\n\nTIKTOK:\n{c['tiktok']}\n" + "-" * 50)
