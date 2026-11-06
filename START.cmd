@echo off
setlocal DisableDelayedExpansion
echo Mesh Repeater v1.26 - NexusBV 0.9
echo.
echo 1. MAIN - NaIon_COLD
echo 2. MAIN - LTO_2S
echo Q. Exit
choice /C 12Q /N /M "Open boardview: "
if errorlevel 255 exit /b 1
if errorlevel 3 exit /b 0
if errorlevel 2 goto board2
if errorlevel 1 goto board1
exit /b 1
:board1
if not exist "%~dp0START_MAIN_NaIon_COLD.cmd" goto missing
"%~dp0START_MAIN_NaIon_COLD.cmd"
exit /b
:board2
if not exist "%~dp0START_MAIN_LTO_2S.cmd" goto missing
"%~dp0START_MAIN_LTO_2S.cmd"
exit /b
:missing
echo Extract the complete ZIP before starting.
pause
exit /b 1
