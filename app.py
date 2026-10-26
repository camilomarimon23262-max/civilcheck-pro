import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
from PIL import Image
from datetime import date, datetime
import os
import sys
import subprocess
import base64
import hashlib

# Verificación automática de librería PDF
try:
    from fpdf import FPDF
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fpdf2"])
    from fpdf import FPDF

# ================= CONFIGURACIÓN DE LA PÁGINA =================
st.set_page_config(
    page_title="CivilCheck Pro - Sistema de Inspección Técnica",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ================= ESCUDO ANTI-ERROR 'removeChild' Y ESTILOS =================
st.markdown("""
<meta name="google" content="notranslate">
<script>
    document.documentElement.setAttribute('translate', 'no');
    document.documentElement.classList.add('notranslate');
</script>
<style>
    .stApp {
        background-color: #f8fafc;
    }
    .hero-banner {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
        color: white;
        padding: 1.2rem 1.8rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .hero-banner h1 {
        color: white !important;
        margin: 0 !important;
        font-size: 1.5rem !important;
        font-weight: 700 !important;
    }
    .hero-banner p {
        color: #cbd5e1 !important;
        margin: 0.25rem 0 0 0 !important;
        font-size: 0.9rem !important;
    }
    .login-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
        color: white;
        padding: 1.6rem;
        border-radius: 12px;
        text-align: center;
        margin-bottom: 1.2rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    .login-header h2 {
        color: white !important;
        margin: 0 !important;
        font-size: 1.5rem !important;
    }
    .login-header p {
        color: #cbd5e1 !important;
        margin: 0.3rem 0 0 0 !important;
        font-size: 0.9rem !important;
    }
    .module-badge {
        background-color: #1e40af;
        color: white;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        display: inline-block;
        margin-bottom: 6px;
    }
    .ok-box {
        background-color: #ecfdf5;
        border: 1px solid #10b981;
        color: #065f46;
        padding: 12px;
        border-radius: 8px;
        font-weight: 600;
        text-align: center;
        font-size: 0.95rem;
        margin: 10px 0;
    }
    .warn-box {
        background-color: #fef2f2;
        border: 1px solid #ef4444;
        color: #991b1b;
        padding: 12px;
        border-radius: 8px;
        font-weight: 600;
        text-align: center;
        font-size: 0.95rem;
        margin: 10px 0;
    }
    .stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.55rem 1rem !important;
    }
</style>
""", unsafe_allow_html=True)

# Directorios de almacenamiento
CARPETA_FOTOS = "fotos_inspecciones"
CARPETA_PDFS = "pdfs_informes"
os.makedirs(CARPETA_FOTOS, exist_ok=True)
os.makedirs(CARPETA_PDFS, exist_ok=True)

# ================= BASE DE DATOS MULTIUSUARIO Y SEGURIDAD (SQLite WAL) =================
DB_PATH = "ingenieria_inspecciones.db"

def obtener_conexion():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def encriptar_password(password):
    """Encripta la contraseña con SHA-256 para no guardarla en texto plano."""
    return hashlib.sha256(password.strip().encode("utf-8")).hexdigest()

def inicializar_bd():
    conn = obtener_conexion()
    cursor = conn.cursor()
    # Tabla de Usuarios para Login
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            nombre_completo TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            fecha_creacion TEXT NOT NULL
        )
    """)
    # Tabla de Inspecciones
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inspecciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto TEXT NOT NULL,
            direccion TEXT NOT NULL,
            inspector TEXT NOT NULL,
            fecha TEXT NOT NULL,
            estado TEXT NOT NULL,
            total_espacios INTEGER NOT NULL,
            ruta_pdf TEXT NOT NULL
        )
    """)
    # Tabla de Sectores / Puntos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS espacios_inspeccion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inspeccion_id INTEGER NOT NULL,
            nombre_espacio TEXT NOT NULL,
            fachada_ubicacion TEXT NOT NULL,
            longitud_aprox TEXT NOT NULL,
            datos_personalizados TEXT,
            observaciones TEXT,
            nitidez_puntaje REAL,
            estado_foto TEXT,
            ruta_foto TEXT NOT NULL,
            FOREIGN KEY (inspeccion_id) REFERENCES inspecciones (id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()

inicializar_bd()

# ================= FUNCIONES DE AUTENTICACIÓN DE USUARIOS =================
def registrar_usuario_bd(usuario, nombre_completo, password):
    conn = obtener_conexion()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO usuarios (usuario, nombre_completo, password_hash, fecha_creacion)
            VALUES (?, ?, ?, ?)
        """, (
            usuario.strip().lower(),
            nombre_completo.strip(),
            encriptar_password(password),
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))
        conn.commit()
        conn.close()
        return True, "✅ Cuenta creada exitosamente. Ahora puedes iniciar sesión."
    except sqlite3.IntegrityError:
        conn.close()
        return False, "⚠️ Ese nombre de usuario ya está registrado. Elige otro."

def verificar_credenciales_bd(usuario, password):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, usuario, nombre_completo
        FROM usuarios
        WHERE usuario = ? AND password_hash = ?
    """, (usuario.strip().lower(), encriptar_password(password)))
    fila = cursor.fetchone()
    conn.close()
    if fila:
        return {"id": fila[0], "usuario": fila[1], "nombre_completo": fila[2]}
    return None

# ================= GESTIÓN Y VISUALIZACIÓN DE ARCHIVOS PDF =================
def abrir_pdf_en_computador(ruta_pdf):
    ruta_absoluta = os.path.abspath(ruta_pdf)
    if os.path.exists(ruta_absoluta):
        try:
            if sys.platform == "win32":
                os.startfile(ruta_absoluta)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", ruta_absoluta])
            else:
                subprocess.Popen(["xdg-open", ruta_absoluta])
            return True
        except Exception:
            return False
    return False

def mostrar_visor_pdf_en_pantalla(ruta_pdf):
    if os.path.exists(ruta_pdf):
        with open(ruta_pdf, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode("utf-8")
        visor_html = f"""
            <iframe src="data:application/pdf;base64,{base64_pdf}" 
                    width="100%" height="620px" type="application/pdf"
                    style="border: 1px solid #cbd5e1; border-radius: 8px;">
            </iframe>
        """
        st.markdown(visor_html, unsafe_allow_html=True)

# ================= VALIDACIÓN ÓPTICA DE NITIDEZ =================
def evaluar_nitidez_imagen(imagen_pil, umbral=50.0):
    gris = imagen_pil.convert("L")
    gris.thumbnail((600, 600))
    arr = np.asarray(gris, dtype=np.float64)

    if arr.shape[0] < 3 or arr.shape[1] < 3:
        return 100.0, True

    laplaciano = (
        -4 * arr[1:-1, 1:-1]
        + arr[:-2, 1:-1] + arr[2:, 1:-1]
        + arr[1:-1, :-2] + arr[1:-1, 2:]
    )
    puntaje = float(np.var(laplaciano))
    es_nitida = puntaje >= umbral
    return round(puntaje, 1), es_nitida

# ================= GENERADOR DE INFORME TÉCNICO PDF =================
def limpiar_texto_pdf(texto):
    if not texto:
        return ""
    return str(texto).encode("latin-1", "replace").decode("latin-1")

def generar_pdf_inspeccion(proyecto, direccion, inspector, fecha_insp, estado, lista_espacios):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, limpiar_texto_pdf("INFORME TECNICO DE INSPECCION Y PATOLOGIA ESTRUCTURAL"), ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, limpiar_texto_pdf(f"Fecha de emision: {datetime.now().strftime('%Y-%m-%d %H:%M')}"), ln=True, align="C")
    pdf.ln(5)

    pdf.set_fill_color(230, 238, 248)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, limpiar_texto_pdf("1. INFORMACION GENERAL DEL PROYECTO / INMUEBLE"), ln=True, fill=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, limpiar_texto_pdf(f"Proyecto / Edificacion: {proyecto}"), ln=True)
    pdf.cell(0, 6, limpiar_texto_pdf(f"Localizacion / Direccion: {direccion}"), ln=True)
    pdf.cell(0, 6, limpiar_texto_pdf(f"Profesional Responsable: {inspector}   |   Fecha: {fecha_insp}   |   Dictamen: {estado}"), ln=True)
    pdf.cell(0, 6, limpiar_texto_pdf(f"Total de puntos / sectores registrados: {len(lista_espacios)}"), ln=True)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, limpiar_texto_pdf("2. REGISTRO FOTOGRAFICO Y ESPECIFICACIONES POR SECTOR"), ln=True, fill=True)
    pdf.ln(4)

    for idx, item in enumerate(lista_espacios, start=1):
        if pdf.get_y() > 195:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(30, 58, 138)
        pdf.cell(0, 8, limpiar_texto_pdf(f"Registro #{idx}: {item['nombre_espacio']} - {item['fachada_ubicacion']}"), ln=True)
        pdf.set_text_color(0, 0, 0)

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, limpiar_texto_pdf(f"Longitud Aproximada: {item['longitud_aprox']}   |   Validacion de Imagen: {item['estado_foto']}"), ln=True)

        if item["datos_personalizados"].strip():
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, limpiar_texto_pdf("Parametros y mediciones adicionales:"), ln=True)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, limpiar_texto_pdf(item["datos_personalizados"]))

        if item["observaciones"].strip():
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, limpiar_texto_pdf("Observaciones tecnicas:"), ln=True)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, limpiar_texto_pdf(item["observaciones"]))

        if os.path.exists(item["ruta_foto"]):
            try:
                pdf.ln(2)
                pdf.image(item["ruta_foto"], w=95)
            except Exception:
                pdf.cell(0, 6, limpiar_texto_pdf("[Imagen no disponible]"), ln=True)

        pdf.ln(6)
        pdf.set_draw_color(210, 210, 210)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(4)

    nombre_archivo = f"Informe_Tecnico_{int(datetime.now().timestamp())}.pdf"
    ruta_completa = os.path.join(CARPETA_PDFS, nombre_archivo)
    pdf.output(ruta_completa)
    return ruta_completa

# ================= OPERACIONES DE BASE DE DATOS =================
def guardar_inspeccion_bd(proyecto, direccion, inspector, fecha_insp, estado, lista_espacios, ruta_pdf):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO inspecciones (proyecto, direccion, inspector, fecha, estado, total_espacios, ruta_pdf)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (proyecto, direccion, inspector, str(fecha_insp), estado, len(lista_espacios), ruta_pdf))
    inspeccion_id = cursor.lastrowid

    for item in lista_espacios:
        cursor.execute("""
            INSERT INTO espacios_inspeccion (
                inspeccion_id, nombre_espacio, fachada_ubicacion, longitud_aprox,
                datos_personalizados, observaciones, nitidez_puntaje, estado_foto, ruta_foto
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            inspeccion_id,
            item["nombre_espacio"],
            item["fachada_ubicacion"],
            item["longitud_aprox"],
            item["datos_personalizados"],
            item["observaciones"],
            item["nitidez_puntaje"],
            item["estado_foto"],
            item["ruta_foto"]
        ))

    conn.commit()
    conn.close()

def eliminar_inspeccion_bd(inspeccion_id):
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM espacios_inspeccion WHERE inspeccion_id = ?", (inspeccion_id,))
    cursor.execute("DELETE FROM inspecciones WHERE id = ?", (inspeccion_id,))
    conn.commit()
    conn.close()

def obtener_inspecciones_bd():
    conn = obtener_conexion()
    df = pd.read_sql_query("SELECT * FROM inspecciones ORDER BY id DESC", conn)
    conn.close()
    return df

def obtener_espacios_por_inspeccion(inspeccion_id):
    conn = obtener_conexion()
    df = pd.read_sql_query("SELECT * FROM espacios_inspeccion WHERE inspeccion_id = ?", conn, params=(inspeccion_id,))
    conn.close()
    return df

# ================= VARIABLES DE SESIÓN =================
if "usuario_activo" not in st.session_state:
    st.session_state.usuario_activo = None
if "sectores_actuales" not in st.session_state:
    st.session_state.sectores_actuales = []
if "atributos_extra" not in st.session_state:
    st.session_state.atributos_extra = []
if "contador_sector" not in st.session_state:
    st.session_state.contador_sector = 1
if "cam_id" not in st.session_state:
    st.session_state.cam_id = 0
if "datos_edicion" not in st.session_state:
    st.session_state.datos_edicion = None
if "ver_pdf_actual" not in st.session_state:
    st.session_state.ver_pdf_actual = False
if "vista_actual" not in st.session_state:
    st.session_state.vista_actual = "registro"
if "camara_encendida" not in st.session_state:
    st.session_state.camara_encendida = False
if "modo_captura" not in st.session_state:
    st.session_state.modo_captura = "camara"

# ==============================================================================
# PANTALLA DE ACCESO: INICIAR SESIÓN O CREAR CUENTA (SI NO HA ENTRADO)
# ==============================================================================
if st.session_state.usuario_activo is None:
    st.write("")
    st.write("")
    col_esp1, col_login, col_esp2 = st.columns([1, 1.3, 1])

    with col_login:
        st.markdown("""
        <div class="login-header" translate="no">
            <h2>🏗️ CivilCheck Pro</h2>
            <p>Sistema de Inspección Técnica y Patología Estructural</p>
        </div>
        """, unsafe_allow_html=True)

        with st.container(border=True):
            tab_entrar, tab_crear = st.tabs([
                "🔑 Iniciar Sesión",
                "➕ Crear Cuenta Nueva"
            ])

            # --- PESTAÑA 1: INICIAR SESIÓN ---
            with tab_entrar:
                st.subheader("Acceso al Sistema")
                with st.form("form_login"):
                    user_login = st.text_input("👤 Usuario", placeholder="Ingresa tu usuario")
                    pass_login = st.text_input("🔒 Contraseña", type="password", placeholder="Ingresa tu contraseña")
                    btn_entrar = st.form_submit_button("🚀 Entrar a la Plataforma", type="primary", use_container_width=True)

                    if btn_entrar:
                        if not user_login.strip() or not pass_login.strip():
                            st.error("⚠️ Ingresa tu usuario y contraseña.")
                        else:
                            datos_usuario = verificar_credenciales_bd(user_login, pass_login)
                            if datos_usuario:
                                st.session_state.usuario_activo = datos_usuario
                                st.rerun()
                            else:
                                st.error("❌ Usuario o contraseña incorrectos.")

            # --- PESTAÑA 2: CREAR CUENTA ---
            with tab_crear:
                st.subheader("Registro de Nuevo Usuario")
                with st.form("form_registro", clear_on_submit=True):
                    nombre_reg = st.text_input("👷 Nombre Completo (Ingeniero / Profesional) *", placeholder="Ej: Ing. Carlos Andrés Gómez")
                    user_reg = st.text_input("👤 Crear Nombre de Usuario *", placeholder="Ej: cgomez")
                    pass_reg1 = st.text_input("🔒 Crear Contraseña *", type="password", placeholder="Mínimo 4 caracteres")
                    pass_reg2 = st.text_input("🔒 Confirmar Contraseña *", type="password", placeholder="Repite la contraseña")
                    btn_registrar = st.form_submit_button("✅ Crear Cuenta", type="primary", use_container_width=True)

                    if btn_registrar:
                        if not nombre_reg.strip() or not user_reg.strip() or not pass_reg1.strip():
                            st.error("⚠️ Todos los campos son obligatorios.")
                        elif len(pass_reg1.strip()) < 4:
                            st.error("⚠️ La contraseña debe tener al menos 4 caracteres.")
                        elif pass_reg1 != pass_reg2:
                            st.error("⚠️ Las contraseñas no coinciden.")
                        else:
                            exito, mensaje = registrar_usuario_bd(user_reg, nombre_reg, pass_reg1)
                            if exito:
                                st.success(mensaje)
                            else:
                                st.error(mensaje)

    st.stop()

# ==============================================================================
# APLICACIÓN PRINCIPAL (SOLO VISIBLE PARA USUARIOS AUTENTICADOS)
# ==============================================================================
usuario_info = st.session_state.usuario_activo

# Barra superior con información del usuario activo y botón para Cerrar Sesión
col_banner, col_user = st.columns([3.8, 1.2])
with col_banner:
    st.markdown("""
    <div class="hero-banner" translate="no">
        <h1>🏗️ CivilCheck Pro — Sistema de Inspección Técnica y Patología Estructural</h1>
        <p>Plataforma de levantamiento fotográfico, control dimensional y emisión de informes técnicos en formato PDF.</p>
    </div>
    """, unsafe_allow_html=True)

with col_user:
    with st.container(border=True):
        st.markdown(f"👷 **{usuario_info['nombre_completo']}**")
        st.caption(f"Usuario activo: `{usuario_info['usuario']}`")
        if st.button("🔒 Cerrar Sesión", use_container_width=True):
            st.session_state.usuario_activo = None
            st.session_state.camara_encendida = False
            st.rerun()

nav1, nav2, nav3 = st.columns(3)
with nav1:
    if st.button("📸 REGISTRO DE INSPECCIÓN", type="primary" if st.session_state.vista_actual == "registro" else "secondary", use_container_width=True):
        st.session_state.vista_actual = "registro"
        st.rerun()
with nav2:
    df_total = obtener_inspecciones_bd()
    if st.button(f"📂 REPOSITORIO DOCUMENTAL PDF ({len(df_total)})", type="primary" if st.session_state.vista_actual == "archivos" else "secondary", use_container_width=True):
        st.session_state.vista_actual = "archivos"
        st.rerun()
with nav3:
    if st.button("📊 INDICADORES Y CONTROL", type="primary" if st.session_state.vista_actual == "panel" else "secondary", use_container_width=True):
        st.session_state.vista_actual = "panel"
        st.rerun()

st.write("")

# ================= VISTA 1: REGISTRO DE INSPECCIÓN =================
if st.session_state.vista_actual == "registro":

    if "ultimo_pdf" in st.session_state and os.path.exists(st.session_state.ultimo_pdf):
        with st.container(border=True):
            st.success("✅ **Informe Técnico PDF generado y almacenado en la base de datos.**")
            b_pdf1, b_pdf2, b_pdf3, b_pdf4 = st.columns(4)
            with b_pdf1:
                if st.button("📂 Abrir Documento PDF", type="primary", use_container_width=True):
                    if not abrir_pdf_en_computador(st.session_state.ultimo_pdf):
                        st.info("Utilice la opción '👁️ Visualizar en Pantalla'.")
            with b_pdf2:
                if st.button("👁️ Visualizar en Pantalla", use_container_width=True):
                    st.session_state.ver_pdf_actual = not st.session_state.ver_pdf_actual
            with b_pdf3:
                with open(st.session_state.ultimo_pdf, "rb") as f_pdf:
                    st.download_button(
                        label="📥 Descargar PDF",
                        data=f_pdf,
                        file_name=os.path.basename(st.session_state.ultimo_pdf),
                        mime="application/pdf",
                        use_container_width=True
                    )
            with b_pdf4:
                if st.button("➕ Nuevo Levantamiento", use_container_width=True):
                    del st.session_state.ultimo_pdf
                    st.session_state.ver_pdf_actual = False
                    st.rerun()

            if st.session_state.ver_pdf_actual:
                mostrar_visor_pdf_en_pantalla(st.session_state.ultimo_pdf)

    editando = st.session_state.datos_edicion
    if editando:
        st.info(f"✏️ **Edición de Registro Activa:** Modificando parámetros o imagen de **{editando['nombre_espacio']}**.")

    col_izquierda, col_derecha = st.columns([1.15, 1.15], gap="large")

    # ---------------- MÓDULO 1: CAPTURA DE EVIDENCIA ----------------
    with col_izquierda:
        with st.container(border=True):
            st.markdown('<span class="module-badge">Módulo 1 · Captura de Evidencia</span>', unsafe_allow_html=True)
            st.subheader(f"📷 Registro Visual — Punto #{len(st.session_state.sectores_actuales) + 1}")

            btn_modo1, btn_modo2 = st.columns(2)
            with btn_modo1:
                if st.button("📸 TOMAR FOTO (Cámara)", type="primary" if st.session_state.modo_captura == "camara" else "secondary", use_container_width=True):
                    st.session_state.modo_captura = "camara"
                    st.session_state.camara_encendida = True
            with btn_modo2:
                if st.button("📁 SUBIR IMAGEN", type="primary" if st.session_state.modo_captura == "archivo" else "secondary", use_container_width=True):
                    st.session_state.modo_captura = "archivo"

            archivo_imagen = None

            if st.session_state.modo_captura == "camara":
                if not st.session_state.camara_encendida:
                    if st.button("🔴 ACTIVAR CÁMARA Y TOMAR FOTO AHORA", type="primary", use_container_width=True):
                        st.session_state.camara_encendida = True
                        st.rerun()
                else:
                    archivo_imagen = st.camera_input(
                        "Capturar fotografía",
                        key=f"cam_estable_{st.session_state.cam_id}",
                        label_visibility="collapsed"
                    )
            else:
                archivo_imagen = st.file_uploader(
                    "Seleccionar archivo de imagen (JPG, PNG)",
                    type=["jpg", "jpeg", "png"],
                    key=f"file_estable_{st.session_state.cam_id}"
                )

            imagen_lista_pil = None
            puntaje_nitidez = 0.0
            foto_aprobada = False
            estado_foto_texto = "OK"

            if archivo_imagen is not None:
                imagen_lista_pil = Image.open(archivo_imagen).convert("RGB")
            elif editando and os.path.exists(editando["ruta_foto"]):
                st.image(editando["ruta_foto"], caption="Evidencia fotográfica actual", width=280)
                imagen_lista_pil = Image.open(editando["ruta_foto"]).convert("RGB")

            if imagen_lista_pil is not None:
                puntaje_nitidez, es_nitida = evaluar_nitidez_imagen(imagen_lista_pil, umbral=50.0)

                if es_nitida:
                    st.markdown(f'<div class="ok-box" translate="no">✅ VALIDACIÓN ÓPTICA: OK — Imagen nítida (Índice: {puntaje_nitidez})</div>', unsafe_allow_html=True)
                    foto_aprobada = True
                    estado_foto_texto = f"OK ({puntaje_nitidez})"
                else:
                    st.markdown(f'<div class="warn-box" translate="no">⚠️ ALERTA DE ENFOQUE — Nitidez baja detectada (Índice: {puntaje_nitidez})</div>', unsafe_allow_html=True)
                    confirmar_manual = st.checkbox("✅ Aprobar imagen manualmente (OK)")
                    if confirmar_manual:
                        foto_aprobada = True
                        estado_foto_texto = f"OK Manual ({puntaje_nitidez})"

                if st.button("🔄 Descartar y Capturar Nuevamente", type="secondary", use_container_width=True):
                    if editando:
                        st.session_state.datos_edicion["ruta_foto"] = ""
                    st.session_state.cam_id += 1
                    st.session_state.camara_encendida = True
                    st.rerun()

    # ---------------- MÓDULO 2: ESPECIFICACIONES TÉCNICAS ----------------
    with col_derecha:
        with st.container(border=True):
            st.markdown('<span class="module-badge">Módulo 2 · Especificaciones Técnicas</span>', unsafe_allow_html=True)
            st.subheader("📝 Identificación y Parámetros del Sector")

            valor_nombre = editando["nombre_espacio"] if editando else f"Sector {st.session_state.contador_sector:02d}"
            valor_longitud = editando["longitud_aprox"] if editando else ""
            valor_obs = editando["observaciones"] if editando else ""

            nombre_espacio = st.text_input(
                "📍 Identificador del Área / Sector / Elemento *",
                value=valor_nombre,
                placeholder="Ej: Sector 01, Zona Norte, Muro Eje B"
            )

            col_long, col_fach = st.columns(2)
            with col_long:
                longitud_aprox = st.text_input(
                    "📏 Longitud Aproximada *",
                    value=valor_longitud,
                    placeholder="Ej: 2.40 m / 85 cm"
                )
            with col_fach:
                lista_ubicaciones = [
                    "Muro Fachada",
                    "Muro Interior / Divisorio",
                    "Elemento Estructural (Columna / Viga)",
                    "Losa / Placa de Entrepiso",
                    "Piso / Contrapiso",
                    "✍️ Escribir manualmente..."
                ]

                valor_previo_ubicacion = editando["fachada_ubicacion"] if editando else "Muro Fachada"
                if valor_previo_ubicacion in lista_ubicaciones[:-1]:
                    idx_f = lista_ubicaciones.index(valor_previo_ubicacion)
                    texto_manual_previo = ""
                elif editando:
                    idx_f = len(lista_ubicaciones) - 1
                    texto_manual_previo = valor_previo_ubicacion
                else:
                    idx_f = 0
                    texto_manual_previo = ""

                seleccion_ubicacion = st.selectbox("🧱 Componente / Ubicación *", lista_ubicaciones, index=idx_f)

                if seleccion_ubicacion == "✍️ Escribir manualmente...":
                    fachada_ubicacion = st.text_input(
                        "✍️ Escriba el Componente / Ubicación *",
                        value=texto_manual_previo,
                        placeholder="Ej: Muro Culata, Cubierta, Escalera..."
                    )
                else:
                    fachada_ubicacion = seleccion_ubicacion

            st.markdown("---")
            st.markdown("**➕ Parámetros Técnicos Adicionales**")

            c_dato1, c_dato2, c_boton = st.columns([1.2, 1.3, 0.8])
            with c_dato1:
                campo_personal = st.text_input("Parámetro / Variable", placeholder="Ej: Dimensión / Espesor fisura")
            with c_dato2:
                valor_personal = st.text_input("Valor / Medición", placeholder="Ej: 3.20m x 2.40m / 1.5 mm")
            with c_boton:
                st.write("")
                st.write("")
                if st.button("➕ Agregar", use_container_width=True):
                    if campo_personal.strip() and valor_personal.strip():
                        st.session_state.atributos_extra.append(f"- {campo_personal.strip()}: {valor_personal.strip()}")
                        st.rerun()

            texto_atributos = "\n".join(st.session_state.atributos_extra)
            datos_personalizados = st.text_area(
                "📋 Registro de Parámetros y Dimensiones:",
                value=texto_atributos,
                height=85,
                placeholder="Detalle de dimensiones, espesores, patologías o variables adicionales..."
            )

            observaciones = st.text_area(
                "📝 Concepto / Observaciones Técnicas:",
                value=valor_obs,
                height=68,
                placeholder="Descripción técnica del hallazgo o condición estructural..."
            )

            st.write("")
            if st.button("✅ CONFIRMAR OK Y REGISTRAR SECTOR", type="primary", use_container_width=True):
                if imagen_lista_pil is None:
                    st.error("⚠️ Se requiere evidencia fotográfica para registrar el punto.")
                elif not foto_aprobada:
                    st.error("⚠️ La imagen aún no cuenta con validación 'OK'.")
                elif not nombre_espacio.strip() or not longitud_aprox.strip():
                    st.error("⚠️ Complete el Identificador del Sector y la Longitud Aproximada.")
                elif not fachada_ubicacion.strip():
                    st.error("⚠️ Escriba o seleccione el Componente / Ubicación.")
                else:
                    nombre_foto = f"evidencia_{int(datetime.now().timestamp())}_{len(st.session_state.sectores_actuales)+1}.jpg"
                    ruta_foto_guardada = os.path.join(CARPETA_FOTOS, nombre_foto)
                    imagen_lista_pil.save(ruta_foto_guardada, "JPEG", quality=90)

                    st.session_state.sectores_actuales.append({
                        "nombre_espacio": nombre_espacio.strip(),
                        "fachada_ubicacion": fachada_ubicacion.strip(),
                        "longitud_aprox": longitud_aprox.strip(),
                        "datos_personalizados": datos_personalizados.strip(),
                        "observaciones": observaciones.strip(),
                        "nitidez_puntaje": puntaje_nitidez,
                        "estado_foto": estado_foto_texto,
                        "ruta_foto": ruta_foto_guardada
                    })

                    st.session_state.atributos_extra = []
                    st.session_state.datos_edicion = None
                    st.session_state.contador_sector = len(st.session_state.sectores_actuales) + 1
                    st.session_state.cam_id += 1
                    st.session_state.camara_encendida = True
                    st.rerun()

    # ---------------- MÓDULO 3: CONSOLIDADO Y EMISIÓN DOCUMENTAL ----------------
    st.write("")
    with st.container(border=True):
        col_tit_res, col_btn_reiniciar = st.columns([3, 1])
        with col_tit_res:
            st.markdown('<span class="module-badge">Módulo 3 · Consolidado y Emisión Documental</span>', unsafe_allow_html=True)
            st.subheader(f"📑 Puntos de Inspección Registrados ({len(st.session_state.sectores_actuales)})")
        with col_btn_reiniciar:
            if len(st.session_state.sectores_actuales) > 0:
                if st.button("🔄 Reiniciar Levantamiento", use_container_width=True):
                    st.session_state.sectores_actuales = []
                    st.session_state.atributos_extra = []
                    st.session_state.contador_sector = 1
                    st.session_state.datos_edicion = None
                    st.session_state.cam_id += 1
                    st.rerun()

        if len(st.session_state.sectores_actuales) == 0:
            st.info("No existen puntos registrados en el levantamiento actual.")
        else:
            cols_tarjetas = st.columns(3)
            for i, c_item in enumerate(st.session_state.sectores_actuales):
                with cols_tarjetas[i % 3]:
                    with st.container(border=True):
                        if os.path.exists(c_item["ruta_foto"]):
                            st.image(c_item["ruta_foto"], use_container_width=True)
                        st.markdown(f"#### {i+1}. {c_item['nombre_espacio']}")
                        st.write(f"🧱 **Componente:** {c_item['fachada_ubicacion']}")
                        st.write(f"📏 **Longitud:** {c_item['longitud_aprox']}  |  📷 **{c_item['estado_foto']}**")
                        if c_item["datos_personalizados"]:
                            st.text(c_item["datos_personalizados"])
                        if c_item["observaciones"]:
                            st.caption(f"📝 {c_item['observaciones']}")

                        btn_c1, btn_c2 = st.columns(2)
                        with btn_c1:
                            if st.button("✏️ Editar / Imagen", key=f"corr_{i}", use_container_width=True):
                                item_corregir = st.session_state.sectores_actuales.pop(i)
                                st.session_state.datos_edicion = item_corregir
                                st.session_state.atributos_extra = (
                                    item_corregir["datos_personalizados"].split("\n")
                                    if item_corregir["datos_personalizados"] else []
                                )
                                st.session_state.cam_id += 1
                                st.rerun()
                        with btn_c2:
                            if st.button("🗑️ Eliminar", key=f"quitar_{i}", use_container_width=True):
                                st.session_state.sectores_actuales.pop(i)
                                st.rerun()

            st.divider()
            st.markdown("### 📄 Emisión de Informe Técnico (PDF)")
            with st.form("form_final_pdf"):
                f1, f2, f3, f4 = st.columns(4)
                with f1:
                    proyecto = st.text_input("🏢 Proyecto / Inmueble *", placeholder="Ej: Edificio Mirador / Bloque B")
                with f2:
                    direccion = st.text_input("📍 Localización / Dirección *", placeholder="Ej: Calle 45 # 12-30")
                with f3:
                    # Se rellena automáticamente con el nombre del usuario que inició sesión
                    inspector = st.text_input("👷 Profesional Responsable *", value=usuario_info["nombre_completo"])
                with f4:
                    estado_insp = st.selectbox("⚖️ Dictamen Técnico", ["Afectación Leve", "Requiere Intervención", "Revisión Estructural Prioritaria", "Sin Afectación Crítica"])

                guardar_todo = st.form_submit_button("💾 GENERAR Y ALMACENAR INFORME TÉCNICO (PDF)", type="primary", use_container_width=True)

                if guardar_todo:
                    if not proyecto.strip() or not direccion.strip() or not inspector.strip():
                        st.error("⚠️ Complete los campos obligatorios del Proyecto, Localización y Profesional Responsable.")
                    else:
                        ruta_pdf = generar_pdf_inspeccion(
                            proyecto.strip(),
                            direccion.strip(),
                            inspector.strip(),
                            date.today(),
                            estado_insp,
                            st.session_state.sectores_actuales
                        )
                        guardar_inspeccion_bd(
                            proyecto.strip(),
                            direccion.strip(),
                            inspector.strip(),
                            date.today(),
                            estado_insp,
                            st.session_state.sectores_actuales,
                            ruta_pdf
                        )
                        st.session_state.sectores_actuales = []
                        st.session_state.atributos_extra = []
                        st.session_state.contador_sector = 1
                        st.session_state.datos_edicion = None
                        st.session_state.ultimo_pdf = ruta_pdf
                        st.session_state.ver_pdf_actual = True
                        st.rerun()

# ================= VISTA 2: REPOSITORIO DOCUMENTAL PDF =================
elif st.session_state.vista_actual == "archivos":
    st.subheader("📂 Repositorio Compartido de Informes Técnicos (PDF)")
    df_insp = obtener_inspecciones_bd()

    if len(df_insp) == 0:
        st.info("No se encuentran informes registrados en la base de datos.")
    else:
        busq = st.text_input("🔍 Filtrar por Proyecto, Localización o Profesional Responsable:")
        if busq:
            df_insp = df_insp[
                df_insp["proyecto"].str.contains(busq, case=False, na=False) |
                df_insp["direccion"].str.contains(busq, case=False, na=False) |
                df_insp["inspector"].str.contains(busq, case=False, na=False)
            ]

        for _, fila in df_insp.iterrows():
            with st.container(border=True):
                c_info, c_botones = st.columns([2.2, 2])
                with c_info:
                    st.markdown(f"### 🏢 {fila['proyecto']} — *{fila['estado']}*")
                    st.write(f"📍 **Localización:** {fila['direccion']} | 👷 **Responsable:** {fila['inspector']} | 📅 **Fecha:** {fila['fecha']}")
                    st.caption(f"🔢 Sectores / Puntos evaluados: **{fila['total_espacios']}**")

                with c_botones:
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        if st.button("📂 Abrir PDF", key=f"open_{fila['id']}", type="primary", use_container_width=True):
                            if not abrir_pdf_en_computador(fila["ruta_pdf"]):
                                st.info("Despliegue abajo '👁️ Visualizar Documento PDF'.")
                    with b2:
                        if os.path.exists(fila["ruta_pdf"]):
                            with open(fila["ruta_pdf"], "rb") as pdf_file:
                                st.download_button(
                                    label="📥 Descargar",
                                    data=pdf_file,
                                    file_name=f"Informe_{fila['proyecto'].replace(' ', '_')}_{fila['id']}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_{fila['id']}",
                                    use_container_width=True
                                )
                    with b3:
                        if st.button("✏️ Modificar", key=f"redo_{fila['id']}", use_container_width=True):
                            df_esp = obtener_espacios_por_inspeccion(fila["id"])
                            sectores_rec = []
                            for _, esp in df_esp.iterrows():
                                sectores_rec.append({
                                    "nombre_espacio": esp["nombre_espacio"],
                                    "fachada_ubicacion": esp["fachada_ubicacion"],
                                    "longitud_aprox": esp["longitud_aprox"],
                                    "datos_personalizados": esp["datos_personalizados"] or "",
                                    "observaciones": esp["observaciones"] or "",
                                    "nitidez_puntaje": esp["nitidez_puntaje"],
                                    "estado_foto": esp["estado_foto"],
                                    "ruta_foto": esp["ruta_foto"]
                                })
                            eliminar_inspeccion_bd(fila["id"])
                            st.session_state.sectores_actuales = sectores_rec
                            st.session_state.contador_sector = len(sectores_rec) + 1
                            st.session_state.vista_actual = "registro"
                            st.rerun()

                with st.expander("👁️ Visualizar Documento PDF en Pantalla"):
                    if os.path.exists(fila["ruta_pdf"]):
                        mostrar_visor_pdf_en_pantalla(fila["ruta_pdf"])

# ================= VISTA 3: INDICADORES Y CONTROL =================
elif st.session_state.vista_actual == "panel":
    st.subheader("📊 Indicadores Generales de Inspección")
    df_insp = obtener_inspecciones_bd()

    m1, m2, m3 = st.columns(3)
    m1.metric("🏢 Proyectos / Inmuebles Evaluados", len(df_insp))
    total_c = int(df_insp["total_espacios"].sum()) if len(df_insp) > 0 else 0
    m2.metric("📷 Total de Sectores / Puntos Registrados", total_c)
    urg = len(df_insp[df_insp["estado"] == "Revisión Estructural Prioritaria"]) if len(df_insp) > 0 else 0
    m3.metric("⚠️ Revisiones Estructurales Prioritarias", urg)

    st.divider()
    if len(df_insp) > 0:
        st.dataframe(df_insp[["id", "proyecto", "direccion", "inspector", "fecha", "estado", "total_espacios"]], use_container_width=True, hide_index=True)
