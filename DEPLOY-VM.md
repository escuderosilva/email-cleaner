# Despliegue en servidor / VM interna de Wherex

Guía para levantar la herramienta en una VM propia (recomendado para que el
chequeo SMTP funcione y para mantener los datos de contactos dentro del
perímetro de Wherex).

---

## 1. Requisitos para IT (qué debe tener la VM)

**Base**
- Linux (Ubuntu/Debian recomendado) con **Docker** y **Docker Compose** instalados.
- Recursos sugeridos: **2 vCPU, 4 GB RAM, ~10 GB de disco**.

**Para que el chequeo SMTP funcione** (esto es lo que Streamlit Cloud no permite):
- **Salida al puerto 25 (TCP) habilitada** hacia internet. Es lo más importante;
  muchos entornos lo bloquean por defecto para prevenir spam.
- **IP dedicada** con **rDNS/PTR** apuntando a un hostname válido (los servidores
  de correo de destino verifican el DNS inverso). Sin esto, muchos responden
  "no verificable".
- Idealmente un **subdominio dedicado** para el saludo SMTP (no el dominio
  principal de envío de Wherex), para no arriesgar la reputación de `wherex.com`.

**Acceso a la app**
- La app expone el puerto **8501**. Debe quedar accesible **solo dentro de la red
  de Wherex / por VPN**, o detrás de un **reverse proxy con autenticación (SSO)**.
  No exponerla abierta a internet: procesa datos de contactos (PII).

**Datos**
- Al ser una VM interna, los datos de contactos **no salen del perímetro** de
  Wherex. La app no los almacena: solo procesa el archivo en memoria y guarda
  caché técnico (dominios MX) e historial de chequeos en un volumen local.

---

## 2. Despliegue (pasos)

```bash
# 1. Clonar el repositorio en la VM
git clone https://github.com/escuderosilva/email-cleaner.git
cd email-cleaner

# 2. Variables simples (token de HubSpot e ID de la hoja de uso)
cat > .env <<'EOF'
HUBSPOT_TOKEN=pat-na1-...tu-service-key...
USAGE_SHEET_ID=1iH7H4XVSUrUg3bORUBIJJO-KVeFLT34WDlNIk-pCf-o
EOF

# 3. Credencial de Google (para el log de uso en la hoja): dejar el JSON del
#    service account en secrets/sa.json
mkdir -p secrets
cp /ruta/a/email-cleaner-logger-XXXX.json secrets/sa.json

# 4. Construir y levantar
docker compose up -d --build

# 5. Ver logs / estado
docker compose logs -f
```

La app queda en `http://<ip-de-la-vm>:8501` (idealmente detrás del proxy/VPN).

**Si no vas a usar el log en Google Sheet:** borra del `docker-compose.yml` la
línea del volumen `./secrets/sa.json:...` y la variable `GCP_SERVICE_ACCOUNT_FILE`.

---

## 3. Operación

- **Actualizar a una versión nueva:**
  ```bash
  git pull && docker compose up -d --build
  ```
- **Reiniciar:** `docker compose restart`
- **Datos persistentes:** el volumen `cleaner-data` guarda el caché MX, el
  historial de chequeos y el log de uso; sobrevive reinicios y actualizaciones.
- **Backups:** basta respaldar el volumen `cleaner-data` (y la Google Sheet, que
  ya es externa).

---

## 4. Seguridad

- `.env` y `secrets/` están en `.gitignore`: las credenciales no viajan al repo.
- Mantener la app detrás de VPN/SSO; el login por correo de la app es solo para
  trazabilidad, no es autenticación fuerte.
- Rotar la Service Key de HubSpot y la clave del service account si se exponen.
