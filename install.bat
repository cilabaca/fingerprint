@echo off
REM Script de instalación para ZKTeco Bridge Service
REM Ejecutar como Administrador

echo ========================================
echo ZKTeco Bridge Service - Instalador
echo ========================================
echo.

REM Verificar permisos de administrador
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Debe ejecutar como Administrador
    echo Haga clic derecho y seleccione "Ejecutar como administrador"
    pause
    exit /b 1
)

echo [1/6] Verificando Python...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Python no encontrado
    echo Descargue e instale Python 3.8+ desde: https://www.python.org/downloads/
    pause
    exit /b 1
)

python --version
echo Python detectado correctamente!
echo.

echo [2/6] Verificando pip...
pip --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: pip no encontrado
    echo Instalando pip...
    python -m ensurepip --upgrade
)

pip --version
echo.

echo [3/6] Instalando dependencias...
pip install -r requirements.txt
if %errorLevel% neq 0 (
    echo ERROR: Fallo al instalar dependencias
    pause
    exit /b 1
)
echo Dependencias instaladas correctamente!
echo.

echo [4/6] Verificando ZKFingerSDK...
if exist "C:\Windows\System32\libzkfp.dll" (
    echo [OK] libzkfp.dll encontrada en System32
) else if exist "C:\Windows\SysWOW64\libzkfp.dll" (
    echo [OK] libzkfp.dll encontrada en SysWOW64
) else (
    echo [ADVERTENCIA] libzkfp.dll NO encontrada
    echo.
    echo Por favor instale ZKFingerSDK 5.x desde:
    echo https://www.zkteco.com/en/index/Service/load/id/632.html
    echo.
    echo Presione cualquier tecla para continuar de todos modos...
    pause >nul
)
echo.

echo [5/6] Creando directorio de logs...
if not exist "logs" mkdir logs
echo Directorio de logs creado
echo.

echo [6/6] Configurando firewall...
netsh advfirewall firewall delete rule name="ZKTeco Bridge Service" >nul 2>&1
netsh advfirewall firewall add rule name="ZKTeco Bridge Service" dir=in action=allow protocol=TCP localport=5000
echo Regla de firewall configurada para puerto 5000
echo.

echo ========================================
echo Instalacion completada!
echo ========================================
echo.
echo Para iniciar el servicio ejecute:
echo    python bridge_service.py
echo.
echo O use el script: start_service.bat
echo.
pause