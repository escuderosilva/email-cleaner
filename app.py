import io
import os
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(Path(__file__).resolve().parent / ".env")

# En local las claves vienen del .env; en Streamlit Cloud, de los Secrets del panel.
try:
    import json as _json
    for _k in ("HUBSPOT_TOKEN", "USAGE_SHEET_ID", "GCP_SERVICE_ACCOUNT_JSON"):
        if os.environ.get(_k) or _k not in st.secrets:
            continue
        _v = st.secrets[_k]
        # El service account puede venir como string JSON o como sección TOML.
        os.environ[_k] = _v if isinstance(_v, str) else _json.dumps(dict(_v))
except Exception:
    pass

from cleaner.pipeline import clean_dataframe
from cleaner.usage import ALLOWED_DOMAINS, is_allowed_email, log_event

st.set_page_config(page_title="Limpiador de bases de contactos", page_icon="📧", layout="wide")

# ---------- Estilo suave ----------
st.markdown(
    """
    <style>
      .block-container { max-width: 1150px; padding-top: 2rem; }
      div.stButton > button, .stDownloadButton > button {
          border-radius: 10px; padding: 0.55rem 1.1rem; font-weight: 600;
      }
      [data-testid="stMetric"] {
          background: rgba(127,127,127,0.07); border-radius: 14px; padding: 14px 16px;
      }
      [data-testid="stExpander"] details {
          border-radius: 12px; border: 1px solid rgba(127,127,127,0.20);
      }
      h1, h2, h3 { letter-spacing: -0.01em; }
      .paso { font-size: 0.8rem; font-weight: 700; color: #4F8DFD;
              text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: -0.3rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Escribe el Excel en modo streaming (write_only) para usar poca RAM:
    no mantiene todos los objetos-celda en memoria como haría pandas.to_excel."""
    from openpyxl import Workbook

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("contactos")
    ws.append([str(c) for c in df.columns])
    for row in df.itertuples(index=False, name=None):
        ws.append([
            "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)
            for v in row
        ])
    buf = io.BytesIO()
    wb.save(buf)
    wb.close()
    return buf.getvalue()


def read_upload(uploaded) -> pd.DataFrame:
    name = uploaded.name.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded, dtype=str)
    return pd.read_csv(uploaded, dtype=str)


def guess_email_column(columns) -> int:
    for i, c in enumerate(columns):
        if "email" in c.lower() or "correo" in c.lower() or "mail" in c.lower():
            return i
    return 0


# ---------- Acceso (login por correo corporativo, para trazar el uso) ----------
if "user_email" not in st.session_state:
    st.title("Limpiador de bases de contactos")
    st.markdown("Ingresa tu correo corporativo para usar la herramienta.")
    with st.form("login"):
        correo = st.text_input("Correo", placeholder="tunombre@wherex.com")
        entrar = st.form_submit_button("Entrar")
    if entrar:
        if is_allowed_email(correo):
            st.session_state["user_email"] = correo.strip().lower()
            log_event(st.session_state["user_email"], "login")
            st.rerun()
        else:
            dominios = " o ".join("@" + d for d in sorted(ALLOWED_DOMAINS))
            st.error(f"Debes ingresar un correo corporativo ({dominios}).")
    st.stop()

usuario = st.session_state["user_email"]

with st.sidebar:
    st.markdown(f"**Sesión**\n\n{usuario}")
    if st.button("Salir"):
        del st.session_state["user_email"]
        st.rerun()

# ---------- Encabezado ----------
st.title("Limpiador de bases de contactos")
st.caption("Sube tu lista, límpiala y descarga los contactos válidos para tus campañas.")

with st.expander("¿Qué hace esta herramienta y cómo la uso?"):
    st.markdown(
        """
        Revisa cada correo de tu lista y determina si sirve para enviar campañas,
        reduciendo los rebotes.

        1. Sube tu archivo (Excel o CSV).
        2. Aprieta Procesar.
        3. Descarga la lista limpia.

        No modifica tu archivo original: genera uno nuevo, ya limpio.
        """
    )

# ---------- Paso 1: subir ----------
st.markdown('<div class="paso">Paso 1</div>', unsafe_allow_html=True)
st.subheader("Sube tu lista de contactos")
uploaded = st.file_uploader(
    "Arrastra aquí tu archivo Excel o CSV",
    type=["csv", "xlsx", "xls"],
    help="Acepta Excel (.xlsx, .xls) y CSV. Debe tener una columna con los correos.",
)

if uploaded:
    try:
        df = read_upload(uploaded)
    except Exception as e:
        st.error(f"No pude leer el archivo. Revisa que sea un Excel o CSV válido. Detalle: {e}")
        st.stop()

    if df.empty:
        st.warning("El archivo no tiene filas.")
        st.stop()

    st.success(f"Archivo cargado: {len(df):,} filas.")

    columns = list(df.columns)
    c1, c2 = st.columns(2)
    with c1:
        email_col = st.selectbox(
            "¿Cuál columna tiene los correos?", columns,
            index=guess_email_column(columns),
            help="La herramienta intenta adivinarla. Cámbiala si eligió mal.",
        )
    with c2:
        activity_options = ["(no ordenar por fecha)"] + columns
        default_act = (
            activity_options.index("Last Activity Date")
            if "Last Activity Date" in columns else 0
        )
        activity_choice = st.selectbox(
            "Columna de fecha (para quedarse con el contacto más reciente)",
            activity_options, index=default_act,
            help="Si hay correos repetidos, se conserva el de actividad más nueva. "
                 "Si no sabes, déjalo como está.",
        )

    with st.expander("Opciones (vienen configuradas por defecto)"):
        autocorrect = st.checkbox(
            "Corregir errores de tipeo en dominios", value=True,
            help="Arregla cosas como 'gmial.com' → 'gmail.com'. Nunca toca dominios que sí funcionan.",
        )
        dedup = st.checkbox(
            "Detectar correos repetidos", value=True,
            help="Marca los duplicados para que puedas excluirlos. No borra nada de tu archivo.",
        )
        colr1, colr2 = st.columns([1, 1])
        omitir_recientes = colr1.checkbox(
            "No revisar de nuevo los correos vistos hace poco", value=True,
            help="Ahorra tiempo: reutiliza el resultado de correos ya chequeados hace poco.",
        )
        dias = colr2.number_input(
            "¿Hace cuántos días?", min_value=1, max_value=365, value=30, step=1,
            disabled=not omitir_recientes,
            help="Un correo revisado dentro de esta ventana no se vuelve a chequear.",
        )

    if st.button("Procesar lista", type="primary", use_container_width=True):
        progress = st.progress(0.0, text="Revisando dominios...")

        def on_progress(done, total):
            if total:
                progress.progress(done / total, text=f"Revisando dominios: {done}/{total}")
            else:
                progress.progress(1.0, text="Listo, todo estaba en memoria")

        activity_col = None if activity_choice.startswith("(") else activity_choice
        with st.spinner("Procesando tu lista..."):
            result = clean_dataframe(
                df, email_col, activity_col=activity_col,
                autocorrect_typos=autocorrect, dedup=dedup,
                recheck_days=int(dias) if omitir_recientes else None,
                progress_callback=on_progress,
            )
        progress.empty()
        st.session_state["result"] = result
        st.session_state["nombre_base"] = Path(uploaded.name).stem
        log_event(usuario, "procesar", f"{len(df):,} filas · {uploaded.name}")

# ---------- Paso 2: resultados ----------
if "result" in st.session_state:
    result = st.session_state["result"]
    nombre = st.session_state.get("nombre_base", "contactos")

    st.divider()
    st.markdown('<div class="paso">Paso 2</div>', unsafe_allow_html=True)
    st.subheader("Resultado de la limpieza")

    counts = result["estado"].value_counts()
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total", f"{len(result):,}", help="Filas en tu archivo.")
    m2.metric("Válidos", f"{counts.get('valido', 0):,}", help="Listos para enviar.")
    m3.metric("Riesgo", f"{counts.get('riesgo', 0):,}", help="Se pueden enviar con criterio.")
    m4.metric("Inválidos", f"{counts.get('invalido', 0):,}", help="No enviar: rebotarían.")
    m5.metric("Repetidos", f"{int(result['es_duplicado'].sum()):,}", help="Correos duplicados.")

    corregidos = int((result["correccion_typo"] != "").sum())
    reusados = int(result["reutilizado"].sum())
    notas = []
    if corregidos:
        notas.append(f"{corregidos:,} dominios con typos corregidos")
    if reusados:
        notas.append(f"{reusados:,} reutilizados del historial")
    if notas:
        st.caption(" · ".join(notas))

    with st.expander("¿Qué significan válido, riesgo e inválido?"):
        st.markdown(
            """
            - **Válido** — bien escrito y su dominio puede recibir mensajes. Se puede enviar.
            - **Riesgo** — sirve, pero tiene alguna señal a considerar (ej. es una cuenta
              genérica como `info@`, o no se pudo confirmar del todo). Enviar con criterio.
            - **Inválido** — no conviene enviar: está vacío, mal escrito, el dominio no
              recibe correo o es un correo desechable. Rebotaría.

            La columna **motivo** explica el porqué de cada caso.
            """
        )

    with st.expander("Ver desglose por motivo y tipo de dominio"):
        cols = st.columns(2)
        with cols[0]:
            st.markdown("**Motivos**")
            motivos = result.loc[result["motivo"] != "", "motivo"].str.split(";").explode()
            if not motivos.empty:
                st.dataframe(motivos.value_counts().rename("cantidad"), use_container_width=True)
            else:
                st.write("Sin observaciones.")
        with cols[1]:
            st.markdown("**Tipo de dominio**")
            st.dataframe(result["tipo_dominio"].value_counts().rename("cantidad"), use_container_width=True)

    # ---- Filtros ----
    st.markdown("##### Explorar la tabla")
    f1, f2 = st.columns(2)
    filtro = f1.multiselect(
        "Mostrar estados", ["valido", "riesgo", "invalido"],
        default=["valido", "riesgo", "invalido"],
        help="Elige qué estados ver en la tabla de abajo.",
    )
    motivos_disponibles = sorted(
        {m for m in result["motivo"].str.split(";").explode().dropna() if m}
    )
    filtro_motivo = f2.multiselect(
        "Filtrar por tipo de error / motivo", motivos_disponibles, default=[],
        help="Vacío = todos. Ejemplo: elige 'dominio_sin_mx' para ver solo esos.",
    )
    ocultar_dup = st.checkbox("Ocultar repetidos en la tabla", value=True)

    view = result[result["estado"].isin(filtro)]
    if filtro_motivo:
        patron = "|".join(re.escape(m) for m in filtro_motivo)
        view = view[view["motivo"].str.contains(patron, na=False)]
    if ocultar_dup:
        view = view[~view["es_duplicado"]]
    st.dataframe(view, use_container_width=True, height=380)
    st.caption(f"Mostrando {len(view):,} de {len(result):,} filas.")

    # ---- Paso 3: descargar ----
    st.divider()
    st.markdown('<div class="paso">Paso 3</div>', unsafe_allow_html=True)
    st.subheader("Descarga tu lista limpia")

    opciones = [
        "Solo válidos y sin repetidos (recomendado para enviar)",
        "Enviables (válidos + riesgo, sin repetidos)",
        "Lo que estoy viendo en la tabla (con filtros)",
        "Todo (base completa con estado y motivo)",
    ]
    dcol1, dcol2 = st.columns([2, 1])
    sel = dcol1.selectbox("¿Qué quieres descargar?", opciones)
    fmt = dcol2.radio("Formato", ["CSV (más liviano)", "Excel (.xlsx)"], horizontal=False)

    # Se construye SOLO el subconjunto elegido, para no tener 4 copias en memoria.
    if sel.startswith("Solo válidos"):
        df_desc = result[(result["estado"] == "valido") & (~result["es_duplicado"])]
    elif sel.startswith("Enviables"):
        df_desc = result[(result["estado"].isin(["valido", "riesgo"])) & (~result["es_duplicado"])]
    elif sel.startswith("Lo que estoy"):
        df_desc = view
    else:
        df_desc = result

    st.caption(f"Se descargarán {len(df_desc):,} filas.")
    if fmt.startswith("CSV"):
        st.download_button(
            "Descargar", df_desc.to_csv(index=False).encode("utf-8"),
            file_name=f"{nombre}_limpio.csv", mime="text/csv",
            type="primary", use_container_width=True,
        )
    else:
        if len(df_desc) > 40000:
            st.warning(
                "Exportar tantas filas a Excel usa bastante memoria. Si la app se "
                "pone lenta o se corta, usa **CSV** (Excel lo abre igual)."
            )
        st.download_button(
            "Descargar", to_excel_bytes(df_desc),
            file_name=f"{nombre}_limpio.xlsx", mime=EXCEL_MIME,
            type="primary", use_container_width=True,
        )

    # ---- Verificación SMTP (avanzado) ----
    st.divider()
    with st.expander("Verificación avanzada (SMTP) — opcional, para usuarios avanzados"):
        st.markdown(
            "Hace un chequeo más profundo conectándose al servidor de cada correo "
            "(sin enviar nada) y **actualiza el estado de la base** con lo que encuentre."
        )
        st.warning(
            "Requiere un correo remitente **dedicado** (no uses wherex.com) y una red que "
            "no bloquee el puerto 25. Desde oficinas o casas suele salir 'no verificable'. "
            "Máximo 3.000 correos por vez."
        )
        sender = st.text_input(
            "Correo remitente para el chequeo", placeholder="checker@tu-dominio-dedicado.com",
            help="Se usa solo para el saludo con el servidor; no se envía ningún correo.",
        )
        # Se chequea exactamente lo que el usuario tiene visible en la tabla (según sus filtros).
        target = view[view["email_normalizado"].str.contains("@", na=False)].drop_duplicates(
            subset="email_normalizado"
        )
        st.info(
            f"Se verificarán los **{len(target):,} correos que estás viendo en la tabla** "
            "(según los filtros del Paso 2). Ajusta los filtros de arriba para elegir cuáles."
        )
        estricto = st.checkbox(
            "Tratar 'no verificable' como inválido (más estricto)", value=False,
            help="Por defecto queda en 'riesgo' para no descartar buenos contactos.",
        )
        if st.button("Verificar y actualizar la base"):
            from cleaner.smtp_verify import verify_batch, MAX_ROWS
            from cleaner.pipeline import reconcile_smtp
            emails = target["email_normalizado"].tolist()
            if not sender or "@" not in sender:
                st.error("Ingresa un correo remitente válido.")
            elif not emails:
                st.info("No hay correos con dirección válida en la tabla actual. Ajusta los filtros.")
            elif len(emails) > MAX_ROWS:
                st.error(
                    f"{len(emails):,} correos superan el máximo de {MAX_ROWS:,}. "
                    "Usa los filtros del Paso 2 para reducir la selección."
                )
            else:
                sprog = st.progress(0.0, text="Verificando...")
                res = verify_batch(
                    emails, sender,
                    progress_callback=lambda i, t: sprog.progress(i / t, text=f"Verificando {i}/{t}"),
                )
                sprog.empty()
                smtp_by_index = dict(zip(target.index, res))
                st.session_state["result"] = reconcile_smtp(
                    result, smtp_by_index, strict_unverifiable=estricto
                )
                log_event(usuario, "smtp", f"{len(res):,} correos")
                st.success(f"Listo. Se actualizaron {len(res):,} correos en la base.")
                st.rerun()

    # ---- HubSpot (opcional) ----
    with st.expander("Actualizar HubSpot con estos resultados — opcional"):
        st.markdown(
            "Por defecto la herramienta **no toca HubSpot**. Actívalo solo si quieres "
            "reflejar esta limpieza en tu CRM **marcando el estado** en cada contacto. "
            "No borra ni archiva contactos. Corre siempre la simulación primero."
        )
        usar_hs = st.checkbox("Sí, quiero marcar el estado en HubSpot", value=False)
        if usar_hs:
            owner_email = st.text_input(
                "Tu correo (queda registrado como quién validó)",
                value=usuario,
                help="Se asocia a tu perfil de HubSpot en la propiedad 'Validado por', "
                     "junto con la fecha de la verificación.",
            )
            dry = st.checkbox(
                "Modo simulación (no toca el CRM)", value=True,
                help="Te muestra a cuántos afectaría, sin cambiar nada. Desmárcalo para ejecutar de verdad.",
            )
            if st.button("Marcar estado en HubSpot"):
                if not owner_email or "@" not in owner_email:
                    st.error("Ingresa tu correo para registrar quién hizo la validación.")
                else:
                    try:
                        from cleaner.hubspot_sync import sync_statuses
                        summary = sync_statuses(result, owner=owner_email.strip(), dry_run=dry)
                        st.json(summary)
                        log_event(usuario, "hubspot",
                                  f"dry_run={dry} · {summary['total_a_actualizar']} contactos")
                        if dry:
                            st.success("Simulación lista. Revisa el resumen y desmarca 'Modo simulación' para ejecutar.")
                        else:
                            st.success("Estados marcados en HubSpot.")
                    except Exception as e:
                        st.error(f"Error: {e}")
