#!/usr/bin/env python3
"""
Posten mit Freigabe
-------------------
1. Wählt nach den Upload-Regeln die nächsten Videos aus (siehe youtube_upload.py).
2. Zeigt dir jedes Video (Vorschau) + Caption. Du entscheidest:
      j = Go, posten      n = nie posten (SKIP)      s = später entscheiden
      b = Caption bearbeiten (öffnet TextEdit), danach nochmal fragen
3. Freigegebene Videos:
      YouTube: werden privat hochgeladen und automatisch zu den Posting-Zeiten veröffentlicht.
      TikTok:  werden für Entwürfe vorgemerkt. Schreib danach Claude "TikTok-Entwürfe",
               dann landen sie als Entwurf in deiner TikTok-App und du postest von dort.

Nichts wird ohne dein "j" hochgeladen.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import youtube_upload as yt  # noqa: E402

LINE = "─" * 60


def base(path):
    return os.path.splitext(path)[0]


def is_approved(path):
    return os.path.exists(base(path) + ".freigabe")


def preview(path):
    """Mac: Schnellvorschau (schliessen mit Leertaste/Esc). Sonst Standard-Player."""
    if sys.platform == "darwin":
        subprocess.run(["qlmanage", "-p", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.startfile(path)  # Windows
        except AttributeError:
            subprocess.run(["xdg-open", path])


def edit_caption(path, kind):
    txt = base(path) + ".txt"
    if not os.path.exists(txt):
        title, desc, tags = yt.read_meta(path, kind)
        with open(txt, "w", encoding="utf-8") as f:
            f.write(f"TITEL: {title}\nTAGS: {', '.join(tags)}\n---\n{desc}\n")
    if sys.platform == "darwin":
        subprocess.run(["open", "-e", txt])
    input("   Caption in TextEdit ändern, SPEICHERN (Cmd+S), dann hier Enter drücken... ")


def mark_skip(path):
    txt = base(path) + ".txt"
    old = open(txt, encoding="utf-8").read() if os.path.exists(txt) else ""
    with open(txt, "w", encoding="utf-8") as f:
        f.write("SKIP (von dir abgelehnt)\n" + old)


def approved_today():
    """Zählt heutige Freigaben (gilt für YouTube und TikTok gemeinsam)."""
    from datetime import datetime
    today = datetime.now().date()
    shorts, longs, streamers = 0, 0, []
    for root, _, files in os.walk(HERE):
        for f in files:
            if f.endswith(".freigabe"):
                p = os.path.join(root, f)
                if datetime.fromtimestamp(os.path.getmtime(p)).date() == today:
                    if os.path.abspath(root).startswith(os.path.abspath(yt.LONG_DIR)):
                        longs += 1
                    else:
                        shorts += 1
                        streamers.append(os.path.basename(root))
    return shorts, longs, streamers


def candidates():
    """Alle offenen Videos nach Regeln sortiert (ohne Limit) + was heute noch geht."""
    todo = [(p, k) for p, k in yt.find_videos() if not yt.is_skip(p) and not is_approved(p)]
    todo.sort(key=lambda x: os.path.getmtime(x[0]), reverse=yt.NEUESTE_ZUERST)
    s_done, l_done, used = approved_today()
    return todo, yt.MAX_SHORTS_PRO_TAG - s_done, yt.MAX_LANG_PRO_TAG - l_done, used, s_done, l_done


def review():
    todo, s_left, l_left, used, s_done, l_done = candidates()
    print(f"\nHeute schon geplant: {s_done}/{yt.MAX_SHORTS_PRO_TAG} Shorts, {l_done}/{yt.MAX_LANG_PRO_TAG} lange Videos.")
    if (s_left <= 0 and l_left <= 0) or not todo:
        print("Heute nichts mehr freizugeben (Tageslimit erreicht oder keine neuen Videos).")
        return []
    per = {}
    for st in used:
        per[st] = per.get(st, 0) + 1
    approved = []
    for path, kind in todo:
        if kind == "short":
            st = os.path.basename(os.path.dirname(path))
            if s_left <= 0 or per.get(st, 0) >= yt.MAX_PRO_STREAMER_PRO_TAG:
                continue
        elif l_left <= 0:
            continue
        while True:
            title, desc, _tags = yt.read_meta(path, kind)
            print(f"\n{LINE}\n{'SHORT' if kind == 'short' else 'LANGES VIDEO'}: {os.path.basename(path)}")
            print(f"TITEL: {title}\n\n{desc}\n{LINE}")
            print("Vorschau öffnet sich ... (schliessen mit Leertaste)")
            preview(path)
            try:
                a = input("Go? [j] posten  [n] nie  [s] später  [b] Caption bearbeiten  [q] fertig: ").strip().lower()
            except EOFError:
                a = "q"
            if a == "b":
                edit_caption(path, kind)
                continue
            break
        if a == "q":
            break
        if a == "j":
            open(base(path) + ".freigabe", "w").close()
            approved.append((path, kind))
            if kind == "short":
                per[st] = per.get(st, 0) + 1
                s_left -= 1
            else:
                l_left -= 1
            print("   ✓ freigegeben")
        elif a == "n":
            mark_skip(path)
            print("   ✗ wird nie gepostet")
        else:
            print("   … später")
        if s_left <= 0 and l_left <= 0:
            print("\nTageslimit erreicht.")
            break
    return approved


def upload_youtube(approved):
    if not approved:
        return
    if not os.path.exists(yt.SECRET_FILE):
        print("\nYouTube ist noch nicht eingerichtet (client_secret.json fehlt) - überspringe YouTube.")
        return
    kanaele = yt.connected_channels() or ["1"]
    for k in kanaele:  # jeder verbundene Kanal bekommt die freigegebenen Videos
        yt.set_kanal(k)
        todo = [(p, kd) for p, kd in approved if not os.path.exists(base(p) + yt.MARKER)]
        if not todo:
            continue
        token = yt.get_access_token()
        print(f"\nYouTube Kanal {k} ({yt.channel_name(token)}): lade hoch und plane ...")
        slots = yt.next_slots(len(todo))
        for (path, kind), slot in zip(todo, slots):
            title, desc, tags = yt.read_meta(path, kind)
            try:
                vid = yt.upload(token, path, title, desc, tags, slot.astimezone().isoformat())
            except Exception as e:
                print(f"   Fehler bei {os.path.basename(path)}: {e}")
                continue
            with open(base(path) + yt.MARKER, "w", encoding="utf-8") as f:
                f.write(f"https://youtu.be/{vid}\nhttps://studio.youtube.com/video/{vid}/edit\n"
                        f"geplant: {slot:%d.%m. %H:%M}\n")
            print(f"   {yt.TAGE[slot.weekday()]} {slot:%H:%M}  {title}")
        yt.notify(f"YouTube Kanal {k} geplant", f"{len(todo)} Video(s) werden automatisch veröffentlicht")


def tiktok_list():
    waiting = []
    for root, _, files in os.walk(yt.SHORTS_DIR):
        for f in files:
            p = os.path.join(root, f)
            if f.endswith(".freigabe") and not os.path.exists(base(p) + ".tiktok.txt"):
                waiting.append(base(p))
    if waiting:
        print(f"\nTikTok: {len(waiting)} Video(s) warten auf den Entwurf.")
        print('   -> Schreib Claude im Chat: "TikTok-Entwürfe"')
    return waiting


def main():
    os.chdir(HERE)
    approved = review()
    upload_youtube(approved)
    tiktok_list()
    print("\nFertig.")


if __name__ == "__main__":
    main()
