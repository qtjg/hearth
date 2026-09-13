# 🗺️ Hearth Roadmap — the road to the warmest player on every desktop

> This file is about **what burns next**. Shipped features live in the
> [README](README.md). It is revisited every release — waves get promoted,
> re-scoped, or retired, but the fire never gets a "maybe".
>
> Last stoked: **2026-09-14**, right after v0.6.2 (Glass & Motion — the 2020s visual pass).

---

## ✅ Where we are

| Release | Theme | Highlights |
|---------|-------|------------|
| v0.4.0 | The cozy core | floating panel, queue tools, pinning, hotkeys, radio |
| v0.5.0 | The library | search scopes, album pages, top tracks, shortcuts |
| v0.6.0 | The wide world | Discover (charts / moods / ~280 playlists) + World Explorer (74 genre stations) |
| v0.6.1 | The spotlight | **artist pages** (face, top tracks, releases, kindred acts) + **synced lyrics** (LRCLIB, glowing line, click-to-seek) |
| v0.6.2 | Glass & Motion | gradients, glass surfaces, shadows & accent glows, 3D rounded covers + floor reflection, view crossfades, glossy EQ bars |

254 tests and counting, headless on a 3 OS × 2 Python CI matrix. Every
network layer is *never-raises*; the UI never blocks on the world.

---

## 🎯 How waves are chosen

1. **Cozy first** — an upgrade ships only if it makes the daily loop
   (open → play → sing along) warmer, not just feature-richer.
2. **Off the main thread** — anything that touches the network goes through
   the job pool; the UI is never allowed to wait.
3. **Headless or it didn't happen** — every wave lands with tests that run
   under `QT_QPA_PLATFORM=offscreen`, same as CI.
4. **No account walls** — Hearth stays keyless where its sources are
   keyless (YT Music, LRCLIB). Opt-in bridges are the only exceptions.

---

## 🔥 v0.7.0 — Memory & Rituals

*The hearth should know you. This wave makes Hearth remember.*

1. **Listen history** — `storage.log_play()` already records every play;
   surface it as a "Recently played" shelf and a full history page with
   day-jumps. Your past becomes a playlist.
2. **"On Repeat" smart playlist** — an auto-updating top-25 computed from
   play counts (decayed so last week beats last year). Appears in the
   Library next to your pins.
3. **The Glow Mix** — a Friday-evening ritual: one tap builds a fresh mix
   from your heavy rotation + the related artists the v0.6.1 pages gave us.
4. **Queue persistence** — the queue, its order, and its position survive a
   restart. Close the laptop mid-song, open it on the same beat.
5. **Discord Rich Presence** 🎮 — show the burning track on your profile
   via `pypresence` (opt-in): title, artist, elapsed time, "Listen along"
   button linking the YouTube URL Hearth already copies.

**Acceptance:** history & On Repeat fully headless-tested; queue restores
in <1 s; Rich Presence never touches the audio path and degrades silently
when Discord is absent.

---

## 🎭 v0.8.0 — The Wider Stage

*The same fire, more rooms.*

1. **Desktop lyrics overlay** — the synced-lyrics engine steps out of the
   window: a frameless, always-on-top, click-through-except-draggable strip
   glowing the current line over any app. Karaoke for your whole desktop.
2. **Theater mode** — full-screen Now Playing: giant cover, huge synced
   lines, ambient palette glow. For the TV on the wall.
3. **Palette packs + theme editor** — `theme.py` palettes become importable
   packs; a small editor tweaks accent, glow and wallpaper with live
   preview. Your hearth, your colors.
4. **Per-track memory** — playback rate and volume nudges remembered per
   track (podcast at 1.75×, concert film at 1.0×, automatically).

**Acceptance:** overlay composites at 60 fps with zero audio interference;
themes are pure data files (no code); everything survives the offscreen suite.

---

## 📦 v0.9.0 — Reach

*Every desktop means every desktop.*

1. **AUR publication** — `hearth-music` on the Arch User Repository
   (the `packaging/` recipes graduate to a real PKGBUILD + git tag flow).
2. **Windows winget + macOS Homebrew/cask manifests** — one-command installs
   on the other two CI platforms.
3. **Update whisper** — a polite, dismissible "a newer hearth is lit"
   note (checks GitHub releases; never auto-downloads, never nags twice).
4. **Diagnostics report** — one dialog that shows which fetch leg served
   each shelf (catalogue → web → flat index), powered by `ytm_resilience`
   counters. Bug reports go from "it's broken" to "leg 2 timed out".

**Acceptance:** fresh-machine installs verified on all three OSes; the
update check is off by default in tests and never blocks startup.

---

## 🎪 v1.0.0 — The Festival

*The 1.0 bar: nothing left that a listener would call "missing".*

1. **Gapless playback** — pre-resolve the next track in the queue while the
   current one plays; crossfade option (0–3 s) on the player bar.
2. **Native backend probe** — a pluggable playback core behind
   `PlaybackCore`, starting with an mpv-backed variant that unlocks a real
   equalizer and bit-perfect output where the OS allows it.
3. **Plugin hooks** — a tiny, versioned extension surface (one JSON
   manifest + one Python entry point) so shelf sources and palette packs
   can be added without forking.
4. **Multi-language UI** — strings extracted, community translations
   welcome; Hindi and Spanish first.

---

## 🌱 Wish pool

*Not scheduled, not forgotten — promoted into a wave when the fire is ready:*

- Last.fm scrobbling bridge (opt-in, keyed)
- Local music library side-by-side with YT Music shelves
- Podcasts & audiobooks shelf (speed memory from v0.8.0 makes this sing)
- Listening parties — share a queue link, synced "next track" voting
- Mini-visualizer in the player bar (palette-colored, GPU-cheap)

---

## 🛡️ Standing guardrails

- The catalogue never raises; a dead shelf is an empty shelf with a note.
- Every job runs on the worker pools; the UI thread only paints.
- Lyrics and metadata stay keyless; opt-in bridges never gate core playback.
- Every wave lands with headless tests; CI stays 3 OS × 2 Python green.
- Only this repo's own shelves are touched — no account data leaves the
  machine except to the services the user chose.
