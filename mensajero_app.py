import os
import html
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote

import streamlit as st
from google.cloud import firestore
from streamlit_geolocation import streamlit_geolocation

# ENCANTO Mensajero - primera versión móvil
st.set_page_config(page_title="ENCANTO Mensajero", page_icon="🛵", layout="centered")

DATABASE_ID = "encanto-rutas-db"
TZ = ZoneInfo("America/Bogota")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# Interfaz móvil: alto contraste, controles táctiles y tarjetas compactas.
st.markdown("""
<style>
/* Forzar colores legibles aunque el navegador o Streamlit use tema oscuro. */
:root {
    color-scheme: light;
}
html, body, [data-testid="stAppViewContainer"], .stApp {
    background: #fffafd !important;
    color: #292033 !important;
}
[data-testid="stHeader"] {
    background: rgba(255,250,253,.96) !important;
}
[data-testid="stMain"], [data-testid="stMainBlockContainer"] {
    color: #292033 !important;
}
.block-container {
    max-width: 680px;
    padding: 2.5rem 1rem 2rem;
}
.encanto-note {
    padding: 14px 15px;
    margin: 8px 0 14px;
    border-radius: 13px;
    border: 1px solid #dfcef2;
    background: #f2eaff !important;
    color: #342044 !important;
    font-size: 1rem;
    line-height: 1.5;
}
.encanto-note * { color: #342044 !important; }
.gps-cta {
    margin: 10px 0 14px;
    padding: 18px 14px;
    text-align: center;
    border-radius: 20px;
    border: 2px solid #d783f3;
    background: linear-gradient(145deg, #fff7ff 0%, #f3e4ff 100%);
    box-shadow: 0 5px 18px rgba(128, 50, 171, .12);
}
.gps-cta-icon {
    font-size: 2.2rem;
    line-height: 1.2;
    margin-bottom: 5px;
}
.gps-cta-title {
    color: #4a247b !important;
    font-size: 1.25rem;
    line-height: 1.3;
    font-weight: 800;
    margin-bottom: 14px;
}
.gps-cta-button {
    background: linear-gradient(110deg, #54228b, #9a36b6);
    color: #fff !important;
    padding: 15px 12px;
    border-radius: 14px;
    font-size: 1rem;
    line-height: 1.35;
    font-weight: 800;
    box-shadow: 0 4px 10px rgba(84, 34, 139, .22);
    margin-bottom: 12px;
}
.gps-cta-help {
    color: #44334f !important;
    font-size: .96rem;
    line-height: 1.5;
    margin: 4px 0 12px;
}
.gps-cta-help b { color: #4a247b !important; }
.gps-cta-privacy {
    background: #f0e0fb;
    color: #4a247b !important;
    padding: 11px;
    border-radius: 12px;
    font-size: .9rem;
    line-height: 1.4;
    text-align: left;
}
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4,
[data-testid="stText"],
[data-testid="stCaptionContainer"],
.stCaption,
label,
[data-testid="stWidgetLabel"] p {
    color: #292033 !important;
}
[data-testid="stCaptionContainer"], .stCaption {
    color: #62566b !important;
    font-size: .9rem !important;
    line-height: 1.45 !important;
}
.encanto-hero {
    padding: 18px 18px;
    border-radius: 18px;
    color: #fff !important;
    background: linear-gradient(115deg, #4a247b, #8750c2 62%, #d94f98);
    margin: 0 0 18px;
    box-shadow: 0 4px 14px rgba(74,36,123,.12);
}
.encanto-hero h1 {
    color: #fff !important;
    font-size: 1.55rem;
    line-height: 1.2;
    margin: 0;
}
.encanto-hero p {
    color: #fff !important;
    font-size: .98rem;
    line-height: 1.4;
    margin: 7px 0 0;
}
h1, h2, h3 {
    color: #342044 !important;
    letter-spacing: -.02em;
}
h2 { font-size: 1.35rem !important; }
h3 { font-size: 1.12rem !important; }
div[data-testid="stMetric"] {
    background: #fff !important;
    border: 1px solid #e5d7f1;
    padding: 10px 12px;
    border-radius: 14px;
    gap: 4px;
}
div[data-testid="stMetric"] label,
div[data-testid="stMetric"] [data-testid="stMetricLabel"],
div[data-testid="stMetric"] [data-testid="stMetricValue"],
div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    color: #342044 !important;
}
[data-testid="stVerticalBlockBorderWrapper"] {
    background: #fff !important;
    border: 1px solid #e7d9f0 !important;
    border-radius: 16px !important;
    padding: 12px !important;
}
.pill {
    display: inline-block;
    padding: 5px 10px;
    border-radius: 999px;
    background: #f0e7ff;
    color: #522d86 !important;
    font-size: .85rem;
    font-weight: 750;
    border: 1px solid #e2d0fa;
}
/* Botones con buen contraste y altura cómoda para tocar en el celular. */
.stButton button,
.stLinkButton a,
[data-testid="stFormSubmitButton"] button {
    width: 100%;
    min-height: 48px;
    border-radius: 13px !important;
    font-weight: 700 !important;
    font-size: 1rem !important;
    border: 1px solid #63379a !important;
    background: #63379a !important;
    color: #fff !important;
    box-shadow: none !important;
    padding: .65rem .8rem !important;
}
.stButton button p,
.stLinkButton a p,
[data-testid="stFormSubmitButton"] button p {
    color: #fff !important;
}
.stButton button:hover,
.stLinkButton a:hover,
[data-testid="stFormSubmitButton"] button:hover {
    background: #4a247b !important;
    border-color: #4a247b !important;
    color: #fff !important;
}
.stButton button:focus,
.stLinkButton a:focus,
[data-testid="stFormSubmitButton"] button:focus {
    box-shadow: 0 0 0 3px #e3d1f5 !important;
}
/* Campos de formulario: fondo blanco y texto oscuro, también en iPhone. */
input, textarea,
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea {
    background: #fff !important;
    color: #292033 !important;
    -webkit-text-fill-color: #292033 !important;
    border-color: #cbbbd9 !important;
}
input::placeholder, textarea::placeholder {
    color: #756980 !important;
    -webkit-text-fill-color: #756980 !important;
    opacity: 1 !important;
}
[data-baseweb="select"] > div {
    background: #fff !important;
    color: #292033 !important;
    border-color: #cbbbd9 !important;
}
[data-baseweb="select"] *, [data-baseweb="radio"] label,
[data-testid="stCheckbox"] label {
    color: #292033 !important;
}
[data-baseweb="radio"] label, [data-testid="stCheckbox"] label {
    min-height: 35px;
    align-items: center;
}
[data-testid="stForm"] {
    border: 1px solid #eadff2;
    border-radius: 14px;
    padding: 12px;
    background: #fff !important;
}
/* Avisos de Streamlit: fondos claros y texto oscuro legible. */
[data-testid="stAlert"],
[data-testid="stAlert"] > div,
[data-testid="stAlert"] [data-testid="stAlertContent"],
[data-testid="stAlert"] [data-testid="stMarkdownContainer"],
[data-testid="stAlert"] [role="alert"] {
    border-radius: 13px !important;
    background: #f2eaff !important;
    background-color: #f2eaff !important;
    color: #342044 !important;
    border-color: #dfcef2 !important;
}
[data-testid="stAlert"] *,
[data-testid="stAlert"] p,
[data-testid="stAlert"] div,
[data-testid="stAlert"] span,
[data-testid="stAlert"] svg {
    color: #342044 !important;
    fill: #63379a !important;
}
/* El componente GPS se muestra en un iframe separado: ajustamos su marco
   para evitar la franja negra exterior y que no ocupe todo el ancho. */
iframe[title*="streamlit_geolocation"],
iframe[title*="geolocation"] {
    display: block !important;
    width: 100% !important;
    max-width: 100% !important;
    height: 64px !important;
    min-height: 64px !important;
    border: 0 !important;
    border-radius: 12px !important;
    background: transparent !important;
    color-scheme: light !important;
    overflow: hidden !important;
}
hr {
    border-color: #e7d9f0 !important;
}
/* Ajustes específicos para pantallas pequeñas. */
@media (max-width: 600px) {
    .block-container {
        padding: 3.5rem .75rem 1.5rem !important;
    }
    .encanto-hero {
        padding: 15px;
        border-radius: 15px;
        margin-bottom: 14px;
    }
    .encanto-hero h1 {
        font-size: 1.35rem;
    }
    [data-testid="stMarkdownContainer"] h2 {
        font-size: 1.22rem !important;
    }
    [data-testid="stMarkdownContainer"] h3 {
        font-size: 1.05rem !important;
    }
    div[data-testid="stMetric"] {
        padding: 8px 7px;
    }
    div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
        font-size: .78rem !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.25rem !important;
    }
    .stButton button, .stLinkButton a,
    [data-testid="stFormSubmitButton"] button {
        min-height: 46px;
        font-size: .96rem !important;
    }
}
</style>
<div class="encanto-hero"><h1>🛵 ENCANTO Mensajero</h1><p>Tus rutas, tus entregas y tus novedades en un solo lugar.</p></div>
""", unsafe_allow_html=True)

@st.cache_resource
def get_db():
    return firestore.Client(database=DATABASE_ID)

def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")

def fmt_cop(value):
    try:
        return f"$ {int(value or 0):,}".replace(",", ".") + " COP"
    except (TypeError, ValueError):
        return "$ 0 COP"

def maps_url(order):
    lat = order.get("latitud") or order.get("latitude")
    lng = order.get("longitud") or order.get("longitude")
    if lat is not None and lng is not None:
        return f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"
    address = ", ".join(str(order.get(k, "")).strip() for k in ("direccion", "barrio", "ciudad") if order.get(k))
    return "https://www.google.com/maps/dir/?api=1&destination=" + quote(address)

def get_messenger_by_phone(db, messenger_id, phone):
    doc = db.collection("mensajeros").document(messenger_id).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    if not data.get("activo", True):
        return None
    stored_phone = "".join(c for c in str(data.get("telefono", "")) if c.isdigit())
    supplied_phone = "".join(c for c in str(phone) if c.isdigit())
    if not stored_phone or stored_phone != supplied_phone:
        return None
    data["id"] = data.get("id", doc.id)
    return data

def load_routes(db, messenger_id):
    routes = []
    for doc in db.collection("rutas").stream():
        r = doc.to_dict() or {}
        r.setdefault("id", doc.id)
        if r.get("mensajero_id") == messenger_id and r.get("estado") in ("Asignada", "En camino"):
            routes.append(r)
    routes.sort(key=lambda r: r.get("creada_en", ""))
    return routes

def load_orders(db, route):
    found = []
    for number in route.get("pedido_numeros", []):
        doc = db.collection("pedidos").document(str(number)).get()
        if doc.exists:
            order = doc.to_dict() or {}
            order.setdefault("numero", str(number))
            order["documento_id"] = doc.id
            found.append(order)
    # Preserve optimized order from pedido_numeros.
    return found

def update_order_and_route(db, order_number, changes):
    db.collection("pedidos").document(str(order_number)).update(changes)

def safe_text(value, fallback="No registrado"):
    value = str(value or "").strip()
    return html.escape(value if value else fallback)

db = None
db_error = None
try:
    db = get_db()
except Exception as exc:
    db_error = str(exc)

if db is None:
    st.error("No se pudo conectar con Firestore. Verifica la cuenta de servicio y los permisos del servicio Cloud Run.")
    if db_error:
        st.caption(db_error)
    st.stop()

if "courier_session" not in st.session_state:
    st.session_state.courier_session = None

with st.sidebar:
    st.markdown("### 🔐 Sesión del mensajero")
    if st.session_state.courier_session:
        st.success(st.session_state.courier_session.get("nombre", "Mensajero"))
        if st.button("Cerrar sesión", use_container_width=True):
            st.session_state.courier_session = None
            st.rerun()
    else:
        st.caption("Usa el ID de mensajero y el teléfono registrados por administración.")

if not st.session_state.courier_session:
    st.subheader("Ingresar")
    st.markdown('<div class="encanto-note">El ID y el teléfono deben coincidir con el registro de mensajeros de ENCANTO Rutas.</div>', unsafe_allow_html=True)
    with st.form("courier_login"):
        messenger_id = st.text_input("ID de mensajero", placeholder="Ej.: A1B2C3D4E5F6")
        phone = st.text_input("Teléfono registrado", placeholder="Número registrado en el panel")
        submit = st.form_submit_button("Entrar a mi ruta", type="primary", use_container_width=True)
    if submit:
        try:
            messenger = get_messenger_by_phone(db, messenger_id.strip().upper(), phone)
            if messenger:
                st.session_state.courier_session = {
                    "id": messenger["id"],
                    "nombre": messenger.get("nombre", "Mensajero"),
                    "telefono": messenger.get("telefono", "")
                }
                st.rerun()
            else:
                st.error("No pudimos validar los datos. Revisa el ID y el teléfono con administración.")
        except Exception as exc:
            st.error("No fue posible validar el acceso.")
            st.caption(str(exc))
    with st.expander("¿Dónde encuentro mi ID?"):
        st.write("Administración debe compartirte el ID del mensajero registrado en ENCANTO Rutas. Si no lo tienes, solicítalo.")
    st.caption("Versión piloto: este acceso valida ID + teléfono. Antes de uso público, se recomienda cambiarlo por PIN individual con hash o Firebase Authentication.")
    st.stop()

courier = st.session_state.courier_session
st.markdown(f"### Hola, {safe_text(courier['nombre'])} 👋")
st.caption(f"Última actualización: {datetime.now(TZ).strftime('%d/%m/%Y · %I:%M %p')}")

if st.button("🔄 Actualizar mis rutas", use_container_width=True):
    st.rerun()

st.markdown("### 📍 Mi ubicación GPS")
st.markdown("""
<div class="gps-cta">
  <div class="gps-cta-icon">📍</div>
  <div class="gps-cta-title">Activa tu ubicación para continuar</div>
  <div class="gps-cta-button">📍 PERMITIR UBICACIÓN PARA CONTINUAR</div>
  <div class="gps-cta-help">Toca el control de ubicación que aparece justo debajo y, cuando tu iPhone lo pregunte, selecciona <b>Permitir</b>.</div>
  <div class="gps-cta-privacy">🔒 Tu ubicación se compartirá con administración mientras uses la app.</div>
</div>
""", unsafe_allow_html=True)
gps = streamlit_geolocation()
if isinstance(gps, dict) and gps.get("latitude") is not None and gps.get("longitude") is not None:
    try:
        gps_lat = float(gps["latitude"])
        gps_lng = float(gps["longitude"])
        gps_accuracy = gps.get("accuracy")
        gps_record = {
            "mensajero_id": courier["id"],
            "mensajero_nombre": courier["nombre"],
            "latitud": gps_lat,
            "longitud": gps_lng,
            "precision_metros": float(gps_accuracy) if gps_accuracy is not None else None,
            "actualizado_en": now_iso(),
            "fuente": "navegador"
        }
        db.collection("ubicaciones_mensajeros").document(courier["id"]).set(gps_record, merge=True)
        st.success(f"Ubicación actualizada · {gps_lat:.5f}, {gps_lng:.5f}")
        st.caption("La ubicación más reciente queda guardada en Firestore para que pueda consultarse desde el panel administrativo.")
    except Exception as exc:
        st.warning("No se pudo guardar la ubicación GPS.")
        st.caption(str(exc))
else:
    st.info("Activa el permiso de ubicación del navegador para registrar tu posición. Si no aparece la solicitud, revisa los permisos del sitio en el navegador.")

try:
    routes = load_routes(db, courier["id"])
except Exception as exc:
    st.error("No se pudieron cargar tus rutas.")
    st.caption(str(exc))
    st.stop()

if not routes:
    st.success("No tienes rutas pendientes asignadas.")
    st.info("Cuando administración te asigne una ruta, aparecerá aquí.")
    st.stop()

for route in routes:
    route_id = route["id"]
    orders = load_orders(db, route)
    status = route.get("estado", "Asignada")

    # Mantener solo pedidos todavía activos y asignados a este mensajero.
    # El orden sigue siendo el definido por route["pedido_numeros"].
    active_orders = []
    for order in orders:
        order_state = order.get("estado", "Pendiente")
        assigned_to = order.get("mensajero_id")
        if assigned_to not in (None, "") and str(assigned_to) != str(courier["id"]):
            continue
        if order_state not in ("Entregado", "Novedad", "Cancelado", "Cancelada"):
            active_orders.append(order)

    total = len(orders)
    delivered = sum(o.get("estado") == "Entregado" for o in orders)
    incidents = sum(o.get("estado") == "Novedad" for o in orders)
    cancelled = sum(o.get("estado") in ("Cancelado", "Cancelada") for o in orders)
    st.markdown("---")
    st.markdown(f"## 🧭 Ruta {safe_text(route_id)}")
    st.markdown(f'<span class="pill">{safe_text(status)}</span>', unsafe_allow_html=True)

    m1, m2, m3 = st.columns(3)
    m1.metric("Pedidos", total)
    m2.metric("Entregados", delivered)
    m3.metric("Novedades", incidents)

    if route.get("distancia_metros"):
        st.caption(f"Distancia estimada: {route['distancia_metros']/1000:.1f} km · Duración estimada: {int(route.get('duracion_segundos',0)/60)} min")
    if route.get("url_google_maps"):
        st.link_button("🗺️ Abrir ruta completa en Google Maps", route["url_google_maps"], use_container_width=True)

    if status == "Asignada":
        st.warning("Confirma que recibiste los paquetes antes de salir.")
        if st.button("📦 Confirmar recogida y comenzar ruta", key=f"start_{route_id}", type="primary", use_container_width=True):
            try:
                batch = db.batch()
                batch.update(db.collection("rutas").document(route_id), {
                    "estado": "En camino",
                    "recogida_confirmada_en": now_iso(),
                    "despachada_en": now_iso(),
                    "recogida_confirmada_por": courier["id"]
                })
                for order in orders:
                    order_state = order.get("estado")
                    assigned_to = order.get("mensajero_id")
                    if order_state not in ("Entregado", "Novedad", "Cancelado", "Cancelada") and assigned_to in (None, "", courier["id"]):
                        batch.update(db.collection("pedidos").document(str(order["numero"])), {
                            "estado": "En camino",
                            "recogido": True,
                            "recogido_en": now_iso(),
                            "recogido_por": courier["nombre"],
                            "estado_actualizado_en": now_iso()
                        })
                batch.commit()
                st.success("Recogida registrada. ¡Buen recorrido!")
                st.rerun()
            except Exception as exc:
                st.error("No se pudo registrar la salida.")
                st.caption(str(exc))

    if active_orders:
        # La primera entrega activa de la ruta es la única que se presenta.
        order = active_orders[0]
        number = str(order.get("numero", ""))
        state = order.get("estado", "Pendiente")
        position = next((i for i, item in enumerate(orders) if str(item.get("numero", "")) == number), 0) + 1

        st.markdown("### 📦 Tu siguiente entrega")
        st.caption(f"Pedido {position} de {total} · Al guardar el resultado aparecerá el siguiente")
        with st.container(border=True):
            st.markdown(f"## Pedido {safe_text(number)}")
            st.markdown(f"**{safe_text(order.get('nombre'))}**")
            st.markdown(f'<span class="pill">{safe_text(state)}</span>', unsafe_allow_html=True)

            address = ", ".join(str(order.get(k, "")).strip() for k in ("direccion", "barrio", "ciudad") if order.get(k))
            st.write("📍", address or "Dirección no registrada")
            if order.get("referencia"):
                st.caption("Referencia: " + safe_text(order.get("referencia")))
            if order.get("telefono"):
                phone_clean = "".join(c for c in str(order.get("telefono")) if c.isdigit())
                st.link_button("📲 WhatsApp del cliente", f"https://wa.me/{phone_clean}", use_container_width=True)

            order_value = order.get("valor", 0)
            st.write("💵 Valor del pedido: **" + fmt_cop(order_value) + "**")
            st.link_button("➡️ Navegar a este cliente", maps_url(order), use_container_width=True)

            with st.form(f"delivery_{route_id}_{number}"):
                new_state = st.radio(
                    "Resultado de la visita",
                    ["Entregado", "Novedad"],
                    horizontal=True,
                    key=f"state_{route_id}_{number}"
                )
                incident_type = st.selectbox(
                    "Motivo de novedad",
                    ["Cliente ausente", "No responde", "Dirección incorrecta", "Cliente solicita reprogramar", "Cliente solicita cancelar", "Producto rechazado", "Otro"],
                    key=f"incident_{route_id}_{number}"
                )
                incident_note = st.text_area(
                    "Detalle / observaciones",
                    key=f"note_{route_id}_{number}",
                    placeholder="Describe qué pasó..."
                )
                cash_collected = st.checkbox(
                    "Confirmo que recibí el pago del cliente",
                    key=f"cash_{route_id}_{number}"
                )
                cash_amount = st.number_input(
                    "Valor recaudado (COP)",
                    min_value=0,
                    value=max(0, int(order_value or 0)),
                    step=1000,
                    key=f"cash_amount_{route_id}_{number}"
                )
                proof_photo = st.file_uploader(
                    "Foto de evidencia (opcional)",
                    type=["jpg", "jpeg", "png"],
                    key=f"photo_{route_id}_{number}"
                )
                save_delivery = st.form_submit_button(
                    "Guardar resultado y continuar",
                    type="primary",
                    use_container_width=True
                )

            if save_delivery:
                try:
                    if new_state == "Novedad" and not incident_note.strip() and incident_type == "Otro":
                        st.error("Describe la novedad para que administración pueda gestionarla.")
                        st.stop()

                    timestamp = now_iso()
                    changes = {
                        "estado": new_state,
                        "estado_actualizado_en": timestamp,
                        "actualizado_por_mensajero_id": courier["id"],
                        "actualizado_por_mensajero_nombre": courier["nombre"]
                    }

                    if new_state == "Novedad":
                        changes.update({
                            "novedad_tipo": incident_type,
                            "novedad_detalle": incident_note.strip(),
                            "novedad_estado_gestion": "Pendiente de revisión",
                            "novedad_reportada_en": timestamp,
                            "requiere_gestion_humana": True
                        })
                    else:
                        changes.update({
                            "entregado_en": timestamp,
                            "novedad_tipo": None,
                            "novedad_detalle": None,
                            "requiere_gestion_humana": False,
                            "cobro_registrado": bool(cash_collected),
                            "valor_recaudado": int(cash_amount) if cash_collected else 0,
                            "cobro_registrado_en": timestamp if cash_collected else None,
                            "cobro_registrado_por": courier["id"] if cash_collected else None
                        })

                    if proof_photo is not None:
                        st.warning("La foto se seleccionó, pero la subida persistente de evidencia requiere configurar Cloud Storage. No se guardará el archivo en Firestore.")

                    update_order_and_route(db, number, changes)
                    st.success(f"Pedido {number}: {new_state.lower()} registrado.")
                    st.rerun()
                except Exception as exc:
                    st.error("No se pudo guardar el resultado de la entrega.")
                    st.caption(str(exc))
    else:
        st.success("No tienes más entregas activas en esta ruta.")
        st.caption("Las entregas completadas, las novedades y los pedidos cancelados no se muestran como siguiente entrega.")

    # El resumen aparece cuando ya no quedan entregas activas.
    route_cash = sum(int(o.get("valor_recaudado", 0) or 0) for o in orders)
    if status == "En camino" and not active_orders:
        st.success("Ya no quedan pedidos activos en esta ruta.")
        st.markdown("### 🧾 Resumen de ruta")
        a, b, c, d = st.columns(4)
        a.metric("Entregados", delivered)
        b.metric("Novedades", incidents)
        c.metric("Cancelados", cancelled)
        d.metric("Dinero registrado", fmt_cop(route_cash))

        if st.button("🏁 Finalizar ruta", key=f"finish_{route_id}", use_container_width=True):
            try:
                db.collection("rutas").document(route_id).update({
                    "estado": "Finalizada",
                    "finalizada_en": now_iso(),
                    "finalizada_por": courier["id"],
                    "resumen_entregados": delivered,
                    "resumen_novedades": incidents,
                    "resumen_cancelados": cancelled,
                    "resumen_valor_recaudado": route_cash
                })
                st.success("Ruta finalizada.")
                st.rerun()
            except Exception as exc:
                st.error("No se pudo finalizar la ruta.")
                st.caption(str(exc))

st.divider()
st.caption("ENCANTO Mensajero · La ubicación GPS solo se registra mientras la app está abierta y con permiso del dispositivo.")
