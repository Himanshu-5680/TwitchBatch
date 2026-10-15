# TwitchBatch

Put a Word file in. Get the Twitch videos out, one MP4 at a time, into your Downloads folder.

The page shows a status card the moment you click **Download all**: which video is playing through, the percent, how much has arrived, the speed, and the time left. Files never land inside this project folder. A video that is already saved is skipped.

Download only what you have the right to keep. TwitchBatch does not log in and does not bypass a subscriber wall. It is not an official Twitch product.

## Start in one minute

You need Python 3.10 or newer, and [FFmpeg](https://ffmpeg.org/download.html) on PATH. Older `.doc` files must be saved as `.docx` first.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python server.py
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787).

Prefer not to install Python on that PC? Double-click `dist\TwitchBatch.exe`. FFmpeg still has to be installed. The exe opens the same page. Windows may warn because the file is unsigned. Allow it only if you built it yourself or trust the copy.

The exe uses port 8787. Close `python server.py` before you double-click it, or the port is already taken.

## Use it

1. **Home.** Upload the `.docx`. The page lists every Twitch video and clip link it finds, including links behind other words, in tables, and in text boxes.
2. **One quality.** 1080p, 720p, or 480p MP4. That choice covers the whole list.
3. **Download all.** A card pops up at once. Leave it open. The table under the form keeps the same rows if you close the card.
4. **Files.** They save in the folder shown on the form. That starts as the Downloads folder of the person logged in on the computer running TwitchBatch.

Refresh the page to stop a long video or a live stream. The partial file stays, so the next run can resume. Upload the document again. Finished MP4s are skipped.

## Where the file actually goes

| You open the page on | The MP4 is written to |
| --- | --- |
| The same PC that runs the server or the exe | That PC's save folder |
| A phone, using the PC's address | Still the PC. Use the link on a finished row to keep a copy on the phone |

There is no Android APK. The downloader needs Python, yt-dlp, and FFmpeg, and this project does not ship those inside an installable phone app. On a phone, open the page in Chrome.

## Let another device open it

On the computer that should do the downloading:

```powershell
python server.py --host 0.0.0.0 --port 8787
```

On the other device, open `http://<that-computer-ip>:8787`.

## If something looks wrong

| What you see | What to do |
| --- | --- |
| Download all does nothing useful | The file must be `.docx`, and it must contain Twitch links |
| "FFmpeg is not on PATH" | Install FFmpeg, then start TwitchBatch again |
| "Pick a folder outside this project" | Choose Downloads, or any folder that is not this repo |
| The card says Stopped | A refresh ended the run. Upload the file again. The partial video can resume |
| The port is already in use | Something is already on 8787. Close the other TwitchBatch window |
| Windows blocks the exe | The file is unsigned. Run it only if you trust this copy |

## Build the exe again

From this folder, with the virtual environment on:

```powershell
pip install pyinstaller
pyinstaller --noconfirm --clean --onefile --name TwitchBatch --add-data "web/index.html;web" --collect-all yt_dlp --collect-all docx server.py
```

The new file is `dist\TwitchBatch.exe`.

## What it will not do

- Read an old binary `.doc` file
- Download a private or login-only video
- Keep the on-screen list after a refresh. Upload the file again
- Merge picture and sound without FFmpeg

Profile: [github.com/Himanshu-5680](https://github.com/Himanshu-5680). The download engine is [yt-dlp](https://github.com/yt-dlp/yt-dlp).

Every part of the app is written up in [guide.md](guide.md). Repository setup is in [CONTRIBUTING.md](CONTRIBUTING.md). The code of conduct is [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

Twitch is a trademark of its owner.
