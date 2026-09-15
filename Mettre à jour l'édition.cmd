@echo off
rem Fabrique l'édition du jour sur cet ordinateur (collecte, regroupement, rédaction, publication
rem dans docs/). L'application de bureau la lit au démarrage.
chcp 65001 >nul
cd /d "%~dp0pipeline"
if not exist ".venv\Scripts\python.exe" (
  echo L'environnement Python manque : voir « Faire tourner les étapes 1 à 5 » dans README.md.
  pause
  exit /b 1
)
if not exist ".env" (
  echo Le fichier pipeline\.env manque : copie .env.exemple en .env et colle une clé d'API.
  pause
  exit /b 1
)
set PYTHONUTF8=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
".venv\Scripts\python.exe" edition.py
echo.
echo Terminé. Ouvre (ou rouvre) Actu quotidienne : la nouvelle édition se charge au démarrage.
pause
