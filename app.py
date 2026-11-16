
# ============================================================
# ENCANTO RUTAS
# Sistema de pedidos, direcciones, rutas y etiquetas de envío
# ============================================================

# IMPORTACIONES
import streamlit as st
import streamlit.components.v1 as components
import uuid
import html
import json
import os
import urllib.parse
import urllib.request
import urllib.error

from datetime import datetime
from google.cloud import firestore


# ============================================================
# 1. CONFIGURACIÓN GENERAL
# ============================================================

st.set_page_config(
    page_title="ENCANTO Rutas",
    page_icon="📦",
    layout="wide"
)

# Identificador de la base de datos creada en Google Cloud.
DATABASE_ID = "encanto-rutas-db"

# La clave se obtiene del secreto configurado en Cloud Run.
# Nunca escribas la clave real directamente en este archivo.
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# API de Google Places para sugerir y confirmar direcciones.
PLACES_AUTOCOMPLETE_URL = (
    "https://places.googleapis.com/v1/places:autocomplete"
)

PLACES_DETAILS_URL = "https://places.googleapis.com/v1/places/"


# ============================================================
# 2. CONEXIÓN A FIRESTORE
# ============================================================

@st.cache_resource
def conectar_firestore():
    """
    Crea una conexión reutilizable a Firestore.
    Cloud Run utilizará la cuenta de servicio configurada
    en el servicio para autenticarse.
    """
    return firestore.Client(database=DATABASE_ID)


db = None
error_firestore = None

try:
    db = conectar_firestore()
except Exception as error:
    error_firestore = str(error)


# ============================================================
# 3. FUNCIONES AUXILIARES PARA FIRESTORE
# ============================================================


def cargar_pedidos():
    """Lee los pedidos guardados permanentemente en Firestore."""
    if db is None:
        return []

    documentos = db.collection("pedidos").stream()
    pedidos_cargados = []

    for documento in documentos:
        pedido = documento.to_dict() or {}

        # Recuperar campos que falten en pedidos antiguos.
        pedido.setdefault("numero", documento.id)
        pedido.setdefault("nombre", "Sin nombre")
        pedido.setdefault("estado", "Pendiente")

        pedido["documento_id"] = documento.id
        pedidos_cargados.append(pedido)

    # Ordenar por fecha, del más reciente al más antiguo.
    pedidos_cargados.sort(
        key=lambda pedido: pedido.get("fecha_iso", ""),
        reverse=True
    )

    return pedidos_cargados


def guardar_pedido(pedido):
    """Guarda un pedido nuevo o actualiza uno existente."""
    if db is None:
        return False

    numero = pedido["numero"]

    # El número del pedido también es el identificador del documento.
    db.collection("pedidos").document(numero).set(pedido)
    return True


def actualizar_pedido(numero, cambios):
    """Actualiza solamente los campos indicados de un pedido."""
    if db is None:
        return False

    db.collection("pedidos").document(numero).update(cambios)
    return True


# ============================================================
# 4. FUNCIONES PARA GOOGLE PLACES
# ============================================================

def solicitar_places(metodo, url, datos=None, campos=None):
    """
    Realiza una petición a Google Places desde el servidor.
    La clave no se expone en el navegador del usuario.
    """
    if not GOOGLE_MAPS_API_KEY:
        raise ValueError(
            "No está configurada la variable GOOGLE_MAPS_API_KEY."
        )

    encabezados = {
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "Content-Type": "application/json"
    }

    if campos:
        encabezados["X-Goog-FieldMask"] = campos

    cuerpo = None
    if datos is not None:
        cuerpo = json.dumps(datos).encode("utf-8")

    solicitud = urllib.request.Request(
        url,
        data=cuerpo,
        headers=encabezados,
        method=metodo
    )

    with urllib.request.urlopen(solicitud, timeout=15) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def buscar_direcciones(texto):
    """
    Obtiene sugerencias de direcciones en Colombia.
    Se necesita tener habilitada Places API (New).
    """
    if len(texto.strip()) < 4:
        return []

    resultado = solicitar_places(
        "POST",
        PLACES_AUTOCOMPLETE_URL,
        datos={
            "input": texto,
            "includedRegionCodes": ["co"],
            "languageCode": "es"
        },
        campos=(
            "suggestions.placePrediction.placeId,"
            "suggestions.placePrediction.text"
        )
    )

    sugerencias = []

    for elemento in resultado.get("suggestions", []):
        prediccion = elemento.get("placePrediction", {})
        identificador = prediccion.get("placeId")
        texto_sugerido = prediccion.get("text", {}).get("text", "")

        if identificador and texto_sugerido:
            sugerencias.append({
                "id": identificador,
                "texto": texto_sugerido
            })

    return sugerencias


def obtener_detalles_lugar(place_id):
    """
    Consulta la dirección confirmada y sus coordenadas.
    Se necesita Places API (New).
    """
    url = PLACES_DETAILS_URL + urllib.parse.quote(
        place_id, safe=""
    )

    resultado = solicitar_places(
        "GET",
        url,
        campos="id,formattedAddress,location,displayName"
    )

    ubicacion = resultado.get("location", {})

    return {
        "place_id": resultado.get("id", place_id),
        "direccion": resultado.get("formattedAddress", ""),
        "latitud": ubicacion.get("latitude"),
        "longitud": ubicacion.get("longitude")
    }


# ============================================================
# 5. MEMORIA DE LA SESIÓN
# ============================================================

if "pedidos" not in st.session_state:
    st.session_state.pedidos = []

if "pedidos_cargados" not in st.session_state:
    st.session_state.pedidos_cargados = False

if "direccion_confirmada" not in st.session_state:
    st.session_state.direccion_confirmada = None

if "sugerencias_direccion" not in st.session_state:
    st.session_state.sugerencias_direccion = []

if "destinos_ruta" not in st.session_state:
    st.session_state.destinos_ruta = []

# Cargamos los pedidos una vez por sesión.
if db is not None and not st.session_state.pedidos_cargados:
    try:
        st.session_state.pedidos = cargar_pedidos()
        st.session_state.pedidos_cargados = True
    except Exception as error:
        st.warning(
            "No fue posible cargar los pedidos de Firestore. "
            "Revisa los permisos de la cuenta de servicio."
        )
        st.caption(str(error))


# ============================================================
# 6. ENCABEZADO Y ESTADO DE CONEXIONES
# ============================================================

st.title("📦 ENCANTO Rutas")
st.caption("Gestión de pedidos, entregas y rutas · Encanto Capilar")

if db is not None:
    st.success("Base de datos Firestore conectada.")
else:
    st.warning(
        "Firestore no está disponible. Los pedidos nuevos "
        "solo se conservarán temporalmente en esta sesión."
    )
    if error_firestore:
        st.caption(error_firestore)

if GOOGLE_MAPS_API_KEY:
    st.success("Clave de Google Maps configurada.")
else:
    st.warning(
        "Falta GOOGLE_MAPS_API_KEY en las variables de Cloud Run."
    )


# ============================================================
# 7. INDICADORES DEL DASHBOARD
# ============================================================

pedidos = st.session_state.pedidos
total = len(pedidos)

entregados = sum(
    pedido.get("estado") == "Entregado"
    for pedido in pedidos
)

en_camino = sum(
    pedido.get("estado") == "En camino"
    for pedido in pedidos
)

pendientes = sum(
    pedido.get("estado") == "Pendiente"
    for pedido in pedidos
)

a, b, c, d = st.columns(4)

a.metric("📦 Pedidos", total)
b.metric("✅ Entregados", entregados)
c.metric("🚚 En camino", en_camino)
d.metric("⏳ Pendientes", pendientes)

st.divider()


# ============================================================
# 8. FORMULARIO PARA REGISTRAR UN PEDIDO
# ============================================================

st.header("📝 Registrar pedido")

# El campo de dirección está fuera del formulario para permitir
# que la aplicación muestre sugerencias mientras se escribe.
direccion_escrita = st.text_input(
    "Dirección del cliente *",
    key="direccion_input",
    placeholder="Ej.: Calle 5 # 10-20, Cali"
)

# Si cambia el texto, ya no consideramos confirmada la selección
# anterior. La nueva dirección debe confirmarse nuevamente.
if (
    st.session_state.direccion_confirmada
    and direccion_escrita.strip()
    != st.session_state.direccion_confirmada.get("texto_busqueda", "")
):
    st.session_state.direccion_confirmada = None

# Autocompletado con Google Places.
if direccion_escrita.strip() and len(direccion_escrita.strip()) >= 4:

    if GOOGLE_MAPS_API_KEY:
        try:
            sugerencias = buscar_direcciones(direccion_escrita)
            st.session_state.sugerencias_direccion = sugerencias

        except urllib.error.HTTPError as error:
            st.session_state.sugerencias_direccion = []
            st.warning(
                "Google Places rechazó la consulta. "
                "Verifica que Places API (New) esté habilitada "
                "y que la clave tenga permiso para utilizarla."
            )
            st.caption(f"Código HTTP: {error.code}")

        except Exception as error:
            st.session_state.sugerencias_direccion = []
            st.warning("No se pudieron cargar las sugerencias.")
            st.caption(str(error))

    else:
        st.session_state.sugerencias_direccion = []

# Presentamos una lista para seleccionar una sugerencia.
sugerencias = st.session_state.sugerencias_direccion

if sugerencias:
    opciones = ["Selecciona una dirección confirmada"] + [
        sugerencia["texto"] for sugerencia in sugerencias
    ]

    seleccion = st.selectbox(
        "📍 Selecciona la dirección encontrada en Google Maps",
        opciones,
        key="seleccion_direccion"
    )

    if seleccion != opciones[0]:
        sugerencia_seleccionada = next(
            (
                sugerencia
                for sugerencia in sugerencias
                if sugerencia["texto"] == seleccion
            ),
            None
        )

        if sugerencia_seleccionada:
            try:
                # Consultamos las coordenadas solo cuando el usuario
                # selecciona una dirección de las sugerencias.
                lugar = obtener_detalles_lugar(
                    sugerencia_seleccionada["id"]
                )

                lugar["texto_busqueda"] = direccion_escrita.strip()
                st.session_state.direccion_confirmada = lugar

                st.success("Dirección seleccionada correctamente.")

                if (
                    lugar.get("latitud") is not None
                    and lugar.get("longitud") is not None
                ):
                    st.caption(
                        f"Coordenadas: {lugar['latitud']}, "
                        f"{lugar['longitud']}"
                    )

            except Exception as error:
                st.error(
                    "No se pudieron obtener los detalles de esta "
                    "dirección. Verifica Places API (New)."
                )
                st.caption(str(error))

# Permitimos continuar incluso si no se elige una sugerencia.
# En ese caso, la dirección queda sin coordenadas confirmadas.

with st.form("pedido", clear_on_submit=True):

    nombre = st.text_input("Nombre del cliente *")
    telefono = st.text_input("WhatsApp *")
    barrio = st.text_input("Barrio")
    ciudad = st.text_input("Ciudad", value="Cali")
    referencia = st.text_input("Punto de referencia")

    producto = st.text_input("Producto")

    valor = st.number_input(
        "Valor a cobrar (COP)",
        min_value=0,
        step=1000
    )

    observaciones = st.text_area("Observaciones")

    guardar = st.form_submit_button(
        "Guardar pedido",
        type="primary"
    )

    if guardar:

        direccion_confirmada = st.session_state.direccion_confirmada

        # Si se confirmó una sugerencia, guardamos su dirección
        # formateada; si no, guardamos el texto manual.
        direccion_final = (
            direccion_confirmada["direccion"]
            if direccion_confirmada
            else direccion_escrita.strip()
        )

        if (
            not nombre.strip()
            or not telefono.strip()
            or not direccion_final
        ):
            st.error(
                "Completa el nombre, WhatsApp y dirección."
            )

        else:
            ahora = datetime.now()

            nuevo_pedido = {
                "numero": str(uuid.uuid4())[:8].upper(),
                "fecha": ahora.strftime("%d/%m/%Y %H:%M"),
                "fecha_iso": ahora.isoformat(),
                "nombre": nombre.strip(),
                "telefono": telefono.strip(),
                "direccion": direccion_final,
                "barrio": barrio.strip(),
                "ciudad": ciudad.strip(),
                "referencia": referencia.strip(),
                "producto": producto.strip(),
                "valor": int(valor),
                "observaciones": observaciones.strip(),
                "estado": "Pendiente",

                # Estos campos se llenan si se confirma una dirección
                # mediante las sugerencias de Google Places.
                "place_id": (
                    direccion_confirmada.get("place_id")
                    if direccion_confirmada else None
                ),
                "latitud": (
                    direccion_confirmada.get("latitud")
                    if direccion_confirmada else None
                ),
                "longitud": (
                    direccion_confirmada.get("longitud")
                    if direccion_confirmada else None
                )
            }

            try:
                # Primero intentamos guardar permanentemente.
                guardado_permanente = guardar_pedido(nuevo_pedido)

                # Mantenemos también una copia para actualizar
                # la interfaz de la sesión actual.
                st.session_state.pedidos.insert(0, nuevo_pedido)

                if guardado_permanente:
                    st.success(
                        f"Pedido {nuevo_pedido['numero']} guardado "
                        "en Firestore."
                    )
                else:
                    st.warning(
                        "Pedido agregado a esta sesión, pero no se "
                        "guardó permanentemente porque Firestore "
                        "no está conectado."
                    )

                st.session_state.direccion_confirmada = None
                st.session_state.sugerencias_direccion = []
                st.rerun()

            except Exception as error:
                st.error(
                    "No se pudo guardar el pedido en Firestore."
                )
                st.caption(str(error))


# ============================================================
# 9. LISTA DE PEDIDOS REGISTRADOS
# ============================================================

st.divider()
st.header("📋 Pedidos registrados")

if not st.session_state.pedidos:
    st.info("Todavía no hay pedidos registrados.")

for i, p in enumerate(st.session_state.pedidos):

    with st.expander(
        f"{p.get('numero', 'Sin número')} · {p.get('nombre', 'Sin nombre')} · {p.get('estado', 'Pendiente')}"
    ):

        st.write("**WhatsApp:**", p.get("telefono", ""))

        st.write(
            "**Dirección:**",
            p.get("direccion", ""),
            p.get("barrio", ""),
            p.get("ciudad", "")
        )

        st.write("**Producto:**", p.get("producto", ""))

        st.write(
            "**Valor a cobrar:**",
            f"${p.get('valor', 0):,} COP"
        )

        st.write("**Referencia:**", p.get("referencia", ""))
        st.write("**Observaciones:**", p.get("observaciones", ""))

        # Coordenadas guardadas al confirmar la dirección.
        latitud = p.get("latitud")
        longitud = p.get("longitud")

        if latitud is not None and longitud is not None:
            st.write("**Latitud:**", latitud)
            st.write("**Longitud:**", longitud)

            url_punto = (
                "https://www.google.com/maps/search/?api=1&query="
                f"{latitud},{longitud}"
            )

            st.link_button(
                "📍 Ver ubicación confirmada",
                url_punto,
                use_container_width=True
            )

        else:
            # Compatibilidad con pedidos registrados antes de
            # activar Places: se puede seguir buscando la dirección.
            partes = [
                p.get("direccion", ""),
                p.get("barrio", ""),
                p.get("ciudad", ""),
                "Colombia"
            ]

            direccion_completa = ", ".join(
                parte.strip()
                for parte in partes
                if parte and parte.strip()
            )

            url_maps = (
                "https://www.google.com/maps/search/?api=1&query="
                + urllib.parse.quote_plus(direccion_completa)
            )

            st.link_button(
                "📍 Buscar dirección en Google Maps",
                url_maps,
                use_container_width=True
            )

            st.caption(
                "Esta dirección todavía no tiene coordenadas "
                "confirmadas. Puedes seguir buscándola en Maps."
            )

        # ========================================================
        # 10. ACTUALIZAR EL ESTADO DE LA ENTREGA
        # ========================================================

        opciones_estado = [
            "Pendiente",
            "En camino",
            "Entregado",
            "Novedad"
        ]

        estado_actual = p.get("estado", "Pendiente")

        if estado_actual not in opciones_estado:
            estado_actual = "Pendiente"

        estado = st.selectbox(
            "Estado de la entrega",
            opciones_estado,
            index=opciones_estado.index(estado_actual),
            key="estado_" + p["numero"]
        )

        if estado != p.get("estado", "Pendiente"):

            try:
                # Si Firestore está disponible, persistimos el cambio.
                if db is not None:
                    actualizar_pedido(
                        p["numero"],
                        {"estado": estado}
                    )

                st.session_state.pedidos[i]["estado"] = estado
                st.rerun()

            except Exception as error:
                st.error("No se pudo actualizar el estado en Firestore.")
                st.caption(str(error))

        # ========================================================
        # 11. SELECCIONAR DESTINOS PARA UNA RUTA
        # ========================================================

        incluir_ruta = st.checkbox(
            "Incluir este pedido en la ruta",
            value=p["numero"] in st.session_state.destinos_ruta,
            key="ruta_" + p["numero"]
        )

        if incluir_ruta:
            if p["numero"] not in st.session_state.destinos_ruta:
                st.session_state.destinos_ruta.append(p["numero"])
        elif p["numero"] in st.session_state.destinos_ruta:
            st.session_state.destinos_ruta.remove(p["numero"])

        # ========================================================
        # 12. PREPARAR ETIQUETA TÉRMICA
        # ========================================================

        if st.button(
            "Preparar etiqueta 10 × 15 cm",
            key="etiqueta_" + p["numero"]
        ):
            st.session_state.etiqueta = p["numero"]


# ============================================================
# 13. CONSTRUIR RUTA CON VARIOS DESTINOS
# ============================================================

st.divider()
st.header("🗺️ Preparar ruta de entregas")

st.write(
    "Selecciona los pedidos que quieres visitar y genera "
    "un recorrido de Google Maps con varios destinos."
)

if st.session_state.destinos_ruta:

    pedidos_seleccionados = [
        pedido
        for pedido in st.session_state.pedidos
        if pedido["numero"] in st.session_state.destinos_ruta
    ]

    st.write(
        f"Destinos seleccionados: {len(pedidos_seleccionados)}"
    )

    for pedido in pedidos_seleccionados:
        st.write(
            f"• {pedido['nombre']} — "
            f"{pedido['direccion']}, {pedido['ciudad']}"
        )

    if st.button("🚚 Abrir ruta en Google Maps", type="primary"):

        destinos = []

        for pedido in pedidos_seleccionados:
            if (
                pedido.get("latitud") is not None
                and pedido.get("longitud") is not None
            ):
                destino = (
                    f"{pedido['latitud']},{pedido['longitud']}"
                )
            else:
                destino = ", ".join(
                    parte.strip()
                    for parte in [
                        pedido.get("direccion", ""),
                        pedido.get("barrio", ""),
                        pedido.get("ciudad", ""),
                        "Colombia"
                    ]
                    if parte and parte.strip()
                )

            destinos.append(destino)

        if len(destinos) == 1:
            url_ruta = (
                "https://www.google.com/maps/dir/?api=1"
                "&destination="
                + urllib.parse.quote(destinos[0])
                + "&travelmode=driving"
            )
        else:
            origen = destinos[0]
            destino_final = destinos[-1]
            puntos_intermedios = destinos[1:-1]

            url_ruta = (
                "https://www.google.com/maps/dir/?api=1"
                "&origin=" + urllib.parse.quote(origen)
                + "&destination=" + urllib.parse.quote(destino_final)
                + "&travelmode=driving"
            )

            if puntos_intermedios:
                url_ruta += "&waypoints=" + urllib.parse.quote(
                    "|".join(puntos_intermedios)
                )

        st.link_button(
            "Abrir recorrido en Google Maps",
            url_ruta,
            use_container_width=True
        )

        st.caption(
            "Google Maps abrirá los destinos en el orden seleccionado. "
            "Esta versión no optimiza automáticamente el orden ni "
            "calcula una ruta optimizada mediante Routes API."
        )

    if st.button("Limpiar selección de ruta"):
        st.session_state.destinos_ruta = []
        st.rerun()

else:
    st.info("Selecciona al menos un pedido para preparar una ruta.")


# ============================================================
# 14. GENERAR ETIQUETA TÉRMICA
# ============================================================

if st.session_state.get("etiqueta"):

    p = next(
        (
            pedido
            for pedido in st.session_state.pedidos
            if pedido["numero"] == st.session_state.etiqueta
        ),
        None
    )

    if p:
        st.divider()
        st.subheader("🏷️ Vista previa de etiqueta")

        # Protegemos los datos antes de insertarlos en HTML.
        esc = lambda valor: html.escape(str(valor or ""))

        etiqueta = f"""
        <div class="label">
            <header>
                <h1>ENCANTO</h1>
                <b>CAPILAR · ENVÍOS</b>
            </header>

            <p>
                <b>PEDIDO:</b> {esc(p['numero'])}<br>
                <b>FECHA:</b> {esc(p.get('fecha', ''))}
            </p>

            <hr>

            <h2>DESTINATARIO</h2>
            <h2>{esc(p.get('nombre', ''))}</h2>

            <p><b>WHATSAPP:</b> {esc(p.get('telefono', ''))}</p>

            <p>
                <b>DIRECCIÓN:</b><br>
                {esc(p.get('direccion', ''))}<br>
                {esc(p.get('barrio', ''))},
                {esc(p.get('ciudad', ''))}
            </p>

            <p><b>REFERENCIA:</b> {esc(p.get('referencia', ''))}</p>

            <hr>

            <p><b>PRODUCTO:</b> {esc(p.get('producto', ''))}</p>

            <p>
                <b>OBSERVACIONES:</b>
                {esc(p.get('observaciones', ''))}
            </p>

            <div class="cash">
                <small>VALOR A COBRAR</small>
                <h1>${p.get('valor', 0):,} COP</h1>
            </div>
        </div>
        """

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

                @media print {{
                    .toolbar {{
                        display: none;
                    }}
                }}
            </style>
        </head>

        <body>
            <div class="toolbar">
                <button onclick="window.print()">Imprimir etiqueta</button>
            </div>

            {etiqueta}
        </body>
        </html>
        """

        components.html(
            documento,
            height=650,
            scrolling=True
        )

        st.info(
            "Al imprimir, selecciona papel de 100 × 150 mm, "
            "escala 100 % y márgenes ninguno."
        )


# ============================================================
# 15. PIE DE PÁGINA
# ============================================================

st.caption(
    "ENCANTO Rutas · Pedidos, direcciones y preparación de rutas."
)
