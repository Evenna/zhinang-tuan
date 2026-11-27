/* The Agora — themed debate halls.
 * Flow: Themes index (original oversized list, aside shows motion + residents)
 *   → Hall (pick motion, pick up to 5 debaters from the colonnade or anyone)
 *   → Debate floor (rounds, stances move people between camps, ask the floor / @ one, kick, pull in)
 *   → Verdict stele (publish to the hall's record, continue, share).
 * Data: /api/agora/* on the live backend; falls back to assets/agora-static.json on the static preview.
 * Depends on globals from index.html: state, API_BASE, THEMES, activeThemeIndex, themeGrid,
 * getPortraitAdjustments, getPosterPalette, loadPeoplePage, openSitePage.
 */
(function () {
  const MAX_SEATS = 5;
  const MIN_SEATS = 2;
  const STANCE_LABEL = { for: 'For', against: 'Against', undecided: 'Undecided' };
  const MOVE_LABEL = { argues: 'argues', rebuts: 'rebuts', concedes: 'concedes', reframes: 'reframes' };
  const THINKING = [
    'is looking for the weak premise',
    'is turning the question over',
    'is drafting a counter-example',
    'is weighing what was just said',
    'is choosing which word to fight over',
    'is remembering something from a long life',
    'is deciding whether to agree'
  ];

  const page = document.getElementById('themesPage');
  let view = document.getElementById('agoraView');
  if (page && !view) {
    view = document.createElement('div');
    view.className = 'agora-view';
    view.id = 'agoraView';
    page.append(view);
  }

  const AG = {
    halls: null,
    hallDetail: {},
    staticData: null,
    live: null,
    hall: null,
    motion: '',
    picked: [],
    debate: null,
    busy: false,
    target: null
  };

  /* ───────── helpers ───────── */
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const apiBase = () => (typeof API_BASE !== 'undefined' ? API_BASE : (window.ASK_SOCRATES_API || 'http://127.0.0.1:8000/api'));
  const peopleList = () => (typeof state !== 'undefined' && Array.isArray(state.people) ? state.people : []);

  function person(slug) {
    const found = peopleList().find((p) => p.slug === slug);
    if (found) return found;
    const fromHall = Object.values(AG.hallDetail).flatMap((h) => h.residents || []).find((r) => r.slug === slug);
    const [c1, c2] = typeof getPosterPalette === 'function' ? getPosterPalette(fromHall?.name || slug, '') : ['#4a3d2a', '#6b5a3e'];
    return { slug, name: fromHall?.name || slug.replace(/-/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase()), intro: fromHall?.intro || '', era: fromHall?.era || '', posterColor: c1, posterColorSoft: c2 };
  }
  const nameOf = (slug) => (slug === 'user' ? 'You' : person(slug).name);
  const firstName = (slug) => nameOf(slug).split(' ').slice(-1)[0];

  function cutout(slug) {
    const ext = window.ASK_SOCRATES_CATALOG ? 'webp' : 'png';
    return `assets/character_cutouts/${slug}.${ext}`;
  }
  // png ↔ webp fallback for portraits (static export only ships webp)
  document.addEventListener('error', (event) => {
    const img = event.target;
    if (!(img instanceof HTMLImageElement) || !img.dataset.agImg || img.dataset.agRetried) return;
    img.dataset.agRetried = '1';
    img.src = img.src.endsWith('.png') ? img.src.replace(/\.png$/, '.webp') : img.src.replace(/\.webp$/, '.png');
  }, true);

  function adjust(slug) {
    try { return { scale: 1, x: 0, y: 0, flip: false, ...(getPortraitAdjustments(slug) || {}) }; } catch (e) { return { scale: 1, x: 0, y: 0, flip: false }; }
  }

  // Arch niche. width in px so the card-calibrated portrait offsets scale correctly.
  function niche(slug, { width = 112, picked = false, extra = '', plate = true, attrs = '', cls = '' } = {}) {
    const p = person(slug);
    const a = adjust(slug);
    const style = `--c1:${p.posterColor};--c2:${p.posterColorSoft};--px:${a.x};--py:${a.y};--ps:${a.scale};--pf:${a.flip ? -1 : 1};--k:${(width / 286).toFixed(3)};width:${width}px`;
    return `<button type="button" class="ag-niche${picked ? ' is-picked' : ''} ${cls}" data-slug="${esc(slug)}" style="${style}" ${attrs} title="${esc(p.name)}">
      <span class="ag-niche-arch"><img data-ag-img="1" src="${cutout(slug)}" alt="" loading="lazy" decoding="async"></span>
      <span class="ag-niche-check" aria-hidden="true">✓</span>
      ${plate ? `<span class="ag-niche-plate">${esc(p.name)}</span>` : ''}${extra}
    </button>`;
  }
  function miniAv(slug) {
    const p = person(slug);
    return `<span class="ag-turn-av" style="--c1:${p.posterColor};--c2:${p.posterColorSoft}"><img data-ag-img="1" src="${cutout(slug)}" alt="" loading="lazy"></span>`;
  }
  function face(slug) {
    const p = person(slug);
    return `<span style="--c1:${p.posterColor}"><img data-ag-img="1" src="${cutout(slug)}" alt="" loading="lazy"></span>`;
  }
  const tag = (stance) => `<span class="ag-tag is-${esc(stance || 'undecided')}">${STANCE_LABEL[stance] || 'Undecided'}</span>`;

  function colonnade() {
    // Thin-line Roman architecture: fluted columns with Doric capitals, coffered barrel arch, stepped floor in perspective.
    const W = 1440, H = 900, cx = 720;
    let g = '';
    const column = (x, w, top, bottom) => {
      let c = `<rect x="${x - 6}" y="${top - 16}" width="${w + 12}" height="9"/><path d="M${x - 2} ${top - 7} Q${x + w / 2} ${top + 4} ${x + w + 2} ${top - 7}"/><rect x="${x}" y="${top - 2}" width="${w}" height="5"/>`;
      c += `<path d="M${x + 2} ${top + 3} L${x + 4} ${bottom - 8} M${x + w - 2} ${top + 3} L${x + w - 4} ${bottom - 8}"/>`;
      for (let f = 1; f < 6; f += 1) { const fx = x + (w * f) / 6; c += `<line x1="${fx}" y1="${top + 8}" x2="${fx}" y2="${bottom - 12}" stroke-opacity="0.55"/>`; }
      c += `<rect x="${x - 2}" y="${bottom - 8}" width="${w + 4}" height="6"/><rect x="${x - 8}" y="${bottom - 2}" width="${w + 16}" height="10"/><rect x="${x - 14}" y="${bottom + 8}" width="${w + 28}" height="12"/>`;
      return c;
    };
    [[52, 70, 120, 790], [196, 54, 170, 760]].forEach(([x, w, t, b]) => { g += column(x, w, t, b) + column(W - x - w, w, t, b); });
    g += `<path d="M0 92 H${W} M0 102 H${W} M0 112 H${W}"/>`;
    for (let x = 20; x < W; x += 36) g += `<rect x="${x}" y="72" width="16" height="20" stroke-opacity="0.6"/>`;
    const r1 = 452, r2 = 416, r3 = 372, sy = 610;
    g += [r1, r2, r3, r3 - 10].map((r) => `<path d="M${cx - r} ${sy} A${r} ${r} 0 0 1 ${cx + r} ${sy}"/>`).join('');
    for (let a = 0; a <= 180; a += 9) {
      const rad = (Math.PI * a) / 180, c = Math.cos(rad), sn = Math.sin(rad);
      g += `<line x1="${(cx - c * r1).toFixed(1)}" y1="${(sy - sn * r1).toFixed(1)}" x2="${(cx - c * r2).toFixed(1)}" y2="${(sy - sn * r2).toFixed(1)}"/>`;
      if (a % 18 === 0) g += `<line x1="${(cx - c * r2).toFixed(1)}" y1="${(sy - sn * r2).toFixed(1)}" x2="${(cx - c * r3).toFixed(1)}" y2="${(sy - sn * r3).toFixed(1)}" stroke-opacity="0.5"/>`;
    }
    g += `<path d="M${cx - 14} ${sy - r1 - 2} L${cx} ${sy - r1 - 26} L${cx + 14} ${sy - r1 - 2}"/>`;
    [810, 826, 846, 870].forEach((y, i) => { g += `<path d="M0 ${y} H${W}" stroke-opacity="${(0.9 - i * 0.15).toFixed(2)}"/>`; });
    for (let k = -8; k <= 8; k += 1) g += `<line x1="${cx + k * 28}" y1="810" x2="${cx + k * 150}" y2="${H}" stroke-opacity="0.35"/>`;
    return `<div class="ag-colonnade" aria-hidden="true"><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid slice" fill="none" stroke="rgba(212,175,123,0.62)" stroke-width="1">${g}</svg></div>`;
  }

  function tallyOf(seats, stances) {
    const t = { for: 0, against: 0, undecided: 0 };
    seats.forEach((s) => { const k = stances?.[s]; if (k && t[k] !== undefined) t[k] += 1; else t.undecided += 1; });
    return t;
  }
  function tallyBar(t) {
    return `<div class="ag-tally">${['for', 'undecided', 'against'].map((k) => `<div style="--n:${t[k]}"><div class="ag-tally-label is-${k}">${STANCE_LABEL[k]}<b>${t[k]}</b></div><div class="ag-tally-bar bg-${k}"></div></div>`).join('')}</div>`;
  }
  const miniTally = (t = {}) => `<span class="ag-mini-tally">${['for', 'undecided', 'against'].map((k) => `<i class="bg-${k}" style="flex:${t[k] || 0}"></i>`).join('')}</span>`;

  /* ───────── data ───────── */
  async function fetchJSON(url, options = {}, timeout = 9000) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    try {
      const res = await fetch(url, { ...options, signal: ctrl.signal, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
      const text = await res.text();
      const data = text ? JSON.parse(text) : {};
      if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
      return data;
    } finally { clearTimeout(timer); }
  }
  async function staticData() {
    if (!AG.staticData) AG.staticData = await fetchJSON('assets/agora-static.json', {}, 15000);
    return AG.staticData;
  }
  async function get(path) {
    if (AG.live !== false) {
      try { const data = await fetchJSON(apiBase() + '/agora' + path); AG.live = true; return data; } catch (e) { AG.live = false; }
    }
    const s = await staticData();
    if (path === '/halls') return { halls: s.halls };
    if (path.startsWith('/halls/')) return s.details[path.slice(7)];
    if (path.startsWith('/debates/')) {
      const d = s.debates[decodeURIComponent(path.slice(9))];
      if (!d) throw new Error('Debate not found');
      return d;
    }
    throw new Error('Not available offline');
  }
  async function post(path, body, timeout = 120000) {
    try {
      return await fetchJSON(apiBase() + '/agora' + path, { method: 'POST', body: JSON.stringify(body) }, timeout);
    } catch (e) {
      if (e.name === 'AbortError') throw new Error('The floor took too long to answer. Try again.');
      if (AG.live === false || /Failed to fetch|NetworkError|Load failed/i.test(e.message)) throw new Error('Live debating needs the backend, which is offline right now. Past debates are still open to read.');
      throw e;
    }
  }
  async function halls() {
    if (!AG.halls) AG.halls = (await get('/halls')).halls;
    return AG.halls;
  }
  async function hallDetail(id, fresh = false) {
    if (fresh || !AG.hallDetail[id]) AG.hallDetail[id] = await get('/halls/' + id);
    return AG.hallDetail[id];
  }
  async function ensurePeople() {
    try { if (typeof loadPeoplePage === 'function') await loadPeoplePage(); } catch (e) { /* niches fall back to hall data */ }
  }

  /* ───────── index aside (original list untouched) ───────── */
  async function syncAside() {
    const aside = document.querySelector('#themesPage .theme-aside');
    if (!aside || typeof THEMES === 'undefined') return;
    const theme = THEMES[typeof activeThemeIndex === 'number' ? activeThemeIndex : 0];
    let box = aside.querySelector('.ag-aside');
    if (!box) { box = document.createElement('div'); box.className = 'ag-aside'; aside.append(box); }
    let list;
    try { list = await halls(); } catch (e) { box.innerHTML = ''; return; }
    const hall = list.find((h) => h.id === theme?.id);
    if (!hall) { box.innerHTML = ''; return; }
    const meta = document.getElementById('themeAsideMeta');
    if (meta) meta.innerHTML = `<b style="color:var(--ag-gold);font-weight:500">${hall.resident_count}</b> residents · <b style="color:var(--ag-gold);font-weight:500">${hall.debate_count}</b> debates on record`;
    paintWall(hall);
    box.innerHTML = `
      <div style="margin-top:26px"><span class="ag-pill">Motion of the week</span></div>
      <div class="ag-aside-motion">“${esc(hall.motion)}”</div>
      <div class="ag-aside-niches">${hall.featured.map((s) => niche(s, { width: 86, plate: false, attrs: 'tabindex="-1"' })).join('')}</div>
      <div class="ag-aside-meta"><span class="ag-live-dot"></span><b>${hall.live_count}</b> debating now</div>
      <button class="ag-btn is-solid" type="button" data-ag-enter="${esc(hall.id)}">Enter the hall →</button>`;
  }

  async function paintWall(hall) {
    const menu = document.querySelector('#themesPage .theme-menu');
    if (!menu) return;
    let wall = menu.querySelector('.ag-wall');
    if (!wall) { wall = document.createElement('div'); wall.className = 'ag-wall'; wall.setAttribute('aria-hidden', 'true'); menu.prepend(wall); }
    if (!menu.querySelector(':scope > .ag-colonnade')) menu.insertAdjacentHTML('afterbegin', colonnade());
    if (wall.dataset.hall === hall.id) return;
    wall.dataset.hall = hall.id;
    const featured = new Set(hall.featured);
    const paint = (residents, fade) => {
      // everyone once (featured spread through the middle rows), then repeat the rest faintly to fill the wall
      const rest = residents.filter((r) => !featured.has(r.slug));
      const lit = residents.filter((r) => featured.has(r.slug));
      const order = [...rest];
      lit.forEach((r, k) => order.splice(Math.min(order.length, 13 + k * 9), 0, r));
      const slots = [...order];
      while (slots.length < 54) slots.push(...rest.length ? rest : residents);
      if (fade) wall.classList.remove('is-in');
      wall.innerHTML = slots.slice(0, Math.max(54, order.length)).map((r, i) => niche(r.slug, { width: 84, plate: false, cls: featured.has(r.slug) && i < order.length ? 'is-lit' : '', attrs: `tabindex="-1" data-d="${i % 12}"` })).join('');
      requestAnimationFrame(() => requestAnimationFrame(() => wall.classList.add('is-in')));
    };
    const cached = AG.hallDetail[hall.id]?.residents;
    if (cached) { paint(cached, true); return; }
    paint(hall.featured.map((slug) => ({ slug })), true);
    try {
      const residents = (await hallDetail(hall.id)).residents;
      if (residents && wall.dataset.hall === hall.id) paint(residents, false);
    } catch (e) { /* featured only */ }
  }
  // warm all halls so hovering is instant
  setTimeout(async () => { try { (await halls()).forEach((h) => hallDetail(h.id).catch(() => {})); } catch (e) { /* offline */ } }, 1200);


  /* ───────── open / close ───────── */
  function setURL(params) {
    const url = new URL(location.href);
    ['view', 'hall', 'debate'].forEach((k) => url.searchParams.delete(k));
    Object.entries(params).forEach(([k, v]) => v && url.searchParams.set(k, v));
    history.replaceState(null, '', url);
  }
  function openAgora() {
    page?.classList.add('agora-open');
    window.scrollTo({ top: 0 });
  }
  function closeAgora() {
    page?.classList.remove('agora-open');
    closeModal();
    setURL({ view: 'themes' });
    syncAside();
  }

  /* ───────── Hall ───────── */
  async function openHall(id, { keepPicks = false } = {}) {
    openAgora();
    view.innerHTML = `<div class="ag-hall">${colonnade()}<div class="ag-hall-main"><div class="ag-crumb">Loading the hall<span class="ag-dots"></span></div></div></div>`;
    setURL({ view: 'themes', hall: id });
    await ensurePeople();
    let hall;
    try { hall = await hallDetail(id); } catch (e) {
      view.innerHTML = `<div class="ag-hall">${colonnade()}<div class="ag-hall-main"><div class="ag-error">${esc(e.message)}</div><button class="ag-btn" data-ag-back-index>← All themes</button></div></div>`;
      return;
    }
    if (AG.hall !== id || !keepPicks) {
      AG.hall = id;
      AG.motion = hall.motion;
      AG.picked = hall.residents.slice(0, 3).map((r) => r.slug);
    }
    renderHall();
  }

  function renderHall() {
    const hall = AG.hallDetail[AG.hall];
    if (!hall) return;
    const picked = new Set(AG.picked);
    const slots = Array.from({ length: MAX_SEATS - AG.picked.length }, () => '<button type="button" class="ag-slot" data-ag-invite aria-label="Invite someone">+</button>').join('');
    view.innerHTML = `<div class="ag-hall">${colonnade()}
      <div class="ag-hall-main">
        <div class="ag-crumb"><button type="button" data-ag-back-index>Themes</button><span>/</span><span>${esc(hall.title)} · ${esc(hall.zh || '')}</span></div>
        <h1 class="ag-h1">The <em>${esc(hall.title)}</em> Hall</h1>
        <div class="ag-motion-box">
          <span class="ag-pill">Motion on the floor</span>
          <textarea class="ag-motion-input" id="agMotion" rows="2" maxlength="300" placeholder="Or write your own motion — a question with a yes or no">${esc(AG.motion)}</textarea>
          <div class="ag-motion-alt">${hall.motions.map((m) => `<button type="button" class="ag-chip${m === AG.motion ? ' is-on' : ''}" data-ag-motion="${esc(m)}">${esc(m)}</button>`).join('')}</div>
        </div>
        <div class="ag-gallery-head"><span>Residents of the hall · ${hall.residents.length}</span>
          <button type="button" class="ag-round" data-ag-scroll="-1" aria-label="Scroll left">←</button><button type="button" class="ag-round" data-ag-scroll="1" aria-label="Scroll right">→</button></div>
        <div class="ag-gallery" id="agGallery">${hall.residents.map((r) => niche(r.slug, { width: 112, picked: picked.has(r.slug), attrs: 'data-ag-pick' })).join('')}</div>
        <div class="ag-steps"></div>
        <section class="ag-floor">
          <div class="ag-floor-head">The floor · ${AG.picked.length} / ${MAX_SEATS}</div>
          <div class="ag-floor-row">${AG.picked.map((s) => `<div style="position:relative">${niche(s, { width: 92, extra: `<span class="ag-niche-x" data-ag-unpick="${esc(s)}" role="button" aria-label="Remove">×</span>` })}<div class="ag-plinth"></div></div>`).join('')}${slots}</div>
          <div class="ag-floor-foot">
            <span class="ag-floor-hint">${AG.picked.length < MIN_SEATS ? `Pick at least ${MIN_SEATS} minds to open a debate.` : 'Opposing views make the best debates. Anyone among the 251 can be invited.'}</span>
            <span style="display:flex;gap:10px;flex-wrap:wrap"><button type="button" class="ag-btn" data-ag-invite>+ Invite anyone</button>
            <button type="button" class="ag-btn is-solid" data-ag-open ${AG.picked.length < MIN_SEATS ? 'disabled' : ''}>Open the debate →</button></span>
          </div>
        </section>
      </div>
      <aside class="ag-side">
        <div class="ag-side-head">Debates on record · ${hall.debates.length}</div>
        ${hall.debates.map(pastItem).join('') || '<p class="ag-side-note">No debates yet. Yours could be the first.</p>'}
        <p class="ag-side-note">Visitors shown here are illustrative; every reply comes from the AI personas.</p>
      </aside>
    </div>`;
  }

  function pastItem(d) {
    return `<button type="button" class="ag-past" data-ag-read="${esc(d.id)}">
      <div class="ag-past-q">${esc(d.motion)}</div>
      <div class="ag-past-by">${esc([d.name, d.role, d.city].filter(Boolean).join(' · '))}</div>
      <div class="ag-past-row"><span class="ag-faces">${(d.participants || []).map(face).join('')}</span><span style="margin-left:8px">${d.replies} replies · ♥ ${d.likes || 0}</span>${miniTally(d.tally)}</div>
    </button>`;
  }

  function togglePick(slug) {
    const i = AG.picked.indexOf(slug);
    if (i >= 0) AG.picked.splice(i, 1);
    else if (AG.picked.length < MAX_SEATS) AG.picked.push(slug);
    else return flash('The floor holds five. Remove someone first.');
    const scroll = document.getElementById('agGallery')?.scrollLeft || 0;
    renderHall();
    const g = document.getElementById('agGallery');
    if (g) g.scrollLeft = scroll;
  }

  function flash(text) {
    let el = document.getElementById('agFlash');
    if (!el) {
      el = document.createElement('div');
      el.id = 'agFlash';
      el.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:999;padding:10px 18px;border-radius:999px;background:#1d1913;border:1px solid rgba(212,175,123,.5);color:#f2ebdf;font-size:12px;transition:opacity .3s';
      document.body.append(el);
    }
    el.textContent = text;
    el.style.opacity = '1';
    clearTimeout(el._t);
    el._t = setTimeout(() => { el.style.opacity = '0'; }, 2200);
  }

  /* ───────── Picker modal (anyone of the 251) ───────── */
  let modal = null;
  let pickerMode = 'hall';
  let pickerTab = 'hall';
  function openPicker(mode) {
    pickerMode = mode;
    pickerTab = 'hall';
    if (!modal) {
      modal = document.createElement('div');
      modal.className = 'ag-modal';
      modal.hidden = true;
      modal.innerHTML = `<div class="ag-modal-panel" role="dialog" aria-modal="true">
        <div class="ag-modal-head"><h3>Invite to the floor</h3><input id="agPickSearch" placeholder="Search by name, field, era…" autocomplete="off"><button type="button" class="ag-round" data-ag-close-modal aria-label="Close">×</button></div>
        <div class="ag-modal-tabs" id="agPickTabs"></div>
        <div class="ag-modal-grid" id="agPickGrid"></div>
        <div class="ag-modal-foot" id="agPickFoot"></div></div>`;
      document.body.append(modal);
      modal.addEventListener('click', (event) => {
        if (event.target === modal || event.target.closest('[data-ag-close-modal]')) return closeModal();
        const tab = event.target.closest('[data-ag-tab]');
        if (tab) { pickerTab = tab.dataset.agTab; return renderPicker(); }
        const n = event.target.closest('.ag-niche');
        if (n) choosePicked(n.dataset.slug);
      });
      modal.querySelector('#agPickSearch').addEventListener('input', renderPicker);
      document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && modal && !modal.hidden) closeModal(); });
    }
    modal.querySelector('#agPickSearch').value = '';
    modal.querySelector('h3').textContent = mode === 'debate' ? 'Pull someone in' : 'Invite to the floor';
    modal.hidden = false;
    renderPicker();
    setTimeout(() => modal.querySelector('#agPickSearch').focus(), 50);
  }
  function closeModal() { if (modal) modal.hidden = true; }
  function renderPicker() {
    const seated = new Set(pickerMode === 'debate' ? AG.debate?.seats || [] : AG.picked);
    const hall = AG.hallDetail[AG.debate?.hall || AG.hall];
    const q = modal.querySelector('#agPickSearch').value.trim().toLowerCase();
    let pool = pickerTab === 'hall' && hall ? hall.residents.map((r) => person(r.slug)) : peopleList();
    if (q) {
      pool = peopleList().filter((p) => [p.name, p.englishName, p.domain, p.era, p.intro, p.archetype].join(' ').toLowerCase().includes(q));
    }
    modal.querySelector('#agPickTabs').innerHTML = q ? `<span class="ag-chip is-on">${pool.length} matches</span>` :
      `<button type="button" class="ag-chip${pickerTab === 'hall' ? ' is-on' : ''}" data-ag-tab="hall">${esc(hall?.title || 'This')} hall</button><button type="button" class="ag-chip${pickerTab === 'all' ? ' is-on' : ''}" data-ag-tab="all">Everyone · ${peopleList().length}</button>`;
    modal.querySelector('#agPickGrid').innerHTML = pool.map((p) => niche(p.slug, { width: 104, cls: seated.has(p.slug) ? 'is-seated' : '' })).join('') || '<p class="ag-floor-hint">Nobody by that name walks this square.</p>';
    const count = seated.size;
    modal.querySelector('#agPickFoot').textContent = count >= MAX_SEATS ? 'The floor is full (5). Remove someone to make room.' : `${count} of ${MAX_SEATS} seats taken.`;
  }
  function choosePicked(slug) {
    if (pickerMode === 'debate') { closeModal(); return window.__agora.pullIn(slug); }
    if (AG.picked.includes(slug)) return;
    if (AG.picked.length >= MAX_SEATS) return flash('The floor holds five. Remove someone first.');
    AG.picked.push(slug);
    renderHall();
    renderPicker();
    if (AG.picked.length >= MAX_SEATS) closeModal();
  }

  window.__agora = { AG, esc, sleep, niche, miniAv, face, tag, colonnade, tallyOf, tallyBar, miniTally, nameOf, firstName, person, get, post, halls, hallDetail, ensurePeople, openAgora, closeAgora, openHall, renderHall, togglePick, openPicker, closeModal, flash, setURL, syncAside, pastItem, THINKING, MOVE_LABEL, STANCE_LABEL, MAX_SEATS, MIN_SEATS, view, page };
})();
