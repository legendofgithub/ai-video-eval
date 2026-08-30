@echo off
REM Web front-end launcher: FastAPI + static page at http://127.0.0.1:8765
cd /d %~dp0
python -m pip install -r requirements.txt
python server.py
pause
