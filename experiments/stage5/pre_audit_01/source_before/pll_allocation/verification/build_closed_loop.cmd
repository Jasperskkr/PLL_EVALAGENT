@echo off
setlocal
set "PLL_STEP_BUILD=%~dp0build_stage4_1_r2"
if not "%~1"=="" set "PLL_STEP_BUILD=%~f1"
if exist "%PLL_STEP_BUILD%" exit /b 2
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
mkdir "%PLL_STEP_BUILD%"
cl /nologo /O2 /EHsc /std:c++17 /LD "%~dp0closed_loop_kernel.cpp" /Fo"%PLL_STEP_BUILD%\kernel.obj" /link /OUT:"%PLL_STEP_BUILD%\closed_loop.dll" /IMPLIB:"%PLL_STEP_BUILD%\kernel.lib"
if errorlevel 1 exit /b 1
python "%~dp0closed_loop_native.py" --record-build "%PLL_STEP_BUILD%"
