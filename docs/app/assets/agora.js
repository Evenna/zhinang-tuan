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

  // Line art traced 1:1 from the approved design plates (assets/agora-*-lines.webp).
  function colonnade(kind = 'debate') {
    return `<div class="ag-colonnade ag-lines ag-lines--${kind}" aria-hidden="true"></div>`;
  }
  function colonnadeSvg() {
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
    if (!menu.querySelector(':scope > .ag-colonnade')) menu.insertAdjacentHTML('afterbegin', colonnade('index'));
    if (wall.dataset.hall === hall.id) return;
    wall.dataset.hall = hall.id;
    const featured = new Set(hall.featured);
    const paint = (residents, fade) => {
      // faint wall of the hall's residents; the lit ones are placed afterwards into gaps the words don't cover
      const rest = residents.filter((r) => !featured.has(r.slug));
      const pool = rest.length ? rest : residents;
      const slots = [];
      let sd = [...hall.id].reduce((x, c) => x * 31 + c.charCodeAt(0), 7) >>> 0;
      const rn = () => { sd = (sd * 1664525 + 1013904223) >>> 0; return sd / 4294967296; };
      // shuffled passes, no neighbour repeats at the seams, so the repetition doesn't read as a pattern
      while (slots.length < 72) { const pass = pool.slice().sort(() => rn() - 0.5); if (slots.length && pass[0] === slots[slots.length - 1]) pass.push(pass.shift()); slots.push(...pass); }
      if (fade) wall.classList.remove('is-in');
      wall.innerHTML = slots.slice(0, Math.max(72, pool.length)).map((r, i) => niche(r.slug, { width: 84, plate: false, attrs: `tabindex="-1" data-d="${i % 12}"` })).join('');
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
  // Light a few residents only where no word sits, spread evenly over top / middle / bottom.
  function placeLit(wall, hall, rest) {
    const menu = wall.parentElement;
    const niches = [...wall.querySelectorAll('.ag-niche')];
    if (!niches.length) return;
    const words = [];
    menu.querySelectorAll('.theme-row').forEach((row) => {
      const t = row.querySelector('.theme-title');
      if (t) {
        const r = document.createRange(); r.selectNodeContents(t);
        const b = r.getBoundingClientRect();
        const pad = b.height * 0.2; // range box includes line-height; trim to the glyphs
        words.push({ l: b.left - 70, r: b.right + 20, t: b.top + pad, b: b.bottom - pad * 0.6 }); // room for the hover shift + arrow
      }
      const n = row.querySelector('.theme-num');
      if (n) { const b = n.getBoundingClientRect(); words.push({ l: b.left - 14, r: b.right + 14, t: b.top - 10, b: b.bottom + 10 }); }
    });
    const box = wall.getBoundingClientRect();
    const fade = (b) => b.left < box.left + 20 || b.right > box.right - 20 || b.top < box.top + 20 || b.bottom > box.bottom - 30;
    const free = niches.map((el) => ({ el, b: el.getBoundingClientRect() }))
      .filter(({ b }) => b.width && !fade(b) && !words.some((w) => b.left < w.r && b.right > w.l && b.top < w.b && b.bottom > w.t))
      .map((o) => ({ ...o, x: o.b.left + o.b.width / 2, y: o.b.top + o.b.height / 2 }));
    // dim every niche that sits under a word even further, so the type always wins
    niches.forEach((el) => {
      const b = el.getBoundingClientRect();
      el.classList.toggle('is-under', words.some((w) => b.left < w.r && b.right > w.l && b.top < w.b && b.bottom > w.t));
    });
    // Lit residents float freely in the open space left of the words (not snapped to the wall grid),
    // one per vertical band so the composition never gets top-heavy.
    let seed = [...hall.id].reduce((a, c) => a * 31 + c.charCodeAt(0), 7) >>> 0;
    const rnd = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };
    const NW = 78, NH = Math.round(NW * 1.4), GAP = 44;
    const blocked = words.map((w) => ({ l: w.l - GAP, r: w.r + GAP, t: w.t - GAP * 0.6, b: w.b + GAP * 0.6 }));
    const aside = document.querySelector('#themesPage .theme-aside')?.getBoundingClientRect();
    const minX = Math.max(box.left + 40, aside ? aside.right + 60 : 0);
    const cands = [];
    for (let y = box.top + 40; y + NH < box.bottom - 40; y += 14) {
      for (let x = minX; x + NW < box.right - 30; x += 14) {
        if (!blocked.some((w) => x < w.r && x + NW > w.l && y < w.b && y + NH > w.t)) cands.push({ x, y, cx: x + NW / 2, cy: y + NH / 2 });
      }
    }
    wall.querySelectorAll('.ag-lit-float').forEach((n) => n.remove());
    if (!cands.length) return;
    // one light per horizontal band (top → bottom), zig-zagging left/right so they read as a loose constellation
    const want = hall.featured.length + 1;
    const H = box.bottom - box.top;
    const picks = [];
    const xs = cands.map((c) => c.cx), xMin = Math.min(...xs), xMax = Math.max(...xs);
    let side = rnd() < 0.5 ? 0 : 1;
    for (let k = 0; k < want; k += 1) {
      const lo = box.top + 30 + ((H - 60) * k) / want, hi = box.top + 30 + ((H - 60) * (k + 1)) / want;
      const inBand = cands.filter((c) => c.y >= lo - 10 && c.y + NH <= hi + 30 && !picks.some((p) => Math.abs(p.cy - c.cy) < NH + 16 && Math.abs(p.cx - c.cx) < NW + 30));
      if (!inBand.length) continue;
      const target = side ? xMax : xMin; side = 1 - side;
      let best = null, bestS = Infinity;
      inBand.forEach((c) => { const sc = Math.abs(c.cx - target) + Math.abs(c.cy - (lo + hi) / 2) * 0.6 + rnd() * 40; if (sc < bestS) { bestS = sc; best = c; } });
      picks.push(best);
    }
    // stagger: alternate the bands between the inner and outer half so they zig-zag instead of forming a line
    picks.sort((a, b) => a.cy - b.cy);
    const extra = rest.slice().sort(() => rnd() - 0.5);
    const order = [...hall.featured, ...extra.map((r) => r.slug)];
    const featuredBands = picks.map((_, i) => i).sort(() => rnd() - 0.5);
    const isFeat = new Set(featuredBands.slice(0, hall.featured.length));
    let fi = 0, ei = hall.featured.length;
    picks.forEach((p, i) => {
      const feat = isFeat.has(i);
      const slug = feat ? order[fi++] : order[ei++];
      if (!slug) return;
      const tmp = document.createElement('div');
      tmp.innerHTML = niche(slug, { width: NW, plate: false, cls: `ag-lit-float ${feat ? 'is-lit' : 'is-glow'}`, attrs: `tabindex="-1" data-d="${i * 2}"` }).trim();
      const el = tmp.firstElementChild;
      el.style.left = `${p.x - box.left}px`; el.style.top = `${p.y - box.top}px`;
      wall.append(el);
    });
    // fade the grid niches the floating ones sit on
    const lit = [...wall.querySelectorAll('.ag-lit-float')].map((e) => e.getBoundingClientRect());
    niches.forEach((el) => { const b = el.getBoundingClientRect(); if (lit.some((l) => b.left < l.right + 8 && b.right > l.left - 8 && b.top < l.bottom + 8 && b.bottom > l.top - 8)) el.classList.add('is-under'); });
  }
  window.addEventListener('resize', () => {
    clearTimeout(AG._wallT);
    AG._wallT = setTimeout(() => { const w = document.querySelector('#themesPage .ag-wall'); if (w?.dataset.hall) { const id = w.dataset.hall; w.dataset.hall = ''; halls().then((l) => { const h = l.find((x) => x.id === id); if (h) paintWall(h); }).catch(() => {}); } }, 250);
  });

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
    const residents = hall.residents.map((r) => r.slug);
    const guests = AG.picked.filter((s) => !residents.includes(s));
    const pool = [...guests, ...residents];
    const motions = hall.motions.filter((m) => m !== AG.motion).slice(0, 3);
    view.innerHTML = `<div class="ag-hall ag-hall--v7">${colonnade()}
      <div class="ag-hall-main">
        <div class="ag-crumb"><button type="button" data-ag-back-index>Themes</button><span>/</span><span>${esc(hall.title)} · ${esc(hall.zh || '')}</span></div>
        <h1 class="ag-h1">The <em>${esc(hall.title)}</em> Hall</h1>
        <div class="ag-motion-box">
          <textarea class="ag-motion-input" id="agMotion" rows="2" maxlength="300" placeholder="Write a motion — a question with a yes or no">${esc(AG.motion)}</textarea>
          <div class="ag-motion-alt"><span class="ag-motion-or">or</span>${motions.map((m) => `<button type="button" class="ag-alt" data-ag-motion="${esc(m)}">${esc(m)}</button>`).join('')}</div>
        </div>
        <div class="ag-pick-head"><span>Who takes the floor</span><b id="agPickCount">${AG.picked.length} / ${MAX_SEATS}</b><button type="button" class="ag-alt" data-ag-invite>Invite anyone →</button></div>
        <div class="ag-gallery" id="agGallery">${pool.map((s) => niche(s, { width: 88, picked: picked.has(s), attrs: 'data-ag-pick' })).join('')}</div>
        <div class="ag-hall-foot">
          <span class="ag-floor-hint" id="agPickHint">${pickHint()}</span>
          <button type="button" class="ag-btn is-solid" data-ag-open ${AG.picked.length < MIN_SEATS ? 'disabled' : ''}>Open the debate →</button>
        </div>
      </div>
      <aside class="ag-side">
        <div class="ag-side-head">On record · ${hall.debates.length}</div>
        <div class="ag-side-list">${hall.debates.map(pastLine).join('') || '<p class="ag-side-note">No debates yet. Yours could be the first.</p>'}</div>
      </aside>
    </div>`;
    const g = document.getElementById('agGallery');
    g?.addEventListener('wheel', (e) => { if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { g.scrollLeft += e.deltaY; e.preventDefault(); } }, { passive: false });
  }
  function pickHint() {
    return AG.picked.length < MIN_SEATS ? `Choose at least ${MIN_SEATS}` : AG.picked.map((s) => esc(firstName(s))).join(' · ');
  }

  function pastLine(d) {
    return `<button type="button" class="ag-past ag-past--line" data-ag-read="${esc(d.id)}">
      <div class="ag-past-q">${esc(d.motion)}</div>
      <div class="ag-past-row"><span class="ag-faces">${(d.participants || []).map(face).join('')}</span><span>${esc(d.name || '')} · ${d.replies} replies</span></div>
    </button>`;
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
    // update in place — no re-render, nothing jumps
    document.querySelectorAll('#agGallery .ag-niche').forEach((n) => n.classList.toggle('is-picked', AG.picked.includes(n.dataset.slug)));
    const c = document.getElementById('agPickCount'); if (c) c.textContent = `${AG.picked.length} / ${MAX_SEATS}`;
    const h = document.getElementById('agPickHint'); if (h) h.innerHTML = pickHint();
    const b = document.querySelector('[data-ag-open]'); if (b) b.disabled = AG.picked.length < MIN_SEATS;
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
    modal.querySelector('h3').textContent = mode === 'debate' ? 'Invite someone in' : 'Invite to the floor';
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
