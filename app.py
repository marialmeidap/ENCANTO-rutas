# ============================================================
# ENCANTO RUTAS - REGISTRO DE PEDIDOS Y ETIQUETAS
# Etiqueta térmica: 100 x 150 mm (10 x 15 cm)
# ============================================================

import html
import uuid
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components


# ------------------------------------------------------------
# 1. CONFIGURACIÓN
# ------------------------------------------------------------

st.set_page_config(
    page_title="ENCANTO Rutas",
    page_icon="📦",
    layout="wide",
)

if "pedidos" not in st.session_state:
    st.session_state["pedidos"] = []

if "pedido_etiqueta" not in st.session_state:
    st.session_state["pedido_etiqueta"] = None


# ------------------------------------------------------------
# 2. FUNCIONES AUXILIARES
# ------------------------------------------------------------

def texto_seguro(valor):
    """Escapa texto antes de insertarlo en el HTML de impresión."""
    return html.escape(str(valor or ""))


def formato_pesos(valor):
    return f"${int(valor):,}".replace(",", ".")


def crear_html_etiqueta(pedido):
    """Construye un documento independiente para imprimir a 10 x 15 cm."""
    numero = texto_seguro(pedido["numero"])
    fecha = texto_seguro(pedido["fecha"])
    nombre = texto_seguro(pedido["nombre"])
    telefono = texto_seguro(pedido["telefono"])
    direccion = texto_seguro(pedido["direccion"])
    barrio = texto_seguro(pedido["barrio"])
    ciudad = texto_seguro(pedido["ciudad"])
    referencia = texto_seguro(pedido["referencia"])
    producto = texto_seguro(pedido["producto"] or "No especificado")
    observaciones = texto_seguro(
        pedido["observaciones"] or "Sin observaciones"
    )
    valor = texto_seguro(formato_pesos(pedido["valor_cobrar"]) + " COP")

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Etiqueta ENCANTO {numero}</title>
<style>
    @page {{
        size: 100mm 150mm;
        margin: 0;
    }}

    * {{
        box-sizing: border-box;
    }}

    html, body {{
        margin: 0;
        padding: 0;
        width: 100mm;
        min-width: 100mm;
        background: #fff;
        color: #111;
        font-family: Arial, Helvetica, sans-serif;
    }}

    .toolbar {{
        width: 100%;
        padding: 10px;
        background: #f2f2f2;
        font-family: Arial, sans-serif;
    }}

    .toolbar button {{
        padding: 10px 16px;
        font-size: 14px;
        cursor: pointer;
