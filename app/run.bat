@echo off
REM 一键启动（接收方本机需有 Python 3.11+）
cd /d %~dp0
python -m pip install -r requirements.txt
python app.py
pause
