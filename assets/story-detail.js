/* Story detail — a full-screen sub-page (no site nav).
   Left: the brief (question → summary → voices → answer → likes & comments).
   Right: the original conversation, avatar + bubble. */
(() => {
  const esc = v => String(v ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const titleCase = slug => String(slug).split('-').map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(' ');
  const catalog = () => window.ASK_SOCRATES_CATALOG || window.ASK_SOCRATES_PREVIEW?.people || [];
  const advisorName = slug => catalog().find(p => p.slug === slug)?.english_name || window.STORY_COMMUNITY?.names?.[slug] || titleCase(slug);
  const imgTag = src => `<img src="${esc(src)}" alt="" loading="lazy" onerror="if(!this.dataset.f){this.dataset.f=1;this.src=this.src.replace(/\\.png$/,'.webp')}">`;
  const LIKE_KEY = 'askSocrates.likedStories';
  const COMMENT_KEY = 'askSocrates.storyComments';
  const read = (k, f) => { try { return JSON.parse(localStorage.getItem(k)) || f; } catch (e) { return f; } };
  const write = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };

  function palette(slug) {
    const p = catalog().find(x => x.slug === slug) || {};
    try { if (typeof getPosterPalette === 'function') return getPosterPalette(p.english_name || advisorName(slug), p.chinese_name || ''); } catch (e) {}
    return ['#4a3d2a', '#6b5a3e'];
  }
  function arch(slug, cls = 'sd-av') {
    const [c1, c2] = palette(slug);
    return `<span class="${cls}" style="--c1:${c1};--c2:${c2}">${imgTag(`assets/character_cutouts/${slug}.${window.ASK_SOCRATES_CATALOG ? 'webp' : 'png'}`)}</span>`;
  }
  function turnsOf(s) {
    if (Array.isArray(s.transcript) && s.transcript.length) return s.transcript.map(t => ({speaker: t.speaker === 'host' ? 'system' : t.speaker, text: t.text}));
    const solo = (s.conversation || []).map(t => ({speaker: t.role === 'user' ? 'user' : s.advisor_slug, text: t.text}));
    const table = (s.roundtable || []).map(t => ({speaker: t.speaker, text: t.text}));
    return table.length ? [...solo, {speaker: 'system', text: 'Moved to the roundtable'}, ...table] : solo;
  }
  async function loadFull(user, advisor) {
    const api = window.ASK_SOCRATES_API;
    if (api && user.id) {
      try { const r = await fetch(`${api}/stories/${user.id}`); if (r.ok) return await r.json(); } catch (e) { /* bundled copy */ }
    }
    return {...user};
  }

  let root = null;
  let pushed = false;
  function ensure() {
    if (root) return root;
    root = document.createElement('div');
    root.className = 'sd';
    root.hidden = true;
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    document.body.append(root);
    root.addEventListener('click', e => {
      if (e.target.closest('[data-sd-back]')) close();
      if (e.target.closest('[data-st-ask]')) { close(); setTimeout(() => document.getElementById('storyAsk')?.click(), 60); }
    });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && !root.hidden) close(); });
    addEventListener('popstate', () => {
      if (!root.hidden && !new URLSearchParams(location.search).get('story')) { pushed = false; hide(); }
    });
    return root;
  }
  function hide() {
    root.hidden = true;
    document.body.classList.remove('is-deep');
    document.body.style.overflow = '';
  }
  function close() {
    if (!root || root.hidden) return;
    if (pushed) { pushed = false; history.back(); return; }
    const u = new URL(location.href); u.searchParams.delete('story'); history.replaceState(history.state, '', u);
    hide();
  }

  function renderSocial(story) {
    const liked = !!read(LIKE_KEY, {})[story.id];
    const like = root.querySelector('[data-st-like]');
    like.classList.toggle('is-on', liked);
    like.querySelector('b').textContent = Number(story.likes ?? story.resonance ?? 0) + (liked ? 1 : 0);
    const mine = read(COMMENT_KEY, {})[story.id] || [];
    const all = [...mine, ...(story.comments || [])];
    root.querySelector('[data-st-comment-count]').textContent = all.length;
    root.querySelector('.sd-comments-list').innerHTML = all.map(c => `<div class="sd-comment">
      <span class="sd-comment-av">${c.avatar ? `<img src="${esc(c.avatar)}" alt="" loading="lazy">` : esc(String(c.name || '?').charAt(0))}</span>
      <div><div class="sd-comment-head"><b>${esc(c.name)}</b>${c.is_author ? '<em>author</em>' : ''}${c.mine ? '<em>you</em>' : ''}<span>♥ ${esc(c.likes ?? 0)}</span></div>
      <p>${esc(c.text)}</p></div></div>`).join('') || '<p class="sd-empty">No comments yet.</p>';
  }

  async function open(user, advisor) {
    if (!user || !advisor) return;
    ensure();
    root.innerHTML = '<div class="sd-page"><header class="sd-bar"><button class="sd-back" type="button" data-sd-back>← Stories</button></header><div class="sd-loading">Opening the story…</div></div>';
    root.hidden = false;
    document.body.classList.add('is-deep');
    document.body.style.overflow = 'hidden';
    const url = new URL(location.href);
    if (url.searchParams.get('story') !== user.id) {
      url.searchParams.set('view', 'stories');
      url.searchParams.set('story', user.id);
      history.pushState({story: user.id}, '', url);
      pushed = true;
    }
    const story = {advisor_slug: advisor.slug, advisor_name: advisor.name, ...(await loadFull(user, advisor))};
    story.advisor_slug = story.advisor_slug || advisor.slug;
    const nameOf = slug => slug === story.advisor_slug && story.advisor_name ? story.advisor_name : advisorName(slug);
    const date = story.date ? new Date(story.date).toLocaleDateString('en-US', {month: 'short', day: 'numeric', year: 'numeric'}) : '';
    const turns = turnsOf(story);
    const participants = story.participants?.length ? story.participants : [...new Set(turns.map(t => t.speaker).filter(s => s !== 'user' && s !== 'system'))];
    const isTable = story.mode === 'roundtable' || participants.length > 1;
    const sum = story.summary || {};
    const first = (story.name || 'User').split(' ')[0];
    const userAv = story.avatar ? `<img class="sd-uav" src="${esc(story.avatar)}" alt="">` : `<span class="sd-uav">${esc(first[0])}</span>`;
    let prev = '';
    const chat = turns.map(t => {
      if (t.speaker === 'system') { prev = ''; return `<div class="sd-sys"><span>${esc(/roundtable/i.test(t.text) ? 'Moved to the roundtable' : t.text)}</span></div>`; }
      const mine = t.speaker === 'user';
      const cont = t.speaker === prev;
      prev = t.speaker;
      return `<div class="sd-msg${mine ? ' is-user' : ''}${cont ? ' is-cont' : ''}">
        <div class="sd-msg-av">${cont ? '' : (mine ? userAv : arch(t.speaker))}</div>
        <div class="sd-msg-body">${cont ? '' : `<span class="sd-who">${esc(mine ? first : nameOf(t.speaker))}</span>`}<div class="sd-bubble">${esc(t.text)}</div></div>
      </div>`;
    }).join('');
    const voices = (sum.positions || []).length
      ? sum.positions.map(p => `<li>${arch(p.speaker)}<div><b>${esc(nameOf(p.speaker))}</b><p>${esc(p.stance || p.text || '')}</p></div></li>`).join('')
      : participants.map(s => `<li>${arch(s)}<div><b>${esc(nameOf(s))}</b></div></li>`).join('');
    const turnCount = turns.filter(t => t.speaker !== 'system').length;

    root.innerHTML = `<div class="sd-page">
      <header class="sd-bar">
        <button class="sd-back" type="button" data-sd-back aria-label="Back to stories">← Stories</button>
        <span class="sd-bar-meta">${esc([isTable ? 'Roundtable' : 'One-on-one', date].filter(Boolean).join(' · '))}</span>
        <span class="sd-bar-end"><span class="sd-tip" hidden>Link copied</span><button type="button" class="sd-share" data-sd-share>Share</button></span>
      </header>
      <div class="sd-grid">
        <article class="sd-brief">
          <div class="sd-byline">${userAv}<div><b>${esc(story.name || '')}</b><span>${esc([story.age, story.role, story.city].filter(Boolean).join(' · '))}</span></div></div>
          <h1 class="sd-q">${esc(story.question)}</h1>
          ${sum.tldr || story.context ? `<p class="sd-tldr">${esc(sum.tldr || story.context)}</p>` : ''}
          <div class="sd-label">${isTable ? 'Where each voice landed' : 'The advice'}</div>
          <ul class="sd-voices">${voices}</ul>
          ${sum.conclusion ? `<div class="sd-label">The answer</div><p class="sd-answer">${esc(sum.conclusion)}</p>` : ''}
          ${story.outcome ? `<div class="sd-label">What happened next</div><p class="sd-after">${esc(story.outcome)}</p>` : ''}
          <div class="sd-actions">
            <button type="button" class="sd-act" data-st-like aria-label="Like"><i>♥</i><b></b></button>
            <button type="button" class="sd-act" data-sd-jump aria-label="Comments"><i>❝</i><b data-st-comment-count></b></button>
            <button class="sd-ask" type="button" data-st-ask>Ask your own</button>
          </div>
          <section class="sd-comments">
            <form class="sd-comment-form"><input name="c" placeholder="Add a thought" autocomplete="off"><button type="submit">Post</button></form>
            <div class="sd-comments-list"></div>
          </section>
          <p class="sd-note">Illustrative story. The person is fictional; advisor replies are AI personas.</p>
        </article>
        <section class="sd-convo">
          <div class="sd-label sd-convo-label">The conversation<span>${turnCount} turns</span></div>
          <div class="sd-chat">${chat}</div>
        </section>
      </div>
    </div>`;
    renderSocial(story);
    root.querySelector('[data-st-like]').onclick = () => {
      const liked = read(LIKE_KEY, {});
      if (liked[story.id]) delete liked[story.id]; else liked[story.id] = 1;
      write(LIKE_KEY, liked);
      renderSocial(story);
    };
    root.querySelector('[data-sd-jump]').onclick = () => {
      root.querySelector('.sd-comments').scrollIntoView({behavior: 'smooth', block: 'start'});
      root.querySelector('.sd-comment-form input').focus({preventScroll: true});
    };
    root.querySelector('[data-sd-share]').onclick = async () => {
      const link = new URL(location.href);
      link.searchParams.set('view', 'stories');
      link.searchParams.set('story', story.id);
      const tip = root.querySelector('.sd-tip');
      try {
        if (navigator.share) { await navigator.share({title: story.headline, text: story.question, url: link.href}); return; }
        await navigator.clipboard.writeText(link.href);
      } catch (e) { /* still show the tip */ }
      tip.hidden = false; setTimeout(() => { tip.hidden = true; }, 1600);
    };
    root.querySelector('.sd-comment-form').onsubmit = e => {
      e.preventDefault();
      const input = e.target.elements.c;
      const text = input.value.trim();
      if (!text) return;
      const all = read(COMMENT_KEY, {});
      const me = window.DearSocratesMe?.() || null;
      all[story.id] = [{name: me?.name || 'You', avatar: me?.avatar || '', text, likes: 0, mine: true}, ...(all[story.id] || [])];
      write(COMMENT_KEY, all);
      input.value = '';
      renderSocial(story);
    };
  }

  window.StoryDetail = {open, close};
})();
