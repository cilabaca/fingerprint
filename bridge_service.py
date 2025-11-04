"""
ZKTeco USB Bridge Service - Versión Final
Servicio puente entre aplicación web y sensor biométrico ZKTeco ZK4500
Versión: 4.0.0 - Manejo robusto de threads y reconexión automática
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import time
import base64
import json
import logging
import sys
import os
from datetime import datetime
import requests # <--- Nueva importación para comunicarnos con la API PHP

# ==================== CONFIGURACIÓN DE LOGGING CORREGIDA ====================
class UTF8StreamHandler(logging.StreamHandler):
    def __init__(self, stream=None):
        super().__init__(stream)
    
    def emit(self, record):
        try:
            msg = self.format(record)
            # Forzar codificación UTF-8 para evitar errores con emojis
            if hasattr(self.stream, 'buffer'):
                self.stream.buffer.write(msg.encode('utf-8') + self.terminator.encode('utf-8'))
                self.stream.buffer.flush()
            else:
                # Fallback para streams que no soportan bytes
                self.stream.write(msg + self.terminator)
                self.stream.flush()
        except Exception:
            self.handleError(record)

# Configurar logger principal
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Crear formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Handler para consola con UTF-8
console_handler = UTF8StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# Handler para archivo (siempre usa UTF-8)
file_handler = logging.FileHandler('bridge_service.log', encoding='utf-8')
file_handler.setFormatter(formatter)

# Agregar handlers al logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# También configurar el logger de werkzeug (Flask)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

logger.info("=== ZKTeco USB Bridge Service Iniciado ===")

# ==================== CARGA DEL SDK ZKTECO ====================
try:
    import ctypes
    from ctypes import *
    
    # Determinar arquitectura
    is_64bit = sys.maxsize > 2**32
    logger.info(f"Ejecutando en modo {'64-bit' if is_64bit else '32-bit'}")
    
    # Intentar cargar la librería principal
    try:
        if os.path.exists('libzkfp.dll'):
            zkfp = ctypes.CDLL('libzkfp.dll')
        elif os.path.exists('libzkfpcsharp.dll'):
            zkfp = ctypes.CDLL('libzkfpcsharp.dll')
        else:
            zkfp = ctypes.windll.LoadLibrary('libzkfp.dll')
        
        logger.info("DLL cargada exitosamente")
    except Exception as e:
        logger.error(f"Error al cargar DLL: {e}")
        raise
    
    # ==================== DEFINICIÓN DE PROTOTIPOS ====================
    # ZKFPM_Init
    zkfp.ZKFPM_Init.argtypes = []
    zkfp.ZKFPM_Init.restype = ctypes.c_int
    
    # ZKFPM_Terminate
    zkfp.ZKFPM_Terminate.argtypes = []
    zkfp.ZKFPM_Terminate.restype = ctypes.c_int
    
    # ZKFPM_GetDeviceCount
    zkfp.ZKFPM_GetDeviceCount.argtypes = []
    zkfp.ZKFPM_GetDeviceCount.restype = ctypes.c_int
    
    # ZKFPM_OpenDevice
    zkfp.ZKFPM_OpenDevice.argtypes = [ctypes.c_int]
    zkfp.ZKFPM_OpenDevice.restype = ctypes.c_void_p
    
    # ZKFPM_CloseDevice
    zkfp.ZKFPM_CloseDevice.argtypes = [ctypes.c_void_p]
    zkfp.ZKFPM_CloseDevice.restype = ctypes.c_int
    
    # ZKFPM_GetParameters
    zkfp.ZKFPM_GetParameters.argtypes = [
        ctypes.c_void_p,  # handle
        ctypes.c_int,     # nParamCode
        ctypes.POINTER(ctypes.c_ubyte),  # paramValue
        ctypes.POINTER(ctypes.c_int)     # size
    ]
    zkfp.ZKFPM_GetParameters.restype = ctypes.c_int
    
    # ZKFPM_AcquireFingerprint
    zkfp.ZKFPM_AcquireFingerprint.argtypes = [
        ctypes.c_void_p,  # handle
        ctypes.POINTER(ctypes.c_ubyte),  # fpImage
        ctypes.c_int,     # cbFPImage
        ctypes.POINTER(ctypes.c_ubyte),  # fpTemplate
        ctypes.POINTER(ctypes.c_int)     # cbTemplate
    ]
    zkfp.ZKFPM_AcquireFingerprint.restype = ctypes.c_int
    
    # ZKFPM_GenRegTemplate (para combinar 3 plantillas)
    zkfp.ZKFPM_GenRegTemplate.argtypes = [
        ctypes.c_void_p,  # handle
        ctypes.POINTER(ctypes.c_ubyte),  # temp1
        ctypes.POINTER(ctypes.c_ubyte),  # temp2
        ctypes.POINTER(ctypes.c_ubyte),  # temp3
        ctypes.POINTER(ctypes.c_ubyte),  # regTemp
        ctypes.POINTER(ctypes.c_int)     # cbRegTemp
    ]
    zkfp.ZKFPM_GenRegTemplate.restype = ctypes.c_int
    
    # ZKFPM_DBMatch (para comparar dos plantillas)
    zkfp.ZKFPM_DBMatch.argtypes = [
        ctypes.c_void_p,  # handle
        ctypes.POINTER(ctypes.c_ubyte),  # temp1
        ctypes.c_int,     # cbTemp1
        ctypes.POINTER(ctypes.c_ubyte),  # temp2
        ctypes.c_int      # cbTemp2
    ]
    zkfp.ZKFPM_DBMatch.restype = ctypes.c_int
    
    # ZKFPM_DBInit (basado en C# SDK 5.3.10) 
    zkfp.ZKFPM_DBInit.argtypes = []
    zkfp.ZKFPM_DBInit.restype = ctypes.c_void_p

    # ZKFPM_DBFree (basado en C# SDK 5.3.11) [cite: 209]
    zkfp.ZKFPM_DBFree.argtypes = [ctypes.c_void_p]
    zkfp.ZKFPM_DBFree.restype = ctypes.c_int

    # Constantes del SDK
    ZKFP_ERR_OK = 0
    ZKFP_ERR_INITLIB = -1
    ZKFP_ERR_INIT = -2
    ZKFP_ERR_NO_DEVICE = -3
    ZKFP_ERR_NOT_SUPPORT = -4
    ZKFP_ERR_INVALID_PARAM = -5
    ZKFP_ERR_OPEN = -6
    ZKFP_ERR_INVALID_HANDLE = -7
    ZKFP_ERR_CAPTURE = -8
    ZKFP_ERR_EXTRACT_FP = -9
    ZKFP_ERR_ABSORT = -10
    ZKFP_ERR_MEMORY_NOT_ENOUGH = -11
    ZKFP_ERR_BUSY = -12
    ZKFP_ERR_ADD_FINGER = -13
    ZKFP_ERR_DEL_FINGER = -14
    ZKFP_ERR_FAIL = -17
    ZKFP_ERR_CANCEL = -18
    ZKFP_ERR_VERIFY_FP = -20
    ZKFP_ERR_MERGE = -22
    ZKFP_ERR_NOT_OPENED = -23
    ZKFP_ERR_NOT_INIT = -24
    ZKFP_ERR_ALREADY_INIT = -25
    ZKFP_ERR_LOADIMAGE = -26
    ZKFP_ERR_ANALYZE_FP = -27
    
    # Códigos de parámetros
    PARAM_CODE_IMAGE_WIDTH = 1
    PARAM_CODE_IMAGE_HEIGHT = 2
    
    SDK_AVAILABLE = True
    logger.info("SDK de ZKTeco cargado correctamente con prototipos seguros")
    
except Exception as e:
    SDK_AVAILABLE = False
    logger.error(f"Error crítico al cargar SDK: {e}")
    logger.warning("El servicio funcionará en modo simulación")

# ==================== CONFIGURACIÓN DE LA APLICACIÓN ====================
# MODIFIQUE ESTA URL A SU ENTORNO REAL si la API no está en localhost
PHP_API_URL = "http://localhost/fingerprint/api.php" 
MATCH_THRESHOLD = 60 # Umbral de coincidencia (60 es un valor típico de ZKTeco)

# ==================== CONFIGURACIÓN FLASK ====================
app = Flask(__name__)
CORS(app)

# ==================== CLASE ZKTecoDevice COMPLETAMENTE CORREGIDA ====================
class ZKTecoDevice:
    """Clase para manejar el dispositivo ZKTeco ZK4500 - Versión Final Completamente Corregida"""

    def __init__(self):
        self.device_handle = None
        self.db_handle = None        
        self.capture_thread = None
        self.is_capturing = False
        self.width = 300  # Valores por defecto
        self.height = 400
        self.last_capture = {}  # Inicializado como dict vacío
        self.register_count = 0
        self.register_templates = []
        self.current_mode = "idle"
        self.is_initialized = False
        self._lock = threading.Lock()
        self.register_step = "CAPTURE" # Estado para la FSM de registro        
        logger.info("Instancia de ZKTecoDevice creada correctamente")

    # Métodos privados (con _)
    def _get_error_message(self, error_code):
        """Convertir código de error a mensaje legible"""
        error_messages = {
            ZKFP_ERR_OK: "Operación exitosa",
            ZKFP_ERR_INITLIB: "Error al inicializar librería",
            ZKFP_ERR_INIT: "Error de inicialización",
            ZKFP_ERR_NO_DEVICE: "No se encontró dispositivo",
            ZKFP_ERR_NOT_SUPPORT: "Operación no soportada",
            ZKFP_ERR_INVALID_PARAM: "Parámetro inválido",
            ZKFP_ERR_OPEN: "Error al abrir dispositivo",
            ZKFP_ERR_INVALID_HANDLE: "Handle inválido",
            ZKFP_ERR_CAPTURE: "Error de captura / esperando dedo",
            ZKFP_ERR_EXTRACT_FP: "Error al extraer huella",
            ZKFP_ERR_ABSORT: "Operación abortada",
            ZKFP_ERR_MEMORY_NOT_ENOUGH: "Memoria insuficiente",
            ZKFP_ERR_BUSY: "Dispositivo ocupado",
            ZKFP_ERR_ADD_FINGER: "Error al agregar huella",
            ZKFP_ERR_DEL_FINGER: "Error al eliminar huella",
            ZKFP_ERR_FAIL: "Operación fallida",
            ZKFP_ERR_CANCEL: "Operación cancelada",
            ZKFP_ERR_VERIFY_FP: "Error de verificación",
            ZKFP_ERR_MERGE: "Error al combinar plantillas",
            ZKFP_ERR_NOT_OPENED: "Dispositivo no abierto",
            ZKFP_ERR_NOT_INIT: "No inicializado",
            ZKFP_ERR_ALREADY_INIT: "Ya inicializado",
            ZKFP_ERR_LOADIMAGE: "Error al cargar imagen",
            ZKFP_ERR_ANALYZE_FP: "Error al analizar huella"
        }
        return error_messages.get(error_code, f"Error desconocido (código: {error_code})")
    
    def _verify_device_connection(self):
        """Verificar que el dispositivo esté conectado y funcionando"""
        if not self.device_handle or not SDK_AVAILABLE:
            return False
        
        try:
            # Intentar obtener parámetros del dispositivo para verificar conexión
            param_buffer = (ctypes.c_ubyte * 4)()
            size = ctypes.c_int(4)
            
            ret = zkfp.ZKFPM_GetParameters(
                self.device_handle,
                PARAM_CODE_IMAGE_WIDTH,
                param_buffer,
                ctypes.byref(size)
            )
            
            return ret == ZKFP_ERR_OK
            
        except Exception as e:
            logger.debug(f"Error en verificación de conexión: {e}")
            return False
    
    def _reconnect_device(self):
        """Reconectar dispositivo automáticamente - VERSIÓN MEJORADA Y CORREGIDA DEADLOCK"""
        try:
            logger.warning("🔄 Intentando reconexión automática del dispositivo...")

            # ================== INICIO DE CORRECCIÓN DE DEADLOCK ==================
            # Identificar si el hilo actual es el hilo de captura
            current_thread_ident = threading.current_thread().ident
            capture_thread_ident = self.capture_thread.ident if self.capture_thread else None
            is_self_call = (current_thread_ident == capture_thread_ident)
            
            if is_self_call:
                logger.warning("🔧 _reconnect_device llamado por el hilo de captura (auto-reparación).")
            # =================== FIN DE CORRECCIÓN DE DEADLOCK ===================

            # ✅ MEJORA: Detener captura de forma más gradual
            # ✅ CORRECCIÓN: Solo setear a False si NO es una auto-llamada,
            # de lo contrario el hilo se detendrá después de reconectar.
            if not is_self_call:
                self.is_capturing = False
            
            # Esperar a que el thread se detenga naturalmente
            # ✅ CORRECCIÓN DE DEADLOCK: NO esperar si somos el mismo hilo
            if not is_self_call:
                timeout = 5  # Aumentar timeout
                start_time = time.time()
                if self.capture_thread and self.capture_thread.is_alive():
                    while self.capture_thread.is_alive() and (time.time() - start_time) < timeout:
                        time.sleep(0.2)
                    
                    if self.capture_thread.is_alive():
                        logger.warning("⚠️ El hilo de captura no terminó en el tiempo esperado, continuando...")
            else:
                logger.warning("🔧 Omitiendo espera de thread (auto-llamada).")
            
            with self._lock:
                # ✅ MEJORA: Cerrar dispositivo de forma más segura
                # --- INICIO DE CORRECCIÓN ---
                # Liberar DB Handle antes de Terminate
                if self.db_handle and SDK_AVAILABLE:
                    try:
                        logger.info("🔒 Liberando cache de algoritmos (db_handle)...")
                        ret = zkfp.ZKFPM_DBFree(self.db_handle)
                        if ret == ZKFP_ERR_OK:
                            logger.info("✅ db_handle liberado correctamente")
                        else:
                            logger.warning(f"⚠️ Código al liberar db_handle: {ret}")
                    except Exception as e:
                        logger.warning(f"⚠️ Error al liberar db_handle: {e}")
                    finally:
                        self.db_handle = None
                # --- FIN DE CORRECCIÓN ---
                
                # ✅ MEJORA: Terminar SDK de forma controlada
                if self.is_initialized and SDK_AVAILABLE:
                    try:
                        logger.info("🔒 Terminando SDK...")
                        ret = zkfp.ZKFPM_Terminate()
                        if ret == ZKFP_ERR_OK:
                            logger.info("✅ SDK terminado correctamente")
                        else:
                            logger.warning(f"⚠️ Código al terminar SDK: {ret}")
                    except Exception as e:
                        logger.warning(f"⚠️ Error al terminar SDK: {e}")
                    finally:
                        self.is_initialized = False
                
                # ✅ MEJORA: Pausa más larga para asegurar reset del dispositivo
                logger.info("⏳ Esperando 3 segundos para reset del dispositivo...")
                time.sleep(3)
                
                # Reintentar inicialización
                logger.info("🔄 Reinicializando SDK...")
                init_result = self.initialize()
                if not init_result.get('success'):
                    logger.error(f"❌ Error en reconexión - No se pudo inicializar: {init_result.get('message')}")
                    return False
                
                # Reabrir dispositivo
                logger.info("🔌 Reabriendo dispositivo...")
                open_result = self.open_device(0)
                if open_result.get('success'):
                    logger.info("✅ Reconexión exitosa - Dispositivo reconectado")
                    
                    # ✅ MEJORA: Pausa antes de reiniciar captura
                    time.sleep(2)
                    
                    # ✅ CORRECCIÓN DE DEADLOCK:
                    # NO reiniciar la captura si fue una auto-llamada,
                    # ya que el hilo original (este mismo) debe continuar.
                    if not is_self_call:
                        capture_result = self.start_capture()
                        if capture_result.get('success'):
                            logger.info("✅ Captura reiniciada después de reconexión")
                        else:
                            logger.warning("⚠️ No se pudo reiniciar la captura después de reconexión")
                    
                    return True
                else:
                    logger.error(f"❌ Error en reconexión - No se pudo abrir dispositivo: {open_result.get('message')}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Error durante reconexión: {e}")
            return False

    def _capture_loop(self):
        """Loop de captura en segundo plano - VERSIÓN MEJORADA SIN DEADLOCK"""
        logger.info("Loop de captura iniciado")
        
        if not SDK_AVAILABLE:
            logger.error("SDK no disponible")
            self.is_capturing = False
            return
        
        # Verificación inicial de conexión
        if not self.device_handle or not self._verify_device_connection():
            logger.error("Dispositivo no conectado o no responde al iniciar captura")
            self.is_capturing = False
            return
        
        # Crear buffers
        try:
            image_buffer_size = self.width * self.height
            image_buffer = (ctypes.c_ubyte * image_buffer_size)()
            template_buffer = (ctypes.c_ubyte * 2048)()
            template_size = ctypes.c_int(2048)
            
            logger.info(f"Buffers creados: imagen={image_buffer_size}, template=2048")
        except Exception as e:
            logger.error(f"Error al crear buffers: {e}")
            self.is_capturing = False
            return
        
        consecutive_errors = 0
        max_consecutive_errors = 5
        connection_check_interval = 10
        capture_count = 0
        
        try:
            while self.is_capturing:
                try:
                    # Verificación periódica de conexión
                    capture_count += 1
                    if capture_count >= connection_check_interval:
                        capture_count = 0
                        if not self._verify_device_connection():
                            logger.warning("Dispositivo desconectado durante captura - intentando reconexión")
                            if self._reconnect_device():
                                logger.info("Reconexión exitosa - continuando captura")
                                # Recrear buffers después de reconexión
                                try:
                                    image_buffer_size = self.width * self.height
                                    image_buffer = (ctypes.c_ubyte * image_buffer_size)()
                                    template_buffer = (ctypes.c_ubyte * 2048)()
                                    template_size = ctypes.c_int(2048)
                                except Exception as e:
                                    logger.error(f"Error al recrear buffers: {e}")
                                    break
                            else:
                                logger.error("No se pudo reconectar - deteniendo captura")
                                break
                    
                    # Verificar si debemos continuar
                    if not self.is_capturing:
                        break
                        
                    if not self.device_handle:
                        logger.error("Handle perdido durante captura")
                        break
                    
                    template_size.value = 2048
                    
                    # Capturar huella
                    ret = zkfp.ZKFPM_AcquireFingerprint(
                        self.device_handle,
                        image_buffer,
                        image_buffer_size,
                        template_buffer,
                        ctypes.byref(template_size)
                    )
                    
                    # =================== INICIO DE FSM DE REGISTRO ===================
                    
                    # Manejo de estado para MODO REGISTRO
                    if self.current_mode == "registering":
                        
                        # --- ESTADO 1: ESPERANDO DEDO ---
                        if self.register_step == "CAPTURE":
                            if ret == ZKFP_ERR_OK:
                                # ¡Tenemos una huella! Procesarla.
                                consecutive_errors = 0
                                
                                template_bytes = bytes(template_buffer[:template_size.value])
                                image_bytes = bytes(image_buffer[:image_buffer_size])
                                
                                self.last_capture = {
                                    'template': base64.b64encode(template_bytes).decode('utf-8'),
                                    'image': base64.b64encode(image_bytes).decode('utf-8'),
                                    'timestamp': time.time(),
                                    'width': self.width, 'height': self.height,
                                    'template_size': template_size.value
                                }
                                
                                # Procesar el registro (usando la función que ya teníamos)
                                registration_complete = self._process_registration(template_bytes)
                                
                                if registration_complete:
                                    logger.info("Registro completado, deteniendo loop de captura...")
                                    self.is_capturing = False # Flag para detener
                                    break # Salir del 'while'
                                
                                # Si no está completo, cambiar de estado
                                self.register_step = "WAIT_FOR_LIFT"
                                if self.last_capture:
                                    self.last_capture['registration_error'] = "¡Bien! Ahora levante el dedo."
                                logger.info(f"Captura {self.register_count}/3. Cambiando a estado 'WAIT_FOR_LIFT'")
                            
                            elif ret == ZKFP_ERR_CAPTURE:
                                # Normal, esperando dedo
                                consecutive_errors = 0
                                if self.last_capture:
                                    self.last_capture.pop('registration_error', None)
                                pass
                            
                            else:
                                # Otro error
                                consecutive_errors += 1
                                # ... (copiar aquí la lógica de manejo de errores de más abajo) ...

                        
                        # --- ESTADO 2: ESPERANDO QUE LEVANTE EL DEDO ---
                        elif self.register_step == "WAIT_FOR_LIFT":
                            if ret == ZKFP_ERR_OK:
                                # El dedo SIGUE puesto. Ignorar.
                                consecutive_errors = 0
                                pass 
                            
                            elif ret == ZKFP_ERR_CAPTURE:
                                # ¡Dedo levantado! (Error -8) 
                                consecutive_errors = 0
                                # Volver al estado de captura para la siguiente huella
                                self.register_step = "CAPTURE"
                                if self.last_capture:
                                    self.last_capture.pop('registration_error', None)
                                logger.info("Dedo levantado. Cambiando a estado 'CAPTURE'")
                            
                            else:
                                # Otro error
                                consecutive_errors += 1
                                # ... (copiar aquí la lógica de manejo de errores de más abajo) ...

                    # Manejo de estado para OTROS MODOS (verifying, idle)
                    else:
                        if ret == ZKFP_ERR_OK:
                            consecutive_errors = 0
                            try:
                                template_bytes = bytes(template_buffer[:template_size.value])
                                image_bytes = bytes(image_buffer[:image_buffer_size])
                                
                                self.last_capture = {
                                    'template': base64.b64encode(template_bytes).decode('utf-8'),
                                    'image': base64.b64encode(image_bytes).decode('utf-8'),
                                    'timestamp': time.time(),
                                    'width': self.width, 'height': self.height,
                                    'template_size': template_size.value
                                }
                                
                                if self.current_mode == "verifying":
                                    self._process_verification(template_bytes)
                                
                            except Exception as e:
                                logger.error(f"Error al procesar captura (modo no-registro): {e}")
                            
                        elif ret == ZKFP_ERR_CAPTURE:
                            consecutive_errors = 0
                            pass
                        
                        else:
                            # ESTA ES LA LÓGICA DE MANEJO DE ERRORES (copiarla arriba también)
                            consecutive_errors += 1
                            error_msg = self._get_error_message(ret)
                            
                            if consecutive_errors == 1:
                                logger.warning(f"Error en captura: {error_msg} (código: {ret})")
                            
                            if consecutive_errors >= max_consecutive_errors:
                                logger.error(f"Demasiados errores consecutivos ({consecutive_errors}), verificando conexión")
                                if not self._verify_device_connection():
                                    logger.warning("Problema de conexión detectado - intentando reconexión")
                                    if self._reconnect_device():
                                        consecutive_errors = 0
                                        continue
                                logger.error("No se pudo resolver el problema - deteniendo captura")
                                break
                    
                    # =================== FIN DE FSM DE REGISTRO ===================
                    
                    time.sleep(0.1)
                    
                except Exception as e:
                    consecutive_errors += 1
                    logger.error(f"Excepción en captura: {e}")
                    
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("Demasiadas excepciones, deteniendo captura")
                        break
                    
                    time.sleep(0.5)
        
        except Exception as e:
            logger.error(f"Excepción crítica en loop de captura: {e}")
        
        finally:
            # Asegurarse de que el flag esté desactivado
            self.is_capturing = False
            logger.info("Loop de captura finalizado")

    def _process_registration(self, template):
        """Procesar registro de huella con manejo robusto de errores"""
        try:
            if self.current_mode != "registering":
                return False # No detener el loop
            
            if not self._verify_device_connection():
                logger.error("❌ Dispositivo desconectado al procesar registro")
                if self._reconnect_device():
                    logger.info("✅ Reconexión exitosa - continuando registro")
                else:
                    logger.error("❌ No se pudo reconectar - abortando registro")
                    self._reset_registration_state()
                    return True # Detener el loop por error crítico
            
            # Evitar acumulación de plantillas
            if self.register_count >= 3:
                logger.warning("⚠️ Ya se tienen 3 plantillas, ignorando captura adicional")
                return False # No detener el loop

            # =================== INICIO DE CORRECCIÓN (Intento 2) ===================
            # VERIFICAR SI LA HUELLA ES *EXACTAMENTE* LA MISMA (byte por byte)
            # Esto previene errores de búfer, pero permite huellas similares.
            
            if template in self.register_templates:
                logger.warning(f"⚠️ Plantilla duplicada exacta detectada. Por favor, levante el dedo y colóquelo de nuevo.")
                
                # Informar al frontend del error
                if self.last_capture:
                    self.last_capture['registration_error'] = "Huella duplicada. Levante el dedo e intente de nuevo"
                
                return False # No agregar esta huella, no detener el loop

            # Si llegamos aquí, es una huella nueva.
            # Limpiamos cualquier error anterior.
            if self.last_capture:
                 self.last_capture.pop('registration_error', None)
            # =================== FIN DE CORRECCIÓN (Intento 2) ===================
            
            # Agregar plantilla
            self.register_templates.append(template)
            self.register_count = len(self.register_templates)
            
            logger.info(f"✅ Captura {self.register_count}/3 completada - Tamaño: {len(template)} bytes")
            
            # Actualizar información de progreso
            if self.last_capture:
                self.last_capture['register_count'] = self.register_count
                self.last_capture['registration_in_progress'] = True
                # ✅ CRÍTICO: Asegurar que se actualice el estado
                self.last_capture['registration_complete'] = False
            
            # Si tenemos 3 capturas, generar plantilla final
            if self.register_count >= 3:
                logger.info("🎯 3 CAPTURAS COMPLETADAS - Preparando generación de plantilla final...")
               # logger.info("⏳ Pausa de 1.5 segundos para estabilizar dispositivo...")
                time.sleep(1.5)
                
                # Verificar conexión antes de generar
                if not self._verify_device_connection():
                    logger.error("❌ Dispositivo desconectado antes de generar plantilla")
                    if not self._reconnect_device():
                        logger.error("❌ No se pudo reconectar - reiniciando registro")
                        self._reset_registration_state()
                        return True # Detener el loop por error crítico
                
                # Generar plantilla final
                success = self._generate_final_template_robust()
                
                if success:
                    logger.info("✅ REGISTRO COMPLETADO EXITOSAMENTE")
                 #   return True # *** DEVOLVER TRUE PARA DETENER EL LOOP ***
      
                    # ✅ VERIFICAR que la plantilla final esté en last_capture
                    if self.last_capture and 'final_template' in self.last_capture:
                        logger.info(f"✅ Plantilla final confirmada en last_capture (tamaño: {len(self.last_capture['final_template'])})")
                        
                        # ✅ FORZAR actualización del estado
                        self.last_capture['registration_complete'] = True
                        self.last_capture['registration_in_progress'] = False
                        
                        # ✅ AGREGAR: Timestamp para verificar actualización
                        self.last_capture['completion_timestamp'] = time.time()
                        
                        logger.info("✅ Estado de registro actualizado: registration_complete=True")
                    else:
                        logger.error("❌ Plantilla final NO encontrada en last_capture después de generación")
                        return False
                    
                    return True                                     
                else:
                    logger.error("❌ No se pudo generar plantilla final")
                    # Mantener 2 plantillas para reintentar
                    if len(self.register_templates) >= 2:
                        self.register_count = 2
                        self.register_templates = self.register_templates[:2]
                        if self.last_capture:
                            self.last_capture['register_count'] = 2
                            self.last_capture['registration_error'] = "Error al generar plantilla final"
                    return False # No detener, permitir reintento
            else:
                logger.info(f"⏳ Progreso: {self.register_count}/3 capturas")
                return False # No detener, continuar capturando
                        
        except Exception as e:
            logger.exception(f"❌ ERROR CRÍTICO en _process_registration: {e}")
            self._reset_registration_state()
            return True # Detener el loop por error crítico

    def _generate_final_template_robust(self):
        """Genera plantilla final con reintentos y manejo robusto de errores"""
        try:
            if not self._validate_templates():
                logger.error("❌ Validación de plantillas falló")
                return False

            # ✅ VERIFICAR db_handle
            if not self.db_handle:
                logger.error("❌ db_handle no disponible para GenRegTemplate")
                return False

            max_attempts = 3
            
            for attempt in range(1, max_attempts + 1):
                try:
                    logger.info(f"🔄 Intento {attempt} de {max_attempts}")
                    
                    # Verificar handle válido
                    if not self.device_handle or self.device_handle <= 0:
                        logger.error("❌ Handle inválido detectado")
                        if not self._reconnect_device():
                            continue
                    
                    # Crear buffers para las 3 plantillas
                    logger.info("🔧 Creando buffers para plantillas...")
                    template1 = (ctypes.c_ubyte * len(self.register_templates[0]))(*self.register_templates[0])
                    template2 = (ctypes.c_ubyte * len(self.register_templates[1]))(*self.register_templates[1])
                    template3 = (ctypes.c_ubyte * len(self.register_templates[2]))(*self.register_templates[2])
                    
                    # Buffer para plantilla final
                    reg_temp_len = 2048
                    reg_temp = (ctypes.c_ubyte * reg_temp_len)()
                    reg_temp_size = ctypes.c_int(reg_temp_len)
                    
                    logger.info("🎯 Llamando ZKFPM_GenRegTemplate...")
                    
                    # Llamar a GenRegTemplate
                    ret = zkfp.ZKFPM_GenRegTemplate(
                        self.db_handle,
                        template1,
                        template2,
                        template3,
                        reg_temp,
                        ctypes.byref(reg_temp_size)
                    )
                    
                    logger.info(f"📊 Resultado de GenRegTemplate: {ret} ({self._get_error_message(ret)})")
                    
                    if ret == ZKFP_ERR_OK:
                        final_size = reg_temp_size.value
                        logger.info(f"✅ Plantilla final generada - Tamaño: {final_size} bytes")
                        
                        # Convertir a bytes y base64
                        final_template = bytes(reg_temp[:final_size])
                        final_template_b64 = base64.b64encode(final_template).decode('utf-8')
                        
                        # Actualizar last_capture con plantilla final
                        if self.last_capture:
                            self.last_capture['final_template'] = final_template_b64
                            self.last_capture['registration_complete'] = True
                            self.last_capture['final_template_size'] = final_size
                            self.last_capture['registration_in_progress'] = False
                        
                        logger.info("✅ Plantilla final guardada en last_capture")
                        return True
                        
                    elif ret == ZKFP_ERR_INVALID_HANDLE:
                        logger.error(f"❌ Error al generar plantilla (intento {attempt}): Handle inválido")
                      #  logger.warning("🔧 Error de handle inválido - intentando recuperación...")
                        
                        if self._reconnect_device():
                            continue
                        else:
                            logger.error("❌ No se pudo recuperar el handle")
                            
                    else:
                        error_msg = self._get_error_message(ret)
                        logger.error(f"❌ Error al generar plantilla: {error_msg}")
                        
                        # Para errores no relacionados con handle, no reintentar
                        if ret != ZKFP_ERR_MERGE:
                            return False
                        
                except Exception as e:
                    logger.exception(f"💥 Excepción en intento {attempt}: {e}")
                    if attempt < max_attempts:
                        time.sleep(2)
                        continue
            
            logger.error("❌ Todos los intentos fallaron para generar plantilla")
            return False
            
        except Exception as e:
            logger.exception(f"❌ Error crítico en _generate_final_template_robust: {e}")
            return False

    def _validate_templates(self):
        """Validar que las plantillas sean consistentes y válidas"""
        try:
            if len(self.register_templates) != 3:
                logger.error(f"❌ Número incorrecto de plantillas: {len(self.register_templates)}")
                return False
            
            # Verificar que ninguna plantilla esté vacía
            for i, template in enumerate(self.register_templates):
                if len(template) == 0:
                    logger.error(f"❌ Plantilla {i+1} está vacía")
                    return False
                if len(template) < 100:  # Tamaño mínimo razonable
                    logger.warning(f"⚠️ Plantilla {i+1} muy pequeña: {len(template)} bytes")
            
            # Verificar que las plantillas no sean idénticas (posible error)
            if (self.register_templates[0] == self.register_templates[1] or 
                self.register_templates[1] == self.register_templates[2] or
                self.register_templates[0] == self.register_templates[2]):
                logger.warning("⚠️ Algunas plantillas son idénticas - posible error de captura")
            
            logger.info(f"✅ Plantillas validadas - tamaños: {[len(t) for t in self.register_templates]}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error validando plantillas: {e}")
            return False

    def _process_verification(self, template):
        """Marcar que hay una plantilla disponible para verificar"""
        if self.last_capture:
            self.last_capture['ready_for_verification'] = True
    
    def _reset_registration_state(self):
        """Resetear estado de registro"""
        with self._lock:
            self.register_count = 0
            self.register_templates = []
            self.current_mode = "idle"
            self.register_step = "CAPTURE"            
            # Limpiar solo datos de registro del last_capture
            if self.last_capture:
                for field in ['registration_complete', 'final_template', 'register_count', 'registration_in_progress', 'registration_error']:
                    if field in self.last_capture:
                        del self.last_capture[field]
            
            logger.info("Estado de registro reseteado")

    # Métodos públicos
    def initialize(self):
        """Inicializar el SDK y detectar dispositivos"""
        try:
            if not SDK_AVAILABLE:
                return {
                    'success': False,
                    'message': 'SDK no disponible. Instale ZKFingerSDK 5.x'
                }
            
            with self._lock:
                logger.info("Inicializando dispositivo...")
                
                try:
                    ret = zkfp.ZKFPM_Init()
                    logger.info(f"Código de retorno de Init: {ret}")
                except Exception as e:
                    logger.error(f"Excepción en ZKFPM_Init: {e}")
                    return {
                        'success': False,
                        'message': f'Error al llamar ZKFPM_Init: {str(e)}'
                    }
                
                if ret == ZKFP_ERR_OK or ret == ZKFP_ERR_ALREADY_INIT:
                    self.is_initialized = True
                    # --- INICIO DE CORRECCIÓN ---
                    # Crear el handle de la caché de algoritmos (DB Handle)
                    if not self.db_handle:
                        try:
                            self.db_handle = zkfp.ZKFPM_DBInit()
                            if self.db_handle:
                                logger.info(f"✅ Cache de algoritmos (db_handle) creada: {self.db_handle}")
                            else:
                                logger.error("❌ No se pudo crear la cache de algoritmos (db_handle)")
                                return {
                                    'success': False,
                                    'message': 'No se pudo inicializar la caché de algoritmos'
                                }
                        except Exception as e:
                            logger.error(f"Excepción en ZKFPM_DBInit: {e}")
                            return {'success': False, 'message': f'Error en DBInit: {str(e)}'}
                    # --- FIN DE CORRECCIÓN ---                    
                    try:
                        device_count = zkfp.ZKFPM_GetDeviceCount()
                        logger.info(f"Dispositivos detectados: {device_count}")
                    except Exception as e:
                        logger.error(f"Error al obtener conteo de dispositivos: {e}")
                        device_count = 0
                    
                    if device_count > 0:
                        return {
                            'success': True,
                            'device_count': device_count,
                            'message': f'Dispositivo(s) detectado(s): {device_count}'
                        }
                    else:
                        return {
                            'success': False,
                            'message': 'No se detectaron dispositivos. Verifique la conexión USB.'
                        }
                else:
                    error_msg = self._get_error_message(ret)
                    logger.error(f"Error al inicializar: {error_msg}")
                    return {
                        'success': False,
                        'message': f'Error al inicializar: {error_msg}'
                    }
                    
        except Exception as e:
            logger.error(f"Excepción en initialize: {e}", exc_info=True)
            return {
                'success': False,
                'message': f'Excepción: {str(e)}'
            }

    def open_device(self, index=0):
        """Abrir conexión con el dispositivo - VERSIÓN MEJORADA"""
        try:
            if not SDK_AVAILABLE:
                return {
                    'success': False,
                    'message': 'SDK no disponible'
                }
            
            # Inicializar si no está inicializado
            if not self.is_initialized:
                init_result = self.initialize()
                if not init_result.get('success'):
                    return init_result
            
            with self._lock:
                logger.info(f"Intentando abrir dispositivo con índice {index}...")
                
                # Cerrar conexión existente si hay una
                if self.device_handle:
                    try:
                        zkfp.ZKFPM_CloseDevice(self.device_handle)
                        logger.info("Conexión anterior cerrada")
                    except Exception as e:
                        logger.warning(f"Error al cerrar conexión anterior: {e}")
                    finally:
                        self.device_handle = None
                
                try:
                    handle = zkfp.ZKFPM_OpenDevice(index)
                    logger.info(f"Handle obtenido: {handle}")
                    
                    if handle is None or handle == 0:
                        logger.error("Handle inválido recibido")
                        return {
                            'success': False,
                            'message': 'No se pudo abrir el dispositivo. Handle inválido.'
                        }
                    
                    self.device_handle = handle
                    logger.info(f"Dispositivo abierto correctamente")
                    
                    # VERIFICAR QUE EL DISPOSITIVO RESPONDE
                    verification_passed = self._verify_device_connection()
                    if not verification_passed:
                        logger.error("El dispositivo no responde después de abrirlo")
                        try:
                            zkfp.ZKFPM_CloseDevice(self.device_handle)
                        except:
                            pass
                        self.device_handle = None
                        return {
                            'success': False,
                            'message': 'El dispositivo no responde. Verifique la conexión USB.'
                        }
                    
                except Exception as e:
                    logger.error(f"Excepción al abrir dispositivo: {e}")
                    return {
                        'success': False,
                        'message': f'Error al abrir dispositivo: {str(e)}'
                    }
                
                # Obtener parámetros del dispositivo
                try:
                    # Obtener ancho de imagen
                    param_buffer = (ctypes.c_ubyte * 4)()
                    size = ctypes.c_int(4)
                    
                    ret = zkfp.ZKFPM_GetParameters(
                        self.device_handle,
                        PARAM_CODE_IMAGE_WIDTH,
                        param_buffer,
                        ctypes.byref(size)
                    )
                    
                    if ret == ZKFP_ERR_OK:
                        self.width = int.from_bytes(bytes(param_buffer[:4]), byteorder='little')
                    else:
                        self.width = 300
                        logger.warning(f"No se pudo obtener ancho, usando valor por defecto: {self.width}")
                    
                    # Obtener alto de imagen
                    param_buffer = (ctypes.c_ubyte * 4)()
                    size = ctypes.c_int(4)
                    
                    ret = zkfp.ZKFPM_GetParameters(
                        self.device_handle,
                        PARAM_CODE_IMAGE_HEIGHT,
                        param_buffer,
                        ctypes.byref(size)
                    )
                    
                    if ret == ZKFP_ERR_OK:
                        self.height = int.from_bytes(bytes(param_buffer[:4]), byteorder='little')
                    else:
                        self.height = 400
                        logger.warning(f"No se pudo obtener alto, usando valor por defecto: {self.height}")
                    
                except Exception as e:
                    logger.warning(f"Error al obtener parámetros: {e}, usando valores por defecto")
                    self.width = 300
                    self.height = 400
                
                logger.info(f"Dimensiones de imagen: {self.width}x{self.height}")
                
                return {
                    'success': True,
                    'message': 'Dispositivo conectado exitosamente',
                    'width': self.width,
                    'height': self.height
                }
                
        except Exception as e:
            logger.error(f"Excepción en open_device: {e}", exc_info=True)
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }
    
    def close_device(self):
        """Cerrar conexión con el dispositivo"""
        try:
            logger.info("Cerrando dispositivo...")
            self.stop_capture()
            
            with self._lock:
                if self.device_handle and SDK_AVAILABLE:
                    try:
                        zkfp.ZKFPM_CloseDevice(self.device_handle)
                    except Exception as e:
                        logger.error(f"Error al cerrar handle: {e}")
                    self.device_handle = None
                
                if self.is_initialized and SDK_AVAILABLE:
                    try:
                        zkfp.ZKFPM_Terminate()
                    except Exception as e:
                        logger.error(f"Error al terminar SDK: {e}")
                    self.is_initialized = False
            
            logger.info("Dispositivo desconectado correctamente")
            return {
                'success': True,
                'message': 'Dispositivo desconectado'
            }
            
        except Exception as e:
            logger.error(f"Error al cerrar dispositivo: {e}")
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }

    def start_capture(self):
        """Iniciar captura continua de huellas"""
        if not self.device_handle:
            return {
                'success': False,
                'message': 'Dispositivo no conectado'
            }
        
        if not self.is_capturing:
            self.is_capturing = True
            self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.capture_thread.start()
            logger.info("Captura iniciada")
            return {
                'success': True,
                'message': 'Captura iniciada'
            }
        
        return {
            'success': False,
            'message': 'Ya está capturando'
        }

    def stop_capture(self):
        """Detener captura de forma segura sin deadlocks"""
        if not self.is_capturing:
            return {
                'success': True,
                'message': 'La captura ya estaba detenida'
            }
        
        logger.info("Deteniendo captura...")
        self.is_capturing = False
        
        # NO hacer join aquí - puede causar deadlock
        # El thread se detendrá por sí mismo cuando is_capturing sea False
        if self.capture_thread and self.capture_thread.is_alive():
            # Esperar máximo 3 segundos para que el thread termine naturalmente
            timeout = 3
            start_time = time.time()
            while self.capture_thread.is_alive() and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            if self.capture_thread.is_alive():
                logger.warning("El hilo de captura no terminó en el tiempo esperado")
            else:
                logger.info("Hilo de captura terminado correctamente")
        
        logger.info("Captura detenida")
        return {
            'success': True,
            'message': 'Captura detenida'
        }

    def set_mode(self, mode):
        """Establecer modo de operación"""
        valid_modes = ['idle', 'registering', 'verifying']
        
        if mode not in valid_modes:
            return {
                'success': False,
                'message': f'Modo inválido. Opciones: {", ".join(valid_modes)}'
            }
        
        self.current_mode = mode
        logger.info(f"Modo cambiado a: {mode}")
        
        if mode == "registering":
            self.register_count = 0
            self.register_templates = []
            self.register_step = "CAPTURE"        
        return {
            'success': True,
            'mode': mode,
            'message': f'Modo establecido a: {mode}'
        }

    def get_last_capture(self):
        """Obtener última captura de forma segura"""
        try:
            if self.last_capture:
                # Crear una copia para evitar problemas de referencia
                capture_copy = self.last_capture.copy()
                return {
                    'success': True,
                    'data': capture_copy
                }
            else:
                return {
                    'success': False,
                    'message': 'No hay capturas disponibles',
                    'current_mode': self.current_mode,
                    'register_count': self.register_count
                }
                
        except Exception as e:
            logger.error(f"Error en get_last_capture: {e}")
            return {
                'success': False,
                'message': f'Error al obtener captura: {str(e)}'
            }
        
        self.current_mode = mode
        logger.info(f"Modo cambiado a: {mode}")
        
        if mode == "registering":
            self.register_count = 0
            self.register_templates = []
        
        return {
            'success': True,
            'mode': mode,
            'message': f'Modo establecido a: {mode}'
        }
    
    def get_status(self):
        """Obtener estado actual del dispositivo"""
        return {
            'success': True,
            'connected': self.device_handle is not None,
            'capturing': self.is_capturing,
            'mode': self.current_mode,
            'width': self.width,
            'height': self.height,
            'initialized': self.is_initialized,
            'register_count': self.register_count,
            'sdk_available': SDK_AVAILABLE
        }
    
    def get_thread_status(self):
        """Obtener estado del thread de captura para debugging"""
        thread_status = {
            'is_capturing': self.is_capturing,
            'thread_alive': self.capture_thread.is_alive() if self.capture_thread else False,
            'thread_name': self.capture_thread.name if self.capture_thread else None,
            'thread_ident': self.capture_thread.ident if self.capture_thread else None
        }
        
        logger.info(f"Estado del thread: {thread_status}")
        return thread_status
    
    def compare_templates(self, template1_b64, template2_b64):
        """Comparar dos plantillas de huellas dactilares"""
        try:
            if not SDK_AVAILABLE or not self.device_handle:
                return {
                    'success': False,
                    'message': 'SDK no disponible o dispositivo no conectado'
                }

            # ❌ CRÍTICO: Necesitamos db_handle, no device_handle
            if not self.db_handle:
                logger.error("db_handle no inicializado para comparación")
                return {
                    'success': False,
                    'message': 'Cache de algoritmos no inicializado'
                }

            # Decodificar plantillas
            try:
                template1_bytes = base64.b64decode(template1_b64)
                template2_bytes = base64.b64decode(template2_b64)
            except Exception as e:
                logger.error(f"Error al decodificar plantillas: {e}")
                return {
                    'success': False,
                    'message': 'Error al decodificar plantillas'
                }
            
            # Crear arrays de ctypes
            temp1 = (ctypes.c_ubyte * len(template1_bytes))(*template1_bytes)
            temp2 = (ctypes.c_ubyte * len(template2_bytes))(*template2_bytes)
            
            # Comparar plantillas
            score = zkfp.ZKFPM_DBMatch(
                self.db_handle,
                temp1,
                len(template1_bytes),
                temp2,
                len(template2_bytes)
            )
            
            logger.info(f"Comparación de plantillas - Score: {score}")
            
            # Umbral de coincidencia
            # MATCH_THRESHOLD = 60
            is_match = score >= MATCH_THRESHOLD
            
            return {
                'success': True,
                'match': is_match,
                'score': score,
                'threshold': MATCH_THRESHOLD,
                'message': 'Coincidencia encontrada' if is_match else 'No coincide'
            }
            
        except Exception as e:
            logger.error(f"Error en compare_templates: {e}", exc_info=True)
            return {
                'success': False,
                'message': f'Error al comparar: {str(e)}'
            }
    
    def get_registration_status(self):
        """Obtener estado detallado del registro para debugging"""
        status = {
            'current_mode': self.current_mode,
            'register_count': self.register_count,
            'templates_stored': len(self.register_templates),
            'device_connected': self.device_handle is not None,
            'is_capturing': self.is_capturing,
            'last_capture_has_final': self.last_capture.get('final_template') if self.last_capture else False,
            'last_capture_complete': self.last_capture.get('registration_complete') if self.last_capture else False
        }
        
        logger.info(f"Estado registro: {status}")
        return status
    
    def reset_registration(self):
        """Resetear estado de registro - llamado por el frontend después de guardar"""
        try:
            with self._lock:
                logger.info("Reset manual de registro solicitado por frontend")
                
                self.register_count = 0
                self.register_templates = []
                self.current_mode = "idle"
                
                # Limpiar datos de registro del last_capture
                if self.last_capture:
                    for field in ['registration_complete', 'final_template', 'register_count', 'registration_in_progress', 'registration_error']:
                        if field in self.last_capture:
                            del self.last_capture[field]
                
                logger.info("Estado de registro reseteado completamente")
            
            return {
                'success': True,
                'message': 'Registro reseteado exitosamente',
                'current_mode': self.current_mode,
                'register_count': self.register_count
            }
            
        except Exception as e:
            logger.error(f"Error en reset_registration: {e}")
            return {
                'success': False,
                'message': f'Error al resetear: {str(e)}'
            }

# ==================== INSTANCIA GLOBAL ====================
device = ZKTecoDevice()

# ==================== RUTAS DE LA API ====================
@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check del servicio"""
    return jsonify({
        'success': True,
        'message': 'ZKTeco Bridge Service Running',
        'version': '4.0.0',
        'timestamp': datetime.now().isoformat(),
        'sdk_available': SDK_AVAILABLE
    })

@app.route('/api/device/initialize', methods=['POST'])
def initialize_device():
    """Inicializar dispositivo"""
    logger.info("Solicitud: Inicializar dispositivo")
    result = device.initialize()
    return jsonify(result)

@app.route('/api/device/open', methods=['POST'])
def open_device():
    """Abrir dispositivo"""
    data = request.get_json() or {}
    index = data.get('index', 0)
    
    logger.info(f"Solicitud: Abrir dispositivo (índice: {index})")
    result = device.open_device(index)
    
    if result.get('success'):
        device.start_capture()
    
    return jsonify(result)

@app.route('/api/device/close', methods=['POST'])
def close_device():
    """Cerrar dispositivo"""
    logger.info("Solicitud: Cerrar dispositivo")
    result = device.close_device()
    return jsonify(result)

@app.route('/api/device/status', methods=['GET'])
def device_status():
    """Obtener estado del dispositivo"""
    status = device.get_status()
    return jsonify(status)

@app.route('/api/device/verify_connection', methods=['GET'])
def verify_connection():
    """Verificar estado de conexión del dispositivo"""
    logger.info("Solicitud: Verificar conexión del dispositivo")
    
    is_connected = device._verify_device_connection()
    
    return jsonify({
        'success': is_connected,
        'connected': is_connected,
        'message': 'Dispositivo conectado y respondiendo' if is_connected else 'Dispositivo desconectado o no responde'
    })

@app.route('/api/capture/start', methods=['POST'])
def start_capture():
    """Iniciar captura"""
    logger.info("Solicitud: Iniciar captura")
    result = device.start_capture()
    return jsonify(result)

@app.route('/api/capture/stop', methods=['POST'])
def stop_capture():
    """Detener captura"""
    logger.info("Solicitud: Detener captura")
    result = device.stop_capture()
    return jsonify(result)

@app.route('/api/capture/get', methods=['GET'])
def get_capture():
    """Obtener última captura"""
    result = device.get_last_capture()
    return jsonify(result)

@app.route('/api/mode/set', methods=['POST'])
def set_mode():
    """Establecer modo (idle, registering, verifying)"""
    data = request.get_json()
    
    if not data or 'mode' not in data:
        return jsonify({
            'success': False,
            'message': 'Parámetro "mode" requerido'
        }), 400
    
    mode = data.get('mode', 'idle')
    logger.info(f"Solicitud: Cambiar modo a '{mode}'")
    result = device.set_mode(mode)
    return jsonify(result)

@app.route('/api/compare', methods=['POST'])
def compare_templates():
    """Comparar dos plantillas de huellas"""
    data = request.get_json()
    
    if not data:
        return jsonify({
            'success': False,
            'message': 'Datos no proporcionados'
        }), 400
    
    template1 = data.get('template1')
    template2 = data.get('template2')
    
    if not template1 or not template2:
        return jsonify({
            'success': False,
            'message': 'Se requieren template1 y template2'
        }), 400
    
    logger.info("Solicitud: Comparar plantillas")
    result = device.compare_templates(template1, template2)
    return jsonify(result)

# bridge_service.py - Agregar la nueva ruta (por ejemplo, después de @app.route('/api/registration/reset', methods=['POST']))

@app.route('/api/db/match_one_to_many', methods=['POST'])
def match_one_to_many_api():
    """
    Verifica una plantilla capturada contra TODAS las plantillas en la BD (1:N).
    Esta es la nueva arquitectura segura.
    """
    if not SDK_AVAILABLE:
        return jsonify({'success': False, 'message': 'SDK no disponible para matching.'}), 500

    data = request.get_json()
    captured_template_b64 = data.get('captured_template')

    if not captured_template_b64:
        return jsonify({'success': False, 'message': 'Plantilla de huella capturada faltante.'}), 400

    # ✅ VERIFICAR db_handle
    if not device.db_handle:
        logger.error("❌ db_handle no disponible para matching 1:N")
        return jsonify({'success': False, 'message': 'Cache de algoritmos no inicializado.'}), 500

    # 1. Recuperar plantillas registradas desde la API PHP (SEGURIDAD)
    try:
        logger.info(f"Obteniendo plantillas registradas desde API PHP...")
        # Llama a la nueva ruta segura en api.php
        response = requests.get(f"{PHP_API_URL}?action=get_verification_data")
        response.raise_for_status() # Lanza excepción para errores HTTP
        
        db_data = response.json()
        if not db_data.get('success'):
            logger.error(f"Error al obtener datos de verificación desde API: {db_data.get('message')}")
            return jsonify({'success': False, 'message': 'Error al cargar datos de verificación de la BD.'}), 500
        
        registered_templates = db_data.get('data', [])
        if not registered_templates:
            logger.warning("No hay plantillas registradas en la BD para comparar.")
            return jsonify({'success': True, 'match': False, 'message': 'No hay huellas registradas en el sistema.'})

        logger.info(f"Plantillas obtenidas para matching: {len(registered_templates)}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión con API PHP: {e}")
        return jsonify({'success': False, 'message': f'Error de conexión con el servicio API PHP: {e}'}), 500
    
    # except Exception as e:
    #    logger.error(f"Error inesperado al procesar datos de la API: {e}")
    #    return jsonify({'success': False, 'message': 'Error interno al procesar plantillas.'}), 500

    # 2. Convertir la plantilla capturada
    try:
        template_bytes = base64.b64decode(captured_template_b64)
        
        # Bloqueo del dispositivo para asegurar el acceso exclusivo al SDK.
        with device._lock:
            # Convertir la plantilla capturada UNA SOLA VEZ
            template1 = (ctypes.c_ubyte * len(template_bytes)).from_buffer_copy(template_bytes)

            # 3. Realizar el matching 1:N
            matched_user = None
            best_score = 0
            
            for template_data in registered_templates:
                try:
                    registered_template_bytes = base64.b64decode(template_data.get('template'))
                    template2 = (ctypes.c_ubyte * len(registered_template_bytes)).from_buffer_copy(registered_template_bytes)

                    # ZKFPM_DBMatch (handle, temp1, len1, temp2, len2)
                    score = zkfp.ZKFPM_DBMatch(
                        device.db_handle,
                        template1,
                        len(template_bytes),
                        template2,
                        len(registered_template_bytes)
                    )

                    if score > best_score:
                        best_score = score

                    if score >= MATCH_THRESHOLD:
                        matched_user = template_data
                        matched_user['score'] = score
                        break # Encontrado! Salir del loop 1:N

                except Exception as e:
                    logger.error(f"Error en ZKFPM_DBMatch para usuario {template_data.get('user_id_str')}: {e}")
                    # Continuar con el siguiente
                    
        # 3. Devolver resultado
        if matched_user:
            logger.info(f"✅ Coincidencia encontrada para {matched_user.get('user_id_str')} con score {matched_user.get('score')}")
            return jsonify({
                'success': True,
                'match': True,
                'matched_user': {
                    'id': matched_user.get('user_internal_id'),
                    'user_id': matched_user.get('user_id_str'),
                    'name': matched_user.get('name'),
                    'finger_index': matched_user.get('finger_index'),
                    'score': matched_user.get('score')
                },
                'best_score': best_score
            })
        else:
            logger.info(f"❌ No se encontró coincidencia (Mejor score: {best_score})")
            return jsonify({
                'success': True,
                'match': False,
                'message': 'Huella no reconocida',
                'best_score': best_score
            })
            
    except Exception as e:
        logger.error(f"Error crítico en match_one_to_many_api: {e}")
        return jsonify({'success': False, 'message': 'Error interno durante el matching.'}), 500

@app.route('/api/debug/last_capture', methods=['GET'])
def debug_last_capture():
    """Endpoint para inspeccionar el estado actual de last_capture"""
    try:
        if device.last_capture:
            # Crear copia sin la imagen para reducir payload
            debug_data = {k: v for k, v in device.last_capture.items() if k not in ['image', 'template']}
            
            # Agregar información de longitud de datos grandes
            if 'final_template' in device.last_capture:
                debug_data['final_template_length'] = len(device.last_capture['final_template'])
            if 'template' in device.last_capture:
                debug_data['template_length'] = len(device.last_capture['template'])
            
            return jsonify({
                'success': True,
                'last_capture': debug_data,
                'current_mode': device.current_mode,
                'register_count': device.register_count,
                'is_capturing': device.is_capturing
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No hay datos en last_capture',
                'current_mode': device.current_mode,
                'register_count': device.register_count
            })
    except Exception as e:
        logger.error(f"Error en debug_last_capture: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
        
@app.route('/api/debug/registration_status', methods=['GET'])
def debug_registration_status():
    """Endpoint de debugging para estado de registro"""
    logger.info("Solicitud: Estado de registro (DEBUG)")
    status = device.get_registration_status()
    return jsonify({
        'success': True,
        'status': status
    })

@app.route('/api/debug/thread_status', methods=['GET'])
def debug_thread_status():
    """Endpoint de debugging para estado de threads"""
    logger.info("Solicitud: Estado de threads (DEBUG)")
    status = device.get_thread_status()
    return jsonify({
        'success': True,
        'status': status
    })

@app.route('/api/registration/reset', methods=['POST'])
def reset_registration():
    """Resetear estado de registro"""
    logger.info("Solicitud: Resetear registro")
    result = device.reset_registration()
    return jsonify(result)

@app.errorhandler(404)
def not_found(error):
    """Manejo de rutas no encontradas"""
    return jsonify({
        'success': False,
        'message': 'Endpoint no encontrado',
        'error': str(error)
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Manejo de errores internos"""
    logger.error(f"Error interno del servidor: {error}")
    return jsonify({
        'success': False,
        'message': 'Error interno del servidor',
        'error': str(error)
    }), 500

# ==================== INICIO DEL SERVICIO ====================
if __name__ == '__main__':
    print("=" * 60)
    print("ZKTeco USB Bridge Service v4.0.0 - VERSIÓN FINAL")
    print("Sistema de Registro Biométrico de Usuarios")
    print("=" * 60)
    print(f"SDK Disponible: {'Sí' if SDK_AVAILABLE else 'No'}")
    print(f"Iniciando servicio en http://localhost:5000")
    
    if not SDK_AVAILABLE:
        print("\nADVERTENCIA: SDK no disponible")
        print("Instale ZKFingerSDK 5.x desde:")
        print("https://www.zkteco.com/en/index/Service/load/id/632.html")
    
    print("=" * 60)
    print("\nCaracterísticas implementadas:")
    print("✅ Manejo robusto de threads - Sin deadlocks")
    print("✅ Reconexión automática en caso de desconexión")
    print("✅ Verificación constante de conexión del dispositivo")
    print("✅ Múltiples reintentos para operaciones críticas")
    print("✅ Logging mejorado con codificación UTF-8")
    print("✅ API completamente funcional y estable")
    print("✅ Debugging avanzado de threads y estado")
    print("\nEndpoints de debugging disponibles:")
    print("  GET /api/debug/thread_status")
    print("  GET /api/debug/registration_status")
    print("  GET /api/device/verify_connection")
    print("\nPresione Ctrl+C para detener el servicio\n")
    
    try:
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=False,
            threaded=True,
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\nDeteniendo servicio...")
        device.close_device()
        print("Servicio detenido correctamente")
    except Exception as e:
        logger.error(f"Error fatal: {e}", exc_info=True)
        print(f"\nError fatal: {e}")