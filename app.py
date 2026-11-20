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

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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

# Ubicación fija de la bodega de ENCANTO.
BODEGA_LATITUD = 3.4522
BODEGA_LONGITUD = -76.5339


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
    Busca direcciones, negocios, unidades residenciales
    y puntos de referencia en Valle del Cauca, Colombia.
    """
    texto = texto.strip()

    if len(texto) < 3:
        return []

    resultado = solicitar_places(
        "POST",
        PLACES_AUTOCOMPLETE_URL,
        datos={
            "input": texto,
            "includedRegionCodes": ["co"],
            "languageCode": "es",
            "regionCode": "co",
            "locationBias": {
                "rectangle": {
                    "low": {
                        "latitude": 3.0,
                        "longitude": -77.5
                    },
                    "high": {
                        "latitude": 4.5,
                        "longitude": -75.8
                    }
                }
            }
        },
        campos=(
            "suggestions.placePrediction.placeId,"
            "suggestions.placePrediction.text,"
            "suggestions.placePrediction.structuredFormat"
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

hoy = datetime.now(ZoneInfo("America/Bogota")).date()

st.subheader("📅 Consultar pedidos por fecha")

rango_fechas = st.date_input(
    "Selecciona el periodo (máximo 30 días)",
    value=(hoy, hoy),
    max_value=hoy,
    format="DD/MM/YYYY",
    key="filtro_periodo_pedidos"
)

# Streamlit puede devolver una fecha o un rango de dos fechas.
if isinstance(rango_fechas, (tuple, list)):
    fecha_inicio = rango_fechas[0]
    fecha_fin = (
        rango_fechas[1]
        if len(rango_fechas) == 2
        else rango_fechas[0]
    )
else:
    fecha_inicio = rango_fechas
    fecha_fin = rango_fechas

# Limitar la consulta a un máximo de 30 días.
if (fecha_fin - fecha_inicio).days > 29:
    fecha_inicio_consulta = fecha_fin - timedelta(days=29)
    st.warning(
        "El periodo máximo es de 30 días. "
        "Se mostrarán los últimos 30 días del rango seleccionado."
    )
else:
    fecha_inicio_consulta = fecha_inicio


def obtener_fecha_pedido(pedido):
    """Obtiene la fecha del pedido, incluidos registros antiguos."""
    fecha_iso = pedido.get("fecha_iso")

    if fecha_iso:
        try:
            fecha_hora = datetime.fromisoformat(fecha_iso)

            if fecha_hora.tzinfo is not None:
                fecha_hora = fecha_hora.astimezone(
                    ZoneInfo("America/Bogota")
                )

            return fecha_hora.date()

        except (TypeError, ValueError):
            pass

    fecha_texto = pedido.get("fecha")

    if fecha_texto:
        try:
            return datetime.strptime(
                fecha_texto, "%d/%m/%Y %H:%M"
            ).date()
        except (TypeError, ValueError):
            pass

    return None

# Filtrar pedidos por el periodo seleccionado.
pedidos_periodo = []

for pedido in pedidos:
    fecha_pedido = obtener_fecha_pedido(pedido)

    if (
        fecha_pedido is not None
        and fecha_inicio_consulta <= fecha_pedido <= fecha_fin
    ):
        pedidos_periodo.append(pedido)


# Calcular indicadores del periodo.
total = len(pedidos_periodo)

entregados = sum(
    pedido.get("estado") == "Entregado"
    for pedido in pedidos_periodo
)

en_camino = sum(
    pedido.get("estado") == "En camino"
    for pedido in pedidos_periodo
)

pendientes = sum(
    pedido.get("estado") == "Pendiente"
    for pedido in pedidos_periodo
)

novedades = sum(
    pedido.get("estado") == "Novedad"
    for pedido in pedidos_periodo
)

valor_por_cobrar = sum(
    int(pedido.get("valor", 0) or 0)
    for pedido in pedidos_periodo
    if pedido.get("estado") != "Entregado"
)

valor_entregado = sum(
    int(pedido.get("valor", 0) or 0)
    for pedido in pedidos_periodo
    if pedido.get("estado") == "Entregado"
)

st.caption(
    f"Periodo: {fecha_inicio_consulta.strftime('%d/%m/%Y')} "
    f"al {fecha_fin.strftime('%d/%m/%Y')}"
)

a, b, c, d = st.columns(4)

a.metric("📦 Pedidos", total)
b.metric("✅ Entregados", entregados)
c.metric("🚚 En camino", en_camino)
d.metric("⏳ Pendientes", pendientes)

e, f, g = st.columns(3)

e.metric("⚠️ Novedades", novedades)
f.metric("💰 Por cobrar", f"$ {valor_por_cobrar:,.0f} COP")
g.metric("💵 Valor entregado", f"$ {valor_entregado:,.0f} COP")

st.markdown("#### 📋 Pedidos del periodo")

if pedidos_periodo:
    detalle_pedidos = [
        {
            "Pedido": pedido.get("numero", ""),
            "Fecha": pedido.get("fecha", ""),
            "Cliente": pedido.get("nombre", ""),
            "Ciudad": pedido.get("ciudad", ""),
            "Estado": pedido.get("estado", "Pendiente"),
            "Valor (COP)": int(pedido.get("valor", 0) or 0)
        }
        for pedido in pedidos_periodo
    ]

    st.dataframe(
        detalle_pedidos,
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No hay pedidos registrados en el periodo seleccionado.")

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
            ahora = datetime.now(ZoneInfo("America/Bogota"))

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
            "Asignado",
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
# 13. CONSTRUIR Y OPTIMIZAR RUTA CON GOOGLE ROUTES API
# ============================================================

st.divider()
st.header("🗺️ Preparar ruta optimizada de entregas")

st.write(
    "Selecciona los pedidos que quieres entregar. "
    "La ruta comenzará en la bodega y Google calculará "
    "el orden de visita más conveniente."
)

def consultar_ruta_google(origen, destino, intermedios):
    """Calcula una ruta y optimiza sus puntos intermedios."""

    if not GOOGLE_MAPS_API_KEY:
        raise ValueError(
            "No está configurada GOOGLE_MAPS_API_KEY."
        )

    url = "https://routes.googleapis.com/directions/v2:computeRoutes"

    datos = {
        "origin": {
            "location": {
                "latLng": {
                    "latitude": origen[0],
                    "longitude": origen[1]
                }
            }
        },
        "destination": {
            "location": {
                "latLng": {
                    "latitude": destino[0],
                    "longitude": destino[1]
                }
            }
        },
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "languageCode": "es",
        "regionCode": "CO"
    }

    if intermedios:
        datos["intermediates"] = [
            {
                "location": {
                    "latLng": {
                        "latitude": punto[0],
                        "longitude": punto[1]
                    }
                }
            }
            for punto in intermedios
        ]

# Google puede reorganizar los puntos intermedios.
    if len(intermedios) >= 2:
        datos["optimizeWaypointOrder"] = True

    solicitud = urllib.request.Request(
        url,
        data=json.dumps(datos).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": (
                "routes.duration,"
                "routes.distanceMeters,"
                "routes.optimizedIntermediateWaypointIndex"
            )
        },
        method="POST"
    )

    with urllib.request.urlopen(
        solicitud, timeout=30
    ) as respuesta:
        resultado = json.loads(
            respuesta.read().decode("utf-8")
        )

    rutas = resultado.get("routes", [])

    if not rutas:
        raise ValueError(
            "Google no devolvió una ruta para estos destinos."
        )

    ruta = rutas[0]
    indices = ruta.get(
        "optimizedIntermediateWaypointIndex",
        list(range(len(intermedios)))
    )

    return {
        "orden": indices,
        "duracion_segundos": int(
            ruta.get("duration", "0s").removesuffix("s")
        ),
        "distancia_metros": int(
            ruta.get("distanceMeters", 0)
        )
    }


if st.session_state.destinos_ruta:

    pedidos_seleccionados = [
        pedido
        for pedido in st.session_state.pedidos
        if pedido["numero"] in st.session_state.destinos_ruta
    ]

    st.write(
        f"Destinos seleccionados: "
        f"{len(pedidos_seleccionados)}"
    )

    for pedido in pedidos_seleccionados:
        st.write(
            f"• {pedido.get('numero', '')} — "
            f"{pedido.get('nombre', '')} — "
            f"{pedido.get('direccion', '')}"
        )

    if st.button(
        "🚚 Optimizar ruta desde la bodega",
        type="primary"
    ):
        # Solo optimizamos pedidos con coordenadas confirmadas.
        pedidos_validos = []
        pedidos_sin_coordenadas = []

        for pedido in pedidos_seleccionados:
            lat = pedido.get("latitud")
            lon = pedido.get("longitud")

            if lat is None or lon is None:
                pedidos_sin_coordenadas.append(pedido)
                continue

            try:
                pedidos_validos.append({
                    "pedido": pedido,
                    "lat": float(lat),
                    "lon": float(lon)
                })
            except (TypeError, ValueError):
                pedidos_sin_coordenadas.append(pedido)

        if pedidos_sin_coordenadas:
            st.error(
                "Hay pedidos sin coordenadas confirmadas. "
                "Corrige sus direcciones antes de optimizar."
            )

            for pedido in pedidos_sin_coordenadas:
                st.write(
                    f"• {pedido.get('numero', '')} — "
                    f"{pedido.get('direccion', '')}"
                )

        elif not pedidos_validos:
            st.warning(
                "Selecciona al menos un pedido válido."
            )

        elif len(pedidos_validos) > 26:
            st.error(
                "Por ahora, optimiza un máximo de 26 "
                "entregas por recorrido."
            )

        else:
            origen_bodega = (
                BODEGA_LATITUD,
                BODEGA_LONGITUD
            )

            puntos = [
                (item["lat"], item["lon"])
                for item in pedidos_validos
            ]

            mejor_resultado = None
            mejor_orden = None

            barra = st.progress(0)
            estado_calculo = st.empty()

            try:
                # Probamos cada cliente como posible destino final.
                # Cada consulta compara una ruta que sale de la bodega.
                total_opciones = len(puntos)

                for indice_final in range(total_opciones):
                    estado_calculo.caption(
                        "Comparando posibles recorridos: "
                        f"{indice_final + 1} de {total_opciones}"
                    )

                    indices_intermedios = [
                        i for i in range(total_opciones)
                        if i != indice_final
                    ]

                    puntos_intermedios = [
                        puntos[i]
                        for i in indices_intermedios
                    ]

                    resultado = consultar_ruta_google(
                        origen_bodega,
                        puntos[indice_final],
                        puntos_intermedios
                    )

                    orden_intermedios = [
                        indices_intermedios[i]
                        for i in resultado["orden"]
                    ]

                    orden_completo = (
                        orden_intermedios + [indice_final]
                    )

                    if (
                        mejor_resultado is None
                        or resultado["duracion_segundos"]
                        < mejor_resultado["duracion_segundos"]
                    ):
                        mejor_resultado = resultado
                        mejor_orden = orden_completo

                    barra.progress(
                        (indice_final + 1) / total_opciones
                    )

                barra.empty()
                estado_calculo.empty()

                pedidos_ordenados = [
                    pedidos_validos[i]["pedido"]
                    for i in mejor_orden
                ]

                st.session_state["ruta_optimizada"] = [
                    pedido["numero"]
                    for pedido in pedidos_ordenados
                ]

                st.success("Ruta calculada correctamente.")

                st.subheader("Orden recomendado de entregas")

                for numero, pedido in enumerate(
                    pedidos_ordenados, start=1
                ):
                    st.write(
                        f"{numero}. **{pedido.get('nombre', '')}** "
                        f"— {pedido.get('direccion', '')}"
                    )

                minutos = round(
                    mejor_resultado["duracion_segundos"] / 60
                )

                kilometros = (
                    mejor_resultado["distancia_metros"] / 1000
                )

                col1, col2 = st.columns(2)
                col1.metric(
                    "Tiempo estimado de conducción",
                    f"{minutos} min"
                )
                col2.metric(
                    "Distancia estimada",
                    f"{kilometros:.1f} km"
                )
                # Construimos Google Maps con el orden calculado.
                destino_final = puntos[mejor_orden[-1]]

                url_ruta = (
                    "https://www.google.com/maps/dir/?api=1"
                    "&origin="
                    + urllib.parse.quote(
                        f"{BODEGA_LATITUD},{BODEGA_LONGITUD}"
                    )
                    + "&destination="
                    + urllib.parse.quote(
                        f"{destino_final[0]},{destino_final[1]}"
                    )
                    + "&travelmode=driving"
                )

                if len(mejor_orden) > 1:
                    waypoints = [
                        f"{puntos[i][0]},{puntos[i][1]}"
                        for i in mejor_orden[:-1]
                    ]

                    url_ruta += (
                        "&waypoints="
                        + urllib.parse.quote("|".join(waypoints))
                    )

                st.link_button(
                    "📍 Abrir ruta optimizada en Google Maps",
                    url_ruta,
                    use_container_width=True
                )

                st.caption(
                    "La ruta comienza en la bodega y termina "
                    "en el último cliente. No incluye regreso "
                    "automático a la bodega."
                )
                 # Guardar temporalmente la propuesta para asignarla
                # desde el módulo de despacho.
                st.session_state["ruta_propuesta"] = {
                    "id": uuid.uuid4().hex[:12].upper(),
                    "pedido_numeros": [
                        pedido["numero"] for pedido in pedidos_ordenados
                    ],
                    "duracion_segundos": mejor_resultado["duracion_segundos"],
                    "distancia_metros": mejor_resultado["distancia_metros"],
                    "url": url_ruta,
                    "creada_en": datetime.now(
                        ZoneInfo("America/Bogota")
                    ).isoformat()
                }

            except urllib.error.HTTPError as error:
                detalle = error.read().decode(
                    "utf-8", errors="replace"
                )

                st.error(
                    f"Google Routes API devolvió el error "
                    f"HTTP {error.code}."
                )
                st.code(detalle)

            except Exception as error:
                st.error(
                    "No fue posible optimizar la ruta."
                )
                st.caption(str(error))

    if st.button("Limpiar selección de ruta"):
        st.session_state.destinos_ruta = []
        st.session_state.pop("ruta_optimizada", None)
        st.rerun()

else:
    st.info(
        "Selecciona al menos un pedido para preparar una ruta."
    )

# ============================================================
# 14. DESPACHO Y GESTIÓN DE MENSAJEROS
# ============================================================

st.divider()
st.header("🚚 Despacho y mensajeros")
st.caption(
    "Registra mensajeros, revisa las rutas optimizadas y asigna "
    "cada recorrido antes de que salga de la bodega."
)

if db is None:
    st.warning(
        "Firestore no está disponible. No se pueden guardar "
        "mensajeros ni asignaciones de forma permanente."
    )
else:
    with st.expander("➕ Registrar mensajero", expanded=False):
        with st.form("form_nuevo_mensajero", clear_on_submit=True):
            nombre_mensajero = st.text_input("Nombre del mensajero *")
            telefono_mensajero = st.text_input("Teléfono / WhatsApp *")
            guardar_mensajero = st.form_submit_button(
                "Guardar mensajero", type="primary"
            )

        if guardar_mensajero:
            if not nombre_mensajero.strip() or not telefono_mensajero.strip():
                st.error("Completa el nombre y el teléfono del mensajero.")
            else:
                try:
                    mensajero_id = uuid.uuid4().hex[:12].upper()
                    db.collection("mensajeros").document(mensajero_id).set({
                        "id": mensajero_id,
                        "nombre": nombre_mensajero.strip(),
                        "telefono": telefono_mensajero.strip(),
                        "activo": True,
                        "creado_en": datetime.now(
                            ZoneInfo("America/Bogota")
                        ).isoformat()
                    })
                    st.success("Mensajero registrado correctamente.")
                    st.rerun()
                except Exception as error:
                    st.error("No se pudo registrar el mensajero.")
                    st.caption(str(error))

    try:
        mensajeros_registrados = []
        for doc in db.collection("mensajeros").stream():
            m = doc.to_dict() or {}
            m.setdefault("id", doc.id)
            m.setdefault("nombre", "Sin nombre")
            m.setdefault("telefono", "")
            m.setdefault("activo", True)
            mensajeros_registrados.append(m)

        st.subheader("👥 Mensajeros registrados")
        if not mensajeros_registrados:
            st.info("Registra el primer mensajero para poder asignar rutas.")
        else:
            for m in mensajeros_registrados:
                col_nombre, col_tel, col_estado = st.columns([3, 2, 1.5])
                col_nombre.write(f"**{m['nombre']}**")
                col_tel.write(m.get("telefono", ""))
                estado_m = col_estado.selectbox(
                    "Estado", ["Activo", "Inactivo"],
                    index=0 if m.get("activo", True) else 1,
                    key="estado_mensajero_" + m["id"],
                    label_visibility="collapsed"
                )
                activo_nuevo = estado_m == "Activo"
                if activo_nuevo != m.get("activo", True):
                    db.collection("mensajeros").document(m["id"]).update(
                        {"activo": activo_nuevo}
                    )
                    st.rerun()

        activos = [m for m in mensajeros_registrados if m.get("activo", True)]
        st.subheader("📋 Asignar propuesta optimizada")
        propuesta = st.session_state.get("ruta_propuesta")

        if propuesta:
            st.write(
                f"**{len(propuesta['pedido_numeros'])} pedidos** · "
                f"Propuesta {propuesta['id']}"
            )
            st.caption("Revisa la ruta y selecciona el mensajero responsable.")
            if not activos:
                st.warning("Primero registra al menos un mensajero activo.")
            else:
                opciones = {
                    f"{m['nombre']} · {m.get('telefono', '')}": m
                    for m in activos
                }
                with st.form("form_asignar_ruta"):
                    etiqueta = st.selectbox("Asignar a", list(opciones.keys()))
                    confirmar = st.form_submit_button(
                        "✅ Guardar y asignar ruta", type="primary"
                    )

                if confirmar:
                    mensajero = opciones[etiqueta]
                    numeros = propuesta["pedido_numeros"]
                    try:
                        # Comprobación previa para evitar doble asignación.
                        rutas_existentes = [
                            d.to_dict() or {} for d in db.collection("rutas").stream()
                        ]
                        ocupados = set()
                        for r in rutas_existentes:
                            if r.get("estado") in ("Asignada", "En camino"):
                                ocupados.update(r.get("pedido_numeros", []))
                        duplicados = [n for n in numeros if n in ocupados]

                        if duplicados:
                            st.error(
                                "No se asignó: estos pedidos ya están en una "
                                "ruta activa: " + ", ".join(duplicados)
                            )
                        else:
                            ruta_id = propuesta["id"]
                            ahora = datetime.now(
                                ZoneInfo("America/Bogota")
                            ).isoformat()
                            batch = db.batch()
                            batch.set(db.collection("rutas").document(ruta_id), {
                                "id": ruta_id,
                                "estado": "Asignada",
                                "mensajero_id": mensajero["id"],
                                "mensajero_nombre": mensajero["nombre"],
                                "mensajero_telefono": mensajero["telefono"],
                                "pedido_numeros": numeros,
                                "origen": {
                                    "latitud": BODEGA_LATITUD,
                                    "longitud": BODEGA_LONGITUD
                                },
                                "duracion_segundos": propuesta["duracion_segundos"],
                                "distancia_metros": propuesta["distancia_metros"],
                                "url_google_maps": propuesta["url"],
                                "creada_en": ahora,
                                "despachada_en": None,
                                "finalizada_en": None
                            })
                            for numero in numeros:
                                batch.update(db.collection("pedidos").document(numero), {
                                    "ruta_id": ruta_id,
                                    "mensajero_id": mensajero["id"],
                                    "mensajero_nombre": mensajero["nombre"],
                                    "estado": "Asignado"
                                })
                            batch.commit()
                            st.session_state.pop("ruta_propuesta", None)
                            st.session_state.destinos_ruta = []
                            st.success(f"Ruta {ruta_id} asignada a {mensajero['nombre']}.")
                            st.rerun()
                    except Exception as error:
                        st.error("No se pudo guardar la asignación en Firestore.")
                        st.caption(str(error))
        else:
            st.info("Optimiza una ruta en la sección anterior para crear una propuesta de despacho.")

        st.subheader("🛣️ Rutas guardadas")
        rutas_guardadas = [d.to_dict() or {} for d in db.collection("rutas").stream()]
        rutas_guardadas.sort(key=lambda r: r.get("creada_en", ""), reverse=True)
        if not rutas_guardadas:
            st.info("Todavía no hay rutas guardadas.")
        for ruta in rutas_guardadas:
            with st.expander(
                f"Ruta {ruta.get('id', '')} · {ruta.get('mensajero_nombre', 'Sin asignar')} · {ruta.get('estado', 'Sin estado')}"
            ):
                st.write("**Pedidos:** " + ", ".join(ruta.get("pedido_numeros", [])))
                st.write(f"**Distancia estimada:** {ruta.get('distancia_metros', 0) / 1000:.1f} km")
                st.write(f"**Tiempo estimado:** {round(ruta.get('duracion_segundos', 0) / 60)} min")
                if ruta.get("url_google_maps"):
                    st.link_button(
                        "📍 Abrir ruta en Google Maps", ruta["url_google_maps"],
                        key="abrir_ruta_" + ruta.get("id", uuid.uuid4().hex),
                        use_container_width=True
                    )
                if ruta.get("estado") == "Asignada":
                    if st.button("🚚 Confirmar salida", key="salida_" + ruta.get("id", "")):
                        db.collection("rutas").document(ruta["id"]).update({
                            "estado": "En camino",
                            "despachada_en": datetime.now(ZoneInfo("America/Bogota")).isoformat()
                        })
                        st.rerun()
                if ruta.get("estado") in ("Asignada", "En camino"):
                    if st.button("Finalizar ruta", key="finalizar_" + ruta.get("id", "")):
                        db.collection("rutas").document(ruta["id"]).update({
                            "estado": "Finalizada",
                            "finalizada_en": datetime.now(ZoneInfo("America/Bogota")).isoformat()
                        })
                        st.rerun()
    except Exception as error:
        st.error("No se pudo cargar el módulo de despacho.")
        st.caption(str(error))

# ============================================================
# 15. GENERAR ETIQUETA TÉRMICA
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
