# 🔌 ZKTeco USB Bridge Service

Servicio puente que permite la comunicación entre aplicaciones web y el sensor biométrico ZKTeco ZK4500 a través de USB.

---

## 📋 Requisitos Previos

### Software
- **Windows** 7, 8, 10 u 11 (64-bit recomendado)
- **Python** 3.8 o superior
- **ZKFingerSDK 5.x** instalado
- **pip** (gestor de paquetes Python)

### Hardware
- Sensor **ZKTeco ZK4500** 
- Puerto USB 2.0 o superior disponible
- 4GB RAM mínimo

---

## 🚀 Instalación Rápida

### Opción 1: Instalación Automática (Recomendado)

```bash
# Ejecutar como Administrador
install.bat
```

### Opción 2: Instalación Manual

```bash
# 1. Verificar Python
python --version

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Verificar instalación de ZKFingerSDK
# Las DLLs deben estar en:
#   - C:\Windows\System32\libzkfp.dll (32-bit)
#   - C:\Windows\SysWOW64\libzkfp.dll (64-bit)

# 4. Crear directorio de logs
mkdir logs

# 5. Configurar firewall (opcional)
netsh advfirewall firewall add rule name="ZKTeco Bridge" dir=in action=allow protocol=TCP localport=5000
```

---

## ▶️ Iniciar el Servicio

### Opción 1: Script Batch

```bash
start_service.bat
```

### Opción 2: Python Directo

```bash
python bridge_service.py
```

El servicio se ejecutará en: `http://localhost:5000`

---

## 🧪 Probar la Instalación

```bash
# Ejecutar script de prueba
python test_service.py
```

Este script verificará:
- ✅ Servicio corriendo
- ✅ SDK disponible
- ✅ Dispositivo detectado
- ✅ Captura de huellas

---

## 📡 API Endpoints

### Health Check
```http
GET /api/health
```

**Respuesta:**
```json
{
  "success": true,
  "message": "ZKTeco Bridge Service Running",
  "version": "1.0.0",
  "timestamp": "2025-10-28T10:30:00",
  "sdk_available": true
}
```

### Inicializar Dispositivo
```http
POST /api/device/initialize
```

**Respuesta:**
```json
{
  "success": true,
  "device_count": 1,
  "message": "Dispositivo(s) detectado(s): 1"
}
```

### Abrir Dispositivo
```http
POST /api/device/open
Content-Type: application/json

{
  "index": 0
}
```

**Respuesta:**
```json
{
  "success": true,
  "message": "Dispositivo conectado exitosamente",
  "width": 300,
  "height": 400,
  "handle": 12345
}
```

### Cerrar Dispositivo
```http
POST /api/device/close
```

**Respuesta:**
```json
{
  "success": true,
  "message": "Dispositivo desconectado"
}
```

### Estado del Dispositivo
```http
GET /api/device/status
```

**Respuesta:**
```json
{
  "success": true,
  "connected": true,
  "capturing": true,
  "mode": "registering",
  "width": 300,
  "height": 400,
  "initialized": true,
  "register_count": 2,
  "sdk_available": true
}
```

### Obtener Captura
```http
GET /api/capture/get
```

**Respuesta:**
```json
{
  "success": true,
  "data": {
    "template": "base64_encoded_template...",
    "image": "base64_encoded_image...",
    "timestamp": 1698500000.123,
    "width": 300,
    "height": 400,
    "register_count": 2,
    "registration_complete": false
  }
}
```

### Establecer Modo
```http
POST /api/mode/set
Content-Type: application/json

{
  "mode": "registering"
}
```

**Modos disponibles:**
- `idle` - Sin operación
- `registering` - Modo registro (3 capturas)
- `verifying` - Modo verificación

**Respuesta:**
```json
{
  "success": true,
  "mode": "registering",
  "message": "Modo establecido a: registering"
}
```

---

## 🔄 Flujo de Trabajo

### Registro de Huella (3 capturas)

```python
# 1. Inicializar
POST /api/device/initialize

# 2. Abrir dispositivo
POST /api/device/open
{"index": 0}

# 3. Establecer modo registro
POST /api/mode/set
{"mode": "registering"}

# 4. Obtener capturas (polling)
GET /api/capture/get  # Repetir hasta register_count = 3

# 5. Cuando registration_complete = true, obtener plantilla final
GET /api/capture/get
# Respuesta incluirá: "final_template" y "registration_complete": true
```

### Verificación de Huella

```python
# 1. Establecer modo verificación
POST /api/mode/set
{"mode": "verifying"}

# 2. Obtener captura
GET /api/capture/get

# 3. Comparar template con base de datos (en backend PHP)
```

---

## 🐛 Solución de Problemas

### Error: "SDK no disponible"

**Causa:** ZKFingerSDK no está instalado o las DLLs no se encuentran.

**Solución:**
```bash
# 1. Descargar ZKFingerSDK 5.x desde:
#    https://www.zkteco.com/en/index/Service/load/id/632.html

# 2. Instalar el SDK

# 3. Verificar que las DLLs existan:
dir C:\Windows\System32\libzkfp.dll
dir C:\Windows\SysWOW64\libzkfp.dll

# 4. Si no existen, copiar manualmente desde:
#    C:\Program Files\ZKTeco\ZKFingerSDK\bin\
```

### Error: "No se detectaron dispositivos"

**Causa:** El sensor no está conectado o los drivers no están instalados.

**Solución:**
1. Verificar conexión USB física
2. Verificar en Administrador de Dispositivos (Windows)
3. Reinstalar drivers del dispositivo
4. Probar con otro puerto USB
5. Reiniciar el servicio

### Error: "Puerto 5000 ya en uso"

**Causa:** Otro servicio está usando el puerto 5000.

**Solución:**
```bash
# Ver qué está usando el puerto
netstat -ano | findstr :5000

# Cambiar el puerto en bridge_service.py:
# app.run(host='0.0.0.0', port=5001)

# O en .env:
# PORT=5001
```

### Error: "Acceso denegado" o "Permission denied"

**Causa:** Permisos insuficientes para acceder al dispositivo USB.

**Solución:**
1. Ejecutar el servicio como Administrador
2. Verificar permisos del usuario
3. Desactivar temporalmente el antivirus

### El servicio se detiene inesperadamente

**Causa:** Errores no manejados o problema con el dispositivo.

**Solución:**
```bash
# Revisar logs
type logs\bridge_service.log

# Ejecutar en modo debug
# Editar bridge_service.py:
# app.run(host='0.0.0.0', port=5000, debug=True)
```

### Capturas lentas o intermitentes

**Causa:** Interferencia USB o problema de hardware.

**Solución:**
1. Usar puerto USB conectado directamente a la placa madre
2. Evitar hubs USB
3. Limpiar el sensor biométrico
4. Verificar cable USB
5. Reducir `CAPTURE_INTERVAL` en configuración

---

## 📊 Logs

Los logs se guardan en: `logs/bridge_service.log`

### Niveles de Log
- **DEBUG**: Información detallada de depuración
- **INFO**: Eventos normales (conexiones, capturas)
- **WARNING**: Advertencias no críticas
- **ERROR**: Errores que no detienen el servicio
- **CRITICAL**: Errores graves

### Ver Logs en Tiempo Real

```bash
# Windows PowerShell
Get-Content logs\bridge_service.log -Wait -Tail 50

# CMD
type logs\bridge_service.log
```

---

## ⚙️ Configuración Avanzada

### Variables de Entorno (.env)

Crear archivo `.env` basado en `.env.example`:

```env
PORT=5000
HOST=0.0.0.0
DEBUG=false
LOG_LEVEL=INFO
LOG_FILE=logs/bridge_service.log
CAPTURE_INTERVAL=100
MAX_RETRIES=3
```

### Ejecutar como Servicio de Windows

Usar **NSSM** (Non-Sucking Service Manager):

```bash
# 1. Descargar NSSM desde https://nssm.cc/download

# 2. Instalar servicio
nssm install ZKTecoBridge "C:\Python39\python.exe" "C:\ruta\bridge_service.py"

# 3. Iniciar servicio
nssm start ZKTecoBridge

# 4. Detener servicio
nssm stop ZKTecoBridge

# 5. Desinstalar servicio
nssm remove ZKTecoBridge
```

---

## 🔒 Seguridad

### Recomendaciones

1. **Firewall**: Permitir solo conexiones desde localhost si no se requiere acceso remoto
2. **HTTPS**: Usar proxy reverso (nginx) con SSL en producción
3. **Autenticación**: Implementar tokens de acceso para la API
4. **Rate Limiting**: Limitar solicitudes por IP
5. **Logs**: Monitorear accesos sospechosos

### Restringir a Localhost

```python
# En bridge_service.py cambiar:
app.run(host='127.0.0.1', port=5000)  # Solo localhost
```

### Proxy Reverso con Nginx

```nginx
server {
    listen 443 ssl;
    server_name fingerprint.empresa.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 📈 Rendimiento

### Optimizaciones

1. **Reducir CAPTURE_INTERVAL** para capturas más rápidas
2. **Aumentar recursos** si se procesan muchas solicitudes
3. **Usar Redis** para caché de plantillas
4. **Escalar horizontalmente** con múltiples instancias

### Benchmarks Típicos

- **Inicialización**: ~1-2 segundos
- **Captura de huella**: ~200-500ms
- **Generación de plantilla**: ~300ms
- **Verificación 1:1**: ~50-100ms

---

## 🆘 Soporte

### Recursos Útiles

- [Documentación ZKTeco](https://www.zkteco.com)
- [SDK Download](https://www.zkteco.com/en/index/Service/load/id/632.html)
- [Especificaciones ZK4500](https://www.zkteco.com/en/product_detail/391.html)

### Reportar Problemas

Al reportar un problema, incluir:
1. Versión de Windows
2. Versión de Python
3. Logs del servicio
4. Mensaje de error completo
5. Pasos para reproducir

---

## 📝 Notas Importantes

⚠️ **El servicio debe ejecutarse en el mismo equipo donde está conectado el sensor USB**

⚠️ **Solo funciona en Windows** (debido a las DLLs del SDK)

⚠️ **Un solo dispositivo por servicio** (para múltiples dispositivos, ejecutar varias instancias en diferentes puertos)

⚠️ **Requiere permisos de Administrador** para acceso USB completo

---

## 🔄 Actualizaciones

Para actualizar el servicio:

```bash
# 1. Detener el servicio
Ctrl+C

# 2. Hacer backup
copy bridge_service.py bridge_service.py.backup

# 3. Actualizar archivos
# (copiar nuevos archivos)

# 4. Actualizar dependencias
pip install -r requirements.txt --upgrade

# 5. Reiniciar servicio
python bridge_service.py
```

---

**Versión:** 1.0.0  
**Última actualización:** Octubre 2025  
**Compatible con:** ZKTeco ZK4500, ZK9500, SLK20R, SLK20M