@echo off
rem Desinstalle Runner : double-clic sur ce fichier.
rem Le vrai travail est fait par desinstaller.ps1, lance depuis une copie dans le dossier
rem temporaire (pour pouvoir supprimer le dossier de Runner, celui-ci compris).
if not exist "%~dp0desinstaller.ps1" (
    echo.
    echo  Le fichier desinstaller.ps1 est introuvable.
    echo.
    pause
    exit /b 1
)
copy /y "%~dp0desinstaller.ps1" "%TEMP%\runner_desinstaller.ps1" >nul
start "Runner - desinstallation" powershell -NoProfile -ExecutionPolicy Bypass -File "%TEMP%\runner_desinstaller.ps1" -Dossier "%~dp0."
exit
