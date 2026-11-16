@echo off
setlocal
set "PLL_STEP_BUILD=%~dp0build_phase_step"
if not "%~1"=="" set "PLL_STEP_BUILD=%~f1"
if exist "%PLL_STEP_BUILD%" exit /b 2
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
mkdir "%PLL_STEP_BUILD%"
cl /nologo /O2 /EHsc /std:c++17 /LD "%~dp0phase_step_kernel.cpp" /Fo"%PLL_STEP_BUILD%\kernel.obj" /link /OUT:"%PLL_STEP_BUILD%\phase_step.dll" /IMPLIB:"%PLL_STEP_BUILD%\kernel.lib"
if errorlevel 1 exit /b 1
python "%~dp0phase_step_native.py" --record-build "%PLL_STEP_BUILD%"
