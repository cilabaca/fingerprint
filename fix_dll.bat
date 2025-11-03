@echo off
REM Script para copiar DLLs de ZKTeco al directorio del proyecto
REM Ejecutar como Administrador si es necesario

echo ========================================
echo Configuracion de DLLs ZKTeco
echo ========================================
echo.

REM Detectar arquitectura de Python
python -c "import sys; print('64' if sys.maxsize > 2**32 else '32')" > arch.tmp
set /p ARCH=<arch.tmp
del arch.tmp

echo Python detectado: %ARCH%-bit
echo.

REM Definir rutas según arquitectura
if "%ARCH%"=="64" (
    set DLL_SOURCE=C:\Windows\SysWOW64
    echo Usando DLLs de: %DLL_SOURCE%
) else (
    set DLL_SOURCE=C:\Windows\System32
    echo Usando DLLs de: %DLL_SOURCE%
)
echo.

REM Buscar DLLs
echo Buscando DLLs...
echo.

set FOUND=0

if exist "%DLL_SOURCE%\libzkfp.dll" (
    echo [OK] Encontrada: %DLL_SOURCE%\libzkfp.dll
    set FOUND=1
) else (
    echo [ERROR] NO encontrada: %DLL_SOURCE%\libzkfp.dll
)

if exist "%DLL_SOURCE%\libzkfpcsharp.dll" (
    echo [OK] Encontrada: %DLL_SOURCE%\libzkfpcsharp.dll
) else (
    echo [AVISO] NO encontrada: %DLL_SOURCE%\libzkfpcsharp.dll
    echo         (opcional, no siempre necesaria)
)

echo.

if %FOUND%==0 (
    echo ========================================
    echo ERROR: No se encontraron las DLLs
    echo ========================================
    echo.
    echo Las DLLs del SDK no estan instaladas.
    echo.
    echo Por favor:
    echo 1. Descargue ZKFingerSDK 5.x desde:
    echo    https://www.zkteco.com/en/index/Service/load/id/632.html
    echo.
    echo 2. Instale el SDK
    echo.
    echo 3. Ejecute este script nuevamente
    echo.
    pause
    exit /b 1
)

REM Copiar DLLs al directorio actual
echo ========================================
echo Copiando DLLs al directorio del proyecto
echo ========================================
echo.

copy "%DLL_SOURCE%\libzkfp.dll" . >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [OK] libzkfp.dll copiada
) else (
    echo [ERROR] No se pudo copiar libzkfp.dll
    echo         Intente ejecutar como Administrador
)

if exist "%DLL_SOURCE%\libzkfpcsharp.dll" (
    copy "%DLL_SOURCE%\libzkfpcsharp.dll" . >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo [OK] libzkfpcsharp.dll copiada
    )
)

echo.
echo ========================================
echo Verificando archivos copiados
echo ========================================
echo.

if exist "libzkfp.dll" (
    echo [OK] libzkfp.dll presente en el directorio
    
    REM Mostrar información del archivo
    for %%A in ("libzkfp.dll") do (
        echo     Tamano: %%~zA bytes
        echo     Fecha: %%~tA
    )
) else (
    echo [ERROR] libzkfp.dll NO esta en el directorio
)

echo.
echo ========================================
echo Configuracion completada
echo ========================================
echo.
echo Ahora puede ejecutar:
echo   python bridge_service.py
echo.
echo O ejecute primero el diagnostico:
echo   python diagnose.py
echo.
pause