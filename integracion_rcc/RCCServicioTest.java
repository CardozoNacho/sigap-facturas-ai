package Services;
import org.json.*;

/** Pruebas de seleccion sin conexion a PostgreSQL ni datos reales. */
public class RCCServicioTest {
    static JSONObject f(String id,String comprobante,boolean marcada){
        return new JSONObject().put("factura_id",id).put("nfact","123456789012").put("comprobante",comprobante)
            .put("fecha","2026-06-18").put("importe","1234.5600").put("nexp","90001/26").put("folio","0062").put("marcada",marcada);
    }
    static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
    static void count(JSONObject summary,String key,int expected){check(summary.getInt(key)==expected,key+": "+summary.getInt(key)+" != "+expected);}
    public static void main(String[] args){
        JSONArray raw=new JSONArray().put(f("1","001",false)).put(f("2","",false)).put(f("3","abc",false))
            .put(f("4","004",true)).put(f("5","005",false).put("fecha","2026-02-30"))
            .put(f("6","006",false)).put(f("7","006",false)).put(f("8","008",false).put("importe","1.001"))
            .put(f("9","009",false).put("importe","0"));
        JSONObject result=RCCServicio.clasificar(raw,"2026"),s=result.getJSONObject("resumen");
        count(s,"total",9);count(s,"con_comprobante",7);count(s,"ya_cargadas",1);count(s,"sin_comprobante",1);
        count(s,"comprobante_invalido",1);count(s,"comprobantes_repetidos",2);count(s,"otros_errores",3);count(s,"disponibles",1);
        JSONObject eligible=result.getJSONArray("facturas").getJSONObject(0);
        check("001".equals(eligible.getString("comprobante")),"Perdio ceros iniciales");
        check("1234.56".equals(eligible.getString("importe")),"Importe sin precision exacta");
        check(!eligible.has("marcada"),"El contrato no debe permitir marcar desde el cliente");
        check("0062".equals(eligible.getString("folio")),"No conserva folio del expediente");
        check("1".equals(eligible.getString("factura_id")),"No debe sustituir el identificador interno por el folio");
        JSONObject map=RCCServicio.folios(new JSONArray().put(eligible).put(new JSONObject().put("factura_id","2")));
        check("0062".equals(map.getString("1")) && "".equals(map.getString("2")),"Mapa incorrecto o folio faltante inventado");
        count(RCCServicio.clasificar(new JSONArray(),null).getJSONObject("resumen"),"disponibles",0);
        count(RCCServicio.clasificar(new JSONArray().put(f("1","001",true)),null).getJSONObject("resumen"),"disponibles",0);
        boolean invalid=false;try{RCCServicio.anio("90001/26","2025");}catch(IllegalArgumentException e){invalid=true;}check(invalid,"Acepto anio diferente");
        JSONArray batch=new JSONArray().put(new JSONObject().put("factura_id","1")).put(new JSONObject().put("factura_id","2"));
        JSONObject outcomes=new JSONObject().put("1",new JSONObject().put("estado","revision"));
        check(RCCServicio.estadoFinal(batch,outcomes)==null,"Una revision no debe terminar un lote con facturas pendientes");
        outcomes.put("2",new JSONObject().put("estado","guardada"));
        check("completado_con_revision".equals(RCCServicio.estadoFinal(batch,outcomes)),"No identifico cierre con revision");
        outcomes.getJSONObject("1").put("estado","ya_existente");
        check("completado".equals(RCCServicio.estadoFinal(batch,outcomes)),"No identifico cierre exitoso");
        outcomes.getJSONObject("1").put("estado","incierto");
        check(RCCServicio.estadoFinal(batch,outcomes)==null,"No debe dar por completado un envio incierto");
        JSONObject saved=new JSONObject().put("estado","guardada").put("mensaje","Guardado confirmado").put("fila",new JSONArray().put("evidencia"));
        check(RCCServicio.resultadoMarcada(saved).similar(saved),"Al retomar no debe convertir una guardada en ya_existente ni perder evidencia");
        check("confirmada".equals(RCCServicio.resultadoMarcada(null).getString("estado")),"Una marca previa sin detalle no prueba que el comprobante preexistiera al envio");
        outcomes.getJSONObject("1").put("estado","confirmada");
        check("completado".equals(RCCServicio.estadoFinal(batch,outcomes)),"No reconoce una reconciliacion confirmada");
        JSONObject expected=new JSONObject().put("comprobante","00012345").put("fecha","2026-06-18").put("importe","1234.56").put("exp_numero","90001").put("exp_anio","2026");
        JSONArray visible=new JSONArray().put("").put("Reparticion").put("LIQ-SP-B").put("00018-00012345").put("E.N.E.R.S.A.").put("ACACNI").put("19-06-2026").put("1235.00").put("EX-90001/2026").put("Validado");
        JSONArray reasons=RCCServicio.diferencias(expected,visible);
        check(reasons.length()==2 && reasons.toString().contains("Fecha:") && reasons.toString().contains("Importe:"),"No detalla los campos que difieren");
        visible.put(6,"18-06-2026").put(7,"1234.56");
        check(RCCServicio.coincide(expected,visible),"La verificacion coincidente debe mantenerse");
        System.out.println("Seleccion RCC: comprobaciones aprobadas, sin acceso a base ni portal.");
    }
}
