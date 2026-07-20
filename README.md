# Limpiador de bases de contactos

Herramienta web (Streamlit) para limpiar bases de emails y reducir el bounce
rate: valida sintaxis, dominios y MX/DNS, corrige typos, deduplica, verifica por
SMTP (opcional) y actualiza HubSpot (opcional). Acepta Excel y CSV.

Para el uso diario (no técnico), ver **[MANUAL.md](MANUAL.md)**.

---

## Correr en local

```bash
pip install -r requirements.txt
streamlit run app.py
```

O usa los lanzadores de doble clic: `abrir-windows.bat` / `abrir-mac.command`.

La integración con HubSpot lee la Service Key desde un archivo `.env` local:

```
HUBSPOT_TOKEN=tu-service-key
```

(Copia `.env.example` a `.env`. El `.env` está en `.gitignore` y no se sube.)

---

## Desplegar en Streamlit Community Cloud

1. Sube este repo a GitHub (ver más abajo).
2. Entra a https://share.streamlit.io con tu cuenta de GitHub.
3. **New app** → elige el repo, rama `main` y archivo principal `app.py`.
4. En **Advanced settings → Secrets**, pega la Service Key (NO va en el repo):

   ```toml
   HUBSPOT_TOKEN = "tu-service-key"
   ```

5. **Deploy**. La app queda en una URL pública.
6. Importante para datos de clientes: en la configuración de la app, márcala como
   **privada** e invita solo los correos del equipo. Streamlit no tiene login
   propio; sin esto, cualquiera con la URL podría usarla.

> Nota de cumplimiento: al hostear en un cloud de terceros, las bases de contactos
> (PII) salen del perímetro de Wherex. Si eso es un problema, hostea en infra
> propia (hay un `Dockerfile` de referencia en el MANUAL) o usa la herramienta en
> local.

---

## Acceso y trazabilidad

Al abrir la app se pide un correo corporativo (`@wherex.com` / `@wherexpay.com`)
antes de dejar usarla. Cada acción relevante (login, procesar, SMTP, HubSpot)
se registra con el correo y la fecha:

- A **stdout** → queda en los logs de Streamlit Cloud (Manage app → logs). Esta es
  la fuente durable de tracking en el hosting.
- A `data/usage_log.csv` → persistente en local, **efímero en Streamlit Cloud**
  (se pierde al reiniciar el contenedor).

Este login es liviano y sirve para **trazar el uso**, no como seguridad fuerte
(alguien podría escribir cualquier correo del dominio). Para identidad real y no
falsificable, marca la app como privada en Streamlit Cloud y usa su login de
Google (SSO); se puede leer el correo autenticado con `st.user`.

## Subir a GitHub

Ya viene inicializado como repo git con un commit inicial. Para publicarlo:

```bash
# crea el repo vacío en github.com (privado, recomendado) y luego:
git remote add origin git@github.com:TU-USUARIO/email-cleaner.git
git push -u origin main
```

Qué **no** se sube (protegido por `.gitignore`): `.env` (la Service Key),
`.venv/`, el historial y el caché de datos.

---

## Estructura

```
app.py                     Interfaz Streamlit (3 pasos)
cleaner/
  pipeline.py              Orquestación de la limpieza + reconciliación SMTP
  validators.py            Sintaxis, MX/DNS con caché y concurrencia
  domains.py               Listas de dominios desechables, free-mail y roles
  smtp_verify.py           Verificación SMTP con salvaguardas (opcional)
  hubspot_sync.py          Write-back / archivado en HubSpot (opcional)
  history.py               Historial de chequeos (evita revalidar)
scripts/refresh_mx_cache.py  Refresco del caché MX (cron)
data/disposable_domains.txt  Lista de dominios desechables
```
