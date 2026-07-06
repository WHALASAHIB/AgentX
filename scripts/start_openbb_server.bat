@echo off
REM Start OpenBB Data Server — supplementary market data via OpenBB + yfinance
REM Runs on port 8101 alongside the main backend (8005), MCP server (8100)
title OpenBB Data Server
cd /d C:\Trading
python openbb_server.py
pause
