@echo off
cd /d "%~dp0"
echo Iniciando Quenotas...
echo.
py web\manage.py migrate --noinput
if errorlevel 1 (
    echo.
    echo No se pudo preparar la base de datos. Revisa el error de arriba.
    pause
    exit /b 1
)
py web\manage.py recuperar_trabajos
echo.
echo   En este equipo:   http://localhost:8000
echo   Desde el telefono (mismo wifi):
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do for /f "tokens=1" %%b in ("%%a") do echo   http://%%b:8000
echo.
start "" cmd /c "timeout /t 3 >nul & start http://localhost:8000"
py web\manage.py runserver 0.0.0.0:8000 --noreload
pause
