@echo off
REM Downloads the Whisper large-v3-turbo GGML model (~1.6 GB) from
REM https://huggingface.co/ggerganov/whisper.cpp into this project's
REM models\ folder. NOT run automatically - large download, run yourself.
setlocal
set MODELS_DIR=%~dp0..\models
if not exist "%MODELS_DIR%" mkdir "%MODELS_DIR%"

REM Downloads to .part first (so the app doesn't treat a half-downloaded
REM model as ready); -C - resumes if this was interrupted partway.
curl -L --fail -C - -o "%MODELS_DIR%\ggml-large-v3-turbo.bin.part" ^
  "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin"
if errorlevel 1 (
  echo Download failed - run this script again to resume.
  pause
  exit /b 1
)
move /y "%MODELS_DIR%\ggml-large-v3-turbo.bin.part" "%MODELS_DIR%\ggml-large-v3-turbo.bin" >nul

echo.
echo Downloaded to %MODELS_DIR%\ggml-large-v3-turbo.bin
pause
