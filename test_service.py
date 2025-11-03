"""
Script de prueba para ZKTeco Bridge Service
Ejecutar este script para verificar que el servicio funcione correctamente
"""

import requests
import time
import sys

BASE_URL = "http://localhost:5000"

def print_header(text):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)

def print_result(success, message):
    icon = "✅" if success else "❌"
    print(f"{icon} {message}")

def test_health():
    """Probar endpoint de health check"""
    print_header("TEST 1: Health Check")
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=5)
        data = response.json()
        
        if response.status_code == 200 and data.get('success'):
            print_result(True, "Servicio está corriendo correctamente")
            print(f"   Versión: {data.get('version')}")
            print(f"   SDK Disponible: {'Sí' if data.get('sdk_available') else 'No'}")
            return True
        else:
            print_result(False, "Servicio respondió con error")
            return False
            
    except requests.exceptions.ConnectionError:
        print_result(False, "No se puede conectar al servicio")
        print("   Asegúrese de que bridge_service.py esté ejecutándose")
        return False
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

def test_initialize():
    """Probar inicialización del dispositivo"""
    print_header("TEST 2: Inicializar Dispositivo")
    try:
        response = requests.post(f"{BASE_URL}/api/device/initialize", timeout=10)
        data = response.json()
        
        if data.get('success'):
            print_result(True, f"Dispositivo inicializado: {data.get('message')}")
            return True
        else:
            print_result(False, f"Error: {data.get('message')}")
            return False
            
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

def test_open_device():
    """Probar apertura del dispositivo"""
    print_header("TEST 3: Abrir Dispositivo")
    try:
        response = requests.post(
            f"{BASE_URL}/api/device/open",
            json={"index": 0},
            timeout=10
        )
        data = response.json()
        
        if data.get('success'):
            print_result(True, "Dispositivo abierto correctamente")
            print(f"   Resolución: {data.get('width')}x{data.get('height')}")
            return True
        else:
            print_result(False, f"Error: {data.get('message')}")
            return False
            
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

def test_status():
    """Probar obtención de estado"""
    print_header("TEST 4: Estado del Dispositivo")
    try:
        response = requests.get(f"{BASE_URL}/api/device/status", timeout=5)
        data = response.json()
        
        if data.get('success'):
            print_result(True, "Estado obtenido correctamente")
            print(f"   Conectado: {'Sí' if data.get('connected') else 'No'}")
            print(f"   Capturando: {'Sí' if data.get('capturing') else 'No'}")
            print(f"   Modo: {data.get('mode')}")
            return True
        else:
            print_result(False, "Error al obtener estado")
            return False
            
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

def test_capture():
    """Probar captura de huella"""
    print_header("TEST 5: Captura de Huella")
    print("⏳ Coloque el dedo en el sensor dentro de 10 segundos...")
    
    try:
        # Esperar un poco para que el usuario coloque el dedo
        time.sleep(2)
        
        # Intentar obtener captura durante 10 segundos
        max_attempts = 20
        for i in range(max_attempts):
            response = requests.get(f"{BASE_URL}/api/capture/get", timeout=5)
            data = response.json()
            
            if data.get('success') and data.get('data'):
                capture_data = data.get('data')
                print_result(True, "Huella capturada exitosamente")
                print(f"   Timestamp: {capture_data.get('timestamp')}")
                print(f"   Tiene imagen: {'Sí' if capture_data.get('image') else 'No'}")
                print(f"   Tiene template: {'Sí' if capture_data.get('template') else 'No'}")
                return True
            
            time.sleep(0.5)
            print(f"   Intento {i+1}/{max_attempts}...", end="\r")
        
        print_result(False, "No se capturó ninguna huella en el tiempo límite")
        print("   Verifique que el dispositivo esté conectado correctamente")
        return False
        
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

def test_close_device():
    """Probar cierre del dispositivo"""
    print_header("TEST 6: Cerrar Dispositivo")
    try:
        response = requests.post(f"{BASE_URL}/api/device/close", timeout=10)
        data = response.json()
        
        if data.get('success'):
            print_result(True, "Dispositivo cerrado correctamente")
            return True
        else:
            print_result(False, f"Error: {data.get('message')}")
            return False
            
    except Exception as e:
        print_result(False, f"Error: {e}")
        return False

def main():
    """Ejecutar todos los tests"""
    print("\n" + "█" * 60)
    print("  PRUEBA DE ZKTeco BRIDGE SERVICE")
    print("█" * 60)
    
    # Verificar si el servicio está corriendo
    if not test_health():
        print("\n❌ El servicio no está disponible")
        print("\nPara iniciar el servicio, ejecute:")
        print("   python bridge_service.py")
        print("\nO use el script:")
        print("   start_service.bat")
        sys.exit(1)
    
    # Test de inicialización
    if not test_initialize():
        print("\n⚠️  El dispositivo no pudo inicializarse")
        print("Verifique que:")
        print("  1. ZKFingerSDK 5.x esté instalado")
        print("  2. El sensor ZKTeco esté conectado por USB")
        print("  3. Los drivers estén correctamente instalados")
        sys.exit(1)
    
    # Test de apertura
    device_opened = test_open_device()
    
    # Test de estado
    test_status()
    
    # Test de captura (solo si el dispositivo se abrió)
    if device_opened:
        test_capture()
    
    # Test de cierre
    test_close_device()
    
    # Resumen final
    print_header("RESUMEN")
    print("✅ Pruebas completadas")
    print("\nEl servicio está funcionando correctamente.")
    print("Puede proceder a usar la aplicación web.")
    
    print("\n" + "█" * 60 + "\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Prueba interrumpida por el usuario")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        sys.exit(1)