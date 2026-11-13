
import streamlit as st
import streamlit.components.v1 as components
import uuid
from datetime import datetime
import html

st.set_page_config(page_title="ENCANTO Rutas", page_icon="📦", layout="wide")

if "pedidos" not in st.session_state:
    st.session_state.pedidos = []

st.title("📦 ENCANTO Rutas")
st.caption("Gestión de entregas · Encanto Capilar")

pedidos = st.session_state.pedidos
total = len(pedidos)
entregados = sum(p["estado"] == "Entregado" for p in pedidos)

a, b, c = st.columns(3)
a.metric("Pedidos", total)
b.metric("Entregados", entregados)
c.metric("Pendientes", total - entregados)

st.divider()
st.header("📝 Registrar pedido")

with st.form("pedido", clear_on_submit=True):
    nombre = st.text_input("Nombre del cliente *")
    telefono = st.text_input("WhatsApp *")
    direccion = st.text_input("Dirección completa *")
    barrio = st.text_input("Barrio")
    ciudad = st.text_input("Ciudad", value="Cali")
    referencia = st.text_input("Punto de referencia")
    producto = st.text_input("Producto")
    valor = st.number_input("Valor a cobrar (COP)", min_value=0, step=1000)
    observaciones = st.text_area("Observaciones")
    guardar = st.form_submit_button("Guardar pedido", type="primary")

    if guardar:
        if not nombre.strip() or not telefono.strip() or not direccion.strip():
            st.error("Completa el nombre, WhatsApp y dirección.")
        else:
            st.session_state.pedidos.append({
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
            })
            st.success("Pedido guardado.")
            st.rerun()

st.divider()
st.header("📋 Pedidos registrados")

for i, p in enumerate(st.session_state.pedidos):
    with st.expander(f"{p['numero']} · {p['nombre']} · {p['estado']}"):
        st.write("**WhatsApp:**", p["telefono"])
        st.write("**Dirección:**", p["direccion"], p["barrio"], p["ciudad"])
        st.write("**Producto:**", p["producto"])
        st.write("**Valor a cobrar:**", f"${p['valor']:,} COP")
        st.write("**Referencia:**", p["referencia"])
        st.write("**Observaciones:**", p["observaciones"])
        estado = st.selectbox("Estado", ["Pendiente", "En camino", "Entregado", "Novedad"], index=["Pendiente", "En camino", "Entregado", "Novedad"].index(p["estado"]), key=p["numero"])
        if estado != p["estado"]:
            st.session_state.pedidos[i]["estado"] = estado
            st.rerun()
        if st.button("Preparar etiqueta 10 × 15 cm", key="etiqueta_" + p["numero"]):
            st.session_state.etiqueta = p["numero"]

if st.session_state.get("etiqueta"):
    p = next((x for x in st.session_state.pedidos if x["numero"] == st.session_state.etiqueta), None)
    if p:
        esc = lambda v: html.escape(str(v or ""))
        etiqueta = f"""
        <div class="label">
        <header><h1>ENCANTO</h1><b>CAPILAR · ENVÍOS</b></header>
        <p><b>PEDIDO:</b> {esc(p['numero'])}<br><b>FECHA:</b> {esc(p['fecha'])}</p>
        <hr><h2>DESTINATARIO</h2><h2>{esc(p['nombre'])}</h2>
        <p><b>WHATSAPP:</b> {esc(p['telefono'])}</p>
        <p><b>DIRECCIÓN:</b><br>{esc(p['direccion'])}<br>{esc(p['barrio'])}, {esc(p['ciudad'])}</p>
        <p><b>REFERENCIA:</b> {esc(p['referencia'])}</p>
        <hr><p><b>PRODUCTO:</b> {esc(p['producto'])}</p>
        <p><b>OBSERVACIONES:</b> {esc(p['observaciones'])}</p>
        <div class="cash"><small>VALOR A COBRAR</small><h1>${p['valor']:,} COP</h1></div>
        </div>
        """
        documento = f"""<!doctype html><html><head><meta charset="utf-8"><style>
        @page{{size:100mm 150mm;margin:0}}
        *{{box-sizing:border-box}}body{{margin:0;font-family:Arial;color:#000}}
        .label{{width:100mm;height:150mm;padding:6mm;overflow:hidden;border:1px solid #000}}
        header{{text-align:center;border-bottom:2px solid;padding-bottom:3mm}}
        header h1{{font-size:24pt;margin:0 0 2mm}}h2{{font-size:16pt;margin:3mm 0}}
        p{{font-size:11pt;overflow-wrap:anywhere;line-height:1.3}}
        .cash{{border:2px solid;text-align:center;padding:3mm;margin-top:5mm}}
        .cash h1{{font-size:21pt;margin:2mm 0}}
        @media print{{.toolbar{{display:none}}}}
        </style></head><body><div class="toolbar"><button onclick="window.print()">Imprimir etiqueta</button></div>{etiqueta}</body></html>"""
        st.subheader("🏷️ Vista previa de etiqueta")
        components.html(documento, height=650, scrolling=True)
        st.info("Al imprimir, selecciona papel de 100 × 150 mm, escala 100 % y márgenes ninguno.")

st.caption("Prototipo en desarrollo · Los pedidos se guardan temporalmente en esta sesión.")
