<div align="center">

<img src="docs/assets/hero-3d.svg" width="100%" alt="Hearth — a cozy three-pane desktop player for YouTube Music"/>

<a href="https://github.com/qtjg/hearth"><img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=700&size=20&duration=3200&pause=900&color=FF7A18&center=true&vCenter=true&width=860&height=56&lines=Search+%E2%86%92+stream+%E2%86%92+smile.+No+account%2C+no+keys.;Endless+radio+%C2%B7+live+lyrics+%C2%B7+drag-and-drop+queue;Seven+themes+%C2%B7+one+cozy+hearth" alt="Hearth in one breath"/></a>

[![CI](https://github.com/qtjg/hearth/actions/workflows/ci.yml/badge.svg)](https://github.com/qtjg/hearth/actions/workflows/ci.yml)
![tests](https://img.shields.io/badge/tests-201%20passing-3fb950?style=flat-square&logo=pytest&logoColor=white)
![version](https://img.shields.io/badge/version-v0.6.0-ff7a18?style=flat-square)
![python](https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square&logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/UI-PyQt6-41cd52?style=flat-square&logo=qt&logoColor=white)
![license](https://img.shields.io/badge/license-MIT-8b949e?style=flat-square)
![platforms](https://img.shields.io/badge/arch%20%7C%20windows%20%7C%20macos-every%20desktop-ff2d55?style=flat-square)

**A full three-pane desktop music player for YouTube Music.**

*Sidebar navigation · Home shelves · Playlists · Now Playing with lyrics · Endless radio · Runs where you run*

</div>

---

## 🧊 The System, in 3D

Both diagrams below are hand-built, zero-dependency animated SVGs (pure SMIL —
no JavaScript, no external services) living in
[`docs/assets/`](docs/assets/). They float, glow, and flow directly on GitHub —
zoom in, they're lossless at any size.

<img src="docs/assets/arch-3d.svg" width="100%" alt="Isometric 3D diagram of Hearth's architecture: UI, PlaybackCore, worker pools, catalog, yt-dlp and YT Music API"/>

Hearth is a stack of floating layers, and the anim shows exactly how a request
travels: everything enters through the **main window**, drops into the
**playback core** (a pure queue engine wrapped by a thin Qt backend), fans out
to **isolated thread pools** so heavy network work never touches the GUI loop,
resolves through the **catalog** (guest API, link parsing, exponential retry
backoff, loudness hints), and finally lands on the **sources** — `yt-dlp` for
streams, YT Music's guest API for search, radio and lyrics. Your data never
leaves the machine: SQLite keeps favorites, history and playlists, QSettings
keeps the knobs.

```mermaid
flowchart LR
    A["🔍 Search / paste a link"] --> B["SearchJob<br/>(background pool)"]
    B --> C["Results"]
    C -->|pick| D["PlaybackCore<br/>+ QueueEngine"]
    D --> E["LoadJob<br/>(playback pool)"]
    E -->|"stream URL + loudness"| F["▶ QMediaPlayer"]
    F --> G["SQLite history<br/>+ top tracks"]
    D -->|"queue runs dry"| H["queue_dry"]
    H --> I["RadioJob<br/>(watch graph)"]
    I -->|"autoplay refill"| D
    C --> J["LyricsJob"] --> K["📝 Now Playing lyrics"]
```

<details>
<summary>🧊 About the 3D artwork</summary>

Both assets are committed SVGs rendered with isometric polygons, layered
gradients and SMIL keyframe animations (`animate`, `animateTransform`), so they
animate inside GitHub's sanitized `<img>` pipeline with **zero** JavaScript and
**zero** third-party requests. Want them standalone? Open
[`docs/assets/hero-3d.svg`](docs/assets/hero-3d.svg) or
[`docs/assets/arch-3d.svg`](docs/assets/arch-3d.svg) in any browser and watch
the equalizer dance and the stack hover in real time.

</details>

## 🐍 The Firekeeper Snake

Every six hours a scheduled action feeds qtjg's contribution graph to a snake,
and it slithers through every green square it has earned. Light and dark
variants land on the `output` branch and swap automatically to match your
GitHub theme:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/qtjg/hearth/output/github-contribution-grid-snake-dark.svg"/>
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/qtjg/hearth/output/github-contribution-grid-snake.svg"/>
  <img src="https://raw.githubusercontent.com/qtjg/hearth/output/github-contribution-grid-snake.svg" width="100%" alt="Contribution graph snake"/>
</picture>

---

## 🖼️ The Big Window (v0.3)

Hearth grew from a floating ribbon into a complete desktop music app, laid out
the way every major streaming client works — three panes, one window:

- **Left sidebar** — Home, Search, and Your Library navigation, plus all of
  your playlists with one-click creation.
- **Home** — horizontally scrolling shelves: Quick Picks seeded from guest-API
  searches, your Pinned favorites, and Recently played, all as big cover cards.
- **Search** — a prominent query box (debounced, link-aware) over clean result
  rows with mini covers, artist, and duration.
- **Your Library** — pinned favorites, recent history, and playlist cards.
- **Playlists** — create, rename, delete; add any track via its context menu
  (▶ Play next · ➕ Add to queue · ♡ Pin · 📌 Add to playlist); Play-all and
  Shuffle buttons on every playlist page.
- **Bottom player bar** — cover tile, ♡ pin, shuffle / repeat, prev / play /
  next, draggable seek with time labels, queue drawer, and a volume slider.
- **Queue drawer** — dockable "Up next" panel; right-click any row to remove it.

## 📻 Radio, Lyrics & Words (v0.4 / v0.5)

The clone wave: the features people actually live in on the big streaming
services, built on the same guest-API engine — no account, no keys:

- **Now Playing view** — a full page with a big cover, the current track's
  identity, a ♡ pin, and a live lyrics sheet (auto-loaded per track, cached,
  with a graceful "no lyrics" state).
- **📻 Start Radio** — right-click any track, hit the player-bar button, or
  press it on the Now Playing page: hearth fetches related tracks from the
  YT Music watch graph and queues them around your seed.
- **♾️ Endless autoplay** — when the queue runs dry (repeat off), the radio
  engine quietly refills it and the music keeps going. That's the whole point.
- **🔍 Search scopes** — ♪ Songs · ▶ Videos · 💿 Albums chips. Album results
  open a real album page with ▶ Play all and 🔀 Shuffle.
- **🎛️ Queue power tools** — drag & drop reordering (the playing row stays
  pinned), ▶ Play now, ↑↓ move, ✕ remove, and a Clear button. Double-click
  any upcoming row to jump straight to it.
- **🔥 Top tracks** — a Home shelf ranked by your real play counts.
- **⌨️ In-window keys** — `Space` play/pause · `←`/`→` seek ±10s · `↑`/`↓`
  volume · `/` search · `M` mute · `S` shuffle · `R` repeat · `N` now playing
  · `Q` queue — all guarded, so typing in the search box never triggers them.
- **💾 Library backup** — export or import every playlist as portable JSON
  (`.hearthplaylist.json`), plus full-library favorites+playlists export via
  the store API. Files are boring JSON on purpose: no lock-in, no cloud.
- **🔗 Copy YouTube link** — every track's context menu carries its URL.
- **🎚️ Speed cycler & ⏾ sleep menu** live on the player bar (`1x` and `⏾`).

Love the old vibe? The original floating ribbon is still there: run
`./launch.sh --ribbon` (or `python -m hearth --ribbon`) for the compact
always-on-top companion. Legacy and new share the same engine.

## 🌍 Discover — Every Music in the World (v0.6)

The whole YT Music catalogue, browsable without typing a single query. A new
🧭 **Discover** tab opens the same shelves the streaming giants use — moods,
genres, charts, releases — and every card plays in one tap:

- **🔥 Charts** — Daily & Top-100 global music video charts, straight from
  YT Music's chart engine.
- **🎶 Trending** — the 20 tracks the world is playing right now.
- **✨ New releases** — every fresh album this week (cards open real album
  pages with Play all / Shuffle).
- **🎬 New videos** — brand-new official music videos, playable list.
- **Moods & moments** — Chill, Focus, Party, Romance, Gaming… ~280 curated
  playlists per mood.
- **Genres** — Bollywood & Indian, Hip-hop, Classical, Dance, Decades,
  Indonesian and a dozen more — the world's music, literally. (This needed a
  custom junk-card-tolerant parser layer: one malformed promo card used to
  kill an entire shelf upstream — hearth skips the junk, keeps the shelf.)
- **Every curated page** carries ▶ Play all · 🔀 Shuffle · ➕ Queue all
  (100+ tracks straight into the up-next queue), plus per-track context
  menus — pin, radio, play-next, add-to-playlist, copy link.

## 🗺️ World Explorer — the Curated Dial (v0.6)

Discover browses what YT Music's shelves serve today. The **🗺️ World** tab is
the other half of the promise — a hand-built dial of **74 genre stations**
spanning **nine regions of sound**, so every kind of music on Earth is one
tap away even when the network (or the guest API) is having a bad day:

- **🥁 Africa** — Afrobeat, Amapiano, Highlife, Ethio-Jazz, Makossa, Taarab
- **🌸 Asia** — K-Pop, J-Pop, City Pop, Mandopop, Cantopop, Bollywood,
  Bhangra, Kollywood, Hindustani & Carnatic classical, Qawwali
- **🇬🇧 Europe** — Britpop, Eurodance, Italo Disco, Flamenco, Fado, Chanson,
  Balkan Brass, Nordic Folk, Celtic, Klezmer
- **🌶️ Latin America** — Reggaeton, Salsa, Bachata, Cumbia, Bossa Nova, MPB,
  Tango, Rock en español · **🟩 Caribbean** — Reggae, Dancehall, Soca, Calypso
- **🌙 MENA** — Arabic Pop, Raï, Khaliji, Anatolian Rock, Persian Classical
- **🎸 North America** — Blues, Bluegrass, Country, Motown, Funk, Gospel,
  New Orleans Jazz, Surf Rock
- **🏠 Global & Electronic** — House, Techno, Trance, DnB, Dubstep, Ambient,
  Lo-Fi, Synthwave, Jazz, Classical, Hip-Hop, R&B, Metal, Punk, Indie
- **📼 Eras** — 60s Oldies → 2010s Bangers

Each dial spins a **station**: rotating search seeds (same genre, fresh mix
every visit), instant queue-up. **🔎 Filter** the dial ("africa", "metal",
"bhangra"…) and **🎲 Surprise me** tunes anywhere on Earth.

**🔍 Search-everywhere fallback:** when the guest catalogue has never heard
of a track — rare live cuts, B-sides, regional uploads — hearth falls back
to the web (songs → videos → yt-dlp's index), so "we can't find it" comes
as close to impossible as a player can get.

## ✨ What It Does

| Feature | The Vibe |
|:---|:---|
| 🖼️ **Three-pane main window** | Sidebar + home shelves + library views + bottom transport — the full desktop-player experience |
| 🎵 **Playlists that stick** | Create, rename, delete, reorder-safe add/remove — stored in the SQLite database you own |
| 📋 **Queue drawer** | See and prune what's coming; Play-next jumps the line, Add-to-queue appends |
| 🔍 **Search or paste** | Type a song name or drop a YouTube / YT Music link — debounced, retried, instant |
| 🪟 **Ribbon companion** | The classic floating always-on-top mini player still ships (`--ribbon`) for IDE-side listening |
| 🔀 **Shuffle & repeat** | Non-destructive upcoming-queue shuffle plus cycleable repeat (off / all / one), persisted across reboots |
| ⚡ **Speed control** | Cycle 0.75x → 1.0x → 1.25x → 1.5x via native `QMediaPlayer.setPlaybackRate()` |
| ⏾ **Sleep timer** | 15–60 minute presets with a gentle exponential volume fade-out before pausing |
| 🔊 **Loudness normalization** | Stream loudness is nudged toward a target so quiet/blast tracks stop yo-yoing the volume knob |
| 🎨 **Seven live themes** | Grove (the new default), Hearthlight, Emberfall, Frost, Moss, Orchid, and Slate re-skin everything in real time |
| ♥ **Favorites & history** | Pin tracks and revisit your listening history — local SQLite, no account, no telemetry |
| 🖥️ **Tray presence** | Play, pause, skip, or summon the window from the system tray; a second launch just wakes the first |
| ⌨️ **Hotkeys** | App-scope chords for every common action, with system-shortcut conflict detection |
| 📻 **Radio & autoplay** | Endless playback: Start Radio from any track, auto-refill when the queue dries |
| 🌍 **Discover the world** | Charts, trending, new releases, moods & genres — every playlist on YT Music, browsable without typing |
| 🗺️ **World Explorer** | 74 curated genre stations across 9 regions, filter + dice, search-everywhere web fallback |
| 📝 **Lyrics** | Now Playing page with auto-loaded lyrics, cache, and no-lyrics fallback |
| 💿 **Album pages** | Search Albums scope → full track list with Play all / Shuffle |
| 🔥 **Top tracks** | Home shelf ranked by your real play counts |
| 💾 **Remembers everything** | Window size/position, volume, theme, repeat mode, speed, autoplay, favorites, playlists, and history persist |

---

## 🐧 Arch Linux (First-Class)

Hearth is built on Arch. Two ways to run it:

### Option A — venv (recommended, most reliable)

```bash
sudo pacman -S --needed python python-pip ffmpeg git
git clone https://github.com/qtjg/hearth.git
cd hearth
./install.sh && ./launch.sh
```

The PyPI `PyQt6` wheel ships the FFmpeg multimedia backend for Linux, so audio
plays out of the box — no GStreamer plumbing required. `ffmpeg` covers the
occasional yt-dlp remux.

<details>
<summary>Tray icon notes per desktop</summary>

Works out of the box on KDE Plasma, Hyprland/sway (with a tray-capable bar like
Waybar), and any panel implementing `StatusNotifierItem`. On GNOME you'll need
an AppIndicator extension for the tray to appear — the floating ribbon itself
is unaffected.

</details>

### Option B — native pacman package

A [PKGBUILD](packaging/arch/PKGBUILD) is provided:

```bash
cd packaging/arch && makepkg -si
```

It builds against Arch's system Python and Qt6 stack (`python-pyqt6`,
`qt6-multimedia`, `gst-plugins-good`, `gst-libav`) with no venv isolation.

---

## 🪟 Windows & 🍎 macOS

```bat
install.bat
launch.bat        (or launch_debug.bat to watch the logs)
```

```bash
./install.sh && ./launch.sh
```

Both use an isolated `.venv` — your system Python stays untouched.

---

## ⌨️ Default Hotkeys

| Keys | Action |
|:---|:---|
| `Ctrl` + `Alt` + `Space` | Play / pause |
| `Ctrl` + `Alt` + `→` | Next track |
| `Ctrl` + `Alt` + `←` | Previous track |
| `Ctrl` + `Alt` + `E` | Toggle the window / ribbon |
| `Ctrl` + `Alt` + `F` | Focus search |

**In-window keys** (v0.5) work wherever you are — `Space` play/pause,
`←`/`→` seek ±10s, `↑`/`↓` volume, `/` focus search, `M` mute, `S` shuffle,
`R` repeat, `N` Now Playing, `Q` queue drawer. They yield automatically while
you're typing in the search box.

Bindings are merged from user overrides on top of the defaults and validated by
a conflict detector that flags duplicates and system-shortcut collisions
(`Ctrl+C`, `Alt+F4`, `Super+L`, …) before they can hurt you.

---

## 🗂️ Project Structure

```
hearth/
├── hearth/
│   ├── app.py          → lifecycle, persistence, hotkeys, logging
│   ├── catalog.py      → YT Music guest search, link parsing, retry backoff
│   ├── config.py       → palettes, tunables, hotkey defaults (single source of truth)
│   ├── cover.py        → cover tiles: painted flame fallback + async album art
│   ├── hotkeys.py      → conflict detection & override merging
│   ├── jobs.py         → QRunnable search/load workers on isolated pools
│   ├── models.py       → Track dataclass & serialization
│   ├── panel.py        → the floating ribbon (legacy companion UI)
│   ├── player.py       → queue engine (pure) + lazy Qt Multimedia backend
│   ├── share.py        → playlist JSON encode/decode for portable exports
│   ├── storage.py      → SQLite favorites, history & playlists
│   ├── stream.py       → yt-dlp resolver, format picker, loudness gain
│   ├── theme.py        → stylesheets compiled from Palette tokens
│   ├── toast.py        → non-focus-stealing now-playing toast
│   ├── tray.py         → tray presence, painted icon, single-instance guard
│   ├── window.py       → the three-pane main window (sidebar/shelves/transport)
│   ├── world.py        → the 74-genre World Explorer universe (pure data)
│   ├── ytm_resilience.py → junk-card-tolerant YT Music parser layer (Discover)
│   └── utils.py        → small zero-dependency helpers
├── docs/assets/        → animated 3D SVG artwork used by this README
├── tests/              → 201 headless tests (offscreen Qt platform)
├── packaging/arch/     → PKGBUILD for a native Arch package
├── install.sh / .bat   → one-command venv setup per OS
├── launch.sh / .bat    → silent desktop launchers
└── pyproject.toml      → `pip install .` gives you the `hearth` command
```

---

## 🧪 Testing

201 tests cover models, palettes, playlists, share codecs, storage, retry
backoff, format picking, queue semantics, radio + autoplay refill, lyrics
caching, hotkey conflicts, the genre universe (every dial described, seed
rotation), search-everywhere fallback ladders, the main window (views,
player bar, queue dock with drag & drop, pin flow), and the real app
booting headless:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -v
```

CI runs the same suite on a **3 OS × 2 Python matrix** (ubuntu / windows /
macos × 3.11 / 3.13) on every push — the "every desktop" promise is enforced,
not just claimed.

---

## 🗺️ Roadmap

- 🎨 Artist pages (Discover serves the shelves; artist drill-down is next)
- 📦 AUR package publication
- 🕓 Synced (time-cued) lyrics

---

<details>
<summary>📈 Repo stats</summary>

<a href="https://github.com/qtjg/hearth"><img src="https://github-readme-stats.vercel.app/api/pin/?username=qtjg&repo=hearth&theme=github_dark_orange&show_icons=true" height="160" alt="hearth repo stats"/></a>
<img src="https://github-readme-stats.vercel.app/api/top-langs/?username=qtjg&layout=compact&theme=github_dark_orange" height="160" alt="top languages"/>

</details>

---

## 📜 License

**Hearth** is distributed under the [MIT License](LICENSE).

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&height=110&color=0:7b2ff7,50:ff2d55,100:ff7a18&section=footer" width="100%" alt=""/>

<sub><strong>Hearth</strong> — keep the fire warm. 🔥</sub>

</div>
