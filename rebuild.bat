@echo off
cd /d "%~dp0"
echo Stopping any running TwitchBatch processes...
taskkill /F /IM TwitchBatch.exe /T 2>nul

echo Cleaning old build files...
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

echo Building fresh TwitchBatch.exe...
echo TwitchBatch.spec packs the page, yt-dlp, and python-docx into the exe.
if exist ".venv\Scripts\pyinstaller.exe" (
  ".venv\Scripts\pyinstaller.exe" --noconfirm --clean TwitchBatch.spec
) else (
  pyinstaller --noconfirm --clean TwitchBatch.spec
)
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)

echo Done! New exe is ready in dist\TwitchBatch.exe
pause
