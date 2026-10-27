import streamlit as st
import sqlite3
import pandas as pd
from PIL import Image
from datetime import date, datetime
import os
import sys
import subprocess
import base64
import hashlib

# Instalar automáticamente la librería de PDF (fpdf2) si no está instalada
try:
    from fpdf import FPDF
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fpdf2"])
    from fpdf import FPDF

# ================= CONFIGURACIÓN DE LA PÁGINA =================
st.set_page_config(
    page_title="CivilCheck Pro - Inspección Técnica",
    page_icon="🏗️",
    layout="wide"
)

# Estilos visuales para el banner de acceso y la interfaz paso a paso
st.markdown("""
    <style>
    .stButton > button {
        font-weight: 600;
        border-radius: 8px;
        padding: 0.6rem 1rem;
    }
    .banner-login {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%);
        color: white;
        padding: 28px 20px;
        border-radius: 14px;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    .banner-login h1 {
        color: white;
        margin: 0;
        font-size: 2rem;
    }
    .banner-login p {
        color: #cbd5e1;
        margin-top: 8px;
        font-size: 0.95rem;
    }
    .paso-titulo {
        background-color: #1e3a8a;
        color: white;
        padding: 10px 16px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 1.08rem;
        margin-bottom: 14px;
    }
    </style>
""", unsafe_allow_html=True)

CARPETA_FOTOS = "fotos_inspecciones"
CARPETA_PDFS = "pdfs_informes"
os.makedirs(CARPETA_FOTOS, exist_ok=True)
os.makedirs(CARPETA_PDFS, exist_ok=True)

# ================= BASE DE DATOS MULTIUSUARIO (SIN ERRORES DE ESTRUCTURA) =================
DB_PATH = "ingenieria_inspecciones.db"

def obtener_conexion():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def hash_password(password):
    return hashlib.sha256(str(password).strip().encode("utf-8")).hexdigest()

def inicializar_bd():
    conn = obtener_conexion()
    cursor = conn.cursor()

    # 1. Verificar estructura exacta de la tabla 'usuarios' sin borrar cuentas en cada recarga
    cursor.execute("PRAGMA table_info(usuarios);")
    cols_usuarios = [col[1] for col in cursor.fetchall()]
    cols_req_usuarios = {"id", "usuario", "nombre_completo", "password_hash", "fecha_creacion"}

    if not cols_req_usuarios.issubset(set(cols_usuarios)):
        usuarios_previos = []
        if "usuario" in cols_usuarios and "password_hash" in cols_usuarios:
            try:
                cursor.execute("SELECT usuario, password_hash FROM usuarios;")
                usuarios_previos = [(u, u, p) for u, p in cursor.fetchall()]
            except Exception:
                pass
        elif "usuario" in cols_usuarios and "password" in cols_usuarios:
            try:
                cursor.execute("SELECT usuario, password FROM usuarios;")
                usuarios_previos = [(u, u, p) for u, p in cursor.fetchall()]
            except Exception:
                pass

        cursor.execute("DROP TABLE IF EXISTS usuarios;")
        cursor.execute("""
            CREATE TABLE usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT UNIQUE NOT NULL,
                nombre_completo TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                fecha_creacion TEXT NOT NULL
            )
        """)
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
        for u, nom, p_hash in usuarios_previos:
            if u and p_hash:
                cursor.execute(
                    "INSERT OR IGNORE INTO usuarios (usuario, nombre_completo, password_hash, fecha_creacion) VALUES (?, ?, ?, ?)",
                    (str(u).strip().lower(), str(nom).strip(), p_hash, ahora)
                )

    # Asegurar usuario de respaldo 'admin' (clave: 1234) sin afectar otras cuentas
    cursor.execute(
        "INSERT OR IGNORE INTO usuarios (usuario, nombre_completo, password_hash, fecha_creacion) VALUES (?, ?, ?, ?)",
        ("admin", "Administrador", hash_password("1234"), datetime.now().strftime("%Y-%m-%d %H:%M"))
    )

    # 2. Verificar estructura de 'inspecciones'
    cursor.execute("PRAGMA table_info(inspecciones);")
    cols_insp = [col[1] for col in cursor.fetchall()]
    cols_req_insp = {"id", "proyecto", "direccion", "inspector", "fecha", "estado", "total_espacios", "ruta_pdf"}
    if not cols_req_insp.issubset(set(cols_insp)):
        cursor.execute("DROP TABLE IF EXISTS espacios_inspeccion;")
        cursor.execute("DROP TABLE IF EXISTS inspecciones;")
        cursor.execute("""
            CREATE TABLE inspecciones (
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

    # 3. Verificar estructura de 'espacios_inspeccion'
    cursor.execute("PRAGMA table_info(espacios_inspeccion);")
    cols_esp = [col[1] for col in cursor.fetchall()]
    cols_req_esp = {
        "id", "inspeccion_id", "nombre_espacio", "fachada_ubicacion",
        "longitud_aprox", "datos_personalizados", "observaciones",
        "nitidez_puntaje", "estado_foto", "ruta_foto"
    }
    if not cols_req_esp.issubset(set(cols_esp)):
        cursor.execute("DROP TABLE IF EXISTS espacios_inspeccion;")
        cursor.execute("""
            CREATE TABLE espacios_inspeccion (
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

# ================= FUNCIONES DE AUTENTICACIÓN =================
def registrar_o_actualizar_usuario_bd(usuario, nombre_completo, password):
    u_limpio = usuario.strip().lower()
    nom_limpio = nombre_completo.strip() if nombre_completo.strip() else u_limpio
    p_hash = hash_password(password)
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")

    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE LOWER(usuario) = ?", (u_limpio,))
    existe = cursor.fetchone()

    if existe:
        # Si ya existía el usuario, actualiza su contraseña para que nunca quede bloqueado
        cursor.execute(
            "UPDATE usuarios SET password_hash = ?, nombre_completo = ? WHERE LOWER(usuario) = ?",
            (p_hash, nom_limpio, u_limpio)
        )
    else:
        cursor.execute(
            "INSERT INTO usuarios (usuario, nombre_completo, password_hash, fecha_creacion) VALUES (?, ?, ?, ?)",
            (u_limpio, nom_limpio, p_hash, ahora)
        )
    conn.commit()
    conn.close()
    return u_limpio

def verificar_credenciales_bd(usuario, password):
    u_limpio = usuario.strip().lower()
    p_hash = hash_password(password)
    conn = obtener_conexion()
    cursor = conn.cursor()
    cursor.execute("SELECT usuario, password_hash FROM usuarios WHERE LOWER(usuario) = ?", (u_limpio,))
    fila = cursor.fetchone()
    conn.close()
    if fila and fila[1] == p_hash:
        return fila[0]
    return None

# ================= PANTALLA DE ACCESO (LOGIN / REGISTRO) =================
if "usuario_logueado" not in st.session_state:
    st.session_state.usuario_logueado = None

if not st.session_state.usuario_logueado:
    col_izq, col_centro, col_der = st.columns([1, 1.5, 1])
    with col_centro:
        st.markdown("""
            <div class="banner-login">
                <h1>🏗️ CivilCheck Pro</h1>
                <p>Sistema de Inspección Técnica y Patología Estructural</p>
            </div>
        """, unsafe_allow_html=True)

        with st.container(border=True):
            tab_login, tab_registro = st.tabs(["🔑 Iniciar Sesión", "➕ Crear Cuenta Nueva"])

            with tab_login:
                st.markdown("### Acceso al Sistema")
                with st.form("form_login"):
                    user_input = st.text_input("👤 Usuario", placeholder="Ingresa tu usuario (ej: camilo2 o admin)")
                    pass_input = st.text_input("🔒 Contraseña", type="password", placeholder="Ingresa tu contraseña")
                    btn_ingresar = st.form_submit_button("🚀 Entrar a la Plataforma", type="primary", use_container_width=True)

                    if btn_ingresar:
                        if not user_input.strip() or not pass_input.strip():
                            st.error("⚠️ Escribe tu usuario y tu contraseña.")
                        else:
                            usuario_valido = verificar_credenciales_bd(user_input, pass_input)
                            if usuario_valido:
                                st.session_state.usuario_logueado = usuario_valido
                                st.rerun()
                            else:
                                st.error("❌ Usuario o contraseña incorrectos. Si olvidaste tu clave, entra a la pestaña '➕ Crear Cuenta Nueva' y escríbela de nuevo para actualizarla.")

                st.caption("💡 *Acceso rápido de respaldo: Usuario **`admin`** | Contraseña **`1234`***")

            with tab_registro:
                st.markdown("### Crear o Actualizar tu Cuenta")
                st.caption("Crea un usuario nuevo (o escribe tu usuario actual para asignarle una contraseña nueva) y entrarás automáticamente.")
                with st.form("form_registro"):
                    new_user = st.text_input("👤 Nombre de Usuario *", placeholder="Ej: camilo2")
                    new_nombre = st.text_input("👷 Nombre del Ingeniero / Inspector (Opcional)", placeholder="Ej: Ing. Camilo Marimón")
                    new_pass = st.text_input("🔒 Contraseña *", type="password", placeholder="Escribe tu contraseña")
                    btn_crear = st.form_submit_button("✨ Guardar Cuenta y Entrar Ahora", type="primary", use_container_width=True)

                    if btn_crear:
                        if not new_user.strip() or not new_pass.strip():
                            st.error("⚠️ Escribe un nombre de usuario y una contraseña.")
                        else:
                            usuario_creado = registrar_o_actualizar_usuario_bd(new_user, new_nombre, new_pass)
                            st.session_state.usuario_logueado = usuario_creado
                            st.success("🎉 ¡Cuenta guardada con éxito! Entrando al sistema...")
                            st.rerun()
    st.stop()

# ================= GUARDADO DE IMAGEN EN ALTA CALIDAD (300 DPI) =================
def guardar_imagen_alta_calidad(imagen_pil, ruta_destino):
    """Guarda la fotografía en máxima calidad (98%, 300 DPI, sin pérdida de nitidez en grietas)."""
    if imagen_pil.mode in ("RGBA", "P"):
        imagen_pil = imagen_pil.convert("RGB")
    imagen_pil.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
    imagen_pil.save(
        ruta_destino,
        format="JPEG",
        quality=98,
        subsampling=0,
        optimize=True,
        dpi=(300, 300)
    )

# ================= FUNCIONES PARA ABRIR Y VER EL ARCHIVO PDF =================
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
                    width="100%" height="650px" type="application/pdf"
                    style="border: 1px solid #cbd5e1; border-radius: 8px;">
            </iframe>
        """
        st.markdown(visor_html, unsafe_allow_html=True)

# ================= GENERADOR DE ARCHIVOS PDF (SIN ETIQUETA DE IMAGEN NÍTIDA) =================
def limpiar_texto_pdf(texto):
    if not texto:
        return ""
    return str(texto).encode("latin-1", "replace").decode("latin-1")

def generar_pdf_inspeccion(proyecto, direccion, inspector, fecha_insp, estado, lista_espacios):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Encabezado
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, limpiar_texto_pdf("INFORME TECNICO DE INSPECCION DE FISURAS"), ln=True, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, limpiar_texto_pdf(f"Generado el: {datetime.now().strftime('%Y-%m-%d %H:%M')}"), ln=True, align="C")
    pdf.ln(4)

    # 1. Datos Generales
    pdf.set_fill_color(240, 244, 248)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, limpiar_texto_pdf("1. DATOS GENERALES DE LA EDIFICACION / INMUEBLE"), ln=True, fill=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, limpiar_texto_pdf(f"Proyecto / Inmueble: {proyecto}"), ln=True)
    pdf.cell(0, 6, limpiar_texto_pdf(f"Direccion / Ubicacion: {direccion}"), ln=True)
    pdf.cell(0, 6, limpiar_texto_pdf(f"Ingeniero / Inspector: {inspector}   |   Fecha: {fecha_insp}   |   Estado: {estado}"), ln=True)
    pdf.cell(0, 6, limpiar_texto_pdf(f"Total de zonas registradas: {len(lista_espacios)}"), ln=True)
    pdf.ln(6)

    # 2. Registro Fotográfico y Mediciones
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, limpiar_texto_pdf("2. REGISTRO FOTOGRAFICO Y MEDICIONES POR ZONA / FACHADA"), ln=True, fill=True)
    pdf.ln(4)

    for idx, item in enumerate(lista_espacios, start=1):
        if pdf.get_y() > 180:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(30, 58, 138)
        pdf.cell(0, 8, limpiar_texto_pdf(f"Zona #{idx}: {item['nombre_espacio']} ({item['fachada_ubicacion']})"), ln=True)
        pdf.set_text_color(0, 0, 0)

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, limpiar_texto_pdf(f"Longitud o medida aproximada: {item['longitud_aprox']}"), ln=True)

        if item["datos_personalizados"].strip():
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, limpiar_texto_pdf("Medidas y datos adicionales:"), ln=True)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, limpiar_texto_pdf(item["datos_personalizados"]))

        if item["observaciones"].strip():
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, limpiar_texto_pdf("Observaciones / Descripcion:"), ln=True)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, limpiar_texto_pdf(item["observaciones"]))

        if os.path.exists(item["ruta_foto"]):
            try:
                pdf.ln(3)
                pdf.image(item["ruta_foto"], w=125)
            except Exception:
                pdf.cell(0, 6, limpiar_texto_pdf("[No se pudo incrustar la imagen]"), ln=True)

        pdf.ln(6)
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(4)

    nombre_archivo = f"Informe_{int(datetime.now().timestamp())}.pdf"
    ruta_completa = os.path.join(CARPETA_PDFS, nombre_archivo)
    pdf.output(ruta_completa)
    return ruta_completa

# ================= FUNCIONES DE BASE DE DATOS DE INSPECCIONES =================
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
            0.0,
            "",
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
if "cuartos_actuales" not in st.session_state:
    st.session_state.cuartos_actuales = []
if "atributos_extra" not in st.session_state:
    st.session_state.atributos_extra = []
if "contador_cuarto" not in st.session_state:
    st.session_state.contador_cuarto = 1
if "cam_id" not in st.session_state:
    st.session_state.cam_id = 0
if "datos_edicion" not in st.session_state:
    st.session_state.datos_edicion = None
if "ver_pdf_actual" not in st.session_state:
    st.session_state.ver_pdf_actual = False
if "menu_activo" not in st.session_state:
    st.session_state.menu_activo = "📸 Nueva Inspección (Cámara)"

# ================= BARRA LATERAL =================
with st.sidebar:
    st.title("🏗️ CivilCheck Pro")
    st.caption(f"👤 Sesión activa: **{st.session_state.usuario_logueado}**")
    st.divider()

    opciones_menu = [
        "📸 Nueva Inspección (Cámara)",
        "📁 Abrir / Ver Informes PDF",
        "📊 Panel de Control"
    ]
    menu = st.radio(
        "📍 Menú Principal",
        opciones_menu,
        index=opciones_menu.index(st.session_state.menu_activo)
    )
    st.session_state.menu_activo = menu

    st.divider()
    st.info(f"🏠 **Zonas en este informe:** {len(st.session_state.cuartos_actuales)}")

    if len(st.session_state.cuartos_actuales) > 0:
        if st.button("🗑️ Reiniciar borrador actual", use_container_width=True):
            st.session_state.cuartos_actuales = []
            st.session_state.atributos_extra = []
            st.session_state.contador_cuarto = 1
            st.session_state.datos_edicion = None
            st.session_state.cam_id += 1
            st.rerun()

    st.divider()
    if st.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state.usuario_logueado = None
        st.rerun()

# ================= VISTA 1: NUEVA INSPECCIÓN PASO A PASO =================
if menu == "📸 Nueva Inspección (Cámara)":
    st.title("📸 Crear Informe de Inspección")
    st.caption("Completa los 3 pasos en orden para registrar las fotografías en alta calidad y generar tu PDF.")

    # Cuadro de descarga cuando se acaba de crear un PDF
    if "ultimo_pdf" in st.session_state and os.path.exists(st.session_state.ultimo_pdf):
        with st.container(border=True):
            st.success("✅ **¡Tu archivo PDF fue generado con éxito!** Selecciona qué deseas hacer:")
            col_op1, col_op2, col_op3 = st.columns(3)

            with col_op1:
                with open(st.session_state.ultimo_pdf, "rb") as f_pdf:
                    st.download_button(
                        label="📥 1. DESCARGAR ARCHIVO PDF",
                        data=f_pdf,
                        file_name=os.path.basename(st.session_state.ultimo_pdf),
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )

            with col_op2:
                if st.button("👁️ 2. Ver PDF aquí en pantalla", use_container_width=True):
                    st.session_state.ver_pdf_actual = not st.session_state.ver_pdf_actual

            with col_op3:
                if st.button("➕ 3. Hacer otro informe nuevo", use_container_width=True):
                    del st.session_state.ultimo_pdf
                    st.session_state.ver_pdf_actual = False
                    st.rerun()

            if st.session_state.ver_pdf_actual:
                st.markdown("#### 📄 Vista previa del informe PDF:")
                mostrar_visor_pdf_en_pantalla(st.session_state.ultimo_pdf)

    editando = st.session_state.datos_edicion
    if editando:
        st.warning(f"✏️ **Modo Corrección:** Estás corrigiendo la foto o los datos de **{editando['nombre_espacio']}**.")

    col_cam, col_datos = st.columns([1.1, 1.2])

    # --- PASO 1: FOTOGRAFÍA ---
    with col_cam:
        with st.container(border=True):
            st.markdown(f'<div class="paso-titulo">PASO 1: Fotografía del Espacio #{len(st.session_state.cuartos_actuales) + 1}</div>', unsafe_allow_html=True)

            metodo_foto = st.radio(
                "¿Cómo deseas agregar la fotografía?",
                ["📷 Tomar foto con la Cámara", "🖼️ Subir imagen desde Galería / PC"],
                horizontal=True
            )

            archivo_imagen = None
            if metodo_foto == "📷 Tomar foto con la Cámara":
                st.caption("💡 *Apunta a la fisura o muro y toca el botón para capturar la foto.*")
                archivo_imagen = st.camera_input(
                    "Capturar fotografía",
                    key=f"camara_{st.session_state.cam_id}"
                )
            else:
                archivo_imagen = st.file_uploader(
                    "Selecciona una imagen desde tu celular o computador",
                    type=["jpg", "jpeg", "png", "webp"],
                    key=f"uploader_{st.session_state.cam_id}"
                )

            imagen_lista_pil = None
            if archivo_imagen is not None:
                imagen_lista_pil = Image.open(archivo_imagen).convert("RGB")
            elif editando and os.path.exists(editando["ruta_foto"]):
                st.caption("📷 *Fotografía guardada actualmente:*")
                st.image(editando["ruta_foto"], use_container_width=True)
                imagen_lista_pil = Image.open(editando["ruta_foto"]).convert("RGB")

            if imagen_lista_pil is not None:
                st.success("✅ Fotografía lista en alta resolución (300 DPI).")
                if st.button("🔄 Descartar y tomar otra foto", use_container_width=True):
                    if editando:
                        st.session_state.datos_edicion["ruta_foto"] = ""
                    st.session_state.cam_id += 1
                    st.rerun()

    # --- PASO 2: DATOS DEL ESPACIO ---
    with col_datos:
        with st.container(border=True):
            st.markdown(f'<div class="paso-titulo">PASO 2: Datos del Espacio #{len(st.session_state.cuartos_actuales) + 1}</div>', unsafe_allow_html=True)

            valor_nombre = editando["nombre_espacio"] if editando else f"Cuarto {st.session_state.contador_cuarto}"
            valor_longitud = editando["longitud_aprox"] if editando else ""
            valor_obs = editando["observaciones"] if editando else ""

            nombre_espacio = st.text_input(
                "1️⃣ Nombre del cuarto o espacio (Obligatorio) *",
                value=valor_nombre,
                placeholder="Ej: Cuarto 1, Sala, Fachada Principal"
            )

            c1, c2 = st.columns(2)
            with c1:
                longitud_aprox = st.text_input(
                    "2️⃣ Longitud o medida aproximada (Obligatorio) *",
                    value=valor_longitud,
                    placeholder="Ej: 2.10 m / 80 cm"
                )
            with c2:
                lista_fachadas = [
                    "Muro Interior",
                    "Fachada Principal (Frontal)",
                    "Fachada Posterior",
                    "Fachada Lateral Derecha",
                    "Fachada Lateral Izquierda",
                    "Columna / Viga Estructural",
                    "Losa / Techo / Cielo Raso",
                    "Piso / Contrapiso"
                ]
                idx_fachada = lista_fachadas.index(editando["fachada_ubicacion"]) if (editando and editando["fachada_ubicacion"] in lista_fachadas) else 0
                fachada_ubicacion = st.selectbox("3️⃣ Fachada / Ubicación *", lista_fachadas, index=idx_fachada)

            observaciones = st.text_area(
                "4️⃣ Observaciones o descripción de la fisura (Opcional):",
                value=valor_obs,
                height=75,
                placeholder="Anotaciones adicionales de la revisión..."
            )

            with st.expander("➕ Agregar medidas adicionales personalizadas (Ancho, dimensión, espesor, etc.)"):
                col_k, col_v, col_b = st.columns([1.2, 1.2, 0.8])
                with col_k:
                    nuevo_campo_nombre = st.text_input("¿Qué dato deseas agregar?", placeholder="Ej: Ancho fisura")
                with col_v:
                    nuevo_campo_valor = st.text_input("Valor", placeholder="Ej: 1.5 mm")
                with col_b:
                    st.write("")
                    st.write("")
                    if st.button("➕ Agregar"):
                        if nuevo_campo_nombre.strip() and nuevo_campo_valor.strip():
                            st.session_state.atributos_extra.append(f"- {nuevo_campo_nombre.strip()}: {nuevo_campo_valor.strip()}")
                            st.rerun()

                texto_inicial_atributos = "\n".join(st.session_state.atributos_extra)
                datos_personalizados = st.text_area(
                    "Medidas personalizadas incluidas:",
                    value=texto_inicial_atributos,
                    height=68,
                    placeholder="Ej:\n- Dimensión del muro: 4.0m x 2.4m\n- Espesor de fisura: 2 mm"
                )

            st.write("")
            if st.button("✅ GUARDAR ESTE CUARTO Y SEGUIR CON EL SIGUIENTE", type="primary", use_container_width=True):
                if imagen_lista_pil is None:
                    st.error("⚠️ Primero completa el PASO 1: Toma la foto con la cámara o sube una imagen.")
                elif not nombre_espacio.strip():
                    st.error("⚠️ Escribe el nombre del cuarto o espacio en la casilla 1️⃣.")
                elif not longitud_aprox.strip():
                    st.error("⚠️ Escribe la longitud o medida aproximada en la casilla 2️⃣.")
                else:
                    nombre_foto = f"foto_{int(datetime.now().timestamp())}_{len(st.session_state.cuartos_actuales)+1}.jpg"
                    ruta_foto_guardada = os.path.join(CARPETA_FOTOS, nombre_foto)
                    guardar_imagen_alta_calidad(imagen_lista_pil, ruta_foto_guardada)

                    st.session_state.cuartos_actuales.append({
                        "nombre_espacio": nombre_espacio.strip(),
                        "fachada_ubicacion": fachada_ubicacion,
                        "longitud_aprox": longitud_aprox.strip(),
                        "datos_personalizados": datos_personalizados.strip(),
                        "observaciones": observaciones.strip(),
                        "nitidez_puntaje": 0.0,
                        "estado_foto": "",
                        "ruta_foto": ruta_foto_guardada
                    })

                    st.session_state.atributos_extra = []
                    st.session_state.datos_edicion = None
                    st.session_state.contador_cuarto = len(st.session_state.cuartos_actuales) + 1
                    st.session_state.cam_id += 1
                    st.toast("✅ Cuarto guardado en alta calidad")
                    st.rerun()

    # --- PASO 3: REVISIÓN Y GENERACIÓN DE PDF ---
    st.divider()
    with st.container(border=True):
        st.markdown(f'<div class="paso-titulo">PASO 3: Revisar Cuartos Guardados ({len(st.session_state.cuartos_actuales)}) y Generar Informe PDF</div>', unsafe_allow_html=True)

        if len(st.session_state.cuartos_actuales) == 0:
            st.info("👆 Toma la foto del **Cuarto 1** en el PASO 1, llena sus datos en el PASO 2 y presiona **'✅ GUARDAR ESTE CUARTO'**.")
        else:
            st.caption("💡 *Si algún cuarto quedó mal, toca **'✏️ Corregir'** en su tarjeta. Cuando termines todos los cuartos, llena los datos finales abajo para crear tu PDF.*")
            cols_preview = st.columns(3)
            for i, cuarto in enumerate(st.session_state.cuartos_actuales):
                with cols_preview[i % 3]:
                    with st.container(border=True):
                        if os.path.exists(cuarto["ruta_foto"]):
                            st.image(cuarto["ruta_foto"], use_container_width=True)
                        st.markdown(f"**{i+1}. {cuarto['nombre_espacio']}**")
                        st.caption(f"📍 {cuarto['fachada_ubicacion']} | 📏 Longitud: **{cuarto['longitud_aprox']}**")
                        if cuarto["datos_personalizados"]:
                            st.text(cuarto["datos_personalizados"])
                        if cuarto["observaciones"]:
                            st.caption(f"📝 {cuarto['observaciones']}")

                        b_edit, b_del = st.columns(2)
                        with b_edit:
                            if st.button("✏️ Corregir", key=f"edit_{i}", use_container_width=True):
                                cuarto_a_corregir = st.session_state.cuartos_actuales.pop(i)
                                st.session_state.datos_edicion = cuarto_a_corregir
                                st.session_state.atributos_extra = (
                                    cuarto_a_corregir["datos_personalizados"].split("\n")
                                    if cuarto_a_corregir["datos_personalizados"] else []
                                )
                                st.session_state.cam_id += 1
                                st.rerun()
                        with b_del:
                            if st.button("🗑️ Eliminar", key=f"del_{i}", use_container_width=True):
                                st.session_state.cuartos_actuales.pop(i)
                                st.rerun()

            st.markdown("---")
            st.markdown("#### 📄 Datos Generales de la Edificación para Generar el PDF")
            with st.form("form_cerrar_inspeccion"):
                f1, f2, f3, f4 = st.columns(4)
                with f1:
                    proyecto = st.text_input("Casa / Edificio *", placeholder="Ej: Casa Familia Pérez")
                with f2:
                    direccion = st.text_input("Dirección / Ubicación *", placeholder="Ej: Cra 15 # 20-10")
                with f3:
                    inspector = st.text_input("Ingeniero / Inspector *", value=st.session_state.usuario_logueado)
                with f4:
                    estado_insp = st.selectbox(
                        "Estado General",
                        ["Con Fisuras Leves", "Requiere Reparación", "Revisión Estructural Urgente", "Sin Novedad Crítica"]
                    )

                boton_generar_pdf = st.form_submit_button("📄 GUARDAR INFORME Y GENERAR ARCHIVO PDF", type="primary", use_container_width=True)

                if boton_generar_pdf:
                    if not proyecto.strip() or not direccion.strip() or not inspector.strip():
                        st.error("⚠️ Completa el nombre de la Casa/Edificio, la Dirección y el Inspector.")
                    else:
                        ruta_pdf = generar_pdf_inspeccion(
                            proyecto.strip(),
                            direccion.strip(),
                            inspector.strip(),
                            date.today(),
                            estado_insp,
                            st.session_state.cuartos_actuales
                        )
                        guardar_inspeccion_bd(
                            proyecto.strip(),
                            direccion.strip(),
                            inspector.strip(),
                            date.today(),
                            estado_insp,
                            st.session_state.cuartos_actuales,
                            ruta_pdf
                        )
                        st.session_state.cuartos_actuales = []
                        st.session_state.atributos_extra = []
                        st.session_state.contador_cuarto = 1
                        st.session_state.datos_edicion = None
                        st.session_state.ultimo_pdf = ruta_pdf
                        st.session_state.ver_pdf_actual = True
                        st.rerun()

# ================= VISTA 2: HISTORIAL DE INFORMES PDF =================
elif menu == "📁 Abrir / Ver Informes PDF":
    st.title("📁 Archivos PDF Guardados")
    st.caption("Descarga tus informes en PDF, visualízalos en pantalla o ábrelos para corregirlos.")

    df_insp = obtener_inspecciones_bd()

    if len(df_insp) == 0:
        st.info("Todavía no hay informes guardados.")
    else:
        busq = st.text_input("🔍 Buscar informe por Casa/Edificio, Dirección o Inspector:")
        if busq:
            df_insp = df_insp[
                df_insp["proyecto"].str.contains(busq, case=False, na=False) |
                df_insp["direccion"].str.contains(busq, case=False, na=False) |
                df_insp["inspector"].str.contains(busq, case=False, na=False)
            ]

        for _, fila in df_insp.iterrows():
            with st.container(border=True):
                c_info, c_acciones = st.columns([2.2, 2])
                with c_info:
                    st.markdown(f"### 🏢 {fila['proyecto']} — *{fila['estado']}*")
                    st.write(f"📍 **Dirección:** {fila['direccion']} | 👷 **Inspector:** {fila['inspector']} | 📅 **Fecha:** {fila['fecha']}")
                    st.caption(f"🔢 Cuartos registrados: **{fila['total_espacios']}**")

                with c_acciones:
                    b1, b2 = st.columns(2)
                    with b1:
                        if os.path.exists(fila["ruta_pdf"]):
                            with open(fila["ruta_pdf"], "rb") as pdf_file:
                                st.download_button(
                                    label="📥 Descargar PDF",
                                    data=pdf_file,
                                    file_name=f"Informe_{fila['proyecto'].replace(' ', '_')}_{fila['id']}.pdf",
                                    mime="application/pdf",
                                    key=f"dl_{fila['id']}",
                                    type="primary",
                                    use_container_width=True
                                )
                    with b2:
                        if st.button("🔄 Corregir / Rehacer", key=f"redo_{fila['id']}", use_container_width=True):
                            df_esp = obtener_espacios_por_inspeccion(fila["id"])
                            cuartos_recuperados = []
                            for _, esp in df_esp.iterrows():
                                cuartos_recuperados.append({
                                    "nombre_espacio": esp["nombre_espacio"],
                                    "fachada_ubicacion": esp["fachada_ubicacion"],
                                    "longitud_aprox": esp["longitud_aprox"],
                                    "datos_personalizados": esp["datos_personalizados"] or "",
                                    "observaciones": esp["observaciones"] or "",
                                    "nitidez_puntaje": 0.0,
                                    "estado_foto": "",
                                    "ruta_foto": esp["ruta_foto"]
                                })
                            eliminar_inspeccion_bd(fila["id"])
                            st.session_state.cuartos_actuales = cuartos_recuperados
                            st.session_state.contador_cuarto = len(cuartos_recuperados) + 1
                            st.session_state.menu_activo = "📸 Nueva Inspección (Cámara)"
                            st.rerun()

                with st.expander("👁️ Visualizar el archivo PDF aquí en pantalla"):
                    if os.path.exists(fila["ruta_pdf"]):
                        mostrar_visor_pdf_en_pantalla(fila["ruta_pdf"])
                    else:
                        st.warning("El archivo PDF no se encuentra disponible.")

# ================= VISTA 3: PANEL DE CONTROL =================
elif menu == "📊 Panel de Control":
    st.title("📊 Resumen General de Inspecciones")
    df_insp = obtener_inspecciones_bd()

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Informes PDF Creados", len(df_insp))
    total_cuartos = int(df_insp["total_espacios"].sum()) if len(df_insp) > 0 else 0
    c2.metric("Total Cuartos Fotografiados", total_cuartos)
    urgentes = len(df_insp[df_insp["estado"] == "Revisión Estructural Urgente"]) if len(df_insp) > 0 else 0
    c3.metric("Revisiones Estructurales Urgentes", urgentes)

    st.divider()
    if len(df_insp) > 0:
        st.dataframe(
            df_insp[["id", "proyecto", "direccion", "inspector", "fecha", "estado", "total_espacios"]],
            use_container_width=True,
            hide_index=True
        )
