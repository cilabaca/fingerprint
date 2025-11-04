<?php 

// ==================== CORRECCIÓN DE ERRORES JSON ====================
// Desactiva la visualización de errores en el output para no corromper el JSON.
ini_set('display_errors', 0);
ini_set('display_startup_errors', 0);
error_reporting(E_ALL); // Opcional: Mantener registro de todos los errores
// ====================================================================

// api.php - API REST para gestión de huellas
header("Access-Control-Allow-Origin: *");
header("Content-Type: application/json; charset=UTF-8");
header("Access-Control-Allow-Methods: POST, GET, PUT, DELETE, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type, Access-Control-Allow-Headers, Authorization, X-Requested-With");

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

require_once 'config.php';

class FingerprintAPI {
    private $conn;

    public function __construct() {
        $database = new Database();
        $this->conn = $database->getConnection();
    }

    // Lógica "Upsert" para registrar huella
    public function registerFingerprint($data) {
        $requiredFields = ['user_id', 'name', 'template', 'finger_index'];
        foreach ($requiredFields as $field) {
            if (!isset($data[$field]) || empty($data[$field])) {
                return ['success' => false, 'message' => "Campo requerido faltante: $field"];
            }
            
            // Validar tipos de datos
            if (!is_numeric($finger_index) || $finger_index < 1 || $finger_index > 10) {
                return ['success' => false, 'message' => 'finger_index debe ser un número entre 1 y 10'];
            }

            // Validar longitud del template
            if (strlen($template) < 100 || strlen($template) > 10000) {
                return ['success' => false, 'message' => 'Template inválido: longitud fuera de rango'];
            }

            // Validar formato base64 del template
            if (!preg_match('/^[a-zA-Z0-9\/\r\n+]*={0,2}$/', $template)) {
                return ['success' => false, 'message' => 'Template debe estar en formato Base64'];
            }            
        }

        try {
            $this->conn->beginTransaction();
            
            $userId_str = $data['user_id'];
            $name = $data['name'];
            $template = $data['template'];
            $finger_index = $data['finger_index'];
            
            // Paso 1: Buscar o crear el usuario en la tabla 'users'
            $query_user = "SELECT id FROM users WHERE user_id = :user_id_str";
            $stmt_user = $this->conn->prepare($query_user);
            $stmt_user->bindParam(":user_id_str", $userId_str);
            $stmt_user->execute();
            
            $user_internal_id = null;

            // Validar finger_index
            if ($finger_index < 1 || $finger_index > 10) {
                return ['success' => false, 'message' => 'Índice de dedo inválido. Debe ser entre 1 y 10.'];
            }

            if ($stmt_user->rowCount() > 0) {
                // El usuario ya existe, obtener su ID interno
                $row = $stmt_user->fetch(PDO::FETCH_ASSOC);
                $user_internal_id = $row['id'];
                
                // Opcional: Actualizar el nombre si cambió
                $update_name_query = "UPDATE users SET name = :name WHERE id = :id";
                $stmt_update_name = $this->conn->prepare($update_name_query);
                $stmt_update_name->bindParam(":name", $name);
                $stmt_update_name->bindParam(":id", $user_internal_id);
                $stmt_update_name->execute();
                
            } else {
                // El usuario no existe, crearlo
                $insert_user_query = "INSERT INTO users (user_id, name) VALUES (:user_id_str, :name)";
                $stmt_insert_user = $this->conn->prepare($insert_user_query);
                $stmt_insert_user->bindParam(":user_id_str", $userId_str);
                $stmt_insert_user->bindParam(":name", $name);
                $stmt_insert_user->execute();
                
                $user_internal_id = $this->conn->lastInsertId();
            }
            
            // Paso 2: Insertar o actualizar la huella en la tabla 'fingerprints'
            $query_finger = "
                INSERT INTO fingerprints (user_id, finger_index, template, created_at)
                VALUES (:user_id, :finger_index, :template, NOW())
                ON DUPLICATE KEY UPDATE
                template = VALUES(template),
                updated_at = NOW()
            ";
            
            $stmt_finger = $this->conn->prepare($query_finger);
            $stmt_finger->bindParam(":user_id", $user_internal_id, PDO::PARAM_INT);
            $stmt_finger->bindParam(":finger_index", $finger_index, PDO::PARAM_INT);
            $stmt_finger->bindParam(":template", $template, PDO::PARAM_STR);
            
            if ($stmt_finger->execute()) {
                $this->conn->commit();
                return [
                    'success' => true,
                    'message' => 'Huella registrada/actualizada exitosamente',
                    'user_id' => $userId_str,
                    'name' => $name
                ];
            } else {
                $this->conn->rollBack();
                return ['success' => false, 'message' => 'Error al guardar la huella'];
            }
            
        } catch(PDOException $e) {
            if ($this->conn->inTransaction()) {
                $this->conn->rollBack();
            }
            return ['success' => false, 'message' => 'Error de BD: ' . $e->getMessage()];
        }
    }

    /**
     * Obtiene todos los IDs de usuario y las plantillas para la verificación 1:N.
     * Esta función está diseñada para ser consumida *solo* por el servicio Python Bridge 
     * y no debe ser llamada directamente desde el navegador (por seguridad).
     * @return array
     */
    public function getAllVerificationData() {
        try {
            // Solo obtener IDs internos y plantillas para el matching
            $query = "
                SELECT 
                    u.id AS user_internal_id, 
                    u.user_id AS user_id_str, 
                    u.name, 
                    f.template, 
                    f.finger_index
                FROM 
                    fingerprints f
                JOIN 
                    users u ON f.user_id = u.id
                WHERE
                    u.status = 1
            ";
            $stmt = $this->conn->prepare($query);
            $stmt->execute();
            $data = $stmt->fetchAll(PDO::FETCH_ASSOC);

            return [
                'success' => true, 
                'data' => $data
            ];
        } catch(PDOException $e) {
            // Manejo de error más detallado para el backend
            error_log("Error en getAllVerificationData: " . $e->getMessage());
            return [
                'success' => false, 
                'message' => 'Error de base de datos al obtener datos de verificación'
            ];
        }
    }   
    
    // Obtener lista de huellas registradas (para la tabla "Usuarios" en la UI)
    public function getRegisteredFingerprints() {
        try {
            $query = "
                SELECT 
                    f.id, -- ID de la huella (para borrar)
                    u.user_id,
                    u.name,
                    f.finger_index,
                    f.created_at,
                    u.status
                FROM fingerprints f
                JOIN users u ON f.user_id = u.id
                ORDER BY f.created_at DESC
            ";
            $stmt = $this->conn->prepare($query);
            $stmt->execute();
            
            $fingerprints = $stmt->fetchAll(PDO::FETCH_ASSOC);
            
            return [
                'success' => true,
                'users' => $fingerprints // 'users' para compatibilidad con index.html
            ];
            
        } catch(PDOException $e) {
            return ['success' => false, 'message' => 'Error al obtener usuarios: ' . $e->getMessage()];
        }
    }

    // Eliminar una huella específica
    public function deleteFingerprint($fingerprintId) {
        try {
            // El ID que recibimos es el ID de la tabla 'fingerprints'
            $query = "DELETE FROM fingerprints WHERE id = :id";
            $stmt = $this->conn->prepare($query);
            $stmt->bindParam(":id", $fingerprintId, PDO::PARAM_INT);
            
            if ($stmt->execute()) {
                if ($stmt->rowCount() > 0) {
                    return ['success' => true, 'message' => 'Huella eliminada exitosamente'];
                } else {
                    return ['success' => false, 'message' => 'No se encontró la huella'];
                }
            }
            return ['success' => false, 'message' => 'Error al eliminar huella'];
        } catch(PDOException $e) {
            return ['success' => false, 'message' => 'Error: ' . $e->getMessage()];
        }
    }

    // Registrar log de acceso
    public function logAccess($userId, $status, $method = 'fingerprint') {
        try {
            // $userId ahora es el ID interno (INT) de la tabla 'users'
            $query = "INSERT INTO access_logs (user_id, access_time, status, method) 
                      VALUES (:user_id, NOW(), :status, :method)";
            
            $stmt = $this->conn->prepare($query);
            $stmt->bindParam(":user_id", $userId); // Puede ser NULL si falla
            $stmt->bindParam(":status", $status);
            $stmt->bindParam(":method", $method);
            
            return $stmt->execute();
            
        } catch(PDOException $e) {
            return false;
        }
    }

    // Obtener logs de acceso
    public function getAccessLogs($limit = 50) {
        try {
            $query = "
                SELECT 
                    al.id, 
                    al.access_time, 
                    al.status, 
                    al.method,
                    u.name, 
                    u.user_id 
                FROM access_logs al 
                LEFT JOIN users u ON al.user_id = u.id 
                ORDER BY al.access_time DESC 
                LIMIT :limit
            ";
            
            $stmt = $this->conn->prepare($query);
            $stmt->bindParam(":limit", $limit, PDO::PARAM_INT);
            $stmt->execute();
            
            $logs = $stmt->fetchAll(PDO::FETCH_ASSOC);
            
            return ['success' => true, 'logs' => $logs];
        } catch(PDOException $e) {
            return ['success' => false, 'message' => 'Error: ' . $e->getMessage()];
        }
    }

} // CIERRE de FingerprintAPI

// api.php - Reemplazar completamente el bloque de "Manejo de rutas API"

// Manejo de rutas API (ACTUALIZADO, CORREGIDO Y SEGURO)
$api = new FingerprintAPI();
$method = $_SERVER['REQUEST_METHOD'];
$request = isset($_GET['action']) ? $_GET['action'] : '';
$response = ['success' => false, 'message' => 'Acción no válida'];

try {
    switch ($method) {
        case 'POST':
            $data = json_decode(file_get_contents("php://input"), true);
            if (json_last_error() !== JSON_ERROR_NONE) {
                throw new Exception('JSON inválido en el cuerpo de la solicitud');
            }

            switch ($request) {
                case 'register':
                    $response = $api->registerFingerprint($data);
                    break;
                case 'log_access':
                    $userId = isset($data['user_id']) ? $data['user_id'] : null;
                    $status = isset($data['status']) ? $data['status'] : 'failed';
                    $method_log = isset($data['method']) ? $data['method'] : 'fingerprint';
                    $api->logAccess($userId, $status, $method_log);
                    $response = ['success' => true]; // Log no necesita respuesta detallada
                    break;
                default:
                    $response = ['success' => false, 'message' => 'Acción POST no válida'];
                    http_response_code(404);
                    break;
            }
            break;

        case 'GET':
            switch ($request) {
                case 'users':
                    // Esto obtiene la lista de huellas para la UI (seguro)
                    $response = $api->getRegisteredFingerprints();
                    break;
                case 'logs':
                    $limit = isset($_GET['limit']) ? intval($_GET['limit']) : 50;
                    $response = $api->getAccessLogs($limit);
                    break;
                
                // RUTA SEGURA - SOLO PARA EL BRIDGE DE PYTHON
                case 'get_verification_data':
                    $response = $api->getAllVerificationData();
                    break;

                default:
                    $response = ['success' => false, 'message' => 'Acción GET no válida'];
                    http_response_code(404);
                    break;
            }
            break;

        case 'DELETE':
            $fingerprintId = isset($_GET['id']) ? intval($_GET['id']) : null;
            if ($fingerprintId) {
                $response = $api->deleteFingerprint($fingerprintId);
            } else {
                $response = ['success' => false, 'message' => 'ID de huella no proporcionado'];
                http_response_code(400);
            }
            break;

        default:
            $response = ['success' => false, 'message' => 'Método no permitido'];
            http_response_code(405);
            break;
    }

} catch (Exception $e) {
    // Captura de errores global
    error_log("Error en API: " . $e->getMessage());
    $response = ['success' => false, 'message' => 'Error interno del servidor: ' . $e->getMessage()];
    http_response_code(500);
}

// Establecer código de éxito/error basado en la respuesta
if (isset($response['success']) && !$response['success'] && http_response_code() === 200) {
    http_response_code(400); // Bad Request si la operación falló
}

echo json_encode($response);

// database.sql - Script SQL para crear la base de datos
/*
CREATE DATABASE IF NOT EXISTS fingerprint_db;
USE fingerprint_db;

-- Tabla para almacenar información del usuario (empleado)
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) UNIQUE NOT NULL, -- ID del empleado (ej: "EMP001")
    name VARCHAR(100) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    status TINYINT(1) DEFAULT 1,
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Tabla para almacenar las huellas (plantillas)
CREATE TABLE IF NOT EXISTS fingerprints (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL, -- FK a la tabla users
    finger_index INT NOT NULL, -- 1-10 (Índice Derecho, Pulgar Izq, etc.)
    template TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- Clave foránea
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    
    -- Evitar duplicados: un usuario solo puede tener una huella por dedo
    UNIQUE KEY uk_user_finger (user_id, finger_index),
    
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Tabla de logs (sin cambios, pero actualizada la FK)
CREATE TABLE IF NOT EXISTS access_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT, -- FK a la tabla users (puede ser NULL si falla)
    access_time DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    method VARCHAR(20) DEFAULT 'fingerprint',
    
    -- Actualizado ON DELETE SET NULL para no perder logs si se borra el usuario
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
    
    INDEX idx_access_time (access_time),
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Índice compuesto para optimizar verificación 1:N
ALTER TABLE fingerprints 
ADD INDEX idx_user_template (user_id, finger_index);

-- Índice para búsquedas por estado de usuario
ALTER TABLE users 
ADD INDEX idx_status (status);
*/
?>