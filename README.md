<div align="center">

# 🔥 Hearth

**A cozy floating music companion for every desktop — Arch Linux, Windows, and macOS.**

*Warm as a fireside · Light as a ribbon · Runs where you run*

<br/>

**Python 3.10+ · PyQt6 · YouTube Music · SQLite · MIT**

</div>

---

## ✨ What It Does

| Feature | The Vibe |
|:---|:---|
| 🔍 **Search or paste** | Type a song name or drop a YouTube / YT Music link straight into the field — debounced and instant |
| ♾️ **Endless queue** | The recommendation graph feeds look-alike tracks in behind your seed so the room never goes quiet |
| 🪟 **Ribbon → panel** | A thin, discreet desk ribbon that blooms into an expanded player when you want to dig into the queue |
| ⌨️ **Always on top** | Floats cleanly over IDEs, browsers, and terminals — pure Qt, no platform-specific hacks |
| 🔁 **Repeat & speed** | Cycle repeat (off / all / one) and playback speed (0.75x–1.5x), both persisted across reboots |
| 🎨 **Live themes** | Ember, Forest, and Orchid palettes re-skin the whole player in real time |
| ♥ **Favorites & history** | Pin tracks and revisit your listening history — stored in a local SQLite database you own |
| 🖥️ **Tray presence** | Play, pause, skip, or summon from the system tray; a second launch just wakes the first |
| 💾 **Remembers everything** | Window position, volume, theme, repeat mode, speed, favorites, and history persist across reboots |

---

## 🐧 Arch Linux (First-Class)

Hearth is built on Arch. Two ways to run it:

### Option A — venv (recommended, most reliable)

```bash
git clone https://github.com/qtjg/hearth.git
cd hearth
./install.sh      # creates .venv and installs pinned wheels (bundles its own Qt)
./launch.sh
```

### Option B — system packages (pacman-native)

Install the runtime deps from the official repos, then run from source:

```bash
sudo pacman -S --needed python python-pyqt6 qt6-multimedia \
    gst-plugins-good gst-plugins-bad gst-libav \
    python-ytmusicapi python-yt-dlp python-requests
python -m hearth
```

> [!NOTE]
> The GStreamer plugins (`gst-plugins-good/bad`, `gst-libav`) are what Qt's
> multimedia layer uses to decode audio on Linux — without them tracks stay
> silent. AAC-in-MP4 streams are preferred, which every backend above decodes.

<details>
<summary><b>Building an Arch package</b> (optional)</summary>

A starter `PKGBUILD` lives in [`packaging/arch/`](packaging/arch/PKGBUILD):

```bash
cd packaging/arch
makepkg -si
```

</details>

### Tray icon on GNOME

GNOME hides tray icons by default. Either install
[AppIndicator extension](https://extensions.gnome.org/extension/615/appindicator-support/)
or run Hearth on KDE / Hyprland / sway where tray support is standard.

---

## 🪟 Windows

```bat
git clone https://github.com/qtjg/hearth.git
cd hearth
install.bat
launch.bat
```

`launch.bat` starts Hearth silently in the background; `launch_debug.bat`
keeps a console open for live logs.

## 🍎 macOS

```bash
git clone https://github.com/qtjg/hearth.git
cd hearth && ./install.sh && ./launch.sh
```

Qt uses AVFoundation on macOS — no extra codecs needed.

---

## 🎛️ How It Works

Stream resolution and recommendation generation run completely asynchronously
on **isolated thread pools**, so audio starts the instant a stream URL lands:

1. **Playback pool** — dedicated to resolving the audio stream for the track you picked.
2. **Background pool** — search, radio expansion, and cover-art downloads never stall playback.

All heavy work is retried with exponential backoff; permanently dead tracks
(age gates, removed videos) are detected and auto-skipped instead of wedging
the queue.

```
Search / Paste → Queue Engine ─┬─► LoadJob  ─► QMediaPlayer
                               └─► RadioJob ─► queue grows behind the seed
```

---

## 🧪 Testing

```bash
pytest tests/ -v          # 29 tests: models, storage, catalogue, streams, UI smoke
```

The suite runs fully offscreen (`QT_QPA_PLATFORM=offscreen`) — no display or
audio server required — which is exactly how CI runs it on all three OSes.

---

## 📦 Project Structure

```
hearth/
├── hearth/
│   ├── app.py          → lifecycle, session restore, wiring
│   ├── catalog.py      → YouTube Music guest API with retry backoff
│   ├── config.py       → design tokens, themes, geometry & tunables
│   ├── jobs.py         → QRunnable tasks for the thread pools
│   ├── models.py       → Track dataclass & serialization
│   ├── panel.py        → the floating ribbon + expanded player
│   ├── player.py       → audio core, queue engine, repeat/speed
│   ├── storage.py      → SQLite favorites & playback history
│   ├── stream.py       → yt-dlp resolver with cross-platform format pick
│   ├── theme.py        → stylesheets compiled from the live palette
│   └── tray.py         → tray presence, runtime-painted icon, single-instance
├── tests/              → pytest suite (runs headless on every OS)
├── packaging/arch/     → PKGBUILD for a native Arch package
├── install.sh / .bat   → one-command venv setup per platform
└── .github/workflows/  → CI matrix: ubuntu-latest, windows-latest, macos-latest
```

---

## 🗺️ Roadmap

- [ ] Lyrics tab via YT Music
- [ ] Desktop "Now Playing" toast
- [ ] Sleep timer with volume fade
- [ ] Global hotkeys with conflict detection
- [ ] AUR package publication

---

## 🫡 Credits

- **[@qtjg](https://github.com/qtjg)** — author and maintainer
- **[Ember](https://github.com/AIwolfie/Ember)** by [@AIwolfie](https://github.com/AIwolfie) — the project that inspired Hearth's cozy floating-panel concept

## 📄 License

MIT — see [LICENSE](LICENSE).
