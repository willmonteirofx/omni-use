@echo off
REM Downloads the OmniParser V2 weights (https://huggingface.co/microsoft/OmniParser-v2.0)
REM into models\omniparser (outside the omniparser submodule), same layout
REM as omniparser's README uses for its weights folder:
REM   weights\icon_detect\model.pt           (YOLO detector, ~40 MB)
REM   weights\icon_caption_florence\...      (Florence-2 captioner, ~1.1 GB)
REM plus the Florence-2-base processor files (tokenizer + code, a few MB)
REM that util/utils.py loads by name. Run scripts\install_agent.bat first.
REM The LLM is separate: scripts\download_qwen9b.bat (or 4b).
setlocal
set ROOT=%~dp0..
set HF_HOME=%ROOT%\models\hf
set W=%ROOT%\models\omniparser
call "%ROOT%\agent\.venv\Scripts\activate.bat"

for %%F in (icon_detect/model.pt icon_detect/model.yaml icon_detect/train_args.yaml icon_caption/config.json icon_caption/generation_config.json icon_caption/model.safetensors) do (
  huggingface-cli download microsoft/OmniParser-v2.0 %%F --local-dir "%W%"
  if errorlevel 1 goto fail
)
if exist "%W%\icon_caption_florence" rmdir /s /q "%W%\icon_caption_florence"
move "%W%\icon_caption" "%W%\icon_caption_florence" >nul

huggingface-cli download microsoft/Florence-2-base --include "*.json" "*.py" "*.txt"
if errorlevel 1 goto fail

echo.
echo OmniParser V2 weights are in %W%
pause
exit /b 0
:fail
echo Download failed - run this script again to resume.
pause
exit /b 1
