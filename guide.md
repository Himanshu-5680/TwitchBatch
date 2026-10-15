# TwitchBatch guide

TwitchBatch reads a Word `.docx`, finds Twitch video and clip links, and downloads them one by one. On a local PC (`python server.py` or `dist\TwitchBatch.exe`), the computer that runs the server writes MP4 files with `-movflags +faststart`, so Windows Media Player and VLC can seek. On Render, a short clip is built in the temp folder, sent, and deleted. A long VOD is piped as MPEG-TS and is not stored on the server.

The page is not an official Twitch product. Download only videos you have the right to keep. The app does not log in and does not bypass a subscriber wall.

## Start on your PC

You need Python 3.10 or newer and FFmpeg on PATH.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server.py
```

Open http://127.0.0.1:8787.

`python3` on Windows is often a broken Store alias. Use `.\.venv\Scripts\python.exe` if `python` is not the virtual environment.

To let a phone on the same Wi-Fi open the page, while the download still happens on this computer:

```powershell
python server.py --host 0.0.0.0 --port 8787
```

Then open `http://<this-pc-ip>:8787`.

The other way to start is `dist\TwitchBatch.exe`. It opens http://127.0.0.1:8787 by itself. Close `python server.py` first, or port 8787 is already taken. If you changed any code, run `rebuild.bat` first. The exe keeps its old behavior until it is rebuilt. FFmpeg is not inside the exe. Windows may warn because the exe is unsigned. Allow it only if you built it or trust the copy.

## Use the page on this PC

1. Home. Choose a `.docx`. Old binary `.doc` files are rejected. Save them as `.docx` first. The upload limit is 25 MB.
2. The page lists every Twitch video and clip it finds. One quality applies to the whole list: 1080p MP4, 720p MP4, or 480p MP4. The default is 1080p.
3. The save folder starts as the Downloads folder of whoever is logged in (`Path.home() / "Downloads"`). You can change it. Any folder inside this project is rejected.
4. **Download all** runs yt-dlp and FFmpeg and opens the BATCHCAST card. It shows which video, the percent, size, speed, and time left.
5. On merge, FFmpeg uses `-movflags +faststart`. That moves the `moov` index to the start of the file. A finished MP4 that is already in the folder is skipped.
6. PAUSE JOB waits at the next progress update. RESUME continues the same file. Refresh sends cancel. The partial file stays. Refresh also clears the on-screen list, so upload the document again.

A finished row links to `/api/file?name=...`. That sends a copy and leaves the original in the save folder.

## Render and the local PC

### Short clips and long VODs

`/api/cloud_stream` accepts only a Twitch link. Anything else returns `400`.

* A clip under 3 minutes and under 400 MB is written in the temp folder with `+faststart`, sent, then deleted. That MP4 can be seeked.
* A longer video is piped as MPEG-TS (`.ts`). VLC can seek it because the timestamps are inside the stream. Windows Media Player usually cannot. The server does not keep the file.
* One FFmpeg runs at a time. If the browser disconnects, the process is killed.
* Chrome and Edge ask for a folder on the **Download all** click and write the `.mp4` or `.ts` there.
* Firefox and Safari have no folder picker. The page does not mark those rows done.

### Why a pipe cannot be a faststart MP4

Faststart is a second pass. FFmpeg has to finish the file, move the `moov` box to the front, and rewrite the byte offsets. A pipe never has the whole file on disk, so that pass cannot run. That is why a long cloud video is `.ts`, and why a seekable MP4 for Windows Media Player comes from `server.py` or `TwitchBatch.exe` on this PC.

### Why the Render site cannot call the exe

A public `https://` page cannot call `http://127.0.0.1:8787`. The browser blocks mixed content. CORS headers do not remove that block. Open http://127.0.0.1:8787 when you run the exe or `python server.py`.

## Where the file goes

| You open the page on | The file is written to |
| --- | --- |
| The PC running `server.py` or the exe | That PC's save folder, as a faststart MP4 |
| A phone pointed at that PC | Still the PC. Use the finished-row link for a copy |
| Render, Chrome or Edge, short clip | The folder you pick, as a faststart MP4. The server copy is deleted |
| Render, Chrome or Edge, long VOD | The folder you pick, as `.ts`. Nothing stays on the server |

`downloads/` inside the repo only keeps `.gitkeep`. Do not put videos there.

## Phone, and why there is no APK

This project does not ship an APK. A real on-phone downloader would need Python, yt-dlp, and FFmpeg inside Android, plus the Android SDK to compile. A WebView app would only open this website. The download would still run on the machine that hosts the server.

The phone path:

1. On the PC, run `python server.py --host 0.0.0.0 --port 8787`.
2. On the phone, open `http://<pc-ip>:8787` in Chrome.
3. Use Add to Home screen. That icon is not an APK. Files still save on the PC.

## What each request does

| Method and path | What it does |
| --- | --- |
| `GET /` | Serves `web/index.html` |
| `GET /api/health` | `{ffmpeg, folder, cloud}`. Locally `cloud` is `false` |
| `POST /api/extract` | Raw `.docx` bytes. `X-Filename` must end in `.docx`. Returns `{links}` |
| `POST /api/download` | JSON `{urls, quality, folder}`. Starts one local job. `409` if a job is already running |
| `GET /api/cloud_stream` | One Twitch URL. Short clip: temp faststart MP4, then delete. Long VOD: MPEG-TS pipe. `400` for any other URL |
| `GET /api/job` | `{running, paused, message, fraction, rows}` |
| `POST /api/pause` | Holds the worker until resume |
| `POST /api/resume` | Lets the worker continue |
| `POST /api/cancel` | Stops the job. The page sends this on `pagehide` |
| `GET /api/file?name=` | Sends one file from the current save folder, by basename only. The original stays |

One job at a time. The job lives in memory. Restarting the server clears the list. It does not delete MP4s.

## How a video is saved on the PC

1. `link_extractor.py` opens the `.docx` and walks body, tables, headers, and footers.
2. It reads visible text and real hyperlink targets. Two URLs in one paragraph both count.
3. Accepted shapes: `twitch.tv/videos/{id}`, `twitch.tv/{channel}/v/{id}`, `twitch.tv/.../clip/{slug}`, `twitch.tv/clip/{slug}`, `clips.twitch.tv/{slug}`. Query strings and fragments are removed. `/channel/v/{id}` becomes `https://www.twitch.tv/videos/{id}`.
4. `formats.py` maps the label to `bestvideo[height<=N]+bestaudio/best[height<=N]`. The merge format is mp4.
5. `downloader.py` asks yt-dlp for the id without downloading. If `{id}.mp4` exists, is larger than 0 bytes, and has no sibling `{id}*.part` or `{id}*.ytdl`, that row is `already saved`.
6. Otherwise yt-dlp downloads into the save folder and FFmpeg merges with `-movflags +faststart`. The kept file is the merged `.mp4` whose name does not contain `.f`.
7. Options: `restrictfilenames`, `windowsfilenames`, `noplaylist`, two retries, a 30 second socket timeout, and `continuedl`.

VOD ids look like `v2896051202`. Clip ids are the slug or number yt-dlp reports. A `.part` next to an MP4 means that video is not finished, so it resumes instead of being skipped.

Pause blocks inside the progress hook and between videos. It does not cut a fragment in half. The first lookup of a URL can still finish before the first pause tick.

## The page

`web/index.html` is the only frontend. There is no `frontend-preview` folder.

* Hash routes: `#/home` and `#/about`.
* Theme key: `localStorage` `twitchbatch-theme`. Default is dark. The button says "Light mode" while the page is dark.
* Fonts come from Google Fonts: Chakra Petch, Space Grotesk, JetBrains Mono.
* The status card title is BATCHCAST. The header name is TWITCHBATCH.
* Cubes are 360px on a desktop. At 1100px the stats wrap. At 760px the cubes shrink to the screen.
* `prefers-reduced-motion` turns the motion off.
* PAUSE JOB is wired to the server. Closing the card does not stop the download. Refresh does.

`app.py` is the older Streamlit screen. `streamlit run app.py` still starts it. The product path is `server.py`. Do not import `app.py` from `server.py`.

## Every project file

| File | Role |
| --- | --- |
| `server.py` | The app. Page, local batch, and `/api/cloud_stream`. Port 8787. Host `127.0.0.1` unless you pass `--host` |
| `web/index.html` | The page |
| `link_extractor.py` | `.docx` to Twitch URLs. The name must stay. A file named `extractor.py` is hidden by yt-dlp |
| `downloader.py` | One URL, one faststart MP4, progress text, and the MPEG-TS pipe used for a long cloud VOD |
| `formats.py` | 1080p, 720p, and 480p |
| `app.py` | Old Streamlit UI |
| `requirements.txt` | `streamlit==1.65.0`, `python-docx==1.2.0`, `yt-dlp==2026.8.19` |
| `Dockerfile` | Render image. Installs FFmpeg, upgrades yt-dlp, and starts `server.py --host 0.0.0.0` |
| `.dockerignore` | Keeps the virtual environment, build output, and videos out of the image |
| `TwitchBatch.spec` | PyInstaller recipe. Keep this in Git |
| `rebuild.bat` | Stops `TwitchBatch.exe`, deletes `build/` and `dist/`, and builds a new exe from the spec |
| `dist/TwitchBatch.exe` | Built app. Not committed |
| `downloads/.gitkeep` | Keeps the empty folder |
| `.gitignore` | Ignores `.venv/`, bytecode, secrets, videos, `build/`, and `dist/` |
| `README.md` | The start page |
| `CONTRIBUTING.md` | Push steps and issues |
| `CODE_OF_CONDUCT.md` | How to behave in the repo |
| `.github/workflows/check.yml` | Installs requirements, compiles the Python files, and extracts two sample links. It does not download a video |
| `.github/ISSUE_TEMPLATE/bug_report.md` | Bug report |
| `.github/ISSUE_TEMPLATE/feature_request.md` | Feature request |
| `guide.md` | This file |

PyInstaller is a build tool. It is installed in `.venv` and is not listed in `requirements.txt`.

## Build the exe again

```powershell
.\rebuild.bat
```

Or:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean TwitchBatch.spec
```

The result is `dist\TwitchBatch.exe`. The spec packs `web/index.html` and collects `yt_dlp` and `docx`. When the exe is frozen, the page is read from the PyInstaller temp folder. The exe opens the local page about 1.5 seconds after it starts.

## Put it on GitHub

The remote is https://github.com/Himanshu-5680/TwitchBatch.git. Do not commit `.mp4`, `.env`, or `dist\`.

```powershell
git add .
git status
git commit -m "Describe the change"
git push
```

Full rules are in `CONTRIBUTING.md`.

## When something fails

| What you see | What it means |
| --- | --- |
| Only `.docx` | The file is an old `.doc` or not a Word file |
| FFmpeg is not on PATH | Install FFmpeg and start the server again. A running process does not see a PATH change |
| Pick a folder outside this project | The save path is this repo or a folder inside it |
| A long cloud VOD will not seek in Windows Media Player | It is a `.ts` file. Open it in VLC. Use the local server for a faststart MP4 |
| The Render page does not use the local exe | The browser blocks HTTPS-to-HTTP. Open `http://127.0.0.1:8787` |
| Firefox or Safari does nothing on cloud Download all | There is no folder picker. The page does not fake a finished download |
| The exe shows old behavior | Run `rebuild.bat` |
| A batch is already running | One job at a time. Wait, pause, or refresh |
| Stopped | Refresh cancelled the job. Upload again. A `.part` file can resume |
| Port already in use | The exe and `python server.py` both want 8787. Close one |
| Windows blocks the exe | Unsigned file. Run it only if you trust this copy |
| Private or login-only video | Out of scope. The row fails and the next link still runs |
| The card says paused but the file grows for a moment | Pause waits for the next progress tick |

## Limits

* No login, no cookies, no subscriber bypass.
* No old `.doc` support.
* A cloud VOD is `.ts`. A cloud clip is a faststart MP4 only when it is under 3 minutes and under 400 MB.
* A public HTTPS page cannot call `http://127.0.0.1:8787`.
* The on-screen list dies on refresh. The files do not.
* A live stream can be stopped with refresh. It is not a finished MP4 until yt-dlp closes it.
* The height you pick is a ceiling. A 720p-only video still downloads when 1080p is selected.
* Google Fonts need a network the first time the page loads. The download itself does not use those fonts.

Profile: https://github.com/Himanshu-5680. Download engine: https://github.com/yt-dlp/yt-dlp. Twitch is a trademark of its owner.
