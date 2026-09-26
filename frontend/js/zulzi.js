// ---------------------------------------------------------------------
// Zulzi station-hub commerce (frontend client).
//
// Lets a rider pre-order local goods (padstols, refreshments, essentials)
// from station-side vendors and have them delivered to the train carriage
// when the train pulls into that station stop.
//
// Adapter pattern: the live Zulzi partner API is reached at
// window.ZULZI_API_BASE (set in the deployed environment). When that is not
// configured — the hackathon default — the backend falls back to its mock
// catalog, so carriage commerce works with zero partner credentials. The
// client only ever talks to the Kasi Compass backend; the backend owns the
// adapter boundary, never the browser.
// ---------------------------------------------------------------------

const ZULZI_BASE = window.ZULZI_API_BASE || null;

const ORDER_LIFECYCLE_LABELS = {
    placed: 'Order received',
    confirmed: 'Confirmed by Zulzi',
    preparing: 'Vendor preparing',
    out_for_delivery: 'Out for delivery to platform',
    delivering_to_carriage: 'At the station — heading to your carriage',
    delivered_to_carriage: 'Delivered to carriage',
    received: 'Received by rider',
    cancelled: 'Cancelled',
};

function zulziStatusLabel(status) {
    return ORDER_LIFECYCLE_LABELS[status] || status;
}

function formatPrice(amount, currency = 'ZAR') {
    return new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency,
        minimumFractionDigits: 2,
    }).format(amount);
}

function formatEta(epoch) {
    if (!epoch) return null;
    const date = new Date(epoch * 1000);
    if (Number.isNaN(date.getTime())) return null;
    return date.toLocaleString(undefined, {
        weekday: 'short',
        hour: '2-digit',
        minute: '2-digit',
    });
}

async function fetchZulziStops() {
    const response = await fetch(`${API_BASE}/zulzi/stops`);
    if (!response.ok) throw new Error(`Failed to fetch Zulzi stops: ${response.statusText}`);
    return response.json();
}

async function fetchZulziVendors(waypointId) {
    const response = await fetch(`${API_BASE}/zulzi/vendors?waypoint_id=${encodeURIComponent(waypointId)}`);
    if (!response.ok) throw new Error(`Failed to fetch vendors: ${response.statusText}`);
    return response.json();
}

async function fetchZulziMenu(vendorId) {
    const response = await fetch(`${API_BASE}/zulzi/vendors/${encodeURIComponent(vendorId)}/menu`);
    if (!response.ok) throw new Error(`Failed to fetch menu: ${response.statusText}`);
    return response.json();
}

async function fetchZulziVendor(vendorId) {
    const response = await fetch(`${API_BASE}/zulzi/vendors/${encodeURIComponent(vendorId)}`);
    if (!response.ok) throw new Error(`Failed to fetch vendor: ${response.statusText}`);
    return response.json();
}

async function placeZulziOrder(payload) {
    const response = await fetch(`${API_BASE}/zulzi/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            ...payload,
            rider_id: payload.rider_id || getOrCreateRiderId(),
        }),
    });
    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Failed to place order: ${response.statusText}`);
    }
    return response.json();
}

async function fetchZulziOrder(orderId) {
    const response = await fetch(`${API_BASE}/zulzi/orders/${encodeURIComponent(orderId)}`);
    if (!response.ok) throw new Error(`Failed to fetch order: ${response.statusText}`);
    return response.json();
}

async function cancelZulziOrder(orderId) {
    const response = await fetch(`${API_BASE}/zulzi/orders/${encodeURIComponent(orderId)}/cancel`, { method: 'POST' });
    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Could not cancel order: ${response.statusText}`);
    }
    return response.json();
}

async function advanceZulziOrder(orderId) {
    const response = await fetch(`${API_BASE}/zulzi/orders/${encodeURIComponent(orderId)}/advance`, { method: 'POST' });
    if (!response.ok) throw new Error(`Failed to advance order: ${response.statusText}`);
    return response.json();
}

async function confirmZulziReceived(orderId) {
    const response = await fetch(`${API_BASE}/zulzi/orders/${encodeURIComponent(orderId)}/received`, { method: 'POST' });
    if (!response.ok) throw new Error(`Failed to mark received: ${response.statusText}`);
    return response.json();
}

async function fetchRiderOrders(riderId) {
    const params = new URLSearchParams({ rider_id: riderId });
    const response = await fetch(`${API_BASE}/zulzi/orders?${params.toString()}`);
    if (!response.ok) throw new Error(`Failed to fetch orders: ${response.statusText}`);
    return response.json();
}

window.ZULZI_STATUS_LABEL = zulziStatusLabel;
window.formatPrice = formatPrice;
window.formatZulziEta = formatEta;

// ---------------------------------------------------------------------
// Zulzi commerce panel UI.
//
// Self-contained: initZulzi() populates the stop/volume selectors from the
// backend's own /zulzi/stops contract (so catalog and corridor can never
// disagree), renders vendors and menus, keeps a client-side cart, and tracks
// the placed order's status. The cart lives only in memory — a page reload
// loses it, which is the safe default: a half-filled cart is worth less than
// a rider who can re-pick at the next stop.
// ---------------------------------------------------------------------

const zulziState = {
    selectedVendorId: null,
    cart: [],
};

const ZULZI_ELS = {
    panel: document.getElementById('zulzi-panel'),
    stopSelect: document.getElementById('zulzi-stop'),
    vendorsEmpty: document.getElementById('zulzi-vendors-empty'),
    vendorsList: document.getElementById('zulzi-vendors'),
    menu: document.getElementById('zulzi-menu'),
    menuVendor: document.getElementById('zulzi-menu-vendor'),
    menuList: document.getElementById('zulzi-menu-list'),
    backToVendors: document.getElementById('zulzi-back-to-vendors'),
    cart: document.getElementById('zulzi-cart'),
    cartItems: document.getElementById('zulzi-cart-items'),
    cartTotal: document.getElementById('zulzi-cart-total'),
    carriageInput: document.getElementById('zulzi-carriage'),
    seatInput: document.getElementById('zulzi-seat'),
    placeOrder: document.getElementById('zulzi-place-order'),
    clearCart: document.getElementById('zulzi-clear-cart'),
    orderStatus: document.getElementById('zulzi-order-status'),
    orderId: document.getElementById('zulzi-order-id'),
    orderItems: document.getElementById('zulzi-order-items'),
    orderTotal: document.getElementById('zulzi-order-total'),
    orderStatusText: document.getElementById('zulzi-order-status'),
    orderDelivery: document.getElementById('zulzi-order-delivery'),
    cancelBtn: document.getElementById('zulzi-cancel-order'),
    receivedBtn: document.getElementById('zulzi-received-order'),
    advanceBtn: document.getElementById('zulzi-advance-order'),
    status: document.getElementById('zulzi-status'),
};

function setZulziStatus(text, tone = 'info') {
    if (!ZULZI_ELS.status) return;
    ZULZI_ELS.status.textContent = text;
    ZULZI_ELS.status.dataset.tone = tone;
}

function renderZulziStops(stops) {
    if (!ZULZI_ELS.stopSelect) return;
    ZULZI_ELS.stopSelect.innerHTML = '<option value="">Select a stop…</option>';
    for (const stop of stops) {
        const option = document.createElement('option');
        option.value = stop.waypoint_id;
        option.textContent = `${stop.name} — ${stop.vendor_count} vendor(s)`;
        ZULZI_ELS.stopSelect.appendChild(option);
    }
}

function renderZulziVendors(vendors) {
    if (!ZULZI_ELS.vendorsList || !ZULZI_ELS.vendorsEmpty) return;
    ZULZI_ELS.vendorsEmpty.classList.add('hidden');
    ZULZI_ELS.vendorsList.innerHTML = '';
    ZULZI_ELS.vendorsList.classList.remove('hidden');
    for (const vendor of vendors) {
        const card = document.createElement('button');
        card.className = 'zulzi-vendor-card';
        card.setAttribute('data-vendor-id', vendor.vendor_id);
        card.innerHTML = `
            <span class="zulzi-vendor-name">${vendor.name}</span>
            <span class="zulzi-vendor-meta">${vendor.category}${vendor.rating ? ' · ' + vendor.rating + '★' : ''}</span>
        `;
        card.addEventListener('click', () => selectZulziVendor(vendor.vendor_id));
    }
}

async function selectZulziVendor(vendorId) {
    zulziState.selectedVendorId = vendorId;
    ZULZI_ELS.vendorsList.classList.add('hidden');
    try {
        const menu = await fetchZulziMenu(vendorId);
        ZULZI_ELS.menuVendor.textContent = menu.vendor_name;
        renderZulziMenu(menu.items);
    } catch (err) {
        setZulziStatus(`Could not load menu: ${err.message}`, 'warn');
    }
    ZULZI_ELS.menu.classList.remove('hidden');
}

function renderZulziMenu(items) {
    if (!ZULZI_ELS.menuList) return;
    ZULZI_ELS.menuList.innerHTML = '';
    for (const item of items) {
        const li = document.createElement('li');
        li.className = 'zulzi-menu-item';
        li.innerHTML = `
            <div class="zulzi-item-info">
                <strong>${item.name}</strong>
                <span class="zulzi-item-desc">${item.description || ''}</span>
            </div>
            <div class="zulzi-item-price">${formatPrice(item.price, item.currency)}</div>
            <button class="zulzi-add" data-item-id="${item.item_id}" data-item-name="${item.name}" data-item-price="${item.price}" data-item-currency="${item.currency}" ${item.available ? '' : 'disabled'}>
                + Add
            </button>
        `;
        ZULZI_ELS.menuList.appendChild(li);
    }
    ZULZI_ELS.menuList.querySelectorAll('.zulzi-add').forEach((btn) => {
        btn.addEventListener('click', addToCart);
    });
}

function addToCart(event) {
    const btn = event.currentTarget;
    const item = {
        item_id: btn.dataset.itemId,
        name: btn.dataset.itemName,
        unit_price: parseFloat(btn.dataset.itemPrice),
        currency: btn.dataset.itemCurrency,
        quantity: 1,
    };
    const existing = zulziState.cart.find((i) => i.item_id === item.item_id);
    if (existing) {
        existing.quantity += 1;
    } else {
        zulziState.cart.push(item);
    }
    renderCart();
}

function changeQuantity(itemId, delta) {
    const item = zulziState.cart.find((i) => i.item_id === itemId);
    if (!item) return;
    item.quantity = Math.max(1, item.quantity + delta);
    if (item.quantity > 20) item.quantity = 20;
    renderCart();
}

function removeFromCart(itemId) {
    zulziState.cart = zulziState.cart.filter((i) => i.item_id !== itemId);
    renderCart();
}

function renderCart() {
    if (!ZULZI_ELS.cartItems || !ZULZI_ELS.cart || !ZULZI_ELS.cartTotal) return;
    ZULZI_ELS.cartItems.innerHTML = '';
    let total = 0;
    for (const item of zulziState.cart) {
        const line = document.createElement('li');
        line.className = 'zulzi-cart-line';
        line.innerHTML = `
            <span class="zulzi-cart-line-name">${item.name}</span>
            <div class="zulzi-qty-controls">
                <button type="button" class="zulzi-qty" data-item-id="${item.item_id}" data-delta="-1">−</button>
                <span>${item.quantity}×</span>
                <button type="button" class="zulzi-qty" data-item-id="${item.item_id}" data-delta="1">+</button>
            </div>
            <span class="zulzi-cart-line-total">${formatPrice(item.unit_price * item.quantity, item.currency)}</span>
            <button type="button" class="zulzi-remove" data-item-id="${item.item_id}">✕</button>
        `;
        ZULZI_ELS.cartItems.appendChild(line);
        total += item.unit_price * item.quantity;
    }
    const currency = zulziState.cart[0]?.currency || 'ZAR';
    ZULZI_ELS.cartTotal.textContent = `Total: ${formatPrice(total, currency)}`;

    const hasItems = zulziState.cart.length > 0;
    ZULZI_ELS.cart.classList.toggle('hidden', !hasItems);
    ZULZI_ELS.placeOrder.disabled = !hasItems;

    ZULZI_ELS.cartItems.querySelectorAll('.zulzi-qty').forEach((btn) => {
        btn.addEventListener('click', (e) => changeQuantity(btn.dataset.itemId, parseInt(btn.dataset.delta, 10)));
    });
    ZULZI_ELS.cartItems.querySelectorAll('.zulzi-remove').forEach((btn) => {
        btn.addEventListener('click', () => removeFromCart(btn.dataset.itemId));
    });
}

async function placeZulziOrderHandler() {
    if (!zulziState.selectedVendorId || zulziState.cart.length === 0) return;
    const waypointId = ZULZI_ELS.stopSelect.value;
    const carriage = ZULZI_ELS.carriageInput.value.trim();
    const seat = ZULZI_ELS.seatInput.value.trim();
    if (!waypointId || !carriage || !seat) {
        setZulziStatus('Pick a stop and enter your carriage + seat.', 'warn');
        return;
    }
    ZULZI_ELS.placeOrder.disabled = true;
    setZulziStatus('Placing your carriage order…');
    try {
        const order = await placeZulziOrder({
            waypoint_id: waypointId,
            vendor_id: zulziState.selectedVendorId,
            carriage,
            seat,
            items: zulziState.cart.map((i) => ({ item_id: i.item_id, quantity: i.quantity })),
        });
        zulziState.currentOrderId = order.order_id;
        zulziState.cart = [];
        renderCart();
        renderZulziOrder(order);
    } catch (err) {
        setZulziStatus(err.message, 'warn');
    } finally {
        ZULZI_ELS.placeOrder.disabled = false;
    }
}

function renderZulziOrder(order) {
    if (!ZULZI_ELS.orderStatus) return;
    ZULZI_ELS.orderStatus.classList.remove('hidden');
    ZULZI_ELS.orderStatusText.textContent = zulziStatusLabel(order.status);
    ZULZI_ELS.orderId.textContent = `Order #${order.order_id.slice(0, 8)} · ${formatPrice(order.total_amount, order.currency)}`;
    ZULZI_ELS.orderItems.textContent = order.items.map((i) => `${i.name} ×${i.quantity}`).join(', ');
    ZULZI_ELS.orderTotal.textContent = `Total: ${formatPrice(order.total_amount, order.currency)}`;
    const eta = formatZulziEta(order.delivery_eta);
    ZULZI_ELS.orderDelivery.textContent = eta
        ? `Expected at ${order.waypoint_name} when the train arrives: ${eta}`
        : `Delivery pinned to ${order.waypoint_name} station arrival`;

    ZULZI_ELS.cancelBtn.disabled = order.status !== 'placed' && order.status !== 'confirmed' && order.status !== 'preparing';
    ZULZI_ELS.receivedBtn.disabled = order.status !== 'delivered_to_carriage';
    ZULZI_ELS.advanceBtn.disabled = order.status === 'received' || order.status === 'cancelled';
}

async function cancelZulziOrderHandler() {
    if (!zulziState.currentOrderId) return;
    try {
        const order = await cancelZulziOrder(zulziState.currentOrderId);
        renderZulziOrder(order);
        setZulziStatus('Order cancelled.', 'ok');
    } catch (err) {
        setZulziStatus(err.message, 'warn');
    }
}

async function receivedZulziOrderHandler() {
    if (!zulziState.currentOrderId) return;
    try {
        const order = await confirmZulziReceived(zulziState.currentOrderId);
        renderZulziOrder(order);
        setZulziStatus('Thanks — order marked received.', 'ok');
    } catch (err) {
        setZulziStatus(err.message, 'warn');
    }
}

async function advanceZulziOrderHandler() {
    if (!zulziState.currentOrderId) return;
    try {
        const order = await advanceZulziOrder(zulziState.currentOrderId);
        renderZulziOrder(order);
    } catch (err) {
        setZulziStatus(err.message, 'warn');
    }
}

function initZulzi() {
    if (!ZULZI_ELS.panel) return;

    fetchZulziStops()
        .then(renderZulziStops)
        .catch((err) => setZulziStatus(`Could not load stops: ${err.message}`, 'warn'));

    ZULZI_ELS.stopSelect?.addEventListener('change', async () => {
        const waypointId = ZULZI_ELS.stopSelect.value;
        if (!waypointId) {
            ZULZI_ELS.vendorsEmpty.classList.remove('hidden');
            ZULZI_ELS.vendorsList.classList.add('hidden');
            return;
        }
        try {
            const vendors = await fetchZulziVendors(waypointId);
            if (vendors.length === 0) {
                ZULZI_ELS.vendorsEmpty.textContent = 'No vendors at this stop yet.';
                ZULZI_ELS.vendorsEmpty.classList.remove('hidden');
                ZULZI_ELS.vendorsList.classList.add('hidden');
            } else {
                renderZulziVendors(vendors);
            }
        } catch (err) {
            setZulziStatus(`Could not load vendors: ${err.message}`, 'warn');
        }
    });

    ZULZI_ELS.backToVendors?.addEventListener('click', () => {
        ZULZI_ELS.menu.classList.add('hidden');
        ZULZI_ELS.vendorsList.classList.remove('hidden');
        zulziState.selectedVendorId = null;
    });

    ZULZI_ELS.clearCart?.addEventListener('click', () => {
        zulziState.cart = [];
        renderCart();
        setZulziStatus('', 'info');
    });

    ZULZI_ELS.placeOrder?.addEventListener('click', placeZulziOrderHandler);
    ZULZI_ELS.cancelBtn?.addEventListener('click', cancelZulziOrderHandler);
    ZULZI_ELS.receivedBtn?.addEventListener('click', receivedZulziOrderHandler);
    ZULZI_ELS.advanceBtn?.addEventListener('click', advanceZulziOrderHandler);
}

