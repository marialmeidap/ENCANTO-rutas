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

import folium
from streamlit_folium import st_folium

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
    """Busca direcciones y puntos de referencia con Google Places."""
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
            # Sesgo geográfico amplio para Cali y municipios cercanos.
            "locationBias": {
                "circle": {
                    "center": {"latitude": 3.45, "longitude": -76.53},
                    "radius": 50000.0
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
                "texto": texto_sugerido,
                "tipo": "place"
            })
    return sugerencias


def buscar_direcciones_aproximadas(texto):
    """Usa Geocoding API como respaldo si Places no ofrece sugerencias."""
    if not GOOGLE_MAPS_API_KEY or len(texto.strip()) < 3:
        return []

    parametros = urllib.parse.urlencode({
        "address": texto.strip(),
        "components": "country:CO",
        "region": "co",
        "language": "es",
        "key": GOOGLE_MAPS_API_KEY
    })
    url = "https://maps.googleapis.com/maps/api/geocode/json?" + parametros
    solicitud = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(solicitud, timeout=15) as respuesta:
        resultado = json.loads(respuesta.read().decode("utf-8"))

    sugerencias = []
    for item in resultado.get("results", [])[:5]:
        ubicacion = item.get("geometry", {}).get("location", {})
        lat = ubicacion.get("lat")
        lon = ubicacion.get("lng")
        direccion = item.get("formatted_address", "")
        if lat is not None and lon is not None and direccion:
            sugerencias.append({
                "id": "geocode:" + str(lat) + "," + str(lon),
                "texto": "📍 Aproximada: " + direccion,
                "tipo": "geocode",
                "direccion": direccion,
                "latitud": float(lat),
                "longitud": float(lon)
            })
    return sugerencias


def obtener_detalles_lugar(place_id):
    """Consulta la dirección confirmada y sus coordenadas en Places."""
    url = PLACES_DETAILS_URL + urllib.parse.quote(place_id, safe="")
    resultado = solicitar_places(
        "GET", url, campos="id,formattedAddress,location,displayName"
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

if "ubicacion_mapa" not in st.session_state:
    st.session_state.ubicacion_mapa = None

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

# Estilo visual: panel más moderno, colores de marca y tarjetas limpias.
st.markdown("""
<style>
:root { --encanto-ink: #241b2f; --encanto-purple: #6d3fc0; --encanto-pink: #e85d9e; --encanto-teal: #19a7a0; }
.stApp { background: linear-gradient(180deg, #fff9fc 0%, #f7f5ff 48%, #ffffff 100%); }
[data-testid="stHeader"] { background: rgba(255,255,255,.75); }
h1, h2, h3 { color: var(--encanto-ink); }
h1 { letter-spacing: -0.035em; }
div[data-testid="stMetric"] { background: linear-gradient(135deg,#ffffff,#f5efff); border: 1px solid #e7daf8; padding: 14px 16px; border-radius: 16px; box-shadow: 0 4px 14px rgba(67,35,99,.06); }
div[data-testid="stMetricLabel"] { color: #6d5b7c; }
div[data-testid="stMetricValue"] { color: #522b91; }
.stButton > button, .stLinkButton > a, div[data-testid="stFormSubmitButton"] button { border-radius: 12px; border: 1px solid #d9c7f5; font-weight: 650; transition: all .15s ease; }
.stButton > button[kind="primary"], div[data-testid="stFormSubmitButton"] button[kind="primary"] { background: linear-gradient(90deg,#6d3fc0,#a34fba); color: white; border: 0; }
div[data-testid="stExpander"] { background: rgba(255,255,255,.88); border: 1px solid #e6ddec; border-radius: 14px; overflow: hidden; }
div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea, div[data-testid="stSelectbox"] div[role="combobox"] { border-radius: 10px; }
.encanto-banner { padding: 20px 24px; border-radius: 18px; color: white; background: linear-gradient(110deg,#49257d 0%,#8547bd 55%,#e85d9e 100%); margin: 10px 0 22px 0; box-shadow: 0 8px 24px rgba(83,40,127,.16); }
.encanto-banner p { margin: 5px 0 0 0; color: #f8eefe; }
</style>
<div class="encanto-banner"><h2 style="color:white;margin:0">✨ Tu operación, más clara y organizada</h2><p>Pedidos · Recogidas · Rutas · Entregas — Encanto Capilar</p></div>
""", unsafe_allow_html=True)

# Roles y credenciales: configurar en variables de entorno/Secret Manager de Cloud Run.
# No guardar contraseñas en el repositorio ni compartirlas por chat.
ADMIN_USER = os.environ.get("ENCANTO_ADMIN_USER", "")
ADMIN_PASSWORD = os.environ.get("ENCANTO_ADMIN_PASSWORD", "")
BODEGA_USER = os.environ.get("ENCANTO_BODEGA_USER", "")
BODEGA_PASSWORD = os.environ.get("ENCANTO_BODEGA_PASSWORD", "")

if "usuario_encanto" not in st.session_state:
    st.session_state.usuario_encanto = None
if "rol_encanto" not in st.session_state:
    st.session_state.rol_encanto = None

with st.sidebar:
    st.markdown("## 🔐 Acceso del equipo")
    if st.session_state.rol_encanto:
        st.success(f"Sesión: {st.session_state.usuario_encanto} · {st.session_state.rol_encanto}")
        if st.button("Cerrar sesión", use_container_width=True):
            st.session_state.usuario_encanto = None
            st.session_state.rol_encanto = None
            st.rerun()
    else:
        with st.form("login_encanto"):
            usuario_login = st.text_input("Usuario")
            password_login = st.text_input("Contraseña", type="password")
            entrar = st.form_submit_button("Ingresar", type="primary", use_container_width=True)
        if entrar:
            if ADMIN_USER and ADMIN_PASSWORD and usuario_login == ADMIN_USER and password_login == ADMIN_PASSWORD:
                st.session_state.usuario_encanto = usuario_login
                st.session_state.rol_encanto = "Administradora"
                st.rerun()
            elif BODEGA_USER and BODEGA_PASSWORD and usuario_login == BODEGA_USER and password_login == BODEGA_PASSWORD:
                st.session_state.usuario_encanto = usuario_login
                st.session_state.rol_encanto = "Bodega"
                st.rerun()
            else:
                st.error("Credenciales incorrectas o no configuradas.")
    if not all([ADMIN_USER, ADMIN_PASSWORD, BODEGA_USER, BODEGA_PASSWORD]):
        st.warning("Falta configurar uno o más secretos ENCANTO_* en Cloud Run. Edición y eliminación permanecerán bloqueadas hasta configurarlos.")
    st.caption("Administradora: edición y eliminación. Bodega: registro de recogidas.")


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

col_refrescar, col_estado = st.columns([1, 4])
with col_refrescar:
    if st.button("🔄 Actualizar pedidos", use_container_width=True):
        try:
            if db is not None:
                st.session_state.pedidos = cargar_pedidos()
                st.session_state.pedidos_cargados = True
                st.success("Pedidos sincronizados con Firestore.")
                st.rerun()
            else:
                st.warning("Firestore no está conectado.")
        except Exception as error:
            st.error("No se pudieron actualizar los pedidos.")
            st.caption(str(error))
with col_estado:
    st.caption("Los cambios guardados se sincronizan con Firestore. Usa Actualizar pedidos para traer cambios recientes de otros usuarios.")

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

# La dirección se mantiene fuera del formulario para que las sugerencias
# se actualicen al escribir.
direccion_escrita = st.text_input(
    "Dirección del cliente *",
    key="direccion_input",
    placeholder="Ej.: Calle 5 # 10-20, Cali o un punto de referencia"
)

# Al cambiar el texto, se descartan coordenadas de una búsqueda anterior.
texto_actual = direccion_escrita.strip()
if st.session_state.direccion_confirmada and texto_actual != st.session_state.direccion_confirmada.get("texto_busqueda", ""):
    st.session_state.direccion_confirmada = None
    st.session_state.ubicacion_mapa = None

if texto_actual and len(texto_actual) >= 3:
    if GOOGLE_MAPS_API_KEY:
        try:
            sugerencias = buscar_direcciones(texto_actual)
            if not sugerencias:
                sugerencias = buscar_direcciones_aproximadas(texto_actual)
            st.session_state.sugerencias_direccion = sugerencias
        except urllib.error.HTTPError as error:
            # Aunque las APIs de Google fallen, el usuario puede fijar el punto manualmente.
            st.session_state.sugerencias_direccion = []
            st.warning(
                "Google no devolvió sugerencias para esta dirección. "
                "Puedes fijar el punto manualmente en el mapa."
            )
            st.caption(f"Código HTTP: {error.code}")
        except Exception as error:
            st.session_state.sugerencias_direccion = []
            st.warning("No se pudieron cargar sugerencias; puedes marcar el punto en el mapa.")
            st.caption(str(error))
    else:
        st.session_state.sugerencias_direccion = []
else:
    st.session_state.sugerencias_direccion = []

sugerencias = st.session_state.sugerencias_direccion
if sugerencias:
    opciones = ["Selecciona una dirección"] + [x["texto"] for x in sugerencias]
    seleccion = st.selectbox(
        "📍 Direcciones encontradas (incluye aproximadas)",
        opciones,
        key="seleccion_direccion"
    )
    if seleccion != opciones[0]:
        sugerencia = next((x for x in sugerencias if x["texto"] == seleccion), None)
        lugar_actual = st.session_state.direccion_confirmada
        # No volver a colocar el pin de Google en cada rerun: eso impediría
        # que el usuario ajustara manualmente el punto sobre el mapa.
        pin_manual_activo = bool(
            lugar_actual
            and lugar_actual.get("origen_coordenadas") == "pin_manual"
            and lugar_actual.get("texto_busqueda", "") == texto_actual
        )
        sugerencia_ya_aplicada = bool(
            lugar_actual
            and sugerencia
            and lugar_actual.get("texto_busqueda", "") == texto_actual
            and (
                lugar_actual.get("place_id") == sugerencia.get("id")
                or (
                    sugerencia.get("tipo") == "geocode"
                    and lugar_actual.get("latitud") == sugerencia.get("latitud")
                    and lugar_actual.get("longitud") == sugerencia.get("longitud")
                )
            )
        )
        if sugerencia and not pin_manual_activo and not sugerencia_ya_aplicada:
            try:
                if sugerencia.get("tipo") == "geocode":
                    lugar = {
                        "place_id": None,
                        "direccion": sugerencia["direccion"],
                        "latitud": sugerencia["latitud"],
                        "longitud": sugerencia["longitud"],
                        "aproximada": True
                    }
                else:
                    lugar = obtener_detalles_lugar(sugerencia["id"])
                    lugar["aproximada"] = False
                lugar["texto_busqueda"] = texto_actual
                st.session_state.direccion_confirmada = lugar
                st.session_state.ubicacion_mapa = {
                    "latitud": float(lugar["latitud"]),
                    "longitud": float(lugar["longitud"])
                }
                st.success("Ubicación seleccionada. Si hace falta, ajusta el punto en el mapa.")
            except Exception as error:
                st.warning("No se pudieron obtener los detalles de esa sugerencia. Puedes fijar el punto en el mapa.")
                st.caption(str(error))

# Mapa interactivo: el usuario puede hacer clic donde realmente está el cliente.
st.markdown("#### 🗺️ Confirma la ubicación en el mapa")
st.caption("Haz clic sobre el mapa para colocar o ajustar el pin. Puedes acercar el mapa con la rueda del ratón.")
ubicacion_actual = st.session_state.ubicacion_mapa
if ubicacion_actual:
    centro_lat = float(ubicacion_actual["latitud"])
    centro_lon = float(ubicacion_actual["longitud"])
    zoom_mapa = 16
else:
    centro_lat, centro_lon, zoom_mapa = 3.4516, -76.5320, 12

mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=zoom_mapa, control_scale=True)
if ubicacion_actual:
    folium.Marker(
        [centro_lat, centro_lon],
        tooltip="Ubicación seleccionada",
        popup="Punto del cliente",
        icon=folium.Icon(color="purple", icon="map-marker")
    ).add_to(mapa)

resultado_mapa = st_folium(
    mapa,
    width=None,
    height=360,
    returned_objects=["last_clicked"],
    key="mapa_direccion_cliente_" + str(abs(hash(texto_actual)))
)
click_mapa = (resultado_mapa or {}).get("last_clicked")
if click_mapa and click_mapa.get("lat") is not None and click_mapa.get("lng") is not None:
    nueva_ubicacion = {
        "latitud": float(click_mapa["lat"]),
        "longitud": float(click_mapa["lng"])
    }
    anterior = st.session_state.ubicacion_mapa
    if not anterior or abs(float(anterior["latitud"]) - nueva_ubicacion["latitud"]) > 0.00001 or abs(float(anterior["longitud"]) - nueva_ubicacion["longitud"]) > 0.00001:
        st.session_state.ubicacion_mapa = nueva_ubicacion
        st.session_state.direccion_confirmada = {
            "place_id": None,
            "direccion": texto_actual,
            "texto_busqueda": texto_actual,
            "latitud": nueva_ubicacion["latitud"],
            "longitud": nueva_ubicacion["longitud"],
            "aproximada": True,
            "origen_coordenadas": "pin_manual"
        }
        st.rerun()

ubicacion_final = st.session_state.ubicacion_mapa
if ubicacion_final:
    st.success(
        f"📌 Punto fijado: {ubicacion_final['latitud']:.6f}, "
        f"{ubicacion_final['longitud']:.6f}"
    )
    st.caption("Estas coordenadas se guardarán con el pedido y se usarán para optimizar la ruta.")
else:
    st.info("Selecciona una sugerencia o fija el punto del cliente en el mapa antes de guardar para que el pedido pueda entrar en la optimización.")

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
        ubicacion_final = st.session_state.ubicacion_mapa

        # Si Google confirmó una dirección, guardamos el formato de Google.
        # Si se fijó el pin manualmente, conservamos el texto digitado.
        direccion_final = (
            direccion_confirmada.get("direccion")
            if direccion_confirmada and direccion_confirmada.get("direccion")
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
                    float(ubicacion_final["latitud"])
                    if ubicacion_final else (
                        direccion_confirmada.get("latitud") if direccion_confirmada else None
                    )
                ),
                "longitud": (
                    float(ubicacion_final["longitud"])
                    if ubicacion_final else (
                        direccion_confirmada.get("longitud") if direccion_confirmada else None
                    )
                ),
                "ubicacion_aproximada": bool(
                    direccion_confirmada.get("aproximada", False)
                    if direccion_confirmada else ubicacion_final is not None
                ),
                "origen_coordenadas": (
                    direccion_confirmada.get("origen_coordenadas", "google_places")
                    if direccion_confirmada else (
                        "pin_manual" if ubicacion_final else None
                    )
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
                st.session_state.ubicacion_mapa = None
                st.rerun()

            except Exception as error:
                st.error(
                    "No se pudo guardar el pedido en Firestore."
                )
                st.caption(str(error))

# ============================================================
# 9. LISTA DE PEDIDOS REGISTRADOS
st.divider()
st.header("📋 Pedidos registrados")
st.caption("Busca, filtra por fecha de creación y gestiona cada pedido desde su ficha.")

if not st.session_state.pedidos:
    st.info("Todavía no hay pedidos registrados.")
else:
    todos_pedidos = list(st.session_state.pedidos)
    fechas_validas = [obtener_fecha_pedido(x) for x in todos_pedidos]
    fechas_validas = [x for x in fechas_validas if x is not None]
    fecha_min = min(fechas_validas) if fechas_validas else hoy
    fecha_max = max(fechas_validas) if fechas_validas else hoy
    c_busqueda, c_estado, c_desde, c_hasta = st.columns([2.2, 1.1, 1.2, 1.2])
    with c_busqueda:
        busqueda_pedidos = st.text_input("🔎 Buscar pedido", placeholder="Número, cliente, WhatsApp o dirección", key="buscar_pedidos_registrados")
    with c_estado:
        filtro_estado_pedidos = st.selectbox("Estado", ["Todos", "Pendiente", "Asignado", "En camino", "Entregado", "Novedad"], key="estado_filtro_pedidos")
    with c_desde:
        fecha_desde_registro = st.date_input("Registrado desde", value=fecha_min, min_value=fecha_min, max_value=fecha_max, format="DD/MM/YYYY", key="fecha_desde_registro")
    with c_hasta:
        fecha_hasta_registro = st.date_input("Registrado hasta", value=fecha_max, min_value=fecha_min, max_value=fecha_max, format="DD/MM/YYYY", key="fecha_hasta_registro")
    if fecha_desde_registro > fecha_hasta_registro:
        st.warning("La fecha inicial no puede ser posterior a la fecha final.")
        pedidos_registrados_filtrados = []
    else:
        texto_busqueda = busqueda_pedidos.strip().casefold()
        pedidos_registrados_filtrados = []
        for pedido_filtro in todos_pedidos:
            fecha_filtro = obtener_fecha_pedido(pedido_filtro)
            if fecha_filtro is None or not (fecha_desde_registro <= fecha_filtro <= fecha_hasta_registro):
                continue
            if filtro_estado_pedidos != "Todos" and pedido_filtro.get("estado", "Pendiente") != filtro_estado_pedidos:
                continue
            campos_busqueda = " ".join(str(pedido_filtro.get(campo, "")) for campo in ("numero", "nombre", "telefono", "direccion", "barrio", "ciudad")).casefold()
            if texto_busqueda and texto_busqueda not in campos_busqueda:
                continue
            pedidos_registrados_filtrados.append(pedido_filtro)
    m1, m2, m3 = st.columns(3)
    m1.metric("Coincidencias", len(pedidos_registrados_filtrados))
    m2.metric("Recogidos", sum(bool(x.get("recogido")) for x in pedidos_registrados_filtrados))
    m3.metric("Pendientes de recogida", sum(not bool(x.get("recogido")) for x in pedidos_registrados_filtrados))
    if not pedidos_registrados_filtrados:
        st.info("No hay pedidos que coincidan con los filtros seleccionados.")

for p in pedidos_registrados_filtrados:
    i = next((idx for idx, original in enumerate(st.session_state.pedidos) if original.get("numero") == p.get("numero")), 0)

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
                if db is None:
                    raise RuntimeError("Firestore no está conectado; el cambio no se guardó.")
                actualizar_pedido(
                    p["numero"],
                    {"estado": estado, "estado_actualizado_en": datetime.now(ZoneInfo("America/Bogota")).isoformat()}
                )
                st.session_state.pedidos[i]["estado"] = estado
                st.session_state.pedidos[i]["estado_actualizado_en"] = datetime.now(ZoneInfo("America/Bogota")).isoformat()
                st.rerun()

            except Exception as error:
                st.error("No se pudo actualizar el estado en Firestore.")
                st.caption(str(error))

        st.markdown("##### 📦 Control de recogida en bodega")
        recogido = bool(p.get("recogido", False))
        st.caption(
            "Recogido: " + ("Sí" if recogido else "No") +
            (f" · {p.get('recogido_en', '')}" if p.get("recogido_en") else "")
        )
        if st.session_state.rol_encanto in ("Administradora", "Bodega"):
            texto_boton = "↩️ Deshacer recogida" if recogido else "✅ Marcar paquete recogido"
            if st.button(texto_boton, key="recogida_" + p["numero"], use_container_width=True):
                try:
                    if db is None:
                        raise RuntimeError("Firestore no está conectado; la recogida no se guardó.")
                    ahora_recogida = datetime.now(ZoneInfo("America/Bogota")).isoformat()
                    cambios_recogida = {
                        "recogido": not recogido,
                        "recogido_en": ahora_recogida if not recogido else None,
                        "recogido_por": st.session_state.usuario_encanto if not recogido else None
                    }
                    actualizar_pedido(p["numero"], cambios_recogida)
                    st.session_state.pedidos[i].update(cambios_recogida)
                    st.rerun()
                except Exception as error:
                    st.error("No se pudo guardar el control de recogida.")
                    st.caption(str(error))
        else:
            st.caption("Inicia sesión como Bodega o Administradora para registrar la recogida.")

        # Edición y eliminación solo para la administradora.
        if st.session_state.rol_encanto == "Administradora":
            with st.expander("✏️ Editar datos del pedido"):
                with st.form("editar_pedido_" + p["numero"]):
                    ed_nombre = st.text_input("Nombre", value=p.get("nombre", ""))
                    ed_telefono = st.text_input("WhatsApp", value=p.get("telefono", ""))
                    ed_direccion = st.text_input("Dirección", value=p.get("direccion", ""))
                    ed_barrio = st.text_input("Barrio", value=p.get("barrio", ""))
                    ed_ciudad = st.text_input("Ciudad", value=p.get("ciudad", "Cali"))
                    ed_referencia = st.text_input("Referencia", value=p.get("referencia", ""))
                    ed_producto = st.text_input("Producto", value=p.get("producto", ""))
                    ed_valor = st.number_input("Valor a cobrar (COP)", min_value=0, step=1000, value=max(0, int(p.get("valor", 0) or 0)))
                    ed_observaciones = st.text_area("Observaciones", value=p.get("observaciones", ""))
                    guardar_edicion = st.form_submit_button("💾 Guardar cambios", type="primary")
                if guardar_edicion:
                    if not ed_nombre.strip() or not ed_telefono.strip() or not ed_direccion.strip():
                        st.error("Nombre, WhatsApp y dirección son obligatorios.")
                    else:
                        cambios_edicion = {
                            "nombre": ed_nombre.strip(), "telefono": ed_telefono.strip(),
                            "direccion": ed_direccion.strip(), "barrio": ed_barrio.strip(),
                            "ciudad": ed_ciudad.strip(), "referencia": ed_referencia.strip(),
                            "producto": ed_producto.strip(), "valor": int(ed_valor),
                            "observaciones": ed_observaciones.strip(),
                            "editado_en": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
                            "editado_por": st.session_state.usuario_encanto
                        }
                        try:
                            if db is None:
                                raise RuntimeError("Firestore no está conectado; la edición no se guardó.")
                            actualizar_pedido(p["numero"], cambios_edicion)
                            st.session_state.pedidos[i].update(cambios_edicion)
                            st.success("Pedido actualizado.")
                            st.rerun()
                        except Exception as error:
                            st.error("No se pudo guardar la edición.")
                            st.caption(str(error))
            with st.expander("🗑️ Eliminar pedido"):
                st.warning("Esta acción elimina el pedido de Firestore y no se puede deshacer.")
                confirmar_eliminar = st.checkbox("Confirmo que deseo eliminar este pedido", key="confirmar_eliminar_" + p["numero"])
                if st.button("Eliminar definitivamente", key="eliminar_" + p["numero"], disabled=not confirmar_eliminar):
                    try:
                        if db is None:
                            raise RuntimeError("Firestore no está conectado; el pedido no se eliminó.")
                        db.collection("pedidos").document(p["numero"]).delete()
                        st.session_state.pedidos = [x for x in st.session_state.pedidos if x.get("numero") != p["numero"]]
                        st.session_state.destinos_ruta = [x for x in st.session_state.destinos_ruta if x != p["numero"]]
                        st.success("Pedido eliminado.")
                        st.rerun()
                    except Exception as error:
                        st.error("No se pudo eliminar el pedido.")
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
                            st.session_state.pedidos = cargar_pedidos()
                            st.session_state.pedidos_cargados = True
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
