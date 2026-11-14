"""
PASO 2 — Unir y limpiar los focos de calor MODIS y VIIRS.

Entrada : data/raw/modis/*.csv y data/raw/viirs/*.csv  (descargados en el paso 1)
Salida  : data/processed/focos_limpios.parquet

Qué hace:
  1. Lee todos los CSV de cada sensor con DuckDB (rápido, aunque sean millones de filas).
  2. Pone ambos sensores en las MISMAS columnas (MODIS y VIIRS traen nombres distintos).
  3. Filtra: solo fuegos de vegetación (type = 0) y con confianza aceptable.
  4. Quita filas duplicadas y guarda todo en Parquet.

Uso (desde fireseason/, con el entorno activado):
    python pipeline/02_limpiar.py
"""
import duckdb

import config

SALIDA = config.PROCESSED / "focos_limpios.parquet"

# Columnas comunes que tendrán ambos sensores:
#   lat, lon, fecha, hora, sensor, satelite, confianza, frp, dia_noche, version, type
SQL_MODIS = f"""
SELECT
    latitude                          AS lat,
    longitude                         AS lon,
    CAST(acq_date AS DATE)            AS fecha,
    lpad(CAST(acq_time AS VARCHAR), 4, '0') AS hora,
    'MODIS'                           AS sensor,
    CAST(satellite AS VARCHAR)        AS satelite,     -- Terra / Aqua
    CAST(confidence AS VARCHAR)       AS confianza,    -- 0..100
    frp,
    daynight                          AS dia_noche,
    CAST(version AS VARCHAR)          AS version,
    type
FROM read_csv('{config.RAW_MODIS.as_posix()}/*.csv', union_by_name = true)
WHERE type = {config.TIPO_VEGETACION}
  AND confidence >= {config.MODIS_CONFIANZA_MIN}
"""

confianzas_viirs = ", ".join(f"'{c}'" for c in sorted(config.VIIRS_CONFIANZA_OK))
SQL_VIIRS = f"""
SELECT
    latitude                          AS lat,
    longitude                         AS lon,
    CAST(acq_date AS DATE)            AS fecha,
    lpad(CAST(acq_time AS VARCHAR), 4, '0') AS hora,
    'VIIRS'                           AS sensor,
    CASE CAST(satellite AS VARCHAR)
        WHEN 'N' THEN 'S-NPP'
        WHEN '1' THEN 'NOAA-20'
        WHEN 'N20' THEN 'NOAA-20'
        WHEN '2' THEN 'NOAA-21'
        WHEN 'N21' THEN 'NOAA-21'
        ELSE CAST(satellite AS VARCHAR)
    END                               AS satelite,
    CAST(confidence AS VARCHAR)       AS confianza,    -- l / n / h
    frp,
    daynight                          AS dia_noche,
    CAST(version AS VARCHAR)          AS version,
    type
FROM read_csv('{config.RAW_VIIRS.as_posix()}/*.csv', union_by_name = true)
WHERE type = {config.TIPO_VEGETACION}
  AND confidence IN ({confianzas_viirs})
"""


def contar_crudos(con, carpeta):
    return con.execute(f"SELECT count(*) FROM read_csv('{carpeta.as_posix()}/*.csv', union_by_name = true)").fetchall()[0][0]


def main():
    config.PROCESSED.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    print("Contando focos crudos...")
    crudos_modis = contar_crudos(con, config.RAW_MODIS)
    crudos_viirs = contar_crudos(con, config.RAW_VIIRS)

    print("Limpiando y uniendo MODIS + VIIRS...")
    con.sql(f"""
        COPY (
            SELECT DISTINCT * FROM ({SQL_MODIS} UNION ALL {SQL_VIIRS})
            ORDER BY fecha, hora
        ) TO '{SALIDA.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)

    # ---- Resumen para revisar que todo tenga sentido ----
    focos = f"read_parquet('{SALIDA.as_posix()}')"
    limpios = dict(con.sql(f"SELECT sensor, count(*) FROM {focos} GROUP BY sensor").fetchall())

    print("\n=== RESUMEN ===")
    print(f"MODIS: {crudos_modis:>10,} crudos -> {limpios.get('MODIS', 0):>10,} limpios")
    print(f"VIIRS: {crudos_viirs:>10,} crudos -> {limpios.get('VIIRS', 0):>10,} limpios")
    print(f"Archivo: {SALIDA}  ({SALIDA.stat().st_size / 1e6:.1f} MB)\n")

    print("Focos limpios por año y sensor:")
    print(con.sql(f"""
        SELECT year(fecha) AS anio,
               count(*) FILTER (WHERE sensor = 'MODIS') AS modis,
               count(*) FILTER (WHERE sensor = 'VIIRS') AS viirs
        FROM {focos} GROUP BY anio ORDER BY anio
    """).df().to_string(index=False))

    print("\nVersiones de datos (NRT = preliminar, el resto = estándar):")
    print(con.sql(f"SELECT sensor, version, count(*) AS focos FROM {focos} GROUP BY ALL ORDER BY ALL").df().to_string(index=False))


if __name__ == "__main__":
    main()
