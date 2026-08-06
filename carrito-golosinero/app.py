import os, sqlite3, json
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, jsonify, request, render_template, session

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('CARRITO_DATA_DIR', os.path.join(BASE, 'data'))
os.makedirs(DATA_DIR, exist_ok=True)
DB = os.path.join(DATA_DIR, 'carrito.db')
app = Flask(__name__, template_folder='.')
app.secret_key = os.environ.get('APP_SECRET', 'change-this-secret')
SELLER_PIN = os.environ.get('SELLER_PIN', '4827')
LOCAL_TZ = ZoneInfo('America/Argentina/Salta')

INITIAL_PRODUCTS = [
    ('Baguette', '🥖', 'Sandwiches', 2500, 0),
    ('Pebete de jamón y queso', '🥪', 'Sandwiches', 3000, 0),
    ('Coca-Cola', '🥤', 'Gaseosas', 1800, 0),
    ('Agua mineral', '💧', 'Gaseosas', 1200, 0),
    ('Alfajor', '🍫', 'Golosinas', 1200, 0),
    ('Papas fritas', '🍟', 'Golosinas', 1500, 0),
    ('Chicle', '🍬', 'Golosinas', 700, 0),
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
          lat REAL, lng REAL, floor TEXT DEFAULT 'Planta baja', corridor TEXT DEFAULT 'Pasillo A', updated_at TEXT, active INTEGER DEFAULT 0
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
        con.execute('UPDATE cart_location SET lat=?, lng=?, floor=?, corridor=?, updated_at=?, active=? WHERE id=1',
                    (data.get('lat'), data.get('lng'), data.get('floor', 'Planta baja'), data.get('corridor', 'Pasillo A'), datetime.now().isoformat(timespec='seconds'), 1 if data.get('active', True) else 0))
    return jsonify({'ok': True})

@app.post('/api/location/off')
@seller_required
def location_off():
    with db() as con:
        con.execute('UPDATE cart_location SET active=0, updated_at=? WHERE id=1', (datetime.now().isoformat(timespec='seconds'),))
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
