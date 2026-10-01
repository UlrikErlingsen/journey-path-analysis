@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 (
  echo Trace Signal needs Python 3.10 or newer.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  echo Creating Trace Signal's private Python environment...
  py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
if not defined ARROW_DEFAULT_MEMORY_POOL set ARROW_DEFAULT_MEMORY_POOL=system
for /f %%H in ('powershell -NoProfile -Command "(Get-FileHash requirements.txt -Algorithm SHA256).Hash.ToLower()"') do set REQ_HASH=%%H
if not exist .venv\.tracesignal-requirements-%REQ_HASH% (
  echo First launch: downloading packages. Later launches will be faster.
  python -m pip --disable-pip-version-check install --prefer-binary -r requirements.txt
  del /q .venv\.tracesignal-requirements-* .venv\.tracesignal-ready 2>nul
  type nul > .venv\.tracesignal-requirements-%REQ_HASH%
)
if not defined TRACESIGNAL_PORT set TRACESIGNAL_PORT=8585
if not defined TRACESIGNAL_MAX_UPLOAD_MB set TRACESIGNAL_MAX_UPLOAD_MB=50
python -m streamlit run app.py --server.headless=false --server.address=127.0.0.1 --server.port=%TRACESIGNAL_PORT% --server.maxUploadSize=%TRACESIGNAL_MAX_UPLOAD_MB% --server.fileWatcherType=none --browser.gatherUsageStats=false
