# Start Chrome in Debug Mode with Temporary Profile
# This ensures debug port opens reliably

Write-Host "Closing all Chrome instances..." -ForegroundColor Yellow

# Close all Chrome processes
Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

# Wait for Chrome to fully close
Start-Sleep -Seconds 3

Write-Host "Starting Chrome with remote debugging..." -ForegroundColor Green

# Use a dedicated debug profile to avoid conflicts
$debugProfile = "$env:TEMP\chrome-agent-debug"

# Start Chrome with debugging enabled
Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList "--remote-debugging-port=9222 --user-data-dir=`"$debugProfile`""

Start-Sleep -Seconds 5

Write-Host "Chrome is now running in debug mode!" -ForegroundColor Green
Write-Host "Your AI agent can now control Chrome using Selenium." -ForegroundColor Cyan
Write-Host ""
Write-Host "Note: Using a separate profile for automation." -ForegroundColor Yellow
Write-Host "You can manually log into sites in this Chrome window." -ForegroundColor Yellow
