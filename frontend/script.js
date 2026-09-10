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

// ===== PRODUCTOS Y ESTILOS =====
async function cargarProductos() {
    const contenedor = document.getElementById('productosContainer');
    if (!contenedor) return;
    contenedor.innerHTML = '<div class="sin-huecos">Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/catalogo`);
        const items = await res.json();
        const productos = items.filter(i => i.tipo === 'producto');
        contenedor.innerHTML = '';
        if (!productos.length) {
            contenedor.innerHTML = '<div class="sin-huecos">No hay productos.</div>';
            return;
        }
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
        console.error('Error:', error);
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
        if (!estilos.length) {
            contenedor.innerHTML = '<div class="sin-huecos">No hay estilos.</div>';
            return;
        }
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
        console.error('Error:', error);
        contenedor.innerHTML = '<div class="sin-huecos">Error al cargar.</div>';
    }
}

// ===== AUTENTICACIÓN =====
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
    
    // Forzar visibilidad de tabs solo-admin
    document.querySelectorAll('.solo-admin').forEach(el => {
        if (admin) {
            el.style.setProperty('display', 'inline-block', 'important');
        } else {
            el.style.setProperty('display', 'none', 'important');
        }
    });
    
    const tabConfig = document.querySelector('#tabsBarbero button:last-child');
    if (tabConfig) tabConfig.textContent = admin ? 'Configuracion' : 'Bloquear dias';
    
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
    if (tab === 'pendientes') { b[0].classList.add('activo'); document.getElementById('tabPendientes').style.display = 'block'; cargarPendientes(); }
    else if (tab === 'historial') { b[1].classList.add('activo'); document.getElementById('tabHistorial').style.display = 'block'; cargarHistorial(); }
    else if (tab === 'barberos') {
        if (!esAdmin()) { alert('Solo admin'); return; }
        b[2].classList.add('activo'); document.getElementById('tabBarberos').style.display = 'block';
        cargarBarberos(); cargarBarberosSelectorAdmin();
    }
    else if (tab === 'catalogo') {
        if (!esAdmin()) { alert('Solo admin'); return; }
        b[3].classList.add('activo'); document.getElementById('tabCatalogo').style.display = 'block';
        cargarCatalogoAdmin();
    }
    else if (tab === 'configuracion') {
        b[4].classList.add('activo'); document.getElementById('tabConfiguracion').style.display = 'block';
        cargarBarberosSelectorAdmin();
    }
}

// ===== RESERVAR =====
async function cargarHuecos() {
    const fecha = document.getElementById('fecha').value;
    const barberoId = document.getElementById('barbero').value || 0;
    if (!fecha) { alert('Selecciona fecha'); return; }
    const c = document.getElementById('huecos');
    c.innerHTML = '<div class="sin-huecos">Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/disponibilidad?fecha=${encodeURIComponent(fecha)}&barbero_id=${barberoId}`);
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
    if (!tel) { alert('Ingresa teléfono'); return; }
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
            const ec = ct.estado === 'confirmada' ? 'estado-confirmada' : 'estado-pendiente';
            const et = ct.estado === 'confirmada' ? 'Confirmada' : 'Pendiente';
            div.innerHTML = `
                <div class="info">
                    <div class="fecha-hora">${escaparHTML(ct.fecha)} - ${escaparHTML(ct.hora_inicio)}</div>
                    <div class="servicio">${escaparHTML(ct.servicio)}</div>
                    <div class="barbero-info">Barbero: ${escaparHTML(ct.barbero || 'N/A')}</div>
                </div>
                <div><span class="estado ${ec}">${et}</span></div>
                <div class="acciones">
                    <button class="btn-cancelar" onclick="cancelarCita(${ct.id})">Cancelar</button>
                    <button class="btn-modificar" onclick="solicitarModificacion(${ct.id})">Modificar</button>
                </div>
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
        alert(data.mensaje || data.error);
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
        alert(data.mensaje || data.error);
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
    if (!confirm('¿Rechazar?')) return;
    try {
        const res = await fetch(`${API_URL}/api/panel/rechazar-cita`, {
            method: 'POST', headers: getAuthHeaders(),
            body: JSON.stringify({ cita_id: id })
        });
        const d = await res.json();
        alert(d.mensaje || d.error);
        cargarPendientes();
    } catch (e) { alert('Error.'); }
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
    if (!confirm('¿Cancelar?')) return;
    try {
        const res = await fetch(`${API_URL}/api/panel/cancelar-cita-confirmada`, {
            method: 'POST', headers: getAuthHeaders(),
            body: JSON.stringify({ cita_id: id })
        });
        const d = await res.json();
        alert(d.mensaje || d.error);
        if (res.ok) cargarHistorial();
    } catch (e) { alert('Error.'); }
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
    document.querySelectorAll('.dia-check').forEach(c => c.checked = true);
    document.getElementById('mensajeBarbero').style.display = 'none';
}

function cerrarFormBarbero() { document.getElementById('formBarbero').style.display = 'none'; }

async function guardarBarbero() {
    const id = document.getElementById('barberoEditId').value;
    const nombre = document.getElementById('barberoNombre').value.trim();
    if (!nombre) { alert('Nombre obligatorio'); return; }
    const dias = Array.from(document.querySelectorAll('.dia-check:checked')).map(c => c.value);
    if (!dias.length) { alert('Selecciona días'); return; }
    const body = {
        nombre,
        telefono: document.getElementById('barberoTelefono').value.trim(),
        email: document.getElementById('barberoEmail').value.trim(),
        dias_trabajo: dias
    };
    const url = id ? `${API_URL}/api/admin/barberos/${id}` : `${API_URL}/api/admin/barberos`;
    const method = id ? 'PUT' : 'POST';
    try {
        const res = await fetch(url, { method, headers: getAuthHeaders(), body: JSON.stringify(body) });
        const d = await res.json();
        const msg = document.getElementById('mensajeBarbero');
        msg.className = 'mensaje ' + (res.ok ? 'exito' : 'error');
        msg.textContent = d.mensaje || d.error;
        msg.style.display = 'block';
        if (res.ok) {
            setTimeout(() => {
                cerrarFormBarbero();
                cargarBarberos();
                cargarBarberosSelectorAdmin();
                cargarBarberosSelectorCliente();
            }, 2500);
        }
    } catch (e) { alert('Error.'); }
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
            let botones = '';
            if (esAdmin()) {
                botones = `
                    <button class="btn-modificar" onclick="editarBarbero(${b.id})">Editar</button>
                    ${b.activo ? `<button class="btn-danger" onclick="desactivarBarbero(${b.id})">Desactivar</button>` : ''}
                    <button class="btn-danger" style="background:#5a1a1a;" onclick="eliminarBarberoPermanente(${b.id})">🗑️ Eliminar</button>
                `;
            }
            div.innerHTML = `
                <div class="info">
                    <div class="fecha-hora">${escaparHTML(b.nombre)}</div>
                    <div class="cliente">${escaparHTML(b.telefono || 'Sin tel')} - ${escaparHTML(b.email || 'Sin email')}</div>
                    <div class="barbero-info">Estado: ${b.activo ? 'Activo' : 'Inactivo'}</div>
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
        let dias = [];
        try { dias = JSON.parse(b.dias_trabajo); } catch (e) {}
        document.querySelectorAll('.dia-check').forEach(c => c.checked = dias.includes(c.value));
        document.getElementById('formBarbero').style.display = 'block';
        document.getElementById('formBarbero').scrollIntoView({ behavior: 'smooth' });
    } catch (e) { alert('Error.'); }
}

async function desactivarBarbero(id) {
    if (!confirm('¿Desactivar? Se cancelarán sus citas futuras.')) return;
    try {
        const res = await fetch(`${API_URL}/api/admin/barberos/${id}`, {
            method: 'DELETE', headers: getAuthHeaders()
        });
        const d = await res.json();
        alert(d.mensaje || d.error);
        if (res.ok) { cargarBarberos(); cargarBarberosSelectorAdmin(); cargarBarberosSelectorCliente(); }
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
        if (res.ok) { cargarBarberos(); cargarBarberosSelectorAdmin(); cargarBarberosSelectorCliente(); }
    } catch (e) { alert('Error.'); }
}

async function cargarBarberosSelectorCliente() {
    try {
        const res = await fetch(`${API_URL}/api/barberos`);
        const bs = await res.json();
        const sel = document.getElementById('barbero');
        if (!sel) return;
        const val = sel.value;
        sel.innerHTML = '<option value="0">Cualquiera disponible</option>';
        bs.forEach(b => {
            const o = document.createElement('option');
            o.value = b.id; o.textContent = b.nombre;
            sel.appendChild(o);
        });
        if (val) sel.value = val;
    } catch (e) {}
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

// ===== INICIALIZACIÓN =====
document.addEventListener('DOMContentLoaded', function() {
    cargarSesion();
    actualizarUISegunRol();  // ← NUEVA LÍNEA
    try {
        const f = new Date(); f.setDate(f.getDate() + 1);
        const fStr = f.toISOString().split('T')[0];
        const h = new Date();
        const hStr = h.toISOString().split('T')[0];
        const iF = document.getElementById('fecha');
        if (iF) { iF.value = fStr; iF.min = hStr; }
        const iI = document.getElementById('bloqueoInicio');
        const iFn = document.getElementById('bloqueoFin');
        if (iI) { iI.value = hStr; iI.min = hStr; }
        if (iFn) { iFn.value = hStr; iFn.min = hStr; }
    } catch (e) {}
    cargarBarberosSelectorCliente();
});

// ===== EXPORTAR AL GLOBAL =====
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
window.abrirFormItem = abrirFormItem;
window.cerrarFormItem = cerrarFormItem;
window.guardarItem = guardarItem;
window.editarItem = editarItem;
window.toggleItemActivo = toggleItemActivo;
window.eliminarItem = eliminarItem;
window.bloquearDias = bloquearDias;