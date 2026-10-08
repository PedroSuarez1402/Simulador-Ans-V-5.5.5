-- ==============================================================================
-- ESQUEMA SQL: SIMULADOR SAF LINK PLANNER (FASE 1)
-- Compatible con MySQL 5.7 / 8.0 (Laragon / MariaDB)
-- ==============================================================================

CREATE DATABASE IF NOT EXISTS `saf_link_planner` 
  CHARACTER SET utf8mb4 
  COLLATE utf8mb4_unicode_ci;

USE `saf_link_planner`;

-- ------------------------------------------------------------------------------
-- 1. TABLA: RADIOS
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `radios` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `manufacturer` VARCHAR(100) NOT NULL COMMENT 'Fabricante (ej. Mimosa, SAF, Cambium)',
    `model` VARCHAR(100) NOT NULL UNIQUE COMMENT 'Modelo del equipo',
    `frequency_min_ghz` DECIMAL(6, 3) NULL COMMENT 'Frecuencia mínima de operación en GHz',
    `frequency_max_ghz` DECIMAL(6, 3) NULL COMMENT 'Frecuencia máxima de operación en GHz',
    `max_output_power_dbm` DECIMAL(5, 2) NULL COMMENT 'Potencia de transmisión máxima TX (dBm)',
    `integrated_antenna_gain_dbi` DECIMAL(5, 2) DEFAULT 0.00 COMMENT 'Ganancia si tiene antena integrada (dBi)',
    `throughput_gbps` DECIMAL(6, 3) NULL COMMENT 'Capacidad máxima de throughput (Gbps)',
    `bandwidths_mhz` JSON NULL COMMENT 'Lista de anchos de canal soportados en MHz [20, 40, 80, 160]',
    `mimo` VARCHAR(50) NULL COMMENT 'Configuración MIMO (ej. 2x2, 4x4, SISO)',
    `modulation` VARCHAR(100) NULL COMMENT 'Esquemas de modulación soportados (ej. BPSK a 1024QAM)',
    `rx_sensitivity_dbm` JSON NULL COMMENT 'Mapeo de sensibilidades por canal en formato JSON',
    `source_file` VARCHAR(255) NULL COMMENT 'Nombre del PDF datasheet de origen',
    `notes` TEXT NULL COMMENT 'Notas y observaciones adicionales del equipo',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_radio_freq` (`frequency_min_ghz`, `frequency_max_ghz`),
    INDEX `idx_radio_mfg` (`manufacturer`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 2. TABLA: ANTENAS
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `antennas` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `manufacturer` VARCHAR(100) NOT NULL COMMENT 'Fabricante (ej. Mimosa, Jirous, AlgCom, CommScope)',
    `model` VARCHAR(100) NOT NULL UNIQUE COMMENT 'Modelo de antena',
    `gain_dbi` DECIMAL(5, 2) NOT NULL COMMENT 'Ganancia nominal o media (dBi)',
    `gain_low_dbi` DECIMAL(5, 2) NULL COMMENT 'Ganancia en banda baja (dBi)',
    `gain_mid_dbi` DECIMAL(5, 2) NULL COMMENT 'Ganancia en banda media (dBi)',
    `gain_high_dbi` DECIMAL(5, 2) NULL COMMENT 'Ganancia en banda alta (dBi)',
    `frequency_min_ghz` DECIMAL(6, 3) NULL COMMENT 'Rango frec mínimo (GHz)',
    `frequency_max_ghz` DECIMAL(6, 3) NULL COMMENT 'Rango frec máximo (GHz)',
    `beamwidth_deg` DECIMAL(5, 2) NULL COMMENT 'Ancho de haz a -3dB en grados',
    `polarization` VARCHAR(100) NULL COMMENT 'Polarización (ej. Dual-slant 45°, V/H, Circular)',
    `front_to_back_ratio_db` DECIMAL(5, 2) NULL COMMENT 'Relación Frente/Espalda F/B (dB)',
    `xpd_db` DECIMAL(5, 2) NULL COMMENT 'Discriminación de polarización cruzada XPD (dB)',
    `diameter_m` DECIMAL(5, 2) NULL COMMENT 'Diámetro de la parábola en metros',
    `weight_kg` DECIMAL(6, 2) NULL COMMENT 'Peso en kilogramos',
    `packed_weight_kg` DECIMAL(6, 2) NULL COMMENT 'Peso empacado (kg)',
    `wind_area_m2` DECIMAL(6, 3) NULL COMMENT 'Área de exposición al viento en m2',
    `operational_wind_kmh` DECIMAL(6, 2) NULL COMMENT 'Velocidad de viento operacional (km/h)',
    `survival_wind_kmh` DECIMAL(6, 2) NULL COMMENT 'Velocidad de viento de supervivencia (km/h)',
    `vswr` VARCHAR(50) NULL COMMENT 'Relación de onda estacionaria VSWR',
    `port_isolation_db` DECIMAL(5, 2) NULL COMMENT 'Aislamiento entre puertos (dB)',
    `connector` VARCHAR(100) NULL COMMENT 'Tipo de conector (ej. N-Female, SMA, Waveguide)',
    `shielding` VARCHAR(100) NULL COMMENT 'Blindaje / Radomo',
    `material` VARCHAR(100) NULL COMMENT 'Material de construcción',
    `mast_mount` VARCHAR(150) NULL COMMENT 'Diámetro de mástil soportado',
    `elevation_adjustment` VARCHAR(100) NULL COMMENT 'Rango de ajuste mecánico en elevación',
    `azimuth_adjustment` VARCHAR(100) NULL COMMENT 'Rango de ajuste mecánico en azimut',
    `polarization_adjustment` VARCHAR(100) NULL COMMENT 'Rango de ajuste en polarización',
    `dimension_a_mm` DECIMAL(7, 2) NULL,
    `dimension_b_mm` DECIMAL(7, 2) NULL,
    `dimension_c_mm` DECIMAL(7, 2) NULL,
    `source_file` VARCHAR(255) NULL,
    `notes` TEXT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_ant_freq` (`frequency_min_ghz`, `frequency_max_ghz`),
    INDEX `idx_ant_gain` (`gain_dbi`),
    INDEX `idx_ant_mfg` (`manufacturer`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 3. TABLA: PROYECTOS (Cabecera)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `projects` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(150) NOT NULL UNIQUE COMMENT 'Nombre único del proyecto',
    `description` TEXT NULL COMMENT 'Descripción u observaciones del enlace',
    `format` VARCHAR(50) DEFAULT 'SAF-Link-Planner-Project',
    `version` VARCHAR(20) DEFAULT 'V5.5.5',
    `elevation_provider` VARCHAR(100) DEFAULT 'Open-Meteo (Gratuito / Copernicus DEM)',
    `ee_project` VARCHAR(100) DEFAULT 'saf-link-planner',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_project_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 4. TABLA: SITIOS Y CONFIGURACIÓN DEL ENLACE
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `project_links` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `project_id` INT NOT NULL,
    `site_a_name` VARCHAR(100) NOT NULL DEFAULT 'Sitio A',
    `lat_a` DECIMAL(10, 6) NOT NULL,
    `lon_a` DECIMAL(10, 6) NOT NULL,
    `height_a_m` DECIMAL(6, 2) NOT NULL DEFAULT 20.00 COMMENT 'Altura antena sobre terreno Sitio A (m)',
    `site_b_name` VARCHAR(100) NOT NULL DEFAULT 'Sitio B',
    `lat_b` DECIMAL(10, 6) NOT NULL,
    `lon_b` DECIMAL(10, 6) NOT NULL,
    `height_b_m` DECIMAL(6, 2) NOT NULL DEFAULT 20.00 COMMENT 'Altura antena sobre terreno Sitio B (m)',
    `distance_km` DECIMAL(8, 3) NULL COMMENT 'Distancia geodésica calculada (km)',
    `azimuth_ab_deg` DECIMAL(6, 2) NULL COMMENT 'Azimut de A hacia B en grados',
    `azimuth_ba_deg` DECIMAL(6, 2) NULL COMMENT 'Azimut de B hacia A en grados',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 5. TABLA: CONFIGURACIÓN RF DEL PROYECTO
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `project_rf_settings` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `project_id` INT NOT NULL,
    `radio_a_id` INT NULL,
    `radio_b_id` INT NULL,
    `antenna_a_id` INT NULL,
    `antenna_b_id` INT NULL,
    `frequency_ghz` DECIMAL(6, 3) NOT NULL DEFAULT 5.800,
    `tx_power_dbm` DECIMAL(5, 2) NOT NULL DEFAULT 24.00,
    `channel_mhz` INT NOT NULL DEFAULT 80,
    `required_capacity_mbps` DECIMAL(8, 2) NOT NULL DEFAULT 500.00,
    `other_losses_db` DECIMAL(5, 2) NOT NULL DEFAULT 2.00,
    `k_factor` DECIMAL(4, 3) NOT NULL DEFAULT 1.333,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`radio_a_id`) REFERENCES `radios`(`id`) ON DELETE SET NULL,
    FOREIGN KEY (`radio_b_id`) REFERENCES `radios`(`id`) ON DELETE SET NULL,
    FOREIGN KEY (`antenna_a_id`) REFERENCES `antennas`(`id`) ON DELETE SET NULL,
    FOREIGN KEY (`antenna_b_id`) REFERENCES `antennas`(`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 6. TABLA: OBSTÁCULOS MANUALES
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `project_obstacles` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `project_id` INT NOT NULL,
    `dist_km` DECIMAL(8, 3) NOT NULL COMMENT 'Distancia desde Sitio A en km',
    `height_m` DECIMAL(6, 2) NOT NULL COMMENT 'Altura del obstáculo sobre el terreno en metros',
    `tipo` VARCHAR(50) DEFAULT 'Árbol' COMMENT 'Árbol, Edificio, Torre, Estructura, etc.',
    `nombre` VARCHAR(100) DEFAULT 'Obstáculo',
    `activo` TINYINT(1) DEFAULT 1 COMMENT '1 si está activo en el cálculo, 0 si está deshabilitado',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------------------------
-- 7. TABLA: PERFILES EN CACHÉ (Terreno, Vegetación y Cálculos)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `project_profiles` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `project_id` INT NOT NULL UNIQUE,
    `samples_count` INT NOT NULL DEFAULT 512,
    `profile_df_json` LONGTEXT NULL COMMENT 'Datos del perfil topográfico en JSON comprimible',
    `veg_df_json` LONGTEXT NULL COMMENT 'Datos del perfil de vegetación procesado en JSON',
    `exclusions_json` JSON NULL COMMENT 'Zonas de exclusión de vegetación aplicadas',
    `canopy_overrides_json` JSON NULL,
    `calculated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
