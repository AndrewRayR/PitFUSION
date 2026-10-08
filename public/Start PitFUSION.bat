@echo off
setlocal
set "ROOT=%~dp0.."

echo Starting PitFUSION...
echo.
echo Web app: http://localhost:8080/
echo Intel bridge: http://localhost:8090/api/next-match-intel
echo.

if not exist "%ROOT%\tools\lovat_mesh_bridge.py" (
  echo [WARN] Lovat bridge is not installed.
) else (
  if not exist "%ROOT%\.env" echo [WARN] No .env file found. The bridge will start, but production validation will remain unavailable.
  start "PitFUSION Intel Bridge" /D "%ROOT%" cmd /k python "tools\lovat_mesh_bridge.py"
)

start "" "http://localhost:8080/"
python -m http.server 8080 --directory "%ROOT%\public"
pause
