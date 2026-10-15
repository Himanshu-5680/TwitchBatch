![LOCAL · OPEN SOURCE · YOUR DOWNLOADS FOLDER](https://img.shields.io/badge/LOCAL_·_OPEN_SOURCE_·_YOUR_DOWNLOADS_FOLDER-000000?style=for-the-badge&logo=twitch&logoColor=00F593&labelColor=000000&color=9146FF)

![TWITCHBATCH](https://readme-typing-svg.demolab.com?font=Chakra+Petch&weight=700&size=54&duration=1&pause=9999999&color=FFFFFF&background=9146FF&center=true&vCenter=true&width=860&height=95&lines=TWITCHBATCH+%E2%80%94+ONE+BATCH.)

![TwitchBatch Subtitle](https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=700&size=15&duration=3500&pause=1500&color=00F593&background=0E0E10&center=true&vCenter=true&width=860&height=42&lines=Put+a+Word+.docx+in.+Get+Twitch+VODs+%26+Clips+out%2C+one+MP4+at+a+time.;Powered+by+Python+%2B+yt-dlp+%2B+FFmpeg+%E2%80%94+Faststart+Seekable+Local+MP4s.;Zero+Login.+Zero+Subscriber+Bypass.+Auto-Skips+Saved+Files.)

![Python 3.10+](https://img.shields.io/badge/PYTHON-3.10%2B-0E0E10?style=for-the-badge&logo=python&logoColor=00F593&labelColor=000000&color=9146FF)![yt-dlp + FFmpeg](https://img.shields.io/badge/ENGINE-yt--dlp_%2B_FFmpeg-0E0E10?style=for-the-badge&logo=ffmpeg&logoColor=00F593&labelColor=000000&color=00F593)![Port 8787](https://img.shields.io/badge/PORT-8787-0E0E10?style=for-the-badge&labelColor=000000&color=FFB800)![Windows EXE](https://img.shields.io/badge/BUILD-TwitchBatch.exe-0E0E10?style=for-the-badge&logo=windows&logoColor=FFFFFF&labelColor=000000&color=9146FF)

---

**⚠️ RIGHTS FIRST: Download only videos you have the right to keep. Local runs save files on the computer running TwitchBatch. The app does not log in, does not use cookies, and does not bypass a subscriber wall. Not an official Twitch product.**

| 📄 `.DOCX` | 🎬 `1 PRESET` | ⛓️ `IN ORDER` | 💾 `LOCAL DISK` |
| --- | --- | --- | --- |
| **SOURCE FILE** Reads text, tables & hidden links | **ONE QUALITY** 1080p, 720p, or 480p MP4 | **ONE BY ONE** Sequential queue with live stats | **SEEKABLE MP4** Saves to `Downloads` with `+faststart` |

---

## ⚡ HOW IT WORKS — *UPLOAD, CHOOSE, SAVE.*

| STEP 01 · `.DOCX` INPUT | STEP 02 · QUALITY | STEP 03 · LOCAL OR CLOUD |
| --- | --- | --- |
| ![Step 01](https://img.shields.io/badge/.DOCX_INPUT-00F593?style=for-the-badge&label=STEP_01&labelColor=000000&color=00F593)<br><br>**🔍 Upload the Document**<br>`VODs` · `Clips` · `Max 25 MB`<br><br>`link_extractor.py` scans the entire Word `.docx`—body, tables, headers, footers, and hyperlinks hidden behind text. Old binary `.doc` files are rejected (save them as `.docx` first).<br><br>**STAGE:** `01 / 03` | ![Step 02](https://img.shields.io/badge/QUALITY-00F593?style=for-the-badge&label=STEP_02&labelColor=000000&color=00F593)<br><br>**🎚️ Pick One Quality**<br>`1080p MP4` · `720p MP4` · `480p MP4`<br><br>Choose once for the entire batch (default is `1080p MP4`). Your choice acts as a ceiling—if a stream only has `720p`, it automatically grabs the closest lower resolution.<br><br>**STAGE:** `02 / 03` | ![Step 03](https://img.shields.io/badge/LOCAL_DISK-00F593?style=for-the-badge&label=STEP_03&labelColor=000000&color=00F593)<br><br>**🚀 Save to PC**<br>`yt-dlp + FFmpeg` · `+faststart` · `Auto Skip`<br><br>On your PC (`server.py` or `.exe`), videos save to `Downloads` with `-movflags +faststart` so Windows Media Player and VLC can seek. Project folders are refused and finished MP4s are skipped.<br><br>**STAGE:** `03 / 03` |

---

## 📺 LIVE UI — *THE* `BATCHCAST` *360×360 NEOBRUTALIST CUBE*

The moment you click **Download all** on a local run, the **BATCHCAST** status cube pops up showing real-time telemetry from `yt-dlp` and `FFmpeg`:

```text
╔══════════════════════════════════════════════════════════════╗
║  👾 BATCHCAST                                   [ FETCHING ] ║
╠══════════════════════════════════════════════════════════════╣
║  ┌────────────────────────────────────────────────────────┐  ║
║  │ SOURCE: LINKS_LIST.DOCX (1/3)                          │  ║
║  │ twitch.tv/videos/2900177328                            │  ║
║  │ [ 1080p MP4 ]  [ yt-dlp + FFmpeg ]                     │  ║
║  └────────────────────────────────────────────────────────┘  ║
║                                                              ║
║  64%                         142.8 MiB · 11.4 MiB/s · ETA 18s║
║  ┌────────────────────────────────────────────────────────┐  ║
║  │ ████████████████████████████████████░░░░░░░░░░░░░░░░░░ │  ║
║  └────────────────────────────────────────────────────────┘  ║
║  ┌────────────────────────────────────────────────────────┐  ║
║  │ 1. twitch.tv/videos/2900177328             DOWNLOADING │  ║
║  │ 2. twitch.tv/clip/VivaciousTsundere...         WAITING │  ║
║  │ 3. twitch.tv/videos/2896051202                 WAITING │  ║
║  └────────────────────────────────────────────────────────┘  ║
║ ------------------------------------------------------------ ║
║  BATCH: 00 / 03 DONE               [ PAUSE JOB ]  [ CLOSE ]  ║
╚══════════════════════════════════════════════════════════════╝
```

* **`PAUSE JOB` / `RESUME`:** Tells the local server to hold at the next progress tick without cutting a video fragment in half.
* **`CLOSE`:** Hides the modal while the download continues in the background (click **Show status** to reopen).
* **Page Refresh (`F5`):** Sends `/api/cancel` via `navigator.sendBeacon`. The partial `.part` file stays on disk so your next upload resumes where it left off.

---

## 🚀 START IN ONE MINUTE (LOCAL PC)

You need **Python 3.10+** and **[FFmpeg](https://ffmpeg.org/download.html)** on your system `PATH`.

### Option A: Run from Source

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server.py
```

Open **[http://127.0.0.1:8787](http://127.0.0.1:8787)** in your browser.

> **Windows Store alias:** If `python3` is a broken Microsoft Store alias, run `.\.venv\Scripts\python.exe server.py`.

### Option B: Run `TwitchBatch.exe`

Double-click `dist\TwitchBatch.exe`. It opens **[http://127.0.0.1:8787](http://127.0.0.1:8787)** on its own.

* If you changed Python or the page, run `rebuild.bat` first. The exe is a snapshot and does not pick up later edits.
* Close `python server.py` first, or port `8787` is already in use.
* **FFmpeg is not inside the exe.** It still has to be on `PATH`.
* Windows SmartScreen may warn because the binary is unsigned. Allow it only if you built it or trust the copy.

---

## ☁️ LOCAL PC vs RENDER

| Feature | Local PC (`server.py` / `TwitchBatch.exe`) | Cloud (Render) |
| --- | --- | --- |
| **How it downloads** | `yt-dlp` + FFmpeg write straight into the save folder | A short clip is built in the temp folder, sent, then deleted. A long VOD is piped as MPEG-TS and is not stored |
| **Concurrency** | One batch. A `.part` file can resume | One FFmpeg at a time. Disconnect runs `proc.kill()` |
| **Seek** | **Windows Media Player and VLC.** `-movflags +faststart` moves the `moov` index to the start | **Short clip** (under 3 minutes and under 400 MB): same faststart MP4. **Long VOD:** `.ts`. VLC can seek it. Windows Media Player usually cannot |
| **Where the file lands** | `Path.home() / "Downloads"`, unless you pick another folder outside this project. An existing finished MP4 is skipped | **Chrome / Edge:** the click opens a folder picker and writes the `.mp4` or `.ts` there. **Firefox / Safari:** no folder picker, and the page does not pretend the file is done |
| **Accepted URLs** | Twitch VOD and clip links only | Twitch links only. Anything else returns `400` |

A public `https://` Render site cannot call `http://127.0.0.1:8787`. Browsers block that mixed content. `Access-Control-Allow-Origin: *` does not remove the block. When the exe or `python server.py` is running, open **[http://127.0.0.1:8787](http://127.0.0.1:8787)** directly.

---

## 📱 PHONE AND LAN

```powershell
python server.py --host 0.0.0.0 --port 8787
```

Open `http://<this-pc-ip>:8787` on the phone and use **Add to Home screen**.

| You open the page on | Where the file is written | How a phone gets a copy |
| --- | --- | --- |
| The PC running `server.py` or the exe | That PC's save folder | Already on disk |
| A phone on the same Wi-Fi | Still the host PC | Use the finished row's `/api/file?name=...` link. That copy is not deleted |

There is no APK in this repo. A WebView wrapper would only open this page. `yt-dlp` and FFmpeg would still run on the machine that hosts the server.

---

## 🧠 HOW A LOCAL VIDEO IS SAVED

1. `link_extractor.py` walks the `.docx` body, tables, headers, and footers, including hyperlinks hidden behind other words.
2. Query strings and fragments are removed. `/channel/v/{id}` becomes `https://www.twitch.tv/videos/{id}`.
3. Accepted shapes: `twitch.tv/videos/{id}`, `twitch.tv/{channel}/v/{id}`, `twitch.tv/.../clip/{slug}`, `twitch.tv/clip/{slug}`, `clips.twitch.tv/{slug}`.
4. `formats.py` maps the button to `bestvideo[height<=N]+bestaudio/best[height<=N]` and merges to MP4.
5. If `{id}.mp4` already exists, is larger than 0 bytes, and has no sibling `{id}*.part` or `{id}*.ytdl`, the row is `already saved`.
6. Otherwise yt-dlp downloads with `continuedl`, and FFmpeg merges with `-movflags +faststart`.

---

## 🔌 HTTP API

One batch at a time. Restarting the server clears the on-screen list. It does not delete saved files.

| Method and path | What it does |
| --- | --- |
| `GET /` | Serves `web/index.html` |
| `GET /api/health` | `{ffmpeg, folder, cloud}`. Locally `cloud` is `false` |
| `POST /api/extract` | Raw `.docx` bytes. `X-Filename` must end in `.docx`. Returns `{links}`. Limit 25 MB |
| `POST /api/download` | JSON `{urls, quality, folder}`. Starts the local worker. `409` if a job is already running |
| `GET /api/cloud_stream` | One Twitch URL. A short clip is a faststart MP4 built in temp and deleted after send. A long VOD is MPEG-TS on a pipe. Non-Twitch URLs return `400` |
| `GET /api/job` | `{running, paused, message, fraction, rows}` |
| `POST /api/pause` | Holds the worker at the next progress tick |
| `POST /api/resume` | Continues the same job |
| `POST /api/cancel` | Stops the job. The page sends this on `pagehide` |
| `GET /api/file?name=` | Sends one finished file from the current save folder, by basename only. The file stays on disk |

---

## 🗂️ PROJECT STRUCTURE

```text
TwitchBatch/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── workflows/
│       └── check.yml
├── dist/
│   └── TwitchBatch.exe            # built locally, gitignored
├── downloads/
│   └── .gitkeep
├── web/
│   └── index.html
├── .dockerignore
├── .gitignore
├── app.py                         # old Streamlit screen; not imported by server.py
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── Dockerfile
├── downloader.py
├── formats.py
├── guide.md
├── link_extractor.py              # this name must stay; extractor.py collides with yt-dlp
├── README.md
├── rebuild.bat
├── requirements.txt
├── server.py
└── TwitchBatch.spec
```

---

## 🛠️ REBUILD THE EXE

```powershell
.\rebuild.bat
```

Or:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean TwitchBatch.spec
```

`TwitchBatch.spec` packs `web/index.html` and collects `yt_dlp` and `docx`. A bare `pyinstaller server.py` leaves the page out of the exe.

---

## 🧯 TROUBLESHOOTING

| What you see | What to do |
| --- | --- |
| `Only .docx` | Save the old `.doc` as `.docx` |
| `FFmpeg is not on PATH` | Install FFmpeg, then start the server again |
| `Pick a folder outside this project` | Use Downloads or another folder that is not this repo |
| A long cloud VOD will not seek in Windows Media Player | Open the `.ts` in VLC. For a seekable MP4, run `server.py` or `TwitchBatch.exe` on this PC. A short cloud clip is already a faststart MP4 |
| The Render site does not use the local exe | Open `http://127.0.0.1:8787` directly. HTTPS cannot call that HTTP address |
| Firefox or Safari does nothing on cloud **Download all** | Those browsers have no folder picker. Use Chrome or Edge, or run the app on this PC |
| The exe still shows old behavior | Run `rebuild.bat` |
| `A batch is already running` | Wait, pause, or refresh |
| `Stopped` | Refresh cancelled the run. Upload the `.docx` again. A `.part` file can resume |
| `Port already in use` | Close the other process that is using `8787` |
| The card says paused but the file grows for a moment | Pause waits for the next progress tick |
| A private or subscriber-only video fails | Out of scope. That row fails and the next link still runs |

---

## 🚧 KNOWN LIMITS

* No login, no cookies, and no subscriber bypass.
* Old binary `.doc` files are not read.
* A cloud VOD is MPEG-TS, not a faststart MP4. VLC can seek it. Windows Media Player usually cannot. A cloud clip uses the temp disk only when it is under 3 minutes and under 400 MB.
* A public HTTPS page cannot call `http://127.0.0.1:8787`.
* Refresh clears the on-screen list. Files already on disk stay.
* A live stream is not a finished MP4 until yt-dlp closes it.
* Google Fonts load on the first visit. Offline, the page uses system fonts. The download does not need those fonts.

---

[📘 FULL GUIDE (guide.md)](guide.md) • [🤝 CONTRIBUTING.md](CONTRIBUTING.md) • [📜 CODE OF CONDUCT](CODE_OF_CONDUCT.md)

![Himanshu-5680](https://img.shields.io/badge/AUTHOR-Himanshu--5680-9146FF?style=for-the-badge&logo=github&logoColor=FFFFFF&labelColor=000000) [![yt-dlp](https://img.shields.io/badge/POWERED_BY-yt--dlp-00F593?style=for-the-badge&logo=github&logoColor=000000&labelColor=000000)](https://github.com/yt-dlp/yt-dlp)

TwitchBatch is an open-source local tool. Twitch is a trademark of its owner. This project is not affiliated with or endorsed by Twitch.
