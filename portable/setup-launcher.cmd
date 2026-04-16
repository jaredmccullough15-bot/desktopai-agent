@echo off
setlocal
rem Launcher to run setup.ps1 from the USB root
pushd "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\desktop-ai-agent\setup.ps1"
popd
endlocal
