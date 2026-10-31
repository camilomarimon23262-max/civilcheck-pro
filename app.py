import os
import base64
import sqlite3
import hashlib
from datetime import datetime
import streamlit as st
from PIL import Image
from fpdf import FPDF

st.set_page_config(page_title="CivilCheck Pro", page_icon="🏗️", layout="centered")

DB_NAME = "ingenieria_inspecciones.db"
IMG_DIR = "evidencias_hd"
os.makedirs(IMG_DIR, exist_ok=True)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.strip().encode("utf-8")).hexdigest()


def inicializar_bd():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            usuario TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            nombre_completo TEXT NOT NULL
        )
    """)
    cursor.execute("PRAGMA table_info(usuarios)")
    columnas = [col[1] for col in cursor.fetchall()]
    if "password_hash" not in columnas:
        cursor.execute("DROP TABLE usuarios")
        cursor.execute("""
            CREATE TABLE usuarios (
                usuario TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                nombre_completo TEXT NOT NULL
            )
        """)

    cursor.execute(
        "INSERT OR IGNORE INTO usuarios (usuario, password_hash, nombre_completo) VALUES (?, ?, ?)",
        ("admin", hash_password("1234"), "Administrador")
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inspecciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto TEXT NOT NULL,
            inspector TEXT NOT NULL,
            fecha TEXT NOT NULL,
            zona TEXT NOT NULL,
            ubicacion TEXT NOT NULL,
            medida TEXT NOT NULL,
            observaciones TEXT,
            ruta_imagen TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def guardar_imagen_alta_calidad(archivo_subido, ruta_destino):
    imagen_pil = Image.open(archivo_subido)
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


def generar_pdf_informe(proyecto, inspector, zonas):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_fill_color(30, 58, 138)
    pdf.rect(0, 0, 210, 26, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", "B", 15)
    pdf.cell(0, 12, "CIVILCHECK PRO - INFORME TECNICO DE INSPECCION", ln=True, align="C")

    pdf.ln(10)
    pdf.set_text_color(30, 41, 59)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 7, f"Proyecto / Inmueble: {proyecto}", ln=True)
    pdf.cell(0, 7, f"Inspector Responsable: {inspector}", ln=True)
    pdf.cell(0, 7, f"Fecha de Emision: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.ln(4)

    for idx, z in enumerate(zonas, start=1):
        if pdf.get_y() > 185:
            pdf.add_page()
        pdf.set_font("Arial", "B", 12)
        pdf.set_text_color(30, 58, 138)
        pdf.cell(0, 8, f"Zona #{idx}: {z['zona']} ({z['ubicacion']})", ln=True)

        pdf.set_font("Arial", "", 10)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 6, f"Medida: {z['medida']}", ln=True)
        if z["observaciones"]:
            pdf.multi_cell(0, 6, f"Observaciones: {z['observaciones']}")

        if os.path.exists(z["ruta_imagen"]):
            pdf.ln(2)
            pdf.image(z["ruta_imagen"], x=15, w=130)
            pdf.ln(6)

    nombre_pdf = f"Informe_{proyecto.replace(' ', '_')}.pdf"
    pdf.output(nombre_pdf)
    return nombre_pdf


inicializar_bd()

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "usuario_activo" not in st.session_state:
    st.session_state.usuario_activo = ""
if "nombre_activo" not in st.session_state:
    st.session_state.nombre_activo = ""
if "zonas_actuales" not in st.session_state:
    st.session_state.zonas_actuales = []
if "indice_edicion" not in st.session_state:
    st.session_state.indice_edicion = -1

if not st.session_state.autenticado:
    st.title("🏗️ CivilCheck Pro")
    st.caption("Sistema de Inspección Técnica y Patología Estructural")

    tab_login, tab_registro = st.tabs(["🔑 Iniciar Sesión", "➕ Crear Cuenta Nueva"])

    with tab_login:
        with st.container(border=True):
            usr_login = st.text_input("👤 Usuario", value="admin", key="login_usr")
            pwd_login = st.text_input("🔒 Contraseña", value="1234", type="password", key="login_pwd")
            if st.button("🚀 Entrar a la Plataforma", use_container_width=True):
                u_clean = usr_login.strip().lower()
                p_hash = hash_password(pwd_login)
                conn = sqlite3.connect(DB_NAME)
                cur = conn.cursor()
                cur.execute(
                    "SELECT nombre_completo FROM usuarios WHERE LOWER(usuario)=? AND password_hash=?",
                    (u_clean, p_hash)
                )
                fila = cur.fetchone()
                conn.close()
                if fila:
                    st.session_state.autenticado = True
                    st.session_state.usuario_activo = u_clean
                    st.session_state.nombre_activo = fila[0]
                    st.rerun()
                else:
                    st.error("⚠️ Usuario o contraseña incorrectos.")

    with tab_registro:
        with st.container(border=True):
            nom_reg = st.text_input("👷 Nombre Completo *", placeholder="Ej: Ing. Camilo Marimón")
            usr_reg = st.text_input("👤 Nuevo Nombre de Usuario *", placeholder="Ej: camilo2")
            pwd_reg = st.text_input("🔒 Crear Contraseña *", type="password")
            if st.button("✨ Guardar Cuenta y Entrar Ahora", use_container_width=True):
                if not nom_reg.strip() or not usr_reg.strip() or not pwd_reg.strip():
                    st.warning("⚠️ Completa todos los campos para registrar la cuenta.")
                else:
                    u_clean = usr_reg.strip().lower()
                    p_hash = hash_password(pwd_reg)
                    conn = sqlite3.connect(DB_NAME)
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT OR REPLACE INTO usuarios (usuario, password_hash, nombre_completo) VALUES (?, ?, ?)",
                        (u_clean, p_hash, nom_reg.strip())
                    )
                    conn.commit()
                    conn.close()
                    st.session_state.autenticado = True
                    st.session_state.usuario_activo = u_clean
                    st.session_state.nombre_activo = nom_reg.strip()
                    st.rerun()
else:
    col_titulo, col_salir = st.columns([3, 1])
    with col_titulo:
        st.markdown(f"**👷 Usuario activo:** {st.session_state.nombre_activo} (`{st.session_state.usuario_activo}`)")
    with col_salir:
        if st.button("🔒 Cerrar Sesión", use_container_width=True):
            st.session_state.autenticado = False
            st.session_state.usuario_activo = ""
            st.session_state.nombre_activo = ""
            st.rerun()

    st.title("🏗️ CivilCheck Pro - Panel de Inspección")

    zona_editando = None
    if st.session_state.indice_edicion >= 0:
        zona_editando = st.session_state.zonas_actuales[st.session_state.indice_edicion]
        st.info(f"✏️ Editando Zona #{st.session_state.indice_edicion + 1}: {zona_editando['zona']}")

    with st.container(border=True):
        st.subheader("PASO 1: Evidencia Fotográfica")
        modo_captura = st.radio(
            "Método de captura:",
            ["📁 Subir archivo / Galería", "📸 Tomar Foto (Activar Cámara)"],
            horizontal=True
        )
        if modo_captura == "📸 Tomar Foto (Activar Cámara)":
            foto = st.camera_input("Capturar evidencia")
        else:
            foto = st.file_uploader("Seleccionar imagen", type=["jpg", "jpeg", "png"])

    with st.container(border=True):
        st.subheader("PASO 2: Datos del Espacio")
        val_nombre = zona_editando["zona"] if zona_editando else ""
        val_medida = zona_editando["medida"] if zona_editando else ""
        val_obs = zona_editando["observaciones"] if zona_editando else ""

        zona_nombre = st.text_input("1️⃣ Nombre del lugar *", value=val_nombre, placeholder="Ej: Sala, Habitación Principal")
        medida = st.text_input("2️⃣ Longitud o medida *", value=val_medida, placeholder="Ej: 1.50 m")

        opciones_ubi = ["Muro", "Fachada", "Columna / Viga", "Losa / Techo", "Piso", "✍️ Escribir manualmente..."]
        ubicacion_sel = st.selectbox("3️⃣ Fachada / Ubicación *", opciones_ubi)
        if ubicacion_sel == "✍️ Escribir manualmente...":
            ubicacion_final = st.text_input("Ubicación manual *", placeholder="Ej: Balcón, Escalera...")
        else:
            ubicacion_final = ubicacion_sel

        observaciones = st.text_area("4️⃣ Observaciones (Opcional)", value=val_obs, placeholder="Humedad, tipo de fisura...")

        texto_boton = "💾 GUARDAR CAMBIOS DE ESTA ZONA" if zona_editando else "✅ GUARDAR ESTE ESPACIO"
        if st.button(texto_boton, use_container_width=True):
            if (not foto and not zona_editando) or not zona_nombre.strip() or not medida.strip() or not ubicacion_final.strip():
                st.warning("⚠️ Completa la fotografía, el nombre del lugar, la ubicación y la medida.")
            else:
                if foto:
                    ruta_img = os.path.join(IMG_DIR, f"evidencia_{int(datetime.now().timestamp())}.jpg")
                    guardar_imagen_alta_calidad(foto, ruta_img)
                else:
                    ruta_img = zona_editando["ruta_imagen"]

                nuevo_registro = {
                    "zona": zona_nombre.strip(),
                    "ubicacion": ubicacion_final.strip(),
                    "medida": medida.strip(),
                    "observaciones": observaciones.strip(),
                    "ruta_imagen": ruta_img
                }

                if st.session_state.indice_edicion >= 0:
                    st.session_state.zonas_actuales[st.session_state.indice_edicion] = nuevo_registro
                    st.session_state.indice_edicion = -1
                    st.success("✅ Zona actualizada correctamente.")
                else:
                    st.session_state.zonas_actuales.append(nuevo_registro)
                    st.success("✅ Espacio guardado correctamente.")
                st.rerun()

        if zona_editando:
            if st.button("❌ Cancelar Edición", use_container_width=True):
                st.session_state.indice_edicion = -1
                st.rerun()

    with st.container(border=True):
        st.subheader(f"PASO 3: Revisión y Descarga de PDF ({len(st.session_state.zonas_actuales)} zonas)")

        for idx, z in enumerate(st.session_state.zonas_actuales):
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                with c1:
                    st.markdown(f"**{idx + 1}. {z['zona']}**  \n📍 {z['ubicacion']} | 📏 {z['medida']}")
                    if z["observaciones"]:
                        st.caption(f"📝 {z['observaciones']}")
                with c2:
                    if st.button("✏️ Editar", key=f"edit_{idx}", use_container_width=True):
                        st.session_state.indice_edicion = idx
                        st.rerun()
                with c3:
                    if st.button("🗑️ Borrar", key=f"del_{idx}", use_container_width=True):
                        st.session_state.zonas_actuales.pop(idx)
                        st.rerun()

        proyecto = st.text_input("🏢 Casa / Edificio *", placeholder="Ej: Casa Familia Pérez")
        inspector = st.text_input("👷 Inspector *", value=st.session_state.nombre_activo)

        if st.button("📄 GENERAR Y DESCARGAR PDF", use_container_width=True):
            if not proyecto.strip() or not inspector.strip() or not st.session_state.zonas_actuales:
                st.warning("⚠️ Completa el nombre del proyecto, el inspector y agrega al menos una zona.")
            else:
                archivo_pdf = generar_pdf_informe(proyecto.strip(), inspector.strip(), st.session_state.zonas_actuales)
                with open(archivo_pdf, "rb") as f:
                    pdf_bytes = f.read()
                st.download_button(
                    label="📥 Descargar copia del PDF",
                    data=pdf_bytes,
                    file_name=archivo_pdf,
                    mime="application/pdf",
                    use_container_width=True
                )
                b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
                visor_html = f'<iframe src="data:application/pdf;base64,{b64_pdf}" width="100%" height="500px" type="application/pdf"></iframe>'
                st.markdown(visor_html, unsafe_allow_html=True)

        if st.session_state.zonas_actuales:
            if st.button("🔄 Volver a hacer el informe desde cero", use_container_width=True):
                st.session_state.zonas_actuales = []
                st.session_state.indice_edicion = -1
                st.rerun()
