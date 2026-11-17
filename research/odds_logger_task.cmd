@echo off
rem Scheduled every 15 min by Windows Task Scheduler (task name: ThunderedgeOddsLogger)
cd /d "%~dp0.."
".venv\Scripts\python.exe" -m research.odds_logger >> "data\odds_logger.log" 2>&1
".venv\Scripts\python.exe" -m research.gap_detector >> "data\odds_logger.log" 2>&1
