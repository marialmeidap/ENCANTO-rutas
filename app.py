
# ============================================================
# ENCANTO RUTAS - PRIMER MODULO FUNCIONAL
# Registro de pedidos y etiquetas de envio de 10 x 15 cm
# ============================================================

import streamlit as st
import uuid
from datetime import datetime
import html

# ------------------------------------------------------------
# 1. CONFIGURACION GENERAL
# ------------------------------------------------------------

st.set_page_config(
    page_title="ENCANTO Rutas",
    page_icon="📦",
    layout="wide"
)

# ------------------------------------------------------------
# 2. MEMORIA TEMPORAL DE LOS PEDIDOS
# ------------------------------------------------------------
# Por ahora los pedidos se guardan en la sesion de Streamlit.
# En una siguiente etapa los guardaremos en una base de datos
# permanente para no perderlos al reiniciar la aplicacion.

if "pedidos" not in st.session_state:
    st.session_state["pedidos"] = []

# ------------------------------------------------------------
# 3. ENCABEZADO DEL DASHBOARD
# ------------------------------------------------------------

st.title("📦 ENCANTO Rutas")
st.caption("Sistema de entregas para los mensajeros de Encanto Capilar")

st.info(
    "Primera version: registro manual de pedidos y preparacion "
    "de etiquetas. Las rutas, Maps, GPS y WhatsApp se agregaran "
    "en las siguientes etapas."
)

# ------------------------------------------------------------
# 4. CALCULAR LOS INDICADORES DEL DASHBOARD
# ------------------------------------------------------------

pedidos = st.session_state["pedidos"]

total = len(pedidos)
completados = sum(
    1 for pedido in pedidos
    if pedido["estado"] == "Entregado"
)
pendientes = total - completados

col1, col2, col3 = st.columns(3)

col1.metric("Pedidos registrados", total)
col2.metric("Entregas completadas", completados)
col3.metric("Entregas pendientes", pendientes)

st.divider()

# ------------------------------------------------------------
# 5. FORMULARIO PARA REGISTRAR UN PEDIDO
# ------------------------------------------------------------

st.header("📝 Registrar pedido")

with st.form("formulario_pedido", clear_on_submit=True):

    nombre = st.text_input("Nombre completo del cliente *")
    telefono = st.text_input("Telefono de WhatsApp *")

    col1, col2 = st.columns(2)

    with col1:
        ciudad = st.text_input(
            "Ciudad",
            value="Cali"
        )
        barrio = st.text_input("Barrio")

    with col2:
        direccion = st.text_input("Direccion completa *")
        referencia = st.text_input("Punto de referencia")

    col3, col4 = st.columns(2)

    with col3:
        valor_cobrar = st.number_input(
            "Valor a cobrar (COP)",
            min_value=0,
            step=1000,
            value=0
        )

    with col4:
        producto = st.text_input("Producto o descripcion")

    observaciones = st.text_area(
        "Observaciones para el mensajero"
    )

    guardar = st.form_submit_button(
        "Guardar pedido",
        type="primary",
        use_container_width=True
    )

    if guardar:

        if not nombre.strip():
            st.error("Escribe el nombre del cliente.")

        elif not telefono.strip():
            st.error("Escribe el telefono del cliente.")

        elif not direccion.strip():
            st.error("Escribe la direccion del pedido.")

        else:
            numero = str(uuid.uuid4())[:8].upper()

            nuevo_pedido = {
                "numero": numero,
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "nombre": nombre.strip(),
                "telefono": telefono.strip(),
                "ciudad": ciudad.strip(),
                "barrio": barrio.strip(),
                "direccion": direccion.strip(),
                "referencia": referencia.strip(),
                "valor_cobrar": int(valor_cobrar),
                "producto": producto.strip(),
                "observaciones": observaciones.strip(),
                "estado": "Pendiente"
            }

            st.session_state["pedidos"].append(nuevo_pedido)

            st.success(
                f"Pedido {numero} registrado correctamente."
            )

            st.rerun()

# ------------------------------------------------------------
# 6. LISTA DE PEDIDOS REGISTRADOS
# ------------------------------------------------------------

st.divider()
st.header("📋 Pedidos registrados")

pedidos = st.session_state["pedidos"]

if not pedidos:
    st.write("Todavia no hay pedidos. Registra el primero arriba.")

else:
    for indice, pedido in enumerate(pedidos):

        with st.expander(
            f"Pedido {pedido['numero']} | "
            f"{pedido['nombre']} | {pedido['estado']}"
        ):

            st.write(f"**Telefono:** {pedido['telefono']}")
            st.write(
                f"**Direccion:** {pedido['direccion']}, "
                f"{pedido['barrio']}, {pedido['ciudad']}"
            )
            st.write(f"**Producto:** {pedido['producto'] or 'No especificado'}")
            st.write(
                f"**Valor a cobrar:** "
                f"${pedido['valor_cobrar']:,} COP"
            )
            st.write(
                f"**Referencia:** "
                f"{pedido['referencia'] or 'Sin referencia'}"
            )
            st.write(
                f"**Observaciones:** "
                f"{pedido['observaciones'] or 'Sin observaciones'}"
            )

            nuevo_estado = st.selectbox(
                "Estado de la entrega",
                ["Pendiente", "En camino", "Entregado", "Novedad"],
                index=[
                    "Pendiente",
                    "En camino",
                    "Entregado",
                    "Novedad"
                ].index(pedido["estado"]),
                key=f"estado_{pedido['numero']}"
            )

            if nuevo_estado != pedido["estado"]:
                st.session_state["pedidos"][indice]["estado"] = nuevo_estado
                st.rerun()

            # ------------------------------------------------
            # 7. GENERAR VISTA DE LA ETIQUETA
            # ------------------------------------------------

            if st.button(
                "Preparar etiqueta 10 x 15 cm",
                key=f"etiqueta_{pedido['numero']}"
            ):
                st.session_state["pedido_etiqueta"] = pedido["numero"]

# ------------------------------------------------------------
# 8. MOSTRAR ETIQUETA LISTA PARA IMPRIMIR
# ------------------------------------------------------------

numero_etiqueta = st.session_state.get("pedido_etiqueta")

if numero_etiqueta:

    pedido_etiqueta = next(
        (
            pedido for pedido in st.session_state["pedidos"]
            if pedido["numero"] == numero_etiqueta
        ),
        None
    )

    if pedido_etiqueta:

        st.divider()
        st.header("🏷️ Vista previa de la etiqueta")

        # Escapamos el texto para evitar que caracteres del
        # cliente se interpreten como codigo HTML.
        nombre_seguro = html.escape(pedido_etiqueta["nombre"])
        telefono_seguro = html.escape(pedido_etiqueta["telefono"])
        direccion_segura = html.escape(pedido_etiqueta["direccion"])
        ciudad_segura = html.escape(pedido_etiqueta["ciudad"])
        barrio_seguro = html.escape(pedido_etiqueta["barrio"])
        referencia_segura = html.escape(pedido_etiqueta["referencia"])
        producto_seguro = html.escape(pedido_etiqueta["producto"])
        observaciones_seguras = html.escape(
            pedido_etiqueta["observaciones"]
        )

        valor = f"${pedido_etiqueta['valor_cobrar']:,} COP"

        etiqueta_html = f"""
        <div style="
            width: 100mm;
            min-height: 140mm;
            border: 2px solid #222;
            padding: 6mm;
            box-sizing: border-box;
            font-family: Arial, sans-serif;
            color: #111;
            background: white;
        ">
            <div style="text-align:center; border-bottom:2px solid #222;">
                <h1 style="margin:0; font-size:25px;">ENCANTO</h1>
                <h2 style="margin:2px 0 10px; font-size:17px;">
                    CAPILAR · ENVIO
                </h2>
            </div>

            <p style="font-size:13px;">
                <b>PEDIDO:</b> {pedido_etiqueta['numero']}<br>
                <b>FECHA:</b> {pedido_etiqueta['fecha']}
            </p>

            <hr>

            <p style="font-size:17px;">
                <b>DESTINATARIO</b><br>
                {nombre_seguro}
            </p>

            <p style="font-size:14px;">
                <b>TELEFONO:</b> {telefono_seguro}<br><br>
                <b>DIRECCION:</b><br>
                {direccion_segura}<br>
                {barrio_seguro}, {ciudad_segura}<br><br>
                <b>REFERENCIA:</b> {referencia_segura}
            </p>

            <hr>

            <p style="font-size:13px;">
                <b>PRODUCTO:</b> {producto_seguro}<br><br>
                <b>OBSERVACIONES:</b> {observaciones_seguras}
            </p>

            <div style="
                margin-top:15px;
                padding:12px;
                border:2px solid #222;
                text-align:center;
            ">
                <div style="font-size:13px;">VALOR A COBRAR</div>
                <div style="font-size:25px; font-weight:bold;">
                    {valor}
                </div>
            </div>

            <p style="text-align:center; font-size:11px;">
                Gracias por tu compra
            </p>
        </div>
        """

        
import textwrap
import streamlit.components.v1 as components

etiqueta_limpia = textwrap.dedent(etiqueta_html).strip()

documento_etiqueta = f"""
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<style>
@page {{ size: 100mm 150mm; margin: 0; }}
html, body {{
    margin: 0;
    padding: 0;
    background: white;
}}
.hoja {{
    width: 100mm;
    height: 150mm;
    box-sizing: border-box;
    overflow: hidden;
}}
@media print {{
    .barra {{ display: none !important; }}
    html, body {{ width: 100mm; height: 150mm; }}
    .hoja {{ margin: 0; }}
}}
</style>
</head>
<body>
<div class="barra">
<button onclick="window.print()">
Imprimir etiqueta 10 × 15 cm
</button>
</div>
<div class="hoja">{etiqueta_limpia}</div>
</body>
</html>
"""

components.html(documento_etiqueta, height=700, scrolling=True)


        st.warning(
            "Esta es una vista previa. El tamaño y los margenes finales "
            "deben probarse con la impresora termica antes de imprimir "
            "etiquetas reales."
        )

st.divider()
st.caption(
    "ENCANTO Rutas · Prototipo en desarrollo. "
    "Los pedidos de esta version son temporales."
)
