@echo off
REM 在 Windows 上把 dterrain 打包为单个 exe
REM 前提：已安装 Python 3.9+；ffmpeg.exe / ffprobe.exe 已放入项目根目录的 bin 目录
setlocal
cd /d "%~dp0.."

python -m pip install -r requirements.txt pyinstaller || exit /b 1

if not exist "binfmpeg.exe" (
  echo [错误] 缺少 binfmpeg.exe，请从 https://www.gyan.dev/ffmpeg/builds/ 下载后放入 bin 目录
  exit /b 1
)
if not exist "binfprobe.exe" (
  echo [错误] 缺少 binfprobe.exe，请从 https://www.gyan.dev/ffmpeg/builds/ 下载后放入 bin 目录
  exit /b 1
)

python -m PyInstaller --noconfirm --clean --onefile --name dterrain ^
  --add-data "binfmpeg.exe;bin" ^
  --add-data "binfprobe.exe;bin" ^
  --paths dterrain ^
  main.py

echo.
echo 打包完成，产物在 distdterrain.exe
endlocal
