# TwitchBatch guide

TwitchBatch reads a Word `.docx`, finds Twitch video and clip links, and downloads them one by one as MP4 files. The computer that runs the server is the computer that writes the files. The page is not an official Twitch product. Download only videos you have the right to keep. The app does not log in and does not bypass a subscriber wall.

## Start

You need Python 3.10 or newer and FFmpeg on PATH. This machine uses the project virtual environment and FFmpeg 9 from winget.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server.py
```

Open http://127.0.0.1:8787.

`python3` on this Windows PC is a broken Store alias. Use `.\.venv\Scripts\python.exe` if `python` is not the virtual environment.

To let a phone or another PC open the page, while the downloads still happen on this computer:

```powershell
python server.py --host 0.0.0.0 --port 8787
```

Then open `http://<this-pc-ip>:8787`.

The other way to start is `dist\TwitchBatch.exe`. It opens the same page on port 8787. Close `python server.py` first, or the port is already taken. FFmpeg is not inside the exe. Windows may warn because the exe is unsigned. Allow it only if you built it or trust the copy.

## Use the page

1. Home. Choose a `.docx`. Old binary `.doc` files are rejected. Save them as `.docx` first. The upload limit is 25 MB.
2. The page lists every Twitch video and clip it finds. One quality applies to the whole list: 1080p MP4, 720p MP4, or 480p MP4. The default is 1080p.
3. The save folder starts as the Downloads folder of whoever is logged in (`Path.home() / "Downloads"`). On this PC that is `C:\Users\HimanshuG\Downloads`. You can change it. A folder inside this project is rejected.
4. Download all opens the BATCHCAST status card. It shows which video, the percent, size, speed, and time left.
5. PAUSE JOB tells the server to wait at the next progress update. RESUME continues the same file. Refresh sends cancel. The partial file stays and the next upload can resume it. Refresh also clears the on-screen list, so upload the document again. Finished MP4s are skipped.

A finished row has a link, `/api/file?name=...`, so a phone can copy that one MP4. The original file is still on the PC.

## Where the MP4 goes

| You open the page on | The file is written to |
| --- | --- |
| The PC running `server.py` or the exe | That PC's save folder |
| A phone pointed at that PC | Still the PC. Use the finished-row link for a phone copy |

`downloads/` inside the repo only keeps `.gitkeep`. Do not put videos there.

## Phone, and why there is no APK in this folder

This PC has no Java and no Android SDK, so an `.apk` cannot be compiled here. A real on-phone downloader would also need Python, yt-dlp, and FFmpeg inside Android. A WebView or Trusted Web Activity APK would only open this website. The download would still run on the machine that hosts the server.

The fast phone path:

1. Run `python server.py --host 0.0.0.0 --port 8787` on the PC.
2. On the phone, open `http://<pc-ip>:8787` in Chrome.
3. Use Add to Home screen. That gives an icon. It is not an APK, and files still save on the PC.

An installable wrapper only makes sense after the site has a public HTTPS address. [Bubblewrap](https://github.com/GoogleChromeLabs/bubblewrap) can then build a Trusted Web Activity. That still needs the Android SDK, and it still does not move yt-dlp onto the phone.

## What each request does

| Method and path | What it does |
| --- | --- |
| `GET /` | Serves `web/index.html` |
| `GET /api/health` | `{ffmpeg, folder}`. `folder` is the default Downloads path |
| `POST /api/extract` | Raw `.docx` bytes. Header `X-Filename` must end in `.docx`. Returns `{links}` |
| `POST /api/download` | JSON `{urls, quality, folder}`. Starts one background job. 409 if a job is already running |
| `GET /api/job` | `{running, paused, message, fraction, rows}` |
| `POST /api/pause` | Holds the worker until resume |
| `POST /api/resume` | Lets the worker continue |
| `POST /api/cancel` | Stops the job. The page sends this with `sendBeacon` on `pagehide` |
| `GET /api/file?name=` | Streams one finished file from the current job's folder, by basename only |

One job at a time. The job lives in memory. Restarting the server clears the list. It does not delete MP4s.

## How a video is saved

1. `link_extractor.py` opens the `.docx` and walks body, headers, and footers.
2. It reads visible text and real hyperlink targets. Two URLs in one paragraph both count.
3. Accepted shapes: `twitch.tv/videos/{id}`, `twitch.tv/{channel}/v/{id}`, `twitch.tv/.../clip/{slug}`, `twitch.tv/clip/{slug}`, `clips.twitch.tv/{slug}`. Query strings and fragments are removed. `/channel/v/{id}` becomes `https://www.twitch.tv/videos/{id}`.
4. `formats.py` maps the label to a yt-dlp selector. `bestvideo[height<=N]+bestaudio/best[height<=N]` means that height or the closest lower one. The merge format is mp4.
5. `downloader.py` asks yt-dlp for the id without downloading. If `{id}.mp4` exists, is larger than 0 bytes, and has no sibling `{id}*.part` or `{id}*.ytdl`, that row is `already saved`.
6. Otherwise yt-dlp downloads to `{folder}\{id}.ext`, continues a partial file, and FFmpeg merges picture and sound. The kept file is the merged `.mp4` whose name does not contain `.f`.
7. Output options: `restrictfilenames`, `windowsfilenames`, `noplaylist`, two retries, 30 second socket timeout, `continuedl`.

VOD ids look like `v2896051202`. Clip ids are the clip slug or a number, whichever yt-dlp reports. A `.part` next to an MP4 means that video is not finished and will resume, not skip.

Pause blocks inside the progress hook and between videos. It does not cut a fragment in half. The first lookup of a URL can still finish before the first pause tick.

## The page

`web/index.html` is the only frontend. There is no second copy and no `frontend-preview` folder.

- Hash routes: `#/home` and `#/about`.
- Theme key: `localStorage` `twitchbatch-theme`. Default is dark. The button says "Light mode" while the page is dark.
- Fonts come from Google Fonts: Chakra Petch, Space Grotesk, JetBrains Mono.
- The status card title is BATCHCAST. The header name is TWITCHBATCH.
- Cubes are 360px on a desktop. At 1100px the stats wrap. At 760px the cubes shrink to the screen and the results table becomes stacked rows.
- `prefers-reduced-motion` turns the motion off.
- The folder box stays the word `Downloads` until health returns the real path.
- PAUSE JOB is wired to the server. Closing the card does not stop the download. Refresh does.

`app.py` is the older Streamlit screen. It still runs with `streamlit run app.py`, but the product path is `server.py`. Do not import `app.py` from `server.py`. Streamlit starts as soon as that file is imported.

## Every project file

| File | Role |
| --- | --- |
| `server.py` | The app. Serves the page and the API. Port 8787. Host `127.0.0.1` unless you pass `--host` |
| `web/index.html` | The page |
| `link_extractor.py` | `.docx` to Twitch URLs. The name must stay `link_extractor`. A file named `extractor.py` is hidden by yt-dlp |
| `downloader.py` | One URL, one MP4, progress text |
| `formats.py` | The three qualities |
| `app.py` | Old Streamlit UI. Not the main page |
| `requirements.txt` | `streamlit==1.65.0`, `python-docx==1.2.0`, `yt-dlp==2026.8.19` |
| `TwitchBatch.spec` | PyInstaller recipe. Keep this in Git |
| `dist/TwitchBatch.exe` | Built app. Not committed |
| `downloads/.gitkeep` | Keeps the empty folder. Videos do not belong here |
| `.gitignore` | Ignores `.venv/`, bytecode, `.env`, secrets, `downloads/*` except `.gitkeep`, `*.mp4`, `*.part`, `*.ytdl`, `build/`, `dist/`, and OS junk |
| `README.md` | Short start page |
| `CONTRIBUTING.md` | Push steps, issues, and the phone shortcut |
| `CODE_OF_CONDUCT.md` | How to behave in the repo |
| `.github/workflows/check.yml` | On push and pull request: install requirements, compile the Python files, extract two sample links. It does not download a video and does not need FFmpeg |
| `.github/ISSUE_TEMPLATE/bug_report.md` | Bug report |
| `.github/ISSUE_TEMPLATE/feature_request.md` | Feature request |
| `guide.md` | This file |

PyInstaller is a build tool. It is installed in `.venv` and is not listed in `requirements.txt`.

## Build the exe again

From this folder, with the virtual environment:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean TwitchBatch.spec
```

The result is `dist\TwitchBatch.exe`. The spec packs `web/index.html` and collects `yt_dlp` and `docx`. When the exe is frozen, the page is read from the PyInstaller temp folder and the project root is the folder that contains the exe, so a save path next to the exe is still rejected if it is that folder.

## Put it on GitHub

This folder may not have a Git remote yet. Do not commit `.mp4`, `.env`, or `dist\`.

```powershell
git init
git add .
git status
git commit -m "Add TwitchBatch local downloader"
git branch -M main
```

Create an empty repository under https://github.com/Himanshu-5680. Do not let GitHub add a README, or the first push conflicts. Then:

```powershell
git remote add origin https://github.com/Himanshu-5680/TwitchBatch.git
git push -u origin main
```

Use the repository name you actually created. Later: `git add .`, `git commit`, `git push`. Full rules are in `CONTRIBUTING.md`.

## When something fails

| What you see | What it means |
| --- | --- |
| Only `.docx` | The file is an old `.doc` or not a Word file |
| FFmpeg is not on PATH | Install FFmpeg and start the server again. A running process does not see a PATH change |
| Pick a folder outside this project | The save path is this repo or a folder inside it |
| A batch is already running | One job at a time. Wait, pause, or refresh |
| Stopped | Refresh cancelled the job. Upload again. A `.part` file can resume |
| Port already in use | The exe and `python server.py` both want 8787. Close one |
| Windows blocks the exe | Unsigned file. Run it only if you trust this copy |
| Private or login-only video | Out of scope. The row fails and the next link still runs |
| Card says Paused but the file grows for a moment | Pause waits for the next progress tick |

## Limits

- No login, no cookies, no subscriber bypass.
- No old `.doc` support.
- The on-screen list dies on refresh. The files do not.
- Live streams can be stopped with refresh. They are not a finished MP4 until yt-dlp closes them.
- The height you pick is a ceiling. A 720p-only video still downloads when 1080p is selected.
- Google Fonts need a network the first time the page loads. The download itself does not use those fonts.

Profile: https://github.com/Himanshu-5680. Download engine: https://github.com/yt-dlp/yt-dlp. Twitch is a trademark of its owner.
