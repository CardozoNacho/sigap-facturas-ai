(function(){
    'use strict';
    var root=document.getElementById('rcc'), exp=document.getElementById('expedienteRcc'), year=document.getElementById('anioRcc'), iniciar=document.getElementById('iniciarRcc');
    var connected=false,busy=false,reviewed='',availableSignature='',summarySequence=0;
    function message(s){var notice=document.getElementById('mensajeRcc');notice.textContent=s;notice.hidden=!s;}
    function key(){return exp.value+'|'+year.value;}
    function invalidate(){reviewed='';iniciar.disabled=true;document.getElementById('filasRcc').textContent='';}
    async function api(action,params){
        var opt=params?{method:'POST',body:new URLSearchParams(Object.assign({csrf:root.dataset.csrf},params))}:{};
        var res=await fetch('FacturaRCCControler?accion='+action,opt), data=await res.json();
        if(!res.ok)throw new Error(data.error || 'No se pudo completar la operacion');return data;
    }
    async function local(path,data){
        var opt={signal:AbortSignal.timeout(5000)};
        if(data){opt.method='POST';opt.headers={'Content-Type':'application/json','X-Sigap-RCC':'1'};opt.body=JSON.stringify(data);}
        var res=await fetch('http://127.0.0.1:8766/'+path,opt), body=await res.json();
        if(!res.ok)throw new Error(body.error || 'El automatizador no responde');return body;
    }
    async function detectar(){
        var indicator=document.getElementById('conexionRcc');
        try{var s=await local('estado');connected=s.version==='0.2.0';indicator.textContent=connected?(s.ocupado?'Conectado, ocupado':'Conectado'):'Actualice el automatizador con el paquete de esta pantalla';indicator.dataset.estado=connected?(s.ocupado?'ocupado':'conectado'):'desconectado';if(s.mensaje)message(s.mensaje);}
        catch(e){connected=false;indicator.textContent='No detectado: abra SIGAP RCC o revise el permiso de acceso local del navegador';indicator.dataset.estado='desconectado';}
        iniciar.disabled=busy || !connected || reviewed!==key();
    }
    function cell(tr,value){var td=document.createElement('td');td.textContent=value;tr.appendChild(td);}
    function estadoResultado(r){
        if(r.estado==='revision' && r.codigo==='sesion_rcc')return 'Revisar acceso / sesion RCC';
        if(r.estado==='revision' && r.codigo==='diferencias_datos')return 'Revisar diferencias de datos';
        if(r.estado==='confirmada' && r.codigo==='marca_sigap')return 'Marcada previamente en SIGAP';
        return {guardada:'Guardada en esta carga',ya_existente:'Ya existia antes del envio',confirmada:'Confirmada tras verificar el envio',revision:'Requiere revision',incierto:'Envio pendiente de verificar',en_curso:'Enviando'}[r.estado] || r.estado;
    }
    function detalleResultado(r){
        var text=r.mensaje || (r.motivos || []).join(' ');
        if(!text && r.estado==='revision')text='Este resultado no contiene un motivo detallado. Puede corresponder a una version anterior del automatizador; revise la factura antes de repetirla.';
        if(!text && r.estado==='incierto')text='No se pudo confirmar el envio. Debe consultarse RCC antes de volver a guardar.';
        if(r.etapa)text+=(text?'\n':'')+'Momento: '+r.etapa+'.';
        return text;
    }
    function folioVisible(value){return value===null || value===undefined || String(value).trim()===''?'Sin folio':String(value);}
    function signature(rows){return JSON.stringify(rows.map(function(f){return [f.factura_id,f.folio,f.nfact,f.comprobante,f.fecha,f.importe,f.nexp];}));}
    function renderRows(rows){var body=document.getElementById('filasRcc');body.textContent='';rows.forEach(function(f){var tr=document.createElement('tr');cell(tr,folioVisible(f.folio));['nfact','comprobante','fecha','importe','nexp'].forEach(function(k){cell(tr,f[k]);});body.appendChild(tr);});}
    function renderSummary(s){
        var entries=[['Total del expediente',s.total],['Con comprobante valido',s.con_comprobante],['Disponibles para cargar',s.disponibles,'available'],['Ya marcadas en RCC',s.ya_cargadas],['Sin comprobante',s.sin_comprobante]];
        if(s.comprobante_invalido)entries.push(['Comprobante invalido',s.comprobante_invalido]);
        if(s.comprobantes_repetidos)entries.push(['Comprobante repetido',s.comprobantes_repetidos]);
        if(s.otros_errores)entries.push(['Revisar fecha o importe',s.otros_errores]);
        var summary=document.getElementById('resumenDisponiblesRcc');summary.textContent='';
        entries.forEach(function(entry){var item=document.createElement('div'),label=document.createElement('span'),number=document.createElement('strong');item.className='rcc-metric'+(entry[2]?' rcc-metric--'+entry[2]:'');label.className='rcc-metric-label';label.textContent=entry[0]+': ';number.className='rcc-metric-value';number.textContent=entry[1];item.appendChild(label);item.appendChild(number);summary.appendChild(item);});
    }
    async function disponibles(){
        var selected=exp.value,seq=++summarySequence;
        if(!selected){document.getElementById('resumenDisponiblesRcc').textContent='Seleccione un expediente para consultar las facturas disponibles.';availableSignature='';return;}
        try{var data=await api('disponibles',{nexp:selected});if(seq!==summarySequence || selected!==exp.value)return;
            var latest=signature(data.facturas);if(latest!==availableSignature){invalidate();availableSignature=latest;renderRows(data.facturas);}
            renderSummary(data.resumen);
        }catch(e){if(seq!==summarySequence || selected!==exp.value)return;invalidate();availableSignature='';document.getElementById('resumenDisponiblesRcc').textContent=e.message;}
    }
    async function revisar(){
        if(busy)return;invalidate();busy=true;message('Verificando facturas disponibles en SIGAP...');
        try{var requested=key(), data=await api('revisar',{nexp:exp.value,anio:year.value});
            if(requested!==key())return;
            renderRows(data.facturas);renderSummary(data.resumen);availableSignature=signature(data.facturas);
            reviewed=data.habilitado?requested:'';message(data.habilitado?'Disponibles para cargar: '+data.facturas.length+' facturas con comprobante valido.':'No hay facturas disponibles con comprobante valido y pendientes de RCC.');
        }catch(e){message(e.message);}finally{busy=false;iniciar.disabled=!connected || reviewed!==key();}
    }
    async function ejecutar(action,params){
        if(busy)return;
        if(action==='cerrar' && !window.confirm('Cerrar este trabajo sin modificar comprobantes RCC?'))return;
        if(action==='crear' && (reviewed!==key() || !window.confirm('Cargar las facturas revisadas del expediente '+exp.value+' en el portal RCC real?')))return;
        if(action!=='cerrar'){await detectar();if(!connected){message('Abra y configure el automatizador en esta PC.');return;}}
        busy=true;iniciar.disabled=true;
        try{var ticket=await api(action,params);
            if(action!=='cerrar'){await local('ejecutar',ticket);message('Trabajo enviado al automatizador. Los resultados se guardan en SIGAP.');}
            else message('Trabajo cerrado. Los comprobantes del portal no fueron modificados.');
            invalidate();await actualizar();
        }catch(e){message(e.message+' Si se creo el trabajo pero no inicio, use Reanudar.');}
        finally{busy=false;}
    }
    async function actualizar(){
        try{var data=await api('listar'),selected=exp.value;
            exp.textContent='';var empty=document.createElement('option');empty.value='';empty.textContent='Seleccione';exp.appendChild(empty);
            data.expedientes.forEach(function(e){var o=document.createElement('option');o.value=e.nexp;o.textContent=e.nexp+' ('+e.cantidad+' facturas; '+e.con_comprobante+' con comprobante)';exp.appendChild(o);});exp.value=selected;
            var area=document.getElementById('trabajosRcc');area.textContent='';
            if(!data.trabajos.length){var emptyState=document.createElement('p');emptyState.className='rcc-empty';emptyState.textContent='Todavía no hay cargas para mostrar en esta instancia de SIGAP.';area.appendChild(emptyState);}
            data.trabajos.forEach(function(j){var box=document.createElement('section'),title=document.createElement('h3'),heading=document.createElement('div'),badge=document.createElement('span');box.className='rcc-job';heading.className='rcc-job-heading';title.textContent='Expediente '+j.nexp;heading.appendChild(title);badge.className='rcc-status'+(j.estado==='completado'?' rcc-status--success':j.estado==='completado_con_revision'?' rcc-status--warning':'');badge.textContent={abierto:'Pendiente',ejecutando:'En curso',completado:'Finalizada',completado_con_revision:'Finalizada con revisiones',cerrado:'Cerrada',vencido:'Vencida'}[j.estado] || j.estado;heading.appendChild(badge);box.appendChild(heading);
                var info=document.createElement('p');info.className='rcc-job-info';var created=new Date(j.creado);info.textContent='Operador: '+j.usuario+' · '+(isNaN(created.getTime())?j.creado:created.toLocaleString('es-AR'));box.appendChild(info);
                var scroll=document.createElement('div');scroll.className='rcc-table-wrap';scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label','Resultados del expediente '+j.nexp);
                var table=document.createElement('table'),head=document.createElement('thead'),headers=document.createElement('tr');
                ['Folio','Estado','Motivo / detalle','Datos verificados en RCC'].forEach(function(label){var th=document.createElement('th');th.scope='col';th.textContent=label;headers.appendChild(th);});head.appendChild(headers);table.appendChild(head);
                var body=document.createElement('tbody');Object.keys(j.resultados).forEach(function(k){var tr=document.createElement('tr'),r=j.resultados[k];cell(tr,folioVisible((j.folios || {})[k]));var state=document.createElement('td'),pill=document.createElement('span');pill.className='rcc-status'+(['revision','incierto'].indexOf(r.estado)>=0?' rcc-status--warning':['guardada','ya_existente','confirmada'].indexOf(r.estado)>=0?' rcc-status--success':'');pill.textContent=estadoResultado(r);state.appendChild(pill);tr.appendChild(state);cell(tr,detalleResultado(r));tr.lastChild.style.whiteSpace='pre-line';tr.lastChild.style.minWidth='280px';cell(tr,(r.fila || []).join(' | '));body.appendChild(tr);});table.appendChild(body);scroll.appendChild(table);box.appendChild(scroll);
                if(j.estado==='abierto' || j.estado==='ejecutando'){var actions=document.createElement('div');actions.className='rcc-actions';['reanudar','cerrar'].forEach(function(action){var b=document.createElement('button');b.type='button';b.textContent=action==='reanudar'?'Reanudar':'Cerrar trabajo';b.addEventListener('click',function(){ejecutar(action,{id:j.id});});actions.appendChild(b);});box.appendChild(actions);}area.appendChild(box);
            });
            if(exp.value)await disponibles();else{invalidate();await disponibles();}
        }catch(e){message(e.message);}
    }
    exp.addEventListener('change',function(){invalidate();availableSignature='';var suffix=exp.value.split('/')[1] || '';year.value=suffix.length===4?suffix:'';disponibles();});year.addEventListener('input',invalidate);
    document.getElementById('detectarRcc').addEventListener('click',detectar);
    document.getElementById('revisarRcc').addEventListener('click',revisar);
    iniciar.addEventListener('click',function(){ejecutar('crear',{nexp:exp.value,anio:year.value});});
    document.getElementById('actualizarRcc').addEventListener('click',actualizar);
    actualizar().then(function(){var requested=new URLSearchParams(location.search).get('nexp');if(requested){exp.value=requested;var suffix=requested.split('/')[1] || '';year.value=suffix.length===4?suffix:'';disponibles();}});
    detectar();setInterval(function(){if(!busy)actualizar();},15000);
})();
