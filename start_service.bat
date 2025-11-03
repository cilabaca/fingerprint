@echo off
REM Script para iniciar ZKTeco Bridge Service
REM Puede ejecutarse sin permisos de administrador

title ZKTeco Bridge Service

echo ========================================
echo ZKTeco USB Bridge Service
echo ========================================
echo.
echo Iniciando servicio en puerto 5000...
echo Presione Ctrl+C para detener
echo.
echo ========================================
echo.

REM Verificar si Python está disponible
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Python no encontrado
    echo Instale Python 3.8+ desde https://www.python.org
    pause
    exit /b 1
)

REM Verificar si el archivo existe
if not exist "bridge_service.py" (
    echo ERROR: bridge_service.py no encontrado
    echo Asegurese de estar en el directorio correcto
    pause
    exit /b 1
)

REM Iniciar el servicio
python bridge_service.py

REM Si el servicio termina, mostrar mensaje
echo.
echo ========================================
echo Servicio detenido
echo ========================================
pause