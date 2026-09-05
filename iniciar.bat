@echo off
cd /d "%~dp0"
echo Iniciando SacaNotas...
echo.
py web\manage.py migrate --noinput
py web\manage.py recuperar_trabajos
echo.
echo   En este equipo:   http://localhost:8000
echo   Desde el telefono (mismo wifi):
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo   http://%%a:8000
echo.
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8000"
py web\manage.py runserver 0.0.0.0:8000 --noreload
