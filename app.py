import os
import string
import random
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import psycopg2
from psycopg2.extras import DictCursor

# Load dotenv untuk environment lokal VS Code
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)
app.secret_key = 'kasirinaja_saas_super_secret_2026' 

limiter = Limiter(
    get_remote_address, app=app, default_limits=["200 per day", "50 per hour"], storage_uri="memory://"
)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

try:
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
except OSError:
    pass 

# ==========================================
# KONEKSI DATABASE POSTGRESQL (NEON.TECH)
# ==========================================
def get_db_connection():
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL belum disetel di Vercel!")
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    cur.execute('''CREATE TABLE IF NOT EXISTS tenants (
        id SERIAL PRIMARY KEY, nama_toko TEXT, is_active INTEGER DEFAULT 1, created_at TEXT)''')

    cur.execute('''CREATE TABLE IF NOT EXISTS donasi_pendaftaran (
        id SERIAL PRIMARY KEY, nama TEXT, email TEXT, whatsapp TEXT, kode_donasi TEXT, 
        status TEXT, nominal INTEGER DEFAULT 0, created_at TEXT)''')

    cur.execute('''CREATE TABLE IF NOT EXISTS produk (
        id SERIAL PRIMARY KEY, tenant_id INTEGER, sku TEXT, nama TEXT, harga INTEGER, harga_modal INTEGER, 
        kategori TEXT, satuan TEXT, stok INTEGER, stok_min INTEGER, status TEXT, foto TEXT, 
        FOREIGN KEY(tenant_id) REFERENCES tenants(id))''')
        
    cur.execute('CREATE TABLE IF NOT EXISTS transaksi (id SERIAL PRIMARY KEY, tenant_id INTEGER, tanggal TEXT, total INTEGER)')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS detail_transaksi (
        id SERIAL PRIMARY KEY, tenant_id INTEGER, transaksi_id INTEGER, produk_id INTEGER, qty INTEGER,
        harga_satuan INTEGER, subtotal INTEGER)''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS pengeluaran (
        id SERIAL PRIMARY KEY, tenant_id INTEGER, nama TEXT, kategori TEXT, nominal INTEGER, tanggal TEXT)''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY, tenant_id INTEGER, email TEXT UNIQUE, username TEXT UNIQUE, password TEXT, 
        nama TEXT, role TEXT, is_active INTEGER DEFAULT 1)''')
        
    cur.execute('''CREATE TABLE IF NOT EXISTS pengaturan (
        id SERIAL PRIMARY KEY, tenant_id INTEGER, nama_toko TEXT, kontak TEXT, alamat TEXT, footer TEXT, 
        pajak_pb1 INTEGER, service_charge INTEGER, is_tax_included INTEGER, printer TEXT, is_cash_active INTEGER, is_qris_active INTEGER)''')
    
    cur.execute('SELECT COUNT(*) FROM tenants')
    if cur.fetchone()[0] == 0:
        cur.execute('INSERT INTO tenants (nama_toko, created_at) VALUES (%s, %s)', ('KasirinAja HQ', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        cur.execute('INSERT INTO users (tenant_id, email, username, password, nama, role) VALUES (%s, %s, %s, %s, %s, %s)', 
                     (1, 'admin@kasirinaja.com', 'admin', generate_password_hash('admin123'), 'Super Admin', 'SuperAdmin'))
        cur.execute('''INSERT INTO pengaturan (tenant_id, nama_toko, kontak, alamat, footer, pajak_pb1, service_charge, is_tax_included, printer, is_cash_active, is_qris_active)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''', 
                     (1, 'KasirinAja HQ', '0800-0000-0000', 'Cloud Server', 'Terima kasih!', 0, 0, 0, 'BT-Printer-58mm', 1, 1))

    conn.commit() # Simpan tabel utama
    
    # -------------------------------------------------------------
    # SISTEM AUTO-PATCHING (MIGRASI DATABASE LAMA KE BARU)
    # Menyuntikkan kolom baru jika database sebelumnya sudah ada
    # -------------------------------------------------------------
    kolom_tambahan = [
        ("pengaturan", "printer", "TEXT DEFAULT 'BT-Printer-58mm'"),
        ("pengaturan", "is_cash_active", "INTEGER DEFAULT 1"),
        ("pengaturan", "is_qris_active", "INTEGER DEFAULT 1"),
        ("pengaturan", "is_tax_included", "INTEGER DEFAULT 0")
    ]
    
    for tabel, kolom, tipe in kolom_tambahan:
        try:
            cur.execute(f"ALTER TABLE {tabel} ADD COLUMN {kolom} {tipe}")
            conn.commit()
        except psycopg2.Error:
            conn.rollback() # Abaikan dengan damai jika kolom sudah ada
            
    cur.close()
    conn.close()

# ==========================================
# DEKORATOR & FUNGSI BANTU
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
            flash('Akses ditolak!', 'danger')
            return redirect(url_for('kasir'))
        return f(*args, **kwargs)
    return decorated_function

def generate_random_password(length=8):
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

# ==========================================
# RUTE INSTALASI / PEMBARUAN (KHUSUS VERCEL)
# ==========================================
@app.route('/setup')
def setup():
    try:
        init_db()
        return "<h1>✅ DATABASE BERHASIL DIPERBARUI!</h1><p>Kolom baru telah disuntikkan ke Neon.tech. Silakan kembali ke aplikasi Anda.</p>"
    except Exception as e:
        return f"<h1>❌ GAGAL MEMPERBARUI DATABASE:</h1><p>Error Detail: {str(e)}</p>"

# ==========================================
# RUTE APLIKASI SAAS
# ==========================================
@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/api/register_donasi', methods=['POST'])
@limiter.limit("5 per hour")
def register_donasi():
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute('SELECT id FROM users WHERE email = %s', (data.get('email'),))
    if cur.fetchone(): return jsonify({"status": "error", "message": "Email sudah terdaftar!"}), 400
    cur.execute('SELECT id FROM donasi_pendaftaran WHERE kode_donasi = %s', (data.get('kode_donasi'),))
    if cur.fetchone(): return jsonify({"status": "error", "message": "Kode bukti sudah digunakan!"}), 400

    cur.execute('''INSERT INTO donasi_pendaftaran (nama, email, whatsapp, kode_donasi, status, created_at) 
                   VALUES (%s, %s, %s, %s, 'pending', %s)''', 
                (data.get('nama'), data.get('email'), data.get('whatsapp'), data.get('kode_donasi'), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"status": "success", "message": "Pendaftaran berhasil! Tunggu verifikasi admin."})

@app.route('/admin_saas')
@login_required
@superadmin_required
def admin_saas():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM donasi_pendaftaran WHERE status = 'pending' ORDER BY id DESC")
    pendaftar = cur.fetchall()
    
    cur.execute('''SELECT t.id as tenant_id, t.nama_toko, t.is_active, t.created_at, u.nama as owner_nama, u.email, u.username, d.nominal 
        FROM tenants t JOIN users u ON t.id = u.tenant_id 
        LEFT JOIN donasi_pendaftaran d ON u.email = d.email
        WHERE u.role = 'Owner' AND t.id != 1 ORDER BY t.id DESC''')
    klien_aktif = cur.fetchall()
    
    cur.execute("SELECT SUM(nominal) as total FROM donasi_pendaftaran WHERE status = 'approved'")
    total_pendapatan = cur.fetchone()['total'] or 0
    cur.close(); conn.close()
    return render_template('admin_saas.html', pendaftar=pendaftar, klien=klien_aktif, total_pendapatan=total_pendapatan)

@app.route('/admin_saas/verifikasi/<int:donasi_id>', methods=['POST'])
@login_required
@superadmin_required
def verifikasi_akun(donasi_id):
    nominal_masuk = int(request.get_json().get('nominal', 0))
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM donasi_pendaftaran WHERE id = %s AND status = 'pending'", (donasi_id,))
    donatur = cur.fetchone()
    if not donatur: return jsonify({"status": "error", "message": "Data tidak valid."}), 400

    try:
        nama_toko = f"Toko {donatur['nama']}"
        cur.execute('INSERT INTO tenants (nama_toko, created_at) VALUES (%s, %s) RETURNING id', (nama_toko, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        tenant_id = cur.fetchone()['id']
        username = donatur['email'].split('@')[0] + str(random.randint(10, 99))
        password_sementara = generate_random_password()
        
        cur.execute('''INSERT INTO users (tenant_id, email, username, password, nama, role) VALUES (%s, %s, %s, %s, %s, 'Owner')''', 
                    (tenant_id, donatur['email'], username, generate_password_hash(password_sementara), donatur['nama']))
        cur.execute('''INSERT INTO pengaturan (tenant_id, nama_toko, kontak, alamat, footer, pajak_pb1, service_charge, is_tax_included, printer, is_cash_active, is_qris_active)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''', 
                    (tenant_id, nama_toko, donatur['whatsapp'], 'Belum diatur', 'Terima Kasih!\nPowered by KasirinAja', 0, 0, 0, 'BT-Printer-58mm', 1, 1))
        
        cur.execute("UPDATE donasi_pendaftaran SET status = 'approved', nominal = %s WHERE id = %s", (nominal_masuk, donasi_id))
        conn.commit()
        return jsonify({"status": "success", "message": f"Toko berhasil dibuat!\nUsername: {username}\nPassword: {password_sementara}"})
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally: cur.close(); conn.close()

@app.route('/admin_saas/tolak/<int:donasi_id>', methods=['POST'])
@login_required
@superadmin_required
def tolak_akun(donasi_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE donasi_pendaftaran SET status = 'rejected' WHERE id = %s", (donasi_id,))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"status": "success"})

@app.route('/admin_saas/toggle_blokir/<int:tenant_id>', methods=['POST'])
@login_required
@superadmin_required
def toggle_blokir(tenant_id):
    if tenant_id == 1: return jsonify({"status": "error", "message": "HQ tidak bisa diblokir."}), 403
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute('SELECT is_active FROM tenants WHERE id = %s', (tenant_id,))
    new_status = 0 if cur.fetchone()['is_active'] == 1 else 1
    cur.execute('UPDATE tenants SET is_active = %s WHERE id = %s', (new_status, tenant_id))
    cur.execute('UPDATE users SET is_active = %s WHERE tenant_id = %s', (new_status, tenant_id))
    conn.commit()
    cur.close(); conn.close()
    return jsonify({"status": "success", "new_status": new_status})

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if 'user_id' in session: return redirect(url_for('kasir'))
    error = None
    if request.method == 'POST':
        identifier = request.form['username']
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=DictCursor)
            cur.execute('SELECT * FROM users WHERE username = %s OR email = %s', (identifier, identifier))
            user = cur.fetchone()
            cur.close(); conn.close()
            
            if user and user['is_active'] == 1 and check_password_hash(user['password'], request.form['password']):
                session['user_id'], session['tenant_id'] = user['id'], user['tenant_id']
                session['username'], session['nama'], session['role'] = user['username'], user['nama'], user['role']
                return redirect(url_for('kasir'))
            else: error = "Kredensial salah atau toko diblokir."
        except Exception as e:
            error = f"Error Database. Apakah Anda sudah menjalankan /setup? ({e})"
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))

@app.route('/pos')
@login_required
def kasir():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM produk WHERE tenant_id = %s AND status = 'Aktif'", (session['tenant_id'],))
    produk = cur.fetchall()
    
    cur.execute('SELECT * FROM pengaturan WHERE tenant_id = %s', (session['tenant_id'],))
    setting = cur.fetchone()
    
    cur.close(); conn.close()
    return render_template('kasir.html', menu=produk, setting=setting)

@app.route('/produk', methods=['GET', 'POST'])
@login_required
def produk():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    if request.method == 'POST':
        foto_name = "" 
        cur.execute('''INSERT INTO produk (tenant_id, sku, nama, harga, harga_modal, kategori, satuan, stok, stok_min, status, foto)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''', 
                    (session['tenant_id'], request.form['sku'], request.form['nama'], request.form['harga'], request.form.get('harga_modal') or 0, 
                     request.form['kategori'], request.form['satuan'], request.form['stok'], request.form.get('stok_min') or 0, 
                     'Aktif' if 'status' in request.form else 'Nonaktif', foto_name))
        conn.commit(); flash('Produk ditambahkan!', 'success'); return redirect(url_for('produk'))
    
    cur.execute('SELECT * FROM produk WHERE tenant_id = %s ORDER BY id DESC', (session['tenant_id'],))
    semua_produk = cur.fetchall()
    cur.close(); conn.close()
    return render_template('produk.html', menu=semua_produk)

@app.route('/edit_produk/<int:id>', methods=['POST'])
@login_required
def edit_produk(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''UPDATE produk SET nama=%s, sku=%s, kategori=%s, satuan=%s, harga=%s, stok=%s WHERE id=%s AND tenant_id=%s''', 
                 (request.form['nama'], request.form['sku'], request.form['kategori'], request.form['satuan'], request.form['harga'], request.form['stok'], id, session['tenant_id']))
    conn.commit(); cur.close(); conn.close(); flash('Produk disimpan!', 'success'); return redirect(url_for('produk'))

@app.route('/hapus_produk/<int:id>', methods=['POST'])
@login_required
def hapus_produk(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM produk WHERE id = %s AND tenant_id = %s', (id, session['tenant_id']))
    conn.commit(); cur.close(); conn.close(); flash('Produk dihapus!', 'success'); return redirect(url_for('produk'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    tid = session['tenant_id']
    cur.execute('SELECT SUM(total) as tot FROM transaksi WHERE tenant_id = %s', (tid,))
    total_pendapatan = cur.fetchone()['tot'] or 0
    cur.execute('SELECT COUNT(id) as c FROM transaksi WHERE tenant_id = %s', (tid,))
    total_trx = cur.fetchone()['c'] or 0
    
    cur.execute('''SELECT SUBSTRING(tanggal, 1, 10) as tgl, SUM(total) as omzet 
                   FROM transaksi WHERE tenant_id = %s GROUP BY SUBSTRING(tanggal, 1, 10) 
                   ORDER BY tgl DESC LIMIT 7''', (tid,))
    grafik_data = cur.fetchall(); grafik_data.reverse()
    labels = [row['tgl'] for row in grafik_data]
    omzet = [row['omzet'] for row in grafik_data]
    
    cur.execute('SELECT * FROM transaksi WHERE tenant_id = %s ORDER BY id DESC LIMIT 10', (tid,))
    transaksi_terakhir = cur.fetchall()
    cur.close(); conn.close()
    return render_template('dashboard.html', total_pendapatan=total_pendapatan, total_trx=total_trx, labels=labels, omzet=omzet, transaksi=transaksi_terakhir)

@app.route('/laporan')
@login_required
def laporan():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    tid = session['tenant_id']
    cur.execute('SELECT * FROM transaksi WHERE tenant_id = %s ORDER BY id DESC', (tid,))
    transaksi = cur.fetchall()
    cur.execute('SELECT SUM(total) as tot FROM transaksi WHERE tenant_id = %s', (tid,))
    total_kotor = cur.fetchone()['tot'] or 0
    cur.execute('''SELECT SUM(dt.qty * p.harga_modal) as modal FROM detail_transaksi dt 
                   JOIN produk p ON dt.produk_id = p.id WHERE dt.tenant_id = %s''', (tid,))
    total_modal = cur.fetchone()['modal'] or 0
    cur.execute('SELECT SUM(nominal) as png FROM pengeluaran WHERE tenant_id = %s', (tid,))
    total_pengeluaran = cur.fetchone()['png'] or 0
    laba_bersih = total_kotor - total_modal - total_pengeluaran
    cur.execute('SELECT * FROM pengeluaran WHERE tenant_id = %s ORDER BY id DESC', (tid,))
    riwayat_pengeluaran = cur.fetchall()
    cur.close(); conn.close()
    return render_template('laporan.html', transaksi=transaksi, total_kotor=total_kotor, total_modal=total_modal, total_pengeluaran=total_pengeluaran, laba_Inter=laba_bersih, pengeluaran=riwayat_pengeluaran)

@app.route('/catat_pengeluaran', methods=['POST'])
@login_required
def catat_pengeluaran():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO pengeluaran (tenant_id, nama, kategori, nominal, tanggal) VALUES (%s, %s, %s, %s, %s)',
                 (session['tenant_id'], request.form['nama'], request.form['kategori'], int(request.form['nominal']), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit(); cur.close(); conn.close()
    flash('Pengeluaran dicatat!', 'success'); return redirect(url_for('laporan'))

@app.route('/pengaturan')
@login_required
def pengaturan():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute('SELECT * FROM pengaturan WHERE tenant_id = %s', (session['tenant_id'],))
    setting = cur.fetchone()    
    cur.close(); conn.close()
    return render_template('pengaturan.html', setting=setting)

@app.route('/api/pengaturan', methods=['POST'])
@login_required
def api_pengaturan():
    try:
        data = request.get_json()
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''UPDATE pengaturan 
                       SET nama_toko=%s, kontak=%s, alamat=%s, footer=%s, 
                           pajak_pb1=%s, service_charge=%s, is_tax_included=%s, 
                           printer=%s, is_cash_active=%s, is_qris_active=%s 
                       WHERE tenant_id=%s''', 
                    (data.get('nama_toko'), data.get('kontak'), data.get('alamat'), data.get('footer'),
                     data.get('pajak_pb1'), data.get('service_charge'), data.get('is_tax_included'),
                     data.get('printer'), data.get('is_cash_active'), data.get('is_qris_active'), session['tenant_id']))
        
        cur.execute('UPDATE tenants SET nama_toko=%s WHERE id=%s', (data.get('nama_toko'), session['tenant_id']))
        conn.commit()
        return jsonify({"status": "success", "message": "Pengaturan disimpan"}), 200
    except Exception as e:
        if 'conn' in locals() and conn:
            conn.rollback()
        print(f"🔥 ERROR SIMPAN PENGATURAN: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        if 'cur' in locals() and cur: cur.close()
        if 'conn' in locals() and conn: conn.close()

@app.route('/api/settings/change-password', methods=['POST'])
@login_required
def api_change_password():
    data = request.get_json()
    old_password = data.get('oldPassword')
    new_password = data.get('newPassword')

    if not old_password or not new_password or len(new_password) < 6:
        return jsonify({"status": "error", "message": "Password baru harus minimal 6 karakter!"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute('SELECT password FROM users WHERE id = %s', (session['user_id'],))
        user = cur.fetchone()
        
        if not user or not check_password_hash(user['password'], old_password):
            return jsonify({"status": "error", "message": "Password lama yang Anda masukkan salah!"}), 401
            
        hashed_new_password = generate_password_hash(new_password)
        cur.execute('UPDATE users SET password = %s WHERE id = %s', (hashed_new_password, session['user_id']))
        conn.commit()
        
        return jsonify({"status": "success", "message": "Keamanan diperbarui! Sandi berhasil diganti."}), 200
        
    except Exception as e:
        if 'conn' in locals() and conn: conn.rollback()
        print(f"🔥 ERROR GANTI PASSWORD: {str(e)}")
        return jsonify({"status": "error", "message": f"Sistem Error: {str(e)}"}), 500
    finally:
        if 'cur' in locals() and cur: cur.close()
        if 'conn' in locals() and conn: conn.close()

@app.route('/bayar', methods=['POST'])
@login_required
def bayar():
    data = request.get_json()
    total = int(data.get('total', 0))
    keranjang = data.get('keranjang', [])
    tid = session['tenant_id']
    if total < 0 or not keranjang: return jsonify({"status": "error", "message": "Data tidak valid!"}), 400
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=DictCursor)
        cur.execute('INSERT INTO transaksi (tenant_id, tanggal, total) VALUES (%s, %s, %s) RETURNING id', 
                    (tid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), total))
        transaksi_id = cur.fetchone()['id']
        for item in keranjang:
            qty, harga = int(item['qty']), int(item['harga'])
            cur.execute('SELECT stok FROM produk WHERE id = %s AND tenant_id = %s', (item['id'], tid))
            if cur.fetchone()['stok'] < qty: raise ValueError(f"Stok {item['nama']} kurang!")
            cur.execute('INSERT INTO detail_transaksi (tenant_id, transaksi_id, produk_id, qty, harga_satuan, subtotal) VALUES (%s, %s, %s, %s, %s, %s)', 
                        (tid, transaksi_id, item['id'], qty, harga, qty * harga))
            cur.execute('UPDATE produk SET stok = stok - %s WHERE id = %s AND tenant_id = %s', (qty, item['id'], tid))
        conn.commit()
        return jsonify({"status": "success", "transaksi_id": transaksi_id})
    except Exception as e:
        if 'conn' in locals() and conn: conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
    finally: 
        if 'cur' in locals() and cur: cur.close()
        if 'conn' in locals() and conn: conn.close()

# ==========================================
# RUTE BARU: GENERATOR STRUK HTML (Mode PDF)
# ==========================================
@app.route('/cetak_struk/<int:trx_id>')
@login_required
def cetak_struk(trx_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    cur.execute('SELECT * FROM transaksi WHERE id = %s AND tenant_id = %s', (trx_id, session['tenant_id']))
    trx = cur.fetchone()
    
    if not trx:
        cur.close(); conn.close()
        return "<h1>Transaksi tidak ditemukan</h1>", 404
        
    cur.execute('''SELECT dt.*, p.nama FROM detail_transaksi dt 
                   JOIN produk p ON dt.produk_id = p.id 
                   WHERE dt.transaksi_id = %s''', (trx_id,))
    items = cur.fetchall()
    
    cur.execute('SELECT * FROM pengaturan WHERE tenant_id = %s', (session['tenant_id'],))
    setting = cur.fetchone()
    cur.close(); conn.close()
    
    nama_toko = setting['nama_toko'].upper() if setting and setting['nama_toko'] else 'KASIRINAJA'
    alamat = setting['alamat'] if setting and setting['alamat'] else ''
    kontak = setting['kontak'] if setting and setting['kontak'] else ''
    footer = setting['footer'] if setting and setting['footer'] else 'TERIMA KASIH'
    
    html_items = ""
    for item in items:
        html_items += f"""
        <div class="item">
            <div>{item['qty']}x {item['nama']}<br><small>@ Rp {item['harga_satuan']:,}</small></div>
            <div>Rp {item['subtotal']:,}</div>
        </div>
        """
    
    html_struk = f"""
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Cetak Struk #{trx_id}</title>
        <style>
            body {{ font-family: 'Courier New', Courier, monospace; color: #000; text-align: center; width: 100%; max-width: 300px; margin: 0 auto; padding: 20px; font-size: 12px; }}
            .garis {{ border-bottom: 1px dashed #000; margin: 10px 0; }}
            .item {{ display: flex; justify-content: space-between; text-align: left; margin-bottom: 5px; }}
            .tebal {{ font-weight: bold; font-size: 14px; }}
            @media print {{ body {{ padding: 0; margin: 0; width: 100%; }} @page {{ margin: 0; }} }}
        </style>
    </head>
    <body onload="window.print()">
        <h3 style="margin:0;">{nama_toko}</h3>
        <p style="margin:5px 0;">{alamat}</p>
        <p style="margin:5px 0;">Telp/WA: {kontak}</p>
        <div class="garis"></div>
        <div style="text-align: left;">
            Tanggal : {trx['tanggal']}<br>Nota ID : #{trx_id}
        </div>
        <div class="garis"></div>
        {html_items}
        <div class="garis"></div>
        <div class="item tebal">
            <div>TOTAL</div><div>Rp {trx['total']:,}</div>
        </div>
        <div class="garis"></div>
        <p style="white-space: pre-wrap;">{footer}</p>
    </body>
    </html>
    """
    return html_struk

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)