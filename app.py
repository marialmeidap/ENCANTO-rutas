
# ============================================================
# ENCANTO RUTAS
# Archivo principal de nuestra aplicación
# ============================================================

# Importamos Streamlit, la herramienta que nos permite
# crear una aplicación web usando Python.
import streamlit as st

# Configuramos el título y la apariencia de la página.
st.set_page_config(
    page_title="ENCANTO Rutas",
    page_icon="📦",
    layout="wide"
)

# Título principal que aparecerá en nuestra aplicación.
st.title("📦 ENCANTO Rutas")

# Mensaje de bienvenida.
st.write(
    "Sistema de gestión de entregas y rutas "
    "para los mensajeros de Encanto Capilar."
)

# Línea separadora para organizar visualmente la página.
st.divider()

# Creamos tres indicadores iniciales.
# Por ahora muestran cero porque todavía no registramos pedidos.
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Pedidos del día", 0)

with col2:
    st.metric("Entregas completadas", 0)

with col3:
    st.metric("Entregas pendientes", 0)

# Aviso de que estamos construyendo el sistema por etapas.
st.info(
    "¡Bienvenida! Estamos preparando el sistema. "
    "Pronto podrás registrar pedidos, validar direcciones "
    "y organizar las rutas de entrega."
)

# Este es nuestro primer prototipo.
# Todavía no guarda pedidos ni rastrea el GPS.
