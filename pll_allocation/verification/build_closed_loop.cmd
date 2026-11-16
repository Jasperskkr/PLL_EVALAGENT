@echo off
rem Compatibility alias; use build_phase_step.cmd.
call "%~dp0build_phase_step.cmd" %*
exit /b %errorlevel%
