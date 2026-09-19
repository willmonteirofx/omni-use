@echo off
REM Downloads Qwen3.5-9B (the most recent ~9B Qwen, instruct), quantized to
REM Q4_K_M GGUF (~5.7 GB), from https://huggingface.co/unsloth/Qwen3.5-9B-GGUF
REM Once downloaded, pick it in the command bar's settings (gear icon).
setlocal
set MODELS_DIR=%~dp0..\models
if not exist "%MODELS_DIR%" mkdir "%MODELS_DIR%"

REM Downloads to .part first (so the app doesn't list a half-downloaded
REM model); -C - resumes if this was interrupted partway.
curl -L --fail -C - -o "%MODELS_DIR%\qwen3.5-9b-q4_k_m.gguf.part" ^
  "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf"
if errorlevel 1 (
  echo Download failed - run this script again to resume.
  pause
  exit /b 1
)
move /y "%MODELS_DIR%\qwen3.5-9b-q4_k_m.gguf.part" "%MODELS_DIR%\qwen3.5-9b-q4_k_m.gguf" >nul

echo.
echo Downloaded to %MODELS_DIR%\qwen3.5-9b-q4_k_m.gguf
pause
