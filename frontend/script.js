'use strict';

const API_URL = 'https://gochobarber.onrender.com';
let horaSeleccionada = null;
let currentUser = null;

// ===== UTILIDADES =====
function escaparHTML(texto) {
    if (texto === null || texto === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(texto);
    return div.innerHTML;
}

function imgFallback(nombre, tipo) {
    const ancho = tipo === 'producto' ? 200 : 150;
    const alto = 150;
    const texto = encodeURIComponent(nombre || 'Imagen');
    return `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="${ancho}" height="${alto}"><rect fill="%232c1a12" width="${ancho}" height="${alto}"/><text x="50%" y="50%" fill="%23c9a84c" font-family="Segoe UI" font-size="14" text-anchor="middle" dominant-baseline="middle">${texto}</text></svg>`;
}

window.imgError = function(img, nombre, tipo) {
    img.onerror = null;
    img.src = imgFallback(nombre, tipo);
};

// ===== CATALOGO (Productos y Estilos) =====
async function cargarProductos() {
    const contenedor = document.getElementById('productosContainer');
    if (!contenedor) return;
    contenedor.innerHTML = '<div class="sin-huecos">Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/catalogo`);
        const items = await res.json();
        const productos = items.filter(i => i.tipo === 'producto');
        contenedor.innerHTML = '';
        if (!productos.length) { contenedor.innerHTML = '<div class="sin-huecos">No hay productos.</div>'; return; }
        productos.forEach(p => {
            const card = document.createElement('div');
            card.className = 'producto-card';
            const nombreSeguro = escaparHTML(p.nombre);
            card.innerHTML = `
                <img src="imagenes/productos/${p.archivo}" alt="${nombreSeguro}" onerror="imgError(this, '${nombreSeguro.replace(/'/g, '')}', 'producto')">
                <div class="nombre">${nombreSeguro}</div>
                <div class="descripcion">${escaparHTML(p.descripcion || '')}</div>
                <div class="precio">${escaparHTML(p.precio || '')}</div>
            `;
            contenedor.appendChild(card);
        });
    } catch (error) {
        contenedor.innerHTML = '<div class="sin-huecos">Error al cargar.</div>';
    }
}

async function cargarEstilos() {
    const contenedor = document.getElementById('estilosContainer');
    if (!contenedor) return;
    contenedor.innerHTML = '<div class="sin-huecos">Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/catalogo`);
        const items = await res.json();
        const estilos = items.filter(i => i.tipo === 'estilo');
        contenedor.innerHTML = '';
        if (!estilos.length) { contenedor.innerHTML = '<div class="sin-huecos">No hay estilos.</div>'; return; }
        estilos.forEach(e => {
            const card = document.createElement('div');
            card.className = 'estilo-card';
            const nombreSeguro = escaparHTML(e.nombre);
            card.innerHTML = `
                <img src="imagenes/cortes/${e.archivo}" alt="${nombreSeguro}" onerror="imgError(this, '${nombreSeguro.replace(/'/g, '')}', 'corte')">
                <div class="nombre">${nombreSeguro}</div>
            `;
            contenedor.appendChild(card);
        });
    } catch (error) {
        contenedor.innerHTML = '<div class="sin-huecos">Error al cargar.</div>';
    }
}

// ===== AUTENTICACION =====
function getAuthHeaders() {
    const headers = { 'Content-Type': 'application/json', 'Accept': 'application/json' };
    if (currentUser && currentUser.username) headers['X-Username'] = currentUser.username;
    return headers;
}

function guardarSesion(user) {
    currentUser = user;
    try { localStorage.setItem('currentUser', JSON.stringify(user)); } catch (e) {}
}

function cargarSesion() {
    try {
        const g = localStorage.getItem('currentUser');
        if (g) currentUser = JSON.parse(g);
    } catch (e) { currentUser = null; }
}

function cerrarSesion() {
    currentUser = null;
    try { localStorage.removeItem('currentUser'); } catch (e) {}
}

function esAdmin() {
    return currentUser && currentUser.rol === 'admin';
}

function actualizarUISegunRol() {
    const admin = esAdmin();
    
    // Tabs y elementos solo para admin
    document.querySelectorAll('.solo-admin').forEach(el => {
        el.style.setProperty('display', admin ? 'inline-block' : 'none', 'important');
    });
    
    // Tabs y elementos solo para barbero
    document.querySelectorAll('.solo-barbero').forEach(el => {
        el.style.setProperty('display', admin ? 'none' : 'inline-block', 'important');
    });
    
    const filtrosP = document.getElementById('filtrosPendientes');
    const filtrosH = document.getElementById('filtrosHistorial');
    const filaSel = document.getElementById('filaSelectorBloqueo');
    if (admin) {
        if (filtrosP) filtrosP.style.display = 'flex';
        if (filtrosH) filtrosH.style.display = 'flex';
        if (filaSel) filaSel.style.display = 'flex';
    } else {
        const selP = document.getElementById('filtroBarberoPendientes');
        const selH = document.getElementById('filtroBarberoHistorial');
        if (selP) selP.parentElement.style.display = 'none';
        if (selH) selH.parentElement.style.display = 'none';
        if (filaSel) filaSel.style.display = 'none';
    }
    const infoUser = document.getElementById('infoUsuario');
    if (infoUser && currentUser) infoUser.textContent = `(${currentUser.username} - ${currentUser.rol})`;
}

async function loginUsuario() {
    const username = document.getElementById('usernameLogin').value.trim();
    const password = document.getElementById('passwordLogin').value;
    if (!username || !password) { alert('Ingresa usuario y contraseña'); return; }
    const msg = document.getElementById('mensajeLogin');
    msg.className = 'mensaje info';
    msg.textContent = 'Verificando...';
    msg.style.display = 'block';
    try {
        const res = await fetch(`${API_URL}/api/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (res.ok) {
            guardarSesion({ username: data.username, rol: data.rol, barbero_id: data.barbero_id });
            document.getElementById('barberoLogin').style.display = 'none';
            document.getElementById('barberoContenido').style.display = 'block';
            document.getElementById('usernameLogin').value = '';
            document.getElementById('passwordLogin').value = '';
            msg.style.display = 'none';
            actualizarUISegunRol();
            cargarBarberosSelectorAdmin();
            cargarServiciosSelectorAdmin();
            cargarPendientes();
        } else {
            msg.className = 'mensaje error';
            msg.textContent = data.error || 'Error';
        }
    } catch (error) {
        msg.className = 'mensaje error';
        msg.textContent = 'Error al conectar.';
    }
}

function verificarSesion() {
    const login = document.getElementById('barberoLogin');
    const contenido = document.getElementById('barberoContenido');
    if (currentUser && currentUser.username) {
        login.style.display = 'none';
        contenido.style.display = 'block';
        actualizarUISegunRol();
        cargarBarberosSelectorAdmin();
        cargarServiciosSelectorAdmin();
        cargarPendientes();
    } else {
        login.style.display = 'block';
        contenido.style.display = 'none';
    }
}

function logoutBarbero() {
    cerrarSesion();
    document.getElementById('barberoLogin').style.display = 'block';
    document.getElementById('barberoContenido').style.display = 'none';
}

// ===== VISTAS =====
function cambiarVista(vista) {
    const btnCliente = document.getElementById('btnCliente');
    const btnBarbero = document.getElementById('btnBarbero');
    const panelCliente = document.getElementById('panelCliente');
    const panelBarbero = document.getElementById('panelBarbero');
    const tabsCliente = document.getElementById('tabsCliente');
    const tabsBarbero = document.getElementById('tabsBarbero');
    if (vista === 'cliente') {
        btnCliente.classList.add('activo');
        btnBarbero.classList.remove('activo');
        panelCliente.style.display = 'block';
        panelBarbero.style.display = 'none';
        tabsCliente.style.display = 'flex';
        tabsBarbero.style.display = 'none';
    } else {
        btnCliente.classList.remove('activo');
        btnBarbero.classList.add('activo');
        panelCliente.style.display = 'none';
        panelBarbero.style.display = 'block';
        tabsCliente.style.display = 'none';
        tabsBarbero.style.display = 'flex';
        verificarSesion();
    }
}

function cambiarTabCliente(tab) {
    document.querySelectorAll('#tabsCliente button').forEach(b => b.classList.remove('activo'));
    document.querySelectorAll('#panelCliente .panel-tab').forEach(p => p.style.display = 'none');
    const b = document.querySelectorAll('#tabsCliente button');
    if (tab === 'reservar') { b[0].classList.add('activo'); document.getElementById('tabReservar').style.display = 'block'; }
    else if (tab === 'mis-citas') { b[1].classList.add('activo'); document.getElementById('tabMisCitas').style.display = 'block'; }
    else if (tab === 'productos') { b[2].classList.add('activo'); document.getElementById('tabProductos').style.display = 'block'; cargarProductos(); }
    else if (tab === 'estilos') { b[3].classList.add('activo'); document.getElementById('tabEstilos').style.display = 'block'; cargarEstilos(); }
}

function cambiarTabBarbero(tab) {
    document.querySelectorAll('#tabsBarbero button').forEach(b => b.classList.remove('activo'));
    document.querySelectorAll('#barberoContenido .panel-tab').forEach(p => p.style.display = 'none');
    const b = document.querySelectorAll('#tabsBarbero button');
    
    // Detectar el índice de cada botón por su texto (más robusto)
    const tabsNombres = Array.from(b).map(btn => btn.textContent.trim());
    const idxPendientes = tabsNombres.indexOf('Pendientes');
    const idxHistorial = tabsNombres.indexOf('Historial');
    const idxBarberos = tabsNombres.indexOf('Barberos');
    const idxServicios = tabsNombres.indexOf('Servicios');
    const idxCatalogo = tabsNombres.indexOf('Catalogo');
    const idxEstadisticas = tabsNombres.indexOf('Estadisticas');
    const idxMisEstadisticas = tabsNombres.indexOf('Mis Estadisticas');
    const idxConfig = tabsNombres.indexOf('Configuracion');
    
    const activar = (idx) => { if (idx >= 0 && b[idx]) b[idx].classList.add('activo'); };
    
    if (tab === 'pendientes') { activar(idxPendientes); document.getElementById('tabPendientes').style.display = 'block'; cargarPendientes(); }
    else if (tab === 'historial') { activar(idxHistorial); document.getElementById('tabHistorial').style.display = 'block'; cargarHistorial(); }
    else if (tab === 'barberos') {
        if (!esAdmin()) { alert('Solo admin'); return; }
        activar(idxBarberos); document.getElementById('tabBarberos').style.display = 'block';
        cargarBarberos(); cargarBarberosSelectorAdmin();
    }
    else if (tab === 'servicios') {
        activar(idxServicios); document.getElementById('tabServicios').style.display = 'block';
        cargarServiciosSelectorAdmin(); cargarServiciosAdmin();
    }
    else if (tab === 'catalogo') {
        if (!esAdmin()) { alert('Solo admin'); return; }
        activar(idxCatalogo); document.getElementById('tabCatalogo').style.display = 'block';
        cargarCatalogoAdmin();
    }
    else if (tab === 'estadisticas') {
        if (!esAdmin()) { alert('Solo admin'); return; }
        activar(idxEstadisticas); document.getElementById('tabEstadisticas').style.display = 'block';
        cargarEstadisticas();
    }
    else if (tab === 'mis-estadisticas') {
        activar(idxMisEstadisticas); document.getElementById('tabMisEstadisticas').style.display = 'block';
        cargarMisEstadisticas();
    }
    else if (tab === 'configuracion') {
        activar(idxConfig); document.getElementById('tabConfiguracion').style.display = 'block';
        cargarBarberosSelectorAdmin();
    }
}

// ===== RESERVAR =====
async function cargarBarberosCliente() {
    try {
        const res = await fetch(`${API_URL}/api/barberos`);
        const bs = await res.json();
        const sel = document.getElementById('barbero');
        if (!sel) return;
        sel.innerHTML = '<option value="0">Cualquiera disponible</option>';
        bs.forEach(b => {
            const o = document.createElement('option');
            o.value = b.id; o.textContent = b.nombre;
            sel.appendChild(o);
        });
        await alCambiarBarbero();
    } catch (e) {}
}

async function alCambiarBarbero() {
    const barberoId = parseInt(document.getElementById('barbero').value) || 0;
    const sel = document.getElementById('servicio');
    if (!sel) return;
    sel.innerHTML = '<option value="">Cargando...</option>';
    try {
        const res = await fetch(`${API_URL}/api/servicios?barbero_id=${barberoId}`);
        const servicios = await res.json();
        sel.innerHTML = '';
        if (!servicios.length) {
            sel.innerHTML = '<option value="">No hay servicios disponibles</option>';
            return;
        }
        servicios.forEach(s => {
            const o = document.createElement('option');
            o.value = s.id;
            o.textContent = `${s.nombre} (${s.duracion_minutos}min - $${Number(s.precio).toLocaleString('es-CO')} COP)`;
            sel.appendChild(o);
        });
    } catch (e) {
        sel.innerHTML = '<option value="">Error al cargar</option>';
    }
}

async function cargarHuecos() {
    const fecha = document.getElementById('fecha').value;
    const barberoId = document.getElementById('barbero').value || 0;
    const servicioId = document.getElementById('servicio').value || 0;
    if (!fecha) { alert('Selecciona fecha'); return; }
    if (!servicioId) { alert('Selecciona un servicio'); return; }
    const c = document.getElementById('huecos');
    c.innerHTML = '<div class="sin-huecos">Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/disponibilidad?fecha=${encodeURIComponent(fecha)}&barbero_id=${barberoId}&servicio_id=${servicioId}`);
        if (!res.ok) throw new Error();
        const data = await res.json();
        c.innerHTML = '';
        if (data.disponibles && data.disponibles.length > 0) {
            [...new Set(data.disponibles)].forEach(h => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.textContent = h;
                btn.onclick = () => {
                    document.querySelectorAll('#huecos button').forEach(b => b.classList.remove('seleccionado'));
                    btn.classList.add('seleccionado');
                    horaSeleccionada = h;
                    document.getElementById('formReserva').style.display = 'block';
                };
                c.appendChild(btn);
            });
        } else {
            c.innerHTML = '<div class="sin-huecos">No hay horas disponibles.</div>';
        }
    } catch (e) {
        c.innerHTML = '<div class="sin-huecos">Error al cargar.</div>';
    }
}

async function reservar() {
    const fecha = document.getElementById('fecha').value;
    const servicio = document.getElementById('servicio').value;
    const barberoId = parseInt(document.getElementById('barbero').value) || 0;
    const nombre = document.getElementById('nombre').value.trim();
    const telefono = document.getElementById('telefono').value.trim();
    const notas = document.getElementById('notas').value.trim();
    if (!nombre) { alert('Nombre obligatorio'); return; }
    if (!horaSeleccionada) { alert('Selecciona hora'); return; }
    if (!servicio) { alert('Selecciona servicio'); return; }
    const msg = document.getElementById('mensajeReserva');
    msg.className = 'mensaje info';
    msg.textContent = 'Procesando...';
    msg.style.display = 'block';
    try {
        const res = await fetch(`${API_URL}/api/reservar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                fecha, hora_inicio: horaSeleccionada,
                servicio_id: parseInt(servicio), barbero_id: barberoId,
                nombre, telefono, notas
            })
        });
        const data = await res.json();
        msg.className = 'mensaje ' + (res.ok ? 'exito' : 'error');
        msg.textContent = data.mensaje || data.error || 'Error';
        if (res.ok) {
            document.getElementById('formReserva').style.display = 'none';
            document.getElementById('huecos').innerHTML = '';
            document.getElementById('nombre').value = '';
            document.getElementById('telefono').value = '';
            document.getElementById('notas').value = '';
            horaSeleccionada = null;
        }
    } catch (e) {
        msg.className = 'mensaje error';
        msg.textContent = 'Error al conectar.';
    }
}

// ===== MIS CITAS =====
async function consultarCitas() {
    const tel = document.getElementById('telefonoConsulta').value.trim();
    if (!tel) { mostrarToast('Ingresa teléfono', 'error'); return; }
    const c = document.getElementById('misCitas');
    c.innerHTML = '<div class="sin-huecos">Buscando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/mis-citas?telefono=${encodeURIComponent(tel)}`);
        const citas = await res.json();
        c.innerHTML = '';
        if (!citas || !citas.length) { c.innerHTML = '<div class="sin-huecos">No hay citas.</div>'; return; }
        citas.forEach(ct => {
            const div = document.createElement('div');
            div.className = 'cita-item';
            
            // Estilos según estado
            let estadoClase = 'estado-pendiente';
            let estadoTexto = 'Pendiente';
            let estiloExtra = '';
            
            if (ct.estado === 'confirmada') {
                estadoClase = 'estado-confirmada';
                estadoTexto = '✓ Confirmada';
            } else if (ct.estado === 'pendiente_confirmacion') {
                estadoClase = 'estado-pendiente';
                estadoTexto = '⏳ Pendiente';
            } else if (ct.estado === 'cancelada_por_barbero') {
                estadoClase = 'estado-expirada';
                estadoTexto = '❌ Cancelada por el barbero';
                estiloExtra = 'border-left-color: #d97a7a;';
            }
            
            // Si es cancelada, mostrar aviso grande
            let avisoCancelada = '';
            if (ct.estado === 'cancelada_por_barbero') {
                avisoCancelada = `
                    <div style="background: rgba(139, 42, 42, 0.2); padding: 10px; border-radius: 6px; margin-bottom: 10px; color: #d97a7a;">
                        ⚠️ Esta cita fue cancelada. Por favor, agenda una nueva.
                    </div>
                `;
            }
            
            // Botones (solo si no está cancelada)
            let botones = '';
            if (ct.estado === 'confirmada' || ct.estado === 'pendiente_confirmacion') {
                botones = `
                    <button class="btn-cancelar" onclick="cancelarCita(${ct.id})">Cancelar</button>
                    <button class="btn-modificar" onclick="solicitarModificacion(${ct.id})">Modificar</button>
                `;
            }
            
            div.style = estiloExtra;
            div.innerHTML = `
                <div class="info">
                    ${avisoCancelada}
                    <div class="fecha-hora">${escaparHTML(ct.fecha)} - ${escaparHTML(ct.hora_inicio)}</div>
                    <div class="servicio">${escaparHTML(ct.servicio)}</div>
                    <div class="barbero-info">Barbero: ${escaparHTML(ct.barbero || 'N/A')}</div>
                </div>
                <div><span class="estado ${estadoClase}">${estadoTexto}</span></div>
                <div class="acciones">${botones}</div>
            `;
            c.appendChild(div);
        });
    } catch (e) { c.innerHTML = '<div class="sin-huecos">Error.</div>'; }
}

async function cancelarCita(id) {
    if (!confirm('¿Cancelar cita?')) return;
    try {
        const res = await fetch(`${API_URL}/api/cancelar-cita`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cita_id: id })
        });
        const data = await res.json();
        mostrarToast(data.mensaje || data.error, res.ok ? 'exito' : 'error');
        if (res.ok) consultarCitas();
    } catch (e) { alert('Error.'); }
}

async function solicitarModificacion(id) {
    const nf = prompt('Nueva fecha (YYYY-MM-DD):'); if (!nf) return;
    const nh = prompt('Nueva hora (HH:MM):'); if (!nh) return;
    try {
        const res = await fetch(`${API_URL}/api/solicitar-modificacion`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cita_original_id: id, nueva_fecha: nf, nueva_hora: nh })
        });
        const data = await res.json();
        mostrarToast(data.mensaje || data.error, res.ok ? 'exito' : 'error');
        if (res.ok) consultarCitas();
    } catch (e) { alert('Error.'); }
}

// ===== PENDIENTES =====
async function cargarPendientes() {
    const c = document.getElementById('pendientesLista');
    if (!c) return;
    const bid = document.getElementById('filtroBarberoPendientes')?.value || 0;
    c.innerHTML = '<div class="sin-huecos">Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/panel/pendientes?barbero_id=${bid}`, { headers: getAuthHeaders() });
        if (res.status === 401) {
            cerrarSesion();
            document.getElementById('barberoLogin').style.display = 'block';
            document.getElementById('barberoContenido').style.display = 'none';
            return;
        }
        const citas = await res.json();
        c.innerHTML = '';
        if (!citas || !citas.length) { c.innerHTML = '<div class="sin-huecos">No hay pendientes.</div>'; return; }
        citas.forEach(ct => {
            const div = document.createElement('div');
            div.className = 'cita-item';
            let botonElim = '';
            if (esAdmin()) botonElim = `<button class="btn-danger" style="background:#5a1a1a;" onclick="eliminarCitaPermanente(${ct.id})">🗑️ Eliminar</button>`;
            div.innerHTML = `
                <div class="info">
                    <div class="fecha-hora">${escaparHTML(ct.fecha)} - ${escaparHTML(ct.hora_inicio)}</div>
                    <div class="servicio">${escaparHTML(ct.servicio)} (${escaparHTML(ct.tipo_reserva)})</div>
                    <div class="cliente">${escaparHTML(ct.cliente)} - ${escaparHTML(ct.telefono || 'N/A')}</div>
                    <div class="barbero-info">Barbero: ${escaparHTML(ct.barbero)}</div>
                </div>
                <div><span class="estado estado-pendiente">Pendiente</span></div>
                <div class="acciones">
                    <button class="btn-confirmar" onclick="confirmarCita(${ct.id})">Aceptar</button>
                    <button class="btn-rechazar" onclick="rechazarCita(${ct.id})">Rechazar</button>
                    ${botonElim}
                </div>
            `;
            c.appendChild(div);
        });
    } catch (e) { c.innerHTML = '<div class="sin-huecos">Error.</div>'; }
}

async function confirmarCita(id) {
    if (!confirm('¿Confirmar?')) return;
    try {
        const res = await fetch(`${API_URL}/api/panel/confirmar-cita`, {
            method: 'POST', headers: getAuthHeaders(),
            body: JSON.stringify({ cita_id: id })
        });
        const d = await res.json();
        alert(d.mensaje || d.error);
        cargarPendientes();
    } catch (e) { alert('Error.'); }
}

async function rechazarCita(id) {
    if (!await mostrarConfirmacion('¿Rechazar esta cita?')) return;
    try {
        const res = await fetch(`${API_URL}/api/panel/rechazar-cita`, {
            method: 'POST', headers: getAuthHeaders(),
            body: JSON.stringify({ cita_id: id })
        });
        const d = await res.json();
        if (res.ok) {
            mostrarToast('✅ Cita rechazada', 'exito');
            // Ofrecer avisar por WhatsApp
            if (d.cliente_telefono) {
                setTimeout(() => {
                    if (confirm(`¿Avisar a ${d.cliente} por WhatsApp que su cita fue rechazada?`)) {
                        avisarPorWhatsApp(d.cliente, d.cliente_telefono, d.fecha, d.hora_inicio, 'rechazada');
                    }
                }, 500);
            }
        } else {
            mostrarToast(d.error || 'Error', 'error');
        }
        cargarPendientes();
    } catch (e) { mostrarToast('Error al conectar', 'error'); }
}

// ===== HISTORIAL =====
async function cargarHistorial() {
    const c = document.getElementById('historialLista');
    if (!c) return;
    const bid = document.getElementById('filtroBarberoHistorial')?.value || 0;
    c.innerHTML = '<div class="sin-huecos">Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/panel/historial?barbero_id=${bid}`, { headers: getAuthHeaders() });
        if (res.status === 401) {
            cerrarSesion();
            document.getElementById('barberoLogin').style.display = 'block';
            document.getElementById('barberoContenido').style.display = 'none';
            return;
        }
        const citas = await res.json();
        c.innerHTML = '';
        if (!citas || !citas.length) { c.innerHTML = '<div class="sin-huecos">Sin citas.</div>'; return; }
        const estados = {
            'confirmada': { clase: 'estado-confirmada', texto: 'Confirmada' },
            'pendiente_confirmacion': { clase: 'estado-pendiente', texto: 'Pendiente' },
            'realizada': { clase: 'estado-realizada', texto: 'Realizada' },
            'expirada': { clase: 'estado-expirada', texto: 'Expirada' },
            'cancelada_por_cliente': { clase: 'estado-expirada', texto: 'Cancelada (Cliente)' },
            'cancelada_por_barbero': { clase: 'estado-expirada', texto: 'Cancelada (Barbero)' },
            'cancelada_por_sistema': { clase: 'estado-expirada', texto: 'Cancelada (Sistema)' }
        };
        citas.forEach(ct => {
            const div = document.createElement('div');
            div.className = 'cita-item';
            const e = estados[ct.estado] || { clase: 'estado-pendiente', texto: ct.estado };
            let botones = '';
            if (ct.estado === 'confirmada') botones += `<button class="btn-danger" onclick="cancelarCitaConfirmada(${ct.id})">Cancelar</button>`;
            if (esAdmin()) botones += `<button class="btn-danger" style="background:#5a1a1a;" onclick="eliminarCitaPermanente(${ct.id})">🗑️ Eliminar</button>`;
            div.innerHTML = `
                <div class="info">
                    <div class="fecha-hora">${escaparHTML(ct.fecha)} - ${escaparHTML(ct.hora_inicio)}</div>
                    <div class="servicio">${escaparHTML(ct.servicio)} - ${escaparHTML(ct.cliente)}</div>
                    <div class="barbero-info">Barbero: ${escaparHTML(ct.barbero || 'N/A')}</div>
                </div>
                <div><span class="estado ${e.clase}">${e.texto}</span></div>
                <div class="acciones">${botones}</div>
            `;
            c.appendChild(div);
        });
    } catch (e) { c.innerHTML = '<div class="sin-huecos">Error.</div>'; }
}

async function cancelarCitaConfirmada(id) {
    if (!await mostrarConfirmacion('¿Cancelar esta cita?')) return;
    try {
        const res = await fetch(`${API_URL}/api/panel/cancelar-cita-confirmada`, {
            method: 'POST', headers: getAuthHeaders(),
            body: JSON.stringify({ cita_id: id })
        });
        const d = await res.json();
        if (res.ok) {
            mostrarToast('✅ Cita cancelada', 'exito');
            // Ofrecer avisar por WhatsApp
            if (d.cliente_telefono) {
                setTimeout(() => {
                    if (confirm(`¿Avisar a ${d.cliente} por WhatsApp que su cita fue cancelada?`)) {
                        avisarPorWhatsApp(d.cliente, d.cliente_telefono, d.fecha, d.hora_inicio, 'cancelada');
                    }
                }, 500);
            }
        } else {
            mostrarToast(d.error || 'Error', 'error');
        }
        if (res.ok) cargarHistorial();
    } catch (e) { mostrarToast('Error al conectar', 'error'); }
}

async function eliminarCitaPermanente(id) {
    if (!confirm('⚠️ ¿ELIMINAR PERMANENTEMENTE?')) return;
    if (!confirm('¿Estás seguro?')) return;
    try {
        const res = await fetch(`${API_URL}/api/admin/citas/${id}`, {
            method: 'DELETE', headers: getAuthHeaders()
        });
        const d = await res.json();
        alert(d.mensaje || d.error);
        if (res.ok) { cargarHistorial(); cargarPendientes(); }
    } catch (e) { alert('Error.'); }
}

// ===== BARBEROS (ADMIN) =====
function abrirFormBarbero() {
    document.getElementById('formBarbero').style.display = 'block';
    document.getElementById('barberoEditId').value = '';
    document.getElementById('barberoNombre').value = '';
    document.getElementById('barberoTelefono').value = '';
    document.getElementById('barberoEmail').value = '';
    document.getElementById('barberoHoraInicio').value = '08:00';
    document.getElementById('barberoHoraFin').value = '17:00';
    document.getElementById('barberoConPausa').value = 'no';
    document.getElementById('barberoPausaInicio').value = '12:00';
    document.getElementById('barberoPausaFin').value = '14:00';
    toggleCamposPausa();
    document.querySelectorAll('.dia-check').forEach(c => c.checked = true);
    document.getElementById('mensajeBarbero').style.display = 'none';
}

function cerrarFormBarbero() { document.getElementById('formBarbero').style.display = 'none'; }

async function guardarBarbero() {
    const id = document.getElementById('barberoEditId').value;
    const nombre = document.getElementById('barberoNombre').value.trim();
    if (!nombre) { mostrarToast('El nombre es obligatorio', 'error'); return; }
    const dias = Array.from(document.querySelectorAll('.dia-check:checked')).map(c => c.value);
    if (!dias.length) { mostrarToast('Selecciona días', 'error'); return; }
    
    const conPausa = document.getElementById('barberoConPausa').value === 'si';
    const body = {
        nombre,
        telefono: document.getElementById('barberoTelefono').value.trim(),
        email: document.getElementById('barberoEmail').value.trim(),
        hora_inicio: document.getElementById('barberoHoraInicio').value,
        hora_fin: document.getElementById('barberoHoraFin').value,
        pausa_inicio: conPausa ? document.getElementById('barberoPausaInicio').value : null,
        pausa_fin: conPausa ? document.getElementById('barberoPausaFin').value : null,
        dias_trabajo: dias
    };
    const url = id ? `${API_URL}/api/admin/barberos/${id}` : `${API_URL}/api/admin/barberos`;
    const method = id ? 'PUT' : 'POST';
    try {
        const res = await fetch(url, { method, headers: getAuthHeaders(), body: JSON.stringify(body) });
        const d = await res.json();
        mostrarToast(d.mensaje || d.error, res.ok ? 'exito' : 'error');
        if (res.ok) {
            setTimeout(() => {
                cerrarFormBarbero();
                cargarBarberos();
                cargarBarberosSelectorAdmin();
                cargarBarberosCliente();
            }, 1500);
        }
    } catch (e) { mostrarToast('Error al conectar', 'error'); }
}

async function cargarBarberos() {
    const c = document.getElementById('listaBarberos');
    if (!c) return;
    c.innerHTML = '<div class="sin-huecos">Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/admin/barberos`, { headers: getAuthHeaders() });
        if (res.status === 401) { c.innerHTML = '<div class="sin-huecos">Sesión expirada.</div>'; return; }
        const barberos = await res.json();
        c.innerHTML = '';
        if (!barberos.length) { c.innerHTML = '<div class="sin-huecos">No hay barberos.</div>'; return; }
        barberos.forEach(b => {
            const div = document.createElement('div');
            div.className = 'cita-item';
            div.style.opacity = b.activo ? 1 : 0.6;
            
            let botones = '';
            if (esAdmin()) {
                if (b.activo) {
                    // Barbero activo: editar, desactivar, eliminar
                    botones = `
                        <button class="btn-modificar" onclick="editarBarbero(${b.id})">Editar</button>
                        <button class="btn-danger" onclick="desactivarBarbero(${b.id})">Desactivar</button>
                        <button class="btn-danger" style="background:#5a1a1a;" onclick="eliminarBarberoPermanente(${b.id})">🗑️</button>
                    `;
                } else {
                    // Barbero inactivo: reactivar, editar, eliminar
                    botones = `
                        <button class="btn-success" onclick="reactivarBarbero(${b.id})">✅ Reactivar</button>
                        <button class="btn-modificar" onclick="editarBarbero(${b.id})">Editar</button>
                        <button class="btn-danger" style="background:#5a1a1a;" onclick="eliminarBarberoPermanente(${b.id})">🗑️</button>
                    `;
                }
            }
            
            const horario = `${escaparHTML(b.hora_inicio || '08:00')} - ${escaparHTML(b.hora_fin || '17:00')}`;
            const pausa = (b.pausa_inicio && b.pausa_fin) ? ` | Pausa: ${escaparHTML(b.pausa_inicio)} - ${escaparHTML(b.pausa_fin)}` : '';
            
            div.innerHTML = `
                <div class="info">
                    <div class="fecha-hora">${escaparHTML(b.nombre)} ${!b.activo ? '<small style="color:#8a7a6a;">(Inactivo)</small>' : ''}</div>
                    <div class="cliente">${escaparHTML(b.telefono || 'Sin tel')} - ${escaparHTML(b.email || 'Sin email')}</div>
                    <div class="barbero-info">Horario: ${horario}${pausa} | Estado: ${b.activo ? 'Activo' : 'Inactivo'}</div>
                </div>
                <div class="acciones">${botones}</div>
            `;
            c.appendChild(div);
        });
    } catch (e) { c.innerHTML = '<div class="sin-huecos">Error.</div>'; }
}

async function editarBarbero(id) {
    try {
        const res = await fetch(`${API_URL}/api/admin/barberos`, { headers: getAuthHeaders() });
        const bs = await res.json();
        const b = bs.find(x => x.id === id);
        if (!b) return;
        document.getElementById('barberoEditId').value = b.id;
        document.getElementById('barberoNombre').value = b.nombre || '';
        document.getElementById('barberoTelefono').value = b.telefono || '';
        document.getElementById('barberoEmail').value = b.email || '';
        document.getElementById('barberoHoraInicio').value = b.hora_inicio || '08:00';
        document.getElementById('barberoHoraFin').value = b.hora_fin || '17:00';
        if (b.pausa_inicio && b.pausa_fin) {
            document.getElementById('barberoConPausa').value = 'si';
            document.getElementById('barberoPausaInicio').value = b.pausa_inicio;
            document.getElementById('barberoPausaFin').value = b.pausa_fin;
        } else {
            document.getElementById('barberoConPausa').value = 'no';
        }
        toggleCamposPausa();
        let dias = [];
        try { dias = JSON.parse(b.dias_trabajo); } catch (e) {}
        document.querySelectorAll('.dia-check').forEach(c => c.checked = dias.includes(c.value));
        document.getElementById('formBarbero').style.display = 'block';
        document.getElementById('formBarbero').scrollIntoView({ behavior: 'smooth' });
    } catch (e) { mostrarToast('Error al cargar datos', 'error'); }
}

async function desactivarBarbero(id) {
    if (!confirm('¿Desactivar? Se cancelarán sus citas futuras.')) return;
    try {
        const res = await fetch(`${API_URL}/api/admin/barberos/${id}`, {
            method: 'DELETE', headers: getAuthHeaders()
        });
        const d = await res.json();
        alert(d.mensaje || d.error);
        if (res.ok) { cargarBarberos(); cargarBarberosSelectorAdmin(); cargarBarberosCliente(); }
    } catch (e) { alert('Error.'); }
}

async function eliminarBarberoPermanente(id) {
    if (!confirm('⚠️ ¿ELIMINAR PERMANENTEMENTE?\nSe borrarán sus datos y usuario.')) return;
    if (!confirm('¿Estás seguro?')) return;
    try {
        const res = await fetch(`${API_URL}/api/admin/barberos/${id}/permanente`, {
            method: 'DELETE', headers: getAuthHeaders()
        });
        const d = await res.json();
        alert(d.mensaje || d.error);
        if (res.ok) { cargarBarberos(); cargarBarberosSelectorAdmin(); cargarBarberosCliente(); }
    } catch (e) { alert('Error.'); }
}

async function cargarBarberosSelectorAdmin() {
    try {
        const res = await fetch(`${API_URL}/api/admin/barberos`, { headers: getAuthHeaders() });
        if (res.status === 401) return;
        const bs = (await res.json()).filter(b => b.activo);
        const fP = document.getElementById('filtroBarberoPendientes');
        const fH = document.getElementById('filtroBarberoHistorial');
        const bB = document.getElementById('bloqueoBarbero');
        if (esAdmin()) {
            [fP, fH].forEach(sel => {
                if (!sel) return;
                const v = sel.value;
                sel.innerHTML = '<option value="0">Todos</option>';
                bs.forEach(b => {
                    const o = document.createElement('option');
                    o.value = b.id; o.textContent = b.nombre;
                    sel.appendChild(o);
                });
                if (v) sel.value = v;
            });
            if (bB) {
                bB.innerHTML = '';
                bs.forEach(b => {
                    const o = document.createElement('option');
                    o.value = b.id; o.textContent = b.nombre;
                    bB.appendChild(o);
                });
            }
        }
    } catch (e) {}
}

// ===== SERVICIOS (ADMIN) =====
async function cargarServiciosSelectorAdmin() {
    const sel = document.getElementById('serviciosBarberoSelect');
    if (!sel) return;
    try {
        // Si es admin, mostrar todos los barberos
        if (esAdmin()) {
            const res = await fetch(`${API_URL}/api/admin/barberos`, { headers: getAuthHeaders() });
            const bs = (await res.json()).filter(b => b.activo);
            const val = sel.value;
            sel.innerHTML = '';
            bs.forEach(b => {
                const o = document.createElement('option');
                o.value = b.id; o.textContent = b.nombre;
                sel.appendChild(o);
            });
            if (val) sel.value = val;
        } else {
            // Si es barbero, solo su propio nombre
            const o = document.createElement('option');
            o.value = currentUser.barbero_id;
            o.textContent = 'Mis servicios';
            sel.innerHTML = '';
            sel.appendChild(o);
            sel.parentElement.style.display = 'none';
        }
    } catch (e) {}
}

async function cargarServiciosAdmin() {
    const c = document.getElementById('listaServicios');
    if (!c) return;
    const selBarbero = document.getElementById('serviciosBarberoSelect');
    const barberoId = selBarbero?.value || currentUser?.barbero_id;
    if (!barberoId) { c.innerHTML = '<div class="sin-huecos">Selecciona un barbero.</div>'; return; }
    c.innerHTML = '<div class="sin-huecos">Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/admin/servicios?barbero_id=${barberoId}`, { headers: getAuthHeaders() });
        if (res.status === 401) { c.innerHTML = '<div class="sin-huecos">Sesión expirada.</div>'; return; }
        const servicios = await res.json();
        c.innerHTML = '';
        if (!servicios.length) { c.innerHTML = '<div class="sin-huecos">No hay servicios.</div>'; return; }
        servicios.forEach(s => {
            const div = document.createElement('div');
            div.className = 'cita-item';
            div.style.opacity = s.activo ? 1 : 0.5;
            div.innerHTML = `
                <div class="info">
                    <div class="fecha-hora">${escaparHTML(s.nombre)} ${!s.activo ? '<small style="color:#8a7a6a;">(Inactivo)</small>' : ''}</div>
                    <div class="servicio">Duracion: ${s.duracion_minutos} min - Precio: $${Number(s.precio).toLocaleString('es-CO')} COP</div>
                    ${s.descripcion ? `<div class="cliente">${escaparHTML(s.descripcion)}</div>` : ''}
                </div>
                <div class="acciones">
                    <button class="btn-modificar" onclick="editarServicio(${s.id})">Editar</button>
                    <button class="btn-secundario" onclick="toggleServicioActivo(${s.id}, ${s.activo})">${s.activo ? 'Desactivar' : 'Activar'}</button>
                    <button class="btn-danger" onclick="eliminarServicio(${s.id})">🗑️</button>
                </div>
            `;
            c.appendChild(div);
        });
    } catch (e) { c.innerHTML = '<div class="sin-huecos">Error.</div>'; }
}

function abrirFormServicio() {
    document.getElementById('formServicio').style.display = 'block';
    document.getElementById('servicioEditId').value = '';
    document.getElementById('servicioNombre').value = '';
    document.getElementById('servicioDuracion').value = '';
    document.getElementById('servicioPrecio').value = '';
    document.getElementById('servicioDescripcion').value = '';
    document.getElementById('mensajeServicio').style.display = 'none';
}

function cerrarFormServicio() { document.getElementById('formServicio').style.display = 'none'; }

async function guardarServicio() {
    const id = document.getElementById('servicioEditId').value;
    const nombre = document.getElementById('servicioNombre').value.trim();
    const duracion = parseInt(document.getElementById('servicioDuracion').value);
    const precio = parseFloat(document.getElementById('servicioPrecio').value);
    if (!nombre) { alert('El nombre es obligatorio'); return; }
    if (!duracion || duracion <= 0) { alert('Duración inválida'); return; }
    if (isNaN(precio) || precio < 0) { alert('Precio inválido'); return; }
    const selBarbero = document.getElementById('serviciosBarberoSelect');
    const barberoId = selBarbero?.value || currentUser?.barbero_id;
    const body = {
        nombre,
        duracion_minutos: duracion,
        precio: precio,
        descripcion: document.getElementById('servicioDescripcion').value.trim(),
        barbero_id: parseInt(barberoId)
    };
    const url = id ? `${API_URL}/api/admin/servicios/${id}` : `${API_URL}/api/admin/servicios`;
    const method = id ? 'PUT' : 'POST';
    try {
        const res = await fetch(url, { method, headers: getAuthHeaders(), body: JSON.stringify(body) });
        const d = await res.json();
        const msg = document.getElementById('mensajeServicio');
        msg.className = 'mensaje ' + (res.ok ? 'exito' : 'error');
        msg.textContent = d.mensaje || d.error;
        msg.style.display = 'block';
        if (res.ok) {
            setTimeout(() => { cerrarFormServicio(); cargarServiciosAdmin(); }, 1000);
        }
    } catch (e) { alert('Error.'); }
}

async function editarServicio(id) {
    const selBarbero = document.getElementById('serviciosBarberoSelect');
    const barberoId = selBarbero?.value || currentUser?.barbero_id;
    try {
        const res = await fetch(`${API_URL}/api/admin/servicios?barbero_id=${barberoId}`, { headers: getAuthHeaders() });
        const servicios = await res.json();
        const s = servicios.find(x => x.id === id);
        if (!s) return;
        document.getElementById('servicioEditId').value = s.id;
        document.getElementById('servicioNombre').value = s.nombre;
        document.getElementById('servicioDuracion').value = s.duracion_minutos;
        document.getElementById('servicioPrecio').value = s.precio;
        document.getElementById('servicioDescripcion').value = s.descripcion || '';
        document.getElementById('formServicio').style.display = 'block';
        document.getElementById('formServicio').scrollIntoView({ behavior: 'smooth' });
    } catch (e) { alert('Error.'); }
}

async function toggleServicioActivo(id, activo) {
    try {
        const res = await fetch(`${API_URL}/api/admin/servicios/${id}`, {
            method: 'PUT', headers: getAuthHeaders(),
            body: JSON.stringify({ activo: !activo })
        });
        if (res.ok) cargarServiciosAdmin();
    } catch (e) {}
}

async function eliminarServicio(id) {
    if (!confirm('¿Eliminar este servicio? Si tiene citas, solo se desactivará.')) return;
    try {
        const res = await fetch(`${API_URL}/api/admin/servicios/${id}`, {
            method: 'DELETE', headers: getAuthHeaders()
        });
        const d = await res.json();
        alert(d.mensaje || d.error);
        if (res.ok) cargarServiciosAdmin();
    } catch (e) { alert('Error.'); }
}

// ===== CATALOGO (ADMIN) =====
async function cargarCatalogoAdmin() {
    const c = document.getElementById('listaCatalogo');
    if (!c) return;
    c.innerHTML = '<div class="sin-huecos">Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/admin/catalogo`, { headers: getAuthHeaders() });
        if (res.status === 401) { c.innerHTML = '<div class="sin-huecos">Sesión expirada.</div>'; return; }
        const items = await res.json();
        c.innerHTML = '';
        if (!items.length) { c.innerHTML = '<div class="sin-huecos">Catálogo vacío.</div>'; return; }
        const prods = items.filter(i => i.tipo === 'producto');
        const ests = items.filter(i => i.tipo === 'estilo');
        const render = (titulo, lista) => {
            if (!lista.length) return '';
            return `<h4 style="color:#c9a84c; margin:20px 0 10px;">${titulo} (${lista.length})</h4>` +
                lista.map(i => `
                    <div class="cita-item" style="opacity:${i.activo ? 1 : 0.5};">
                        <div class="info">
                            <div class="fecha-hora">${escaparHTML(i.nombre)} ${!i.activo ? '<small style="color:#8a7a6a;">(Inactivo)</small>' : ''}</div>
                            <div class="servicio">${escaparHTML(i.archivo)}${i.precio ? ' - ' + escaparHTML(i.precio) : ''}</div>
                            ${i.descripcion ? `<div class="cliente">${escaparHTML(i.descripcion)}</div>` : ''}
                        </div>
                        <div class="acciones">
                            <button class="btn-modificar" onclick="editarItem(${i.id})">Editar</button>
                            <button class="btn-secundario" onclick="toggleItemActivo(${i.id}, ${i.activo})">${i.activo ? 'Desactivar' : 'Activar'}</button>
                            <button class="btn-danger" onclick="eliminarItem(${i.id})">🗑️</button>
                        </div>
                    </div>
                `).join('');
        };
        c.innerHTML = render('Productos', prods) + render('Estilos', ests);
    } catch (e) { c.innerHTML = '<div class="sin-huecos">Error.</div>'; }
}

function abrirFormItem() {
    document.getElementById('formItem').style.display = 'block';
    document.getElementById('itemEditId').value = '';
    document.getElementById('itemTipo').value = 'producto';
    document.getElementById('itemArchivo').value = '';
    document.getElementById('itemNombre').value = '';
    document.getElementById('itemPrecio').value = '';
    document.getElementById('itemDescripcion').value = '';
    document.getElementById('itemOrden').value = 0;
    document.getElementById('mensajeItem').style.display = 'none';
}

function cerrarFormItem() { document.getElementById('formItem').style.display = 'none'; }

async function guardarItem() {
    const id = document.getElementById('itemEditId').value;
    const body = {
        tipo: document.getElementById('itemTipo').value,
        archivo: document.getElementById('itemArchivo').value.trim(),
        nombre: document.getElementById('itemNombre').value.trim(),
        precio: document.getElementById('itemPrecio').value.trim(),
        descripcion: document.getElementById('itemDescripcion').value.trim(),
        orden: parseInt(document.getElementById('itemOrden').value) || 0
    };
    if (!body.archivo || !body.nombre) { alert('Archivo y nombre obligatorios'); return; }
    const url = id ? `${API_URL}/api/admin/catalogo/${id}` : `${API_URL}/api/admin/catalogo`;
    const method = id ? 'PUT' : 'POST';
    try {
        const res = await fetch(url, { method, headers: getAuthHeaders(), body: JSON.stringify(body) });
        const d = await res.json();
        const msg = document.getElementById('mensajeItem');
        msg.className = 'mensaje ' + (res.ok ? 'exito' : 'error');
        msg.textContent = d.mensaje || d.error;
        msg.style.display = 'block';
        if (res.ok) setTimeout(() => { cerrarFormItem(); cargarCatalogoAdmin(); }, 1000);
    } catch (e) { alert('Error.'); }
}

async function editarItem(id) {
    try {
        const res = await fetch(`${API_URL}/api/admin/catalogo`, { headers: getAuthHeaders() });
        const items = await res.json();
        const it = items.find(i => i.id === id);
        if (!it) return;
        document.getElementById('itemEditId').value = it.id;
        document.getElementById('itemTipo').value = it.tipo;
        document.getElementById('itemArchivo').value = it.archivo;
        document.getElementById('itemNombre').value = it.nombre;
        document.getElementById('itemPrecio').value = it.precio || '';
        document.getElementById('itemDescripcion').value = it.descripcion || '';
        document.getElementById('itemOrden').value = it.orden || 0;
        document.getElementById('formItem').style.display = 'block';
        document.getElementById('formItem').scrollIntoView({ behavior: 'smooth' });
    } catch (e) { alert('Error.'); }
}

async function toggleItemActivo(id, activo) {
    try {
        const res = await fetch(`${API_URL}/api/admin/catalogo/${id}`, {
            method: 'PUT', headers: getAuthHeaders(),
            body: JSON.stringify({ activo: !activo })
        });
        if (res.ok) cargarCatalogoAdmin();
    } catch (e) {}
}

async function eliminarItem(id) {
    if (!confirm('¿Eliminar item? (La imagen sigue en el repo)')) return;
    try {
        const res = await fetch(`${API_URL}/api/admin/catalogo/${id}`, {
            method: 'DELETE', headers: getAuthHeaders()
        });
        const d = await res.json();
        alert(d.mensaje || d.error);
        if (res.ok) cargarCatalogoAdmin();
    } catch (e) { alert('Error.'); }
}

// ===== BLOQUEAR DIAS =====
async function bloquearDias() {
    const ini = document.getElementById('bloqueoInicio').value;
    const fin = document.getElementById('bloqueoFin').value;
    const mot = document.getElementById('bloqueoMotivo').value.trim() || 'Descanso';
    const bid = parseInt(document.getElementById('bloqueoBarbero')?.value) || 1;
    if (!ini || !fin) { alert('Fechas'); return; }
    if (fin < ini) { alert('Fecha fin inválida'); return; }
    const msg = document.getElementById('mensajeBloqueo');
    msg.className = 'mensaje info';
    msg.textContent = 'Procesando...';
    msg.style.display = 'block';
    try {
        const res = await fetch(`${API_URL}/api/panel/bloquear`, {
            method: 'POST', headers: getAuthHeaders(),
            body: JSON.stringify({ fecha_inicio: ini, fecha_fin: fin, motivo: mot, barbero_id: bid })
        });
        const d = await res.json();
        if (res.status === 409) {
            if (confirm(`Hay ${d.citas_afectadas.length} citas. ¿Cancelar?`)) {
                const ids = d.citas_afectadas.map(c => c.id);
                const r2 = await fetch(`${API_URL}/api/panel/cancelar-citas-masivo`, {
                    method: 'POST', headers: getAuthHeaders(),
                    body: JSON.stringify({ cita_ids: ids })
                });
                const d2 = await r2.json();
                msg.className = 'mensaje exito';
                msg.textContent = d2.mensaje;
            }
        } else if (res.ok) {
            msg.className = 'mensaje exito';
            msg.textContent = d.mensaje;
        } else {
            msg.className = 'mensaje error';
            msg.textContent = d.error || 'Error';
        }
    } catch (e) {
        msg.className = 'mensaje error';
        msg.textContent = 'Error al conectar.';
    }
}

// Helper: obtener fecha en zona horaria de Venezuela (UTC-4)
function fechaVE(diasAdelante = 0) {
    // Crear fecha actual en UTC
    const ahora = new Date();
    // Convertir a hora Venezuela (UTC-4)
    const ahoraVE = new Date(ahora.getTime() - (4 * 60 * 60 * 1000));
    // Sumar días
    ahoraVE.setUTCDate(ahoraVE.getUTCDate() + diasAdelante);
    // Devolver en formato YYYY-MM-DD
    return ahoraVE.toISOString().split('T')[0];
}

// ===== INICIALIZACIÓN =====
document.addEventListener('DOMContentLoaded', function() {
    cargarModo();
    cargarSesion();
    actualizarUISegunRol();
    try {
        const fechaManana = fechaVE(1);  // Mañana
        const fechaHoy = fechaVE(0);      // Hoy

        const iF = document.getElementById('fecha');
        if (iF) { iF.value = fechaManana; iF.min = fechaHoy; }

        const iI = document.getElementById('bloqueoInicio');
        const iFn = document.getElementById('bloqueoFin');
        if (iI) { iI.value = fechaHoy; iI.min = fechaHoy; }
        if (iFn) { iFn.value = fechaHoy; iFn.min = fechaHoy; }
    } catch (e) {}
    cargarBarberosCliente();
});

// TOASTS
function mostrarToast(mensaje, tipo = 'info', duracion = 3500) {
    const cont = document.getElementById('toast-container');
    if (!cont) return;
    const toast = document.createElement('div');
    toast.className = `toast ${tipo}`;
    toast.textContent = mensaje;
    cont.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, duracion);
}

// MODAL
let modalResolve = null;
function mostrarConfirmacion(mensaje, titulo = 'Confirmar') {
    return new Promise(resolve => {
        modalResolve = resolve;
        document.getElementById('modal-titulo').textContent = titulo;
        document.getElementById('modal-mensaje').textContent = mensaje;
        document.getElementById('modal-overlay').classList.add('activo');
    });
}
function cerrarModal(resultado) {
    document.getElementById('modal-overlay').classList.remove('activo');
    if (modalResolve) { modalResolve(resultado); modalResolve = null; }
}

function toggleModo() {
    document.body.classList.toggle('modo-claro');
    const modo = document.body.classList.contains('modo-claro') ? 'claro' : 'oscuro';
    try { localStorage.setItem('modo', modo); } catch (e) {}
    mostrarToast(`Modo ${modo}`, 'info');
}
function cargarModo() {
    try {
        if (localStorage.getItem('modo') === 'claro') document.body.classList.add('modo-claro');
    } catch (e) {}
}

function toggleCamposPausa() {
    const val = document.getElementById('barberoConPausa').value;
    document.getElementById('campoPausaInicio').style.display = val === 'si' ? 'block' : 'none';
    document.getElementById('campoPausaFin').style.display = val === 'si' ? 'block' : 'none';
}

async function reactivarBarbero(id) {
    if (!confirm('¿Reactivar este barbero?')) return;
    try {
        const res = await fetch(`${API_URL}/api/admin/barberos/${id}/reactivar`, {
            method: 'PUT',
            headers: getAuthHeaders()
        });
        const d = await res.json();
        alert(d.mensaje || d.error);
        if (res.ok) {
            cargarBarberos();
            cargarBarberosSelectorAdmin();
            cargarBarberosCliente();
        }
    } catch (e) { alert('Error.'); }
}

// ===== AVISAR POR WHATSAPP =====
function avisarPorWhatsApp(nombre, telefono, fecha, hora, accion) {
    // Limpiar el teléfono: solo dígitos
    let numero = String(telefono || '').replace(/\D/g, '');
    if (!numero) {
        mostrarToast('El cliente no tiene teléfono registrado', 'error');
        return;
    }
    // Si empieza con 0, asumir Venezuela (+58)
    if (numero.startsWith('0')) {
        numero = '58' + numero.substring(1);
    }
    // Si no empieza con 58, asumir Venezuela
    if (!numero.startsWith('58')) {
        numero = '58' + numero;
    }
    
    // Construir el mensaje
    let mensaje = '';
    if (accion === 'rechazada') {
        mensaje = `Hola ${nombre}, tu solicitud de cita para el ${fecha} a las ${hora} NO pudo ser aceptada. Por favor, contáctanos para agendar en otro horario. - Gocho Barber`;
    } else if (accion === 'cancelada') {
        mensaje = `Hola ${nombre}, tu cita del ${fecha} a las ${hora} ha sido cancelada. Disculpa las molestias. Por favor, contáctanos para reagendar. - Gocho Barber`;
    } else {
        mensaje = `Hola ${nombre}, te escribimos de Gocho Barber por tu cita del ${fecha} a las ${hora}.`;
    }
    
    // Codificar el mensaje para URL
    const mensajeCod = encodeURIComponent(mensaje);
    
    // Abrir WhatsApp Web en nueva pestaña
    window.open(`https://wa.me/${numero}?text=${mensajeCod}`, '_blank');
}


// ===== ESTADÍSTICAS =====
let charts = {};

async function cargarEstadisticas() {
    try {
        const res = await fetch(`${API_URL}/api/admin/estadisticas`, { headers: getAuthHeaders() });
        if (res.status === 401) {
            mostrarToast('Sesión expirada', 'error');
            return;
        }
        const data = await res.json();
        if (data.error) {
            mostrarToast(data.error, 'error');
            return;
        }
        
        document.getElementById('statCitasMes').textContent = data.resumen.citas_mes_actual;
        document.getElementById('statCitasTotal').textContent = data.resumen.citas_totales;
        document.getElementById('statClientes').textContent = data.resumen.total_clientes;
        document.getElementById('statIngresos').textContent = '$' + Number(data.resumen.ingresos_totales).toLocaleString('es-CO');
        
        dibujarGraficoBarras('graficoCitas', data.citas_mes.etiquetas, data.citas_mes.valores, 'Citas');
        dibujarGraficoLineas('graficoIngresos', data.ingresos_mes.etiquetas, data.ingresos_mes.valores);
        dibujarGraficoDona('graficoBarberos', data.barberos.nombres, data.barberos.cantidades);
        dibujarTopClientes(data.clientes_top);
    } catch (e) {
        console.error('Error cargando estadísticas:', e);
        mostrarToast('Error al cargar estadísticas', 'error');
    }
}

async function cargarMisEstadisticas() {
    try {
        const res = await fetch(`${API_URL}/api/admin/estadisticas`, { headers: getAuthHeaders() });
        if (res.status === 401) {
            mostrarToast('Sesión expirada', 'error');
            return;
        }
        const data = await res.json();
        if (data.error) {
            mostrarToast(data.error, 'error');
            return;
        }
        
        document.getElementById('statMisCitasMes').textContent = data.resumen.citas_mes_actual;
        document.getElementById('statMisCitasTotal').textContent = data.resumen.citas_totales;
        document.getElementById('statMisClientes').textContent = data.resumen.total_clientes;
        document.getElementById('statMisIngresos').textContent = '$' + Number(data.resumen.ingresos_totales).toLocaleString('es-CO');
        
        dibujarGraficoBarras('graficoMisCitas', data.citas_mes.etiquetas, data.citas_mes.valores, 'Citas');
        dibujarGraficoLineas('graficoMisIngresos', data.ingresos_mes.etiquetas, data.ingresos_mes.valores);
        dibujarGraficoDona('graficoMisServicios', data.barberos.nombres, data.barberos.cantidades);
        dibujarTopClientes(data.clientes_top, 'topMisClientes');
    } catch (e) {
        console.error('Error cargando estadísticas:', e);
        mostrarToast('Error al cargar estadísticas', 'error');
    }
}

function dibujarGraficoBarras(id, etiquetas, valores, label) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: etiquetas,
            datasets: [{
                label: label,
                data: valores,
                backgroundColor: 'rgba(201, 168, 76, 0.6)',
                borderColor: '#c9a84c',
                borderWidth: 1,
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: '#8a7a6a', stepSize: 1 }
                },
                x: {
                    ticks: { color: '#8a7a6a' }
                }
            }
        }
    });
}

function dibujarGraficoLineas(id, etiquetas, valores) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: etiquetas,
            datasets: [{
                label: 'Ingresos (COP)',
                data: valores,
                borderColor: '#c9a84c',
                backgroundColor: 'rgba(201, 168, 76, 0.15)',
                tension: 0.3,
                fill: true,
                pointBackgroundColor: '#c9a84c',
                pointRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { 
                        color: '#8a7a6a',
                        callback: function(value) {
                            return '$' + Number(value).toLocaleString('es-CO');
                        }
                    }
                },
                x: {
                    ticks: { color: '#8a7a6a' }
                }
            }
        }
    });
}

function dibujarGraficoDona(id, nombres, cantidades) {
    const ctx = document.getElementById(id);
    if (!ctx) return;
    if (charts[id]) charts[id].destroy();
    
    const colores = [
        'rgba(201, 168, 76, 0.8)',
        'rgba(212, 184, 120, 0.8)',
        'rgba(139, 106, 26, 0.8)',
        'rgba(240, 213, 168, 0.8)',
        'rgba(106, 74, 42, 0.8)'
    ];
    
    charts[id] = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: nombres,
            datasets: [{
                data: cantidades,
                backgroundColor: colores,
                borderColor: '#1a1410',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#f0d5a8' }
                }
            }
        }
    });
}

function dibujarTopClientes(clientes, contenedorId = 'topClientes') {
    const cont = document.getElementById(contenedorId);
    if (!cont) return;
    if (!clientes || !clientes.length) {
        cont.innerHTML = '<div class="sin-datos-stats">Aún no hay datos de clientes</div>';
        return;
    }
    cont.innerHTML = clientes.map((c, i) => `
        <div class="cliente-top-item">
            <span>${i+1}. ${escaparHTML(c.nombre)}</span>
            <span class="cliente-top-citas">${c.total_citas} citas</span>
        </div>
    `).join('');
}


// ===== MODAL DE DETALLE =====
async function verDetalle(tipo) {
    const modal = document.getElementById('modal-detalle');
    const titulo = document.getElementById('detalle-titulo');
    const contenido = document.getElementById('detalle-contenido');
    
    titulo.textContent = 'Cargando...';
    contenido.innerHTML = '<div class="detalle-vacio">Cargando...</div>';
    modal.classList.add('activo');
    
    try {
        const res = await fetch(`${API_URL}/api/admin/estadisticas-detalle?tipo=${tipo}`, { headers: getAuthHeaders() });
        const data = await res.json();
        if (data.error) {
            contenido.innerHTML = `<div class="detalle-vacio">Error: ${data.error}</div>`;
            return;
        }
        titulo.textContent = data.titulo;
        
        if (!data.items || !data.items.length) {
            contenido.innerHTML = '<div class="detalle-vacio">No hay datos todavía</div>';
            return;
        }
        
        let html = '<table><thead><tr>';
        
        // Encabezados según tipo
        if (tipo === 'citas_mes' || tipo === 'citas_totales') {
            html += '<th>Fecha</th><th>Hora</th><th>Cliente</th><th>Servicio</th><th>Precio</th><th>Barbero</th>';
            html += '</tr></thead><tbody>';
            let total = 0;
            data.items.forEach(it => {
                html += `<tr>
                    <td>${escaparHTML(it.fecha || '')}</td>
                    <td>${escaparHTML(it.hora_inicio || '')}</td>
                    <td>${escaparHTML(it.cliente || '')}</td>
                    <td>${escaparHTML(it.servicio || '')}</td>
                    <td>$${Number(it.precio || 0).toLocaleString('es-CO')}</td>
                    <td>${escaparHTML(it.barbero || '')}</td>
                </tr>`;
                total += Number(it.precio || 0);
            });
            html += `<tr class="total-line"><td colspan="4"><strong>TOTAL</strong></td><td colspan="2"><strong>$${total.toLocaleString('es-CO')}</strong></td></tr>`;
        } else if (tipo === 'clientes') {
            html += '<th>Cliente</th><th>Teléfono</th><th>Citas</th><th>Total gastado</th>';
            html += '</tr></thead><tbody>';
            data.items.forEach(it => {
                html += `<tr>
                    <td>${escaparHTML(it.nombre || '')}</td>
                    <td>${escaparHTML(it.telefono || 'N/A')}</td>
                    <td>${it.total_citas}</td>
                    <td>$${Number(it.total_gastado || 0).toLocaleString('es-CO')}</td>
                </tr>`;
            });
        } else if (tipo === 'ingresos') {
            html += '<th>Servicio</th><th>Cantidad</th><th>Total</th>';
            html += '</tr></thead><tbody>';
            let total = 0;
            data.items.forEach(it => {
                html += `<tr>
                    <td>${escaparHTML(it.servicio || '')}</td>
                    <td>${it.cantidad}</td>
                    <td>$${Number(it.total || 0).toLocaleString('es-CO')}</td>
                </tr>`;
                total += Number(it.total || 0);
            });
            html += `<tr class="total-line"><td colspan="2"><strong>TOTAL</strong></td><td><strong>$${total.toLocaleString('es-CO')}</strong></td></tr>`;
        }
        
        html += '</tbody></table>';
        contenido.innerHTML = html;
    } catch (e) {
        console.error('Error cargando detalle:', e);
        contenido.innerHTML = '<div class="detalle-vacio">Error al cargar</div>';
    }
}

function cerrarModalDetalle() {
    document.getElementById('modal-detalle').classList.remove('activo');
}

window.verDetalle = verDetalle;
window.cerrarModalDetalle = cerrarModalDetalle;
window.cargarMisEstadisticas = cargarMisEstadisticas;
window.cargarEstadisticas = cargarEstadisticas;
window.avisarPorWhatsApp = avisarPorWhatsApp;
window.reactivarBarbero = reactivarBarbero;
window.toggleCamposPausa = toggleCamposPausa;
window.toggleModo = toggleModo;
window.mostrarToast = mostrarToast;
window.mostrarConfirmacion = mostrarConfirmacion;
window.cerrarModal = cerrarModal;
window.cambiarVista = cambiarVista;
window.cambiarTabCliente = cambiarTabCliente;
window.cambiarTabBarbero = cambiarTabBarbero;
window.cargarHuecos = cargarHuecos;
window.reservar = reservar;
window.consultarCitas = consultarCitas;
window.cancelarCita = cancelarCita;
window.solicitarModificacion = solicitarModificacion;
window.loginUsuario = loginUsuario;
window.logoutBarbero = logoutBarbero;
window.cargarPendientes = cargarPendientes;
window.confirmarCita = confirmarCita;
window.rechazarCita = rechazarCita;
window.cargarHistorial = cargarHistorial;
window.cancelarCitaConfirmada = cancelarCitaConfirmada;
window.eliminarCitaPermanente = eliminarCitaPermanente;
window.abrirFormBarbero = abrirFormBarbero;
window.cerrarFormBarbero = cerrarFormBarbero;
window.guardarBarbero = guardarBarbero;
window.editarBarbero = editarBarbero;
window.desactivarBarbero = desactivarBarbero;
window.eliminarBarberoPermanente = eliminarBarberoPermanente;
window.abrirFormServicio = abrirFormServicio;
window.cerrarFormServicio = cerrarFormServicio;
window.guardarServicio = guardarServicio;
window.editarServicio = editarServicio;
window.toggleServicioActivo = toggleServicioActivo;
window.eliminarServicio = eliminarServicio;
window.cargarServiciosAdmin = cargarServiciosAdmin;
window.abrirFormItem = abrirFormItem;
window.cerrarFormItem = cerrarFormItem;
window.guardarItem = guardarItem;
window.editarItem = editarItem;
window.toggleItemActivo = toggleItemActivo;
window.eliminarItem = eliminarItem;
window.bloquearDias = bloquearDias;
window.alCambiarBarbero = alCambiarBarbero;