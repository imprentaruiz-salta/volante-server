"""
Armá tu volante — Imprenta Ruiz
Servidor web para generar volantes publicitarios con IA (Together AI / FLUX)
y enviarlos por WhatsApp a Imprenta Ruiz.

Autor: Generador automático para Carlitos Ruiz
"""

import os
import io
import json
import uuid
import sqlite3
import base64
import requests
from datetime import datetime
from PIL import Image
from flask import Flask, request, jsonify, render_template, send_file, redirect

app = Flask(__name__, static_folder="static", static_url_path="/static")

# Comandas del menú QR. Se guarda en SQLite para que el panel y los celulares
# compartan los pedidos mientras el servidor está activo.
PEDIDOS_DB = os.environ.get("PEDIDOS_DB", os.path.join(os.path.dirname(__file__), "pedidos.sqlite3"))

def init_pedidos_db():
    with sqlite3.connect(PEDIDOS_DB) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mesa TEXT NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'nuevo',
            items TEXT NOT NULL,
            total INTEGER NOT NULL DEFAULT 0,
            observaciones TEXT DEFAULT '',
            estado TEXT NOT NULL DEFAULT 'nuevo',
            creado TEXT NOT NULL
        )""")
        db.commit()

def pedido_dict(row):
    d = dict(row)
    d['items'] = json.loads(d['items'] or '[]')
    return d

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
TOGETHER_API_KEY = os.environ.get("TOGETHER_API_KEY", "")
TOGETHER_IMAGE_URL = "https://api.together.ai/v1/images/generations"

# Modelo FLUX para generación de imágenes
# FLUX.1-schnell = más rápido y económico (4 steps por defecto)
# FLUX.2-flex = mejor tipografía (ideal para volantes con texto)
FLUX_MODEL = os.environ.get("FLUX_MODEL", "black-forest-labs/FLUX.1-schnell")

# Dimensiones aproximadas A5 vertical (proporción ~1:1.414)
# A5 = 148×210 mm → ratio 1:1.414
# Usamos 768×1080 que respeta la proporción A5 y es soportado por FLUX
IMG_WIDTH = 768
IMG_HEIGHT = 1080

# WhatsApp de Imprenta Ruiz
REMOVEBG_API_KEY = os.environ.get("REMOVEBG_API_KEY", "owE5ciXjym7BYhR1MvyXQCYT")
IMPRENTA_WHATSAPP = "5493872101274"

# Mapa de tipos de volante → clave de prompt en inglés
TIPO_MAP = {
    "comida":    "food delivery / restaurant flyer",
    "ropa":      "clothing / fashion store flyer",
    "servicios": "services / handyman / professional business flyer",
    "evento":    "event / party / celebration flyer",
    "comercio":  "general retail / shop flyer",
    "otro":      "general promotional flyer",
}

TIPO_ICONO = {
    "comida":    "🍕",
    "ropa":      "👗",
    "servicios": "💈",
    "evento":    "🎉",
    "comercio":  "🏪",
    "otro":      "✏️",
}

COLOR_MAP = {
    "color":     "vibrant full-color design",
    "byn":       "black and white monochrome design",
    "combinado": "two-tone design with bold accent colors",
}


# ---------------------------------------------------------------------------
# Rutas principales
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """Página principal con el generador de volantes paso a paso."""
    return render_template("index.html", imprenta_wpp=IMPRENTA_WHATSAPP)


@app.route("/imprenta-ruiz")
def imprenta_ruiz():
    """Página pública de Imprenta Ruiz, con preview al compartir el enlace."""
    html = render_template("ruiz.html")
    animated_mascot = '<img class="mascota-float mascota-nueva" style="width:125px;max-height:180px" src="https://share.zapia.com/o8oveyfvpjw58y727ed0ff" alt="Mascota de Imprenta Ruiz">'
    mascot_start = html.find('<img class="mascota-float"')
    if mascot_start >= 0:
        mascot_end = html.find('>', mascot_start)
        if mascot_end >= 0:
            html = html[:mascot_start] + animated_mascot + html[mascot_end + 1:]
    social_preview = """
<meta property="og:type" content="website">
<meta property="og:title" content="Imprenta Ruiz">
<meta property="og:description" content="Precios y trabajos web de Imprenta Ruiz.">
<meta property="og:image" content="https://share.zapia.com/w3qk7m0or5i5s9i2cjysws">
<meta property="og:url" content="https://volante-server.onrender.com/imprenta-ruiz">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="https://share.zapia.com/w3qk7m0or5i5s9i2cjysws">
"""
    return html.replace("</head>", social_preview + "</head>", 1)


@app.route("/health")
def health():
    """Healthcheck para Render."""
    has_key = bool(TOGETHER_API_KEY)
    return jsonify({
        "status": "ok",
        "together_key_configured": has_key,
        "model": FLUX_MODEL,
        "image_size": f"{IMG_WIDTH}x{IMG_HEIGHT}",
    })


# ---------------------------------------------------------------------------
# Construcción del prompt
# ---------------------------------------------------------------------------
def construir_prompt(datos: dict) -> str:
    """
    Construye un prompt detallado en inglés para FLUX a partir de los datos
    del formulario del volante.
    """
    partes = []

    tipo_key = datos.get("tipo", "comercio")
    tipo_en = TIPO_MAP.get(tipo_key, TIPO_MAP["comercio"])
    tipo_es = datos.get("tipo_label", tipo_key)

    # Estilo general del volante
    color_pref = datos.get("color", "color")
    color_en = COLOR_MAP.get(color_pref, COLOR_MAP["color"])

    partes.append(
        f"Professional promotional flyer design, {tipo_en}. "
        f"{color_en}. "
        f"Vertical poster layout, A5 portrait format. "
        f"High-quality graphic design, clean modern aesthetic, "
        f"professional typography, eye-catching visual composition."
    )

    # Nombre del negocio
    nombre = datos.get("nombre", "").strip()
    if nombre:
        partes.append(
            f'The flyer prominently features the business name "{nombre}" '
            f'as the main headline at the top, in large bold elegant typography.'
        )

    # Slogan
    slogan = datos.get("slogan", "").strip()
    if slogan:
        partes.append(
            f'Include the tagline "{slogan}" below the business name '
            f'in a smaller elegant font.'
        )

    # Productos / precios
    productos = datos.get("productos", "").strip()
    if productos:
        partes.append(
            f'Display the following text content as a menu or product list '
            f'on the flyer: "{productos}". '
            f'Format as a clean readable list with prices aligned.'
        )

    # Contacto — WhatsApp
    whatsapp = datos.get("whatsapp", "").strip()
    if whatsapp:
        partes.append(
            f'Include a green WhatsApp contact icon with the number "{whatsapp}" '
            f'in the contact section at the bottom.'
        )

    # Contacto — Telegram
    telegram = datos.get("telegram", "").strip()
    if telegram:
        partes.append(
            f'Include a blue Telegram contact icon with the handle "{telegram}" '
            f'in the contact section.'
        )

    # Dirección
    direccion = datos.get("direccion", "").strip()
    if direccion:
        partes.append(
            f'Include the address "{direccion}" with a small location pin icon '
            f'in the footer area.'
        )

    # Instagram
    instagram = datos.get("instagram", "").strip()
    if instagram:
        handle = instagram if instagram.startswith("@") else f"@{instagram}"
        partes.append(
            f'Include an Instagram social media icon with the handle "{handle}" '
            f'in the social media section.'
        )

    # Facebook
    facebook = datos.get("facebook", "").strip()
    if facebook:
        partes.append(
            f'Include a Facebook social media icon with the page "{facebook}" '
            f'in the social media section.'
        )

    # TikTok
    tiktok = datos.get("tiktok", "").strip()
    if tiktok:
        handle = tiktok if tiktok.startswith("@") else f"@{tiktok}"
        partes.append(
            f'Include a TikTok social media icon with the handle "{handle}" '
            f'in the social media section.'
        )

    # Indicaciones de composición final
    partes.append(
        "The flyer should have a clear visual hierarchy: "
        "business name at top as headline, "
        "tagline below, "
        "product list or menu in the center body, "
        "contact information with icons in the lower section, "
        "social media icons in the footer. "
        "Make sure all text is clearly legible and well-spaced. "
        "The design should look professional and ready to print."
    )

    # Preferencia de color específica
    if color_pref == "byn":
        partes.append("Strictly black, white and grey tones only. No colors.")
    elif color_pref == "combinado":
        partes.append(
            "Use a tasteful combination of a bold primary color "
            "with neutral tones for a striking two-tone effect."
        )
    elif color_pref == "color":
        partes.append(
            "Use vibrant, eye-catching colors appropriate for the business type."
        )

    # Acento de marca si es comercio general o servicios
    if tipo_key in ("comercio", "servicios", "otro"):
        partes.append(
            "Consider using dark navy blue and warm orange/gold as accent colors "
            "for a professional trustworthy look."
        )

    return " ".join(partes)


# ---------------------------------------------------------------------------
# Generación de imagen con Together AI
# ---------------------------------------------------------------------------
@app.route("/generate", methods=["POST"])
def generate():
    """
    Recibe los datos del formulario en JSON, construye un prompt detallado,
    llama a Together AI (FLUX) y devuelve la imagen generada en base64.
    """
    datos = request.get_json(force=True, silent=True)
    if not datos:
        return jsonify({"error": "Datos inválidos"}), 400

    # Validar campos mínimos
    nombre = (datos.get("nombre") or "").strip()
    whatsapp = (datos.get("whatsapp") or "").strip()
    if not nombre:
        return jsonify({"error": "El nombre del negocio es obligatorio"}), 400
    if not whatsapp:
        return jsonify({"error": "El WhatsApp es obligatorio"}), 400

    prompt = construir_prompt(datos)

    # ---------------------------------------------------------------------------
    # Generación de imagen via Pollinations.AI (gratuito, sin API key)
    # GET https://image.pollinations.ai/prompt/{prompt}?width=W&height=H&model=flux&nologo=true
    # ---------------------------------------------------------------------------
    import urllib.parse
    prompt_encoded = urllib.parse.quote(prompt)
    pollinations_url = (
        f"https://image.pollinations.ai/prompt/{prompt_encoded}"
        f"?width={IMG_WIDTH}&height={IMG_HEIGHT}&model=flux&nologo=true&seed={hash(prompt) % 99999}"
    )

    try:
        resp = requests.get(pollinations_url, timeout=90, stream=True)
    except requests.exceptions.Timeout:
        return jsonify({"error": "La generación de la imagen tardó demasiado. Intentá de nuevo."}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Error de conexión con el servicio de IA: {str(e)}"}), 502

    if resp.status_code != 200:
        return jsonify({"error": f"Error del servicio de IA (HTTP {resp.status_code}). Intentá de nuevo."}), 502

    image_b64 = base64.b64encode(resp.content).decode("utf-8")

    return jsonify({
        "image": image_b64,
        "prompt": prompt,
    })


# ---------------------------------------------------------------------------
# Información del volante para WhatsApp
# ---------------------------------------------------------------------------
@app.route("/resumen", methods=["POST"])
def resumen():
    """
    Construye el mensaje de WhatsApp con todos los datos del formulario
    para enviar a Imprenta Ruiz.
    """
    datos = request.get_json(force=True, silent=True) or {}

    tipo_key = datos.get("tipo", "comercio")
    tipo_label = datos.get("tipo_label") or TIPO_MAP.get(tipo_key, tipo_key)
    icono = TIPO_ICONO.get(tipo_key, "✏️")

    lineas = [f"🖨️ *NUEVO VOLANTE PARA IMPRIMIR* 🖨️", ""]
    lineas.append(f"{icono} *Tipo:* {tipo_label}")
    lineas.append("")

    nombre = (datos.get("nombre") or "").strip()
    if nombre:
        lineas.append(f"🏪 *Negocio:* {nombre}")

    slogan = (datos.get("slogan") or "").strip()
    if slogan:
        lineas.append(f"💬 *Slogan:* {slogan}")

    productos = (datos.get("productos") or "").strip()
    if productos:
        lineas.append(f"📝 *Productos/Precios:*")
        lineas.append(productos)

    lineas.append("")

    whatsapp = (datos.get("whatsapp") or "").strip()
    if whatsapp:
        lineas.append(f"📱 *WhatsApp:* {whatsapp}")

    telegram = (datos.get("telegram") or "").strip()
    if telegram:
        lineas.append(f"✈️ *Telegram:* {telegram}")

    direccion = (datos.get("direccion") or "").strip()
    if direccion:
        lineas.append(f"📍 *Dirección:* {direccion}")

    # Redes sociales
    redes = []
    instagram = (datos.get("instagram") or "").strip()
    if instagram:
        handle = instagram if instagram.startswith("@") else f"@{instagram}"
        redes.append(f"Instagram: {handle}")
    facebook = (datos.get("facebook") or "").strip()
    if facebook:
        redes.append(f"Facebook: {facebook}")
    tiktok = (datos.get("tiktok") or "").strip()
    if tiktok:
        handle = tiktok if tiktok.startswith("@") else f"@{tiktok}"
        redes.append(f"TikTok: {handle}")
    if redes:
        lineas.append(f"🔗 *Redes:* {' · '.join(redes)}")

    color = (datos.get("color") or "").strip()
    if color:
        color_label = {
            "color": "A color",
            "byn": "Blanco y negro",
            "combinado": "Combinado",
        }.get(color, color)
        lineas.append(f"🎨 *Estilo:* {color_label}")

    lineas.append("")
    lineas.append("✅ *Ya aprobé el diseño, quiero imprimirlo*")

    mensaje = "\n".join(lineas)
    return jsonify({"mensaje": mensaje})


# ---------------------------------------------------------------------------
# Foto carnet 4x4
# ---------------------------------------------------------------------------
@app.route("/menu")
def menu_page():
    """Página del generador de menú digital profesional."""
    return render_template("menu.html", imprenta_wpp=IMPRENTA_WHATSAPP)


@app.route("/panel")
def panel_page():
    """Panel del encargado para ver y avanzar comandas por estado."""
    return render_template("panel.html")

@app.route("/qr-mesas")
@app.route("/qr")
def qr_mesas_page():
    """Hoja imprimible con un QR diferente para cada mesa."""
    base_url = request.url_root.rstrip("/")
    return render_template("qr_mesas.html", base_url=base_url)

@app.route("/api/pedidos", methods=["GET", "POST"])
def pedidos_api():
    if request.method == "GET":
        estado = request.args.get("estado")
        with sqlite3.connect(PEDIDOS_DB) as db:
            db.row_factory = sqlite3.Row
            if estado:
                rows = db.execute("SELECT * FROM pedidos WHERE estado=? ORDER BY id DESC", (estado,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM pedidos ORDER BY id DESC LIMIT 100").fetchall()
        return jsonify([pedido_dict(r) for r in rows])

    data = request.get_json(silent=True) or {}
    mesa = str(data.get("mesa", "")).strip()
    items = data.get("items") or []
    if not mesa or not items:
        return jsonify(ok=False, error="Falta mesa o productos"), 400
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(PEDIDOS_DB) as db:
        cur = db.execute("""INSERT INTO pedidos
            (mesa,tipo,items,total,observaciones,estado,creado)
            VALUES (?,?,?,?,?,?,?)""", (
                mesa, str(data.get("tipo", "nuevo")), json.dumps(items, ensure_ascii=False),
                int(data.get("total", 0) or 0), str(data.get("observaciones", "")),
                "nuevo", ahora))
        db.commit()
        pedido_id = cur.lastrowid
    return jsonify(ok=True, id=pedido_id, estado="nuevo", creado=ahora)

@app.route("/api/pedidos/<int:pedido_id>", methods=["PATCH"])
def actualizar_pedido(pedido_id):
    data = request.get_json(silent=True) or {}
    estado = str(data.get("estado", "")).strip()
    permitidos = {"nuevo", "preparando", "listo", "entregado", "cancelado"}
    if estado not in permitidos:
        return jsonify(ok=False, error="Estado no válido"), 400
    with sqlite3.connect(PEDIDOS_DB) as db:
        db.execute("UPDATE pedidos SET estado=? WHERE id=?", (estado, pedido_id))
        db.commit()
    return jsonify(ok=True, id=pedido_id, estado=estado)

@app.route("/cumple")
def cumple_page():
    """Página del generador de invitación digital de cumpleaños."""
    return render_template("cumple.html")


# Prompts FLUX por temática
CUMPLE_PROMPTS = {
    "Spiderman":   "Spiderman hero illustration, dynamic pose swinging between buildings, comic book style, vibrant red and blue, dramatic lighting, no text, cinematic",
    "Frozen":      "Elsa from Frozen, magical ice powers, snowflakes swirling, blue and white palette, Disney style illustration, glowing magical atmosphere, no text",
    "Dinosaurios": "cute cartoon T-Rex dinosaur birthday party, colorful balloons, jungle background, fun and playful style, vibrant greens and yellows, no text",
    "Unicornio":   "magical unicorn with rainbow mane, sparkles and stars, pastel pink and purple, whimsical fantasy illustration, glowing magical atmosphere, no text",
    "Fútbol":      "soccer ball illustration, stadium lights, green field, dynamic action, sports poster style, vibrant colors, no text",
    "Princesas":   "beautiful princess with tiara, castle background, pink and gold palette, fairy tale Disney style, sparkles and flowers, no text",
    "Cars":        "Lightning McQueen cartoon race car, race track, motion blur, vibrant red and yellow, Pixar style illustration, dynamic speed lines, no text",
    "Gatitos":     "cute kawaii kittens with birthday hats, pastel colors, confetti, adorable cartoon style, pink and cream palette, no text",
    "General":     "colorful birthday party celebration illustration, balloons confetti streamers, festive background, vibrant colors, joyful atmosphere, no text",
}

# Música por temática (URLs de audio libre de derechos)
CUMPLE_MUSICA = {
    "Spiderman":   "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
    "Frozen":      "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
    "Dinosaurios": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-7.mp3",
    "Unicornio":   "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
    "Fútbol":      "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3",
    "Princesas":   "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
    "Cars":        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-5.mp3",
    "Gatitos":     "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
    "General":     "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-6.mp3",
}


@app.route("/cumple/guardar", methods=["POST"])
def cumple_guardar():
    """Guarda los datos de la invitación y devuelve un link único."""
    datos = request.get_json(force=True, silent=True) or {}

    # Generar ID único corto (8 chars)
    inv_id = uuid.uuid4().hex[:8]

    # Directorio de invitaciones
    inv_dir = os.path.join(os.path.dirname(__file__), "invitaciones")
    os.makedirs(inv_dir, exist_ok=True)

    # Guardar datos
    ruta = os.path.join(inv_dir, f"{inv_id}.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)

    return jsonify({"id": inv_id, "url": f"/i/{inv_id}"})


@app.route("/i/<inv_id>/imagen")
def inv_imagen(inv_id):
    """Genera la imagen IA para la invitación (llamada async desde el browser)."""
    inv_dir = os.path.join(os.path.dirname(__file__), "invitaciones")
    ruta    = os.path.join(inv_dir, f"{inv_id}.json")
    if not os.path.exists(ruta):
        return jsonify({"error": "no encontrado"}), 404

    with open(ruta, encoding="utf-8") as f:
        d = json.load(f)

    # Si ya está cacheada, devolver directo
    img_ruta = os.path.join(inv_dir, f"{inv_id}_img.jpg")
    if os.path.exists(img_ruta):
        with open(img_ruta, "rb") as f:
            return jsonify({"image": base64.b64encode(f.read()).decode()})

    tematica = d.get("tematica", "General")
    prompt   = CUMPLE_PROMPTS.get(tematica, CUMPLE_PROMPTS["General"])
    prompt  += ", celebration birthday party background, high quality digital art"

    try:
        # Pollinations AI — gratis, sin API key
        import urllib.parse
        prompt_enc = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{prompt_enc}?width=768&height=512&nologo=true&seed=42"
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        img_bytes = resp.content
        b64 = base64.b64encode(img_bytes).decode()
        # Cachear en disco
        with open(img_ruta, "wb") as f:
            f.write(img_bytes)
        return jsonify({"image": b64})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/i/<inv_id>")
def ver_invitacion(inv_id):
    """Muestra la invitación ya generada a partir de su ID único."""
    inv_dir = os.path.join(os.path.dirname(__file__), "invitaciones")
    ruta = os.path.join(inv_dir, f"{inv_id}.json")

    if not os.path.exists(ruta):
        return "Invitación no encontrada", 404

    with open(ruta, encoding="utf-8") as f:
        d = json.load(f)

    # Formatear fecha
    meses = ['enero','febrero','marzo','abril','mayo','junio',
             'julio','agosto','septiembre','octubre','noviembre','diciembre']
    fecha_iso = d.get("fecha", "")
    hora_raw  = d.get("hora", "00:00")
    fecha_formato = ""
    if fecha_iso:
        y, m, day = fecha_iso.split("-")
        fecha_formato = f"{int(day)} de {meses[int(m)-1]} de {y}"

    # Formatear hora
    h, mi = hora_raw.split(":")
    h_int = int(h)
    ampm = "pm" if h_int >= 12 else "am"
    h12 = h_int - 12 if h_int > 12 else (12 if h_int == 0 else h_int)
    hora_formato = f"{h12}:{mi} {ampm}"

    direccion = d.get("direccion", "")
    maps_url = f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(direccion + ', Salta')}"

    tematica  = d.get("tematica", "General")
    musica_url = CUMPLE_MUSICA.get(tematica, CUMPLE_MUSICA["General"])

    # Ver si imagen IA ya está cacheada
    inv_dir  = os.path.join(os.path.dirname(__file__), "invitaciones")
    img_ruta = os.path.join(inv_dir, f"{inv_id}_img.jpg")
    imagen_ia = None
    if os.path.exists(img_ruta):
        with open(img_ruta, "rb") as f:
            imagen_ia = base64.b64encode(f.read()).decode()

    return render_template(
        "invitacion.html",
        inv_id       = inv_id,
        nombre       = d.get("nombre", ""),
        anos         = d.get("anos", ""),
        mensaje      = d.get("mensaje", ""),
        fecha_iso    = fecha_iso,
        hora_raw     = hora_raw,
        fecha_formato= fecha_formato,
        hora_formato = hora_formato,
        direccion    = direccion,
        salon        = d.get("salon", ""),
        telefono     = d.get("telefono", ""),
        emoji        = d.get("emoji", "🎉"),
        color1       = d.get("color1", "#7b1fa2"),
        color2       = d.get("color2", "#4a148c"),
        maps_url     = maps_url,
        foto         = d.get("foto", None),
        tematica     = tematica,
        musica_url   = musica_url,
        imagen_ia    = imagen_ia,
    )


@app.route("/carnet")
def carnet_page():
    """Página de foto carnet 4x4."""
    return render_template("carnet.html", imprenta_wpp=IMPRENTA_WHATSAPP)


@app.route("/carnet/procesar", methods=["POST"])
def carnet_procesar():
    """
    Recibe la foto, elimina el fondo con Remove.bg,
    pone fondo celeste carnet y devuelve la imagen en base64.
    """
    if "foto" not in request.files:
        return jsonify({"error": "No se recibió ninguna foto"}), 400

    foto = request.files["foto"]
    foto_bytes = foto.read()

    if not foto_bytes:
        return jsonify({"error": "La foto está vacía"}), 400

    # Llamar a Remove.bg
    try:
        resp = requests.post(
            "https://api.remove.bg/v1.0/removebg",
            files={"image_file": ("foto.jpg", foto_bytes, "image/jpeg")},
            data={"size": "auto"},
            headers={"X-Api-Key": REMOVEBG_API_KEY},
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Error al conectar con el servicio: {str(e)}"}), 502

    if resp.status_code != 200:
        return jsonify({"error": "No pudimos procesar la foto. Intentá con una foto más clara y bien iluminada."}), 502

    # Componer sobre fondo celeste carnet
    fg = Image.open(io.BytesIO(resp.content)).convert("RGBA")
    bg = Image.new("RGBA", fg.size, (164, 210, 230, 255))
    combined = Image.alpha_composite(bg, fg).convert("RGB")

    # Redimensionar a 472x472 px (4x4 cm a 300 DPI)
    final = combined.resize((472, 472), Image.LANCZOS)

    # Convertir a base64
    buf = io.BytesIO()
    final.save(buf, format="JPEG", quality=95, dpi=(300, 300))
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode("utf-8")

    return jsonify({"image": img_b64})


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------
init_pedidos_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
