<?php
// config.php - Configuración de Base de Datos
class Database {
    private $host = "localhost";
    private $db_name = "fingerprint_db";
    private $username = "root";
    private $password = "";
    public $conn;

    public function getConnection() {
        $this->conn = null;
        try {
            $this->conn = new PDO(
                "mysql:host=" . $this->host . ";dbname=" . $this->db_name . ";charset=utf8", 
                $this->username, 
                $this->password
            );
            $this->conn->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
            $this->conn->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
        } catch(PDOException $exception) {
            error_log("Error de conexión: " . $exception->getMessage());
            die(json_encode([
                'success' => false,
                'message' => 'Error de conexión a la base de datos'
            ]));
        }
        return $this->conn;
    }
}
?>