# 📘 Manual del Administrador — Gocho Barber

**Última actualización**: Septiembre 2026
**Para**: Administrador del sistema (Ernesto)
**URL del sistema**: https://gochobarber.pages.dev

---

## 🔑 1. Acceso al panel

1. Abre `https://gochobarber.pages.dev` en el navegador (o la app instalada).
2. Arriba a la derecha, clic en **"Panel"**.
3. Usuario: `admin`
4. Contraseña: la que tengas configurada.
5. Clic en **"Ingresar"**.

**Recomendación**: instala la app en tu celular (Configuración → Instalar app) para tenerla a mano.

---

## 👥 2. Gestión de barberos

### Crear un barbero nuevo

1. Panel → pestaña **"Barberos"**.
2. Clic en **"Nuevo Barbero"**.
3. Llena:
   - **Nombre** (obligatorio): ej. `Leyner`
   - **Teléfono**: opcional
   - **Email**: opcional
   - **Telegram Chat ID**: opcional pero recomendado (ver sección 7)
   - **Hora inicio / Hora fin**: horario de trabajo
   - **Pausa**: activar si tiene hora de almuerzo
   - **Días de trabajo**: marca los que trabaja
4. Clic en **"Guardar"**.

**Importante**: el sistema crea **automáticamente** el usuario y contraseña del barbero:
- Ej: barbero `Leyner` → usuario `leyner` / contraseña `leyner123`
- Esos datos te aparecen en el mensaje de confirmación. **Cópialos y pásalos al barbero**.

### Editar un barbero

1. Pestaña **"Barberos"**.
2. Busca al barbero y clic en **"Editar"**.
3. Cambia lo que necesites.
4. Clic en **"Guardar"**.

### Desactivar un barbero (si ya no trabaja más)

1. Clic en **"Desactivar"**.
2. Confirma.
3. **Qué pasa**: sus citas futuras se cancelan automáticamente y no aparece más en el sistema. **No se borra** (para conservar su historial y estadísticas).

### Reactivar un barbero

1. Pestaña **"Barberos"**.
2. Clic en **"Reactivar"** sobre el que estaba inactivo.
3. Vuelve a estar disponible.

### Eliminar un barbero definitivamente

⚠️ **Solo se puede si NO tiene historial de citas**. Si tiene historial, el sistema solo lo desactiva.

1. Clic en el ícono 🗑️ al lado del barbero.
2. Confirma **dos veces** (es irreversible).

---

## 💈 3. Gestión de servicios

### Crear un servicio para un barbero

1. Panel → pestaña **"Servicios"**.
2. En **"Barbero"**, selecciona a quién le vas a crear el servicio.
3. Clic en **"Nuevo Servicio"**.
4. Llena:
   - **Nombre** (obligatorio): ej. `Corte`
   - **Duración en minutos** (obligatorio): ej. `45`
   - **Precio en COP** (obligatorio): ej. `25000`
   - **Descripción**: opcional
5. Clic en **"Guardar"**.

### Editar un servicio

1. Pestaña **"Servicios"** → selecciona el barbero.
2. Clic en **"Editar"** sobre el servicio.
3. Cambia lo que necesites → **"Guardar"**.

### Desactivar un servicio

- Útil si un barbero ya no ofrece ese servicio pero quieres conservarlo.
- Clic en **"Desactivar"**. Deja de aparecer para los clientes pero queda en el historial.

### Eliminar un servicio

- Solo se elimina **de verdad** si no tiene citas asociadas. Si las tiene, se desactiva.
- Clic en 🗑️.

---

## 🖼️ 4. Gestión del catálogo (productos y cortes)

### Agregar un producto o estilo

**Antes de agregarlo en el panel**, la imagen debe estar subida al repositorio:
- Productos: `frontend/imagenes/productos/`
- Cortes: `frontend/imagenes/cortes/`

**Pasos**:

1. Sube la imagen al repositorio en la carpeta correcta (ej. `producto1.jpg`).
2. Espera que Cloudflare haga deploy (2-3 min).
3. Panel → pestaña **"Catálogo"** → **"Nuevo Item"**.
4. Llena:
   - **Tipo**: Producto o Estilo
   - **Archivo** (obligatorio): solo el nombre del archivo, ej. `producto1.jpg`
   - **Nombre** (obligatorio): ej. `Cera para cabello`
   - **Precio**: ej. `35000 COP`
   - **Descripción**: opcional
   - **Orden**: número (menor = aparece primero)
5. Clic en **"Guardar"**.

### Desactivar un item

- Útil si ya no vendes un producto pero no quieres borrarlo.
- Clic en **"Desactivar"**.

### Eliminar un item

- Solo borra la entrada en el sistema. **La imagen sigue en el repositorio**.
- Clic en 🗑️.

---

## 📋 5. Solicitudes pendientes (citas urgentes)

Las citas con **menos de 1 hora de anticipación** entran como **pendientes** y necesitan confirmación.

### Confirmar una cita pendiente

1. Panel → pestaña **"Pendientes"**.
2. Revisa la cita (cliente, servicio, fecha, hora).
3. Clic en **"Aceptar"**.
4. La cita pasa a "Confirmada".

### Rechazar una cita pendiente

1. Clic en **"Rechazar"**.
2. Confirma.
3. El sistema te ofrece **abrir WhatsApp** con el cliente para avisarle. Acepta y se abre con el mensaje predefinido.

### Filtrar por barbero

- Arriba de la lista hay un filtro **"Filtrar por barbero"**.
- Útil si tienes varios barberos y quieres ver solo los pendientes de uno.

---

## 📅 6. Historial de citas

### Ver todas las citas

1. Panel → pestaña **"Historial"**.
2. Por defecto muestra las últimas 200 citas.

### Filtros disponibles

| Filtro | Qué hace |
|--------|----------|
| **Buscar cliente** | Por nombre o teléfono (búsqueda instantánea) |
| **Desde** | Fecha inicial del rango |
| **Hasta** | Fecha final del rango |
| **Estado** | Confirmada, pendiente, realizada, cancelada, etc. |
| **Barbero** | Filtra por barbero específico |

### Limpiar filtros

- Clic en **"Limpiar"** para borrar todos los filtros y volver a la vista completa.

### Cancelar una cita confirmada

- Clic en **"Cancelar"** en la cita → confirma → te ofrece avisar por WhatsApp.

### Eliminar una cita permanentemente

⚠️ **Solo admin. Solo si es necesario.** Es irreversible.

1. Clic en 🗑️.
2. Confirma **dos veces**.

---

## 🚫 7. Bloquear días (vacaciones, feriados, etc.)

1. Panel → pestaña **"Configuración"**.
2. Sección **"Bloquear día"**:
   - **Barbero**: a quién le bloqueas
   - **Fecha inicio** y **Fecha fin** (puede ser el mismo día)
   - **Motivo**: ej. "Vacaciones"
3. Clic en **"Bloquear"**.

**Si hay citas confirmadas en ese rango**, el sistema te avisa y te pregunta si quieres cancelarlas todas. Confirma para cancelarlas en masa.

---

## 📊 8. Estadísticas

Panel → pestaña **"Estadísticas"**.

### Ver resumen

4 tarjetas con:
- **Citas este mes**
- **Citas totales**
- **Clientes únicos**
- **Ingresos estimados (COP)**

### Ver gráficos

- **Citas por mes** (barras)
- **Ingresos por mes** (línea)
- **Citas por barbero** (dona)
- **Top 5 clientes**

### Ver detalle de cada tarjeta

- **Clic** en cualquier tarjeta → se abre un modal con la lista detallada.
- Ej: clic en "Citas este mes" → lista de cada cita con cliente, servicio, precio, barbero.

---

## 📱 9. Telegram — Notificaciones

### Dónde llegan las notificaciones

| Evento | Grupo admin | Chat del barbero |
|--------|-------------|------------------|
| Nueva cita | ✅ | ✅ (si configuró su Telegram) |
| Cliente cancela | ✅ | ✅ |
| Cliente modifica | ✅ | ✅ |
| Backup diario | ✅ | ❌ |
| Barbero confirmó/rechazó | ✅ | ❌ |

### Cómo obtener el Chat ID de un barbero

Mándale este mensaje por WhatsApp al barbero:

> 1. Abre Telegram y busca **@userinfobot**
> 2. Dale "Start" y mándale cualquier mensaje
> 3. Te responde con un número tipo `Id: 8419014448` → **cópialo**
> 4. Ahora busca **@gochobarber_bot** y dale "Start" (importante)
> 5. Mándame ese número

Cuando te pase el número:

1. Panel → **Barberos** → **Editar** sobre el barbero.
2. Pega el número en **"Telegram Chat ID"**.
3. **Guardar**.

A partir de ahí recibe aviso solo de **sus** citas.

### Agregar personas al grupo de admin

1. Abre Telegram → grupo **"Gocho Barber - Notificaciones"**.
2. Agrega a quien quieras.
3. Listo, no hay que tocar nada en el sistema.

---

## 📲 10. Instalar la app en el celular (PWA)

1. Abre `https://gochobarber.pages.dev` en Chrome (Android) o Safari (iPhone).
2. Panel → **Configuración** → **"Instalar app"**.
3. Ingresa la contraseña del admin.
4. Sigue las instrucciones del sistema.

**En iPhone**: se abre un modal con los pasos (Compartir → Añadir a pantalla de inicio).

---

## 🆘 11. Qué hacer si algo falla

### La página no carga

- Espera 30 segundos. El servidor gratuito "duerme" y tarda en despertar.
- Refresca (F5).

### Aparece "Sin conexión"

- Revisa tu internet.
- Intenta de nuevo.

### Un botón no responde

1. Presiona **F12** en el navegador.
2. Pestaña **"Console"**.
3. Copia el mensaje rojo que aparezca.
4. Pásaselo al desarrollador (o a la IA).

### Necesito ver el error exacto

- **En el celular**: no hay F12. Copia el mensaje del toast (notificación emergente).
- **En PC**: F12 → Console → copia el texto rojo.

---

## 🔒 12. Seguridad

### Cambiar la contraseña del admin

- Actualmente se cambia directamente en la base de datos (a través de Render).
- Pídele al desarrollador o a la IA que te guíe.

### No compartas

- La contraseña del admin
- El token del bot de Telegram
- El token de backup

### Si sospechas que alguien los tiene

- Avísale al desarrollador para rotarlos.

---

## 📞 13. Contacto y soporte

- **Desarrollador**: Ernesto Roa
- **Repositorio**: github.com/deinys-c/barberia
- **Sistema**: https://gochobarber.pages.dev

---

**Fin del manual del administrador.**