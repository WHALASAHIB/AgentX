@echo off
REM Auto-start Hermes Agent Dashboard
cd /d C:\Users\nryur
set HERMES_DASHBOARD_BASIC_AUTH_USERNAME=whala
set HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=agentx2026
hermes dashboard --host 0.0.0.0 --port 9119 --no-open
