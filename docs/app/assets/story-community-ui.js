/** A finite odometer animation, retargeted from its current visible position. */
class StoryRollingNumber {
  constructor(element) {
    this.element = element;
    this.value = 0;
    this.reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    this.reducedMotion.addEventListener('change', () => this.set(this.value, false));
    this.height = null;
    new ResizeObserver(entries => {
      const height = entries[0].contentRect.height;
      if (this.height !== null && height !== this.height) this.set(this.value, false);
      this.height = height;
    }).observe(element);
  }

  set(value, animate = true) {
    this.value = Math.max(0, Math.round(value));
    const text = String(this.value).padStart(2, '0');
    this.element.setAttribute('aria-label', String(this.value));
    if (this.element.children.length !== text.length) {
      this.element.replaceChildren(...Array.from(text, () => {
        const digit = document.createElement('span');
        digit.className = 'story-number-digit';
        digit.setAttribute('aria-hidden', 'true');
        const reel = document.createElement('span');
        reel.className = 'story-number-reel';
        reel.append(...Array.from({length: 30}, (_, index) => {
          const cell = document.createElement('span');
          cell.textContent = String(index % 10);
          return cell;
        }));
        digit.append(reel);
        return digit;
      }));
    }
    const size = parseFloat(getComputedStyle(this.element).fontSize);
    const measured = Array.from(this.element.children, (digit, index) => {
      const reel = digit.firstElementChild;
      const transform = getComputedStyle(reel).transform;
      const offset = transform === 'none' ? 0 : -new DOMMatrixReadOnly(transform).m42 / size;
      return {reel, index, start: ((offset % 10) + 10) % 10, target: Number(text[index])};
    });
    for (const {reel, index, start, target} of measured) {
      reel.getAnimations().forEach(animation => animation.cancel());
      if (!animate || this.reducedMotion.matches) {
        reel.style.transform = `translateY(-${target}em)`;
        continue;
      }
      let end = 10 + target;
      if (end - start < 7) end += 10;
      reel.style.transform = `translateY(-${start}em)`;
      const animation = reel.animate([
        {transform: `translateY(-${start}em)`},
        {transform: `translateY(-${end}em)`}
      ], {duration: 800, delay: index * 45, easing: 'cubic-bezier(0.16, 1, 0.3, 1)', fill: 'both'});
      animation.onfinish = () => {
        reel.style.transform = `translateY(-${target}em)`;
        animation.cancel();
      };
    }
  }
}

/* Demo data is isolated in story-community.js; the scene consumes advisor/user/story records. */
class StoryCommunityScene {
  constructor(root, onSelect) {
    this.root = root;
    this.field = root.querySelector('.story-user-field');
    this.hint = root.querySelector('.story-user-hint');
    this.onSelect = onSelect;
    this.peopleNumber = new StoryRollingNumber(root.querySelector('#storyPeopleNumber'));
    this.topicsNumber = new StoryRollingNumber(root.querySelector('#storyTopicsNumber'));
    this.selections = new Map();
    this.advisor = null;
    this.frame = 0;
    this.resizeObserver = new ResizeObserver(() => this.scheduleLayout());
    this.resizeObserver.observe(root);
    this.resizeObserver.observe(root.querySelector('.story-meta'));
    this.field.addEventListener('click', event => {
      const tile = event.target.closest('[data-community-user]');
      if (tile && !tile.classList.contains('is-text-muted')) this.select(tile.dataset.communityUser, tile);
    });
    this.field.addEventListener('pointerover', event => this.showHint(event.target.closest('[data-community-user]')));
    this.field.addEventListener('pointerleave', () => this.hideHint());
    this.field.addEventListener('focusin', event => this.showHint(event.target.closest('[data-community-user]')));
    this.field.addEventListener('focusout', () => this.hideHint());
    document.fonts.ready.then(() => this.scheduleLayout());
  }

  setAdvisor(advisor) {
    if (!advisor || advisor.slug === this.advisor?.slug) return;
    this.advisor = advisor;
    this.peopleNumber.set(new Set(advisor.users.map(user => user.id)).size);
    this.topicsNumber.set(new Set(advisor.users.flatMap(user => user.topics || [])).size);
    this.field.dataset.advisor = advisor.slug;
    this.field.setAttribute('aria-label', `Sample stories exploring questions with ${advisor.name}`);
    const user = advisor.users.find(item => item.id === this.selections.get(advisor.slug)) || advisor.users[0];
    this.selectedUser = user;
    this.selectedTile = null;
    this.renderField();
    this.onSelect(user, advisor);
    this.hideHint();
    this.scheduleLayout();
  }

  renderField() {
    if (!this.advisor) return;
    const columns = Math.ceil(this.root.clientWidth / 124) + 8;
    const rows = Math.ceil(this.root.clientHeight / 112) + 8;
    this.columns = columns;
    this.rows = rows;
    const plane = document.createElement('div');
    plane.className = 'story-user-plane';
    plane.style.setProperty('--community-columns', columns);
    const fragment = document.createDocumentFragment();
    const users = this.advisor.users;
    // A stable shuffle avoids repeated columns while keeping the field still under the pointer.
    const order = users.map((_, index) => index);
    let seed = Array.from(this.advisor.slug).reduce((value, letter) => (value * 31 + letter.charCodeAt(0)) >>> 0, 7);
    for (let index = order.length - 1; index > 0; index--) {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      const swap = seed % (index + 1);
      [order[index], order[swap]] = [order[swap], order[index]];
    }
    for (let index = 0; index < columns * rows; index++) {
      const user = users[order[(index + Math.floor(index / users.length) * 17) % users.length]];
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'story-user-tile';
      button.dataset.communityUser = user.id;
      button.setAttribute('aria-label', `${user.name}: ${user.headline}`);
      button.setAttribute('aria-pressed', 'false');
      button.tabIndex = -1;
      button.style.setProperty('--user-depth', `${(index % 5) * 2}px`);
      const image = document.createElement('img');
      image.src = user.avatar;
      image.alt = '';
      image.width = 128;
      image.height = 128;
      image.decoding = 'async';
      button.append(image);
      fragment.append(button);
    }
    plane.append(fragment);
    this.field.replaceChildren(plane);
  }

  select(id, tile) {
    const user = this.advisor.users.find(item => item.id === id);
    if (!user) return;
    this.selectedUser = user;
    this.selectedTile = tile;
    this.selections.set(this.advisor.slug, id);
    this.field.querySelectorAll('.is-selected').forEach(item => {
      item.classList.remove('is-selected');
      item.setAttribute('aria-pressed', 'false');
    });
    if (tile) {
      tile.classList.add('is-selected');
      tile.setAttribute('aria-pressed', 'true');
    }
    this.onSelect(user, this.advisor);
    this.hideHint();
    this.scheduleLayout();
  }

  scheduleLayout() {
    cancelAnimationFrame(this.frame);
    this.frame = requestAnimationFrame(() => this.layout());
  }

  layout() {
    if (!this.advisor || !this.root.clientWidth || !this.root.closest('.show')) return;
    this.placeStoryPanel();
    const columns = Math.ceil(this.root.clientWidth / 124) + 8;
    const rows = Math.ceil(this.root.clientHeight / 112) + 8;
    if (this.columns !== columns || this.rows !== rows) this.renderField();
    const rootRect = this.root.getBoundingClientRect();
    const textRects = ['.story-intro', '.story-meta'].map(selector => this.root.querySelector(selector).getBoundingClientRect());
    // Read all transformed geometry before writing styles; no per-frame animation loop.
    const measured = Array.from(this.field.querySelectorAll('button'), tile => ({tile, rect: tile.getBoundingClientRect()}));
    const focusable = new Set();
    let highlighted = false;
    for (const {tile, rect} of measured) {
      const x = (rect.left + rect.right) / 2;
      const y = (rect.top + rect.bottom) / 2;
      const distance = Math.min(...textRects.map(text => Math.hypot(Math.max(text.left - x, 0, x - text.right), Math.max(text.top - y, 0, y - text.bottom))));
      const proximity = Math.max(0, 1 - distance / 150);
      const base = 0.22 + ((tile.dataset.communityUser.length % 4) * 0.01);
      tile.style.setProperty('--user-opacity', (base * (1 - proximity) + 0.035 * proximity).toFixed(3));
      tile.style.setProperty('--user-blur', `${(proximity * 3.2).toFixed(1)}px`);
      const muted = proximity > 0.8;
      tile.classList.toggle('is-text-muted', muted);
      const inView = rect.right > rootRect.left && rect.left < rootRect.right && rect.bottom > rootRect.top && rect.top < rootRect.bottom;
      const canFocus = !muted && inView && !focusable.has(tile.dataset.communityUser);
      tile.tabIndex = canFocus ? 0 : -1;
      if (canFocus) focusable.add(tile.dataset.communityUser);
      const selected = this.selectedTile?.isConnected
        ? tile === this.selectedTile && !muted
        : !highlighted && canFocus && tile.dataset.communityUser === this.selectedUser.id;
      tile.classList.toggle('is-selected', selected);
      tile.setAttribute('aria-pressed', String(selected));
      if (selected) highlighted = true;
    }
  }

  placeStoryPanel() {
    const mobile = this.root.clientWidth <= 700;
    const header = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--site-header-height')) || 101;
    const base = mobile ? 1100 : Math.max(0, innerHeight - header);
    const panel = this.root.querySelector('.story-meta');
    this.root.style.setProperty('--story-scene-height', `${base}px`);
    let anchor = base * (mobile ? 0.45 : 0.48);
    this.root.style.setProperty('--story-ribbon-y', `${anchor}px`);
    const rootRect = this.root.getBoundingClientRect();
    if (mobile) {
      const rect = panel.getBoundingClientRect();
      const bottoms = Array.from(this.root.querySelectorAll('.story-card'), card => card.getBoundingClientRect())
        .filter(card => card.right > rect.left - 20 && card.left < rect.right + 20)
        .map(card => card.bottom - rootRect.top);
      const top = Math.max(base * 0.55, Math.max(0, ...bottoms) + 48);
      this.root.style.setProperty('--story-panel-y', `${top}px`);
      this.root.style.setProperty('--story-scene-height', `${Math.max(base, top + panel.offsetHeight + 28)}px`);
    } else {
      // Both text areas share the two negative-space corners of a single viewport.
      // Keep the entire story visible; adjust the ribbon's anchor within the space between them.
      this.root.classList.remove('is-compact-story');
      for (let attempt = 0; attempt < 2; attempt++) {
        const top = base - panel.offsetHeight - 24;
        this.root.style.setProperty('--story-panel-y', `${top}px`);
        const introRect = this.root.querySelector('.story-intro').getBoundingClientRect();
        const panelRect = panel.getBoundingClientRect();
        const cards = Array.from(this.root.querySelectorAll('.story-card'), card => card.getBoundingClientRect());
        const above = cards.filter(card => card.right > introRect.left && card.left < introRect.right);
        const below = cards.filter(card => card.right > panelRect.left && card.left < panelRect.right);
        const minTop = Math.min(...above.map(card => card.top));
        const maxBottom = Math.max(...below.map(card => card.bottom));
        const lowerShift = introRect.bottom + 24 - minTop;
        const upperShift = panelRect.top - 36 - maxBottom;
        if (lowerShift <= upperShift) {
          anchor += Math.max(lowerShift, Math.min(0, upperShift));
          this.root.style.setProperty('--story-ribbon-y', `${anchor}px`);
          break;
        }
        this.root.classList.add('is-compact-story');
      }
    }
    this.root.dataset.layoutReady = 'true';
  }

  showHint(tile) {
    if (!tile || tile.classList.contains('is-text-muted')) return this.hideHint();
    const user = this.advisor.users.find(item => item.id === tile.dataset.communityUser);
    if (!user) return;
    const root = this.root.getBoundingClientRect();
    const card = tile.getBoundingClientRect();
    const name = document.createElement('strong');
    name.textContent = user.name;
    const question = document.createElement('span');
    question.textContent = user.headline;
    this.hint.replaceChildren(name, question);
    this.hint.hidden = false;
    const width = this.hint.offsetWidth;
    this.hint.style.left = `${Math.max(16, Math.min(root.width - width - 16, card.right - root.left + 10))}px`;
    this.hint.style.top = `${Math.max(12, Math.min(root.height - this.hint.offsetHeight - 12, card.top - root.top))}px`;
  }

  hideHint() { this.hint.hidden = true; }
}
window.StoryCommunityScene = StoryCommunityScene;

/* Full conversation reader: opens a past session (1:1 chat + roundtable + what happened next). */
(() => {
  const esc = value => String(value ?? '').replace(/[&<>"]/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[ch]));
  const titleCase = slug => String(slug).split('-').map(part => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
  const portrait = slug => `assets/character_cutouts/${slug}.png`;
  const advisorName = slug => {
    const person = (window.ASK_SOCRATES_CATALOG || window.ASK_SOCRATES_PREVIEW?.people || []).find(item => item.slug === slug);
    return person?.english_name || titleCase(slug);
  };
  const imgTag = (src, alt) => `<img src="${esc(src)}" alt="${esc(alt)}" onerror="if(!this.dataset.f){this.dataset.f=1;this.src=this.src.replace(/\\.png$/,'.webp')}">`;
  let overlay = null;

  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.className = 'story-transcript';
    overlay.hidden = true;
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.addEventListener('click', event => {
      if (event.target === overlay || event.target.closest('.st-close')) close();
      const ask = event.target.closest('[data-st-ask]');
      if (ask) { close(); document.getElementById('storyAsk')?.click(); }
    });
    document.addEventListener('keydown', event => { if (event.key === 'Escape' && !overlay.hidden) close(); });
    document.body.append(overlay);
    return overlay;
  }

  function close() { if (overlay) { overlay.hidden = true; document.body.style.overflow = ''; } }

  async function loadFull(user, advisor) {
    const api = window.ASK_SOCRATES_API;
    if (api && user.id) {
      try {
        const response = await fetch(`${api}/stories/${user.id}`);
        if (response.ok) return await response.json();
      } catch (error) { /* fall back to the bundled copy */ }
    }
    return {...user, advisor_slug: advisor.slug, advisor_name: advisor.name};
  }

  const LIKE_KEY = 'askSocrates.likedStories';
  const COMMENT_KEY = 'askSocrates.storyComments';
  function readStore(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) || fallback; } catch (error) { return fallback; } }
  function writeStore(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (error) {} }
  function turnsOf(story) {
    if (Array.isArray(story.transcript) && story.transcript.length) {
      return story.transcript.map(t => ({speaker: t.speaker === 'host' ? 'system' : t.speaker, text: t.text}));
    }
    const solo = (story.conversation || []).map(t => ({speaker: t.role === 'user' ? 'user' : story.advisor_slug, text: t.text}));
    const table = (story.roundtable || []).map(t => ({speaker: t.speaker, text: t.text}));
    return table.length ? [...solo, {speaker: 'system', text: 'Moved to roundtable'}, ...table] : solo;
  }
  function speakerName(story, slug) {
    if (slug === 'user') return (story.name || 'User').split(' ')[0];
    if (slug === story.advisor_slug && story.advisor_name) return story.advisor_name;
    return window.STORY_COMMUNITY?.names?.[slug] || advisorName(slug);
  }
  function renderSocial(root, story) {
    const liked = !!readStore(LIKE_KEY, {})[story.id];
    const likeBtn = root.querySelector('[data-st-like]');
    likeBtn.classList.toggle('is-on', liked);
    likeBtn.querySelector('b').textContent = (story.likes ?? story.resonance ?? 0) + (liked ? 1 : 0);
    const mine = readStore(COMMENT_KEY, {})[story.id] || [];
    const all = [...mine, ...(story.comments || [])];
    root.querySelector('[data-st-comment-count]').textContent = all.length;
    root.querySelector('.st-comments-list').innerHTML = all.map(c => `<div class="st-comment${c.is_author ? ' is-author' : ''}${c.mine ? ' is-mine' : ''}">
      <div class="st-comment-head"><b>${esc(c.name)}</b>${c.is_author ? '<span class="st-badge">author</span>' : ''}${c.mine ? '<span class="st-badge">you</span>' : ''}<span class="st-comment-likes">${esc(c.likes ?? 0)} ♥</span></div>
      <p>${esc(c.text)}</p></div>`).join('') || '<p class="st-empty">No comments yet.</p>';
  }

  async function open(user, advisor) {
    if (!user || !advisor) return;
    const root = ensureOverlay();
    root.innerHTML = '<div class="st-panel"><button class="st-close" type="button" aria-label="Close">×</button><div class="st-meta">Loading…</div></div>';
    root.hidden = false;
    document.body.style.overflow = 'hidden';
    const story = {advisor_slug: advisor.slug, advisor_name: advisor.name, ...(await loadFull(user, advisor))};
    const date = story.date ? new Date(story.date).toLocaleDateString('en-US', {month: 'short', day: 'numeric', year: 'numeric'}) : '';
    const turns = turnsOf(story);
    const participants = story.participants?.length ? story.participants : [...new Set(turns.map(t => t.speaker).filter(s => s !== 'user'))];
    const isTable = story.mode === 'roundtable' || participants.length > 1;
    const sum = story.summary || {};
    let prev = '';
    const norm = t => String(t || '').replace(/\W+/g, '').toLowerCase();
    const body = turns[0]?.speaker === 'user' && norm(turns[0].text) === norm(story.question) ? turns.slice(1) : turns;
    const chat = body.map(turn => {
      if (turn.speaker === 'system') { prev = ''; return `<div class="st-sys">${esc(turn.text)}</div>`; }
      const mine = turn.speaker === 'user';
      const showName = turn.speaker !== prev;
      prev = turn.speaker;
      return `<div class="st-line${mine ? ' is-user' : ''}${showName ? '' : ' is-cont'}">${showName ? `<span class="st-who">${esc(mine ? (story.name || 'User').split(' ')[0] : speakerName(story, turn.speaker))}</span>` : ''}<p>${esc(turn.text)}</p></div>`;
    }).join('');
    const summary = sum.conclusion || sum.tldr || story.context || '';
    root.innerHTML = `<div class="st-panel">
      <button class="st-close" type="button" aria-label="Close">×</button>
      <header class="st-top">
        <div class="st-kicker">${esc(story.name)}${date ? ` · ${esc(date)}` : ''}</div>
        <h2 class="st-headline">${esc(story.question)}</h2>
        ${summary ? `<p class="st-tldr">${esc(summary)}</p>` : ''}
      </header>
      <div class="st-transcript">${chat}</div>
      <div class="st-actions">
        <button type="button" class="st-act" data-st-like>♥ <b></b></button>
        <button type="button" class="st-act" data-st-jump-comments>Comments <b data-st-comment-count></b></button>
        <button type="button" class="st-act" data-st-share>Share</button>
        <span class="st-share-tip" hidden>Link copied</span>
        <button class="st-ask" type="button" data-st-ask>Ask your own</button>
      </div>
      <section class="st-comments">
        <form class="st-comment-form"><input name="c" placeholder="Add a thought" autocomplete="off"><button type="submit">Post</button></form>
        <div class="st-comments-list"></div>
      </section>
      <div class="st-note">Illustrative story. The person is fictional; advisor replies are AI personas.</div>
    </div>`;
    renderSocial(root, story);
    root.querySelector('.st-panel').scrollTop = 0;
    root.querySelector('[data-st-like]').onclick = () => {
      const liked = readStore(LIKE_KEY, {});
      if (liked[story.id]) delete liked[story.id]; else liked[story.id] = 1;
      writeStore(LIKE_KEY, liked);
      renderSocial(root, story);
    };
    root.querySelector('[data-st-jump-comments]').onclick = () => root.querySelector('.st-comments').scrollIntoView({behavior: 'smooth', block: 'start'});
    root.querySelector('[data-st-share]').onclick = async () => {
      const url = new URL(location.href);
      url.searchParams.set('view', 'stories');
      url.searchParams.set('story', story.id);
      const tip = root.querySelector('.st-share-tip');
      try {
        if (navigator.share) await navigator.share({title: story.headline, text: story.question, url: url.href});
        else { await navigator.clipboard.writeText(url.href); tip.hidden = false; setTimeout(() => { tip.hidden = true; }, 1600); }
      } catch (error) { tip.textContent = url.href; tip.hidden = false; }
    };
    root.querySelector('.st-comment-form').onsubmit = event => {
      event.preventDefault();
      const input = event.target.elements.c;
      const text = input.value.trim();
      if (!text) return;
      const all = readStore(COMMENT_KEY, {});
      all[story.id] = [{name: 'You', text, likes: 0, mine: true}, ...(all[story.id] || [])];
      writeStore(COMMENT_KEY, all);
      input.value = '';
      renderSocial(root, story);
    };
  }

  function openFromUrl() {
    const id = new URLSearchParams(location.search).get('story');
    if (!id) return;
    for (const a of window.STORY_COMMUNITY?.advisors || []) {
      const u = a.users.find(item => item.id === id);
      if (u) { open(u, a); return; }
    }
  }
  if (document.readyState === 'complete') setTimeout(openFromUrl, 400); else addEventListener('load', () => setTimeout(openFromUrl, 400));

  window.openStoryTranscript = open;
  document.addEventListener('click', event => {
    if (!event.target.closest('#storyRead')) return;
    const scene = window.__storyScene;
    if (scene) open(scene.selectedUser, scene.advisor);
  });
  document.addEventListener('dblclick', event => {
    const tile = event.target.closest('[data-community-user]');
    const scene = window.__storyScene;
    if (!tile || !scene) return;
    open(scene.advisor.users.find(item => item.id === tile.dataset.communityUser), scene.advisor);
  });
})();
