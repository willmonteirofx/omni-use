@echo off
REM Downloads the vision projector of Qwen3.5-9B (~920 MB) from
REM https://huggingface.co/unsloth/Qwen3.5-9B-GGUF. With it llama-server
REM accepts images, so the model SEES the screenshot (with OmniParser's
REM numbered boxes drawn on it), not only the list of elements.
setlocal
set MODELS_DIR=%~dp0..\models
if not exist "%MODELS_DIR%" mkdir "%MODELS_DIR%"
curl -L --fail -C - -o "%MODELS_DIR%\mmproj-qwen3.5-9b-f16.gguf.part" ^
  "https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/mmproj-F16.gguf"
if errorlevel 1 (
  echo Download failed - run this script again to resume.
  pause
  exit /b 1
)
move /y "%MODELS_DIR%\mmproj-qwen3.5-9b-f16.gguf.part" "%MODELS_DIR%\mmproj-qwen3.5-9b-f16.gguf" >nul
echo.
echo Downloaded to %MODELS_DIR%\mmproj-qwen3.5-9b-f16.gguf
pause
