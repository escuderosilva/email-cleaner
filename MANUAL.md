# Manual de uso — Limpiador de bases de contactos

Herramienta para limpiar bases de emails y reducir el bounce rate antes de enviar
campañas. Acepta archivos **Excel y CSV**. Valida sintaxis, dominios y registros
MX/DNS, auto-corrige typos, deduplica y clasifica los contactos. Pensada para que
cualquier persona la use sin conocimientos técnicos. La integración con HubSpot es
**opcional**.

---

## 1. Requisitos

- **Python 3.9 o superior** instalado.
  - Windows: descárgalo desde https://www.python.org/downloads/ y marca
    **"Add Python to PATH"** durante la instalación.
  - Mac: descárgalo desde https://www.python.org/downloads/ (o `brew install python`).
- Conexión a internet (para resolver dominios y, si la usas, HubSpot).

No necesitas saber programar. Los lanzadores instalan todo solos la primera vez.

---

## 2. Cómo abrir la herramienta

La primera vez tarda un par de minutos (crea el entorno e instala dependencias).
Las siguientes veces abre en segundos.

### Windows
1. Abre la carpeta.
2. Haz doble clic en **`abrir-windows.bat`**.
3. Se abrirá una ventana negra (déjala abierta) y luego tu navegador en
   `http://localhost:8501`.

> Si Windows muestra "Windows protegió tu PC": clic en **Más información → Ejecutar de todas formas**.

### Mac
1. Abre la carpeta.
2. Haz doble clic en **`abrir-mac.command`**.
3. Se abrirá la Terminal (déjala abierta) y luego tu navegador en
   `http://localhost:8501`.

> La primera vez Mac puede bloquearlo por seguridad. Si pasa: clic derecho sobre
> `abrir-mac.command` → **Abrir** → **Abrir**. O ve a
> **Ajustes del Sistema → Privacidad y seguridad → Abrir de todas formas**.

Para **cerrar** la herramienta: cierra la ventana negra / Terminal, o presiona
`Ctrl+C` en ella.

---

## 3. Uso paso a paso

La pantalla está dividida en 3 pasos numerados. Cada opción tiene un ícono **❓**
al lado: pasa el mouse por encima y aparece una explicación.

**Paso 1 — Sube tu lista**
1. Arrastra tu archivo **Excel (.xlsx) o CSV**. Ambos formatos funcionan.
2. La herramienta adivina la **columna de correos**; cámbiala si eligió mal.
3. La **columna de fecha** sirve para que, si hay correos repetidos, se quede con
   el contacto más reciente. Si no sabes cuál es, déjala como está.
4. En **⚙️ Opciones** (ya vienen bien por defecto) puedes activar/desactivar:
   corregir typos, detectar repetidos, y no revisar correos vistos hace poco.
5. Aprieta **✨ Procesar lista**.

**Paso 2 — Revisa el resultado**
- Verás tarjetas con Total, Válidos, Riesgo, Inválidos y Repetidos.
- Los desplegables **❓** y **📊** explican qué significa cada número y muestran el
  desglose por motivo.
- En **🔎 Explorar la tabla** puedes filtrar por estado y por tipo de error
  (ej. mostrar solo los de `dominio_sin_mx`).

**Paso 3 — Descarga**
- Elige **qué** descargar (solo válidos, enviables, lo que ves en la tabla, o todo)
  y en **qué formato** (Excel o CSV).
- Aprieta **⬇️ Descargar**. Se genera un archivo nuevo; tu original no se toca.

---

## 4. Qué significan los estados

| Estado | Qué es | Recomendación |
|--------|--------|---------------|
| `valido` | Sintaxis correcta y el dominio recibe correo (tiene MX). | Enviar. |
| `riesgo` | Válido pero con alguna señal (cuenta de rol, DNS no verificable). | Enviar con criterio. |
| `invalido` | Sin email, sintaxis mala, dominio sin MX, desechable o buzón sospechoso. | No enviar. |

Columna `motivo` (puede tener varios separados por `;`):
- `sin_email` — la fila no traía email.
- `sintaxis_invalida` — no es un email bien formado.
- `dominio_sin_mx` — el dominio no puede recibir correo.
- `dns_no_verificable` — no se pudo resolver (timeout/DNS); quedó en riesgo.
- `cuenta_generica_rol` — es info@, ventas@, etc. (no una persona).
- `buzon_sospechoso` — abuse@, test@, spam@, etc.
- `dominio_desechable` — dominio de correo temporal.

Columna `tipo_dominio`: `personal` (gmail, hotmail…), `corporativo` o `desechable`.
Columna `correccion_typo`: si se corrigió el dominio, muestra `original->corregido`.
Columna `last_check_date`: fecha en que se validó ese correo (hoy, o la de una
corrida previa si se reutilizó del historial).
Columna `reutilizado`: `True` si el resultado vino del historial sin revalidar.

---

## 5. Verificación SMTP (opcional, chequeo profundo)

Sección "🔌 Verificación SMTP". Hace un chequeo más profundo conectándose al
servidor de destino, sin enviar correo. Úsalo solo para **lotes chicos** (tope
3.000) y con un **email remitente dedicado** (no uses wherex.com, para no
arriesgar la reputación de envío). Es lento y algunos servidores lo bloquean.

Al terminar, **actualiza automáticamente el estado de la base** (no es un reporte
aparte): descargas y métricas quedan reconciliadas. El resultado se aplica así:

| SMTP dice | Nuevo estado |
|-----------|--------------|
| existe | válido (riesgo si además es cuenta de rol) |
| no existe / sin MX | inválido |
| catch-all (dominio acepta todo) | riesgo |
| no verificable (greylist/timeout) | riesgo (o inválido si marcas modo estricto) |

Casilla **"Tratar 'no verificable' como inválido"**: por defecto está apagada,
porque un "no verificable" suele ser un bloqueo temporal del servidor, no un
correo malo. Actívala solo si prefieres limpiar de forma más agresiva.

---

## 6. Integración con HubSpot (opcional y discrecional)

Por defecto la herramienta **solo limpia el CSV y no toca HubSpot**. Si además
quieres actuar sobre tu CRM, marca la casilla
**"🟠 Buscar y limpiar estos contactos en HubSpot"**. Ahí eliges:

- **Marcar estado en cada contacto** — escribe `valido/riesgo/invalido` en la
  propiedad `email_validation_status`. No borra nada.
- **Archivar los inválidos** — los envía a la papelera de HubSpot (recuperable
  ~90 días, no es borrado permanente).

**Siempre corre primero con "Dry-run" marcado**: simula y te muestra cuántos
contactos afectaría, sin tocar el CRM. Cuando estés conforme, desmarca Dry-run y
ejecuta de verdad.

La conexión con HubSpot ya viene configurada; no tienes que hacer nada extra.

---

## 7. Mantenimiento del caché

La herramienta guarda en `data/mx_cache.json` los dominios ya resueltos, así las
siguientes bases se procesan mucho más rápido. Para refrescarlo (opcional, ej.
mensual), desde la terminal dentro de la carpeta:

```bash
python scripts/refresh_mx_cache.py
```

---

## 8. Problemas frecuentes

- **"No se encontró Python"** → instálalo (sección 1) y vuelve a abrir el lanzador.
- **La página no abre sola** → entra manualmente a `http://localhost:8501`.
- **Muy lento la primera vez** → normal, está instalando dependencias; espera.
- **SMTP marca todo "no_verificable"** → tu red probablemente bloquea el puerto
  25; es esperable desde redes domésticas/corporativas.
