package vista;

import Services.RCCServicio;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.zip.*;
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.*;
import org.json.*;

@WebServlet("/FacturaRCCControler")
public class FacturaRCCControler extends HttpServlet {
    private static final long serialVersionUID=1L;
    private void json(HttpServletResponse r,int code,JSONObject data)throws IOException {
        r.setStatus(code);r.setContentType("application/json");r.setCharacterEncoding("UTF-8");r.setHeader("Cache-Control","no-store");r.getWriter().write(data.toString());
    }
    private boolean session(HttpServletRequest q,HttpServletResponse r)throws IOException {
        if(q.getSession(false)==null || q.getSession(false).getAttribute("rol")==null || !(q.getSession(false).getAttribute("usuarioLogueado") instanceof modelo.Usuario)) {
            json(r,401,new JSONObject().put("error","Inicie sesion en SIGAP."));return false;
        }return true;
    }
    private void habilitado() { if(!Boolean.getBoolean("sigap.rcc.habilitado"))throw new IllegalStateException("RCC no esta habilitado en esta instancia. Verifique migracion y base antes de habilitarlo."); }
    @Override protected void doGet(HttpServletRequest q,HttpServletResponse r)throws IOException {
        if(!session(q,r))return;
        try {
            if("instalador".equals(q.getParameter("accion"))) { instalador(r);return; }
            habilitado();json(r,200,RCCServicio.listar());
        } catch(Exception e) { error(r,e); }
    }
    @Override protected void doPost(HttpServletRequest q,HttpServletResponse r)throws IOException {
        q.setCharacterEncoding("UTF-8");
        try {
            habilitado();String action=q.getParameter("accion");
            if("tomar".equals(action) || "resultado".equals(action)) {
                String auth=q.getHeader("Authorization");
                StringBuilder raw=new StringBuilder();char[] b=new char[1024];int n;
                try(Reader reader=q.getReader()){while((n=reader.read(b))!=-1){raw.append(b,0,n);if(raw.length()>16384)throw new IllegalArgumentException();}}
                json(r,200,RCCServicio.ejecutar(q.getHeader("X-RCC-Job"),auth!=null && auth.startsWith("Bearer ")?auth.substring(7):null,action,new JSONObject(raw.toString())));return;
            }
            if(!session(q,r))return;
            String csrf=(String)q.getSession(false).getAttribute("rccCsrf"),provided=q.getParameter("csrf");
            if(csrf==null || provided==null || !MessageDigest.isEqual(csrf.getBytes(StandardCharsets.UTF_8),provided.getBytes(StandardCharsets.UTF_8))) {json(r,403,new JSONObject().put("error","Formulario vencido. Recargue la vista."));return;}
            String user=((modelo.Usuario)q.getSession(false).getAttribute("usuarioLogueado")).getNombre_usuario();
            JSONObject data;
            if("disponibles".equals(action))data=RCCServicio.disponibles(q.getParameter("nexp"));
            else if("revisar".equals(action))data=RCCServicio.revisar(q.getParameter("nexp"),q.getParameter("anio"));
            else if("crear".equals(action))data=RCCServicio.crear(q.getParameter("nexp"),q.getParameter("anio"),user);
            else if("reanudar".equals(action) || "cerrar".equals(action))data=RCCServicio.renovar(q.getParameter("id"),user,"cerrar".equals(action));
            else throw new IllegalArgumentException("Operacion desconocida.");
            json(r,200,data);
        } catch(Exception e) { error(r,e); }
    }
    private void error(HttpServletResponse r,Exception e)throws IOException {
        if(e instanceof SecurityException)json(r,401,new JSONObject().put("error","Credencial de trabajo invalida o vencida."));
        else if(e instanceof IllegalStateException)json(r,409,new JSONObject().put("error",e.getMessage()));
        else if(e instanceof IllegalArgumentException || e instanceof JSONException)json(r,400,new JSONObject().put("error",e.getMessage()==null?"Parametros invalidos.":e.getMessage()));
        else {log("Operacion RCC no completada: "+e.getClass().getSimpleName());json(r,503,new JSONObject().put("error","No se pudo completar RCC. Revise base permitida, migracion y registro del servidor."));}
    }
    private void instalador(HttpServletResponse r)throws IOException {
        String[] files={"instalar.cmd","instalar.ps1","iniciar.cmd","configurar.cmd","configurar.py","rcc_bridge.py","rcc_browser.py","rcc_contract.py","rcc_vault.py","requirements.txt","README.md"};
        for(String file:files)try(InputStream in=getServletContext().getResourceAsStream("/WEB-INF/rcc/"+file)){if(in==null){json(r,503,new JSONObject().put("error","El WAR no contiene el paquete RCC completo."));return;}}
        r.setContentType("application/zip");r.setHeader("Cache-Control","no-store");r.setHeader("Content-Disposition","attachment; filename=\"SIGAP-RCC-0.2.0.zip\"");
        try(ZipOutputStream zip=new ZipOutputStream(r.getOutputStream())) {
            byte[] buf=new byte[8192];
            for(String file:files){zip.putNextEntry(new ZipEntry("SIGAP-RCC/"+file));try(InputStream in=getServletContext().getResourceAsStream("/WEB-INF/rcc/"+file)){int n;while((n=in.read(buf))!=-1)zip.write(buf,0,n);}zip.closeEntry();}
        }
    }
}
