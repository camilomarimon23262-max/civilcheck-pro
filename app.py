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

# ================= FUNCIONES PARA ABRIR Y VER EL ARCHIVO PDF =================
def abrir_pdf_en_computador(ruta_pdf):
    """Abre el archivo PDF directamente con el visor predeterminado del sistema."""
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
    """Muestra el archivo PDF incrustado directamente dentro de la aplicación."""
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

# ================= DETECTOR AUTOMÁTICO DE NITIDEZ / FOTO BORROSA =================
def evaluar_nitidez_imagen(imagen_pil, umbral=60.0):
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

    # Datos Generales
    pdf.set_fill_color(240, 244, 248)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, limpiar_texto_pdf("1. DATOS GENERALES DE LA EDIFICACION / CASA"), ln=True, fill=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, limpiar_texto_pdf(f"Proyecto / Inmueble: {proyecto}"), ln=True)
    pdf.cell(0, 6, limpiar_texto_pdf(f"Direccion / Ubicacion: {direccion}"), ln=True)
    pdf.cell(0, 6, limpiar_texto_pdf(f"Ingeniero / Inspector: {inspector}   |   Fecha: {fecha_insp}   |   Estado: {estado}"), ln=True)
    pdf.cell(0, 6, limpiar_texto_pdf(f"Total de cuartos / zonas registradas: {len(lista_espacios)}"), ln=True)
    pdf.ln(6)

    # Detalle por Cuarto / Fachada
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, limpiar_texto_pdf("2. REGISTRO FOTOGRAFICO Y MEDICIONES POR CUARTO / FACHADA"), ln=True, fill=True)
    pdf.ln(4)

    for idx, item in enumerate(lista_espacios, start=1):
        if pdf.get_y() > 195:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(30, 58, 138)
        pdf.cell(0, 8, limpiar_texto_pdf(f"Espacio #{idx}: {item['nombre_espacio']} ({item['fachada_ubicacion']})"), ln=True)
        pdf.set_text_color(0, 0, 0)

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, limpiar_texto_pdf(f"Longitud aproximada: {item['longitud_aprox']}   |   Verificacion de Foto: {item['estado_foto']}"), ln=True)

        if item["datos_personalizados"].strip():
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, limpiar_texto_pdf("Datos y medidas personalizadas:"), ln=True)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, limpiar_texto_pdf(item["datos_personalizados"]))

        if item["observaciones"].strip():
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, limpiar_texto_pdf("Observaciones / Descripcion:"), ln=True)
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, limpiar_texto_pdf(item["observaciones"]))

        if os.path.exists(item["ruta_foto"]):
            try:
                pdf.ln(2)
                pdf.image(item["ruta_foto"], w=95)
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
    st.caption("Software de Inspección de Fisuras y Edificaciones")
    st.divider()

    menu = st.radio(
        "Menú Principal",
        [
            "📸 Nueva Inspección (Cámara)",
            "📁 Abrir / Ver Informes PDF",
            "📊 Panel de Control"
        ],
        index=["📸 Nueva Inspección (Cámara)", "📁 Abrir / Ver Informes PDF", "📊 Panel de Control"].index(st.session_state.menu_activo)
    )
    st.session_state.menu_activo = menu

    st.divider()
    st.caption(f"🏠 Cuartos registrados hoy: **{len(st.session_state.cuartos_actuales)}**")

    # Opción para reiniciar todo el informe si quedó mal
    if len(st.session_state.cuartos_actuales) > 0:
        if st.button("🔄 Volver a hacer el informe (Borrar borrador)", use_container_width=True):
            st.session_state.cuartos_actuales = []
            st.session_state.atributos_extra = []
            st.session_state.contador_cuarto = 1
            st.session_state.datos_edicion = None
            st.session_state.cam_id += 1
            st.rerun()

# ================= VISTA 1: NUEVA INSPECCIÓN CON CÁMARA =================
if menu == "📸 Nueva Inspección (Cámara)":
    st.header("📸 Cámara de Inspección de Fisuras y Cuartos")

    # Si se creó un PDF recientemente, mostrar opciones destacadas para ABRIR el archivo
    if "ultimo_pdf" in st.session_state and os.path.exists(st.session_state.ultimo_pdf):
        with st.container(border=True):
            st.success("✅ **¡Tu archivo PDF está listo!** ¿Qué deseas hacer con el archivo?")
            col_op1, col_op2, col_op3, col_op4 = st.columns(4)

            with col_op1:
                if st.button("📂 Abrir PDF en el computador", type="primary", use_container_width=True):
                    exito = abrir_pdf_en_computador(st.session_state.ultimo_pdf)
                    if exito:
                        st.toast("📂 Abriendo archivo PDF en tu computador...")
                    else:
                        st.info("Usa el botón '👁️ Ver PDF aquí en pantalla' o descárgalo.")

            with col_op2:
                if st.button("👁️ Ver PDF aquí en pantalla", use_container_width=True):
                    st.session_state.ver_pdf_actual = not st.session_state.ver_pdf_actual

            with col_op3:
                with open(st.session_state.ultimo_pdf, "rb") as f_pdf:
                    st.download_button(
                        label="📥 Descargar archivo PDF",
                        data=f_pdf,
                        file_name=os.path.basename(st.session_state.ultimo_pdf),
                        mime="application/pdf",
                        use_container_width=True
                    )

            with col_op4:
                if st.button("🔄 Hacer otro informe nuevo", use_container_width=True):
                    del st.session_state.ultimo_pdf
                    st.session_state.ver_pdf_actual = False
                    st.rerun()

            if st.session_state.ver_pdf_actual:
                st.markdown("#### 📄 Vista previa del archivo PDF:")
                mostrar_visor_pdf_en_pantalla(st.session_state.ultimo_pdf)

    # Valores por defecto si el usuario está corrigiendo un cuarto que quedó mal
    editando = st.session_state.datos_edicion
    if editando:
        st.info(f"✏️ **Modo Corrección:** Estás volviendo a tomar la foto o corrigiendo los datos de **{editando['nombre_espacio']}**.")

    st.subheader(f"1. Capturar Foto y Datos del Espacio #{len(st.session_state.cuartos_actuales) + 1}")

    col_cam, col_datos = st.columns([1.15, 1.15])

    with col_cam:
        metodo_foto = st.radio(
            "Fuente de la fotografía:",
            ["📷 Cámara en Vivo", "🖼️ Subir archivo de imagen"],
            horizontal=True
        )

        archivo_imagen = None
        if metodo_foto == "📷 Cámara en Vivo":
            st.caption("💡 *Si es la primera vez, haz clic en **'Permitir'** cuando el navegador pida permiso para usar tu cámara.*")
            archivo_imagen = st.camera_input(
                "Haz clic en 'Take Photo' para capturar el cuarto o fisura",
                key=f"camara_{st.session_state.cam_id}"
            )
        else:
            archivo_imagen = st.file_uploader(
                "Selecciona una foto desde tu dispositivo",
                type=["jpg", "jpeg", "png"],
                key=f"uploader_{st.session_state.cam_id}"
            )

        imagen_lista_pil = None
        puntaje_nitidez = 0.0
        foto_aprobada = False
        estado_foto_texto = "OK"

        # Si tomó foto nueva o si está editando un cuarto y quiere conservar su foto anterior
        if archivo_imagen is not None:
            imagen_lista_pil = Image.open(archivo_imagen).convert("RGB")
        elif editando and os.path.exists(editando["ruta_foto"]):
            st.caption("📷 *Foto actual guardada (toma una nueva arriba si quieres reemplazarla):*")
            st.image(editando["ruta_foto"], width=300)
            imagen_lista_pil = Image.open(editando["ruta_foto"]).convert("RGB")

        if imagen_lista_pil is not None:
            # Botón directo para descartar y volver a tomar la foto si quedó mal
            if st.button("🔄 Quedó mal: Volver a tomar la foto", type="secondary", use_container_width=True):
                if editando:
                    st.session_state.datos_edicion["ruta_foto"] = ""
                st.session_state.cam_id += 1
                st.rerun()

            umbral_nitidez = st.slider(
                "Sensibilidad del detector de nitidez",
                min_value=10.0, max_value=200.0, value=55.0, step=5.0
            )
            puntaje_nitidez, es_nitida = evaluar_nitidez_imagen(imagen_lista_pil, umbral=umbral_nitidez)

            if es_nitida:
                st.success(f"✅ **OK: La foto se ve bien y nítida** (Nitidez: {puntaje_nitidez}).")
                foto_aprobada = True
                estado_foto_texto = f"OK - Nitida ({puntaje_nitidez})"
            else:
                st.error(f"⚠️ **Foto posiblemente borrosa** (Nitidez: {puntaje_nitidez}). Puedes darle a '🔄 Volver a tomar la foto' arriba.")
                forzar_ok = st.checkbox("✅ La foto se ve bien, darle 'OK' de todos modos")
                if forzar_ok:
                    foto_aprobada = True
                    estado_foto_texto = f"OK Manual ({puntaje_nitidez})"

    with col_datos:
        st.markdown("##### 📝 Información del Cuarto y Fachada")
        valor_nombre = editando["nombre_espacio"] if editando else f"Cuarto {st.session_state.contador_cuarto}"
        valor_longitud = editando["longitud_aprox"] if editando else ""
        valor_obs = editando["observaciones"] if editando else ""

        nombre_espacio = st.text_input("Nombre del cuarto o espacio *", value=valor_nombre, placeholder="Ej: Cuarto 1, Sala, Fachada Principal")

        c1, c2 = st.columns(2)
        with c1:
            longitud_aprox = st.text_input("Longitud aproximada *", value=valor_longitud, placeholder="Ej: 2.10 m / 80 cm")
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
            fachada_ubicacion = st.selectbox("Fachada / Ubicación *", lista_fachadas, index=idx_fachada)

        # Sección para agregar cualquier dato libre (Dimensión, Espesor, lo que el ingeniero quiera)
        st.markdown("---")
        st.markdown("##### ➕ Añade lo que quieras a este archivo (Dimensiones, ancho, etc.)")
        col_k, col_v, col_b = st.columns([1.2, 1.4, 0.8])
        with col_k:
            nuevo_campo_nombre = st.text_input("¿Qué dato deseas agregar?", placeholder="Ej: Dimensión / Ancho fisura")
        with col_v:
            nuevo_campo_valor = st.text_input("Valor", placeholder="Ej: 3m x 2.5m / 1.5 mm")
        with col_b:
            st.write("")
            st.write("")
            if st.button("➕ Agregar"):
                if nuevo_campo_nombre.strip() and nuevo_campo_valor.strip():
                    st.session_state.atributos_extra.append(f"- {nuevo_campo_nombre.strip()}: {nuevo_campo_valor.strip()}")
                    st.rerun()

        texto_inicial_atributos = "\n".join(st.session_state.atributos_extra)
        datos_personalizados = st.text_area(
            "Texto y medidas personalizadas del cuarto (puedes escribir libremente lo que quieras incluir):",
            value=texto_inicial_atributos,
            height=90,
            placeholder="Ejemplo:\n- Dimensión del muro: 4.0m x 2.4m\n- Espesor de fisura: 2 mm\n- Humedad: Sin filtración"
        )

        observaciones = st.text_area(
            "Observaciones adicionales:",
            value=valor_obs,
            height=70,
            placeholder="Anotaciones adicionales de la revisión..."
        )

        # Botón OK para guardar el cuarto y pasar al siguiente
        if st.button("✅ OK - Guardar este cuarto y seguir con el siguiente", type="primary", use_container_width=True):
            if imagen_lista_pil is None:
                st.error("⚠️ Primero toma la foto con la cámara o sube una imagen.")
            elif not foto_aprobada:
                st.error("⚠️ La foto no tiene el 'OK'. Vuelve a tomarla o marca la casilla de confirmación.")
            elif not nombre_espacio.strip() or not longitud_aprox.strip():
                st.error("⚠️ Escribe el nombre (ej: Cuarto 1) y la longitud aproximada.")
            else:
                nombre_foto = f"foto_{int(datetime.now().timestamp())}_{len(st.session_state.cuartos_actuales)+1}.jpg"
                ruta_foto_guardada = os.path.join(CARPETA_FOTOS, nombre_foto)
                imagen_lista_pil.save(ruta_foto_guardada, "JPEG", quality=90)

                st.session_state.cuartos_actuales.append({
                    "nombre_espacio": nombre_espacio.strip(),
                    "fachada_ubicacion": fachada_ubicacion,
                    "longitud_aprox": longitud_aprox.strip(),
                    "datos_personalizados": datos_personalizados.strip(),
                    "observaciones": observaciones.strip(),
                    "nitidez_puntaje": puntaje_nitidez,
                    "estado_foto": estado_foto_texto,
                    "ruta_foto": ruta_foto_guardada
                })

                # Limpiar cámara y formulario para el siguiente cuarto (Cuarto 2, Cuarto 3...)
                st.session_state.atributos_extra = []
                st.session_state.datos_edicion = None
                st.session_state.contador_cuarto = len(st.session_state.cuartos_actuales) + 1
                st.session_state.cam_id += 1
                st.rerun()

    # --- PASO 2: REVISIÓN DE CUARTOS Y OPCIÓN DE CORREGIR SI ALGUNO QUEDÓ MAL ---
    st.divider()
    st.subheader(f"2. Cuartos guardados en este informe ({len(st.session_state.cuartos_actuales)})")

    if len(st.session_state.cuartos_actuales) == 0:
        st.info("Toma la foto del **Cuarto 1** arriba y presiona **'✅ OK'** para ir armando el informe.")
    else:
        st.caption("💡 *Si algún cuarto o foto quedó mal, haz clic en **'✏️ Volver a tomar foto / Corregir'** en su tarjeta.*")
        cols_preview = st.columns(3)
        for i, cuarto in enumerate(st.session_state.cuartos_actuales):
            with cols_preview[i % 3]:
                with st.container(border=True):
                    if os.path.exists(cuarto["ruta_foto"]):
                        st.image(cuarto["ruta_foto"], use_container_width=True)
                    st.markdown(f"**{i+1}. {cuarto['nombre_espacio']}**")
                    st.caption(f"📍 {cuarto['fachada_ubicacion']} | 📏 Longitud: **{cuarto['longitud_aprox']}**")
                    st.caption(f"📷 {cuarto['estado_foto']}")
                    if cuarto["datos_personalizados"]:
                        st.text(cuarto["datos_personalizados"])
                    if cuarto["observaciones"]:
                        st.caption(f"📝 {cuarto['observaciones']}")

                    b_edit, b_del = st.columns(2)
                    with b_edit:
                        if st.button("✏️ Corregir / Foto", key=f"edit_{i}", use_container_width=True):
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

        # --- PASO 3: GENERAR EL ARCHIVO PDF ---
        st.markdown("---")
        st.subheader("3. Guardar y Generar el Archivo PDF")
        with st.form("form_cerrar_inspeccion"):
            f1, f2, f3, f4 = st.columns(4)
            with f1:
                proyecto = st.text_input("Casa / Edificio *", placeholder="Ej: Casa Familia Pérez / Edificio Sol")
            with f2:
                direccion = st.text_input("Dirección / Ubicación *", placeholder="Ej: Cra 15 # 20-10")
            with f3:
                inspector = st.text_input("Ingeniero / Inspector *", placeholder="Tu nombre")
            with f4:
                estado_insp = st.selectbox("Estado General", ["Con Fisuras Leves", "Requiere Reparación", "Revisión Estructural Urgente", "Sin Novedad Crítica"])

            boton_generar_pdf = st.form_submit_button("📄 GUARDAR INFORME Y GENERAR ARCHIVO PDF", type="primary", use_container_width=True)

            if boton_generar_pdf:
                if not proyecto.strip() or not direccion.strip() or not inspector.strip():
                    st.error("⚠️ Completa el nombre de la Casa/Edificio, Dirección e Inspector.")
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
    st.header("📁 Archivos PDF Guardados (Base de Datos Compartida)")
    st.caption("Desde aquí cualquier persona del equipo puede abrir el archivo PDF, verlo en pantalla o volver a hacer el informe si algo quedó mal.")

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
                    b1, b2, b3 = st.columns(3)
                    # Opción 1: Abrir el PDF en el visor de Windows
                    with b1:
                        if st.button("📂 Abrir PDF", key=f"open_{fila['id']}", type="primary", use_container_width=True):
                            if not abrir_pdf_en_computador(fila["ruta_pdf"]):
                                st.warning("Despliega abajo '👁️ Ver PDF en pantalla' para abrirlo.")

                    # Opción 2: Descargar el PDF
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

                    # Opción 3: Si el informe quedó mal, reabrirlo para corregir fotos o rehacerlo
                    with b3:
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
                                    "nitidez_puntaje": esp["nitidez_puntaje"],
                                    "estado_foto": esp["estado_foto"],
                                    "ruta_foto": esp["ruta_foto"]
                                })
                            eliminar_inspeccion_bd(fila["id"])
                            st.session_state.cuartos_actuales = cuartos_recuperados
                            st.session_state.contador_cuarto = len(cuartos_recuperados) + 1
                            st.session_state.menu_activo = "📸 Nueva Inspección (Cámara)"
                            st.rerun()

                # Desplegable para abrir y leer el PDF ahí mismo en el navegador
                with st.expander("👁️ Abrir / Visualizar el archivo PDF aquí en pantalla y ver sus fotos"):
                    if os.path.exists(fila["ruta_pdf"]):
                        mostrar_visor_pdf_en_pantalla(fila["ruta_pdf"])
                    else:
                        st.warning("El archivo PDF no se encuentra en la carpeta.")

# ================= VISTA 3: PANEL DE CONTROL =================
elif menu == "📊 Panel de Control":
    st.header("📊 Resumen General de Inspecciones")
    df_insp = obtener_inspecciones_bd()

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Informes PDF Creados", len(df_insp))
    total_cuartos = int(df_insp["total_espacios"].sum()) if len(df_insp) > 0 else 0
    c2.metric("Total Cuartos Fotografiados", total_cuartos)
    urgentes = len(df_insp[df_insp["estado"] == "Revisión Estructural Urgente"]) if len(df_insp) > 0 else 0
    c3.metric("Revisiones Estructurales Urgentes", urgentes)

    st.divider()
    if len(df_insp) > 0:
        st.dataframe(df_insp[["id", "proyecto", "direccion", "inspector", "fecha", "estado", "total_espacios"]], use_container_width=True, hide_index=True)
