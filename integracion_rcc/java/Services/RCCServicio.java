package Services;

import java.sql.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import javax.persistence.EntityManager;
import modelo.PersistenceManager;
import org.hibernate.Session;
import org.json.*;

/** Persistencia simple: solo factura.cargada_rcc. Los trabajos son temporales. */
public final class RCCServicio {
    private RCCServicio() {}
    interface SQL<T> { T run(Connection c) throws Exception; }
    private static final Map<String,Trabajo> trabajos=new LinkedHashMap<>();
    private static final class Trabajo {
        String id,tokenHash,usuario,nexp,base,estado="abierto";
        JSONArray facturas;
        JSONObject resultados=new JSONObject();
        long creado=System.currentTimeMillis(),actualizado=creado,expira=creado+8*3600000L;
    }
    static <T> T db(boolean write,SQL<T> action)throws Exception {
        EntityManager em=PersistenceManager.createEntityManager();
        try {
            return em.unwrap(Session.class).doReturningWork(c -> {
                try {
                    String expected=System.getProperty("sigap.rcc.basePermitida","");
                    try(Statement s=c.createStatement();ResultSet r=s.executeQuery("select current_database()")) {
                        r.next();if(expected.isEmpty() || !expected.equals(r.getString(1)))throw new IllegalStateException("Configure sigap.rcc.basePermitida con la base efectiva autorizada.");
                    }
                    if(write)em.getTransaction().begin();
                    T result=action.run(c);
                    if(write)em.getTransaction().commit();return result;
                }catch(Exception e){
                    if(em.getTransaction().isActive())em.getTransaction().rollback();
                    if(e instanceof SecurityException)throw (SecurityException)e;
                    if(e instanceof IllegalStateException)throw (IllegalStateException)e;
                    if(e instanceof IllegalArgumentException)throw (IllegalArgumentException)e;
                    throw new SQLException("No se pudo completar RCC. Revise base y migracion.",e);
                }
            });
        }finally{em.close();}
    }
    static String hash(String value)throws Exception {
        byte[] b=MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder out=new StringBuilder();for(byte v:b)out.append(String.format("%02x",v&255));return out.toString();
    }
    static String token(){byte[] b=new byte[32];new SecureRandom().nextBytes(b);StringBuilder s=new StringBuilder();for(byte v:b)s.append(String.format("%02x",v&255));return s.toString();}
    static String base(Connection c)throws Exception {
        try(Statement s=c.createStatement();ResultSet r=s.executeQuery("select current_database(),current_schema(),coalesce(cast(inet_server_addr() as text),'local'),inet_server_port()")){
            r.next();return hash(r.getString(1)+"|"+r.getString(2)+"|"+r.getString(3)+"|"+r.getString(4));
        }
    }
    static void validarExp(String exp){if(exp==null || exp.trim().isEmpty() || exp.length()>15 || exp.matches("(?s).*\\p{Cntrl}.*"))throw new IllegalArgumentException("Seleccione un expediente.");}
    static String anio(String exp,String year){
        validarExp(exp);
        if(!exp.matches("[0-9]+/([0-9]{2}|[0-9]{4})") || year==null || !year.matches("(19|20|21)[0-9]{2}") || !year.endsWith(exp.split("/")[1]))throw new IllegalArgumentException("Indique expediente exacto y anio completo coincidente.");
        return year;
    }
    static JSONArray leer(Connection c,String exp,Integer id,boolean bloquear)throws SQLException {
        JSONArray out=new JSONArray();
        String sql="select id,nfact,numero_comprobante,fechas,importepvenc,nexp,coalesce(cargada_rcc,false),folio from factura where "+(id==null?"nexp=?":"id=?")+" order by id"+(bloquear?" for update":"");
        try(PreparedStatement s=c.prepareStatement(sql)){
            if(id==null)s.setString(1,exp);else s.setInt(1,id);
            try(ResultSet r=s.executeQuery()){while(r.next())out.put(new JSONObject().put("factura_id",String.valueOf(r.getInt(1)))
                .put("nfact",r.getString(2)==null?"":r.getString(2)).put("comprobante",r.getString(3)==null?"":r.getString(3).trim())
                .put("fecha",r.getString(4)==null?"":r.getString(4)).put("importe",r.getBigDecimal(5)==null?"":r.getBigDecimal(5).toPlainString())
                .put("nexp",r.getString(6)==null?"":r.getString(6)).put("marcada",r.getBoolean(7))
                .put("folio",r.getString(8)==null?"":r.getString(8).trim()));}
        }return out;
    }
    static JSONObject normalizar(JSONObject row,String year){
        if(!row.getString("nexp").matches("[0-9]+/([0-9]{2}|[0-9]{4})"))throw new IllegalArgumentException("Expediente invalido");
        String numero=row.getString("comprobante");
        if(!numero.matches("[0-9]{1,32}"))throw new IllegalArgumentException("Comprobante invalido");
        LocalDate.parse(row.getString("fecha"));BigDecimal amount=new BigDecimal(row.getString("importe"));
        if(amount.signum()<=0 || amount.stripTrailingZeros().scale()>2)throw new IllegalArgumentException("Importe invalido");
        JSONObject f=new JSONObject(row.toString());f.remove("marcada");
        f.put("importe",amount.setScale(2).toPlainString()).put("exp_numero",row.getString("nexp").split("/")[0]).put("exp_anio",year==null?"":year);return f;
    }
    /** Los grupos excluidos son disjuntos; nunca etiqueta como disponible algo que no pueda enviar. */
    static JSONObject clasificar(JSONArray raw,String year){
        int con=0,ya=0,sin=0,invalidas=0,otros=0,duplicadas=0;
        JSONArray rows=new JSONArray();Map<String,Integer> frequency=new HashMap<>();
        for(int i=0;i<raw.length();i++){String n=raw.getJSONObject(i).getString("comprobante");if(n.matches("[0-9]{1,32}"))frequency.put(n,frequency.getOrDefault(n,0)+1);}
        for(int i=0;i<raw.length();i++){
            JSONObject r=raw.getJSONObject(i);String n=r.getString("comprobante");boolean valid=n.matches("[0-9]{1,32}");if(valid)con++;
            if(r.getBoolean("marcada")){ya++;continue;}
            if(n.isEmpty()){sin++;continue;}
            if(!valid){invalidas++;continue;}
            if(frequency.get(n)>1){duplicadas++;continue;}
            try{rows.put(normalizar(r,year));}catch(RuntimeException e){otros++;}
        }
        return new JSONObject().put("facturas",rows).put("resumen",new JSONObject().put("total",raw.length()).put("con_comprobante",con)
            .put("ya_cargadas",ya).put("sin_comprobante",sin).put("comprobante_invalido",invalidas).put("otros_errores",otros)
            .put("comprobantes_repetidos",duplicadas).put("disponibles",rows.length()));
    }
    public static JSONObject disponibles(String exp)throws Exception {
        validarExp(exp);return db(false,c -> clasificar(leer(c,exp,null,false),null));
    }
    public static JSONObject revisar(String exp,String year)throws Exception {
        anio(exp,year);return db(false,c -> {JSONObject out=clasificar(leer(c,exp,null,false),year);return out.put("habilitado",out.getJSONArray("facturas").length()>0);});
    }
    private static void limpiar(){
        long now=System.currentTimeMillis();
        for(Trabajo j:trabajos.values())if(j.expira<now)j.estado="cerrado";
        Iterator<Trabajo> it=trabajos.values().iterator();while(trabajos.size()>30 && it.hasNext()){Trabajo j=it.next();if(!Arrays.asList("abierto","ejecutando").contains(j.estado))it.remove();}
    }
    public static synchronized JSONObject listar()throws Exception {
        limpiar();return db(false,c -> {
            JSONArray exp=new JSONArray(),jobs=new JSONArray();String identity=base(c);
            try(Statement s=c.createStatement();ResultSet r=s.executeQuery("select nexp,count(*),count(*) filter (where btrim(numero_comprobante) ~ '^[0-9]{1,32}$') from factura where nexp is not null group by nexp having count(*) filter (where btrim(numero_comprobante) ~ '^[0-9]{1,32}$') > 0 order by max(id) desc limit 2000")){
                while(r.next())exp.put(new JSONObject().put("nexp",r.getString(1)).put("cantidad",r.getInt(2)).put("con_comprobante",r.getInt(3)));
            }
            for(Trabajo j:trabajos.values())if(identity.equals(j.base))jobs.put(new JSONObject().put("id",j.id).put("nexp",j.nexp).put("usuario",j.usuario).put("estado",j.estado)
                .put("resultados",new JSONObject(j.resultados.toString())).put("folios",folios(j.facturas)).put("creado",java.time.Instant.ofEpochMilli(j.creado).toString()));
            return new JSONObject().put("expedientes",exp).put("trabajos",jobs).put("version","0.2.0");
        });
    }
    public static synchronized JSONObject crear(String exp,String year,String usuario)throws Exception {
        anio(exp,year);limpiar();return db(false,c -> {
            String identity=base(c);
            for(Trabajo old:trabajos.values())if(identity.equals(old.base) && Arrays.asList("abierto","ejecutando").contains(old.estado))throw new IllegalStateException("Hay una carga abierta en esta instancia. Reanude o cierrela primero.");
            JSONArray rows=clasificar(leer(c,exp,null,false),year).getJSONArray("facturas");
            if(rows.length()==0)throw new IllegalStateException("No hay facturas disponibles con comprobante valido y pendientes de RCC.");
            if(rows.length()>2000)throw new IllegalStateException("La carga supera 2000 facturas.");
            Trabajo j=new Trabajo();j.id=UUID.randomUUID().toString().replace("-","");String secret=token();j.tokenHash=hash(secret);j.usuario=usuario;j.nexp=exp;j.base=identity;j.facturas=rows;
            // Conservar incertidumbre mientras vive esta instancia. Tras reiniciar se consulta RCC desde cero.
            for(Trabajo old:trabajos.values())if(identity.equals(old.base))for(int i=0;i<rows.length();i++){
                String key=rows.getJSONObject(i).getString("factura_id");JSONObject previous=old.resultados.optJSONObject(key);
                if(previous!=null){if(Arrays.asList("incierto","en_curso").contains(previous.optString("estado")))j.resultados.put(key,new JSONObject().put("estado","incierto"));else j.resultados.remove(key);}
            }
            trabajos.put(j.id,j);return new JSONObject().put("id",j.id).put("token",secret);
        });
    }
    public static synchronized JSONObject renovar(String id,String usuario,boolean cerrar)throws Exception {
        Trabajo j=trabajos.get(id);
        if(j==null || !j.usuario.equals(usuario))throw new IllegalArgumentException("Carga inexistente. Si Tomcat se reinicio, vuelva a seleccionar el expediente.");
        db(false,c -> {if(!base(c).equals(j.base))throw new SecurityException();return true;});
        if(!Arrays.asList("abierto","ejecutando").contains(j.estado))throw new IllegalStateException("La carga termino o vencio. Vuelva a seleccionar el expediente.");
        if("ejecutando".equals(j.estado) && j.actualizado>System.currentTimeMillis()-600000)throw new IllegalStateException("El ejecutor tiene una reserva activa. Espere diez minutos sin actividad antes de recuperarla.");
        String secret=token();j.tokenHash=hash(secret);j.estado=cerrar?"cerrado":"abierto";j.actualizado=System.currentTimeMillis();j.expira=j.actualizado+8*3600000L;
        return new JSONObject().put("id",id).put("token",cerrar?"":secret);
    }
    public static synchronized JSONObject ejecutar(String id,String secret,String action,JSONObject input)throws Exception {
        Trabajo j=trabajos.get(id);
        if(j==null || secret==null || !secret.matches("[a-f0-9]{64}") || j.expira<System.currentTimeMillis()
            || !MessageDigest.isEqual(hash(secret).getBytes(StandardCharsets.US_ASCII),j.tokenHash.getBytes(StandardCharsets.US_ASCII)))throw new SecurityException();
        if(!Arrays.asList("abierto","ejecutando").contains(j.estado))throw new IllegalStateException("Carga cerrada.");
        if("tomar".equals(action)){
            if("ejecutando".equals(j.estado))throw new IllegalStateException("Carga ya reservada.");
            db(false,c -> {
                if(!base(c).equals(j.base))throw new SecurityException();
                for(int i=0;i<j.facturas.length();i++){
                    JSONObject expected=j.facturas.getJSONObject(i),current=actual(c,expected,false);
                    if(current.getBoolean("marcada")){String key=expected.getString("factura_id");j.resultados.put(key,resultadoMarcada(j.resultados.optJSONObject(key)));}
                }return true;
            });
            for(String key:j.resultados.keySet())if("en_curso".equals(j.resultados.getJSONObject(key).optString("estado")))j.resultados.getJSONObject(key).put("estado","incierto");
            String fin=estadoFinal(j.facturas,j.resultados);j.estado=fin==null?"ejecutando":fin;j.actualizado=System.currentTimeMillis();
            return new JSONObject().put("facturas",new JSONArray(j.facturas.toString())).put("resultados",new JSONObject(j.resultados.toString()));
        }
        if(!"resultado".equals(action) || !"ejecutando".equals(j.estado))throw new IllegalArgumentException();
        String key=input.getString("factura_id"),next=input.getString("estado");JSONObject f=null;
        for(int i=0;i<j.facturas.length();i++)if(key.equals(j.facturas.getJSONObject(i).getString("factura_id")))f=j.facturas.getJSONObject(i);
        if(f==null || !Arrays.asList("en_curso","incierto","revision","guardada","ya_existente","confirmada").contains(next))throw new IllegalArgumentException();
        JSONObject old=j.resultados.optJSONObject(key);String prior=old==null?"preparada":old.optString("estado");
        if(Arrays.asList("guardada","ya_existente","confirmada").contains(prior)){if(!prior.equals(next))throw new IllegalStateException("Resultado ya confirmado.");return new JSONObject().put("ok",true);}
        if("guardada".equals(next) && !"en_curso".equals(prior))throw new IllegalStateException("Falta inicio del envio.");
        if("confirmada".equals(next) && !Arrays.asList("en_curso","incierto").contains(prior))throw new IllegalStateException("Falta un envio anterior para reconciliar.");
        JSONArray fila=input.optJSONArray("fila");if(fila==null)fila=new JSONArray();if(fila.length()>10 || fila.toString().length()>4000)throw new IllegalArgumentException();
        String mensaje=input.optString("mensaje","");
        String codigo=input.optString("codigo","");
        if(!codigo.matches("[a-z_]{0,40}"))throw new IllegalArgumentException();
        String etapa=input.optString("etapa","");if(etapa.length()>160)etapa=etapa.substring(0,160);
        JSONArray motivos=new JSONArray();
        if(Arrays.asList("guardada","ya_existente","confirmada").contains(next) || ("revision".equals(next) && fila.length()>0)) {
            motivos=diferencias(f,fila);
            if(motivos.length()>0){next="revision";codigo="diferencias_datos";StringBuilder detalle=new StringBuilder();for(int i=0;i<motivos.length();i++)detalle.append(motivos.getString(i)).append(" ");mensaje=detalle.toString().trim();}
        }
        if("revision".equals(next) && mensaje.trim().isEmpty()) {
            mensaje="El automatizador no informo el motivo de revision. Actualice el programa y revise el acceso o formulario del portal antes de reintentar.";
            codigo="revision_sin_detalle";
        }
        if(mensaje.length()>2000)mensaje=mensaje.substring(0,2000);
        final JSONObject expected=f;final boolean marcar=Arrays.asList("guardada","ya_existente","confirmada").contains(next);
        db(marcar,c -> {
            if(!base(c).equals(j.base))throw new SecurityException();actual(c,expected,marcar);
            if(marcar)try(PreparedStatement s=c.prepareStatement("update factura set cargada_rcc=true where id=?")){s.setInt(1,Integer.parseInt(expected.getString("factura_id")));if(s.executeUpdate()!=1)throw new IllegalStateException("La factura no existe.");}
            return true;
        });
        j.resultados.put(key,new JSONObject().put("estado",next).put("fila",fila).put("mensaje",mensaje).put("codigo",codigo).put("etapa",etapa).put("motivos",motivos).put("fecha",java.time.Instant.now().toString()));
        String fin=estadoFinal(j.facturas,j.resultados);
        j.estado=fin!=null?fin:"incierto".equals(next)?"abierto":"ejecutando";j.actualizado=System.currentTimeMillis();return new JSONObject().put("ok",true);
    }
    static JSONObject actual(Connection c,JSONObject expected,boolean lock)throws Exception {
        JSONArray raw=leer(c,null,Integer.parseInt(expected.getString("factura_id")),lock);
        if(raw.length()!=1 || !normalizar(raw.getJSONObject(0),expected.getString("exp_anio")).similar(expected))throw new IllegalStateException("Los datos de la factura cambiaron. Cierre y prepare nuevamente la carga.");return raw.getJSONObject(0);
    }
    static String estadoFinal(JSONArray facturas,JSONObject resultados){
        boolean revision=false;
        for(int i=0;i<facturas.length();i++){
            JSONObject r=resultados.optJSONObject(facturas.getJSONObject(i).getString("factura_id"));
            if(r==null)return null;String estado=r.optString("estado");
            if(!Arrays.asList("guardada","ya_existente","confirmada","revision").contains(estado))return null;
            if("revision".equals(estado))revision=true;
        }
        return revision?"completado_con_revision":"completado";
    }
    static JSONObject folios(JSONArray facturas){
        JSONObject out=new JSONObject();
        for(int i=0;i<facturas.length();i++){JSONObject f=facturas.getJSONObject(i);out.put(f.getString("factura_id"),f.optString("folio","").trim());}
        return out;
    }
    static JSONObject resultadoMarcada(JSONObject previo){
        if(previo!=null && Arrays.asList("guardada","ya_existente","confirmada").contains(previo.optString("estado")))return new JSONObject(previo.toString());
        return new JSONObject().put("estado","confirmada").put("codigo","marca_sigap")
            .put("mensaje","SIGAP ya tiene esta factura marcada como cargada en RCC. No se realizo otro envio ni una nueva consulta al portal al retomar.");
    }
    static JSONArray diferencias(JSONObject f,JSONArray cells){
        JSONArray errors=new JSONArray();
        if(cells.length()!=10)return errors.put("RCC no devolvio una fila completa para verificar los datos.");
        String[][] fields={{"2","Tipo","LIQ-SP-B"},{"3","Comprobante","00018-"+f.getString("comprobante")},
            {"4","Proveedor","E.N.E.R.S.A."},{"6","Fecha",LocalDate.parse(f.getString("fecha")).format(java.time.format.DateTimeFormatter.ofPattern("dd-MM-yyyy"))},
            {"8","Expediente","EX-"+f.getString("exp_numero")+"/"+f.getString("exp_anio")},{"9","Estado","Validado"}};
        for(String[] field:fields){String actual=cells.optString(Integer.parseInt(field[0]),"").trim();if(!field[2].equals(actual))errors.put(field[1]+": SIGAP esperado "+field[2]+"; RCC "+actual+".");}
        String actualAmount=cells.optString(7,"").trim();boolean sameAmount;
        try{sameAmount=new BigDecimal(f.getString("importe")).compareTo(new BigDecimal(actualAmount))==0;}catch(Exception e){sameAmount=false;}
        if(!sameAmount)errors.put("Importe: SIGAP "+f.getString("importe")+"; RCC "+actualAmount+".");
        return errors;
    }
    static boolean coincide(JSONObject f,JSONArray cells){
        try{return diferencias(f,cells).length()==0;}catch(Exception e){return false;}
    }
}
