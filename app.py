
# ============================================================
# ENCANTO RUTAS
# Sistema de pedidos, etiquetas y ubicación en Google Maps
# ============================================================

# IMPORTACIONES
# Streamlit crea la interfaz web.
import streamlit as st

# Permite mostrar la etiqueta HTML para imprimirla.
import streamlit.components.v1 as components

# uuid genera un identificador único para cada pedido.
import uuid

# datetime permite guardar la fecha y hora del pedido.
from datetime import datetime

# html permite proteger los textos antes de mostrarlos en HTML.
import html

# quote_plus convierte una dirección en texto válido para una URL.
# Así podemos buscar direcciones que contienen espacios y símbolos.
from urllib.parse import quote_plus


# ============================================================
# 1. CONFIGURACIÓN GENERAL DE LA APLICACIÓN
# ============================================================

st.set_page_config(
    page_title="ENCANTO Rutas",
    page_icon="📦",
    layout="wide"
)


# ============================================================
# 2. MEMORIA TEMPORAL DE LOS PEDIDOS
# ============================================================

# Si todavía no existe la lista de pedidos en esta sesión,
# la creamos vacía.
#
# IMPORTANTE:
# Esta memoria es temporal. Más adelante conectaremos una base
# de datos para conservar los pedidos permanentemente.
if "pedidos" not in st.session_state:
    st.session_state.pedidos = []


# ============================================================
# 3. ENCABEZADO DEL DASHBOARD
# ============================================================

st.title("📦 ENCANTO Rutas")
st.caption("Gestión de entregas · Encanto Capilar")


# ============================================================
# 4. INDICADORES DEL DASHBOARD
# ============================================================

# Consultamos los pedidos guardados en la sesión actual.
pedidos = st.session_state.pedidos

# Contamos todos los pedidos registrados.
total = len(pedidos)

# Contamos únicamente los pedidos entregados.
entregados = sum(
    pedido["estado"] == "Entregado"
    for pedido in pedidos
)

# Mostramos tres indicadores en la parte superior.
a, b, c = st.columns(3)

a.metric("Pedidos", total)
b.metric("Entregados", entregados)
c.metric("Pendientes", total - entregados)

st.divider()


# ============================================================
# 5. FORMULARIO PARA REGISTRAR UN PEDIDO
# ============================================================

st.header("📝 Registrar pedido")

# El formulario agrupa los campos y permite guardarlos juntos.
# clear_on_submit=True limpia los campos después de guardar.
with st.form("pedido", clear_on_submit=True):

    # Datos básicos del destinatario.
    nombre = st.text_input("Nombre del cliente *")
    telefono = st.text_input("WhatsApp *")

    # Dirección que utilizaremos para buscar el lugar en Maps.
    direccion = st.text_input("Dirección completa *")
    barrio = st.text_input("Barrio")
    ciudad = st.text_input("Ciudad", value="Cali")
    referencia = st.text_input("Punto de referencia")

    # Información comercial del pedido.
    producto = st.text_input("Producto")

    # El valor se almacena como número entero en pesos colombianos.
    valor = st.number_input(
        "Valor a cobrar (COP)",
        min_value=0,
        step=1000
    )

    # Instrucciones adicionales para el mensajero.
    observaciones = st.text_area("Observaciones")

    # Botón para enviar los datos del formulario.
    guardar = st.form_submit_button(
        "Guardar pedido",
        type="primary"
    )

    # Solo procesamos los datos cuando se pulsa Guardar pedido.
    if guardar:

        # Verificamos los campos obligatorios.
        if (
            not nombre.strip()
            or not telefono.strip()
            or not direccion.strip()
        ):
            st.error(
                "Completa el nombre, WhatsApp y dirección."
            )

        else:
            # Creamos el pedido con un número identificador.
            nuevo_pedido = {
                "numero": str(uuid.uuid4())[:8].upper(),
                "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "nombre": nombre.strip(),
                "telefono": telefono.strip(),
                "direccion": direccion.strip(),
                "barrio": barrio.strip(),
                "ciudad": ciudad.strip(),
                "referencia": referencia.strip(),
                "producto": producto.strip(),
                "valor": int(valor),
                "observaciones": observaciones.strip(),
                "estado": "Pendiente"
            }

            # Añadimos el pedido a la lista temporal.
            st.session_state.pedidos.append(nuevo_pedido)

            # Confirmamos que el registro fue exitoso.
            st.success("Pedido guardado correctamente.")

            # Actualizamos la pantalla para mostrar el pedido.
            st.rerun()


# ============================================================
# 6. LISTA DE PEDIDOS REGISTRADOS
# ============================================================

st.divider()
st.header("📋 Pedidos registrados")

# Recorremos la lista y mostramos cada pedido por separado.
for i, p in enumerate(st.session_state.pedidos):

    # Cada pedido aparece dentro de un panel desplegable.
    with st.expander(
        f"{p['numero']} · {p['nombre']} · {p['estado']}"
    ):

        # Mostramos la información registrada.
        st.write("**WhatsApp:**", p["telefono"])

        st.write(
            "**Dirección:**",
            p["direccion"],
            p["barrio"],
            p["ciudad"]
        )

        st.write("**Producto:**", p["producto"])
        st.write("**Valor a cobrar:**", f"${p['valor']:,} COP")
        st.write("**Referencia:**", p["referencia"])
        st.write("**Observaciones:**", p["observaciones"])


        # ====================================================
        # 7. BUSCAR LA DIRECCIÓN EN GOOGLE MAPS
        # ====================================================

        # Unimos la dirección, el barrio, la ciudad y el país.
        # Esto ayuda a distinguir lugares con nombres similares.
        partes_direccion = [
            p["direccion"],
            p["barrio"],
            p["ciudad"],
            "Colombia"
        ]

        # Quitamos los campos vacíos para evitar comas innecesarias.
        direccion_completa = ", ".join(
            parte.strip()
            for parte in partes_direccion
            if parte and parte.strip()
        )

        # Convertimos la dirección en texto válido para una URL.
        consulta_maps = quote_plus(direccion_completa)

        # Creamos el enlace de búsqueda de Google Maps.
        # No necesitamos una clave de API para abrir esta búsqueda.
        url_maps = (
            "https://www.google.com/maps/search/?api=1&query="
            + consulta_maps
        )

        # Mostramos un botón que abre Maps en otra pestaña.
        st.link_button(
            "📍 Buscar dirección en Google Maps",
            url_maps,
            use_container_width=True
        )

        # Aclaramos que el resultado debe revisarse manualmente.
        st.caption(
            "Comprueba que el punto encontrado sea correcto. "
            "Este botón busca la dirección, pero todavía no guarda "
            "coordenadas ni confirma automáticamente la ubicación."
        )


        # ====================================================
        # 8. ACTUALIZAR EL ESTADO DE LA ENTREGA
        # ====================================================

        # El usuario puede seleccionar el estado actual del pedido.
        opciones_estado = [
            "Pendiente",
            "En camino",
            "Entregado",
            "Novedad"
        ]

        estado = st.selectbox(
            "Estado de la entrega",
            opciones_estado,
            index=opciones_estado.index(p["estado"]),
            key=p["numero"]
        )

        # Si el estado cambió, actualizamos el pedido.
        if estado != p["estado"]:
            st.session_state.pedidos[i]["estado"] = estado
            st.rerun()


        # ====================================================
        # 9. PREPARAR LA ETIQUETA DE ENVÍO
        # ====================================================

        # Este botón selecciona el pedido cuya etiqueta queremos ver.
        if st.button(
            "Preparar etiqueta 10 × 15 cm",
            key="etiqueta_" + p["numero"]
        ):
            st.session_state.etiqueta = p["numero"]


# ============================================================
# 10. GENERAR LA ETIQUETA TÉRMICA
# ============================================================

# Buscamos si el usuario seleccionó un pedido para imprimir.
if st.session_state.get("etiqueta"):

    # Recuperamos el pedido correspondiente al identificador.
    p = next(
        (
            pedido
            for pedido in st.session_state.pedidos
            if pedido["numero"] == st.session_state.etiqueta
        ),
        None
    )

    # Solo generamos la etiqueta si encontramos el pedido.
    if p:

        st.divider()
        st.subheader("🏷️ Vista previa de etiqueta")

        # Escapamos los textos para evitar que caracteres especiales
        # del cliente se interpreten como código HTML.
        esc = lambda v: html.escape(str(v or ""))

        # Construimos el contenido visual de la etiqueta.
        etiqueta = f"""
        <div class="label">
            <header>
                <h1>ENCANTO</h1>
                <b>CAPILAR · ENVÍOS</b>
            </header>

            <p>
                <b>PEDIDO:</b> {esc(p['numero'])}<br>
                <b>FECHA:</b> {esc(p['fecha'])}
            </p>

            <hr>

            <h2>DESTINATARIO</h2>
            <h2>{esc(p['nombre'])}</h2>

            <p><b>WHATSAPP:</b> {esc(p['telefono'])}</p>

            <p>
                <b>DIRECCIÓN:</b><br>
                {esc(p['direccion'])}<br>
                {esc(p['barrio'])}, {esc(p['ciudad'])}
            </p>

            <p><b>REFERENCIA:</b> {esc(p['referencia'])}</p>

            <hr>

            <p><b>PRODUCTO:</b> {esc(p['producto'])}</p>

            <p>
                <b>OBSERVACIONES:</b>
                {esc(p['observaciones'])}
            </p>

            <div class="cash">
                <small>VALOR A COBRAR</small>
                <h1>${p['valor']:,} COP</h1>
            </div>
        </div>
        """

        # Creamos el documento completo para mostrar e imprimir.
        # @page configura el tamaño de papel de 100 x 150 mm.
        documento = f"""
        <!doctype html>
        <html lang="es">
        <head>
            <meta charset="utf-8">
            <style>
                @page {{
                    size: 100mm 150mm;
                    margin: 0;
                }}

                * {{
                    box-sizing: border-box;
                }}

                body {{
                    margin: 0;
                    font-family: Arial, sans-serif;
                    color: #000;
                }}

                .label {{
                    width: 100mm;
                    height: 150mm;
                    padding: 6mm;
                    overflow: hidden;
                    border: 1px solid #000;
                }}

                header {{
                    text-align: center;
                    border-bottom: 2px solid;
                    padding-bottom: 3mm;
                }}

                header h1 {{
                    font-size: 24pt;
                    margin: 0 0 2mm;
                }}

                h2 {{
                    font-size: 16pt;
                    margin: 3mm 0;
                }}

                p {{
                    font-size: 11pt;
                    overflow-wrap: anywhere;
                    line-height: 1.3;
                }}

                .cash {{
                    border: 2px solid;
                    text-align: center;
                    padding: 3mm;
                    margin-top: 5mm;
                }}

                .cash h1 {{
                    font-size: 21pt;
                    margin: 2mm 0;
                }}

                /* El botón de imprimir no aparece en el papel. */
                @media print {{
                    .toolbar {{
                        display: none;
                    }}
                }}
            </style>
        </head>

        <body>
            <div class="toolbar">
                <button onclick="window.print()">
                    Imprimir etiqueta
                </button>
            </div>

            {etiqueta}
        </body>
        </html>
        """

        # Mostramos la etiqueta dentro de la aplicación.
        components.html(
            documento,
            height=650,
            scrolling=True
        )

        # Indicaciones para evitar que la impresión se corte.
        st.info(
            "Al imprimir, selecciona papel de 100 × 150 mm, "
            "escala 100 % y márgenes ninguno."
        )


# ============================================================
# 11. PIE DE PÁGINA
# ============================================================

st.caption(
    "ENCANTO Rutas · Prototipo en desarrollo. "
    "Los pedidos se guardan temporalmente en esta sesión."
)
