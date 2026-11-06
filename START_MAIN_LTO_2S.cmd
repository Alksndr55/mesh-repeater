@echo off
setlocal DisableDelayedExpansion
if not exist "%~dp0third_party\NexusBV\0.9\NexusBV.exe" goto missing
if not exist "%~dp0v1\output\current\MAIN\Mesh_Repeater_v1.26_MAIN_LTO_2S.cad" goto missing
if not exist "%~dp0v1\output\current\MAIN\MAIN_schematic.pdf" goto missing
start "" /D "%~dp0third_party\NexusBV\0.9" "%~dp0third_party\NexusBV\0.9\NexusBV.exe" "%~dp0v1\output\current\MAIN\Mesh_Repeater_v1.26_MAIN_LTO_2S.cad" "%~dp0v1\output\current\MAIN\MAIN_schematic.pdf"
if errorlevel 1 goto failed
exit /b 0
:missing
echo Required files are missing. Extract the complete ZIP before starting.
pause
exit /b 1
:failed
echo NexusBV could not start.
pause
exit /b 1
