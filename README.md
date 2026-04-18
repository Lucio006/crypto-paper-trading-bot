# Event Prospector

Herramienta local y privada para extraer empresas expositoras de eventos, encontrar sus mejores contactos y escribir todo en Google Sheets con memoria histórica.

---

## Requisitos

- Python 3.11 o superior
- Cuenta de Google con acceso a Google Cloud Console
- API key de Anthropic (Claude)

---

## 1. Clonar e instalar

```bash
git clone <repo-url>
cd event-prospector

python -m venv venv
source venv/bin/activate      # macOS/Linux
# venv\Scripts\activate       # Windows

pip install -r requirements.txt
playwright install chromium
```

---

## 2. Configurar Google Sheets

### 2.1 Crear el proyecto en Google Cloud

1. Ve a https://console.cloud.google.com
2. Haz clic en **"Nuevo proyecto"** → ponle nombre (ej: `event-prospector`) → **Crear**
3. Asegúrate de que el proyecto nuevo está seleccionado en el menú superior

### 2.2 Activar las APIs necesarias

1. Menú izquierdo → **APIs y servicios** → **Biblioteca**
2. Busca **"Google Sheets API"** → **Habilitar**
3. Busca **"Google Drive API"** → **Habilitar**

### 2.3 Crear la Service Account

1. Menú izquierdo → **APIs y servicios** → **Credenciales**
2. **+ Crear credenciales** → **Cuenta de servicio**
3. Nombre: `event-prospector-bot` → **Crear y continuar** → **Listo**
4. Haz clic en la cuenta de servicio recién creada
5. Pestaña **Claves** → **Agregar clave** → **Crear clave nueva** → **JSON** → **Crear**
6. Se descargará un archivo JSON. Guárdalo en `credentials/service_account.json`

### 2.4 Crear el Google Sheets

1. Abre https://sheets.google.com → crea una hoja en blanco
2. Copia el **ID** de la URL:
   ```
   https://docs.google.com/spreadsheets/d/[ESTE_ES_EL_ID]/edit
   ```
3. En el Sheets, haz clic en **Compartir** (arriba a la derecha)
4. Pega el email de la service account (lo encontrarás en el JSON como `"client_email"`)
5. Dale permiso de **Editor** → **Enviar**

---

## 3. Configurar variables de entorno

```bash
cp .env.example .env
```

Edita `.env` y rellena:

```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_SHEETS_ID=tu_sheets_id_aquí
GOOGLE_SERVICE_ACCOUNT_PATH=./credentials/service_account.json
```

---

## 4. Ejecutar

```bash
streamlit run app.py
```

Abre automáticamente http://localhost:8501 en tu navegador.

---

## 5. Uso

1. Rellena los 3 campos: nombre del evento, fecha y URL del listado de expositores
2. (Opcional) Limita el número de empresas para pruebas
3. Pulsa **"Analizar evento"**
4. El progreso aparece en tiempo real
5. Al finalizar, sigue el enlace directo al Google Sheets

---

## Estructura del Google Sheets

La herramienta crea y mantiene estas pestañas automáticamente:

| Pestaña | Contenido |
|---------|-----------|
| `ÍNDICE EVENTOS` | Resumen de todos los eventos analizados |
| `BASE EMPRESAS` | Base maestra de todas las empresas vistas |
| `YYYY-MM-DD \| Nombre Evento` | Resultados detallados de cada evento |

### Colores de las filas (pestaña de evento)

| Color | Significado |
|-------|-------------|
| Verde | Empresa nueva |
| Amarillo | Empresa ya vista en otro evento |
| Naranja | Empresa ya contactada antes |
| Rojo | No contactar |
| Gris | Requiere revisión manual |

---

## Arquitectura

```
app.py              Interfaz Streamlit (localhost:8501)
pipeline.py         Orquesta el flujo completo
scraper/
  validator.py      Valida que la URL sea un listado de expositores
  level1_listing.py Nivel 1: extrae empresas del listado
  level2_profile.py Nivel 2: ficha individual del expositor
  level3_corporate  Nivel 3: web corporativa → contactos
  utils.py          Regex de emails, teléfonos, normalización
intelligence/
  classifier.py     Claude Haiku: mejor contacto y justificaciones
  deduplicator.py   Deduplicación por dominio/nombre
sheets/
  client.py         Conexión gspread
  writer.py         Escribe las 3 pestañas
  formatter.py      Colores, filtros, anchos
models/
  company.py        Pydantic: Company, ContactData, EventMeta
```

---

## Notas

- La herramienta usa **Claude Haiku** (el más económico) para clasificación de contactos. Con 200 empresas por evento el coste es de ~0,10–0,30 €.
- El scraping respeta tiempos de espera y usa un user-agent de Chrome real para evitar bloqueos básicos. Webs con Cloudflare agresivo pueden requerir ajuste manual.
- Si una web corporativa no carga o tiene solo formulario, la herramienta registra el motivo en la celda correspondiente (no deja campos vacíos sin explicación).
