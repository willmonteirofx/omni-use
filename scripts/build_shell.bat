@echo off
REM Builds the Tauri shell (the floating input). Plain Tauri/WebView2, no CEF.
setlocal
cd /d "%~dp0..\shell"
cargo build --release
pause
