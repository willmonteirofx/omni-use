@echo off
REM Creates agent\.venv with PyTorch (CUDA 12.4 wheels, ~2.5 GB) and the
REM OmniParser V2 + agent dependencies from requirements.txt, then warms up
REM OmniParser's OCR models (easyocr/paddleocr fetch small models on first use).
REM Needs Python 3.12 on PATH.
setlocal
set ROOT=%~dp0..
cd /d "%ROOT%\agent"

if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 goto fail
pip install -r "%ROOT%\requirements.txt"
if errorlevel 1 goto fail

set EASYOCR_MODULE_PATH=%ROOT%\models\easyocr
cd /d "%ROOT%\omniparser"
python -c "import util.utils, easyocr, torch; easyocr.Reader(['pt', 'en']); print('OmniParser OK - CUDA:', torch.cuda.is_available())"
if errorlevel 1 goto fail

echo.
echo Done. Next: scripts\download_models.bat
pause
exit /b 0
:fail
echo Install failed - see the messages above.
pause
exit /b 1
