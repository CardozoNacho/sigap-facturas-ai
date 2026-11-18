<%@ page language="java" contentType="text/html; charset=UTF-8" pageEncoding="UTF-8" %>
<%
if(session.getAttribute("rol")==null){response.sendRedirect("login.jsp");return;}
String rccCsrf=(String)session.getAttribute("rccCsrf");
if(rccCsrf==null){rccCsrf=java.util.UUID.randomUUID().toString();session.setAttribute("rccCsrf",rccCsrf);}
%>
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Facturas RCC - SIGAP</title>
<link href="styles.css" rel="stylesheet">
<link href="css/facturas-rcc.css?v=20261113-vista" rel="stylesheet">
</head>
<body class="rcc-page">
<%@ include file="navbar.jsp" %>
<main class="rcc" id="rcc" data-csrf="<%=rccCsrf%>">
<header class="rcc-header">
    <p class="rcc-eyebrow">SIGAP / FACTURACIÓN</p>
    <h1>Facturas RCC</h1>
    <p>Prepará las facturas de un expediente y seguí su carga en el portal municipal.</p>
</header>
<section class="rcc-panel" aria-labelledby="tituloAutomatizador">
    <div class="rcc-panel-heading"><span class="rcc-step" aria-hidden="true">1</span><div><h2 id="tituloAutomatizador">Conectar el automatizador</h2><p>Instalalo una sola vez en esta PC y mantené SIGAP RCC abierto durante la carga.</p></div></div>
    <div class="rcc-actions">
        <a class="rcc-button rcc-button-primary" href="FacturaRCCControler?accion=instalador"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/></svg>Descargar instalador <span class="rcc-version">0.2.0</span></a>
        <button id="detectarRcc" type="button">Detectar automatizador</button>
        <span class="rcc-connection" id="conexionRcc" data-estado="pendiente" role="status" aria-live="polite">Sin comprobar</span>
    </div>
    <details class="rcc-help"><summary>Cómo instalar y configurar</summary><ol><li>Descargá y descomprimí el paquete. Ejecutá <code>instalar.cmd</code>.</li><li>Abrí <strong>Configurar SIGAP RCC</strong> e ingresá la URL de esta instalación y tus credenciales del portal.</li><li>Abrí <strong>SIGAP RCC</strong> y usá Detectar automatizador en esta pantalla.</li></ol><p>Requiere Python 3.10 o posterior de 64 bits con Tcl/Tk e Internet. El instalador detecta una versión compatible.</p></details>
    <p class="rcc-note">Las credenciales se guardan cifradas en tu cuenta de Windows. Si el navegador solicita acceso local, permitilo para SIGAP.</p>
</section>
<div class="rcc-notice" id="mensajeRcc" role="status" aria-live="polite" hidden></div>
<section class="rcc-panel" aria-labelledby="tituloExpediente">
    <div class="rcc-panel-heading"><span class="rcc-step" aria-hidden="true">2</span><div><h2 id="tituloExpediente">Seleccionar un expediente</h2><p>Revisá las facturas disponibles antes de iniciar la carga.</p></div></div>
    <div class="rcc-fields">
        <div class="rcc-field"><label for="expedienteRcc">Expediente</label><select id="expedienteRcc"><option value="">Seleccione</option></select></div>
        <div class="rcc-field rcc-field-year"><label for="anioRcc">Año completo</label><input id="anioRcc" type="text" inputmode="numeric" maxlength="4" placeholder="2026" aria-describedby="ayudaAnioRcc"><small id="ayudaAnioRcc">Ingresá los cuatro dígitos.</small></div>
    </div>
    <div class="rcc-summary" id="resumenDisponiblesRcc" aria-live="polite">Seleccioná un expediente para consultar las facturas disponibles.</div>
    <div class="rcc-actions"><button id="revisarRcc" type="button">Revisar expediente</button><button class="rcc-button-primary" id="iniciarRcc" type="button" disabled>Cargar en RCC</button></div>
    <p class="rcc-note">Se enviarán solo las facturas con comprobante, fecha e importe válidos que todavía no estén marcadas como cargadas.</p>
    <div class="rcc-table-wrap" tabindex="0" role="region" aria-label="Facturas disponibles"><table><thead><tr><th>Folio</th><th>Factura</th><th>Comprobante</th><th>Fecha</th><th>Importe</th><th>Expediente</th></tr></thead><tbody id="filasRcc"></tbody></table></div>
</section>
<section class="rcc-panel" aria-labelledby="tituloSeguimiento">
    <div class="rcc-panel-heading rcc-heading-actions"><span class="rcc-step" aria-hidden="true">3</span><div><h2 id="tituloSeguimiento">Seguimiento de cargas</h2><p>Consultá el resultado de cada factura y los motivos que requieren revisión.</p></div><button id="actualizarRcc" type="button">Actualizar</button></div>
    <div id="trabajosRcc"></div>
    <details class="rcc-help"><summary>Sobre revisiones y cargas interrumpidas</summary><p>Las facturas con diferencias quedan en revisión y la carga continúa con las siguientes. Después de corregirlas, seleccioná nuevamente el expediente para cargar sus pendientes.</p><p>Reanudar retoma una carga interrumpida. Cerrar trabajo no borra ni anula comprobantes del portal. La marca de cada factura conserva lo ya comprobado en RCC.</p></details>
</section>
</main>
<script src="js/facturas-rcc.js?v=20261113-folios"></script>
</body></html>
