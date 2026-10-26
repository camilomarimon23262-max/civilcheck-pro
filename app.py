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

# Instalar automáticamente la librería de PDF (fpdf2) si no está instalada
try:
    from fpdf import FPDF
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fpdf2"])
    from fpdf import FPDF

# ================= CONFIGURACIÓN DE LA PÁGINA =================
st.set_page_config(
    page_title="CivilCheck - Inspección de Fisuras y Edificaciones",
    page_icon="🏗️",
    layout="wide"
)

# Estilos visuales para hacer la interfaz más clara, grande y fácil de usar
st.markdown("""
    <style>
    .stButton > button {
        font-weight: 600;
        border-radius: 8px;
        padding: 0.55rem 1rem;
    }
    .paso-titulo {
        background-color: #1e3a8a;
        color: white;
        padding: 10px 16px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 1.1rem;
        margin-bottom: 12px;
    }
    </style>
""", unsafe_allow_html=True)

# Carpetas para guardar fotos y PDFs generados
CARPETA_FOTOS = "fotos_inspecciones"
CARPETA_PDFS = "pdfs_informes"
os.makedirs(CARPETA_FOTOS, exist_ok=True)
os.makedirs(CARPETA_PDFS, exist_ok=True)

# ================= BASE DE DATOS MULTIUSUARIO (SQLite WAL) =================
DB_PATH = "ingenieria_inspecciones.db"

def obtener_conexion():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def inicializar_bd():
    conn = obtener_conexion()
    cursor = conn.cursor()
    # Forzar actualización recreando la tabla de usuarios si no tiene la estructura
    cursor.execute("DROP TABLE IF EXISTS usuarios;")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
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

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ================= CONTROL DE SESIÓN DE USUARIO =================
if "usuario_logueado" not in st.session_state:
    st.session_state.usuario_logueado = None

# Si el usuario NO ha iniciado sesión, mostrar pantalla de autenticación
if not st.session_state.usuario_logueado:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1.3, 1])
    with col2:
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center;'>🏗️ CivilCheck Pro</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: gray;'>Sistema de Inspección Técnica y Patología Estructural</p>", unsafe_allow_html=True)
            
            tab_login, tab_registro = st.tabs(["🔑 Iniciar Sesión", "➕ Crear Cuenta Nueva"])

            with tab_login:
                with st.form("form_login"):
                    user_input = st.text_input("Usuario", placeholder="Ingresa tu usuario")
                    pass_input = st.text_input("Contraseña", type="password", placeholder="Ingresa tu contraseña")
                    btn_ingresar = st.form_submit_button("🚀 Entrar a la Plataforma", type="primary", use_container_width=True)

                    if btn_ingresar:
                        if not user_input.strip() or not pass_input.strip():
                            st.error("⚠️ Por favor completa usuario y contraseña.")
                        else:
                            conn = obtener_conexion()
                            cursor = conn.cursor()
                            cursor.execute("SELECT password FROM usuarios WHERE usuario = ?", (user_input.strip(),))
                            resultado = cursor.fetchone()
                            conn.close()

                            if resultado and resultado[0] == hash_password(pass_input):
                                st.session_state.usuario_logueado = user_input.strip()
                                st.success("✅ ¡Bienvenido!")
                                st.rerun()
                            else:
                                st.error("❌ Usuario o contraseña incorrectos.")

            with tab_registro:
                with st.form("form_registro"):
                    new_user = st.text_input("Nuevo Usuario", placeholder="Elige un nombre de usuario")
                    new_pass = st.text_input("Nueva Contraseña", type="password", placeholder="Elige una contraseña")
                    btn_crear = st.form_submit_button("✨ Registrar Cuenta", use_container_width=True)

                    if btn_crear:
                        if not new_user.strip() or not new_pass.strip():
                            st.error("⚠️ Completa los campos para registrarte.")
                        else:
                            try:
                                conn = obtener_conexion()
                                cursor = conn.cursor()
                                cursor.execute("INSERT INTO usuarios (usuario, password) VALUES (?, ?)", 
                                             (new_user.strip(), hash_password(new_pass)))
                                conn.commit()
                                conn.close()
                                st.success("🎉 Cuenta creada con éxito. Ya puedes iniciar sesión en la otra pestaña.")
                            except sqlite3.IntegrityError:
                                st.error("⚠️ Ese nombre de usuario ya existe. Prueba con otro.")
    st.stop()  # Detiene la ejecución aquí hasta que el usuario inicie sesión


# ================= GUARDADO DE IMAGEN EN ALTA CALIDAD =================
def guardar_imagen_alta_calidad(imagen_pil, ruta_destino):
    """Guarda la fotografía conservando la máxima nitidez y detalle para inspección de fisuras."""
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

# ================= GENERADOR DE ARCHIVOS PDF =================
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

    # 2. Detalle por Cuarto / Fachada
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, limpiar_texto_pdf("2. REGISTRO FOTOGRAFICO Y MEDICIONES POR ZONA / FACHADA"), ln=True, fill=True)
    pdf.ln(4)

    for idx, item in enumerate(lista_espacios, start=1):
        if pdf.get_y() > 180:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(30, 58, 138)
        pdf.cell(0, 8, limpiar_texto_pdf(f"Zona #{idx}: {item['nombre_espacio']} - {item['fachada_ubicacion']}"), ln=True)
        pdf.set_text_color(0, 0, 0)

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, limpiar_texto_pdf(f"Longitud aproximada registrada: {item['longitud_aprox']}"), ln=True)

        if item["datos_personalizados"].strip():
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, limpiar_texto_pdf("Medidas y datos adicionales:"), ln=True)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, limpiar_texto_pdf(item["datos_personalizados"]))

        if item["observaciones"].strip():
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, limpiar_texto_pdf("Observaciones tecnicas:"), ln=True)
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

# ================= FUNCIONES DE BASE DE DATOS =================
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
    st.title("🏗️ CivilCheck")
    st.caption(f"👤 Usuario: **{st.session_state.usuario_logueado}**")
    st.divider()

    menu = st.radio(
        "📍 ¿Qué deseas hacer?",
        [
            "📸 Nueva Inspección (Cámara)",
            "📁 Abrir / Ver Informes PDF",
            "📊 Panel de Control"
        ],
        index=["📸 Nueva Inspección (Cámara)", "📁 Abrir / Ver Informes PDF", "📊 Panel de Control"].index(st.session_state.menu_activo)
    )
    st.session_state.menu_activo = menu

    st.divider()
    st.info(f"🏠 **Zonas guardadas:** {len(st.session_state.cuartos_actuales)}")

    if len(st.session_state.cuartos_actuales) > 0:
        if st.button("🗑️ Borrar borrador actual", use_container_width=True):
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

# ================= VISTA 1: NUEVA INSPECCIÓN CON CÁMARA =================
if menu == "📸 Nueva Inspección (Cámara)":
    st.title("📸 Crear Informe de Inspección")
    st.caption("Sigue los 3 pasos en orden para armar y descargar tu informe en PDF.")

    if "ultimo_pdf" in st.session_state and os.path.exists(st.session_state.ultimo_pdf):
        with st.container(border=True):
            st.success("🎉 **¡Tu informe PDF se ha creado con éxito!** Elige una opción abajo:")
            col_op1, col_op2, col_op3 = st.columns(3)

            with col_op1:
                with open(st.session_state.ultimo_pdf, "rb") as f_pdf:
                    st.download_button(
                        label="📥 1. DESCARGAR PDF",
                        data=f_pdf,
                        file_name=os.path.basename(st.session_state.ultimo_pdf),
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )

            with col_op2:
                if st.button("👁️ 2. Ver PDF en pantalla", use_container_width=True):
                    st.session_state.ver_pdf_actual = not st.session_state.ver_pdf_actual

            with col_op3:
                if st.button("➕ 3. Empezar informe nuevo", use_container_width=True):
                    del st.session_state.ultimo_pdf
                    st.session_state.ver_pdf_actual = False
                    st.rerun()

            if st.session_state.ver_pdf_actual:
                st.markdown("#### 📄 Vista previa de tu informe PDF:")
                mostrar_visor_pdf_en_pantalla(st.session_state.ultimo_pdf)

    editando = st.session_state.datos_edicion
    if editando:
        st.warning(f"✏️ **Modo Corrección:** Estás modificando los datos o la foto de **{editando['nombre_espacio']}**.")

    col_cam, col_datos = st.columns([1.1, 1.2])

    with col_cam:
        with st.container(border=True):
            st.markdown(f'<div class="paso-titulo">PASO 1: Fotografía del Espacio #{len(st.session_state.cuartos_actuales) + 1}</div>', unsafe_allow_html=True)
            
            metodo_foto = st.radio(
                "Elige cómo agregar la foto:",
                ["📷 Tomar foto con la Cámara", "🖼️ Subir foto desde la Galería"],
                horizontal=True
            )

            archivo_imagen = None
            if metodo_foto == "📷 Tomar foto con la Cámara":
                archivo_imagen = st.camera_input(
                    "Apunta a la fisura o muro y presiona capturar",
                    key=f"camara_{st.session_state.cam_id}"
                )
            else:
                archivo_imagen = st.file_uploader(
                    "Elige una imagen de tu galería o PC",
                    type=["jpg", "jpeg", "png", "webp"],
                    key=f"uploader_{st.session_state.cam_id}"
                )

            imagen_lista_pil = None
            if archivo_imagen is not None:
                imagen_lista_pil = Image.open(archivo_imagen).convert("RGB")
            elif editando and os.path.exists(editando["ruta_foto"]):
                st.caption("📷 *Fotografía actual:*")
                st.image(editando["ruta_foto"], use_container_width=True)
                imagen_lista_pil = Image.open(editando["ruta_foto"]).convert("RGB")

            if imagen_lista_pil is not None:
                st.success("✅ Fotografía cargada en alta resolución.")
                if st.button("🔄 Tomar otra foto diferente", use_container_width=True):
                    if editando:
                        st.session_state.datos_edicion["ruta_foto"] = ""
                    st.session_state.cam_id += 1
                    st.rerun()

    with col_datos:
        with st.container(border=True):
            st.markdown(f'<div class="paso-titulo">PASO 2: Datos del Espacio #{len(st.session_state.cuartos_actuales) + 1}</div>', unsafe_allow_html=True)

            valor_nombre = editando["nombre_espacio"] if editando else f"Cuarto {st.session_state.contador_cuarto}"
            valor_longitud = editando["longitud_aprox"] if editando else ""
            valor_obs = editando["observaciones"] if editando else ""

            nombre_espacio = st.text_input(
                "1️⃣ Nombre del cuarto o lugar (Obligatorio) *",
                value=valor_nombre,
                placeholder="Ej: Sala, Alcoba Principal..."
            )

            c1, c2 = st.columns(2)
            with c1:
                longitud_aprox = st.text_input(
                    "2️⃣ Longitud o medida (Obligatorio) *",
                    value=valor_longitud,
                    placeholder="Ej: 1.50 m / 45 cm"
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
                fachada_ubicacion = st.selectbox("3️⃣ Ubicación exacta *", lista_fachadas, index=idx_fachada)

            observaciones = st.text_area(
                "4️⃣ Observaciones o descripción (Opcional):",
                value=valor_obs,
                height=80,
                placeholder="Ej: Humedad visible, fisura diagonal..."
            )

            with st.expander("➕ ¿Deseas agregar más medidas específicas?"):
                col_k, col_v, col_b = st.columns([1.2, 1.2, 0.8])
                with col_k:
                    nuevo_campo_nombre = st.text_input("Dato", placeholder="Ej: Ancho de fisura")
                with col_v:
                    nuevo_campo_valor = st.text_input("Medida", placeholder="Ej: 2 mm")
                with col_b:
                    st.write("")
                    st.write("")
                    if st.button("➕ Añadir"):
                        if nuevo_campo_nombre.strip() and nuevo_campo_valor.strip():
                            st.session_state.atributos_extra.append(f"- {nuevo_campo_nombre.strip()}: {nuevo_campo_valor.strip()}")
                            st.rerun()

                texto_inicial_atributos = "\n".join(st.session_state.atributos_extra)
                datos_personalizados = st.text_area(
                    "Medidas adicionales:",
                    value=texto_inicial_atributos,
                    height=68,
                    placeholder="Ej: - Espesor: 2 mm"
                )

            st.write("")
            if st.button("✅ GUARDAR ESTE ESPACIO EN EL INFORME", type="primary", use_container_width=True):
                if imagen_lista_pil is None:
                    st.error("⚠️ Falta el PASO 1: Toma la foto con la cámara o súbela de tu galería.")
                elif not nombre_espacio.strip():
                    st.error("⚠️ Falta escribir el nombre del cuarto o lugar.")
                elif not longitud_aprox.strip():
                    st.error("⚠️ Falta escribir la longitud o medida aproximada.")
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
                    st.toast("✅ Espacio guardado en alta calidad")
                    st.rerun()

    st.divider()
    with st.container(border=True):
        st.markdown(f'<div class="paso-titulo">PASO 3: Revisar Espacios ({len(st.session_state.cuartos_actuales)}) y Crear PDF</div>', unsafe_allow_html=True)

        if len(st.session_state.cuartos_actuales) == 0:
            st.info("👆 Todavía no has agregado ningún espacio. Completa el **PASO 1** y el **PASO 2** arriba.")
        else:
            cols_preview = st.columns(3)
            for i, cuarto in enumerate(st.session_state.cuartos_actuales):
                with cols_preview[i % 3]:
                    with st.container(border=True):
                        if os.path.exists(cuarto["ruta_foto"]):
                            st.image(cuarto["ruta_foto"], use_container_width=True)
                        st.markdown(f"**{i+1}. {cuarto['nombre_espacio']}**")
                        st.caption(f"📍 {cuarto['fachada_ubicacion']} | 📏 Medida: **{cuarto['longitud_aprox']}**")
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
                            if st.button("🗑️ Borrar", key=f"del_{i}", use_container_width=True):
                                st.session_state.cuartos_actuales.pop(i)
                                st.rerun()

            st.markdown("---")
            st.markdown("#### 📄 Datos Finales de la Edificación")
            with st.form("form_cerrar_inspeccion"):
                f1, f2, f3, f4 = st.columns(4)
                with f1:
                    proyecto = st.text_input("Casa / Edificio *", placeholder="Ej: Casa Familia Pérez")
                with f2:
                    direccion = st.text_input("Dirección *", placeholder="Ej: Calle 10 # 15-20")
                with f3:
                    inspector = st.text_input("Inspector *", placeholder="Tu nombre")
                with f4:
                    estado_insp = st.selectbox("Concepto General", ["Con Fisuras Leves", "Requiere Reparación", "Revisión Estructural Urgente", "Sin Novedad Crítica"])

                boton_generar_pdf = st.form_submit_button("📄 FINALIZAR Y CREAR ARCHIVO PDF", type="primary", use_container_width=True)

                if boton_generar_pdf:
                    if not proyecto.strip() or not direccion.strip() or not inspector.strip():
                        st.error("⚠️ Completa los datos de la Casa/Edificio, Dirección e Inspector.")
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

# ================= VISTA 2: ABRIR, VER O REHACER INFORMES PDF =================
elif menu == "📁 Abrir / Ver Informes PDF":
    st.title("📁 Historial de Informes PDF")
    df_insp = obtener_inspecciones_bd()

    if len(df_insp) == 0:
        st.info("Todavía no hay informes guardados.")
    else:
        busq = st.text_input("🔍 Buscar informe:")
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
                    st.caption(f"🔢 Zonas: **{fila['total_espacios']}**")

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
                        if st.button("✏️ Editar Informe", key=f"redo_{fila['id']}", use_container_width=True):
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

                with st.expander("👁️ Ver PDF en pantalla"):
                    if os.path.exists(fila["ruta_pdf"]):
                        mostrar_visor_pdf_en_pantalla(fila["ruta_pdf"])

# ================= VISTA 3: PANEL DE CONTROL =================
elif menu == "📊 Panel de Control":
    st.title("📊 Resumen General de Inspecciones")
    df_insp = obtener_inspecciones_bd()

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Informes PDF", len(df_insp))
    total_cuartos = int(df_insp["total_espacios"].sum()) if len(df_insp) > 0 else 0
    c2.metric("Total Zonas Fotografiadas", total_cuartos)
    urgentes = len(df_insp[df_insp["estado"] == "Revisión Estructural Urgente"]) if len(df_insp) > 0 else 0
    c3.metric("Revisiones Urgentes", urgentes)

    st.divider()
    if len(df_insp) > 0:
        st.dataframe(df_insp[["id", "proyecto", "direccion", "inspector", "fecha", "estado", "total_espacios"]], use_container_width=True, hide_index=True)
