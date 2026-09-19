@echo off
REM Downloads the official prebuilt whisper.cpp with CUDA 12 (NVIDIA GPU) into
REM bin\whisper\. The CPU-only build (scripts\build_whisper.bat) takes ~30 s
REM per short clip with large-v3-turbo; on the GPU it's about a second.
REM Release: https://github.com/ggml-org/whisper.cpp/releases/tag/b5130
setlocal
set ROOT=%~dp0..
set ZIP=%TEMP%\whisper-cublas-12.4.0-bin-x64.zip

curl -L --fail -C - -o "%ZIP%" ^
  "https://github.com/ggml-org/whisper.cpp/releases/download/b5130/whisper-cublas-12.4.0-bin-x64.zip"
if errorlevel 1 (
  echo Download failed - run this script again to resume.
  pause
  exit /b 1
)
if not exist "%ROOT%\bin\whisper" mkdir "%ROOT%\bin\whisper"
tar -xf "%ZIP%" -C "%ROOT%\bin\whisper"
REM The zip wraps everything in Release\ - flatten it.
move /y "%ROOT%\bin\whisper\Release\*" "%ROOT%\bin\whisper\" >nul
rmdir "%ROOT%\bin\whisper\Release"
del "%ZIP%"
echo.
echo Installed to %ROOT%\bin\whisper
pause
