let keranjang = [];
let tipePesanan = "Makan Sini";
let totalTagihanGlobal = 0;
let uangDiterimaGlobal = 0;

// --- FITUR PENCARIAN & FILTER ---
function cariMenu() {
    let input = document.getElementById('inputPencarian').value.toLowerCase();
    let menuItems = document.querySelectorAll('.item-menu');
    menuItems.forEach(item => {
        let namaMenu = item.getAttribute('data-nama');
        if (namaMenu.includes(input)) {
            item.classList.remove('d-none');
        } else {
            item.classList.add('d-none');
        }
    });
}

function filterKategori(kategori) {
    let menuItems = document.querySelectorAll('.item-menu');
    menuItems.forEach(item => {
        let katMenu = item.getAttribute('data-kategori');
        if (kategori === 'Semua' || katMenu === kategori) {
            item.classList.remove('d-none');
        } else {
            item.classList.add('d-none');
        }
    });
}

// --- LOGIKA KERANJANG ---
function sinkronisasiTipePesanan(nilai) {
    tipePesanan = nilai;
    // Sinkronkan radio button HP dan Desktop
    if(document.getElementById('dineInDesk')) document.getElementById(nilai === 'Makan Sini' ? 'dineInDesk' : 'takeawayDesk').checked = true;
    if(document.getElementById('dineInMob')) document.getElementById(nilai === 'Makan Sini' ? 'dineInMob' : 'takeawayMob').checked = true;
}

function kosongkanKeranjang() {
    if (keranjang.length > 0 && confirm("Yakin ingin mengosongkan semua pesanan?")) {
        keranjang = [];
        renderKeranjang();
    }
}

function tambahKeKeranjang(id, nama, harga) {
    let itemSama = keranjang.find(item => item.id === id);
    if (itemSama) { itemSama.qty += 1; } 
    else { keranjang.push({ id: id, nama: nama, harga: harga, qty: 1 }); }
    renderKeranjang();
}

function kurangiDariKeranjang(id) {
    let itemIndex = keranjang.findIndex(item => item.id === id);
    if (itemIndex !== -1) {
        keranjang[itemIndex].qty -= 1;
        if (keranjang[itemIndex].qty === 0) keranjang.splice(itemIndex, 1);
    }
    renderKeranjang();
}

function renderKeranjang() {
    const areaDesktop = document.getElementById('area-keranjang-desktop');
    const areaMobile = document.getElementById('area-keranjang-mobile');
    const totalDesktop = document.getElementById('total-harga-desktop');
    const totalMobile = document.getElementById('total-harga-mobile');
    const fabBadge = document.getElementById('fab-badge');

    let totalQty = keranjang.reduce((sum, item) => sum + item.qty, 0);
    if(fabBadge) fabBadge.innerText = totalQty;

    if (keranjang.length === 0) {
        totalTagihanGlobal = 0;
        const emptyStateHTML = `
            <div class="h-100 d-flex flex-column justify-content-center align-items-center opacity-50 py-5">
                <i class="bi bi-cart-x text-secondary mb-3" style="font-size: 4rem;"></i>
                <h5 class="fw-bold text-dark mb-1">Belum ada pesanan</h5>
                <p class="text-muted text-center small px-4">Klik/sentuh menu ayam atau minuman untuk memulai.</p>
            </div>
        `;
        if(areaDesktop) areaDesktop.innerHTML = emptyStateHTML;
        if(areaMobile) areaMobile.innerHTML = emptyStateHTML;
        if(totalDesktop) totalDesktop.innerText = 'Rp 0';
        if(totalMobile) totalMobile.innerText = 'Rp 0';
        return;
    }

    let htmlKeranjang = '<div class="d-flex flex-column gap-2 pb-3">';
    totalTagihanGlobal = 0;

    keranjang.forEach((item) => {
        let subtotal = item.harga * item.qty;
        totalTagihanGlobal += subtotal;
        
        htmlKeranjang += `
            <div class="bg-white p-3 rounded-4 shadow-sm border border-light">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <h6 class="mb-0 fw-bold text-dark w-75 lh-sm pe-2">${item.nama}</h6>
                    <span class="fw-bold text-danger">Rp ${subtotal.toLocaleString('id-ID')}</span>
                </div>
                <div class="d-flex justify-content-between align-items-center mt-2">
                    <small class="text-muted">Rp ${item.harga.toLocaleString('id-ID')}</small>
                    <div class="d-flex align-items-center gap-2">
                        <div class="btn-touch cursor-pointer" onclick="kurangiDariKeranjang(${item.id})"><i class="bi bi-dash"></i></div>
                        <h6 class="mb-0 fw-bold px-2">${item.qty}</h6>
                        <div class="btn-touch cursor-pointer" onclick="tambahKeKeranjang(${item.id}, '${item.nama}', ${item.harga})"><i class="bi bi-plus"></i></div>
                    </div>
                </div>
            </div>
        `;
    });
    htmlKeranjang += '</div>';

    if(areaDesktop) areaDesktop.innerHTML = htmlKeranjang;
    if(areaMobile) areaMobile.innerHTML = htmlKeranjang;
    
    const formattedTotal = 'Rp ' + totalTagihanGlobal.toLocaleString('id-ID');
    if(totalDesktop) totalDesktop.innerText = formattedTotal;
    if(totalMobile) totalMobile.innerText = formattedTotal;
}

// --- LOGIKA MODAL PEMBAYARAN (NUMPAD & KEMBALIAN) ---
let modalBayarInstance;

function bukaModalPembayaran() {
    if (keranjang.length === 0) {
        alert("Keranjang masih kosong!");
        return;
    }
    
    // Tutup Bottom Sheet HP jika terbuka
    const cartOffcanvasEl = document.getElementById('cartOffcanvas');
    if(cartOffcanvasEl) {
        const offcanvasInstance = bootstrap.Offcanvas.getInstance(cartOffcanvasEl);
        if(offcanvasInstance) offcanvasInstance.hide();
    }

    // Persiapkan UI Modal
    document.getElementById('modal-total-tagihan').innerText = 'Rp ' + totalTagihanGlobal.toLocaleString('id-ID');
    document.getElementById('modal-tipe-pesanan').innerText = tipePesanan;
    
    // Reset kalkulasi tunai
    uangDiterimaGlobal = 0;
    updateLayarKalkulator();
    
    // Tampilkan Modal
    if (!modalBayarInstance) modalBayarInstance = new bootstrap.Modal(document.getElementById('modalPembayaran'));
    modalBayarInstance.show();
}

function toggleMetodeBayar() {
    const isTunai = document.getElementById('bayarTunai').checked;
    const panelNumpad = document.getElementById('panelNumpad');
    const panelKalkulasi = document.getElementById('panelKalkulasi');
    const panelQris = document.getElementById('panelQris');

    if(isTunai) {
        panelNumpad.classList.remove('d-none');
        panelKalkulasi.classList.remove('d-none');
        panelQris.classList.add('d-none');
        panelQris.classList.remove('d-flex');
    } else {
        panelNumpad.classList.add('d-none');
        panelKalkulasi.classList.add('d-none');
        panelQris.classList.remove('d-none');
        panelQris.classList.add('d-flex');
        uangDiterimaGlobal = totalTagihanGlobal; // Jika QRIS, otomatis uang pas
    }
}

// Logika Numpad
function tekanNumpad(angka) {
    if (uangDiterimaGlobal === 0) {
        uangDiterimaGlobal = parseInt(angka.toString());
    } else {
        uangDiterimaGlobal = parseInt(uangDiterimaGlobal.toString() + angka.toString());
    }
    updateLayarKalkulator();
}

function hapusNumpad() {
    uangDiterimaGlobal = 0;
    updateLayarKalkulator();
}

function tambahUangDiterima(nominal) {
    uangDiterimaGlobal += nominal;
    updateLayarKalkulator();
}

function setUangPas() {
    uangDiterimaGlobal = totalTagihanGlobal;
    updateLayarKalkulator();
}

function updateLayarKalkulator() {
    const displayUang = document.getElementById('displayUangDiterima');
    const displayKembalian = document.getElementById('displayKembalian');
    
    displayUang.innerText = 'Rp ' + uangDiterimaGlobal.toLocaleString('id-ID');
    
    let kembalian = uangDiterimaGlobal - totalTagihanGlobal;
    if (kembalian < 0) {
        displayKembalian.innerText = "Kurang Rp " + Math.abs(kembalian).toLocaleString('id-ID');
        displayKembalian.classList.replace('text-success', 'text-danger');
    } else {
        displayKembalian.innerText = 'Rp ' + kembalian.toLocaleString('id-ID');
        displayKembalian.classList.replace('text-danger', 'text-success');
    }
}

function eksekusiPembayaranFinal() {
    const isTunai = document.getElementById('bayarTunai').checked;
    
    if (isTunai && uangDiterimaGlobal < totalTagihanGlobal) {
        alert("Uang tunai yang diterima kurang dari total tagihan!");
        return;
    }

    // Kirim data ke Backend Python (bisa dikembangkan kirim tipePesanan dll)
    fetch('/bayar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ total: totalTagihanGlobal })
    })
    .then(response => response.json())
    .then(data => {
        alert("Pembayaran Berhasil! Struk siap dicetak.\nKembalian: Rp " + (isTunai ? (uangDiterimaGlobal - totalTagihanGlobal).toLocaleString('id-ID') : 0));
        modalBayarInstance.hide();
        keranjang = []; 
        renderKeranjang();
    })
    .catch(error => console.error('Error:', error));
}

document.addEventListener("DOMContentLoaded", renderKeranjang);