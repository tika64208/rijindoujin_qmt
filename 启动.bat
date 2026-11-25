@echo off
chcp 65001 >nul
title 竞价自动交易
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_all.ps1" %*
if "%~1"=="" pause