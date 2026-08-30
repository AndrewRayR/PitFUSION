@echo off
echo Starting PitFUSION web server...
echo.
echo Open your browser to: http://localhost:8080/PitFUSION.html
echo.
echo Starting local opponent intel bridge...
echo.
echo Press Ctrl+C to stop the server.
echo.
if exist ".env" (
  start "PitFUSION Intel Bridge" cmd /k python tools\lovat_mesh_bridge.py
) else (
  echo [WARN] No .env file found. Bridge will start but may not validate intel until configured.
  start "PitFUSION Intel Bridge" cmd /k python tools\lovat_mesh_bridge.py
)
start "" "http://localhost:8080/PitFUSION.html"
python -m http.server 8080
pause
