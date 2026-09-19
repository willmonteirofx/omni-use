@echo off
REM Downloads the default model, Qwen3.5-4B quantized to Q4_K_M GGUF (~2.6 GB),
REM from https://huggingface.co/enacimie/Qwen3.5-4B-Q4_K_M-GGUF
setlocal
set MODELS_DIR=%~dp0..\models
if not exist "%MODELS_DIR%" mkdir "%MODELS_DIR%"

REM Downloads to .part first (so the app doesn't list a half-downloaded
REM model); -C - resumes if this was interrupted partway.
curl -L --fail -C - -o "%MODELS_DIR%\qwen3.5-4b-q4_k_m.gguf.part" ^
  "https://huggingface.co/enacimie/Qwen3.5-4B-Q4_K_M-GGUF/resolve/main/qwen3.5-4b-q4_k_m.gguf"
if errorlevel 1 (
  echo Download failed - run this script again to resume.
  pause
  exit /b 1
)
move /y "%MODELS_DIR%\qwen3.5-4b-q4_k_m.gguf.part" "%MODELS_DIR%\qwen3.5-4b-q4_k_m.gguf" >nul

echo.
echo Downloaded to %MODELS_DIR%\qwen3.5-4b-q4_k_m.gguf
pause
