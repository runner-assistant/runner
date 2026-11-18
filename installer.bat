@echo off
rem Installe ou repare Runner : double-clic sur ce fichier.
rem Le vrai travail est fait par installer.ps1 (PowerShell, deja present sur Windows).
cd /d "%~dp0"
if not exist "%~dp0installer.ps1" (
    echo.
    echo  Le fichier installer.ps1 est introuvable.
    echo  Si tu as ouvert le zip sans le decompresser : clic droit sur le zip ^> Extraire tout,
    echo  puis lance installer.bat depuis le dossier extrait.
    echo.
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer.ps1"
