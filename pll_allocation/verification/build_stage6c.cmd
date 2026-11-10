@echo off
setlocal
set "PLL_BUILD_DIR=%~dp0build_stage6c"
if not "%~1"=="" set "PLL_BUILD_DIR=%~f1"
if exist "%PLL_BUILD_DIR%" (
  echo Build destination already exists; choose a fresh directory.
  exit /b 2
)
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
mkdir "%PLL_BUILD_DIR%"
if errorlevel 1 exit /b 1
cl /nologo /O2 /EHsc /std:c++17 /LD "%~dp0stage6c_kernel.cpp" /Fo"%PLL_BUILD_DIR%\kernel.obj" /link /OUT:"%PLL_BUILD_DIR%\kernel.dll" /IMPLIB:"%PLL_BUILD_DIR%\kernel.lib"
if errorlevel 1 exit /b 1
python "%~dp0stage6c_identity.py" --build-dir "%PLL_BUILD_DIR%"
