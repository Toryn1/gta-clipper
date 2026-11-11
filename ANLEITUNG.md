# GTA 6 Clipper – Anleitung

## 1. Einmalig: Twitch-Zugang holen (2 Min., gratis)
1. Auf https://dev.twitch.tv/console einloggen (Zwei-Faktor-Login muss bei Twitch aktiv sein).
2. **Register Your Application**
   - Name: irgendwas, z.B. `mein-gta-clipper`
   - OAuth Redirect URL: `http://localhost:3000`  (genau so!)
   - Kategorie: *Other*
   - Client-Typ: *Public*
3. Speichern → **Client-ID** kopieren. (Ein Secret brauchst du nicht.)
4. Optional: Client-ID oben in `index.html` und `autoclipper.py` bei `CLIENT_ID = ""` eintragen.

Python brauchst du für beides (python.org, bei Windows "Add to PATH" anhaken).
Unter Windows heisst der Befehl `python` oder `py`, auf Mac `python3`.

## 2. Clip-Finder (die besten bestehenden Clips)
Im Ordner mit den Dateien ein Terminal öffnen:

    python -m http.server 3000 --bind 127.0.0.1

Dann im Browser **http://localhost:3000** öffnen → einloggen → fertig.
- Zeitraum, Sprache, Mindest-Views und "Max. pro Streamer" einstellen (Letzteres sorgt für Abwechslung).
- Clips auswählen → **yt-dlp-Befehle kopieren** → ins Terminal einfügen → Clips landen im Ordner `clips/`,
  benannt als `Streamer - Titel`, damit du beim Posten weisst, wen du nennen musst.
- yt-dlp: https://github.com/yt-dlp/yt-dlp (Windows: `winget install yt-dlp`, Mac: `brew install yt-dlp`)

## 3. Auto-Clipper (erstellt selbst Clips bei Chat-Explosionen)
Wichtig: Der Clip-Finder-Server muss für den Login kurz gestoppt sein (Strg+C), weil beide Port 3000 nutzen.

    python autoclipper.py --dry-run            # erst testen: zeigt nur, wann er clippen WÜRDE
    python autoclipper.py                      # Top 10 GTA-6-Streams
    python autoclipper.py --top 15 --lang de   # nur deutsche Streams
    python autoclipper.py --channels name1,name2
    python autoclipper.py --download           # Clips gleich runterladen (braucht yt-dlp)

Feintuning:
- Zu viele Clips → `--factor 3` oder `--cooldown 180`
- Zu wenige Clips → `--factor 1.8` oder `--min-score 12`
- Clips erscheinen auf deinem Twitch-Account unter "Clips" und im Terminal als Link.
- Manche Streamer erlauben Clips nur Followern/Subs – das Script meldet das.

## Beim Posten
Streamer immer gut sichtbar nennen, Clips etwas bearbeiten (Untertitel, eigener Titel),
und bei Streamern, die du oft nutzt, kurz nachfragen. Das schützt dich vor Copyright-Strikes.
