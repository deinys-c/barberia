'use strict';

// ===== CONFIGURACIÓN =====
const API_URL = 'https://gochobarber.onrender.com';
let horaSeleccionada = null;
let currentUser = null;

// ===== DATOS ESTÁTICOS =====
const productos = [
    { nombre: 'Cera Modeladora', descripcion: 'Fijacion media, acabado mate', precio: '$35.000 COP', imagen: 'imagenes/productos/cera.jpg' },
    { nombre: 'Bruma Capilar', descripcion: 'Hidratacion y brillo natural', precio: '$28.000 COP', imagen: 'imagenes/productos/bruma.jpg' },
    { nombre: 'Aceite de Barba', descripcion: 'Suaviza y nutre la barba', precio: '$32.000 COP', imagen: 'imagenes/productos/aceite.jpg' },
    { nombre: 'Shampoo Solido', descripcion: 'Limpieza profunda sin quimicos', precio: '$25.000 COP', imagen: 'imagenes/productos/shampoo.jpg' },
    { nombre: 'Pomada Clasica', descripcion: 'Fijacion fuerte, brillo intenso', precio: '$30.000 COP', imagen: 'imagenes/productos/pomada.jpg' }
];

const estilos = [
    { nombre: 'Corte Clasico', imagen: 'imagenes/cortes/clasico.jpg' },
    { nombre: 'Fade Moderno', imagen: 'imagenes/cortes/fade.jpg' },
    { nombre: 'Corte Militar', imagen: 'imagenes/cortes/militar.jpg' },
    { nombre: 'Pompadour', imagen: 'imagenes/cortes/pompadour.jpg' },
    { nombre: 'Corte Texturizado', imagen: 'imagenes/cortes/texturizado.jpg' },
    { nombre: 'Barba Perfilada', imagen: 'imagenes/cortes/barba.jpg' }
];

// ===== UTILIDADES =====
function escaparHTML(texto) {
    if (texto === null || texto === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(texto);
    return div.innerHTML;
}

/**
 * Fallback de imagen: genera un SVG en memoria (sin petición de red)
 * para evitar el "marco gris titilando" cuando la imagen no existe.
 */
function imgFallback(nombre, tipo) {
    // tipo: 'producto' o 'corte'
    const ancho = tipo === 'producto' ? 200 : 150;
    const alto = tipo === 'producto' ? 150 : 150;
    const texto = encodeURIComponent(nombre || 'Imagen');
    return `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="${ancho}" height="${alto}" viewBox="0 0 ${ancho} ${alto}"><rect fill="%232c1a12" width="${ancho}" height="${alto}"/><text x="50%" y="50%" fill="%23c9a84c" font-family="Segoe UI, sans-serif" font-size="14" text-anchor="middle" dominant-baseline="middle">${texto}</text></svg>`;
}

window.imgError = function(img, nombre, tipo) {
    img.onerror = null;
    img.src = imgFallback(nombre, tipo);
};

// ===== PRODUCTOS Y ESTILOS =====
function cargarProductos() {
    const contenedor = document.getElementById('productosContainer');
    if (!contenedor) return;
    contenedor.innerHTML = '';
    productos.forEach(p => {
        const card = document.createElement('div');
        card.className = 'producto-card';
        const nombreSeguro = escaparHTML(p.nombre);
        card.innerHTML = `
            <img src="${p.imagen}" alt="${nombreSeguro}" onerror="imgError(this, '${nombreSeguro.replace(/'/g, '')}', 'producto')">
            <div class="nombre">${nombreSeguro}</div>
            <div class="descripcion">${escaparHTML(p.descripcion)}</div>
            <div class="precio">${escaparHTML(p.precio)}</div>
        `;
        contenedor.appendChild(card);
    });
}

function cargarEstilos() {
    const contenedor = document.getElementById('estilosContainer');
    if (!contenedor) return;
    contenedor.innerHTML = '';
    estilos.forEach(e => {
        const card = document.createElement('div');
        card.className = 'estilo-card';
        const nombreSeguro = escaparHTML(e.nombre);
        card.innerHTML = `
            <img src="${e.imagen}" alt="${nombreSeguro}" onerror="imgError(this, '${nombreSeguro.replace(/'/g, '')}', 'corte')">
            <div class="nombre">${nombreSeguro}</div>
        `;
        contenedor.appendChild(card);
    });
}

// ===== AUTENTICACIÓN =====
function getAuthHeaders() {
    const headers = { 'Content-Type': 'application/json', 'Accept': 'application/json' };
    if (currentUser && currentUser.username) {
        headers['X-Username'] = currentUser.username;
    }
    return headers;
}

function guardarSesion(user) {
    currentUser = user;
    try { localStorage.setItem('currentUser', JSON.stringify(user)); } catch (e) {}
}

function cargarSesion() {
    try {
        const guardado = localStorage.getItem('currentUser');
        if (guardado) currentUser = JSON.parse(guardado);
    } catch (e) { currentUser = null; }
}

function cerrarSesion() {
    currentUser = null;
    try { localStorage.removeItem('currentUser'); } catch (e) {}
}

function actualizarUISegunRol() {
    const esAdmin = currentUser && currentUser.rol === 'admin';
    
    document.querySelectorAll('.solo-admin').forEach(el => {
        el.style.display = esAdmin ? 'inline-block' : 'none';
    });
    
    const tabConfig = document.querySelector('#tabsBarbero button:nth-child(4)');
    if (tabConfig) {
        tabConfig.textContent = esAdmin ? 'Configuracion' : 'Bloquear dias';
    }
    
    const filtrosP = document.getElementById('filtrosPendientes');
    const filtrosH = document.getElementById('filtrosHistorial');
    const filaSel = document.getElementById('filaSelectorBloqueo');
    
    if (esAdmin) {
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
    if (infoUser && currentUser) {
        infoUser.textContent = `(${currentUser.username} - ${currentUser.rol})`;
    }
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
            msg.textContent = data.error || 'Error de login';
        }
    } catch (error) {
        console.error('Error en login:', error);
        msg.className = 'mensaje error';
        msg.textContent = 'Error al conectar con el servidor.';
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

// ===== CAMBIAR VISTA =====
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

// ===== TABS CLIENTE =====
function cambiarTabCliente(tab) {
    document.querySelectorAll('#tabsCliente button').forEach(b => b.classList.remove('activo'));
    document.querySelectorAll('#panelCliente .panel-tab').forEach(p => p.style.display = 'none');
    const botones = document.querySelectorAll('#tabsCliente button');
    if (tab === 'reservar') {
        botones[0].classList.add('activo');
        document.getElementById('tabReservar').style.display = 'block';
    } else if (tab === 'mis-citas') {
        botones[1].classList.add('activo');
        document.getElementById('tabMisCitas').style.display = 'block';
    } else if (tab === 'productos') {
        botones[2].classList.add('activo');
        document.getElementById('tabProductos').style.display = 'block';
        cargarProductos();
    } else if (tab === 'estilos') {
        botones[3].classList.add('activo');
        document.getElementById('tabEstilos').style.display = 'block';
        cargarEstilos();
    }
}

// ===== TABS PANEL =====
function cambiarTabBarbero(tab) {
    document.querySelectorAll('#tabsBarbero button').forEach(b => b.classList.remove('activo'));
    document.querySelectorAll('#barberoContenido .panel-tab').forEach(p => p.style.display = 'none');
    const botones = document.querySelectorAll('#tabsBarbero button');
    if (tab === 'pendientes') {
        botones[0].classList.add('activo');
        document.getElementById('tabPendientes').style.display = 'block';
        cargarPendientes();
    } else if (tab === 'historial') {
        botones[1].classList.add('activo');
        document.getElementById('tabHistorial').style.display = 'block';
        cargarHistorial();
    } else if (tab === 'barberos') {
        if (!currentUser || currentUser.rol !== 'admin') {
            alert('Solo el administrador puede gestionar barberos');
            return;
        }
        botones[2].classList.add('activo');
        document.getElementById('tabBarberos').style.display = 'block';
        cargarBarberos();
        cargarBarberosSelectorAdmin();
    } else if (tab === 'configuracion') {
        botones[3].classList.add('activo');
        document.getElementById('tabConfiguracion').style.display = 'block';
        cargarBarberosSelectorAdmin();
    }
}

// ===== RESERVAR =====
async function cargarHuecos() {
    const fecha = document.getElementById('fecha').value;
    const barberoId = document.getElementById('barbero').value || 0;
    if (!fecha) { alert('Selecciona una fecha'); return; }
    const contenedor = document.getElementById('huecos');
    contenedor.innerHTML = '<div class="sin-huecos">Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/disponibilidad?fecha=${encodeURIComponent(fecha)}&barbero_id=${barberoId}`);
        if (!res.ok) throw new Error('Error en la respuesta del servidor');
        const data = await res.json();
        contenedor.innerHTML = '';
        if (data.disponibles && data.disponibles.length > 0) {
            const horasUnicas = [...new Set(data.disponibles)];
            horasUnicas.forEach(h => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.textContent = h;
                btn.onclick = () => {
                    document.querySelectorAll('#huecos button').forEach(b => b.classList.remove('seleccionado'));
                    btn.classList.add('seleccionado');
                    horaSeleccionada = h;
                    document.getElementById('formReserva').style.display = 'block';
                };
                contenedor.appendChild(btn);
            });
        } else {
            contenedor.innerHTML = '<div class="sin-huecos">No hay horas disponibles para este dia.</div>';
        }
    } catch (error) {
        console.error('Error cargando huecos:', error);
        contenedor.innerHTML = '<div class="sin-huecos">Error al cargar horas disponibles.</div>';
    }
}

async function reservar() {
    const fecha = document.getElementById('fecha').value;
    const servicio = document.getElementById('servicio').value;
    const barberoId = parseInt(document.getElementById('barbero').value) || 0;
    const nombre = document.getElementById('nombre').value.trim();
    const telefono = document.getElementById('telefono').value.trim();
    const notas = document.getElementById('notas').value.trim();

    if (!nombre) { alert('El nombre es obligatorio'); return; }
    if (nombre.length < 2) { alert('El nombre debe tener al menos 2 caracteres'); return; }
    if (!horaSeleccionada) { alert('Selecciona una hora'); return; }
    if (!fecha) { alert('Selecciona una fecha'); return; }

    try {
        const [year, month, day] = fecha.split('-').map(Number);
        const [hora, minuto] = horaSeleccionada.split(':').map(Number);
        const fechaCita = new Date(year, month - 1, day, hora, minuto);
        if (fechaCita < new Date()) {
            alert('No se pueden hacer reservas en el pasado');
            return;
        }
    } catch (e) {
        alert('Fecha u hora inválida');
        return;
    }

    const body = {
        fecha,
        hora_inicio: horaSeleccionada,
        servicio_id: parseInt(servicio),
        barbero_id: barberoId,
        nombre,
        telefono,
        notas
    };

    const msg = document.getElementById('mensajeReserva');
    msg.className = 'mensaje info';
    msg.textContent = 'Procesando reserva...';
    msg.style.display = 'block';

    try {
        const res = await fetch(`${API_URL}/api/reservar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
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
    } catch (error) {
        console.error('Error reservando:', error);
        msg.className = 'mensaje error';
        msg.textContent = 'Error al conectar con el servidor.';
    }
}

// ===== MIS CITAS =====
async function consultarCitas() {
    const telefono = document.getElementById('telefonoConsulta').value.trim();
    if (!telefono) { alert('Ingresa tu telefono'); return; }
    const cont = document.getElementById('misCitas');
    cont.innerHTML = '<div class="sin-huecos">Buscando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/mis-citas?telefono=${encodeURIComponent(telefono)}`);
        if (!res.ok) throw new Error('Error en la respuesta');
        const citas = await res.json();
        cont.innerHTML = '';
        if (!citas || !citas.length) {
            cont.innerHTML = '<div class="sin-huecos">No tienes citas proximas.</div>';
            return;
        }
        citas.forEach(c => {
            const div = document.createElement('div');
            div.className = 'cita-item';
            const estadoClase = c.estado === 'confirmada' ? 'estado-confirmada' : 'estado-pendiente';
            const estadoTexto = c.estado === 'confirmada' ? 'Confirmada' : 'Pendiente';
            const alerta = c.alerta_cierre ? '<span class="alerta-cierre">Extiende horario</span>' : '';
            const barberoInfo = c.barbero ? `<div class="barbero-info">Barbero: ${escaparHTML(c.barbero)}</div>` : '';
            div.innerHTML = `
                <div class="info">
                    <div class="fecha-hora">${escaparHTML(c.fecha)} - ${escaparHTML(c.hora_inicio)} ${alerta}</div>
                    <div class="servicio">${escaparHTML(c.servicio)}</div>
                    ${barberoInfo}
                </div>
                <div><span class="estado ${estadoClase}">${estadoTexto}</span></div>
                <div class="acciones">
                    <button class="btn-cancelar" onclick="cancelarCita(${c.id})">Cancelar</button>
                    <button class="btn-modificar" onclick="solicitarModificacion(${c.id})">Modificar</button>
                </div>
            `;
            cont.appendChild(div);
        });
    } catch (error) {
        console.error('Error consultando citas:', error);
        cont.innerHTML = '<div class="sin-huecos">Error al consultar citas.</div>';
    }
}

async function cancelarCita(citaId) {
    if (!confirm('¿Cancelar esta cita?')) return;
    try {
        const res = await fetch(`${API_URL}/api/cancelar-cita`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cita_id: citaId })
        });
        const data = await res.json();
        alert(data.mensaje || data.error);
        if (res.ok) consultarCitas();
    } catch (error) {
        console.error('Error cancelando cita:', error);
        alert('Error al conectar con el servidor.');
    }
}

async function solicitarModificacion(citaId) {
    const nuevaFecha = prompt('Nueva fecha (YYYY-MM-DD):');
    if (!nuevaFecha) return;
    const nuevaHora = prompt('Nueva hora (HH:MM):');
    if (!nuevaHora) return;
    try {
        const res = await fetch(`${API_URL}/api/solicitar-modificacion`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cita_original_id: citaId, nueva_fecha: nuevaFecha, nueva_hora: nuevaHora })
        });
        const data = await res.json();
        alert(data.mensaje || data.error);
        if (res.ok) consultarCitas();
    } catch (error) {
        console.error('Error solicitando modificacion:', error);
        alert('Error al conectar con el servidor.');
    }
}

// ===== PENDIENTES =====
async function cargarPendientes() {
    const cont = document.getElementById('pendientesLista');
    if (!cont) return;
    const barberoId = document.getElementById('filtroBarberoPendientes')?.value || 0;
    cont.innerHTML = '<div class="sin-huecos">Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/panel/pendientes?barbero_id=${barberoId}`, { headers: getAuthHeaders() });
        if (res.status === 401) {
            alert('Sesion expirada. Vuelve a iniciar sesion.');
            cerrarSesion();
            document.getElementById('barberoLogin').style.display = 'block';
            document.getElementById('barberoContenido').style.display = 'none';
            return;
        }
        if (!res.ok) throw new Error('Error en la respuesta');
        const citas = await res.json();
        cont.innerHTML = '';
        if (!citas || !citas.length) {
            cont.innerHTML = '<div class="sin-huecos">No hay solicitudes pendientes.</div>';
            return;
        }
        citas.forEach(c => {
            const div = document.createElement('div');
            div.className = 'cita-item';
            const alerta = c.alerta_cierre ? '<span class="alerta-cierre">Extiende horario</span>' : '';
            div.innerHTML = `
                <div class="info">
                    <div class="fecha-hora">${escaparHTML(c.fecha)} - ${escaparHTML(c.hora_inicio)} ${alerta}</div>
                    <div class="servicio">${escaparHTML(c.servicio)} (${escaparHTML(c.tipo_reserva)})</div>
                    <div class="cliente">Cliente: ${escaparHTML(c.cliente)} - ${escaparHTML(c.telefono || 'N/A')}</div>
                    <div class="barbero-info">Barbero: ${escaparHTML(c.barbero || 'N/A')}</div>
                    ${c.notas_cliente ? `<div class="cliente">Notas: ${escaparHTML(c.notas_cliente)}</div>` : ''}
                </div>
                <div><span class="estado estado-pendiente">Pendiente</span></div>
                <div class="acciones">
                    <button class="btn-confirmar" onclick="confirmarCita(${c.id})">Aceptar</button>
                    <button class="btn-rechazar" onclick="rechazarCita(${c.id})">Rechazar</button>
                </div>
            `;
            cont.appendChild(div);
        });
    } catch (error) {
        console.error('Error cargando pendientes:', error);
        cont.innerHTML = '<div class="sin-huecos">Error al cargar pendientes.</div>';
    }
}

async function confirmarCita(citaId) {
    if (!confirm('¿Confirmar esta cita?')) return;
    try {
        const res = await fetch(`${API_URL}/api/panel/confirmar-cita`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ cita_id: citaId })
        });
        const data = await res.json();
        alert(data.mensaje || data.error);
        cargarPendientes();
    } catch (error) {
        console.error('Error confirmando cita:', error);
        alert('Error al conectar con el servidor.');
    }
}

async function rechazarCita(citaId) {
    if (!confirm('¿Rechazar esta cita?')) return;
    try {
        const res = await fetch(`${API_URL}/api/panel/rechazar-cita`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ cita_id: citaId })
        });
        const data = await res.json();
        alert(data.mensaje || data.error);
        cargarPendientes();
    } catch (error) {
        console.error('Error rechazando cita:', error);
        alert('Error al conectar con el servidor.');
    }
}

// ===== HISTORIAL =====
async function cargarHistorial() {
    const cont = document.getElementById('historialLista');
    if (!cont) return;
    const barberoId = document.getElementById('filtroBarberoHistorial')?.value || 0;
    cont.innerHTML = '<div class="sin-huecos">Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/panel/historial?barbero_id=${barberoId}`, { headers: getAuthHeaders() });
        if (res.status === 401) {
            alert('Sesion expirada. Vuelve a iniciar sesion.');
            cerrarSesion();
            document.getElementById('barberoLogin').style.display = 'block';
            document.getElementById('barberoContenido').style.display = 'none';
            return;
        }
        if (!res.ok) throw new Error('Error en la respuesta');
        const citas = await res.json();
        cont.innerHTML = '';
        if (!citas || !citas.length) {
            cont.innerHTML = '<div class="sin-huecos">No hay citas registradas.</div>';
            return;
        }
        const estados = {
            'confirmada': { clase: 'estado-confirmada', texto: 'Confirmada' },
            'pendiente_confirmacion': { clase: 'estado-pendiente', texto: 'Pendiente' },
            'realizada': { clase: 'estado-realizada', texto: 'Realizada' },
            'expirada': { clase: 'estado-expirada', texto: 'Expirada' },
            'cancelada_por_cliente': { clase: 'estado-expirada', texto: 'Cancelada (Cliente)' },
            'cancelada_por_barbero': { clase: 'estado-expirada', texto: 'Cancelada (Barbero)' },
            'cancelada_por_sistema': { clase: 'estado-expirada', texto: 'Cancelada (Sistema)' }
        };
        citas.forEach(c => {
            const div = document.createElement('div');
            div.className = 'cita-item';
            const estado = estados[c.estado] || { clase: 'estado-pendiente', texto: c.estado };
            let botonCancelar = '';
            if (c.estado === 'confirmada') {
                botonCancelar = `<button class="btn-danger" onclick="cancelarCitaConfirmada(${c.id})">Cancelar</button>`;
            }
            div.innerHTML = `
                <div class="info">
                    <div class="fecha-hora">${escaparHTML(c.fecha)} - ${escaparHTML(c.hora_inicio)}</div>
                    <div class="servicio">${escaparHTML(c.servicio)} - ${escaparHTML(c.cliente)}</div>
                    <div class="barbero-info">Barbero: ${escaparHTML(c.barbero || 'N/A')}</div>
                </div>
                <div><span class="estado ${estado.clase}">${estado.texto}</span></div>
                <div class="acciones">${botonCancelar}</div>
            `;
            cont.appendChild(div);
        });
    } catch (error) {
        console.error('Error cargando historial:', error);
        cont.innerHTML = '<div class="sin-huecos">Error al cargar historial.</div>';
    }
}

async function cancelarCitaConfirmada(citaId) {
    if (!confirm('¿Cancelar esta cita confirmada? El cliente sera notificado.')) return;
    try {
        const res = await fetch(`${API_URL}/api/panel/cancelar-cita-confirmada`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ cita_id: citaId })
        });
        const data = await res.json();
        alert(data.mensaje || data.error);
        if (res.ok) cargarHistorial();
    } catch (error) {
        console.error('Error cancelando cita:', error);
        alert('Error al conectar con el servidor.');
    }
}

// ===== GESTIÓN BARBEROS =====
function abrirFormBarbero() {
    document.getElementById('formBarbero').style.display = 'block';
    document.getElementById('barberoEditId').value = '';
    document.getElementById('barberoNombre').value = '';
    document.getElementById('barberoTelefono').value = '';
    document.getElementById('barberoEmail').value = '';
    document.querySelectorAll('.dia-check').forEach(c => c.checked = true);
    const msg = document.getElementById('mensajeBarbero');
    msg.style.display = 'none';
}

function cerrarFormBarbero() {
    document.getElementById('formBarbero').style.display = 'none';
}

async function guardarBarbero() {
    const id = document.getElementById('barberoEditId').value;
    const nombre = document.getElementById('barberoNombre').value.trim();
    if (!nombre) { alert('El nombre es obligatorio'); return; }
    if (nombre.length < 2) { alert('El nombre debe tener al menos 2 caracteres'); return; }
    const dias = Array.from(document.querySelectorAll('.dia-check:checked')).map(c => c.value);
    if (dias.length === 0) { alert('Selecciona al menos un dia de trabajo'); return; }
    
    const body = {
        nombre,
        telefono: document.getElementById('barberoTelefono').value.trim(),
        email: document.getElementById('barberoEmail').value.trim(),
        dias_trabajo: dias
    };
    const url = id ? `${API_URL}/api/admin/barberos/${id}` : `${API_URL}/api/admin/barberos`;
    const method = id ? 'PUT' : 'POST';
    try {
        const res = await fetch(url, {
            method,
            headers: getAuthHeaders(),
            body: JSON.stringify(body)
        });
        const data = await res.json();
        const msg = document.getElementById('mensajeBarbero');
        msg.className = 'mensaje ' + (res.ok ? 'exito' : 'error');
        msg.textContent = data.mensaje || data.error;
        msg.style.display = 'block';
        if (res.ok) {
            setTimeout(() => {
                cerrarFormBarbero();
                cargarBarberos();
                cargarBarberosSelectorAdmin();
                cargarBarberosSelectorCliente();
            }, 2500);
        }
    } catch (error) {
        console.error('Error guardando barbero:', error);
        alert('Error al conectar con el servidor.');
    }
}

async function cargarBarberos() {
    const cont = document.getElementById('listaBarberos');
    if (!cont) return;
    cont.innerHTML = '<div class="sin-huecos">Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/api/admin/barberos`, { headers: getAuthHeaders() });
        if (res.status === 401) {
            cont.innerHTML = '<div class="sin-huecos">Sesion expirada.</div>';
            return;
        }
        const barberos = await res.json();
        cont.innerHTML = '';
        if (!barberos || !barberos.length) {
            cont.innerHTML = '<div class="sin-huecos">No hay barberos registrados.</div>';
            return;
        }
        barberos.forEach(b => {
            const div = document.createElement('div');
            div.className = 'cita-item';
            div.innerHTML = `
                <div class="info">
                    <div class="fecha-hora">${escaparHTML(b.nombre)}</div>
                    <div class="cliente">${escaparHTML(b.telefono || 'Sin telefono')} - ${escaparHTML(b.email || 'Sin email')}</div>
                    <div class="barbero-info">Estado: ${b.activo ? 'Activo' : 'Inactivo'}</div>
                </div>
                <div class="acciones">
                    <button class="btn-modificar" onclick="editarBarbero(${b.id})">Editar</button>
                    ${b.activo ? `<button class="btn-danger" onclick="desactivarBarbero(${b.id})">Desactivar</button>` : ''}
                </div>
            `;
            cont.appendChild(div);
        });
    } catch (error) {
        console.error('Error cargando barberos:', error);
        cont.innerHTML = '<div class="sin-huecos">Error al cargar barberos.</div>';
    }
}

async function editarBarbero(id) {
    try {
        const res = await fetch(`${API_URL}/api/admin/barberos`, { headers: getAuthHeaders() });
        const barberos = await res.json();
        const b = barberos.find(x => x.id === id);
        if (!b) { alert('Barbero no encontrado'); return; }
        document.getElementById('barberoEditId').value = b.id;
        document.getElementById('barberoNombre').value = b.nombre || '';
        document.getElementById('barberoTelefono').value = b.telefono || '';
        document.getElementById('barberoEmail').value = b.email || '';
        let dias = [];
        try { dias = JSON.parse(b.dias_trabajo); } catch (e) { dias = []; }
        document.querySelectorAll('.dia-check').forEach(c => c.checked = dias.includes(c.value));
        document.getElementById('formBarbero').style.display = 'block';
        document.getElementById('formBarbero').scrollIntoView({ behavior: 'smooth' });
    } catch (error) {
        console.error('Error editando barbero:', error);
        alert('Error al cargar datos del barbero.');
    }
}

async function desactivarBarbero(id) {
    if (!confirm('¿Desactivar este barbero? Se cancelarán sus citas futuras.')) return;
    try {
        const res = await fetch(`${API_URL}/api/admin/barberos/${id}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        const data = await res.json();
        alert(data.mensaje || data.error);
        if (res.ok) {
            cargarBarberos();
            cargarBarberosSelectorAdmin();
            cargarBarberosSelectorCliente();
        }
    } catch (error) {
        console.error('Error desactivando barbero:', error);
        alert('Error al conectar con el servidor.');
    }
}

async function cargarBarberosSelectorCliente() {
    try {
        const res = await fetch(`${API_URL}/api/barberos`);
        const barberos = await res.json();
        const sel = document.getElementById('barbero');
        if (!sel) return;
        const valorActual = sel.value;
        sel.innerHTML = '<option value="0">Cualquiera disponible</option>';
        barberos.forEach(b => {
            const opt = document.createElement('option');
            opt.value = b.id;
            opt.textContent = b.nombre;
            sel.appendChild(opt);
        });
        if (valorActual) sel.value = valorActual;
    } catch (error) {
        console.error('Error cargando selector de barberos:', error);
    }
}

async function cargarBarberosSelectorAdmin() {
    try {
        const res = await fetch(`${API_URL}/api/admin/barberos`, { headers: getAuthHeaders() });
        if (res.status === 401) return;
        const barberos = await res.json();
        const activos = barberos.filter(b => b.activo);

        const filtroPend = document.getElementById('filtroBarberoPendientes');
        const filtroHist = document.getElementById('filtroBarberoHistorial');
        const bloqueoBarbero = document.getElementById('bloqueoBarbero');

        if (currentUser && currentUser.rol === 'admin') {
            [filtroPend, filtroHist].forEach(sel => {
                if (!sel) return;
                const val = sel.value;
                sel.innerHTML = '<option value="0">Todos los barberos</option>';
                activos.forEach(b => {
                    const opt = document.createElement('option');
                    opt.value = b.id;
                    opt.textContent = b.nombre;
                    sel.appendChild(opt);
                });
                if (val) sel.value = val;
            });

            if (bloqueoBarbero) {
                const val = bloqueoBarbero.value;
                bloqueoBarbero.innerHTML = '';
                activos.forEach(b => {
                    const opt = document.createElement('option');
                    opt.value = b.id;
                    opt.textContent = b.nombre;
                    bloqueoBarbero.appendChild(opt);
                });
                if (val) bloqueoBarbero.value = val;
            }
        }
    } catch (error) {
        console.error('Error cargando selectores admin:', error);
    }
}

// ===== BLOQUEAR DIAS =====
async function bloquearDias() {
    const inicio = document.getElementById('bloqueoInicio').value;
    const fin = document.getElementById('bloqueoFin').value;
    const motivo = document.getElementById('bloqueoMotivo').value.trim() || 'Descanso';
    const barberoId = parseInt(document.getElementById('bloqueoBarbero')?.value) || 1;
    if (!inicio || !fin) { alert('Selecciona las fechas'); return; }
    if (fin < inicio) { alert('La fecha fin no puede ser anterior a la fecha inicio'); return; }

    const msg = document.getElementById('mensajeBloqueo');
    msg.className = 'mensaje info';
    msg.textContent = 'Procesando...';
    msg.style.display = 'block';

    try {
        const res = await fetch(`${API_URL}/api/panel/bloquear`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ fecha_inicio: inicio, fecha_fin: fin, motivo, barbero_id: barberoId })
        });
        const data = await res.json();
        if (res.status === 409) {
            if (confirm(`Hay ${data.citas_afectadas.length} citas en este periodo. ¿Cancelarlas todas?`)) {
                const ids = data.citas_afectadas.map(c => c.id);
                const res2 = await fetch(`${API_URL}/api/panel/cancelar-citas-masivo`, {
                    method: 'POST',
                    headers: getAuthHeaders(),
                    body: JSON.stringify({ cita_ids: ids })
                });
                const data2 = await res2.json();
                msg.className = 'mensaje exito';
                msg.textContent = data2.mensaje;
            } else {
                msg.className = 'mensaje error';
                msg.textContent = 'Operacion cancelada por el usuario.';
            }
        } else if (res.ok) {
            msg.className = 'mensaje exito';
            msg.textContent = data.mensaje;
        } else {
            msg.className = 'mensaje error';
            msg.textContent = data.error || 'Error';
        }
    } catch (error) {
        console.error('Error bloqueando dias:', error);
        msg.className = 'mensaje error';
        msg.textContent = 'Error al conectar con el servidor.';
    }
}

// ===== INICIALIZACIÓN =====
document.addEventListener('DOMContentLoaded', function() {
    cargarSesion();

    try {
        const fecha = new Date();
        fecha.setDate(fecha.getDate() + 1);
        const fechaStr = fecha.toISOString().split('T')[0];

        const hoy = new Date();
        const hoyStr = hoy.toISOString().split('T')[0];

        const inputFecha = document.getElementById('fecha');
        if (inputFecha) {
            inputFecha.value = fechaStr;
            inputFecha.min = hoyStr;
        }

        const inputIni = document.getElementById('bloqueoInicio');
        const inputFin = document.getElementById('bloqueoFin');
        if (inputIni) {
            inputIni.value = hoyStr;
            inputIni.min = hoyStr;
        }
        if (inputFin) {
            inputFin.value = hoyStr;
            inputFin.min = hoyStr;
        }
    } catch (e) {
        console.error('Error inicializando fechas:', e);
    }

    cargarBarberosSelectorCliente();
});