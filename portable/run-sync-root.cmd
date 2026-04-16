@echo off
setlocal
set "USBROOT=%~dp0"
set "DEST=%USBROOT%desktop-ai-agent"

REM If already extracted, run directly
if exist "%DEST%\portable\run-sync.ps1" goto RUN

REM Find a zip in root
set "ZIP1=%USBROOT%SmartSherpaSync-USB.zip"
set "ZIP2=%USBROOT%Desktop-AI-Agent-USB.zip"
set "ZIP3=%USBROOT%agent.zip"

set "ZIP="
if exist "%ZIP1%" set "ZIP=%ZIP1%"
if not exist "%ZIP1%" if exist "%ZIP2%" set "ZIP=%ZIP2%"
if not exist "%ZIP1%" if not exist "%ZIP2%" if exist "%ZIP3%" set "ZIP=%ZIP3%"

if not defined ZIP (
  echo Could not find an agent zip on this drive.
  echo Expected one of: SmartSherpaSync-USB.zip or Desktop-AI-Agent-USB.zip
  echo Please place the zip at the drive root, then re-run.
  pause
  exit /b 1
)

echo Extracting "%ZIP%" to "%USBROOT%"...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Try { Expand-Archive -Force -Path '%ZIP%' -DestinationPath '%USBROOT%' } Catch { Write-Output $_; Exit 1 }"

REM Verify extraction
if not exist "%DEST%" (
  if exist "%USBROOT%desktop-ai-agent" set "DEST=%USBROOT%desktop-ai-agent"
)

if not exist "%DEST%\portable\run-sync.ps1" (
  echo Extraction finished, but desktop-ai-agent folder not found.
  echo Please extract the zip manually, then rerun this file.
  pause
  exit /b 1
)

:RUN
echo Starting Smart Sherpa Sync...
powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File "%DEST%\portable\run-sync.ps1"
echo.
echo If nothing appears above, start Chrome in debug mode first.
echo (This window stays open so you can see logs.)
pause
endlocal
