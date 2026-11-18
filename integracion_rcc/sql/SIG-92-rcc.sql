-- Ejecutar manualmente sobre la base de pruebas verificada por el operador.
-- Seguimiento simple: una marca por factura. No crea tablas nuevas.
BEGIN;
ALTER TABLE factura ADD COLUMN IF NOT EXISTS cargada_rcc BOOLEAN NOT NULL DEFAULT FALSE;
COMMIT;
