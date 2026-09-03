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
from pathlib import Path
from PIL import Image
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, render_template, send_file, redirect, url_for

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
    # Carrusel de tres páginas: todas las tarjetas conservan el mismo tamaño.
    # La segunda página reúne las fotos y la tercera los servicios restantes.
    track_start = html.find('<div class="price-track">')
    track_end_marker = '</div></div><div class="dots"><i></i><i></i></div>'
    track_end = html.find(track_end_marker, track_start)
    if track_start >= 0 and track_end >= 0:
        track_end += len(track_end_marker)
        three_slide_carousel = '''<div class="price-track" data-three-slides="polaroid">
<div class="price-slide"><article class="price-card"><div class="price-icon blue">🖨️</div><div class="price-info"><h2>Impresión color</h2><strong>$1.250</strong><small>por faz</small></div></article><article class="price-card"><div class="price-icon pink">📄</div><div class="price-info"><h2>Blanco y negro</h2><strong>$1.250</strong><small>por faz</small></div></article><article class="price-card"><div class="price-icon yellow">🔩</div><div class="price-info"><h2>Anillado</h2><strong>$2.500</strong><small>todos</small></div></article><article class="price-card"><div class="price-icon purple">🏷️</div><div class="price-info"><h2>A4 autoadhesivo</h2><strong>$6.000</strong><small>por hoja</small></div></article></div>
<div class="price-slide"><button class="price-card mitsubishi-card" type="button" onclick="document.getElementById('precios-mitsubishi').classList.add('open')"><div class="price-icon purple">🖼️</div><div class="price-info"><h2>Fotos Mitsubishi</h2><strong>Ver precios</strong><small>tocá para ver precios</small></div></button><button class="price-card inkjet-card" type="button" onclick="document.getElementById('precios-inkjet').classList.add('open')"><div class="price-icon blue">🖨️</div><div class="price-info"><h2>Fotos Inkjet</h2><strong>Ver precios</strong><small>tocá para ver precios</small></div></button><button class="price-card kodak-card" type="button" onclick="document.getElementById('precios-kodak').classList.add('open')"><div class="price-icon pink">📷</div><div class="price-info"><h2>Fotos Kodak</h2><strong>Ver precios</strong><small>tocá para ver precios</small></div></button><button class="price-card polaroid-card" type="button" onclick="document.getElementById('precios-polaroid').classList.add('open')"><div class="price-icon orange">🖼️</div><div class="price-info"><h2>Fotos Polaroid</h2><strong>Ver precios</strong><small>individual · packs</small></div></button></div>
<div class="price-slide"><button class="price-card web-work-card" type="button" onclick="document.getElementById('trabajos-web').classList.add('open')"><div class="price-icon blue">🌐</div><div class="price-info"><h2>Trabajos web interactivos</h2><strong>Ver sitios</strong><small>Fleming · Abigail</small></div></button><button class="price-card plastificado-card" type="button" onclick="document.getElementById('precios-plastificado').classList.add('open')"><div class="price-icon yellow">🧊</div><div class="price-info"><h2>Plastificado</h2><strong>Ver precios</strong><small>6,7×9,8 · 7,6×11 · A4 · Oficio · A3</small></div></button><button class="price-card almanaques-card" type="button" onclick="document.getElementById('precios-almanaques').classList.add('open')"><div class="price-icon orange">📅</div><div class="price-info"><h2>Almanaques</h2><strong>Ver precios</strong><small>tocá para ver precios</small></div></button><button class="price-card tira-card" type="button" onclick="document.getElementById('precios-tira').classList.add('open')"><div class="price-icon pink">🎞️</div><div class="price-info"><h2>Tira de 4 fotos</h2><strong>$6.000</strong><small>7×19 cm vertical</small></div></button></div></div><div class="dots"><i></i><i></i><i></i></div>'''
        html = html[:track_start] + three_slide_carousel + html[track_end:]
    if 'id="precios-polaroid"' not in html:
        polaroid_modal = '<div class="web-modal" id="precios-polaroid" role="dialog" aria-modal="true" aria-label="Precios Fotos Polaroid"><div class="web-box"><div class="web-head"><h2>Precios Fotos Polaroid</h2><button class="web-close" type="button" aria-label="Cerrar" onclick="document.getElementById(\'precios-polaroid\').classList.remove(\'open\')">×</button></div><p class="web-sub">Fotos estilo Polaroid Mitsubishi. Medida final: 8,5×10,5 cm.</p><div class="inkjet-prices"><div><span>Individual</span><b>$3.000</b></div><div><span>Pack de 4</span><b>$10.000</b></div><div><span>Pack de 10</span><b>$22.000</b></div></div></div></div>'
        html = html.replace('</body>', polaroid_modal + '</body>', 1)
    if 'id="precios-plastificado"' not in html:
        plastificado_modal = '<div class="web-modal" id="precios-plastificado" role="dialog" aria-modal="true" aria-label="Precios de plastificado"><div class="web-box"><div class="web-head"><h2>Precios de plastificado</h2><button class="web-close" type="button" aria-label="Cerrar" onclick="document.getElementById(\'precios-plastificado\').classList.remove(\'open\')">×</button></div><p class="web-sub">Plastificado en caliente. Valores por hoja, llevando el cliente la impresión lista.</p><div class="inkjet-prices"><div><span>6,7×9,8 cm</span><b>$1.500</b></div><div><span>7,6×11 cm</span><b>$2.000</b></div><div><span>A4</span><b>$3.000</b></div><div><span>Oficio</span><b>$4.000</b></div><div><span>A3</span><b>$6.000</b></div></div></div></div>'
        html = html.replace('</body>', plastificado_modal + '</body>', 1)
    if 'id="precios-tira"' not in html:
        tira_modal = '<div class="web-modal" id="precios-tira" role="dialog" aria-modal="true" aria-label="Precio de tira vertical de 4 fotos"><div class="web-box"><div class="web-head"><h2>Tira vertical de 4 fotos</h2><button class="web-close" type="button" aria-label="Cerrar" onclick="document.getElementById(\'precios-tira\').classList.remove(\'open\')">×</button></div><p class="web-sub">Cuatro fotos en una tira vertical tipo cabina. Medida aproximada: 7×19 cm.</p><div class="inkjet-prices"><div><span>1 tira</span><b>$6.000</b></div><div><span>2 tiras</span><b>$10.000</b></div><div><span>Con diseño especial</span><b>$7.000</b></div></div></div></div>'
        html = html.replace('</body>', tira_modal + '</body>', 1)
    # Rulito: mascota animada con globo de bienvenida y acceso a todos los precios.
    animated_mascot = '''<div class="rulito-widget" aria-label="Rulito, asistente de Imprenta Ruiz">
      <div class="rulito-bubble">
        <strong class="rulito-message">👋 Hola, bienvenidos a Imprenta Ruiz</strong>
      </div>
      <img class="mascota-float" src="/static/video_muneco_ruiz_transparente.gif" alt="Rulito, muñeco animado de Imprenta Ruiz">
    </div>'''
    mascot_start = html.find('<img class="mascota-float"')
    if mascot_start >= 0:
        mascot_end = html.find('>', mascot_start)
        if mascot_end >= 0:
            html = html[:mascot_start] + animated_mascot + html[mascot_end + 1:]
    location_anchor = '<a class="hit hit-map" href="https://www.google.com/maps/search/?api=1&query=Chacabuco+470+Salta" target="_blank" rel="noopener" aria-label="Cómo llegar a Imprenta Ruiz"></a>'
    location_buttons = '''<div class="location-split hit" aria-label="Ubicación de Imprenta Ruiz">
      <button type="button" class="location-hotspot front-hotspot" data-open-modal="frontModal" title="Ver mi casa" aria-label="Ver mi casa"></button>
      <button type="button" class="location-hotspot map-hotspot" data-open-modal="mapModal" title="Cómo llegar y ver mapa" aria-label="Cómo llegar y ver mapa"></button>
    </div>'''
    html = html.replace(location_anchor, location_buttons, 1)
    location_ui = '''
<style>
.plastificado-card,.tira-card{cursor:pointer;text-align:left;padding:0}
.price-track[data-three-slides="polaroid"]{width:300%;animation:price-slide-three 24s ease-in-out infinite}
.price-track[data-three-slides="polaroid"] .price-slide{width:33.333333%;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr}
@keyframes price-slide-three{0%,24%{transform:translateX(0)}33%,57%{transform:translateX(-33.333333%)}66%,90%{transform:translateX(-66.666666%)}100%{transform:translateX(0)}}
.rulito-widget{position:fixed;right:6px;bottom:96px;z-index:25;width:190px;display:flex;flex-direction:column;align-items:flex-end;pointer-events:none}
.rulito-widget .mascota-float{position:static;width:145px;max-height:205px;pointer-events:none;animation:robot-float 3.2s ease-in-out infinite}
.rulito-bubble{position:relative;width:150px;min-height:44px;margin:0 3px 7px;padding:9px 9px 8px;border:2px solid #202020;border-radius:50%;background:#fff;box-shadow:4px 5px 0 #202020,0 6px 10px rgba(0,0,0,.16);color:#111;font:700 10px/1.2 Arial,sans-serif;text-align:center;pointer-events:auto}
.rulito-bubble:after{content:"";position:absolute;left:23px;bottom:-15px;width:19px;height:17px;background:#fff;border-left:2px solid #202020;border-bottom:2px solid #202020;transform:skew(-25deg) rotate(-28deg);border-radius:0 0 0 4px}
.rulito-bubble strong,.rulito-bubble span{display:block}.rulito-bubble strong{font-size:11px;margin-bottom:2px}.rulito-bubble b{color:#087c9a}.rulito-message{min-height:26px;display:flex!important;align-items:center;justify-content:center}.rulito-message.rulito-pop{animation:rulito-pop .35s ease}@keyframes rulito-pop{0%{opacity:.25;transform:scale(.92)}100%{opacity:1;transform:scale(1)}}
.rulito-prices-btn{display:none}
.rulito-prices-btn:active{transform:scale(.97)}
.rulito-prices-modal{display:none;position:fixed;inset:0;z-index:80;background:rgba(3,16,36,.78);align-items:center;justify-content:center;padding:14px}
.rulito-prices-modal.is-open{display:flex}.rulito-prices-card{position:relative;width:min(700px,96vw);max-height:88vh;overflow:auto;border-radius:22px;padding:20px;background:#fff;box-shadow:0 20px 55px #0008;color:#071b3b;font-family:Arial,sans-serif}.rulito-prices-card h2{margin:0 38px 4px 0;font-size:23px}.rulito-prices-card>p{margin:0 0 14px;color:#516274;font-weight:700}.rulito-price-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.rulito-price-group{padding:11px;border-radius:13px;background:#f0fbff;border-left:4px solid #078da8}.rulito-price-group h3{margin:0 0 6px;font-size:15px;color:#087c9a}.rulito-price-group p{margin:3px 0;font-size:13px;font-weight:700}.rulito-price-close{position:absolute;right:12px;top:10px;border:0;border-radius:10px;background:#071b3b;color:#fff;padding:7px 10px;font-weight:900;cursor:pointer}
@media(max-width:620px){.rulito-widget{right:3px;bottom:82px;width:170px}.rulito-widget .mascota-float{width:112px;max-height:165px}.rulito-bubble{width:130px;padding:7px;font-size:9px}.rulito-bubble strong{font-size:10px}.rulito-price-grid{grid-template-columns:1fr}.rulito-prices-card{padding:16px}.rulito-prices-card h2{font-size:20px}}
.location-split{display:flex;align-items:stretch;pointer-events:auto;background:transparent;z-index:999!important;isolation:isolate}
.location-hotspot{position:relative;z-index:1000;height:100%;border:0;background:transparent;cursor:pointer;pointer-events:auto;touch-action:manipulation;-webkit-tap-highlight-color:rgba(7,27,59,.18)}
.location-hotspot:focus-visible{outline:3px solid #078de8;outline-offset:-4px;border-radius:18px}
.front-hotspot{width:34%}
.map-hotspot{width:66%}
.ruiz-modal{display:none;position:fixed;inset:0;z-index:30;background:rgba(3,16,36,.78);align-items:center;justify-content:center;padding:18px}
.ruiz-modal.is-open{display:flex}
.ruiz-modal-card{position:relative;width:min(920px,96vw);max-height:92vh;overflow:auto;background:#fff;border-radius:20px;padding:22px;box-shadow:0 20px 55px rgba(0,0,0,.4);text-align:center}
.ruiz-modal-card h2{margin:4px 35px 15px;color:#071b3b;font:900 24px Arial}
.ruiz-close{position:absolute;right:14px;top:10px;border:0;border-radius:12px;background:#071b3b;color:#fff;padding:8px 12px;font:900 14px Arial;cursor:pointer}
.ruiz-front-image,.ruiz-map-image{display:block;width:100%;max-height:64vh;object-fit:contain;border-radius:14px;background:#eef3f7}.missing-front{padding:58px 22px;color:#071b3b;font:700 17px Arial;box-sizing:border-box}
.ruiz-map-frame{display:block;width:100%;height:min(52vh,480px);border:0;border-radius:14px;margin-bottom:12px}
.ruiz-map-link{display:inline-block;background:#1769d1;color:#fff;text-decoration:none;border-radius:12px;padding:11px 16px;font:900 15px Arial}
@media(max-width:620px){.location-hotspot{min-height:100%}.ruiz-modal-card{padding:15px}.ruiz-modal-card h2{font-size:19px}.ruiz-modal{padding:9px}}
</style>
<div class="ruiz-modal" id="frontModal" role="dialog" aria-modal="true" aria-labelledby="frontModalTitle">
  <div class="ruiz-modal-card"><button class="ruiz-close" type="button" data-close-modal>Cerrar ✕</button><h2 id="frontModalTitle">Mi casa / Imprenta Ruiz</h2><img class="ruiz-front-image" src="/static/frente_casa_rejas_final.jpg" alt="Frente con rejas de Imprenta Ruiz en Chacabuco 470"></div>
</div>
<div class="ruiz-modal" id="mapModal" role="dialog" aria-modal="true" aria-labelledby="mapModalTitle">
  <div class="ruiz-modal-card"><button class="ruiz-close" type="button" data-close-modal>Cerrar ✕</button><h2 id="mapModalTitle">Cómo llegar a Imprenta Ruiz</h2><iframe class="ruiz-map-frame" title="Mapa de Chacabuco 470, Salta" src="https://www.google.com/maps?q=Chacabuco%20470%2C%20Salta&output=embed" loading="lazy"></iframe><a class="ruiz-map-link" href="https://www.google.com/maps/search/?api=1&query=Chacabuco+470+Salta" target="_blank" rel="noopener">Abrir ubicación en Google Maps</a></div>
</div>
<div class="rulito-prices-modal" id="rulitoPricesModal" role="dialog" aria-modal="true" aria-labelledby="rulitoPricesTitle">
  <div class="rulito-prices-card"><button class="rulito-price-close" type="button" data-rulito-close>Cerrar ✕</button><h2 id="rulitoPricesTitle">🧾 Precios de Imprenta Ruiz</h2><p>Estos son los precios actuales. Si necesitás otro trabajo, preguntame.</p>
    <div class="rulito-price-grid">
      <div class="rulito-price-group"><h3>Impresiones</h3><p>Color: <b>$1.250</b> por faz</p><p>Blanco y negro: <b>$1.250</b> por faz</p><p>Anillado: <b>$2.500</b></p><p>A4 autoadhesivo: <b>$6.000</b></p></div>
      <div class="rulito-price-group"><h3>Fotos Mitsubishi</h3><p>10×15: <b>$4.000</b> · 13×18: <b>$5.000</b></p><p>15×15: <b>$5.000</b> · 15×20: <b>$6.000</b></p><p>20×30: <b>$14.000</b> · A4: <b>$12.000</b></p></div>
      <div class="rulito-price-group"><h3>Fotos Inkjet</h3><p>10×15: <b>$3.000</b> · 13×18: <b>$3.500</b></p><p>15×15: <b>$3.500</b> · 15×20: <b>$4.000</b></p><p>A4: <b>$6.000</b></p></div>
      <div class="rulito-price-group"><h3>Fotos Kodak</h3><p>10×15: <b>$4.500</b> · 15×15: <b>$5.500</b></p><p>15×20: <b>$7.000</b></p></div>
      <div class="rulito-price-group"><h3>Polaroid Mitsubishi</h3><p>Individual: <b>$3.000</b></p><p>Pack de 4: <b>$10.000</b></p><p>Pack de 10: <b>$22.000</b></p><p>Medida: 8,5×10,5 cm</p></div>
      <div class="rulito-price-group"><h3>Almanaques</h3><p>5×8: <b>$2.000</b> · 9×6: <b>$2.500</b></p><p>A4: <b>$6.000</b> · A3: <b>$12.000</b> · A3+: <b>$15.000</b></p></div>
      <div class="rulito-price-group"><h3>Plastificado</h3><p>6,7×9,8 cm: <b>$1.500</b></p><p>7,6×11 cm: <b>$2.000</b></p><p>A4: <b>$3.000</b></p><p>Oficio: <b>$4.000</b></p><p>A3: <b>$6.000</b></p><p>Tira vertical de 4 fotos: <b>$6.000</b> · 7×19 cm</p><p>Diseños web: consultar según proyecto.</p></div>
    </div>
  </div>
</div>
<script>
(function(){
  function closeAll(){document.querySelectorAll('.ruiz-modal.is-open,.rulito-prices-modal.is-open').forEach(function(m){m.classList.remove('is-open')})}
  function openModal(id){closeAll();var m=document.getElementById(id);if(m)m.classList.add('is-open')}
  var pricesModal=document.getElementById('rulitoPricesModal');
  var rulitoMessage=document.querySelector('.rulito-message');
  var rulitoMessages=[
    '👋 Hola, bienvenidos a Imprenta Ruiz',
    'Soy Rulito, tu asistente.',
    '🖨️ Impresión color: $1.250 por faz',
    '📄 Blanco y negro: $1.250 por faz',
    '🔩 Anillado: $2.500',
    '🏷️ A4 autoadhesivo: $6.000 por hoja',
    '📸 Mitsubishi 10×15: $4.000',
    '📸 Mitsubishi 13×18: $5.000',
    '📸 Mitsubishi 15×15: $5.000',
    '📸 Mitsubishi 15×20: $6.000',
    '📸 Mitsubishi 20×30: $14.000',
    '📸 Mitsubishi A4: $12.000',
    '🖼️ Inkjet 10×15: $3.000',
    '🖼️ Inkjet 13×18: $3.500',
    '🖼️ Inkjet 15×15: $3.500',
    '🖼️ Inkjet 15×20: $4.000',
    '🖼️ Inkjet A4: $6.000',
    '📷 Kodak 10×15: $4.500',
    '📷 Kodak 15×15: $5.500',
    '📷 Kodak 15×20: $7.000',
    '🖼️ Polaroid individual: $3.000 · 8,5×10,5 cm',
    '🖼️ Polaroid pack de 4: $10.000',
    '🖼️ Polaroid pack de 10: $22.000',
    '📅 Almanaque 5×8: $2.000',
    '📅 Almanaque 9×6: $2.500',
    '📅 Almanaque A4: $6.000',
    '📅 Almanaque A3: $12.000',
    '📅 Almanaque A3+: $15.000',
    '🧊 Plastificado 6,7×9,8 cm: $1.500',
    '🧊 Plastificado 7,6×11 cm: $2.000',
    '🧊 Plastificado A4: $3.000',
    '🧊 Plastificado Oficio: $4.000',
    '🧊 Plastificado A3: $6.000',
    '🎞️ Tira vertical de 4 fotos: $6.000 · 7×19 cm',
    '💻 Diseños web: consultar'
  ];
  var rulitoIndex=0;
  function nextRulitoMessage(){if(!rulitoMessage)return;rulitoIndex=(rulitoIndex+1)%rulitoMessages.length;rulitoMessage.classList.remove('rulito-pop');void rulitoMessage.offsetWidth;rulitoMessage.textContent=rulitoMessages[rulitoIndex];rulitoMessage.classList.add('rulito-pop')}
  document.querySelectorAll('.rulito-prices-btn').forEach(function(b){b.addEventListener('click',nextRulitoMessage)});
  if(rulitoMessage)window.setInterval(nextRulitoMessage,4200);
  document.querySelectorAll('[data-rulito-close]').forEach(function(b){b.addEventListener('click',closeAll)});
  if(pricesModal)pricesModal.addEventListener('click',function(e){if(e.target===pricesModal)closeAll()});
  document.querySelectorAll('[data-open-modal]').forEach(function(b){b.addEventListener('click',function(){openModal(b.getAttribute('data-open-modal'))})})
  document.querySelectorAll('[data-close-modal]').forEach(function(b){b.addEventListener('click',closeAll)})
  document.querySelectorAll('.ruiz-modal').forEach(function(m){m.addEventListener('click',function(e){if(e.target===m)closeAll()})})
  document.addEventListener('keydown',function(e){if(e.key==='Escape')closeAll()})
  /* Respaldo para teléfonos: si la mascota o la imagen recibe el toque,
     detectamos igualmente las dos zonas del botón Cómo llegar. */
  document.addEventListener('click',function(e){
    var c=document.querySelector('.canvas');if(!c)return;
    var r=c.getBoundingClientRect(),x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;
    if(x>=.10&&x<=.90&&y>=.70&&y<=.83){
      e.preventDefault();e.stopPropagation();openModal(x<.43?'frontModal':'mapModal');
    }
  },true);
})();
</script>
'''
    html = html.replace('</body>', location_ui + '</body>', 1)
    social_preview = """
<meta property="og:type" content="website">
<meta property="og:title" content="Imprenta Ruiz">
<meta property="og:description" content="Precios y trabajos web de Imprenta Ruiz.">
<meta property="og:image" content="https://volante-server.onrender.com/static/imprenta-ruiz-preview-v3.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:url" content="https://volante-server.onrender.com/imprenta-ruiz">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="https://volante-server.onrender.com/static/imprenta-ruiz-preview-v3.jpg">
"""
    return html.replace("</head>", social_preview + "</head>", 1)


@app.route("/imprenta-ruiz/subir-video", methods=["GET", "POST"])
def imprenta_ruiz_subir_video():
    """Carga temporal de videos del muñeco para procesarlos desde Render."""
    upload_dir = Path(app.static_folder) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    mensaje = ""
    enlace = ""
    if request.method == "POST":
        if request.content_length and request.content_length > 150 * 1024 * 1024:
            mensaje = "El video supera el límite de 150 MB."
        else:
            # Algunos teléfonos envían el archivo con otro nombre de campo o sin
            # nombre visible; aceptamos igualmente el primer archivo de video.
            video = request.files.get("video")
            if not video and request.files:
                video = next(iter(request.files.values()))
            nombre = secure_filename(video.filename or "video.mp4") if video else ""
            extensiones = {".mp4", ".mov", ".webm", ".m4v", ".avi", ".mkv", ".webp"}
            extension = Path(nombre).suffix.lower()
            mime = (video.mimetype or "") if video else ""
            if extension not in extensiones and mime.startswith("video/"):
                extension = ".mp4"
            if not video or extension not in extensiones:
                mensaje = "Elegí un video MP4, MOV, WEBM, M4V, AVI, MKV o una imagen WEBP animada."
            else:
                destino = upload_dir / f"ruiz_video_{uuid.uuid4().hex}{extension}"
                video.save(destino)
                enlace = url_for("static", filename=f"uploads/{destino.name}", _external=True)
                mensaje = "Video cargado correctamente."
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Subir video — Imprenta Ruiz</title><style>body{{margin:0;background:#071b3b;font-family:Arial,sans-serif;color:#071b3b;display:grid;place-items:center;min-height:100vh;padding:18px;box-sizing:border-box}}main{{width:min(520px,100%);background:#fff;border-radius:22px;padding:24px;box-shadow:0 18px 50px #0006}}h1{{margin:0 0 8px;font-size:25px}}p{{color:#4d5b6b;line-height:1.45}}input{{width:100%;padding:14px;border:2px dashed #168bb1;border-radius:14px;box-sizing:border-box;background:#f1fbff;margin:12px 0 16px}}button{{width:100%;border:0;border-radius:14px;padding:14px;background:#087c9a;color:#fff;font-weight:900;font-size:16px;cursor:pointer}}.ok{{margin-top:16px;padding:13px;border-radius:12px;background:#e7f8ee;color:#146b3c;font-weight:800;word-break:break-word}}a{{color:#075fa8}}</style></head><body><main><h1>🎬 Subir video del muñeco</h1><p>Elegí el video desde tu celular. Podés subir MP4 o MOV de hasta 150 MB. Después de cargarlo, copiá el enlace y mandámelo por este chat.</p><form method="post" enctype="multipart/form-data"><input type="file" name="video" accept="video/*,.mp4,.mov,.webm,.m4v,.avi,.mkv" required><button type="submit">Subir video</button></form>{f"<div class='ok'>{mensaje}<br><a href='{enlace}' target='_blank'>Abrir o descargar el video</a></div>" if enlace else (f"<div class='ok'>{mensaje}</div>" if mensaje else "")}</main></body></html>'''

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
