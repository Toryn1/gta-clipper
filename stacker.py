#!/usr/bin/env python3
"""
Clip-Zusammenschnitt fürs Hochformat (TikTok / Shorts / Reels)
--------------------------------------------------------------
Oben: der Streamer-Clip   |   Unten: dein eigenes Gameplay
Ergebnis: 1080x1920 (9:16), ganzes Clip-Bild mit Blur-Hintergrund, Ton vom Streamer-Clip, Credit "twitch.tv/<streamer>" in der Mitte.

  python3 stacker.py                  # schneidet alle neuen Clips aus clips/<streamer>/ zusammen
  python3 stacker.py --alle-neu       # macht auch schon geschnittene nochmal

Gameplay-Videos legst du in den Ordner "gameplay" (mp4/mov). Bei mehreren wird zufällig gewählt,
und es wird jedes Mal eine andere Stelle genommen.
Fertige Videos landen in fertig/<streamer>/.
"""

import os
import platform
import random
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CLIPS_DIR = os.path.join(HERE, "clips")
GAMEPLAY_DIR = os.path.join(HERE, "gameplay")
OUT_DIR = os.path.join(HERE, "fertig")
BIN_DIR = os.path.join(HERE, "bin")
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".mkv", ".webm")

W, HALF = 1080, 960  # Breite, Höhe pro Hälfte -> 1080x1920

FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ------------------------------------------------------------- ffmpeg ---

def find_ffmpeg():
    """Sucht ffmpeg; fehlt es (Mac), wird die offizielle Einzeldatei einmalig nach bin/ geladen."""
    for c in (shutil.which("ffmpeg"), os.path.join(BIN_DIR, "ffmpeg"),
              "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if c and os.path.exists(c):
            return c
    if sys.platform != "darwin":
        log("ffmpeg fehlt. Bitte installieren (https://ffmpeg.org).")
        return None
    arm = platform.machine().lower() in ("arm64", "aarch64")
    urls = [
        f"https://ffmpeg.martin-riedl.de/redirect/latest/macos/{'arm64' if arm else 'amd64'}/release/ffmpeg.zip",
        "https://evermeet.cx/ffmpeg/getrelease/zip",
    ]
    os.makedirs(BIN_DIR, exist_ok=True)
    target = os.path.join(BIN_DIR, "ffmpeg")
    zpath = os.path.join(BIN_DIR, "ffmpeg.zip")
    for url in urls:
        try:
            log("ffmpeg fehlt - lade es einmalig herunter (ca. 30-80 MB)...")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 gta-clipper"})
            with urllib.request.urlopen(req, timeout=120) as r, open(zpath, "wb") as f:
                shutil.copyfileobj(r, f)
            with zipfile.ZipFile(zpath) as z:
                member = next(n for n in z.namelist() if os.path.basename(n) == "ffmpeg")
                with z.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            os.chmod(target, 0o755)
            os.remove(zpath)
            log(f"ffmpeg bereit: {target}")
            return target
        except Exception as e:
            log(f"  Quelle nicht erreichbar ({e}), versuche die nächste...")
    log("ffmpeg konnte nicht geladen werden. Alternative: Terminal -> brew install ffmpeg")
    return None


def duration(ffmpeg, path):
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def gameplay_files():
    if not os.path.isdir(GAMEPLAY_DIR):
        return []
    return [os.path.join(GAMEPLAY_DIR, f) for f in sorted(os.listdir(GAMEPLAY_DIR))
            if f.lower().endswith(VIDEO_EXT) and not f.startswith(".")]


# -------------------------------------------------------------- Schnitt ---

def make_video(clip_path, streamer, out_path, ffmpeg=None):
    """Erstellt das 9:16-Video. Gibt den Pfad zurück oder None."""
    ffmpeg = ffmpeg or find_ffmpeg()
    gps = gameplay_files()
    if not ffmpeg:
        return None
    if not gps:
        log(f"Kein Gameplay im Ordner {GAMEPLAY_DIR} - bitte ein Video hineinlegen.")
        return None

    d = duration(ffmpeg, clip_path) or 30.0
    gp = random.choice(gps)
    g = duration(ffmpeg, gp)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    gp_input = []
    if g > d + 1:
        gp_input = ["-ss", f"{random.uniform(0, g - d - 0.5):.2f}", "-i", gp]
    else:
        gp_input = ["-stream_loop", "-1", "-i", gp]  # Gameplay zu kurz -> wiederholen

    # Oben: ganzes Clip-Bild (nichts abgeschnitten), Lücken mit unscharfer Version gefüllt (Layout B)
    base = (f"[0:v]split[c1][c2];"
            f"[c1]scale={W}:{HALF}:force_original_aspect_ratio=increase,crop={W}:{HALF},"
            f"boxblur=20:2,eq=brightness=-0.15,setsar=1[bg];"
            f"[c2]scale={W}:{HALF}:force_original_aspect_ratio=decrease:flags=lanczos,setsar=1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30[top];"
            f"[1:v]scale={W}:{HALF}:force_original_aspect_ratio=increase,crop={W}:{HALF},setsar=1,fps=30[bot];"
            f"[top][bot]vstack=inputs=2,format=yuv420p")
    font = next((f for f in FONTS if os.path.exists(f)), None)
    credit = re.sub(r"[^A-Za-z0-9_]", "", streamer)
    filters = []
    if font and credit:
        filters.append(base + f"[v0];[v0]drawtext=fontfile='{font}':text='twitch.tv/{credit}':"
                              f"fontsize=46:fontcolor=white:borderw=5:bordercolor=black:"
                              f"x=(w-tw)/2:y={HALF}-th-22[v]")
    filters.append(base + "[v]")  # Fallback ohne Text

    tmp = out_path + ".part.mp4"
    for fg in filters:
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", clip_path, *gp_input,
               "-filter_complex", fg, "-map", "[v]", "-map", "0:a?",
               "-t", f"{d:.2f}", "-c:v", "libx264", "-preset", "fast", "-crf", "18",
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", tmp]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            os.replace(tmp, out_path)
            try:
                sys.path.insert(0, HERE)
                import captions
                info_src = os.path.splitext(clip_path)[0] + ".info.json"
                if os.path.exists(info_src):  # Infos mit ins fertige Video übernehmen
                    shutil.copyfile(info_src, os.path.splitext(out_path)[0] + ".info.json")
                captions.write_caption_file(out_path, streamer)
            except Exception as e:
                log(f"(Caption konnte nicht erstellt werden: {e})")
            return out_path
        last_err = r.stderr.strip()[-300:]
    if os.path.exists(tmp):
        os.remove(tmp)
    log(f"Zusammenschnitt fehlgeschlagen: {last_err}")
    return None


def out_path_for(clip_path, streamer):
    """Spiegelt die Ordner: clips/GTA 6/<streamer>/x.mp4 -> fertig/GTA 6/<streamer>/x.mp4"""
    name = os.path.splitext(os.path.basename(clip_path))[0] + ".mp4"
    try:
        rel = os.path.relpath(os.path.dirname(os.path.abspath(clip_path)), CLIPS_DIR)
    except ValueError:
        rel = streamer
    if rel.startswith(".."):
        rel = streamer
    return os.path.join(OUT_DIR, rel, name)


def make_for_clip(clip_path, streamer):
    """Für den Auto-Clipper: einen frisch geladenen Clip direkt schneiden."""
    return make_video(clip_path, streamer, out_path_for(clip_path, streamer))


def process_all(redo=False):
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return
    if not gameplay_files():
        log(f"Kein Gameplay gefunden. Leg ein Video in: {GAMEPLAY_DIR}")
        return
    if not os.path.isdir(CLIPS_DIR):
        log("Noch keine Clips im Ordner 'clips'.")
        return
    todo = []
    for root, _, files in sorted(os.walk(CLIPS_DIR)):
        streamer = os.path.basename(root)
        for f in sorted(files):
            if f.lower().endswith(VIDEO_EXT) and not f.startswith(".") and ".part" not in f:
                src = os.path.join(root, f)
                dst = out_path_for(src, streamer)
                if redo or not os.path.exists(dst):
                    todo.append((src, streamer, dst))
    if not todo:
        log("Alles schon geschnitten - keine neuen Clips.")
        return
    log(f"{len(todo)} Clip(s) werden zusammengeschnitten...")
    ok = 0
    for i, (src, streamer, dst) in enumerate(todo, 1):
        log(f"[{i}/{len(todo)}] {streamer}: {os.path.basename(src)}")
        if make_video(src, streamer, dst, ffmpeg):
            ok += 1
    log(f"Fertig: {ok} Video(s) in {OUT_DIR}")


if __name__ == "__main__":
    os.chdir(HERE)
    process_all(redo="--alle-neu" in sys.argv)
