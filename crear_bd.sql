-- ============================================================
-- crear_bd.sql — CREACIÓN DE LA BASE DE DATOS POSTGRESQL
-- Proyecto: HardPoint PC (EVA-2 Desarrollo Backend)
-- Alumna: Genesis Quezada Sanzana — Sección IEC-C4-N2 — 2026
--
-- Qué hace: crea la base de datos "tienda_hardware_db" con
-- codificación UTF8 (obligatoria para tildes y ñ) y asegura que
-- el rol de conexión tenga el permiso CREATEDB, necesario para
-- que "manage.py test" pueda crear la base de datos de pruebas.
--
-- Cómo ejecutarlo en PowerShell (PostgreSQL 18 en el puerto 5433):
--   $env:PGPASSWORD = "1234"
--   & "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -h localhost -p 5433 -f crear_bd.sql
--
-- Es idempotente: si la base ya existe, no hace nada y no falla.
-- ============================================================

-- ============================================================
-- BLOQUE 1 — PERMISO CREATEDB PARA EL ROL
-- Django crea y destruye la base "test_tienda_hardware_db" al
-- ejecutar las pruebas; sin CREATEDB el comando test falla.
-- ============================================================
ALTER ROLE postgres CREATEDB;

-- ============================================================
-- BLOQUE 2 — CREACIÓN CONDICIONAL DE LA BASE DE DATOS
-- CREATE DATABASE no admite "IF NOT EXISTS", por lo que se
-- genera la sentencia solo cuando la base no existe y se
-- ejecuta con \gexec. TEMPLATE template0 es obligatorio para
-- poder fijar explícitamente la codificación UTF8.
-- ============================================================
SELECT 'CREATE DATABASE tienda_hardware_db ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'tienda_hardware_db')\gexec

-- ============================================================
-- BLOQUE 3 — VERIFICACIÓN
-- Muestra la base creada con su codificación para confirmar
-- que quedó en UTF8.
-- ============================================================
SELECT datname AS base_de_datos, pg_encoding_to_char(encoding) AS codificacion
FROM pg_database
WHERE datname = 'tienda_hardware_db';
