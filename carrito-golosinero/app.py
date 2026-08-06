import os, sqlite3, json
from datetime import datetime
from flask import Flask, jsonify, request, render_template

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('CARRITO_DATA_DIR', os.path.join(BASE, 'data'))
os.makedirs(DATA_DIR, exist_ok=True)
DB = os.path.join(DATA_DIR, 'carrito.db')
app = Flask(__name__, template_folder='.')

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
          available INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS cart_location (
          id INTEGER PRIMARY KEY CHECK(id=1),
          lat REAL, lng REAL, updated_at TEXT, active INTEGER DEFAULT 0
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
        INSERT OR IGNORE INTO cart_location(id, active) VALUES (1, 0);
        ''')
        if con.execute('SELECT COUNT(*) FROM products').fetchone()[0] == 0:
            con.executemany('INSERT INTO products(name,emoji,category,price,stock,available) VALUES (?,?,?,?,?,1)', INITIAL_PRODUCTS)

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
def set_location():
    data = request.get_json(force=True) or {}
    with db() as con:
        con.execute('UPDATE cart_location SET lat=?, lng=?, updated_at=?, active=? WHERE id=1',
                    (data.get('lat'), data.get('lng'), datetime.now().isoformat(timespec='seconds'), 1 if data.get('active', True) else 0))
    return jsonify({'ok': True})

@app.post('/api/location/off')
def location_off():
    with db() as con:
        con.execute('UPDATE cart_location SET active=0, updated_at=? WHERE id=1', (datetime.now().isoformat(timespec='seconds'),))
    return jsonify({'ok': True})

@app.patch('/api/admin/products/<int:pid>')
def update_product(pid):
    data = request.get_json(force=True) or {}
    fields, values = [], []
    if 'name' in data: fields += ['name=?']; values += [str(data['name']).strip()]
    if 'price' in data: fields += ['price=?']; values += [max(0, int(data['price']))]
    if 'stock' in data: fields += ['stock=?']; values += [max(0, int(data['stock']))]
    if 'available' in data: fields += ['available=?']; values += [1 if data['available'] else 0]
    if not fields: return jsonify({'error': 'Sin cambios'}), 400
    values.append(pid)
    with db() as con:
        cur = con.execute('UPDATE products SET ' + ', '.join(fields) + ' WHERE id=?', values)
        if cur.rowcount == 0: return jsonify({'error': 'Producto inexistente'}), 404
        row = con.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
    return jsonify(product_dict(row))

@app.post('/api/admin/products')
def add_product():
    data = request.get_json(force=True) or {}
    name = str(data.get('name', '')).strip()
    if not name: return jsonify({'error': 'Falta el nombre'}), 400
    with db() as con:
        cur = con.execute('INSERT INTO products(name,emoji,category,price,stock,available) VALUES (?,?,?,?,?,?)',
                          (name, data.get('emoji', '📦'), data.get('category', 'Otros'), max(0, int(data.get('price', 0))), max(0, int(data.get('stock', 0))), 1))
        row = con.execute('SELECT * FROM products WHERE id=?', (cur.lastrowid,)).fetchone()
    return jsonify(product_dict(row)), 201

@app.get('/api/orders')
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
            line = {'id': row['id'], 'name': row['name'], 'qty': qty, 'price': row['price']}
            checked.append(line); total += row['price'] * qty
        for line in checked:
            con.execute('UPDATE products SET stock=stock-? WHERE id=?', (line['qty'], line['id']))
        cur = con.execute('''INSERT INTO orders(created_at,customer,phone,floor,corridor,detail,payment,total,status,items_json)
          VALUES (?,?,?,?,?,?,?,?,?,?)''', (datetime.now().isoformat(timespec='seconds'), data['customer'].strip(), data.get('phone','').strip(),
          data['floor'], data['corridor'], data.get('detail','').strip(), data['payment'], total, 'recibido', json.dumps(checked, ensure_ascii=False)))
    return jsonify({'ok': True, 'order_id': cur.lastrowid, 'total': total}), 201

@app.patch('/api/orders/<int:oid>')
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

