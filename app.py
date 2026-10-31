import os
import base64
import sqlite3
from datetime import datetime
import streamlit as st
from PIL import Image
from fpdf import FPDF

st.set_page_config(page_title="CivilCheck Pro", page_icon="🏗️", layout="centered")

DB_NAME = "ingenieria_inspecciones.db"
IMG_DIR = "evidencias_hd"
os.makedirs(IMG_DIR, exist_ok=True)


def inicializar_bd():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            usuario TEXT PRIMARY KEY,
            clave TEXT NOT NULL
        )
    """)
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
    cursor.execute("INSERT OR IGNORE INTO usuarios (usuario, clave) VALUES ('admin', '1234')")
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
    pdf.cell(0, 12, "CIVILCHECK PRO - INFORME TECNICO DE PATOLOGIA", ln=True, align="C")

    pdf.ln(10)
    pdf.set_text_color(30, 41, 59)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 7, f"Proyecto: {proyecto}", ln=True)
    pdf.cell(0, 7, f"Inspector: {inspector}", ln=True)
    pdf.cell(0, 7, f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.ln(4)

    for idx, z in enumerate(zonas, start=1):
        if pdf.get_y() > 185:
            pdf.add_page()
        pdf.set_font("Arial", "B", 12)
        pdf.set_text_color(30, 58, 138)
        pdf.cell(0, 8, f"Zona #{idx}: {z['zona']} ({z['ubicacion']})", ln=True)

        pdf.set_font("Arial", "", 10)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(0, 6, f"Medida registrada: {z['medida']}", ln=True)
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
if "zonas_actuales" not in st.session_state:
    st.session_state.zonas_actuales = []

if not st.session_state.autenticado:
    st.title("🏗️ CivilCheck Pro - Acceso Administrativo")
    with st.container(border=True):
        usr = st.text_input("Usuario", placeholder="admin")
        pwd = st.text_input("Contraseña", type="password", placeholder="1234")
        if st.button("🚀 Entrar a la Plataforma", use_container_width=True):
            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()
            cur.execute("SELECT * FROM usuarios WHERE usuario=? AND clave=?", (usr, pwd))
            if cur.fetchone():
                st.session_state.autenticado = True
                st.rerun()
            else:
                st.error("Credenciales incorrectas.")
            conn.close()
else:
    st.title("🏗️ CivilCheck Pro - Panel Online")
    with st.container(border=True):
        st.subheader("Paso 1: Evidencia Fotográfica y Datos de Zona")
        modo_captura = st.radio("Origen de fotografía:", ["Subir archivo / Galería", "Cámara en vivo"], horizontal=True)
        if modo_captura == "Cámara en vivo":
            foto = st.camera_input("Capturar evidencia")
        else:
            foto = st.file_uploader("Seleccionar imagen", type=["jpg", "jpeg", "png"])

        zona_nombre = st.text_input("1️⃣ Nombre del lugar *", placeholder="Ej: Sala, Columna C-2")
        medida = st.text_input("2️⃣ Longitud o medida *", placeholder="Ej: 1.80 m")
        opciones_ubi = ["Muro", "Fachada", "Columna / Viga", "Losa / Techo", "Piso", "✍️ Escribir manualmente..."]
        ubicacion_sel = st.selectbox("3️⃣ Fachada / Ubicación *", opciones_ubi)
        if ubicacion_sel == "✍️ Escribir manualmente...":
            ubicacion_final = st.text_input("Especificar ubicación manual *", placeholder="Ej: Foso de ascensor")
        else:
            ubicacion_final = ubicacion_sel
        observaciones = st.text_area("4️⃣ Observaciones técnicas", placeholder="Descripción de la patología...")

        if st.button("✅ GUARDAR ESTE ESPACIO", use_container_width=True):
            if not foto or not zona_nombre.strip() or not medida.strip() or not ubicacion_final.strip():
                st.warning("⚠️ Completa la fotografía, el nombre del lugar, la ubicación y la medida.")
            else:
                ruta_img = os.path.join(IMG_DIR, f"evidencia_{int(datetime.now().timestamp())}.jpg")
                guardar_imagen_alta_calidad(foto, ruta_img)
                st.session_state.zonas_actuales.append({
                    "zona": zona_nombre.strip(),
                    "ubicacion": ubicacion_final.strip(),
                    "medida": medida.strip(),
                    "observaciones": observaciones.strip(),
                    "ruta_imagen": ruta_img
                })
                st.success("✅ Zona agregada correctamente al informe actual.")

    with st.container(border=True):
        st.subheader(f"Paso 2: Generar Informe ({len(st.session_state.zonas_actuales)} zonas)")
        proyecto = st.text_input("Casa / Edificio *", placeholder="Ej: Edificio Altos del Parque")
        inspector = st.text_input("Inspector *", placeholder="Tu nombre completo")

        if st.button("📄 GENERAR Y VISUALIZAR PDF", use_container_width=True):
            if not proyecto.strip() or not inspector.strip() or not st.session_state.zonas_actuales:
                st.warning("⚠️ Ingresa el proyecto, el inspector y al menos una zona registrada.")
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
