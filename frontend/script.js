/**
 * BorrowHub — Complete Full-Stack Frontend Integration
 * SVNIT Campus Resource Sharing Platform
 * "Share · Borrow · Grow"
 */

// ==========================================
// 1. CONFIGURATION & STATE
// ==========================================
let API_BASE = (window.location.protocol === "file:" || (window.location.port !== "8000" && window.location.port !== ""))
  ? "http://127.0.0.1:8000"
  : "";

if (window.location.protocol === "file:") {
  window.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById("fileProtocolBar")) {
      const bar = document.createElement("div");
      bar.id = "fileProtocolBar";
      bar.style.cssText = "background: #fef3c7; color: #92400e; font-size: 13px; font-weight: 500; text-align: center; padding: 7px 14px; border-bottom: 1px solid #fde68a; position: relative; z-index: 9999;";
      bar.innerHTML = '⚡ Running in file mode. Ensure <strong>start_server.bat</strong> is open. For the smoothest experience, open <a href="http://127.0.0.1:8000" style="color:#b45309; text-decoration:underline; font-weight:700;">http://127.0.0.1:8000</a>.';
      document.body.prepend(bar);
    }
  });
}
const TOKEN_KEY = "borrowhub_jwt_token";
const USER_KEY = "borrowhub_user_profile";

const state = {
  token: localStorage.getItem(TOKEN_KEY) || null,
  currentUser: JSON.parse(localStorage.getItem(USER_KEY) || "null"),
  categories: [],
  locations: [],
  items: [],
  favorites: new Set(),
  selectedCategory: null,
  query: "",
  showAllPopular: false,
  showAllRecent: false,
  authMode: "login",
  pendingVerifyEmail: null,
  pendingResetEmail: null,
  pendingResetOtp: null,
  editingItemId: null,
  activeListingTab: "my-items",
  activeLoanTab: "borrowed",
  uploadedImageUrls: [],
  currentModalItem: null,
  currentModalAvailability: null,
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function toast(message, isError = false) {
  const el = $("#toast");
  if (!el) return;
  el.textContent = message;
  el.classList.toggle("toast-error", Boolean(isError));
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    el.classList.remove("show");
    el.classList.remove("toast-error");
  }, 3200);
}

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[ch]));
}

function conditionLabel(condition) {
  if (!condition) return "Good";
  return condition.charAt(0).toUpperCase() + condition.slice(1).toLowerCase();
}

function formatDate(isoString) {
  if (!isoString) return "N/A";
  try {
    const d = new Date(isoString);
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return isoString;
  }
}

// ==========================================
// 2. API CLIENT
// ==========================================
async function apiFetch(endpoint, options = {}) {
  const headers = { ...(options.headers || {}) };
  const isAuthEndpoint = endpoint.includes("/auth/");

  if (state.token && !headers["Authorization"] && !isAuthEndpoint) {
    headers["Authorization"] = `Bearer ${state.token}`;
  }

  // Auto set JSON content-type if body is an object and not FormData
  if (options.body && !(options.body instanceof FormData) && typeof options.body === "object") {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }

  let res;
  try {
    try {
      res = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
    } catch (netErr) {
      if (window.location.protocol === "file:" || API_BASE.includes("8000")) {
        const altBase = API_BASE.includes("127.0.0.1")
          ? API_BASE.replace("127.0.0.1", "localhost")
          : API_BASE.replace("localhost", "127.0.0.1");
        try {
          res = await fetch(`${altBase}${endpoint}`, { ...options, headers });
          API_BASE = altBase;
        } catch (altErr) {
          throw new Error("Cannot connect to BorrowHub server. Please make sure 'start_server.bat' is running.");
        }
      } else {
        throw new Error("Cannot connect to BorrowHub server. Please make sure 'start_server.bat' is running.");
      }
    }

    if (res.status === 401 && state.token && !isAuthEndpoint) {
      // Clear invalid session silently without throwing misleading error messages on login
      clearAuthSession();
      throw new Error("Your session has expired. Please sign in again.");
    }

    if (!res.ok) {
      let errorMsg = `Server error (${res.status})`;
      try {
        const errorData = await res.json();
        if (errorData.detail) {
          if (Array.isArray(errorData.detail)) {
            errorMsg = errorData.detail.map(d => d.msg || d.message).join(", ");
          } else {
            errorMsg = errorData.detail;
          }
        }
      } catch {}
      throw new Error(errorMsg);
    }

    if (res.status === 204) return null;
    return await res.json();
  } catch (err) {
    console.error(`API Error [${endpoint}]:`, err);
    throw err;
  }
}

// ==========================================
// 3. AUTHENTICATION & SESSION
// ==========================================
function setAuthSession(token, user) {
  state.token = token;
  state.currentUser = user;
  state.editingItemId = null; // Always clear any editing lock when signing in
  state.uploadedImageUrls = [];
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  updateAuthUI();
  refreshUserData();
}

function clearAuthSession() {
  state.token = null;
  state.currentUser = null;
  state.editingItemId = null;
  state.uploadedImageUrls = [];
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  updateAuthUI();
}

function updateAuthUI() {
  const isAuth = Boolean(state.token && state.currentUser);
  document.body.classList.toggle("is-authenticated", isAuth);

  const signInBtn = $("#signInBtn");
  if (signInBtn) {
    if (isAuth) {
      const firstName = (state.currentUser.full_name || "Student").split(" ")[0];
      signInBtn.innerHTML = `Hi, ${escapeHtml(firstName)} <span>▾</span>`;
      signInBtn.title = `Signed in as ${state.currentUser.svnit_email}. Click to sign out.`;
    } else {
      signInBtn.innerHTML = `Sign In <span>↗</span>`;
      signInBtn.title = "Sign In with your SVNIT account";
    }
  }

  // Update notification badge
  if (isAuth) {
    fetchNotificationCount();
  } else {
    const badge = $("#notificationCount");
    if (badge) badge.hidden = true;
  }

  // Update admin portal buttons
  const adminEmails = ["admin@svnit.ac.in"];
  const isAdmin = Boolean(isAuth && state.currentUser && (
    state.currentUser.role === "ADMIN" ||
    state.currentUser.role === "MODERATOR" ||
    adminEmails.includes((state.currentUser.svnit_email || "").toLowerCase())
  ));

  const navAdminBtn = $("#navAdminBtn");
  if (navAdminBtn) {
    navAdminBtn.style.display = isAdmin ? "inline-flex" : "none";
  }
  const mobileAdmin = $("#mobileAdmin");
  if (mobileAdmin) {
    mobileAdmin.style.display = isAdmin ? "inline-flex" : "none";
  }
}

function showAuthMessage(message, type = "error") {
  const el = $("#authInlineMessage");
  if (!el) return;
  el.textContent = message;
  el.className = `auth-inline-message ${type}`;
  el.hidden = false;
}

function clearAuthMessage() {
  const el = $("#authInlineMessage");
  if (el) {
    el.hidden = true;
    el.textContent = "";
    el.className = "auth-inline-message";
  }
}

function openAuth(mode = "login") {
  state.authMode = mode;
  updateAuthMode();
  const dialog = $("#authDialog");
  if (dialog && !dialog.open) dialog.showModal();
}

function updateAuthMode() {
  clearAuthMessage();
  const isRegister = state.authMode === "register";
  const isForgot = state.authMode === "forgot";

  if ($("#authTabs")) $("#authTabs").hidden = isForgot;
  $$(".auth-tab").forEach(tab => tab.classList.toggle("active", tab.dataset.tab === state.authMode));

  if (isForgot) {
    $("#authTitle").textContent = "Reset password";
    $("#authSubtitle").textContent = "Enter your official SVNIT email to receive a 6-digit password reset code.";
    $("#nameField").hidden = true;
    $("#rollField").hidden = true;
    $("#phoneField").hidden = true;
    $("#passwordField").hidden = true;
    $("#authPassword").required = false;
    $("#authSubmit").innerHTML = "Send Reset Code <span>→</span>";
    $("#forgotBtn").hidden = true;
    if ($("#forgotBackBtn")) $("#forgotBackBtn").hidden = false;
    if ($("#quickAccountsSection")) $("#quickAccountsSection").hidden = true;
    $("#authForm").hidden = false;
    $("#otpSection").hidden = true;
    if ($("#resetOtpSection")) $("#resetOtpSection").hidden = true;
    if ($("#setNewPasswordSection")) $("#setNewPasswordSection").hidden = true;
    if ($("#forgotPasswordActions")) $("#forgotPasswordActions").hidden = false;
  } else {
    state.pendingResetOtp = null;
    $("#authTitle").textContent = isRegister ? "Join BorrowHub" : "Welcome back";
    $("#authSubtitle").textContent = isRegister
      ? "Create your student account to share and borrow on SVNIT campus."
      : "Sign in with your official SVNIT email to continue.";

    $("#nameField").hidden = !isRegister;
    $("#rollField").hidden = !isRegister;
    $("#phoneField").hidden = !isRegister;
    $("#passwordField").hidden = false;
    $("#authPassword").required = true;

    $("#authName").required = isRegister;
    $("#authRoll").required = isRegister;

    $("#authForm").hidden = false;
    $("#otpSection").hidden = true;
    if ($("#resetOtpSection")) $("#resetOtpSection").hidden = true;
    if ($("#setNewPasswordSection")) $("#setNewPasswordSection").hidden = true;

    $("#authSubmit").innerHTML = isRegister ? "Create account <span>→</span>" : "Sign in <span>→</span>";
    $("#forgotBtn").hidden = isRegister;
    if ($("#forgotBackBtn")) $("#forgotBackBtn").hidden = true;
    if ($("#quickAccountsSection")) $("#quickAccountsSection").hidden = false;
    if ($("#forgotPasswordActions")) $("#forgotPasswordActions").hidden = false;
  }
}

// Quick demo login helper
async function demoLogin(username) {
  const accounts = {
    admin: { email: "admin@svnit.ac.in", pass: "Svnit@2026!" },
    priya: { email: "priya@coed.svnit.ac.in", pass: "Svnit@2026!" },
    aarav: { email: "aarav@coed.svnit.ac.in", pass: "Svnit@2026!" },
    rohit: { email: "rohit@coed.svnit.ac.in", pass: "Svnit@2026!" }
  };

  const acc = accounts[username];
  if (!acc) return;

  $("#authEmail").value = acc.email;
  $("#authPassword").value = acc.pass;

  try {
    showAuthMessage("Signing in...", "success");
    state.token = null;
    state.currentUser = null;
    const data = await apiFetch("/api/auth/login", {
      method: "POST",
      body: { email: acc.email, svnit_email: acc.email, password: acc.pass }
    });

    setAuthSession(data.access_token, data.user);
    $("#authDialog").close();
    toast(`Signed in as ${data.user.full_name} (${data.user.svnit_email})`);
    loadMarketplace();
    fetchUserLoans();
  } catch (err) {
    let msg = err.message || "Sign in failed.";
    if (msg.toLowerCase().includes("session expired") || msg.toLowerCase().includes("invalid svnit email or password")) {
      msg = "Incorrect SVNIT email or password. Please check your password or click 'Forgot password?' below.";
    }
    showAuthMessage(msg, "error");
  }
}

// ==========================================
// 4. METRICS & USER DATA REFRESH
// ==========================================
async function refreshUserData() {
  if (!state.token) return;   // nothing to verify before sign-in
  try {
    const me = await apiFetch("/api/auth/me");
    state.currentUser = me;
    localStorage.setItem(USER_KEY, JSON.stringify(me));
    fetchNotificationCount();
    fetchUserLoans();
  } catch (err) {
    console.warn("Could not verify session:", err);
  }
}

async function fetchNotificationCount() {
  if (!state.token) return;
  try {
    const data = await apiFetch("/api/notifications/unread-count");
    const badge = $("#notificationCount");
    if (!badge) return;
    const count = data.unread_count || 0;
    badge.textContent = count > 99 ? "99+" : String(count);
    badge.hidden = count === 0;
  } catch {}
}

// ==========================================
// 5. MARKETPLACE & ITEM EXPLORATION
// ==========================================
const fallbackEmojiMap = {
  "Electronics": "💻",
  "Books": "📚",
  "Lab Equipment": "🧪",
  "Sports": "🏸",
  "Tools": "🔧",
  "Stationery": "🖍️",
  "Musical Instruments": "🎸",
  "Others": "🎒",
  "Daily Essentials": "🎒"
};

function productCard(p) {
  const isFav = state.favorites.has(p.item_id);
  const cat = p.category_name || "Others";
  const bg = cat === "Books" ? "#f5ead7" : cat === "Sports" ? "#e1eddb" : cat === "Lab Equipment" ? "#f6e5e7" : cat === "Stationery" ? "#eee7f5" : "#e5edf0";
  const emoji = fallbackEmojiMap[cat] || "✦";

  const imgMarkup = p.primary_image_url
    ? `<img src="${p.primary_image_url}" alt="${escapeHtml(p.title)}" loading="lazy" onerror="this.outerHTML='<span class=\\'emoji-fallback\\'>${emoji}</span>'">`
    : `<span class="emoji-fallback">${emoji}</span>`;

  return `<article class="product-card" data-id="${p.item_id}">
    <button class="product-image" style="background:${bg}" data-open-item="${p.item_id}" aria-label="View ${escapeHtml(p.title)}">
      ${imgMarkup}
    </button>
    <div class="product-info">
      <button class="favorite-button ${isFav ? "is-favorite" : ""}" data-favorite="${p.item_id}" aria-label="${isFav ? "Remove from" : "Add to"} favorites">
        ${isFav ? "♥" : "♡"}
      </button>
      <h3 class="product-title">${escapeHtml(p.title)}</h3>
      <div class="price-line">
        <strong>₹${Number(p.daily_fee).toFixed(0)}/day</strong>
        <span class="separator">·</span>
        <span>₹${Number(p.deposit_amount).toFixed(0)} deposit</span>
      </div>
      <div class="product-meta">
        <span class="condition ${p.item_condition.toLowerCase()}">${conditionLabel(p.item_condition)}</span>
        <span class="location" title="${escapeHtml(p.location_name || 'SVNIT Campus')}">⌖ ${escapeHtml(p.location_name || 'SVNIT Campus')}</span>
      </div>
    </div>
  </article>`;
}

async function loadMarketplace() {
  try {
    let url = `/api/items?page=1&page_size=24&sort_by=newest`;
    if (state.query) url += `&q=${encodeURIComponent(state.query)}`;
    if (state.selectedCategory) url += `&category_id=${state.selectedCategory}`;

    const data = await apiFetch(url);
    state.items = data.items || [];

    // Sync favorites
    state.favorites.clear();
    state.items.forEach(item => {
      if (item.is_favorite) state.favorites.add(item.item_id);
    });

    renderMarketplace();
  } catch (err) {
    console.error("Failed to load marketplace:", err);
  }
}

function renderMarketplace() {
  const popularSection = document.querySelector("#marketplace");
  const recentSection = document.querySelector(".recent-section");
  const popularGrid = $("#popularGrid");
  const recentGrid = $("#recentGrid");

  if (!popularGrid) return;

  const items = state.items;

  if (items.length === 0) {
    const emptyMarkup = `<div class="marketplace-empty">
      <span class="marketplace-empty-icon">＋</span>
      <h3>No student listings found</h3>
      <p>Be the first to share a resource with the SVNIT campus community.</p>
      <button class="primary-button" type="button" data-open-listing>List an item now <span>→</span></button>
    </div>`;
    popularGrid.innerHTML = emptyMarkup;
    if (recentGrid) recentGrid.innerHTML = "";
    if (popularSection) popularSection.classList.add("is-empty-marketplace");
    if (recentSection) recentSection.hidden = true;
    return;
  }

  if (popularSection) popularSection.classList.remove("is-empty-marketplace");
  if (recentSection) recentSection.hidden = false;

  // Split items into popular (first few) and recent
  const popular = items.slice(0, 4);
  const recent = items.slice(4);

  const displayedPopular = state.showAllPopular ? items : popular;
  const displayedRecent = state.showAllRecent ? recent : recent.slice(0, 4);

  popularGrid.innerHTML = displayedPopular.map(productCard).join("");
  if (recentGrid) {
    if (displayedRecent.length) {
      recentGrid.innerHTML = displayedRecent.map(productCard).join("");
      recentSection.hidden = false;
    } else {
      recentSection.hidden = true;
    }
  }

  // Highlight selected category tile
  $$(".category-tile").forEach(btn => {
    const catName = btn.dataset.category;
    const catObj = state.categories.find(c => c.category_name.toLowerCase().includes(catName.toLowerCase()));
    const isSelected = catObj && state.selectedCategory === catObj.category_id;
    btn.classList.toggle("selected", Boolean(isSelected));
  });
}

// ==========================================
// 6. ITEM DETAILS & BORROW REQUEST MODAL
// ==========================================
async function openItem(itemId) {
  try {
    const [item, availability] = await Promise.all([
      apiFetch(`/api/items/${itemId}`),
      apiFetch(`/api/items/${itemId}/availability`)
    ]);

    state.currentModalItem = item;
    state.currentModalAvailability = availability;

    const content = $("#itemDialogContent");
    const isOwner = state.currentUser && item.owner_id === state.currentUser.user_id;
    const cat = item.category_name || "Others";
    const emoji = fallbackEmojiMap[cat] || "✦";

    // Setup dates: tomorrow as default start, +3 days as default end
    const today = new Date();
    const tmrw = new Date(today);
    tmrw.setDate(tmrw.getDate() + 1);
    const endDef = new Date(tmrw);
    endDef.setDate(endDef.getDate() + 2);

    const minDateStr = tmrw.toISOString().split("T")[0];
    const defaultStartStr = minDateStr;
    const defaultEndStr = endDef.toISOString().split("T")[0];

    // Image gallery
    const images = item.images && item.images.length > 0 ? item.images : [{ image_url: item.primary_image_url || "" }];
    const mainImgSrc = images[0]?.image_url || "";

    const galleryMarkup = mainImgSrc
      ? `<div class="gallery-container">
          <img id="mainGalleryImg" class="gallery-main-img" src="${mainImgSrc}" alt="${escapeHtml(item.title)}" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'item-detail-emoji',textContent:'${emoji}'}))">
          ${images.length > 1 ? `
            <div class="gallery-thumb-strip">
              ${images.map((img, idx) => `
                <img class="gallery-thumb ${idx === 0 ? 'active' : ''}" src="${img.image_url}" data-img-src="${img.image_url}" alt="Thumbnail ${idx + 1}" onerror="this.style.display='none'">
              `).join("")}
            </div>` : ""}
        </div>`
      : `<div class="item-detail-emoji">${emoji}</div>`;

    content.innerHTML = `
      <div class="item-detail-top">
        ${galleryMarkup}
        <div class="item-detail-copy">
          <span class="section-kicker">${escapeHtml(cat.toUpperCase())}</span>
          <h2>${escapeHtml(item.title)}</h2>
          <div class="detail-price">
            ₹${Number(item.daily_fee).toFixed(0)}/day
            <small>· ₹${Number(item.deposit_amount).toFixed(0)} refundable deposit</small>
          </div>
          <p>${escapeHtml(item.description || "Student-listed campus resource.")}</p>
          <span class="condition ${item.item_condition.toLowerCase()}">${conditionLabel(item.item_condition)} condition</span>
        </div>
      </div>

      <div class="detail-list">
        <div class="detail-stat">
          <span>Pickup location</span>
          <strong>${escapeHtml(item.location_name || "SVNIT Campus")}</strong>
        </div>
        <div class="detail-stat">
          <span>Max rental duration</span>
          <strong>${item.max_borrow_days} days</strong>
        </div>
        <div class="detail-stat">
          <span>Owner</span>
          <strong>${escapeHtml(item.owner_name)}</strong>
        </div>
        <div class="detail-stat">
          <span>Hostel / Dept</span>
          <strong>${escapeHtml(item.owner_hostel || "SVNIT Surat")}</strong>
        </div>
      </div>

      ${!isOwner ? `
        <div class="detail-calc-card">
          <h4 style="margin: 0 0 10px; font-size: 13px; color: var(--ink);">Select Borrow Dates</h4>
          <div class="form-row">
            <label class="form-field">
              <span>Start Date</span>
              <input type="date" id="borrowStartDate" min="${minDateStr}" value="${defaultStartStr}">
            </label>
            <label class="form-field">
              <span>End Date</span>
              <input type="date" id="borrowEndDate" min="${minDateStr}" value="${defaultEndStr}">
            </label>
          </div>
          
          <div id="costCalculationBreakdown">
            <!-- Dynamically populated -->
          </div>

          <label class="form-field" style="margin-top: 10px;">
            <span>Message to Owner (optional)</span>
            <textarea id="borrowMessage" rows="2" placeholder="e.g. Need this for Lab exam on Friday, will return promptly."></textarea>
          </label>
        </div>
      ` : ""}

      <div class="detail-actions">
        ${isOwner ? `
          <button class="primary-button" type="button" disabled style="opacity: 0.6;">This is your listing</button>
        ` : `
          <button class="primary-button" id="submitBorrowReqBtn" type="button">Request to Borrow <span>→</span></button>
        `}
        <button class="outline-button" data-favorite="${item.item_id}">
          ${state.favorites.has(item.item_id) ? "♥ Saved" : "♡ Save item"}
        </button>
      </div>
      
      ${isOwner ? `
        <p class="demo-note" style="text-align: center;">You cannot borrow your own resource. Manage this item from My Listings.</p>
      ` : `
        <p class="demo-note" style="text-align: center;">Security deposit is held securely and returned upon verified handover back to owner.</p>
      `}
    `;

    // Wire up thumbnail clicks
    $$(".gallery-thumb", content).forEach(thumb => {
      thumb.addEventListener("click", () => {
        $$(".gallery-thumb", content).forEach(t => t.classList.remove("active"));
        thumb.classList.add("active");
        $("#mainGalleryImg").src = thumb.dataset.imgSrc;
      });
    });

    // Wire up date change calculation
    if (!isOwner) {
      const startEl = $("#borrowStartDate");
      const endEl = $("#borrowEndDate");
      const updateCost = () => updateModalCostCalculation(item);

      startEl.addEventListener("change", () => {
        if (endEl.value < startEl.value) endEl.value = startEl.value;
        updateCost();
      });
      endEl.addEventListener("change", updateCost);

      updateCost();

      // Submit borrow request
      $("#submitBorrowReqBtn").addEventListener("click", () => handleBorrowRequestSubmit(item.item_id));
    }

    $("#itemDialog").showModal();
  } catch (err) {
    toast(`Could not open item: ${err.message}`, true);
  }
}

function updateModalCostCalculation(item) {
  const startVal = $("#borrowStartDate")?.value;
  const endVal = $("#borrowEndDate")?.value;
  const container = $("#costCalculationBreakdown");
  const submitBtn = $("#submitBorrowReqBtn");

  if (!startVal || !endVal || !container) return;

  const start = new Date(startVal);
  const end = new Date(endVal);

  if (end < start) {
    container.innerHTML = `<p style="color: #c53030; font-size: 11px;">End date cannot be earlier than start date.</p>`;
    if (submitBtn) submitBtn.disabled = true;
    return;
  }

  const days = Math.round((end - start) / (1000 * 60 * 60 * 24)) + 1;

  if (days > item.max_borrow_days) {
    container.innerHTML = `<p style="color: #c53030; font-size: 11px;">Max borrowing duration is ${item.max_borrow_days} days (selected: ${days} days).</p>`;
    if (submitBtn) submitBtn.disabled = true;
    return;
  }

  // Check booked dates overlap
  let isOverlap = false;
  if (state.currentModalAvailability?.booked_ranges) {
    for (const r of state.currentModalAvailability.booked_ranges) {
      if (startVal <= r.end_date && endVal >= r.start_date) {
        isOverlap = true;
        break;
      }
    }
  }

  if (isOverlap) {
    container.innerHTML = `<p style="color: #c53030; font-size: 11px;">Selected dates clash with an existing booking. Please pick another date.</p>`;
    if (submitBtn) submitBtn.disabled = true;
    return;
  }

  if (submitBtn) submitBtn.disabled = false;

  const rentalFee = Number(item.daily_fee) * days;
  const deposit = Number(item.deposit_amount);
  const total = rentalFee + deposit;

  container.innerHTML = `
    <div class="calc-row"><span>Duration:</span> <strong>${days} day${days > 1 ? 's' : ''}</strong></div>
    <div class="calc-row"><span>Rental Fee:</span> <strong>₹${rentalFee.toFixed(2)}</strong></div>
    <div class="calc-row"><span>Refundable Security Deposit:</span> <strong>₹${deposit.toFixed(2)}</strong></div>
    <div class="calc-row total"><span>Total Payable upon approval:</span> <strong>₹${total.toFixed(2)}</strong></div>
  `;
}

async function handleBorrowRequestSubmit(itemId) {
  if (!state.currentUser) {
    $("#itemDialog").close();
    openAuth("login");
    showAuthMessage("Please sign in with your SVNIT email to borrow items.", "error");
    return;
  }

  const start_date = $("#borrowStartDate").value;
  const end_date = $("#borrowEndDate").value;
  const borrower_note = $("#borrowMessage").value.trim();

  try {
    $("#submitBorrowReqBtn").disabled = true;
    $("#submitBorrowReqBtn").textContent = "Submitting...";

    await apiFetch("/api/borrow-requests", {
      method: "POST",
      body: {
        item_id: itemId,
        start_date,
        end_date,
        borrower_note: borrower_note || undefined
      }
    });

    $("#itemDialog").close();
    toast("Borrow request submitted! The owner will review your dates.");
    fetchUserLoans();
  } catch (err) {
    toast(`Failed to submit request: ${err.message}`, true);
    if ($("#submitBorrowReqBtn")) {
      $("#submitBorrowReqBtn").disabled = false;
      $("#submitBorrowReqBtn").innerHTML = `Request to Borrow <span>→</span>`;
    }
  }
}

// ==========================================
// 7. LIST AN ITEM & PHOTO UPLOADS
// ==========================================
function openList() {
  if (!state.currentUser) {
    openAuth("login");
    showAuthMessage("Please sign in before listing an item.", "error");
    return;
  }

  const form = $("#listForm");
  form.reset();
  state.editingItemId = null;
  state.uploadedImageUrls = [];
  renderImagePreviews();
  clearListMessage();

  $("#listDialog").querySelector("h2").textContent = "List a campus resource";
  $("#listDialog").querySelector(".modal-submit").innerHTML = "Publish Listing <span>→</span>";
  $("#listDialog").showModal();
  $("#listDialog").scrollTop = 0;
  setTimeout(() => {
    $("#listDialog").scrollTop = 0;
    const titleInp = $("#listTitleInput");
    if (titleInp) {
      titleInp.focus();
    }
  }, 40);
}

function showListMessage(msg, isError = true) {
  const topEl = $("#listFormMessage");
  const bottomEl = $("#listFormBottomMessage");
  if (topEl) {
    topEl.textContent = msg;
    topEl.className = `auth-inline-message ${isError ? 'error' : 'success'}`;
    topEl.style.display = "block";
  }
  if (bottomEl) {
    bottomEl.textContent = msg;
    bottomEl.className = `auth-inline-message ${isError ? 'error' : 'success'}`;
    bottomEl.style.display = "block";
  }
  if (!topEl && !bottomEl) {
    toast(msg, isError);
  }
}

function clearListMessage() {
  const topEl = $("#listFormMessage");
  const bottomEl = $("#listFormBottomMessage");
  if (topEl) {
    topEl.textContent = "";
    topEl.style.display = "none";
  }
  if (bottomEl) {
    bottomEl.textContent = "";
    bottomEl.style.display = "none";
  }
}

async function uploadImageFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await apiFetch("/api/upload", {
    method: "POST",
    body: formData
  });

  return res.url;
}

function renderImagePreviews() {
  const container = $("#imagePreviewContainer");
  if (!container) return;

  container.innerHTML = state.uploadedImageUrls.map((url, idx) => `
    <div class="preview-item">
      <img src="${url}" alt="Item upload ${idx + 1}">
      <button type="button" class="preview-remove" data-remove-img="${idx}">×</button>
    </div>
  `).join("");
}

// Wire image file picker
$("#itemImagesInput")?.addEventListener("change", async (e) => {
  const files = [...e.target.files];
  if (!files.length) return;

  if (state.uploadedImageUrls.length + files.length > 5) {
    toast("Maximum 5 photographs allowed per listing.", true);
    return;
  }

  for (const file of files) {
    try {
      toast(`Uploading ${file.name}...`);
      const url = await uploadImageFile(file);
      state.uploadedImageUrls.push(url);
      renderImagePreviews();
      toast("Image uploaded successfully!");
    } catch (err) {
      toast(`Upload failed for ${file.name}: ${err.message}`, true);
    }
  }
});

$("#imagePreviewContainer")?.addEventListener("click", (e) => {
  const removeBtn = e.target.closest("[data-remove-img]");
  if (removeBtn) {
    const idx = Number(removeBtn.dataset.removeImg);
    state.uploadedImageUrls.splice(idx, 1);
    renderImagePreviews();
  }
});

// Custom location toggle
$("#listLocationSelect")?.addEventListener("change", (e) => {
  const customField = $("#customLocationField");
  if (!customField) return;
  // If location is "Other" or empty
  const loc = state.locations.find(l => l.location_id === Number(e.target.value));
  customField.hidden = !(loc && loc.name.toLowerCase().includes("other"));
});

// Informational character counter for listing description (optional details)
$("#listDescInput")?.addEventListener("input", (e) => {
  const counter = $("#descCharCounter");
  if (!counter) return;
  const len = (e.target.value || "").trim().length;
  counter.textContent = len > 0
    ? `${len} characters entered`
    : "Condition details, accessories, and pickup instructions.";
  counter.style.color = "#718078";
});

// Submit Listing Form
$("#listForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearListMessage();

  if (!state.currentUser) {
    showListMessage("Please sign in before listing an item.");
    return;
  }

  const form = new FormData(e.currentTarget);
  const title = String(form.get("title") || "").trim();
  const category_id = Number(form.get("category_id")) || (state.categories[0] ? state.categories[0].category_id : undefined);
  const location_id = form.get("location_id") ? Number(form.get("location_id")) : (state.locations[0] ? state.locations[0].location_id : undefined);
  const custom_location = String(form.get("custom_location") || "").trim() || undefined;
  const description = String(form.get("description") || "").trim();
  const daily_fee_raw = form.get("daily_fee");
  const deposit_amount_raw = form.get("deposit_amount");
  const daily_fee = daily_fee_raw !== null && daily_fee_raw !== "" && !isNaN(Number(daily_fee_raw)) ? Math.max(0, Number(daily_fee_raw)) : 0;
  const deposit_amount = deposit_amount_raw !== null && deposit_amount_raw !== "" && !isNaN(Number(deposit_amount_raw)) ? Math.max(0, Number(deposit_amount_raw)) : 0;
  const item_condition = String(form.get("item_condition") || "GOOD");
  const max_borrow_days = Number(form.get("max_borrow_days") || 7);

  if (!title || title.length < 2) {
    showListMessage("Please enter an item title (at least 2 characters).");
    const titleInput = $("#listTitleInput");
    if (titleInput) {
      titleInput.style.border = "2px solid #ef4444";
      titleInput.scrollIntoView({ behavior: "smooth", block: "center" });
      titleInput.focus();
    }
    return;
  }

  if (!category_id) {
    showListMessage("Please choose a category for this item.");
    $("#listCategorySelect")?.focus();
    return;
  }

  const payload = {
    title,
    category_id,
    location_id,
    custom_location,
    description: description || undefined,
    daily_fee,
    deposit_amount,
    item_condition,
    max_borrow_days,
    image_urls: state.uploadedImageUrls
  };

  const submitBtn = e.currentTarget.querySelector(".modal-submit");
  try {
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = state.editingItemId ? "Saving updates..." : "Publishing Listing...";
    }

    if (state.editingItemId) {
      await apiFetch(`/api/items/${state.editingItemId}`, {
        method: "PUT",
        body: payload
      });
      toast(`“${title}” updated successfully!`);
    } else {
      await apiFetch("/api/items", {
        method: "POST",
        body: payload
      });
      toast(`🎉 “${title}” listed on BorrowHub! Anyone can borrow it.`);
    }

    state.editingItemId = null;
    state.uploadedImageUrls = [];
    renderImagePreviews();
    $("#listForm")?.reset();
    const titleInput = $("#listTitleInput");
    if (titleInput) titleInput.style.border = "";
    $("#listDialog").close();
    loadMarketplace();
    if ($("#myListingsDialog").open) renderMyListingsDialog();
  } catch (err) {
    showListMessage(`Failed to save listing: ${err.message}`, true);
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = "Publish Listing <span>→</span>";
    }
  }
});

// Reset listing modal state when dialog is closed
$("#listDialog")?.addEventListener("close", () => {
  state.editingItemId = null;
  state.uploadedImageUrls = [];
  renderImagePreviews();
  clearListMessage();
  const titleInput = $("#listTitleInput");
  if (titleInput) titleInput.style.border = "";
  $("#listForm")?.reset();
});

$("#listTitleInput")?.addEventListener("input", (e) => {
  if (e.target.value.trim().length >= 2) {
    e.target.style.border = "";
    clearListMessage();
  }
});

// ==========================================
// 8. MY LISTINGS & INCOMING REQUESTS
// ==========================================
function openMyListings() {
  if (!state.currentUser) {
    openAuth("login");
    showAuthMessage("Please sign in to view your listings.", "error");
    return;
  }
  state.activeListingTab = "my-items";
  renderMyListingsDialog();
  $("#myListingsDialog").showModal();
}

async function renderMyListingsDialog() {
  $("#tabMyItems").classList.toggle("active", state.activeListingTab === "my-items");
  $("#tabIncomingReqs").classList.toggle("active", state.activeListingTab === "incoming-requests");

  const container = $("#myListingsContent");
  container.innerHTML = `<p style="text-align: center; color: #718078; padding: 20px;">Loading...</p>`;

  try {
    const [myListings, incomingReqs] = await Promise.all([
      apiFetch("/api/items/my-listings"),
      apiFetch("/api/borrow-requests/incoming")
    ]);

    $("#myItemsCount").textContent = myListings.length;
    const pendingCount = incomingReqs.filter(r => r.status === "PENDING").length;
    $("#incomingReqCount").textContent = pendingCount;

    if (state.activeListingTab === "my-items") {
      if (!myListings.length) {
        container.innerHTML = `<div class="dialog-empty-state" style="text-align: center; padding: 30px 10px;">
          <div class="empty-symbol" style="font-size: 32px; color: var(--coral);">＋</div>
          <h3 style="margin: 8px 0;">You haven't listed any items yet</h3>
          <p style="color: #66766d; font-size: 11px;">Share calculators, books, lab coats, or electronics with campus.</p>
        </div>`;
        return;
      }

      container.innerHTML = `<div class="manage-list">${myListings.map(item => `
        <article class="manage-list-row" style="display: flex; justify-content: space-between; align-items: center; padding: 12px; border-bottom: 1px solid #f0eee5;">
          <div>
            <h3 style="margin: 0 0 4px; font-size: 13px;">${escapeHtml(item.title)}</h3>
            <p style="margin: 0; font-size: 11px; color: #627267;">
              ₹${Number(item.daily_fee).toFixed(0)}/day · ₹${Number(item.deposit_amount).toFixed(0)} deposit · 
              <span class="status-badge status-${item.listing_status.toLowerCase()}">${item.listing_status}</span>
            </p>
          </div>
          <div class="manage-actions" style="display: flex; gap: 6px;">
            <button type="button" class="btn-secondary-action" data-edit-item="${item.item_id}" style="padding: 6px 10px; font-size: 11px; border-radius: 6px; cursor: pointer;">Edit</button>
            <button type="button" class="delete-listing" data-delete-item="${item.item_id}" style="padding: 6px 10px; font-size: 11px; border-radius: 6px; cursor: pointer; color: #c53030; background: #fff0ef; border: 1px solid #fed7d7;">Archive</button>
          </div>
        </article>
      `).join("")}</div>`;
    } else {
      // Incoming Requests
      if (!incomingReqs.length) {
        container.innerHTML = `<div class="dialog-empty-state" style="text-align: center; padding: 30px 10px;">
          <div class="empty-symbol" style="font-size: 32px; color: #5e806d;">📬</div>
          <h3 style="margin: 8px 0;">No incoming borrow requests</h3>
          <p style="color: #66766d; font-size: 11px;">When students request your resources, they will appear here for your approval.</p>
        </div>`;
        return;
      }

      container.innerHTML = incomingReqs.map(req => `
        <div class="loan-card-item">
          <div class="loan-card-header">
            <h4 class="loan-card-title">${escapeHtml(req.item_title)}</h4>
            <span class="status-badge status-${req.status.toLowerCase()}">${req.status}</span>
          </div>
          <div class="loan-card-meta">
            <span><strong>Borrower:</strong> ${escapeHtml(req.borrower_name)} (${escapeHtml(req.borrower_roll || req.borrower_email)})</span>
            <span><strong>Requested Dates:</strong> ${formatDate(req.start_date)} → ${formatDate(req.end_date)} (${req.days_count} days)</span>
            <span><strong>Total Fee:</strong> ₹${Number(req.total_fee).toFixed(2)} + ₹${Number(req.deposit_amount).toFixed(2)} deposit</span>
            ${req.request_message ? `<span><strong>Note:</strong> “${escapeHtml(req.request_message)}”</span>` : ""}
          </div>
          ${req.status === "PENDING" ? `
            <div class="loan-actions-bar">
              <button type="button" class="btn-primary-action" data-approve-req="${req.request_id}">Approve Request <span>✓</span></button>
              <button type="button" class="btn-secondary-action" data-reject-req="${req.request_id}" style="color: #c53030;">Decline</button>
            </div>
          ` : `
            <p style="font-size: 10px; color: #88948b; margin: 4px 0 0;">Decided on ${formatDate(req.decided_at)}</p>
          `}
        </div>
      `).join("");
    }
  } catch (err) {
    container.innerHTML = `<p style="color: #c53030; font-size: 11px;">Failed to load data: ${err.message}</p>`;
  }
}

$("#tabMyItems")?.addEventListener("click", () => {
  state.activeListingTab = "my-items";
  renderMyListingsDialog();
});

$("#tabIncomingReqs")?.addEventListener("click", () => {
  state.activeListingTab = "incoming-requests";
  renderMyListingsDialog();
});

$("#myListingsDialog")?.addEventListener("click", async (e) => {
  const editBtn = e.target.closest("[data-edit-item]");
  const delBtn = e.target.closest("[data-delete-item]");
  const approveBtn = e.target.closest("[data-approve-req]");
  const rejectBtn = e.target.closest("[data-reject-req]");

  if (editBtn) {
    const id = Number(editBtn.dataset.editItem);
    try {
      const item = await apiFetch(`/api/items/${id}`);
      state.editingItemId = item.item_id;
      const form = $("#listForm");
      form.elements.title.value = item.title;
      form.elements.category_id.value = item.category_id;
      form.elements.description.value = item.description || "";
      form.elements.daily_fee.value = item.daily_fee;
      form.elements.deposit_amount.value = item.deposit_amount;
      form.elements.item_condition.value = item.item_condition || "GOOD";
      form.elements.max_borrow_days.value = item.max_borrow_days || 7;
      if (item.location_id) form.elements.location_id.value = item.location_id;

      state.uploadedImageUrls = item.images ? item.images.map(img => img.image_url) : [];
      renderImagePreviews();

      $("#listDialog").querySelector("h2").textContent = "Edit listing";
      $("#listDialog").querySelector(".modal-submit").innerHTML = "Save Changes <span>→</span>";

      $("#myListingsDialog").close();
      $("#listDialog").showModal();
    } catch (err) {
      toast(`Could not load item details: ${err.message}`, true);
    }
  }

  if (delBtn) {
    const id = Number(delBtn.dataset.deleteItem);
    if (!confirm("Are you sure you want to archive this listing? It will no longer appear in search.")) return;
    try {
      await apiFetch(`/api/items/${id}`, { method: "DELETE" });
      toast("Listing archived.");
      loadMarketplace();
      renderMyListingsDialog();
    } catch (err) {
      toast(`Archive failed: ${err.message}`, true);
    }
  }

  if (approveBtn) {
    const reqId = Number(approveBtn.dataset.approveReq);
    try {
      approveBtn.disabled = true;
      approveBtn.textContent = "Approving...";
      await apiFetch(`/api/borrow-requests/${reqId}/approve`, { method: "POST" });
      toast("Borrow request approved! Loan scheduled.");
      renderMyListingsDialog();
      fetchUserLoans();
    } catch (err) {
      toast(`Failed to approve: ${err.message}`, true);
      approveBtn.disabled = false;
      approveBtn.textContent = "Approve Request ✓";
    }
  }

  if (rejectBtn) {
    const reqId = Number(rejectBtn.dataset.rejectReq);
    const note = prompt("Optional reason for declining (will be shared with borrower):") || undefined;
    try {
      rejectBtn.disabled = true;
      await apiFetch(`/api/borrow-requests/${reqId}/reject`, {
        method: "POST",
        body: { decision_note: note }
      });
      toast("Request declined.");
      renderMyListingsDialog();
    } catch (err) {
      toast(`Action failed: ${err.message}`, true);
    }
  }
});

// ==========================================
// 9. MY LOANS & TWO-PARTY OTP LIFECYCLE
// ==========================================
function openLoansDialog() {
  if (!state.currentUser) {
    openAuth("login");
    showAuthMessage("Please sign in to view your loans.", "error");
    return;
  }
  state.activeLoanTab = "borrowed";
  renderLoansDialog();
  $("#loansDialog").showModal();
}

async function fetchUserLoans() {
  if (!state.token) return;
  try {
    const loans = await apiFetch("/api/loans");
    updateHomepageLoanPreview(loans);
    return loans;
  } catch (err) {
    console.warn("Could not fetch loans:", err);
  }
}

function updateHomepageLoanPreview(loans) {
  const container = $(".next-loan");
  if (!container) return;

  const borrowed = loans.borrowed || [];
  const activeOrSched = borrowed.find(l => ["SCHEDULED", "ACTIVE", "APPROVED"].includes(l.status));

  if (!activeOrSched) {
    container.innerHTML = `
      <div class="next-loan-heading">
        <div><span class="section-kicker">YOUR BORROWHUB</span><h2>Your next loan</h2></div>
        <button class="text-button" id="myLoansBtn">View all →</button>
      </div>
      <div class="loan-empty">
        <span class="loan-empty-icon">▤</span>
        <strong>Your loans will appear here</strong>
        <p>Once you request an item and its owner approves, your loan details will be shown here.</p>
      </div>
    `;
    $("#myLoansBtn")?.addEventListener("click", openLoansDialog);
    return;
  }

  container.innerHTML = `
    <div class="next-loan-heading">
      <div><span class="section-kicker">ACTIVE BORROWING</span><h2>${escapeHtml(activeOrSched.item_title)}</h2></div>
      <button class="text-button" id="myLoansBtn">View all →</button>
    </div>
    <div class="loan-preview">
      <div class="loan-thumb">📦</div>
      <div class="loan-info">
        <strong>${formatDate(activeOrSched.issued_at || activeOrSched.start_date || new Date())}</strong>
        <span>Owner: ${escapeHtml(activeOrSched.owner_name)}</span>
      </div>
      <span class="status-pill">${activeOrSched.status}</span>
    </div>
  `;
  $("#myLoansBtn")?.addEventListener("click", openLoansDialog);
}

async function renderLoansDialog() {
  $("#tabBorrowedLoans").classList.toggle("active", state.activeLoanTab === "borrowed");
  $("#tabLentLoans").classList.toggle("active", state.activeLoanTab === "lent");

  const container = $("#loansContent");
  container.innerHTML = `<p style="text-align: center; color: #718078; padding: 20px;">Loading loans...</p>`;

  try {
    const data = await apiFetch("/api/loans");
    const borrowed = data.borrowed || [];
    const lent = data.lent || [];

    $("#borrowedCount").textContent = borrowed.length;
    $("#lentCount").textContent = lent.length;

    const list = state.activeLoanTab === "borrowed" ? borrowed : lent;
    const isBorrowerView = state.activeLoanTab === "borrowed";

    if (!list.length) {
      container.innerHTML = `<div class="dialog-empty-state" style="text-align: center; padding: 30px 10px;">
        <div class="empty-symbol" style="font-size: 32px; color: #5e806d;">▤</div>
        <h3 style="margin: 8px 0;">No ${state.activeLoanTab} loans found</h3>
        <p style="color: #66766d; font-size: 11px;">Active handovers, OTP codes, and return settlements will appear here.</p>
      </div>`;
      return;
    }

    container.innerHTML = list.map(l => {
      let actionsMarkup = "";

      if (isBorrowerView) {
        // Borrower actions
        if (l.status === "SCHEDULED") {
          const totalPayable = Number(l.agreed_total_fee || 0) + Number(l.agreed_deposit || 0);
          actionsMarkup += `
            <div class="scheduled-handover-card" style="background: #fafcfb; border: 1px solid #cce5d6; border-radius: 12px; padding: 14px; margin-top: 6px;">
              <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <span style="font-size: 11px; font-weight: 700; color: #174d40; text-transform: uppercase; letter-spacing: 0.5px;">🤝 In-Person Handover &amp; Payment</span>
                <span style="font-size: 12px; font-weight: 700; color: #8c2d19; background: #faece7; padding: 2px 8px; border-radius: 6px;">Pay ₹${totalPayable.toFixed(0)}</span>
              </div>
              <p style="margin: 0 0 10px; font-size: 11.5px; color: #40584c; line-height: 1.4;">
                Meet <strong>${escapeHtml(l.owner_name)}</strong> on campus. Pay <strong>₹${totalPayable.toFixed(0)}</strong> (rental: ₹${Number(l.agreed_total_fee).toFixed(0)} + deposit: ₹${Number(l.agreed_deposit).toFixed(0)}) directly via cash or UPI upon meetup, then share your secret Handover OTP below to collect the item.
              </p>
              ${l.handover_otp ? `
                <div class="otp-box" style="margin: 0 auto; text-align: center; background: #ffffff; border: 1.5px dashed #8c2d19; padding: 10px; border-radius: 10px;">
                  <small style="display: block; font-size: 10.5px; font-weight: 600; color: #8c2d19; margin-bottom: 4px;">YOUR SECRET HANDOVER OTP (Give to owner at meetup):</small>
                  <span class="otp-code" style="font-size: 24px; font-weight: 800; letter-spacing: 6px; color: #8c2d19;">${l.handover_otp}</span>
                </div>
              ` : `
                <div style="font-size: 11px; color: #66766d;">OTP will be displayed here for pickup.</div>
              `}
            </div>
          `;
        } else if (l.status === "ACTIVE") {
          if (l.return_otp) {
            actionsMarkup += `
              <div class="otp-box" style="margin: 6px 0; background: #ffffff; border: 1.5px dashed #174d40; padding: 10px; border-radius: 10px; text-align: center;">
                <small style="display: block; font-size: 10.5px; font-weight: 600; color: #174d40; margin-bottom: 4px;">YOUR SECRET RETURN OTP (Share when returning item):</small>
                <span class="otp-code" style="font-size: 24px; font-weight: 800; letter-spacing: 6px; color: #174d40;">${l.return_otp}</span>
              </div>
            `;
          }
          actionsMarkup += `
            <button type="button" class="btn-warning-action" data-dispute-loan="${l.loan_id}">Report Issue / Dispute ⚠</button>
          `;
        } else if (l.status === "RETURNED") {
          actionsMarkup += `
            <button type="button" class="btn-secondary-action" data-review-loan="${l.loan_id}">Leave a Review ★</button>
          `;
        }
      } else {
        // Owner/Lender actions
        if (l.status === "SCHEDULED") {
          const totalToCollect = Number(l.agreed_total_fee || 0) + Number(l.agreed_deposit || 0);
          actionsMarkup += `
            <div style="background: #fafcfb; border: 1px solid #cce5d6; border-radius: 12px; padding: 14px; margin-top: 6px;">
              <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                <span style="font-size: 11px; font-weight: 700; color: #174d40; text-transform: uppercase; letter-spacing: 0.5px;">🤝 Handover Scheduled</span>
                <span style="font-size: 12px; font-weight: 700; color: #174d40; background: #e2f1e8; padding: 2px 8px; border-radius: 6px;">Collect ₹${totalToCollect.toFixed(0)}</span>
              </div>
              <p style="margin: 0 0 10px; font-size: 11.5px; color: #40584c; line-height: 1.4;">
                Meet <strong>${escapeHtml(l.borrower_name)}</strong> on campus. Collect <strong>₹${totalToCollect.toFixed(0)}</strong> (rental: ₹${Number(l.agreed_total_fee).toFixed(0)} + deposit: ₹${Number(l.agreed_deposit).toFixed(0)}) in cash or direct UPI, and enter their 6-digit Handover OTP to confirm payment and handover the item.
              </p>
              <button type="button" class="btn-primary-action" data-verify-handover="${l.loan_id}" style="width: 100%;">Verify Handover &amp; Confirm Payment 🤝</button>
            </div>
          `;
        } else if (l.status === "ACTIVE") {
          actionsMarkup += `
            <button type="button" class="btn-primary-action" data-verify-return="${l.loan_id}">Verify Return &amp; Settle Deposit 🤝</button>
            <button type="button" class="btn-warning-action" data-dispute-loan="${l.loan_id}">Report Damage / Dispute ⚠</button>
          `;
        } else if (l.status === "RETURNED") {
          actionsMarkup += `
            <button type="button" class="btn-secondary-action" data-review-loan="${l.loan_id}">Rate Borrower ★</button>
          `;
        }
      }

      return `
        <div class="loan-card-item">
          <div class="loan-card-header">
            <h4 class="loan-card-title">${escapeHtml(l.item_title)}</h4>
            <span class="status-badge status-${l.status.toLowerCase()}">${l.status}</span>
          </div>
          <div class="loan-card-meta">
            <span><strong>${isBorrowerView ? 'Owner' : 'Borrower'}:</strong> ${escapeHtml(isBorrowerView ? l.owner_name : l.borrower_name)}</span>
            <span><strong>Rental Fee:</strong> ₹${Number(l.agreed_total_fee).toFixed(2)} · <strong>Deposit:</strong> ₹${Number(l.agreed_deposit).toFixed(2)} (${l.deposit_status})</span>
            <span><strong>Due Date:</strong> ${formatDate(l.due_date)}</span>
          </div>
          <div class="loan-actions-bar">
            ${actionsMarkup}
          </div>
        </div>
      `;
    }).join("");
  } catch (err) {
    container.innerHTML = `<p style="color: #c53030; font-size: 11px;">Failed to load loans: ${err.message}</p>`;
  }
}

$("#tabBorrowedLoans")?.addEventListener("click", () => {
  state.activeLoanTab = "borrowed";
  renderLoansDialog();
});

$("#tabLentLoans")?.addEventListener("click", () => {
  state.activeLoanTab = "lent";
  renderLoansDialog();
});

// Handover & Return Verification Modal Triggers
$("#loansDialog")?.addEventListener("click", (e) => {
  const handoverBtn = e.target.closest("[data-verify-handover]");
  const returnBtn = e.target.closest("[data-verify-return]");
  const disputeBtn = e.target.closest("[data-dispute-loan]");
  const reviewBtn = e.target.closest("[data-review-loan]");

  if (handoverBtn) {
    const loanId = Number(handoverBtn.dataset.verifyHandover);
    openHandoverModal(loanId);
  }

  if (returnBtn) {
    const loanId = Number(returnBtn.dataset.verifyReturn);
    openReturnModal(loanId);
  }

  if (disputeBtn) {
    const loanId = Number(disputeBtn.dataset.disputeLoan);
    openDisputeModal(loanId);
  }

  if (reviewBtn) {
    const loanId = Number(reviewBtn.dataset.reviewLoan);
    openReviewModal(loanId);
  }
});

// ==========================================
// 10. ACTION MODALS (OTP, HANDOVER, RETURN, REVIEWS)
// ==========================================
function openActionModal(title, html) {
  const dialog = $("#actionDialog");
  const content = $("#actionDialogContent");
  content.innerHTML = `
    <h2>${title}</h2>
    ${html}
  `;
  dialog.showModal();
}

// Handover verification (Owner verifies borrower's OTP and confirms payment)
async function openHandoverModal(loanId) {
  openActionModal("Verify Handover & Confirm Payment", `
    <div style="text-align: center; padding: 24px 10px; color: #556b60;">
      <p style="margin: 0; font-size: 13px;">Loading loan and payment details...</p>
    </div>
  `);

  try {
    const loan = await apiFetch(`/api/loans/${loanId}`);
    const rental = Number(loan.agreed_total_fee || 0);
    const deposit = Number(loan.agreed_deposit || 0);
    const total = rental + deposit;
    const borrowerName = loan.borrower_name || "Borrower";
    const itemTitle = loan.item_title || "Item";

    const content = $("#actionDialogContent");
    if (!content) return;

    content.innerHTML = `
      <h2>Verify Handover &amp; Confirm Payment</h2>
      <p class="modal-subtitle">Meet <strong>${escapeHtml(borrowerName)}</strong> on campus, collect the payment, and verify their 6-digit Handover OTP to confirm and start the loan.</p>
      
      <div style="background: #f7faf8; border: 1px solid #d5e5db; border-radius: 12px; padding: 14px 16px; margin: 14px 0 18px;">
        <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px;">
          <span style="color: #556b60;">Borrower:</span>
          <strong>${escapeHtml(borrowerName)}</strong>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px;">
          <span style="color: #556b60;">Resource:</span>
          <strong>${escapeHtml(itemTitle)}</strong>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px;">
          <span style="color: #556b60;">Rental Fee:</span>
          <span>₹${rental.toFixed(2)}</span>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 6px;">
          <span style="color: #556b60;">Refundable Security Deposit:</span>
          <span>₹${deposit.toFixed(2)}</span>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 13.5px; font-weight: 700; color: #174d40; border-top: 1px dashed #c0d8cc; padding-top: 8px; margin-top: 6px;">
          <span>Total to Collect (Cash or direct UPI):</span>
          <span style="color: #8c2d19; font-size: 16px;">₹${total.toFixed(2)}</span>
        </div>
      </div>

      <div id="handoverModalError" class="auth-inline-message error" style="display:none; margin-bottom: 12px;"></div>

      <form id="handoverForm" novalidate>
        <label class="form-field">
          <span>Borrower's 6-digit Handover OTP (from their screen)</span>
          <input name="otp" id="handoverOtpInput" type="text" maxlength="6" required placeholder="• • • • • •" autocomplete="off" style="font-size: 22px; letter-spacing: 6px; text-align: center; font-weight: 700;">
        </label>
        <label class="form-field">
          <span>Inspected Item Condition at Handover</span>
          <select name="condition">
            <option value="GOOD">GOOD</option>
            <option value="NEW">NEW</option>
            <option value="FAIR">FAIR</option>
            <option value="WORN">WORN</option>
          </select>
        </label>
        <label class="form-field">
          <span>Handover Notes (optional)</span>
          <input name="notes" placeholder="e.g. Received ₹${total.toFixed(0)}, handed over item in good condition.">
        </label>
        <div id="handoverModalBottomError" class="auth-inline-message error" style="display:none; margin-bottom: 12px;"></div>
        <button class="primary-button modal-submit" type="submit">Confirm Handover &amp; Payment Received 🤝</button>
      </form>
    `;

    function showHandoverError(msg) {
      const topErr = $("#handoverModalError");
      const btmErr = $("#handoverModalBottomError");
      if (topErr) { topErr.textContent = msg; topErr.style.display = "block"; }
      if (btmErr) { btmErr.textContent = msg; btmErr.style.display = "block"; }
    }

    function clearHandoverError() {
      const topErr = $("#handoverModalError");
      const btmErr = $("#handoverModalBottomError");
      if (topErr) { topErr.textContent = ""; topErr.style.display = "none"; }
      if (btmErr) { btmErr.textContent = ""; btmErr.style.display = "none"; }
    }

    $("#handoverForm")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearHandoverError();

      const form = new FormData(e.currentTarget);
      const otp = String(form.get("otp")).trim();
      const condition = String(form.get("condition"));
      const notes = String(form.get("notes") || "");

      if (!otp || otp.length !== 6) {
        showHandoverError("Please enter the complete 6-digit Handover OTP.");
        $("#handoverOtpInput")?.focus();
        return;
      }

      const submitBtn = e.currentTarget.querySelector(".modal-submit");
      try {
        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.textContent = "Verifying Handover & Payment...";
        }

        await apiFetch(`/api/loans/${loanId}/verify-handover`, {
          method: "POST",
          body: {
            handover_otp: otp,
            inspected_condition: condition,
            notes
          }
        });

        // Show payment & handover confirmed screen directly in the front
        content.innerHTML = `
          <div style="text-align: center; padding: 22px 10px;">
            <div style="font-size: 42px; color: #2e7d32; margin-bottom: 8px;">✓</div>
            <h3 style="margin: 0 0 6px; color: #1e5a23; font-size: 20px;">Payment &amp; Handover Confirmed!</h3>
            <p style="margin: 0 0 14px; font-size: 13px; color: #3b5e40;">Payment of <strong>₹${total.toFixed(2)}</strong> received &amp; verified. Loan is now <strong>ACTIVE</strong>.</p>
            <div style="background: #f0f7f3; border: 1px solid #cce5d6; border-radius: 12px; padding: 14px; margin-bottom: 18px; text-align: left; font-size: 12px; color: #254d2b; line-height: 1.6;">
              <div>• <strong>Resource:</strong> ${escapeHtml(itemTitle)}</div>
              <div>• <strong>Borrower:</strong> ${escapeHtml(borrowerName)}</div>
              <div>• <strong>Security Deposit:</strong> ₹${deposit.toFixed(2)} (Status: HELD)</div>
              <div>• <strong>Due Date:</strong> ${formatDate(loan.due_date)}</div>
            </div>
            <button type="button" class="primary-button" id="btnHandoverSuccessDone" style="width: 100%;">Done <span>→</span></button>
          </div>
        `;

        $("#btnHandoverSuccessDone")?.addEventListener("click", () => {
          $("#actionDialog").close();
          renderLoansDialog();
          fetchUserLoans();
        });

        renderLoansDialog();
        fetchUserLoans();
      } catch (err) {
        showHandoverError(`Verification failed: ${err.message}`);
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = "Confirm Handover & Payment Received 🤝";
        }
      }
    });
  } catch (err) {
    const content = $("#actionDialogContent");
    if (content) {
      content.innerHTML = `
        <h2>Error Loading Loan</h2>
        <div class="auth-inline-message error">${escapeHtml(err.message)}</div>
      `;
    }
  }
}

// Return verification (Owner verifies borrower's Return OTP & settles deposit)
function openReturnModal(loanId) {
  openActionModal("Verify Return & Settle Deposit", `
    <p class="modal-subtitle">Inspect the returned item and enter the borrower's Return OTP.</p>
    <div id="returnModalError" class="auth-inline-message error" style="display:none; margin-bottom: 12px;"></div>
    <form id="returnForm" novalidate>
      <label class="form-field">
        <span>Borrower's 6-digit Return OTP</span>
        <input name="otp" id="returnOtpInput" type="text" maxlength="6" required placeholder="e.g. 654321" autocomplete="off" style="font-size: 18px; letter-spacing: 4px; text-align: center;">
      </label>
      <label class="form-field">
        <span>Inspected Condition</span>
        <select name="condition">
          <option value="GOOD">GOOD (No damage)</option>
          <option value="NEW">NEW</option>
          <option value="FAIR">FAIR</option>
          <option value="WORN">WORN</option>
          <option value="DAMAGED">DAMAGED</option>
        </select>
      </label>
      <div class="form-row">
        <label class="form-field">
          <span>Damage deduction (₹)</span>
          <input name="damage_fee" type="number" min="0" step="1" value="0">
        </label>
        <label class="form-field">
          <span>Late fee deduction (₹)</span>
          <input name="late_fee" type="number" min="0" step="1" value="0">
        </label>
      </div>
      <label class="form-field">
        <span>Return Notes</span>
        <input name="notes" placeholder="e.g. Returned on time in perfect condition.">
      </label>
      <div id="returnModalBottomError" class="auth-inline-message error" style="display:none; margin-bottom: 12px;"></div>
      <button class="primary-button modal-submit" type="submit">Verify Return &amp; Release Deposit <span>→</span></button>
    </form>
  `);

  function showReturnError(msg) {
    const topErr = $("#returnModalError");
    const btmErr = $("#returnModalBottomError");
    if (topErr) { topErr.textContent = msg; topErr.style.display = "block"; }
    if (btmErr) { btmErr.textContent = msg; btmErr.style.display = "block"; }
  }

  function clearReturnError() {
    const topErr = $("#returnModalError");
    const btmErr = $("#returnModalBottomError");
    if (topErr) { topErr.textContent = ""; topErr.style.display = "none"; }
    if (btmErr) { btmErr.textContent = ""; btmErr.style.display = "none"; }
  }

  $("#returnForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearReturnError();

    const form = new FormData(e.currentTarget);
    const otp = String(form.get("otp")).trim();
    const condition = String(form.get("condition"));
    const notes = String(form.get("notes") || "");
    const damage = Number(form.get("damage_fee") || 0);
    const late = Number(form.get("late_fee") || 0);

    if (!otp || otp.length !== 6) {
      showReturnError("Please enter the complete 6-digit Return OTP.");
      $("#returnOtpInput")?.focus();
      return;
    }

    try {
      const submitBtn = e.currentTarget.querySelector(".modal-submit");
      submitBtn.disabled = true;
      submitBtn.textContent = "Verifying...";

      // 1. Verify return OTP
      await apiFetch(`/api/loans/${loanId}/verify-return`, {
        method: "POST",
        body: {
          return_otp: otp,
          inspected_condition: condition,
          notes
        }
      });

      // 2. Settle deposit
      await apiFetch(`/api/loans/${loanId}/settle-deposit`, {
        method: "POST",
        body: {
          deduct_amount: Number(damage || 0) + Number(late || 0),
          damage_fee_deduction: damage,
          late_fee_deduction: late,
          settlement_reason: notes || "Full deposit refund",
          refund_method: "UPI"
        }
      });

      const content = $("#actionDialogContent");
      if (content) {
        content.innerHTML = `
          <div style="text-align: center; padding: 22px 10px;">
            <div style="font-size: 42px; color: #2e7d32; margin-bottom: 8px;">✓</div>
            <h3 style="margin: 0 0 6px; color: #1e5a23; font-size: 20px;">Return Verified &amp; Settled!</h3>
            <p style="margin: 0 0 14px; font-size: 13px; color: #3b5e40;">Return inspected and verified. Security deposit settled successfully.</p>
            <button type="button" class="primary-button" id="btnReturnSuccessDone" style="width: 100%;">Done <span>→</span></button>
          </div>
        `;
        $("#btnReturnSuccessDone")?.addEventListener("click", () => {
          $("#actionDialog").close();
          renderLoansDialog();
          fetchUserLoans();
        });
      } else {
        $("#actionDialog").close();
      }

      renderLoansDialog();
      fetchUserLoans();
    } catch (err) {
      showReturnError(`Return verification failed: ${err.message}`);
      const submitBtn = e.currentTarget.querySelector(".modal-submit");
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = "Verify Return & Release Deposit →";
      }
    }
  });
}

// Review modal
function openReviewModal(loanId) {
  let selectedStars = 5;

  openActionModal("Leave Campus Review", `
    <p class="modal-subtitle">Help build trust in the SVNIT student community.</p>
    <div id="reviewModalError" class="auth-inline-message error" style="display:none; margin-bottom: 12px;"></div>
    <form id="reviewForm" novalidate>
      <div style="text-align: center; margin-bottom: 12px;">
        <div class="star-rating-select" id="starContainer">
          <span data-star="1" class="selected">★</span>
          <span data-star="2" class="selected">★</span>
          <span data-star="3" class="selected">★</span>
          <span data-star="4" class="selected">★</span>
          <span data-star="5" class="selected">★</span>
        </div>
        <small id="starLabel" style="color: #64756b; font-weight: 700;">5 / 5 — Excellent Experience</small>
      </div>
      <label class="form-field">
        <span>Review Comments *</span>
        <textarea name="comment" id="reviewCommentInput" rows="3" required placeholder="Punctuality, item condition, communication..."></textarea>
      </label>
      <button class="primary-button modal-submit" type="submit">Submit Review <span>→</span></button>
    </form>
  `);

  const stars = $$("#starContainer span");
  const starLabel = $("#starLabel");

  stars.forEach(s => {
    s.addEventListener("click", () => {
      selectedStars = Number(s.dataset.star);
      stars.forEach(st => {
        st.classList.toggle("selected", Number(st.dataset.star) <= selectedStars);
      });
      starLabel.textContent = `${selectedStars} / 5 stars`;
    });
  });

  $("#reviewForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const comment = e.currentTarget.elements.comment.value.trim();

    if (!comment || comment.length < 3) {
      const errBox = $("#reviewModalError");
      if (errBox) {
        errBox.textContent = "Please enter a comment sharing your experience.";
        errBox.style.display = "block";
      }
      $("#reviewCommentInput")?.focus();
      return;
    }

    try {
      await apiFetch("/api/reviews", {
        method: "POST",
        body: {
          loan_id: loanId,
          rating: selectedStars,
          review_text: comment
        }
      });
      $("#actionDialog").close();
      toast("Thank you! Review submitted.");
    } catch (err) {
      const errBox = $("#reviewModalError");
      if (errBox) {
        errBox.textContent = `Review failed: ${err.message}`;
        errBox.style.display = "block";
      }
    }
  });
}

// Dispute modal with inline error validation and photo proof uploads
function openDisputeModal(loanId) {
  const disputeEvidenceUrls = [];

  openActionModal("Report Issue / Dispute", `
    <p class="modal-subtitle">Submit a damage claim or violation to campus administration for mediation and deposit settlement.</p>
    <div id="disputeInlineError" class="auth-inline-message error" style="display:none; margin-bottom: 12px;"></div>
    <form id="disputeForm" novalidate>
      <label class="form-field">
        <span>Dispute Reason *</span>
        <select name="reason" id="disputeReasonSelect" required>
          <option value="DAMAGE">Item Damaged / Broken Hardware</option>
          <option value="NO_SHOW">Item Not Returned / No-show</option>
          <option value="LATE_RETURN">Late Return Without Prior Notice</option>
          <option value="NON_PAYMENT">Deposit Deduction Disagreement</option>
          <option value="OTHER">Other Campus Violation</option>
        </select>
      </label>
      <label class="form-field">
        <span>Claimed Damage Amount (₹)</span>
        <input name="claimed_amount" id="disputeAmountInput" type="number" min="0" step="10" placeholder="e.g. 250">
        <small style="color: #718078; font-size: 10px;">Amount needed for repair or replacement from the held deposit.</small>
      </label>
      <label class="form-field">
        <span>Description of Issue * (Min 10 characters)</span>
        <textarea name="description" id="disputeDescInput" rows="3" required placeholder="Describe what happened with clear details (what was broken, condition upon return, etc.)..."></textarea>
        <small id="disputeDescCounter" style="color: #718078; font-size: 10px;">Please provide at least 10 characters.</small>
      </label>
      <label class="form-field">
        <span>Upload Photo Proof of Damage / Receipts (Max 3)</span>
        <input type="file" id="disputeProofInput" accept="image/jpeg,image/png,image/webp" multiple style="padding: 8px;">
        <div id="disputeProofPreviews" class="image-upload-preview" style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px;"></div>
      </label>
      <div id="disputeFormBottomMessage" class="auth-inline-message error" style="display:none; margin-bottom: 12px;"></div>
      <button class="primary-button modal-submit" id="disputeSubmitBtn" type="submit">Submit Dispute to Admin <span>→</span></button>
    </form>
  `);

  const descInput = $("#disputeDescInput");
  const counter = $("#disputeDescCounter");
  descInput?.addEventListener("input", () => {
    const len = descInput.value.trim().length;
    if (counter) {
      if (len < 10) {
        counter.textContent = `${len}/10 characters minimum`;
        counter.style.color = "#dc2626";
      } else {
        counter.textContent = `${len} characters entered (Valid)`;
        counter.style.color = "#15803d";
      }
    }
  });

  const proofInput = $("#disputeProofInput");
  const previewsContainer = $("#disputeProofPreviews");

  function renderDisputePreviews() {
    if (!previewsContainer) return;
    previewsContainer.innerHTML = disputeEvidenceUrls.map((url, idx) => `
      <div class="preview-item" style="position: relative; display: inline-block;">
        <img src="${escapeHtml(url)}" alt="Damage proof" style="width: 60px; height: 60px; object-fit: cover; border-radius: 6px; border: 1px solid #d1d5db;">
        <button type="button" class="remove-img" data-idx="${idx}" style="position: absolute; top: -6px; right: -6px; width: 18px; height: 18px; border-radius: 50%; background: #dc2626; color: #fff; border: none; font-size: 12px; cursor: pointer; display: flex; align-items: center; justify-content: center;">×</button>
      </div>
    `).join("");

    previewsContainer.querySelectorAll(".remove-img").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const idx = Number(e.currentTarget.dataset.idx);
        disputeEvidenceUrls.splice(idx, 1);
        renderDisputePreviews();
      });
    });
  }

  proofInput?.addEventListener("change", async (e) => {
    const files = [...e.target.files];
    if (!files.length) return;
    if (disputeEvidenceUrls.length + files.length > 3) {
      showDisputeInlineError("Maximum 3 photo evidence files allowed.");
      return;
    }
    for (const file of files) {
      try {
        const url = await uploadImageFile(file);
        disputeEvidenceUrls.push(url);
        renderDisputePreviews();
      } catch (err) {
        showDisputeInlineError(`Photo upload failed: ${err.message}`);
      }
    }
    proofInput.value = "";
  });

  function showDisputeInlineError(msg) {
    const topErr = $("#disputeInlineError");
    const btmErr = $("#disputeFormBottomMessage");
    if (topErr) { topErr.textContent = msg; topErr.style.display = "block"; }
    if (btmErr) { btmErr.textContent = msg; btmErr.style.display = "block"; }
  }

  function clearDisputeInlineError() {
    const topErr = $("#disputeInlineError");
    const btmErr = $("#disputeFormBottomMessage");
    if (topErr) { topErr.textContent = ""; topErr.style.display = "none"; }
    if (btmErr) { btmErr.textContent = ""; btmErr.style.display = "none"; }
  }

  $("#disputeForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearDisputeInlineError();

    const form = new FormData(e.currentTarget);
    const reason = String(form.get("reason") || "DAMAGE");
    const claimed_raw = form.get("claimed_amount");
    const claimed_amount = claimed_raw ? Number(claimed_raw) : 0;
    const description = String(form.get("description") || "").trim();

    if (!description || description.length < 10) {
      showDisputeInlineError(`Please enter at least 10 characters describing the issue (currently ${description.length} characters).`);
      $("#disputeDescInput")?.focus();
      return;
    }

    const submitBtn = $("#disputeSubmitBtn");
    try {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Submitting dispute...";
      }

      await apiFetch("/api/disputes", {
        method: "POST",
        body: {
          loan_id: loanId,
          dispute_type: reason,
          amount_claimed: claimed_amount,
          description: description,
          evidence_urls: disputeEvidenceUrls
        }
      });

      $("#actionDialog").close();
      toast("Damage claim reported! Campus administration has been notified with your evidence.");
      renderLoansDialog();
    } catch (err) {
      showDisputeInlineError(`Dispute submission failed: ${err.message}`);
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = "Submit Dispute to Admin <span>→</span>";
      }
    }
  });
}

// ==========================================
// 11. NOTIFICATIONS DIALOG
// ==========================================
async function openNotificationsDialog() {
  if (!state.currentUser) {
    openAuth("login");
    showAuthMessage("Please sign in to view notifications.", "error");
    return;
  }

  const listContainer = $("#notificationsList");
  listContainer.innerHTML = `<p style="text-align: center; color: #718078; padding: 20px;">Loading...</p>`;
  $("#notificationsDialog").showModal();

  try {
    const notifs = await apiFetch("/api/notifications");
    if (!notifs.length) {
      listContainer.innerHTML = `<div class="dialog-empty-state" style="text-align: center; padding: 30px 10px;">
        <div class="empty-symbol" style="font-size: 32px; color: #5e806d;">♧</div>
        <h3 style="margin: 8px 0;">You're all caught up!</h3>
        <p style="color: #66766d; font-size: 11px;">No unread notifications at this time.</p>
      </div>`;
      return;
    }

    listContainer.innerHTML = notifs.map(n => `
      <div class="notif-card ${n.is_read ? '' : 'unread'}" data-notif-id="${n.notif_id}">
        <div class="notif-icon">♧</div>
        <div class="notif-content">
          <div class="notif-title">${escapeHtml(n.title)}</div>
          <p class="notif-msg">${escapeHtml(n.message)}</p>
          <span class="notif-time">${formatDate(n.created_at)}</span>
        </div>
      </div>
    `).join("");

    // Mark notifications read
    const unread = notifs.filter(n => !n.is_read);
    for (const u of unread) {
      apiFetch(`/api/notifications/${u.notif_id}/read`, { method: "POST" }).catch(() => {});
    }
    const badge = $("#notificationCount");
    if (badge) badge.hidden = true;
  } catch (err) {
    listContainer.innerHTML = `<p style="color: #c53030; font-size: 11px;">Error: ${err.message}</p>`;
  }
}

$("#markAllReadBtn")?.addEventListener("click", () => {
  $$(".notif-card.unread").forEach(c => c.classList.remove("unread"));
  const badge = $("#notificationCount");
  if (badge) badge.hidden = true;
  apiFetch("/api/notifications/read-all", { method: "POST" }).catch(() => {});
  toast("All marked as read.");
});

// ==========================================
// 12. EVENT LISTENERS & WIRING
// ==========================================
// Global click handling
document.addEventListener("click", (e) => {
  // Open item modal
  const openItemBtn = e.target.closest("[data-open-item]");
  if (openItemBtn) {
    e.preventDefault();
    openItem(openItemBtn.dataset.openItem);
    return;
  }

  // Favorite toggle
  const favBtn = e.target.closest("[data-favorite]");
  if (favBtn) {
    e.preventDefault();
    handleFavoriteToggle(Number(favBtn.dataset.favorite));
    return;
  }

  // Listing trigger
  const listingTrigger = e.target.closest("[data-open-listing]");
  if (listingTrigger) {
    openList();
    return;
  }
});

async function handleFavoriteToggle(itemId) {
  if (!state.currentUser) {
    openAuth("login");
    showAuthMessage("Please sign in to save favorite items.", "error");
    return;
  }

  try {
    const res = await apiFetch(`/api/items/${itemId}/favorite`, { method: "POST" });
    if (res.is_favorite) {
      state.favorites.add(itemId);
      toast("Saved to your favorites ♥");
    } else {
      state.favorites.delete(itemId);
      toast("Removed from favorites");
    }

    // Update heart icons across UI
    $$(`[data-favorite="${itemId}"]`).forEach(btn => {
      btn.classList.toggle("is-favorite", res.is_favorite);
      btn.innerHTML = btn.tagName === "BUTTON" && btn.classList.contains("outline-button")
        ? (res.is_favorite ? "♥ Saved" : "♡ Save item")
        : (res.is_favorite ? "♥" : "♡");
    });
  } catch (err) {
    toast(`Could not update favorite: ${err.message}`, true);
  }
}

// ==========================================
// 12. ADMIN MANAGEMENT & DAMAGED ITEM TRACKING
// ==========================================
let currentAdminTab = "disputes";

async function openAdminDashboard() {
  if (!state.currentUser) {
    openAuth("login");
    showAuthMessage("Please sign in as admin to access the management portal.", "error");
    return;
  }
  const dialog = $("#adminDashboardDialog");
  if (!dialog) return;
  if (!dialog.open) dialog.showModal();
  loadAdminStats();
  switchAdminTab("disputes");
}
window.openAdminDashboard = openAdminDashboard;

function switchAdminTab(tab) {
  currentAdminTab = tab;
  $("#tabAdminDisputes")?.classList.toggle("active", tab === "disputes");
  $("#tabAdminLoans")?.classList.toggle("active", tab === "loans");
  $("#tabAdminItems")?.classList.toggle("active", tab === "items");

  const dispList = $("#adminDisputesList");
  const loanList = $("#adminLoansList");
  const itemList = $("#adminItemsList");
  if (dispList) dispList.hidden = tab !== "disputes";
  if (loanList) loanList.hidden = tab !== "loans";
  if (itemList) itemList.hidden = tab !== "items";

  if (tab === "disputes") loadAdminDisputes();
  else if (tab === "loans") loadAdminLoans();
  else if (tab === "items") loadAdminItems();
}

async function loadAdminStats() {
  try {
    const stats = await apiFetch("/api/admin/stats");
    if ($("#adminKpiDisputes")) $("#adminKpiDisputes").textContent = stats.pending_disputes || 0;
    if ($("#adminKpiDeposits")) $("#adminKpiDeposits").textContent = `₹${Number(stats.total_held_deposits || 0).toLocaleString("en-IN")}`;
    if ($("#adminKpiLoans")) $("#adminKpiLoans").textContent = stats.active_loans || 0;
    if ($("#adminKpiStudents")) $("#adminKpiStudents").textContent = stats.total_students || 0;
  } catch (err) {
    console.warn("Could not load admin stats:", err);
  }
}

async function loadAdminDisputes() {
  const container = $("#adminDisputesList");
  if (!container) return;
  container.innerHTML = `<p style="text-align: center; color: #888; padding: 24px;">Loading damage claims...</p>`;

  try {
    const disputes = await apiFetch("/api/admin/disputes");
    if ($("#adminDisputesCount")) $("#adminDisputesCount").textContent = disputes.length;

    if (!disputes.length) {
      container.innerHTML = `<div style="text-align: center; padding: 36px 12px; color: #58695e;">
        <div style="font-size: 32px; margin-bottom: 8px;">✅</div>
        <h3>No Open Damage Claims or Disputes</h3>
        <p style="font-size: 12px; color: #718078;">All campus item loans are proceeding smoothly without reported damages.</p>
      </div>`;
      return;
    }

    container.innerHTML = disputes.map(d => {
      const isDamage = d.dispute_type === "DAMAGE";
      const statusClass = (d.status || "").toLowerCase();
      const canResolve = d.status === "OPEN" || d.status === "UNDER_REVIEW";

      return `
        <div class="admin-record-card" data-dispute-id="${d.dispute_id}">
          <div class="admin-record-header">
            <div>
              <span class="admin-status-pill ${statusClass}">${escapeHtml(d.status)}</span>
              <strong style="margin-left: 8px; font-size: 13px; color: ${isDamage ? '#b91c1c' : '#2d4c3c'};">
                ${isDamage ? '⚠️ DAMAGED ITEM CLAIM' : escapeHtml(d.dispute_type)}
              </strong>
              <small style="color: #718078; margin-left: 6px;">(Dispute #${d.dispute_id} · Loan #${d.loan_id})</small>
            </div>
            <span style="font-size: 11px; color: #718078;">${formatDate(d.created_at)}</span>
          </div>

          <div class="admin-record-body">
            <div style="margin-bottom: 4px;">
              <strong>Raiser:</strong> ${escapeHtml(d.raised_by_name)} <span style="color: #66766d;">&nbsp;vs&nbsp;</span> <strong>Counterparty:</strong> ${escapeHtml(d.against_user_name)}
            </div>
            <div style="margin-bottom: 6px;">
              <strong>Claimed Damage Amount:</strong> <span style="color: #b91c1c; font-weight: 800;">₹${d.amount_claimed}</span>
              ${d.amount_awarded > 0 ? `<span style="margin-left: 12px; color: #15803d; font-weight: 800;">Awarded to Owner: ₹${d.amount_awarded}</span>` : ''}
            </div>
            <div style="background: #f9fafb; padding: 10px; border-radius: 8px; border: 1px solid #e5e7eb; font-size: 12px; line-height: 1.5;">
              <em>"${escapeHtml(d.description)}"</em>
            </div>
            ${d.evidence_urls && d.evidence_urls.length > 0 ? `
              <div style="margin-top: 10px;">
                <strong style="font-size: 11px; color: #4b5563;">📸 Attached Photo Proof of Damage:</strong>
                <div style="display: flex; gap: 8px; margin-top: 6px; flex-wrap: wrap;">
                  ${d.evidence_urls.map(url => `
                    <a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" title="Click to view full photo">
                      <img src="${escapeHtml(url)}" alt="Damage proof" style="width: 72px; height: 72px; object-fit: cover; border-radius: 8px; border: 1px solid #d1d5db; box-shadow: 0 1px 4px rgba(0,0,0,0.08); cursor: pointer;">
                    </a>
                  `).join("")}
                </div>
              </div>
            ` : ''}
            ${d.resolution_note ? `
              <div style="margin-top: 8px; background: #f0fdf4; padding: 8px 10px; border-radius: 8px; border: 1px solid #bbf7d0; font-size: 11px; color: #166534;">
                <strong>Admin Settlement Note:</strong> ${escapeHtml(d.resolution_note)}
              </div>
            ` : ''}
          </div>

          ${canResolve ? `
            <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 10px;">
              <button class="primary-button" style="padding: 6px 14px; font-size: 11px;" onclick="promptResolveDispute(${d.dispute_id}, ${d.amount_claimed}, '${escapeHtml(d.raised_by_name)}', ${d.loan_id})">
                Mediate &amp; Settle Deposit →
              </button>
            </div>
          ` : ''}
        </div>
      `;
    }).join("");
  } catch (err) {
    container.innerHTML = `<p style="color: #c53030; padding: 20px;">Failed to load disputes: ${err.message}</p>`;
  }
}

async function promptResolveDispute(disputeId, amountClaimed, raiserName, loanId) {
  openActionModal("Mediate Damage Dispute & Settle Deposit", `
    <p class="modal-subtitle">As Campus Admin, review the damaged item report and award deposit deduction to cover repairs/replacement.</p>
    <form id="resolveDisputeForm">
      <label class="form-field">
        <span>Amount Awarded to Item Owner from Deposit (₹)</span>
        <input type="number" name="amount_awarded" min="0" step="1" value="${amountClaimed}" required />
        <small style="color: #64756b; font-size: 10px;">This amount is awarded to the owner. Any remainder is refunded to the borrower.</small>
      </label>
      <label class="form-field">
        <span>Settlement Decision</span>
        <select name="status" required>
          <option value="RESOLVED">Approve Claim & Award Deposit to Owner</option>
          <option value="REJECTED">Reject Claim (Refund Deposit in full to Borrower)</option>
        </select>
      </label>
      <label class="form-field">
        <span>Resolution & Inspection Notes</span>
        <textarea name="resolution_note" rows="3" required placeholder="Explain damage verification, repair cost deducted, and outcome..."></textarea>
      </label>
      <button class="primary-button modal-submit" type="submit">Submit Settlement Decision <span>→</span></button>
    </form>
  `);

  $("#resolveDisputeForm")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const amount_awarded = Number(form.get("amount_awarded")) || 0;
    const status = String(form.get("status"));
    const resolution_note = String(form.get("resolution_note")).trim();

    try {
      await apiFetch(`/api/admin/disputes/${disputeId}/resolve`, {
        method: "POST",
        body: {
          amount_awarded,
          resolution_note,
          status
        }
      });
      $("#actionDialog").close();
      toast("Dispute resolved successfully and deposit settled.");
      loadAdminStats();
      loadAdminDisputes();
    } catch (err) {
      toast(`Resolution error: ${err.message}`, true);
    }
  });
}
window.promptResolveDispute = promptResolveDispute;

async function loadAdminLoans() {
  const container = $("#adminLoansList");
  if (!container) return;
  container.innerHTML = `<p style="text-align: center; color: #888; padding: 24px;">Loading campus loans...</p>`;

  try {
    const loans = await apiFetch("/api/admin/loans");
    if (!loans.length) {
      container.innerHTML = `<p style="text-align: center; color: #888; padding: 24px;">No loans recorded yet.</p>`;
      return;
    }

    container.innerHTML = loans.map(l => {
      const depStatusClass = (l.deposit_status || "").toLowerCase();
      const loanStatusClass = (l.status || "").toLowerCase();
      return `
        <div class="admin-record-card">
          <div class="admin-record-header">
            <div>
              <span class="admin-status-pill ${loanStatusClass}">${escapeHtml(l.status)}</span>
              <strong style="margin-left: 8px; font-size: 13px;">${escapeHtml(l.item_title)}</strong>
              <small style="color: #718078;">(Loan #${l.loan_id})</small>
            </div>
            <div>
              <span class="admin-status-pill ${depStatusClass}">Deposit: ${escapeHtml(l.deposit_status)}</span>
            </div>
          </div>
          <div class="admin-record-body">
            <div><strong>Lender:</strong> ${escapeHtml(l.owner_name)} (${escapeHtml(l.owner_email)})</div>
            <div><strong>Borrower:</strong> ${escapeHtml(l.borrower_name)} (${escapeHtml(l.borrower_email)})</div>
            <div style="margin-top: 4px;">
              <strong>Daily Fee:</strong> ₹${l.agreed_daily_fee} &nbsp;|&nbsp;
              <strong>Security Deposit:</strong> ₹${l.agreed_deposit} &nbsp;|&nbsp;
              <strong>Dates:</strong> ${l.start_date} to ${l.end_date}
            </div>
          </div>
        </div>
      `;
    }).join("");
  } catch (err) {
    container.innerHTML = `<p style="color: #c53030; padding: 20px;">Failed to load loans: ${err.message}</p>`;
  }
}

async function loadAdminItems() {
  const container = $("#adminItemsList");
  if (!container) return;
  container.innerHTML = `<p style="text-align: center; color: #888; padding: 24px;">Loading campus items...</p>`;

  try {
    const items = await apiFetch("/api/admin/items");
    if (!items.length) {
      container.innerHTML = `<p style="text-align: center; color: #888; padding: 24px;">No items listed.</p>`;
      return;
    }

    container.innerHTML = items.map(it => {
      const isActive = it.listing_status === "ACTIVE";
      return `
        <div class="admin-record-card">
          <div class="admin-record-header">
            <div>
              <span class="admin-status-pill ${isActive ? 'active' : 'rejected'}">${escapeHtml(it.listing_status)}</span>
              <strong style="margin-left: 8px; font-size: 13px;">${escapeHtml(it.title)}</strong>
              <small style="color: #718078;">(${escapeHtml(it.category_name)} · Item #${it.item_id})</small>
            </div>
            <span style="font-weight: 800; color: var(--coral-dark);">₹${it.daily_fee}/day · ₹${it.deposit_amount} deposit</span>
          </div>
          <div class="admin-record-body">
            <div><strong>Owner:</strong> ${escapeHtml(it.owner_name)} (${escapeHtml(it.owner_email)}) · <em>${escapeHtml(it.location_name)}</em></div>
            <p style="margin-top: 4px; color: #64756b;">${escapeHtml(it.description)}</p>
          </div>
          <div style="display: flex; justify-content: flex-end; gap: 8px;">
            <button class="outline-button" style="padding: 5px 12px; font-size: 11px;" onclick="toggleAdminItemStatus(${it.item_id}, '${it.listing_status}')">
              ${isActive ? 'Deactivate Listing' : 'Reactivate Listing'}
            </button>
          </div>
        </div>
      `;
    }).join("");
  } catch (err) {
    container.innerHTML = `<p style="color: #c53030; padding: 20px;">Failed to load items: ${err.message}</p>`;
  }
}

async function toggleAdminItemStatus(itemId, currentStatus) {
  const newStatus = currentStatus === "ACTIVE" ? "INACTIVE" : "ACTIVE";
  try {
    await apiFetch(`/api/admin/items/${itemId}/status`, {
      method: "PUT",
      body: { listing_status: newStatus }
    });
    toast(`Item #${itemId} status updated to ${newStatus}.`);
    loadAdminItems();
  } catch (err) {
    toast(`Error: ${err.message}`, true);
  }
}
window.toggleAdminItemStatus = toggleAdminItemStatus;

// Navigation & Auth Buttons
$("#navAdminBtn")?.addEventListener("click", openAdminDashboard);
$("#mobileAdmin")?.addEventListener("click", openAdminDashboard);

$("#tabAdminDisputes")?.addEventListener("click", () => switchAdminTab("disputes"));
$("#tabAdminLoans")?.addEventListener("click", () => switchAdminTab("loans"));
$("#tabAdminItems")?.addEventListener("click", () => switchAdminTab("items"));

$("#signInBtn")?.addEventListener("click", () => {
  if (state.token && state.currentUser) {
    if (confirm(`Sign out of ${state.currentUser.svnit_email}?`)) {
      clearAuthSession();
      toast("You have been signed out.");
      loadMarketplace();
      updateHomepageLoanPreview({ borrowed: [] });
    }
  } else {
    openAuth("login");
  }
});

$("#notificationBtn")?.addEventListener("click", openNotificationsDialog);
$("#myLoansBtn")?.addEventListener("click", openLoansDialog);
$("#listItemHero")?.addEventListener("click", openList);
$("#footerListItem")?.addEventListener("click", openList);
$("#mobileList")?.addEventListener("click", openList);
$("#mobileProfile")?.addEventListener("click", () => openAuth("login"));
$("#addListingFromMine")?.addEventListener("click", () => {
  $("#myListingsDialog").close();
  openList();
});

// Category Tiles
$$(".category-tile").forEach(btn => {
  btn.addEventListener("click", () => {
    const catName = btn.dataset.category;
    const catObj = state.categories.find(c => c.category_name.toLowerCase().includes(catName.toLowerCase()));

    if (catObj) {
      state.selectedCategory = state.selectedCategory === catObj.category_id ? null : catObj.category_id;
    } else {
      state.selectedCategory = null;
    }

    state.query = "";
    $("#searchInput").value = "";
    loadMarketplace();
    $("#marketplace")?.scrollIntoView({ behavior: "smooth" });
  });
});

// Search input
function submitSearch() {
  state.query = $("#searchInput").value.trim();
  state.selectedCategory = null;
  loadMarketplace();
  $("#marketplace")?.scrollIntoView({ behavior: "smooth" });
}

$("#searchInput")?.addEventListener("input", (e) => {
  state.query = e.target.value.trim();
  loadMarketplace();
});
$("#searchBtn")?.addEventListener("click", submitSearch);
$("#searchInput")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") submitSearch();
});

// Auth form submission
$("#authForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = $("#authEmail").value.trim().toLowerCase();

  const svnitEmailRegex = /^[a-zA-Z0-9._%+-]+@([a-zA-Z0-9-]+\.)*svnit\.ac\.in$/i;
  if (!svnitEmailRegex.test(email)) {
    showAuthMessage("Please use your official SVNIT email (e.g. @eed.svnit.ac.in, @eced.svnit.ac.in, @med.svnit.ac.in, @aid.svnit.ac.in, @amhd.svnit.ac.in, @doms.svnit.ac.in, @dohss.svnit.ac.in, @coed.svnit.ac.in, @svnit.ac.in).", "error");
    return;
  }

  const submitBtn = $("#authSubmit");

  // Handle Forgot Password mode: request 6-digit reset code
  if (state.authMode === "forgot") {
    try {
      submitBtn.disabled = true;
      submitBtn.textContent = "Sending code...";
      const res = await apiFetch("/api/auth/forgot-password", {
        method: "POST",
        body: { email }
      });

      state.pendingResetEmail = email;
      state.pendingResetOtp = null;
      $("#authForm").hidden = true;
      if ($("#forgotPasswordActions")) $("#forgotPasswordActions").hidden = true;
      if ($("#setNewPasswordSection")) $("#setNewPasswordSection").hidden = true;
      if ($("#resetOtpSection")) $("#resetOtpSection").hidden = false;

      $("#authTitle").textContent = "Verify reset code";
      $("#authSubtitle").textContent = `Enter the 6-digit verification code sent to ${email}.`;

      if (res.email_sent) {
        showAuthMessage(`Reset code sent to your email (${email})! Check your inbox.`, "success");
        $("#resetOtpInput").value = "";
      } else if (res.otp_debug) {
        showAuthMessage(`Reset code sent to ${email}! (Code: ${res.otp_debug}) Enter below to verify.`, "success");
        $("#resetOtpInput").value = res.otp_debug;
      } else {
        showAuthMessage(`Reset code sent to your email (${email})! Check your inbox.`, "success");
        $("#resetOtpInput").value = "";
      }
      setTimeout(() => $("#resetOtpInput")?.focus(), 80);
    } catch (err) {
      showAuthMessage(err.message, "error");
    } finally {
      submitBtn.disabled = false;
      submitBtn.innerHTML = "Send Reset Code <span>→</span>";
    }
    return;
  }

  const password = $("#authPassword").value;
  if (password.length < 8) {
    showAuthMessage("Password must be at least 8 characters long.", "error");
    return;
  }

  try {
    submitBtn.disabled = true;
    submitBtn.textContent = "Processing...";

    if (state.authMode === "register") {
      const full_name = $("#authName").value.trim();
      const roll_number = $("#authRoll").value.trim();
      const phone_number = $("#authPhone").value.trim() || undefined;

      const regData = await apiFetch("/api/auth/register", {
        method: "POST",
        body: { svnit_email: email, full_name, roll_number, phone: phoneNumber, password }
      });

      // Show OTP verification section
      state.pendingVerifyEmail = email;
      $("#authForm").hidden = true;
      $("#otpSection").hidden = false;
      if (regData.email_sent) {
        showAuthMessage(`Verification code sent to your official email (${email})! Check your inbox to verify your identity.`, "success");
        $("#verifyOtpInput").value = "";
      } else if (regData.verification_token_or_otp) {
        showAuthMessage(`Verification code sent to ${email}! (Code: ${regData.verification_token_or_otp}) Enter below to verify.`, "success");
        $("#verifyOtpInput").value = regData.verification_token_or_otp;
      } else {
        showAuthMessage(`Verification code sent to your email (${email})! Check your inbox.`, "success");
        $("#verifyOtpInput").value = "";
      }
    } else {
      // Login
      const data = await apiFetch("/api/auth/login", {
        method: "POST",
        body: { email, svnit_email: email, password }
      });

      setAuthSession(data.access_token, data.user);
      $("#authDialog").close();
      toast(`Welcome back, ${data.user.full_name}!`);
      loadMarketplace();
      fetchUserLoans();
    }
  } catch (err) {
    let msg = err.message || "Sign in failed.";
    if (msg.toLowerCase().includes("session expired") || msg.toLowerCase().includes("invalid svnit email or password")) {
      msg = "Incorrect SVNIT email or password. Please check your password or click 'Forgot password?' below.";
    }
    showAuthMessage(msg, "error");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = state.authMode === "register" ? "Create account <span>→</span>" : "Sign in <span>→</span>";
    }
  }
});

// Forgot password mode toggles
function openForgotMode(e) {
  if (e && e.preventDefault) e.preventDefault();
  state.authMode = "forgot";
  updateAuthMode();
  setTimeout(() => $("#authEmail")?.focus(), 80);
}
window.openForgotMode = openForgotMode;

function backToLoginMode(e) {
  if (e && e.preventDefault) e.preventDefault();
  state.authMode = "login";
  updateAuthMode();
}
window.backToLoginMode = backToLoginMode;

$("#forgotBtn")?.addEventListener("click", openForgotMode);
$("#forgotBackBtn")?.addEventListener("click", backToLoginMode);
$("#resetBackToLoginBtn")?.addEventListener("click", backToLoginMode);

// Step 2: Verify reset OTP code only
async function handleVerifyResetOtp(e) {
  if (e && e.preventDefault) e.preventDefault();
  const email = state.pendingResetEmail || $("#authEmail").value.trim().toLowerCase();
  const otp = $("#resetOtpInput").value.trim();

  if (!otp || otp.length < 6) {
    showAuthMessage("Please enter the complete 6-digit verification code.", "error");
    $("#resetOtpInput")?.focus();
    return;
  }

  const btn = $("#verifyResetOtpBtn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Verifying code...";
  }

  try {
    await apiFetch("/api/auth/verify-reset-otp", {
      method: "POST",
      body: { email, otp }
    });

    state.pendingResetOtp = otp;
    if ($("#resetOtpSection")) $("#resetOtpSection").hidden = true;
    if ($("#setNewPasswordSection")) $("#setNewPasswordSection").hidden = false;

    $("#authTitle").textContent = "Create new password";
    $("#authSubtitle").textContent = "Choose a strong password (minimum 8 characters) for your SVNIT account.";
    showAuthMessage("Reset code verified! Please set your new password below.", "success");

    $("#resetNewPassword").value = "";
    $("#resetConfirmPassword").value = "";
    setTimeout(() => $("#resetNewPassword")?.focus(), 80);
  } catch (err) {
    showAuthMessage(err.message, "error");
    $("#resetOtpInput")?.focus();
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = "Verify Code <span>→</span>";
    }
  }
}
window.handleVerifyResetOtp = handleVerifyResetOtp;

// Step 3: Save new password (revealed only after OTP verified)
async function handleSaveNewPassword(e) {
  if (e && e.preventDefault) e.preventDefault();
  const email = state.pendingResetEmail || $("#authEmail").value.trim().toLowerCase();
  const otp = state.pendingResetOtp || $("#resetOtpInput").value.trim();
  const newPass = $("#resetNewPassword").value;
  const confirmPass = $("#resetConfirmPassword").value;

  if (!otp || otp.length < 6) {
    showAuthMessage("Reset session expired. Please verify your OTP code again.", "error");
    if ($("#setNewPasswordSection")) $("#setNewPasswordSection").hidden = true;
    if ($("#resetOtpSection")) $("#resetOtpSection").hidden = false;
    return;
  }

  if (newPass.length < 8) {
    showAuthMessage("New password must be at least 8 characters long.", "error");
    $("#resetNewPassword")?.focus();
    return;
  }

  if (newPass !== confirmPass) {
    showAuthMessage("New password and confirmation do not match.", "error");
    $("#resetConfirmPassword")?.focus();
    return;
  }

  const btn = $("#saveNewPasswordBtn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Updating password...";
  }

  try {
    await apiFetch("/api/auth/reset-password", {
      method: "POST",
      body: {
        email,
        otp_or_token: otp,
        new_password: newPass
      }
    });

    showAuthMessage("Password updated successfully! Signing you in...", "success");

    // Automatically sign in with the new password
    const loginData = await apiFetch("/api/auth/login", {
      method: "POST",
      body: {
        email,
        svnit_email: email,
        password: newPass
      }
    });

    setAuthSession(loginData.access_token, loginData.user);
    $("#authDialog").close();
    toast(`Password updated! Welcome back, ${loginData.user.full_name}.`);
    loadMarketplace();
    fetchUserLoans();
  } catch (err) {
    showAuthMessage(err.message, "error");
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = "Set New Password & Sign In <span>→</span>";
    }
  }
}
window.handleSaveNewPassword = handleSaveNewPassword;

// Resend reset code handler
async function handleResendResetOtp(e) {
  if (e && e.preventDefault) e.preventDefault();
  const email = state.pendingResetEmail || $("#authEmail").value.trim().toLowerCase();
  if (!email) return;
  try {
    showAuthMessage("Resending password reset code...", "success");
    const res = await apiFetch("/api/auth/forgot-password", {
      method: "POST",
      body: { email }
    });
    if (res.email_sent) {
      showAuthMessage(`New reset code sent to ${email}! Check your inbox.`, "success");
      $("#resetOtpInput").value = "";
    } else {
      const devOtp = res.otp_debug ? ` (Code: ${res.otp_debug})` : "";
      showAuthMessage(`New reset code sent to ${email}!${devOtp}`, "success");
      if (res.otp_debug) {
        $("#resetOtpInput").value = res.otp_debug;
      }
    }
  } catch (err) {
    let msg = err.message || "Request failed.";
    showAuthMessage(msg, "error");
  }
}
window.handleResendResetOtp = handleResendResetOtp;

$("#verifyResetOtpBtn")?.addEventListener("click", handleVerifyResetOtp);
$("#saveNewPasswordBtn")?.addEventListener("click", handleSaveNewPassword);
$("#resendResetOtpBtn")?.addEventListener("click", handleResendResetOtp);
$("#setNewPasswordCancelBtn")?.addEventListener("click", backToLoginMode);
$("#resetOtpInput")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    handleVerifyResetOtp(e);
  }
});
$("#resetNewPassword")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    $("#resetConfirmPassword")?.focus();
  }
});
$("#resetConfirmPassword")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    handleSaveNewPassword(e);
  }
});

// OTP verification step
$("#verifyOtpBtn")?.addEventListener("click", async () => {
  const otp = $("#verifyOtpInput").value.trim();
  if (!otp || otp.length < 6) {
    showAuthMessage("Please enter the complete 6-digit verification code.", "error");
    return;
  }

  try {
    $("#verifyOtpBtn").disabled = true;
    $("#verifyOtpBtn").textContent = "Verifying...";

    const res = await apiFetch("/api/auth/verify-email", {
      method: "POST",
      body: { email: state.pendingVerifyEmail, otp }
    });

    setAuthSession(res.access_token, res.user);
    $("#authDialog").close();
    toast(`Email verified! Welcome to BorrowHub, ${res.user.full_name}!`);
    loadMarketplace();
    fetchUserLoans();
  } catch (err) {
    showAuthMessage(err.message, "error");
    $("#verifyOtpBtn").disabled = false;
    $("#verifyOtpBtn").textContent = "Verify Email & Complete Sign In →";
  }
});

$("#resendOtpBtn")?.addEventListener("click", async () => {
  if (!state.pendingVerifyEmail) return;
  try {
    showAuthMessage("Resending verification code...", "success");
    const res = await apiFetch("/api/auth/resend-otp", {
      method: "POST",
      body: { email: state.pendingVerifyEmail }
    });
    if (res.email_sent) {
      showAuthMessage(`New verification code sent to ${state.pendingVerifyEmail}! Check your inbox.`, "success");
      $("#verifyOtpInput").value = "";
    } else if (res.otp_debug) {
      showAuthMessage(`New verification code sent to ${state.pendingVerifyEmail}! (Code: ${res.otp_debug})`, "success");
      $("#verifyOtpInput").value = res.otp_debug;
    } else {
      showAuthMessage(`New verification code sent to ${state.pendingVerifyEmail}! Check your inbox.`, "success");
      $("#verifyOtpInput").value = "";
    }
  } catch (err) {
    let msg = err.message || "Sign in failed.";
    if (msg.toLowerCase().includes("session expired") || msg.toLowerCase().includes("invalid svnit email or password")) {
      msg = "Incorrect SVNIT email or password. Please check your password or click 'Forgot password?' below.";
    }
    showAuthMessage(msg, "error");
  }
});

$("#backToLoginBtn")?.addEventListener("click", () => {
  state.authMode = "login";
  updateAuthMode();
});

// Quick demo sign in chips
$$("[data-demo]").forEach(btn => {
  btn.addEventListener("click", () => demoLogin(btn.dataset.demo));
});

// Tabs in auth dialog
$$(".auth-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    state.authMode = tab.dataset.tab;
    updateAuthMode();
  });
});

// Password visibility toggle
const authPassword = $("#authPassword");
const toggleAuthPassword = $("#toggleAuthPassword");
const authEyeIcon = $("#authEyeIcon");
if (authPassword && toggleAuthPassword && authEyeIcon) {
  toggleAuthPassword.addEventListener("click", () => {
    const show = authPassword.type === "password";
    authPassword.type = show ? "text" : "password";
    toggleAuthPassword.setAttribute("aria-label", show ? "Hide password" : "Show password");
    toggleAuthPassword.setAttribute("aria-pressed", String(show));
    authEyeIcon.innerHTML = show
      ? '<path d="M3 3l18 18"></path><path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"></path><path d="M9.9 5.2A10.8 10.8 0 0 1 12 5c6.4 0 10 7 10 7a15.8 15.8 0 0 1-4 4.8"></path><path d="M6.2 6.2C3.5 8.1 2 12 2 12s3.6 7 10 7c1.2 0 2.3-.2 3.3-.6"></path>'
      : '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z"></path><circle cx="12" cy="12" r="3"></circle>';
  });
}

// Reset password visibility toggle
const resetNewPassword = $("#resetNewPassword");
const toggleResetPassword = $("#toggleResetPassword");
const resetEyeIcon = $("#resetEyeIcon");
if (resetNewPassword && toggleResetPassword && resetEyeIcon) {
  toggleResetPassword.addEventListener("click", () => {
    const show = resetNewPassword.type === "password";
    resetNewPassword.type = show ? "text" : "password";
    toggleResetPassword.setAttribute("aria-label", show ? "Hide password" : "Show password");
    toggleResetPassword.setAttribute("aria-pressed", String(show));
    resetEyeIcon.innerHTML = show
      ? '<path d="M3 3l18 18"></path><path d="M10.6 10.6a2 2 0 0 0 2.8 2.8"></path><path d="M9.9 5.2A10.8 10.8 0 0 1 12 5c6.4 0 10 7 10 7a15.8 15.8 0 0 1-4 4.8"></path><path d="M6.2 6.2C3.5 8.1 2 12 2 12s3.6 7 10 7c1.2 0 2.3-.2 3.3-.6"></path>'
      : '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z"></path><circle cx="12" cy="12" r="3"></circle>';
  });
}

// Mobile navigation
$("#mobileMenu")?.addEventListener("click", () => $("#mainNav")?.classList.toggle("open"));
$$(".nav a").forEach(a => a.addEventListener("click", () => $("#mainNav")?.classList.remove("open")));


// ---------------------------------------------------------------------------
// Data Studio page (live database reporting)
// ---------------------------------------------------------------------------
function openDataStudio(focusId) {
  const studio = $("#dataStudio");
  if (!studio) return;
  // The studio lives inside <main>, so only the sibling sections are toggled.
  const sections = $$("main > section:not(#dataStudio)");
  const isOpen = !studio.hidden;

  if (isOpen) {
    studio.hidden = true;
    sections.forEach((s) => { s.hidden = false; });
    window.scrollTo({ top: 0, behavior: "smooth" });
    return;
  }

  sections.forEach((s) => { s.hidden = true; });
  studio.hidden = false;
  // The Data Studio endpoints need a session, so (re)load it now.
  if (window.BorrowHubStudio && typeof window.BorrowHubStudio.refresh === "function") {
    window.BorrowHubStudio.refresh();
  }
  const target = focusId ? document.getElementById(focusId) : null;
  if (target) {
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  } else {
    studio.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

// Protected links in navbar
$$("[data-auth='true']").forEach(a => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    if (!state.currentUser) {
      openAuth("login");
      showAuthMessage("Please sign in to access this page.", "error");
      return;
    }
    const text = a.textContent.trim().toLowerCase();
    if (text.includes("my listings")) {
      openMyListings();
    } else if (text.includes("query lab")) {
      openDataStudio("queryLabCard");
      setTimeout(() => document.getElementById("qlSql")?.focus(), 450);
    } else if (text.includes("data studio")) {
      openDataStudio();
    }
  });
});

// View all popular & recent toggles
$("#viewAllPopular")?.addEventListener("click", () => {
  state.showAllPopular = !state.showAllPopular;
  $("#viewAllPopular").innerHTML = state.showAllPopular ? "Show less ↑" : "View all →";
  renderMarketplace();
});
$("#viewAllRecent")?.addEventListener("click", () => {
  state.showAllRecent = !state.showAllRecent;
  $("#viewAllRecent").innerHTML = state.showAllRecent ? "Show less ↑" : "View all →";
  renderMarketplace();
});

// Join community button
$("#joinBtn")?.addEventListener("click", () => {
  localStorage.setItem("borrowhub_community_joined", "true");
  $("#joinBtn").innerHTML = 'Already joined <span>✓</span>';
  $("#joinBtn").disabled = true;
  toast("You are part of the SVNIT BorrowHub Community!");
});

// ==========================================
// 13. INITIALIZATION
// ==========================================
async function initBorrowHub() {
  updateAuthUI();

  // Load backend categories & locations
  try {
    const [cats, locs] = await Promise.all([
      apiFetch("/api/items/categories"),
      apiFetch("/api/items/locations")
    ]);

    state.categories = cats || [];
    state.locations = locs || [];

    // Populate category dropdown in list form
    const catSelect = $("#listCategorySelect");
    if (catSelect) {
      catSelect.innerHTML = `<option value="">Choose category</option>` +
        state.categories.map(c => `<option value="${c.category_id}">${escapeHtml(c.category_name)}</option>`).join("");
    }

    // Populate location dropdown in list form
    const locSelect = $("#listLocationSelect");
    if (locSelect) {
      locSelect.innerHTML = `<option value="">Choose campus location</option>` +
        state.locations.map(l => `<option value="${l.location_id}">${escapeHtml(l.name)}</option>`).join("");
    }
  } catch (err) {
    console.warn("Could not load categories/locations:", err);
  }

  // Load marketplace listings
  loadMarketplace();

  // If user is already authenticated, verify session & refresh loans
  if (state.token) {
    refreshUserData();
  }

  // Dismiss welcome screen gracefully
  const welcome = $("#welcomeScreen");
  if (welcome) {
    setTimeout(() => {
      welcome.classList.add("welcome-screen-exit");
      setTimeout(() => {
        welcome.remove();
        document.body.classList.remove("pre-auth");
      }, 200);
    }, 300);
  } else {
    document.body.classList.remove("pre-auth");
  }
}

// Start BorrowHub safely
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initBorrowHub);
} else {
  initBorrowHub();
}
