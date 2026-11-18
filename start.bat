@echo off
rem Windows version of start.sh:   start.bat --demo
cd /d "%~dp0"
if not exist venv (
  echo [glyph] first run: setting up (about a minute)
  py -3 -m venv venv
)
call venv\Scripts\activate.bat
rem Install the libraries only when requirements.txt has changed since the last install.
fc /b requirements.txt venv\.requirements-installed >nul 2>&1
if errorlevel 1 (
  python -m pip install -q --upgrade pip
  pip install -q -r requirements.txt && copy /y requirements.txt venv\.requirements-installed >nul
)
if not exist .env (
  copy .env.example .env >nul
  echo [glyph] no key yet: put your Gemini key in .env (running with practice answers for now)
)
python run.py %*
