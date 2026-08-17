import os, sqlite3, json
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, request, render_template, session

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('CARRITO_DATA_DIR', os.path.join(BASE, 'data'))
os.makedirs(DATA_DIR, exist_ok=True)
DB = os.path.join(DATA_DIR, 'la_esquina.db')
app = Flask(__name__, template_folder='.')
app.secret_key = os.environ.get('APP_SECRET', 'change-this-secret')
SELLER_PIN = os.environ.get('SELLER_PIN', '4827')
LOCAL_TZ = ZoneInfo('America/Argentina/Salta')

INITIAL_PRODUCTS = [
    ('Calabaza', '🥦', 'Frutas y verduras', 0, 999),
    ('Zanahoria', '🥦', 'Frutas y verduras', 0, 999),
    ('Champiñones', '🥦', 'Frutas y verduras', 0, 999),
    ('Chícharos', '🥦', 'Frutas y verduras', 0, 999),
    ('Jitomate', '🥦', 'Frutas y verduras', 0, 999),
    ('Limón', '🥦', 'Frutas y verduras', 0, 999),
    ('Pimiento', '🥦', 'Frutas y verduras', 0, 999),
    ('Aguacate', '🥦', 'Frutas y verduras', 0, 999),
    ('Lechuga', '🥦', 'Frutas y verduras', 0, 999),
    ('Espinaca/Acelga', '🥦', 'Frutas y verduras', 0, 999),
    ('Cebolla', '🥦', 'Frutas y verduras', 0, 999),
    ('Ajo', '🥦', 'Frutas y verduras', 0, 999),
    ('Nopales', '🥦', 'Frutas y verduras', 0, 999),
    ('Ejotes', '🥦', 'Frutas y verduras', 0, 999),
    ('Papas', '🥦', 'Frutas y verduras', 0, 999),
    ('Cilantro', '🥦', 'Frutas y verduras', 0, 999),
    ('Manzanas', '🥦', 'Frutas y verduras', 0, 999),
    ('Plátano', '🥦', 'Frutas y verduras', 0, 999),
    ('Fruta de temporada', '🥦', 'Frutas y verduras', 0, 999),
    ('Frijol', '🌾', 'Granos, semillas y frutos secos', 0, 999),
    ('Garbanzos', '🌾', 'Granos, semillas y frutos secos', 0, 999),
    ('Lentejas', '🌾', 'Granos, semillas y frutos secos', 0, 999),
    ('Arroz', '🌾', 'Granos, semillas y frutos secos', 0, 999),
    ('Semillas de girasol', '🌾', 'Granos, semillas y frutos secos', 0, 999),
    ('Ajonjolí', '🌾', 'Granos, semillas y frutos secos', 0, 999),
    ('Almendras', '🌾', 'Granos, semillas y frutos secos', 0, 999),
    ('Nuez', '🌾', 'Granos, semillas y frutos secos', 0, 999),
    ('Chile negro', '🌾', 'Granos, semillas y frutos secos', 0, 999),
    ('Chile de guisar', '🌾', 'Granos, semillas y frutos secos', 0, 999),
    ('Chile cascabel', '🌾', 'Granos, semillas y frutos secos', 0, 999),
    ('Pasas', '🌾', 'Granos, semillas y frutos secos', 0, 999),
    ('Jamón de pavo', '🥩', 'Embutidos', 0, 999),
    ('Chile poblano', '❄️', 'Congelados', 0, 999),
    ('Brócoli', '❄️', 'Congelados', 0, 999),
    ('Pollo', '❄️', 'Congelados', 0, 999),
    ('Camarones', '❄️', 'Congelados', 0, 999),
    ('Filetes de pescado', '❄️', 'Congelados', 0, 999),
    ('Salmón', '❄️', 'Congelados', 0, 999),
    ('Galletas saladas', '🥖', 'Panadería', 0, 999),
    ('Pan de caja', '🥖', 'Panadería', 0, 999),
    ('Bollos', '🥖', 'Panadería', 0, 999),
    ('Baguette', '🥖', 'Panadería', 0, 999),
    ('Tortillas de maíz', '🌮', 'Tortillería', 0, 999),
    ('Tortillas de harina', '🌮', 'Tortillería', 0, 999),
    ('Tostadas de maíz', '🌮', 'Tortillería', 0, 999),
    ('Chile en vinagre', '🥫', 'Enlatados', 0, 999),
    ('Chile chipotle', '🥫', 'Enlatados', 0, 999),
    ('Ensalada de verduras', '🥫', 'Enlatados', 0, 999),
    ('Atún', '🥫', 'Enlatados', 0, 999),
    ('Elote', '🥫', 'Enlatados', 0, 999),
    ('Avena en copos', '🥣', 'Cereales', 0, 999),
    ('Granola', '🥣', 'Cereales', 0, 999),
    ('Harina de trigo', '🥣', 'Cereales', 0, 999),
    ('Pasta tornillo', '🥣', 'Cereales', 0, 999),
    ('Pasta espagueti', '🥣', 'Cereales', 0, 999),
    ('Cuscús', '🥣', 'Cereales', 0, 999),
    ('Huevo', '🧺', 'Otros', 0, 999),
    ('Aceite de oliva', '🧺', 'Otros', 0, 999),
    ('Aceite de canola', '🧺', 'Otros', 0, 999),
    ('Cacao', '🫙', 'Condimentos', 0, 999),
    ('Polvo para hornear', '🫙', 'Condimentos', 0, 999),
    ('Bicarbonato', '🫙', 'Condimentos', 0, 999),
    ('Levadura', '🫙', 'Condimentos', 0, 999),
    ('Vainilla', '🫙', 'Condimentos', 0, 999),
    ('Azúcar', '🫙', 'Condimentos', 0, 999),
    ('Miel', '🫙', 'Condimentos', 0, 999),
    ('Vinagre blanco', '🫙', 'Condimentos', 0, 999),
    ('Vinagre de manzana', '🫙', 'Condimentos', 0, 999),
    ('Vinagre balsámico', '🫙', 'Condimentos', 0, 999),
    ('Salsa de soya', '🫙', 'Condimentos', 0, 999),
    ('Salsa macha', '🫙', 'Condimentos', 0, 999),
    ('Salsa de chile verde', '🫙', 'Condimentos', 0, 999),
    ('Mostaza', '🫙', 'Condimentos', 0, 999),
    ('Mayonesa', '🫙', 'Condimentos', 0, 999),
    ('Mermelada', '🫙', 'Condimentos', 0, 999),
    ('Comino', '🌿', 'Hierbas y especias', 0, 999),
    ('Hojas de laurel', '🌿', 'Hierbas y especias', 0, 999),
    ('Clavo', '🌿', 'Hierbas y especias', 0, 999),
    ('Tomillo', '🌿', 'Hierbas y especias', 0, 999),
    ('Nuez moscada', '🌿', 'Hierbas y especias', 0, 999),
    ('Canela', '🌿', 'Hierbas y especias', 0, 999),
    ('Pimienta', '🌿', 'Hierbas y especias', 0, 999),
    ('Sal', '🌿', 'Hierbas y especias', 0, 999),
    ('Mezcla italiana', '🌿', 'Hierbas y especias', 0, 999),
    ('Orégano', '🌿', 'Hierbas y especias', 0, 999),
    ('Leche', '🥛', 'Lácteos', 0, 999),
    ('Queso panela', '🥛', 'Lácteos', 0, 999),
    ('Queso tipo manchego', '🥛', 'Lácteos', 0, 999),
    ('Yogurt griego', '🥛', 'Lácteos', 0, 999),
    ('Mantequilla', '🥛', 'Lácteos', 0, 999),
]

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS products (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          emoji TEXT DEFAULT '📦',
          category TEXT NOT NULL,
          price INTEGER NOT NULL DEFAULT 0,
          stock INTEGER NOT NULL DEFAULT 0,
          available INTEGER NOT NULL DEFAULT 1,
          image_url TEXT DEFAULT '',
          description TEXT DEFAULT '',
          is_menu INTEGER NOT NULL DEFAULT 0,
          menu_date TEXT DEFAULT '',
          cutoff_time TEXT DEFAULT '11:30'
        );
        CREATE TABLE IF NOT EXISTS cart_location (
          id INTEGER PRIMARY KEY CHECK(id=1),
          lat REAL, lng REAL, floor TEXT DEFAULT 'Planta baja', corridor TEXT DEFAULT 'Pasillo A', updated_at TEXT, active INTEGER DEFAULT 0, status TEXT DEFAULT 'cerrado', meeting_point TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS orders (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          customer TEXT NOT NULL,
          phone TEXT DEFAULT '',
          floor TEXT NOT NULL,
          corridor TEXT NOT NULL,
          detail TEXT DEFAULT '',
          payment TEXT NOT NULL,
          total INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'recibido',
          items_json TEXT NOT NULL
        );
        INSERT OR IGNORE INTO cart_location(id, floor, corridor, active) VALUES (1, 'Planta baja', 'Pasillo A', 0);
        CREATE TABLE IF NOT EXISTS debts (
          id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, created_at TEXT NOT NULL,
          customer TEXT NOT NULL, phone TEXT DEFAULT '', floor TEXT NOT NULL, corridor TEXT NOT NULL,
          detail TEXT DEFAULT '', amount INTEGER NOT NULL, balance INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pendiente'
        );
        CREATE TABLE IF NOT EXISTS debt_payments (
          id INTEGER PRIMARY KEY AUTOINCREMENT, debt_id INTEGER NOT NULL, paid_at TEXT NOT NULL, amount INTEGER NOT NULL, note TEXT DEFAULT ''
        );
        ''')
        product_cols = {r[1] for r in con.execute('PRAGMA table_info(products)').fetchall()}
        if 'image_url' not in product_cols: con.execute("ALTER TABLE products ADD COLUMN image_url TEXT DEFAULT ''")
        if 'description' not in product_cols: con.execute("ALTER TABLE products ADD COLUMN description TEXT DEFAULT ''")
        if 'is_menu' not in product_cols: con.execute("ALTER TABLE products ADD COLUMN is_menu INTEGER NOT NULL DEFAULT 0")
        if 'menu_date' not in product_cols: con.execute("ALTER TABLE products ADD COLUMN menu_date TEXT DEFAULT ''")
        if 'cutoff_time' not in product_cols: con.execute("ALTER TABLE products ADD COLUMN cutoff_time TEXT DEFAULT '11:30'")
        cols = {r[1] for r in con.execute('PRAGMA table_info(cart_location)').fetchall()}
        if 'floor' not in cols: con.execute("ALTER TABLE cart_location ADD COLUMN floor TEXT DEFAULT 'Planta baja'")
        if 'corridor' not in cols: con.execute("ALTER TABLE cart_location ADD COLUMN corridor TEXT DEFAULT 'Pasillo A'")
        if 'status' not in cols: con.execute("ALTER TABLE cart_location ADD COLUMN status TEXT DEFAULT 'cerrado'")
        if 'meeting_point' not in cols: con.execute("ALTER TABLE cart_location ADD COLUMN meeting_point TEXT DEFAULT ''")
        if con.execute('SELECT COUNT(*) FROM products').fetchone()[0] == 0:
            con.executemany('INSERT INTO products(name,emoji,category,price,stock,available) VALUES (?,?,?,?,?,1)', INITIAL_PRODUCTS)

def seller_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get('seller_ok'):
            return jsonify({'error': 'Vendedor no autenticado'}), 401
        return fn(*args, **kwargs)
    return wrapped

@app.post('/api/admin/login')
def admin_login():
    data = request.get_json(force=True) or {}
    if str(data.get('pin', '')) != str(SELLER_PIN):
        return jsonify({'error': 'PIN incorrecto'}), 401
    session['seller_ok'] = True
    return jsonify({'ok': True})

@app.post('/api/admin/logout')
def admin_logout():
    session.clear()
    return jsonify({'ok': True})

@app.get('/api/admin/me')
def admin_me():
    return jsonify({'authenticated': bool(session.get('seller_ok'))})

def menu_block_reason(row):
    if not row or not row['is_menu']: return None
    now = datetime.now(LOCAL_TZ)
    menu_date = (row['menu_date'] or '').strip()
    if menu_date and menu_date != now.date().isoformat():
        return 'Este menú no corresponde a la fecha de hoy.'
    cutoff = (row['cutoff_time'] or '').strip()
    if cutoff:
        try:
            hh, mm = [int(x) for x in cutoff.split(':', 1)]
            if now.hour > hh or (now.hour == hh and now.minute >= mm): return f'El menú de hoy se podía pedir hasta las {cutoff}.'
        except (ValueError, TypeError): pass
    return None

def product_dict(row):
    d = dict(row)
    d['available'] = bool(d['available']) and d['stock'] > 0
    return d

def location_dict(row):
    if not row:
        return {'active': False, 'lat': None, 'lng': None, 'updated_at': None}
    d = dict(row)
    d['active'] = bool(d['active'])
    d['status'] = d.get('status') or ('activo' if d['active'] else 'cerrado')
    d['meeting_point'] = d.get('meeting_point') or ''
    return d

@app.get('/')
def home():
    return render_template('index.html')

@app.get('/api/products')
def products():
    with db() as con:
        rows = con.execute('SELECT * FROM products ORDER BY category, name').fetchall()
    return jsonify([product_dict(r) for r in rows])

@app.get('/api/location')
def get_location():
    with db() as con:
        row = con.execute('SELECT * FROM cart_location WHERE id=1').fetchone()
    return jsonify(location_dict(row))

@app.post('/api/location')
@seller_required
def set_location():
    data = request.get_json(force=True) or {}
    with db() as con:
        status = str(data.get('status', 'activo')).strip() or 'activo'
        active = 0 if status == 'cerrado' else (1 if data.get('active', True) else 0)
        con.execute('UPDATE cart_location SET lat=?, lng=?, floor=?, corridor=?, updated_at=?, active=?, status=?, meeting_point=? WHERE id=1',
                    (data.get('lat'), data.get('lng'), data.get('floor', 'Planta baja'), data.get('corridor', 'Pasillo A'), datetime.now().isoformat(timespec='seconds'), active, status, str(data.get('meeting_point') or '').strip()))
    return jsonify({'ok': True})

@app.post('/api/location/off')
@seller_required
def location_off():
    with db() as con:
        con.execute("UPDATE cart_location SET active=0, status='cerrado', updated_at=? WHERE id=1", (datetime.now().isoformat(timespec='seconds'),))
    return jsonify({'ok': True})

@app.patch('/api/admin/products/<int:pid>')
@seller_required
def update_product(pid):
    data = request.get_json(force=True) or {}
    fields, values = [], []
    if 'name' in data: fields += ['name=?']; values += [str(data['name']).strip()]
    if 'price' in data: fields += ['price=?']; values += [max(0, int(data['price']))]
    if 'stock' in data: fields += ['stock=?']; values += [max(0, int(data['stock']))]
    if 'available' in data: fields += ['available=?']; values += [1 if data['available'] else 0]
    if 'image_url' in data: fields += ['image_url=?']; values += [str(data.get('image_url') or '').strip()]
    if 'description' in data: fields += ['description=?']; values += [str(data.get('description') or '').strip()]
    if 'is_menu' in data: fields += ['is_menu=?']; values += [1 if data['is_menu'] else 0]
    if 'menu_date' in data: fields += ['menu_date=?']; values += [str(data.get('menu_date') or '').strip()]
    if 'cutoff_time' in data: fields += ['cutoff_time=?']; values += [str(data.get('cutoff_time') or '').strip()]
    if not fields: return jsonify({'error': 'Sin cambios'}), 400
    values.append(pid)
    with db() as con:
        cur = con.execute('UPDATE products SET ' + ', '.join(fields) + ' WHERE id=?', values)
        if cur.rowcount == 0: return jsonify({'error': 'Producto inexistente'}), 404
        row = con.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
    return jsonify(product_dict(row))

@app.post('/api/admin/products')
@seller_required
def add_product():
    data = request.get_json(force=True) or {}
    name = str(data.get('name', '')).strip()
    if not name: return jsonify({'error': 'Falta el nombre'}), 400
    with db() as con:
        is_menu = bool(data.get('is_menu', False))
        cur = con.execute('INSERT INTO products(name,emoji,category,price,stock,available,image_url,description,is_menu,menu_date,cutoff_time) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                          (name, data.get('emoji', '📦'), data.get('category', 'Otros'), max(0, int(data.get('price', 0))), max(0, int(data.get('stock', 0))), 1, str(data.get('image_url') or '').strip(), str(data.get('description') or '').strip(), 1 if is_menu else 0, str(data.get('menu_date') or '').strip(), str(data.get('cutoff_time') or '11:30').strip()))
        row = con.execute('SELECT * FROM products WHERE id=?', (cur.lastrowid,)).fetchone()
    return jsonify(product_dict(row)), 201

@app.get('/api/orders')
@seller_required
def orders():
    with db() as con:
        rows = con.execute('SELECT * FROM orders ORDER BY id DESC LIMIT 100').fetchall()
    out = []
    for r in rows:
        d = dict(r); d['items'] = json.loads(d.pop('items_json')); out.append(d)
    return jsonify(out)

@app.post('/api/orders')
def create_order():
    data = request.get_json(force=True) or {}
    required = ['customer', 'floor', 'corridor', 'payment', 'items']
    if any(not data.get(k) for k in required):
        return jsonify({'error': 'Completá nombre, piso, pasillo, medio de pago y productos.'}), 400
    items = data['items']
    if not isinstance(items, list) or not items:
        return jsonify({'error': 'El pedido está vacío.'}), 400
    total = 0
    checked = []
    with db() as con:
        for item in items:
            row = con.execute('SELECT * FROM products WHERE id=?', (item.get('id'),)).fetchone()
            qty = max(0, int(item.get('qty', 0)))
            if not row or qty < 1 or not product_dict(row)['available'] or qty > row['stock']:
                return jsonify({'error': f"No hay disponibilidad de {row['name'] if row else 'un producto'}."}), 409
            blocked = menu_block_reason(row)
            if blocked: return jsonify({'error': blocked}), 409
            line = {'id': row['id'], 'name': row['name'], 'qty': qty, 'price': row['price']}
            checked.append(line); total += row['price'] * qty
        for line in checked:
            con.execute('UPDATE products SET stock=stock-? WHERE id=?', (line['qty'], line['id']))
        cur = con.execute('''INSERT INTO orders(created_at,customer,phone,floor,corridor,detail,payment,total,status,items_json)
          VALUES (?,?,?,?,?,?,?,?,?,?)''', (datetime.now().isoformat(timespec='seconds'), data['customer'].strip(), data.get('phone','').strip(),
          data['floor'], data['corridor'], data.get('detail','').strip(), data['payment'], total, 'recibido', json.dumps(checked, ensure_ascii=False)))
        if str(data['payment']).lower() == 'fiado':
            con.execute('''INSERT INTO debts(order_id,created_at,customer,phone,floor,corridor,detail,amount,balance,status)
              VALUES (?,?,?,?,?,?,?,?,?,?)''', (cur.lastrowid, datetime.now().isoformat(timespec='seconds'), data['customer'].strip(), data.get('phone','').strip(), data['floor'], data['corridor'], data.get('detail','').strip(), total, total, 'pendiente'))
    return jsonify({'ok': True, 'order_id': cur.lastrowid, 'total': total}), 201

@app.get('/api/debts')
@seller_required
def debts():
    with db() as con:
        rows = con.execute("SELECT * FROM debts ORDER BY CASE WHEN status='pendiente' THEN 0 ELSE 1 END, id DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d['payments'] = [dict(x) for x in con.execute('SELECT * FROM debt_payments WHERE debt_id=? ORDER BY id DESC', (r['id'],)).fetchall()]
            out.append(d)
    return jsonify(out)

@app.post('/api/debts/<int:did>/payments')
@seller_required
def debt_payment(did):
    data = request.get_json(force=True) or {}
    try: amount = int(data.get('amount', 0))
    except (TypeError, ValueError): amount = 0
    if amount <= 0: return jsonify({'error': 'Ingresá un importe válido.'}), 400
    with db() as con:
        row = con.execute('SELECT * FROM debts WHERE id=?', (did,)).fetchone()
        if not row: return jsonify({'error': 'Fiado inexistente.'}), 404
        amount = min(amount, row['balance'])
        con.execute('INSERT INTO debt_payments(debt_id,paid_at,amount,note) VALUES (?,?,?,?)', (did, datetime.now().isoformat(timespec='seconds'), amount, data.get('note','').strip()))
        new_balance = row['balance'] - amount
        con.execute('UPDATE debts SET balance=?, status=? WHERE id=?', (new_balance, 'pagado' if new_balance == 0 else 'pendiente', did))
    return jsonify({'ok': True, 'balance': new_balance})

@app.patch('/api/orders/<int:oid>')
@seller_required
def update_order(oid):
    status = (request.get_json(force=True) or {}).get('status')
    allowed = {'recibido', 'preparando', 'en_camino', 'entregado', 'cancelado'}
    if status not in allowed: return jsonify({'error': 'Estado inválido'}), 400
    with db() as con:
        cur = con.execute('UPDATE orders SET status=? WHERE id=?', (status, oid))
        if cur.rowcount == 0: return jsonify({'error': 'Pedido inexistente'}), 404
    return jsonify({'ok': True})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
else:
    init_db()
