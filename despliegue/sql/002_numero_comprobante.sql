-- Aplicar antes de desplegar la entidad actualizada. Historicos permanecen NULL.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE factura ADD COLUMN IF NOT EXISTS numero_comprobante varchar(32);
COMMENT ON COLUMN factura.numero_comprobante IS 'Numero de comprobante ENERSA del encabezado CLASE B-18 Nro. Distinto de nfact; conserva ceros iniciales.';
COMMIT;
