-- Ejecutar primero en la base de pruebas de SIGAP, antes de habilitar altas IA.
-- Columna nullable: las facturas anteriores conservan NULL.
BEGIN;
ALTER TABLE factura ADD COLUMN IF NOT EXISTS documento_pdf bytea;
COMMENT ON COLUMN factura.documento_pdf IS 'PDF de dos paginas: frente y dorso originales de la factura. Se consulta bajo demanda.';
COMMIT;
