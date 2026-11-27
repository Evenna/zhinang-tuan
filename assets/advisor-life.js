/* Advisor life panel: biography timeline + works, with live highlighting of what the advisor just mentioned.
   Data: window.PERSON_TIMELINES (bundled) with fallback to `${ASK_SOCRATES_API}/people/{slug}/timeline`. */
(() => {
  const esc = value => String(value ?? '').replace(/[&<>"]/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[ch]));
  const cache = {};
  const STOP = new Set(['about', 'after', 'their', 'there', 'which', 'would', 'where', 'these', 'those', 'being', 'first', 'world', 'great', 'years', 'while', 'other', 'under', 'became', 'begins', 'began', 'with', 'from', 'into', 'that', 'this', 'when', 'what', 'life', 'work', 'born', 'death', 'dies', 'died']);
  const KIND_LABEL = {life: 'Life', work: 'Work', turning: 'Turning point'};

  async function load(slug) {
    if (!slug) return null;
    if (cache[slug]) return cache[slug];
    let data = window.PERSON_TIMELINES?.[slug] || null;
    if (!data && window.ASK_SOCRATES_API) {
      try {
        const response = await fetch(`${window.ASK_SOCRATES_API}/people/${encodeURIComponent(slug)}/timeline`);
        if (response.ok) data = await response.json();
      } catch (error) { /* offline */ }
    }
    if (data) {
      (data.events || []).forEach(event => {
        const words = `${event.title} ${(event.keywords || []).join(' ')}`.toLowerCase().match(/[a-z\u00c0-\u024f][a-z\u00c0-\u024f'’-]{3,}/g) || [];
        event._terms = [...new Set([...(event.keywords || []).map(k => k.toLowerCase()), ...words.filter(w => !STOP.has(w))])];
        event._years = (String(event.year).match(/\d{3,4}/g) || []);
      });
      (data.works || []).forEach(work => {
        work._terms = [String(work.title || '').toLowerCase().replace(/^the\s+/, '').replace(/[“”"']/g, '')].filter(t => t.length > 3);
      });
    }
    cache[slug] = data;
    return data;
  }

  function renderInto(root, data, person = {}) {
    if (!root) return;
    if (!data) {
      root.innerHTML = `<div class="al-empty">No timeline yet for ${esc(person.name || 'this advisor')}.</div>`;
      return;
    }
    const events = (data.events || []).map((event, index) => `
      <li class="al-event is-${esc(event.kind || 'life')}" data-al-event="${index}">
        <span class="al-year">${esc(event.year)}</span>
        <div class="al-title">${esc(event.title)}</div>
        ${event.detail ? `<div class="al-detail">${esc(event.detail)}</div>` : ''}
      </li>`).join('');
    const works = (data.works || []).map((work, index) => `<li class="al-work" data-al-work="${index}">${esc(work.title)}</li>`).join('');
    root.innerHTML = `
      <ol class="al-timeline">${events}</ol>
      ${works ? `<ul class="al-works">${works}</ul>` : ''}
    `;
    root.dataset.slug = data.slug;
    root.scrollTop = 0;
  }

  async function render(root, slug, person = {}) {
    if (!root) return null;
    if (root.dataset.slug === slug && root.querySelector('.al-timeline')) return cache[slug];
    root.dataset.slug = slug;
    root.innerHTML = '<div class="al-empty">Loading life story…</div>';
    const data = await load(slug);
    if (root.dataset.slug !== slug) return data;
    renderInto(root, data, person);
    return data;
  }

  function score(text, data) {
    const hay = ` ${String(text || '').toLowerCase()} `;
    const hits = [];
    (data?.events || []).forEach((event, index) => {
      let s = 0;
      event._years.forEach(year => { if (hay.includes(year)) s += 3; });
      event._terms.forEach(term => { if (term.length > 3 && hay.includes(term)) s += term.includes(' ') ? 2 : 1; });
      if (s >= 2) hits.push({type: 'event', index, s, label: event.title});
    });
    (data?.works || []).forEach((work, index) => {
      if (work._terms.some(term => hay.includes(term))) hits.push({type: 'work', index, s: 4, label: work.title});
    });
    return hits.sort((a, b) => b.s - a.s);
  }

  /* Highlight events/works mentioned in `text`. Returns number of hits. */
  function highlight(root, text) {
    const slug = root?.dataset.slug;
    const data = slug && cache[slug];
    if (!root || !data) return 0;
    root.querySelectorAll('.is-hit').forEach(el => el.classList.remove('is-hit', 'is-pulse'));
    const hits = score(text, data).slice(0, 3);
    const mention = root.querySelector('.al-mention');
    if (!hits.length) { if (mention) mention.hidden = true; return 0; }
    hits.forEach((hit, order) => {
      const el = root.querySelector(hit.type === 'event' ? `[data-al-event="${hit.index}"]` : `[data-al-work="${hit.index}"]`);
      if (!el) return;
      el.classList.add('is-hit');
      void el.offsetWidth;
      el.classList.add('is-pulse');
      if (order === 0) {
        const top = el.offsetTop - root.clientHeight * 0.3;
        root.scrollTo({top: Math.max(0, top), behavior: 'smooth'});
      }
    });
    if (mention) {
      mention.hidden = false;
      mention.innerHTML = `<span>Mentioned</span> ${hits.map(hit => esc(hit.label)).join('<i>·</i>')}`;
    }
    return hits.length;
  }

  async function bestMatch(slugs, text) {
    let best = null;
    for (const slug of slugs) {
      const data = await load(slug);
      const top = score(text, data)[0];
      if (top && (!best || top.s > best.s)) best = {slug, s: top.s};
    }
    return best?.slug || null;
  }

  async function mentions(slug, text) {
    const data = await load(slug);
    return Boolean(data && score(text, data).length);
  }

  window.AdvisorLife = {load, render, highlight, bestMatch, mentions};
})();
