import os
import sqlite3
import string
import random
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
# Kunci Rahasia Keamanan Sesi
app.secret_key = 'kasirinaja_saas_super_secret_2026' 

# ==========================================
# KONFIGURASI SAAS & RATE LIMITER (ANTI-SPAM)
# ==========================================
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ==========================================
# FONDASI DATABASE MULTI-TENANT (SaaS)
# ==========================================
DB_NAME = 'kasir_saas_v1.db' 

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    
    conn.execute('''CREATE TABLE IF NOT EXISTS tenants (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        nama_toko TEXT, is_active INTEGER DEFAULT 1, created_at TEXT)''')

    # Ditambahkan kolom 'nominal' untuk tracking Total Pendapatan
    conn.execute('''CREATE TABLE IF NOT EXISTS donasi_pendaftaran (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        nama TEXT, email TEXT, whatsapp TEXT, kode_donasi TEXT, 
        status TEXT, nominal INTEGER DEFAULT 0, created_at TEXT)''')
    
    # Auto-Migration: Menambahkan kolom nominal jika tabel sudah telanjur ada dari versi sebelumnya
    try:
        conn.execute('ALTER TABLE donasi_pendaftaran ADD COLUMN nominal INTEGER DEFAULT 0')
    except sqlite3.OperationalError:
        pass # Kolom sudah ada

    conn.execute('''CREATE TABLE IF NOT EXISTS produk (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER, 
        sku TEXT, nama TEXT, harga INTEGER, harga_modal INTEGER, 
        kategori TEXT, satuan TEXT, stok INTEGER, stok_min INTEGER, 
        status TEXT, foto TEXT, FOREIGN KEY(tenant_id) REFERENCES tenants(id))''')
        
    conn.execute('CREATE TABLE IF NOT EXISTS transaksi (id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER, tanggal TEXT, total INTEGER)')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS detail_transaksi (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER, transaksi_id INTEGER, produk_id INTEGER, qty INTEGER,
        harga_satuan INTEGER, subtotal INTEGER)''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS pengeluaran (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER,
        nama TEXT, kategori TEXT, nominal INTEGER, tanggal TEXT)''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER, 
        email TEXT UNIQUE, username TEXT UNIQUE, password TEXT, nama TEXT, 
        role TEXT, is_active INTEGER DEFAULT 1)''')
        
    conn.execute('''CREATE TABLE IF NOT EXISTS pengaturan (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id INTEGER, 
        nama_toko TEXT, kontak TEXT, alamat TEXT, footer TEXT, 
        pajak_pb1 INTEGER, service_charge INTEGER, is_tax_included INTEGER, 
        printer TEXT, is_cash_active INTEGER, is_qris_active INTEGER)''')
    
    cur = conn.cursor()
    
    if cur.execute('SELECT COUNT(*) FROM tenants').fetchone()[0] == 0:
        conn.execute('INSERT INTO tenants (nama_toko, created_at) VALUES (?, ?)', ('KasirinAja HQ', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.execute('INSERT INTO users (tenant_id, email, username, password, nama, role) VALUES (?, ?, ?, ?, ?, ?)', 
                     (1, 'admin@kasirinaja.com', 'admin', generate_password_hash('admin123'), 'Super Admin', 'SuperAdmin'))
        conn.execute('''INSERT INTO pengaturan (tenant_id, nama_toko, kontak, alamat, footer, pajak_pb1, service_charge, is_tax_included, printer, is_cash_active, is_qris_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                     (1, 'KasirinAja HQ', '0800-0000-0000', 'Cloud Server', 'Terima kasih!', 0, 0, 0, 'BT-Printer-58mm', 1, 1))

    conn.commit()
    conn.close()

init_db()

# ==========================================
# DEKORATOR KEAMANAN
# ==========================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'SuperAdmin':
            flash('Akses ditolak! Hanya SuperAdmin yang dapat mengakses halaman ini.', 'danger')
            return redirect(url_for('kasir'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# 1. LANDING PAGE & SAAS REGISTRATION
# ==========================================
@app.route('/landing')
def landing():
    return render_template('landing.html')

@app.route('/api/register_donasi', methods=['POST'])
@limiter.limit("5 per hour")
def register_donasi():
    data = request.json
    nama = data.get('nama')
    email = data.get('email')
    whatsapp = data.get('whatsapp')
    kode_donasi = data.get('kode_donasi')
    tanggal = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = get_db_connection()
    if conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone():
        return jsonify({"status": "error", "message": "Email sudah terdaftar di sistem!"}), 400
    if conn.execute('SELECT id FROM donasi_pendaftaran WHERE kode_donasi = ?', (kode_donasi,)).fetchone():
        return jsonify({"status": "error", "message": "Kode bukti donasi tersebut sudah digunakan!"}), 400

    conn.execute('''INSERT INTO donasi_pendaftaran (nama, email, whatsapp, kode_donasi, status, created_at) 
                    VALUES (?, ?, ?, ?, 'pending', ?)''', (nama, email, whatsapp, kode_donasi, tanggal))
    conn.commit()
    conn.close()
    
    return jsonify({"status": "success", "message": "Pendaftaran berhasil! Tunggu verifikasi via WhatsApp/Email."})


# ==========================================
# 2. PANEL SUPERADMIN (PENGELOLAAN KLIEN SAAS)
# ==========================================
def generate_random_password(length=8):
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

@app.route('/admin_saas')
@login_required
@superadmin_required
def admin_saas():
    conn = get_db_connection()
    # Data Antrean (Pending)
    pendaftar = conn.execute('SELECT * FROM donasi_pendaftaran WHERE status = "pending" ORDER BY id DESC').fetchall()
    
    # Data Klien Aktif (Hanya role Owner dan selain Tenant HQ)
    klien_aktif = conn.execute('''
        SELECT t.id as tenant_id, t.nama_toko, t.is_active, t.created_at, u.nama as owner_nama, u.email, u.username, d.nominal 
        FROM tenants t 
        JOIN users u ON t.id = u.tenant_id 
        LEFT JOIN donasi_pendaftaran d ON u.email = d.email
        WHERE u.role = 'Owner' AND t.id != 1
        ORDER BY t.id DESC
    ''').fetchall()
    
    # Hitung Total Pendapatan dari Donasi
    total_pendapatan = conn.execute('SELECT SUM(nominal) FROM donasi_pendaftaran WHERE status = "approved"').fetchone()[0] or 0
    
    conn.close()
    return render_template('admin_saas.html', pendaftar=pendaftar, klien=klien_aktif, total_pendapatan=total_pendapatan)

@app.route('/admin_saas/verifikasi/<int:donasi_id>', methods=['POST'])
@login_required
@superadmin_required
def verifikasi_akun(donasi_id):
    data = request.get_json()
    nominal_masuk = int(data.get('nominal', 0))
    
    conn = get_db_connection()
    donatur = conn.execute('SELECT * FROM donasi_pendaftaran WHERE id = ? AND status = "pending"', (donasi_id,)).fetchone()
    if not donatur: return jsonify({"status": "error", "message": "Data tidak valid atau sudah diproses."}), 400

    try:
        cur = conn.cursor()
        nama_toko = f"Toko {donatur['nama']}"
        cur.execute('INSERT INTO tenants (nama_toko, created_at) VALUES (?, ?)', (nama_toko, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        tenant_id = cur.lastrowid
        
        username = donatur['email'].split('@')[0] + str(random.randint(10, 99))
        password_sementara = generate_random_password()
        
        cur.execute('''INSERT INTO users (tenant_id, email, username, password, nama, role) 
                       VALUES (?, ?, ?, ?, ?, 'Owner')''', 
                    (tenant_id, donatur['email'], username, generate_password_hash(password_sementara), donatur['nama']))
                    
        cur.execute('''INSERT INTO pengaturan (tenant_id, nama_toko, kontak, alamat, footer, pajak_pb1, service_charge, is_tax_included, printer, is_cash_active, is_qris_active)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                    (tenant_id, nama_toko, donatur['whatsapp'], 'Belum diatur', 'Terima Kasih!\nPowered by KasirinAja', 0, 0, 0, 'BT-Printer-58mm', 1, 1))
        
        cur.execute('UPDATE donasi_pendaftaran SET status = "approved", nominal = ? WHERE id = ?', (nominal_masuk, donasi_id))
        conn.commit()
        
        pesan_notif = f"Toko {nama_toko} berhasil dibuat!\nUsername: {username}\nPassword: {password_sementara}"
        return jsonify({"status": "success", "message": pesan_notif})
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()

@app.route('/admin_saas/tolak/<int:donasi_id>', methods=['POST'])
@login_required
@superadmin_required
def tolak_akun(donasi_id):
    conn = get_db_connection()
    conn.execute('UPDATE donasi_pendaftaran SET status = "rejected" WHERE id = ?', (donasi_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "message": "Pengajuan telah ditolak dan dihapus dari antrean."})

@app.route('/admin_saas/toggle_blokir/<int:tenant_id>', methods=['POST'])
@login_required
@superadmin_required
def toggle_blokir(tenant_id):
    if tenant_id == 1: return jsonify({"status": "error", "message": "Tidak dapat memblokir HQ."}), 403
    conn = get_db_connection()
    tenant = conn.execute('SELECT is_active FROM tenants WHERE id = ?', (tenant_id,)).fetchone()
    new_status = 0 if tenant['is_active'] == 1 else 1
    
    # Blokir akses login seluruh user di toko tersebut
    conn.execute('UPDATE tenants SET is_active = ? WHERE id = ?', (new_status, tenant_id))
    conn.execute('UPDATE users SET is_active = ? WHERE tenant_id = ?', (new_status, tenant_id))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "new_status": new_status})

# ==========================================
# OTENTIKASI & SISTEM LOGIN
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if 'user_id' in session: return redirect(url_for('kasir'))
    error = None
    if request.method == 'POST':
        identifier = request.form['username']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? OR email = ?', (identifier, identifier)).fetchone()
        conn.close()
        
        # Validasi ganda: Pastikan user dan tokonya tidak sedang diblokir
        if user and user['is_active'] == 1 and check_password_hash(user['password'], request.form['password']):
            session['user_id'] = user['id']
            session['tenant_id'] = user['tenant_id']
            session['username'] = user['username']
            session['nama'] = user['nama']
            session['role'] = user['role']
            return redirect(url_for('kasir'))
        else:
            error = "Data kredensial salah atau akun/toko Anda telah dinonaktifkan."
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/update_akun', methods=['POST'])
@login_required
def update_akun():
    conn = get_db_connection()
    try:
        conn.execute('UPDATE users SET nama = ?, username = ? WHERE id = ?', (request.form['nama'], request.form['username'], session['user_id']))
        conn.commit()
        session['nama'] = request.form['nama']
        session['username'] = request.form['username']
        flash('Profil berhasil diperbarui!', 'success')
    except sqlite3.IntegrityError: flash('Username sudah digunakan pihak lain!', 'danger')
    conn.close()
    return redirect(request.referrer)

@app.route('/update_password', methods=['POST'])
@login_required
def update_password():
    conn = get_db_connection()
    user = conn.execute('SELECT password FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if check_password_hash(user['password'], request.form['password_lama']):
        conn.execute('UPDATE users SET password = ? WHERE id = ?', (generate_password_hash(request.form['password_baru']), session['user_id']))
        conn.commit()
        flash('Password berhasil diperbarui! Silakan login ulang.', 'success')
        conn.close()
        return redirect(url_for('logout'))
    else:
        flash('Password lama salah!', 'danger')
        conn.close()
        return redirect(request.referrer)

# ==========================================
# CORE POS ROUTES (MULTI-TENANT FILTERED)
# ==========================================
@app.route('/')
@login_required
def kasir():
    conn = get_db_connection()
    produk = conn.execute("SELECT * FROM produk WHERE tenant_id = ? AND status = 'Aktif'", (session['tenant_id'],)).fetchall()
    setting = conn.execute('SELECT is_cash_active, is_qris_active FROM pengaturan WHERE tenant_id = ?', (session['tenant_id'],)).fetchone()
    conn.close()
    return render_template('kasir.html', menu=produk, setting=setting)

@app.route('/produk', methods=['GET', 'POST'])
@login_required
def produk():
    conn = get_db_connection()
    if request.method == 'POST':
        foto_name = "" 
        if request.files.get('foto') and request.files.get('foto').filename != '':
            foto_name = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + request.files.get('foto').filename
            request.files.get('foto').save(os.path.join(app.config['UPLOAD_FOLDER'], foto_name))

        conn.execute('''INSERT INTO produk (tenant_id, sku, nama, harga, harga_modal, kategori, satuan, stok, stok_min, status, foto)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                     (session['tenant_id'], request.form['sku'], request.form['nama'], request.form['harga'], request.form.get('harga_modal') or 0, 
                      request.form['kategori'], request.form['satuan'], request.form['stok'], request.form.get('stok_min') or 0, 
                      'Aktif' if 'status' in request.form else 'Nonaktif', foto_name))
        conn.commit()
        flash('Produk berhasil ditambahkan!', 'success')
        return redirect(url_for('produk'))
    
    semua_produk = conn.execute('SELECT * FROM produk WHERE tenant_id = ? ORDER BY id DESC', (session['tenant_id'],)).fetchall()
    conn.close()
    return render_template('produk.html', menu=semua_produk)

@app.route('/edit_produk/<int:id>', methods=['POST'])
@login_required
def edit_produk(id):
    conn = get_db_connection()
    conn.execute('''UPDATE produk SET nama=?, sku=?, kategori=?, satuan=?, harga=?, stok=? WHERE id=? AND tenant_id=?''', 
                 (request.form['nama'], request.form['sku'], request.form['kategori'], request.form['satuan'], request.form['harga'], request.form['stok'], id, session['tenant_id']))
    conn.commit()
    conn.close()
    flash('Produk berhasil disimpan!', 'success')
    return redirect(url_for('produk'))

@app.route('/hapus_produk/<int:id>', methods=['POST'])
@login_required
def hapus_produk(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM produk WHERE id = ? AND tenant_id = ?', (id, session['tenant_id']))
    conn.commit()
    conn.close()
    flash('Produk berhasil dihapus!', 'success')
    return redirect(url_for('produk'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    tid = session['tenant_id']
    total_pendapatan = conn.execute('SELECT SUM(total) FROM transaksi WHERE tenant_id = ?', (tid,)).fetchone()[0] or 0
    total_trx = conn.execute('SELECT COUNT(id) FROM transaksi WHERE tenant_id = ?', (tid,)).fetchone()[0] or 0
    
    grafik_data = conn.execute('''
        SELECT substr(tanggal, 1, 10) as tgl, SUM(total) as omzet 
        FROM transaksi WHERE tenant_id = ? GROUP BY substr(tanggal, 1, 10) 
        ORDER BY tgl DESC LIMIT 7''', (tid,)).fetchall()
    grafik_data.reverse()
    
    labels = [row['tgl'] for row in grafik_data]
    omzet = [row['omzet'] for row in grafik_data]
    transaksi_terakhir = conn.execute('SELECT * FROM transaksi WHERE tenant_id = ? ORDER BY id DESC LIMIT 10', (tid,)).fetchall()
    conn.close()
    return render_template('dashboard.html', total_pendapatan=total_pendapatan, total_trx=total_trx, labels=labels, omzet=omzet, transaksi=transaksi_terakhir)

@app.route('/laporan')
@login_required
def laporan():
    conn = get_db_connection()
    tid = session['tenant_id']
    transaksi = conn.execute('SELECT * FROM transaksi WHERE tenant_id = ? ORDER BY id DESC', (tid,)).fetchall()
    total_kotor = conn.execute('SELECT SUM(total) FROM transaksi WHERE tenant_id = ?', (tid,)).fetchone()[0] or 0
    total_modal = conn.execute('''SELECT SUM(dt.qty * p.harga_modal) FROM detail_transaksi dt JOIN produk p ON dt.produk_id = p.id WHERE dt.tenant_id = ?''', (tid,)).fetchone()[0] or 0
    total_pengeluaran = conn.execute('SELECT SUM(nominal) FROM pengeluaran WHERE tenant_id = ?', (tid,)).fetchone()[0] or 0
    laba_bersih = total_kotor - total_modal - total_pengeluaran
    riwayat_pengeluaran = conn.execute('SELECT * FROM pengeluaran WHERE tenant_id = ? ORDER BY id DESC', (tid,)).fetchall()
    conn.close()
    return render_template('laporan.html', transaksi=transaksi, total_kotor=total_kotor, total_modal=total_modal, total_pengeluaran=total_pengeluaran, laba_Inter=laba_bersih, pengeluaran=riwayat_pengeluaran)

@app.route('/catat_pengeluaran', methods=['POST'])
@login_required
def catat_pengeluaran():
    conn = get_db_connection()
    conn.execute('INSERT INTO pengeluaran (tenant_id, nama, kategori, nominal, tanggal) VALUES (?, ?, ?, ?, ?)',
                 (session['tenant_id'], request.form['nama'], request.form['kategori'], int(request.form['nominal']), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    flash('Pengeluaran operasional dicatat!', 'success')
    return redirect(url_for('laporan'))

@app.route('/pengaturan')
@login_required
def pengaturan():
    conn = get_db_connection()
    setting = conn.execute('SELECT * FROM pengaturan WHERE tenant_id = ?', (session['tenant_id'],)).fetchone()
    conn.close()
    return render_template('pengaturan.html', setting=setting)

@app.route('/cetak_struk/<int:transaksi_id>')
@login_required
def cetak_struk(transaksi_id):
    conn = get_db_connection()
    transaksi = conn.execute('SELECT * FROM transaksi WHERE id = ? AND tenant_id = ?', (transaksi_id, session['tenant_id'])).fetchone()
    if not transaksi: return "Nota Tidak Ditemukan", 404
    details = conn.execute('SELECT dt.*, p.nama FROM detail_transaksi dt JOIN produk p ON dt.produk_id = p.id WHERE dt.transaksi_id = ? AND dt.tenant_id = ?', (transaksi_id, session['tenant_id'])).fetchall()
    setting = conn.execute('SELECT * FROM pengaturan WHERE tenant_id = ?', (session['tenant_id'],)).fetchone()
    conn.close()
    return render_template('struk.html', transaksi=transaksi, details=details, setting=setting)

# ==========================================
# ASYNCHRONOUS API ENDPOINTS
# ==========================================
@app.route('/bayar', methods=['POST'])
@login_required
def bayar():
    data = request.get_json()
    total = int(data.get('total', 0))
    keranjang = data.get('keranjang', [])
    tid = session['tenant_id']
    if total < 0 or not keranjang: return jsonify({"status": "error", "message": "Data tidak valid!"}), 400
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute('INSERT INTO transaksi (tenant_id, tanggal, total) VALUES (?, ?, ?)', (tid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), total))
        transaksi_id = cur.lastrowid
        for item in keranjang:
            qty, harga = int(item['qty']), int(item['harga'])
            if cur.execute('SELECT stok FROM produk WHERE id = ? AND tenant_id = ?', (item['id'], tid)).fetchone()['stok'] < qty: raise ValueError(f"Stok {item['nama']} kurang!")
            cur.execute('INSERT INTO detail_transaksi (tenant_id, transaksi_id, produk_id, qty, harga_satuan, subtotal) VALUES (?, ?, ?, ?, ?, ?)', (tid, transaksi_id, item['id'], qty, harga, qty * harga))
            cur.execute('UPDATE produk SET stok = stok - ? WHERE id = ? AND tenant_id = ?', (qty, item['id'], tid))
        conn.commit()
        return jsonify({"status": "success", "transaksi_id": transaksi_id})
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally: conn.close()

@app.route('/sync_offline', methods=['POST'])
@login_required
def sync_offline():
    data = request.get_json()
    tid = session['tenant_id']
    if not data.get('transactions', []): return jsonify({"status": "success"})
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        for trx in data.get('transactions', []):
            cur.execute('INSERT INTO transaksi (tenant_id, tanggal, total) VALUES (?, ?, ?)', (tid, trx.get('tanggal') or datetime.now().strftime("%Y-%m-%d %H:%M:%S"), int(trx.get('total', 0))))
            transaksi_id = cur.lastrowid
            for item in trx.get('keranjang', []):
                qty, harga = int(item['qty']), int(item['harga'])
                cur.execute('INSERT INTO detail_transaksi (tenant_id, transaksi_id, produk_id, qty, harga_satuan, subtotal) VALUES (?, ?, ?, ?, ?, ?)', (tid, transaksi_id, item['id'], qty, harga, qty * harga))
                cur.execute('UPDATE produk SET stok = stok - ? WHERE id = ? AND tenant_id = ?', (qty, item['id'], tid))
        conn.commit()
        return jsonify({"status": "success", "synced_count": len(data.get('transactions', []))})
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error"}), 500
    finally: conn.close()

@app.route('/api/pengaturan', methods=['POST'])
@login_required
def api_pengaturan():
    data = request.get_json()
    conn = get_db_connection()
    conn.execute('''UPDATE pengaturan SET nama_toko=?, kontak=?, alamat=?, footer=?, pajak_pb1=?, service_charge=?, is_tax_included=?, printer=?, is_cash_active=?, is_qris_active=? WHERE tenant_id=?''',
        (data['nama_toko'], data['kontak'], data['alamat'], data['footer'], data['pajak_pb1'], data['service_charge'], data['is_tax_included'], data['printer'], data['is_cash_active'], data['is_qris_active'], session['tenant_id']))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)