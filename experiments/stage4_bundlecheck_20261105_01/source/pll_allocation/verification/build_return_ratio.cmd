@echo off
setlocal
set "PLL_RR_BUILD=%~dp0build_stage4"
if not "%~1"=="" set "PLL_RR_BUILD=%~f1"
if exist "%PLL_RR_BUILD%" exit /b 2
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
mkdir "%PLL_RR_BUILD%"
cl /nologo /O2 /EHsc /std:c++17 /LD "%~dp0return_ratio_kernel.cpp" /Fo"%PLL_RR_BUILD%\kernel.obj" /link /OUT:"%PLL_RR_BUILD%\return_ratio.dll" /IMPLIB:"%PLL_RR_BUILD%\kernel.lib"
if errorlevel 1 exit /b 1
python "%~dp0return_ratio_native.py" --record-build "%PLL_RR_BUILD%"
