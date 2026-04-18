# ── Tab names ─────────────────────────────────────────────────────────────────

TAB_INDEX = "ÍNDICE EVENTOS"
TAB_BASE = "BASE EMPRESAS"


def event_tab_name(event_date: str, event_name: str) -> str:
    """YYYY-MM-DD | Nombre Evento (max 40 chars total for Sheets tab limit)."""
    import re
    safe = re.sub(r"[^\w\s\-]", "", event_name).strip()[:25]
    return f"{event_date} | {safe}"


# ── Column definitions ────────────────────────────────────────────────────────

INDEX_COLUMNS = [
    "ID evento",
    "Fecha del evento",
    "Nombre del evento",
    "Nombre de la pestaña",
    "Enlace del listado de expositores",
    "Fecha de análisis",
    "Empresas detectadas",
    "Empresas nuevas",
    "Empresas ya registradas",
    "Estado del análisis",
    "Observaciones",
]

BASE_COLUMNS = [
    "ID empresa",
    "Nombre original",
    "Nombre normalizado",
    "Otros nombres detectados",
    "Dominio principal",
    "Web principal",
    "País",
    "Sector",
    "Primer evento detectado",
    "Fecha de primera detección",
    "Último evento detectado",
    "Fecha de última detección",
    "Veces detectada",
    "Veces contactada",
    "Última fecha de contacto",
    "Estado comercial",
    "Mejor contacto conocido",
    "Cargo del mejor contacto",
    "Email principal",
    "Teléfono principal",
    "Telegram",
    "Canal recomendado",
    "Última fuente encontrada",
    "Nivel de confianza",
    "Método de coincidencia",
    "Requiere revisión",
    "Motivo de revisión",
    "Notas internas",
]

EVENT_COLUMNS = [
    "ID fila",
    "ID evento",
    "Fecha del evento",
    "Nombre del evento",
    "Nombre de la empresa",
    "Nombre normalizado",
    "Número de stand",
    "Ficha del expositor",
    "Categoría del expositor",
    "Empresa ya registrada",
    "Ya se contactó antes",
    "Descripción del expositor",
    "Web encontrada en la ficha",
    "Enlace corporativo validado",
    "Web principal",
    "Dominio",
    "País",
    "Sector",
    "Teléfono general",
    "Email general",
    "Email de marketing",
    "Email de eventos",
    "Email del CEO",
    "Email del CCO",
    "Telegram",
    "Mejor contacto encontrado",
    "Cargo del mejor contacto",
    "Canal recomendado",
    "Prioridad del contacto",
    "Primer evento detectado",
    "Último evento detectado",
    "Última fecha de contacto",
    "Estado comercial",
    "Motivo si falta email de marketing",
    "Motivo si falta email de eventos",
    "Motivo si falta email del CEO",
    "Motivo si falta email del CCO",
    "Motivo si falta Telegram",
    "Motivo si falta web corporativa",
    "Página donde se encontró el mejor dato",
    "Texto de evidencia",
    "Nivel de confianza",
    "Método de coincidencia",
    "Requiere revisión",
    "Motivo de revisión",
    "Notas internas",
    "Contacto realizado",
    "Fecha de contacto",
    "Resultado del contacto",
    "Responsable",
]

# ── Allowed state values ──────────────────────────────────────────────────────

COMMERCIAL_STATES = [
    "Nueva",
    "No contactada",
    "Contactada",
    "Pendiente de volver a contactar",
    "En conversación",
    "Ganada",
    "Perdida",
    "No contactar",
]

CONTACT_RESULTS = [
    "Sin acción",
    "Contactado sin respuesta",
    "Respondió",
    "Reunión agendada",
    "Interesado",
    "No interesado",
    "Contacto incorrecto",
    "Requiere seguimiento",
]

REVIEW_VALUES = ["Sí", "No"]

CONFIDENCE_LEVELS = ["Alta", "Media", "Baja"]

MATCH_METHODS = ["domain_exact", "name_exact", "name_fuzzy", "needs_review"]

CHANNELS = ["Email", "Teléfono", "Telegram", "Formulario web"]

PRIORITIES = ["Alta", "Media", "Baja"]

# ── Row colors (RGB 0–1 for Google Sheets API) ────────────────────────────────
# Keyed by the condition name used in formatter.py

COLORS = {
    "nueva":       {"red": 0.91, "green": 0.96, "blue": 0.91},  # #E8F5E9 verde
    "conocida":    {"red": 1.00, "green": 0.99, "blue": 0.88},  # #FFFDE7 amarillo
    "contactada":  {"red": 1.00, "green": 0.95, "blue": 0.88},  # #FFF3E0 naranja
    "no_contactar":{"red": 1.00, "green": 0.92, "blue": 0.93},  # #FFEBEE rojo
    "revision":    {"red": 0.96, "green": 0.96, "blue": 0.96},  # #F5F5F5 gris
    "header":      {"red": 0.23, "green": 0.44, "blue": 0.72},  # azul oscuro
}


def row_color_key(commercial_status: str, is_known: bool, requires_review: bool) -> str:
    """Return the color key for a given company state."""
    if commercial_status == "No contactar":
        return "no_contactar"
    if requires_review:
        return "revision"
    if commercial_status in ("Contactada", "Pendiente de volver a contactar",
                              "En conversación", "Ganada", "Perdida"):
        return "contactada"
    if is_known:
        return "conocida"
    return "nueva"


# ── Quick schema summary (for debugging) ─────────────────────────────────────

if __name__ == "__main__":
    print(f"TAB_INDEX   : {TAB_INDEX}")
    print(f"TAB_BASE    : {TAB_BASE}")
    print(f"event_tab_name('2025-06-15', 'IFEMA Madrid 2025') → {event_tab_name('2025-06-15', 'IFEMA Madrid 2025')}")
    print(f"\nÍNDICE EVENTOS  : {len(INDEX_COLUMNS)} columnas")
    print(f"BASE EMPRESAS   : {len(BASE_COLUMNS)} columnas")
    print(f"Pestaña evento  : {len(EVENT_COLUMNS)} columnas")
    print(f"\nEstados comerciales ({len(COMMERCIAL_STATES)}): {COMMERCIAL_STATES}")
    print(f"Colores definidos: {list(COLORS.keys())}")
