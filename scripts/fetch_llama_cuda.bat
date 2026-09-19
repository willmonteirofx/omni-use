@echo off
REM Downloads the official prebuilt llama.cpp (llama-server) with CUDA 12.4
REM for NVIDIA GPUs into bin\llama\, plus the CUDA runtime DLLs it needs.
REM Release: https://github.com/ggml-org/llama.cpp/releases/tag/b11040
setlocal
set ROOT=%~dp0..
set TAG=b11040
set BASE=https://github.com/ggml-org/llama.cpp/releases/download/%TAG%
if not exist "%ROOT%\bin\llama" mkdir "%ROOT%\bin\llama"

for %%Z in (llama-%TAG%-bin-win-cuda-12.4-x64.zip cudart-llama-bin-win-cuda-12.4-x64.zip) do (
  curl -L --fail -C - -o "%TEMP%\%%Z" "%BASE%/%%Z"
  if errorlevel 1 (
    echo Download of %%Z failed - run this script again to resume.
    pause
    exit /b 1
  )
  tar -xf "%TEMP%\%%Z" -C "%ROOT%\bin\llama"
  del "%TEMP%\%%Z"
)

echo.
echo Installed to %ROOT%\bin\llama
pause
