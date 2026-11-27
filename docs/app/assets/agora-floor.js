/* The Agora — debate floor, verdict stele, past-debate reader, wiring. Needs assets/agora.js first. */
(function () {
  const A = window.__agora;
  if (!A) return;
  const { AG, esc, sleep, niche, miniAv, face, tag, colonnade, tallyOf, tallyBar, nameOf, firstName, person, get, post, hallDetail, ensurePeople, openAgora, openHall, renderHall, togglePick, openPicker, closeModal, flash, setURL, syncAside, THINKING, MOVE_LABEL, STANCE_LABEL, MAX_SEATS, view } = A;

  /* ───────── Debate floor ───────── */
  function newDebate({ hall, motion, seats, transcript = [], stances = {}, round = 0, from = null }) {
    AG.debate = { hall, motion, seats: [...seats], transcript: [...transcript], stances: { ...stances }, round, from, speaking: null, thinking: new Set(), error: '', verdict: null, published: null };
    AG.target = null;
  }

  async function startDebate() {
    const motion = (document.getElementById('agMotion')?.value || AG.motion).trim();
    if (motion.length < 3) return flash('Write a motion first.');
    if (AG.picked.length < A.MIN_SEATS) return flash(`Pick at least ${A.MIN_SEATS} minds.`);
    AG.motion = motion;
    newDebate({ hall: AG.hall, motion, seats: AG.picked });
    renderDebate();
    await runRound();
  }

  function camp(stance) {
    const d = AG.debate;
    return d.seats.filter((s) => (d.stances[s] || 'undecided') === stance);
  }

  function renderDebate() {
    const d = AG.debate;
    const hall = AG.hallDetail[d.hall];
    const t = tallyOf(d.seats, d.stances);
    const campHTML = (stance, mid = false) => {
      const people = camp(stance);
      const inner = people.map((s) => niche(s, { width: 98, cls: [d.speaking === s ? 'is-speaking' : '', d.thinking.has(s) ? 'is-thinking' : ''].join(' '), attrs: 'tabindex="-1"' })).join('') || (mid ? '' : '<span class="ag-camp-empty"></span>');
      return `<div class="ag-camp${mid ? ' is-mid' : ''}"><div class="ag-camp-people">${inner}</div><div class="ag-camp-label is-${stance}">${STANCE_LABEL[stance]}</div></div>`;
    };
    view.innerHTML = `<div class="ag-debate">${colonnade()}
      <div class="ag-debate-main">
        <div class="ag-crumb"><button type="button" data-ag-back-index>Themes</button><span>/</span><button type="button" data-ag-back-hall>${esc(hall?.title || d.hall)} Hall</button><span>/</span><span>${d.round ? `Round ${d.round}` : 'Opening'}</span></div>
        <div class="ag-stage">
          <span class="ag-pill">The motion</span>
          <div class="ag-stage-motion">${esc(d.motion)}</div>
          ${tallyBar(t)}
          <div class="ag-camps">${campHTML('for')}${campHTML('undecided', true)}${campHTML('against')}</div>
          <div class="ag-stage-base"></div>
        </div>
        <div class="ag-log" id="agLog">${logHTML()}</div>
        <form class="ag-composer" id="agComposer" autocomplete="off">
          ${AG.target ? `<span class="ag-chip is-on" data-ag-untarget title="Ask everyone instead">@${esc(firstName(AG.target))} ×</span>` : ''}
          <input id="agAsk" maxlength="400" placeholder="${AG.target ? `Ask ${esc(nameOf(AG.target))} directly…` : 'Put a question to the floor, or tell them about your situation…'}" ${AG.busy ? 'disabled' : ''}>
          <button type="submit" class="ag-btn is-solid" ${AG.busy ? 'disabled' : ''}>Ask</button>
        </form>
      </div>
      <aside class="ag-floor-side">
        <div class="ag-side-head">On the floor · ${d.seats.length} / ${MAX_SEATS}</div>
        ${[...camp("for"), ...camp("undecided"), ...camp("against")].map((s) => `<div class="ag-seat">${miniAv(s)}<div><div class="ag-seat-name">${esc(nameOf(s))}</div>${tag(d.stances[s])}<button type="button" class="ag-seat-at" data-ag-at="${esc(s)}">Ask directly</button></div>
          <button type="button" class="ag-seat-x" data-ag-kick="${esc(s)}" title="Send off the floor" ${AG.busy || d.seats.length <= 1 ? 'disabled' : ''}>×</button></div>`).join('')}
        ${d.seats.length < MAX_SEATS ? `<button type="button" class="ag-pull" data-ag-pull ${AG.busy ? 'disabled' : ''}>+ Pull someone in</button>` : ''}
        <div style="display:flex;flex-direction:column;gap:10px;margin-top:22px">
          <button type="button" class="ag-btn" data-ag-next ${AG.busy ? 'disabled' : ''}>Next round →</button>
          <button type="button" class="ag-btn is-solid" data-ag-close ${AG.busy || !d.round ? 'disabled' : ''}>Close the debate · see the verdict</button>
        </div>
        <p class="ag-side-note">Stances move as minds change. Debaters are AI personas grounded in each person's writing and life.</p>
      </aside></div>`;
    const log = document.getElementById('agLog');
    if (log) log.scrollTop = log.scrollHeight;
  }

  function turnHTML(turn) {
    if (turn.speaker === 'system') return `<div class="ag-round-sep">${esc(turn.text)}</div>`;
    if (turn.speaker === 'user') {
      return `<div class="ag-turn is-user"><div class="ag-turn-body"><div class="ag-turn-head"><span class="ag-turn-name">${esc(turn.name || 'You')}${turn.target ? ` → ${esc(nameOf(turn.target))}` : ''}</span></div><div class="ag-turn-text">${esc(turn.text)}</div></div></div>`;
    }
    return `<div class="ag-turn">${miniAv(turn.speaker)}<div class="ag-turn-body"><div class="ag-turn-head"><span class="ag-turn-name">${esc(turn.name || nameOf(turn.speaker))}</span>${tag(turn.stance)}${turn.move ? `<span class="ag-move">${esc(MOVE_LABEL[turn.move] || turn.move)}</span>` : ''}${turn.shift ? `<span class="ag-shift">${esc(turn.shift)}</span>` : ''}</div><div class="ag-turn-text">${esc(turn.text)}</div></div></div>`;
  }

  function logHTML() {
    const d = AG.debate;
    let lastRound = -1;
    const out = [];
    d.transcript.forEach((turn) => {
      if (turn.speaker !== 'system' && turn.round !== lastRound && turn.round > 0 && turn.speaker !== 'user') {
        out.push(`<div class="ag-round-sep">Round ${turn.round}</div>`);
        lastRound = turn.round;
      }
      out.push(turnHTML(turn));
    });
    d.thinking.forEach((s) => {
      const line = THINKING[(s.length + d.round) % THINKING.length];
      out.push(`<div class="ag-turn is-pending">${miniAv(s)}<div class="ag-turn-body"><div class="ag-turn-head"><span class="ag-turn-name">${esc(nameOf(s))}</span></div><div class="ag-turn-text">${esc(firstName(s))} ${esc(line)}<span class="ag-dots"></span></div></div></div>`);
    });
    if (d.error) out.push(`<div class="ag-error">${esc(d.error)} <button type="button" class="ag-link" data-ag-retry>Try again</button></div>`);
    if (!out.length) out.push('<p class="ag-floor-hint" style="text-align:center;margin-top:30px">The floor is quiet. The first round is about to open.</p>');
    return out.join('');
  }

  function payloadTranscript() {
    return AG.debate.transcript.filter((t) => t.speaker !== 'system').map((t) => ({ speaker: t.speaker, text: t.text, stance: t.stance || null, round: t.round || 0 }));
  }

  // One round: everyone (or one target) answers. Replies are revealed one by one so camps visibly shift.
  async function runRound({ question = null, target = null } = {}) {
    const d = AG.debate;
    if (AG.busy) return;
    AG.busy = true;
    d.error = '';
    const round = question && target ? Math.max(d.round, 1) : d.round + 1;
    const speakers = target ? [target] : [...d.seats];
    d.thinking = new Set(speakers);
    renderDebate();
    let data;
    try {
      data = await post('/round', { motion: d.motion, seats: d.seats, transcript: payloadTranscript(), stances: d.stances, question, target, round });
    } catch (e) {
      d.thinking = new Set();
      d.error = e.message;
      d._retry = { question, target };
      AG.busy = false;
      renderDebate();
      return;
    }
    if (AG.debate !== d) return;
    d.round = round;
    for (const turn of data.turns || []) {
      const before = d.stances[turn.speaker];
      const shift = before && turn.stance && before !== turn.stance ? `moved from ${STANCE_LABEL[before]}` : '';
      d.thinking.delete(turn.speaker);
      d.speaking = turn.speaker;
      d.stances[turn.speaker] = turn.stance || before || 'undecided';
      d.transcript.push({ ...turn, shift });
      renderDebate();
      await sleep(900);
    }
    d.thinking = new Set();
    d.speaking = null;
    AG.busy = false;
    renderDebate();
  }

  function ask(text) {
    const d = AG.debate;
    const session = (() => { try { return JSON.parse(localStorage.getItem('zhinang-local-session') || 'null'); } catch (e) { return null; } })();
    d.transcript.push({ speaker: 'user', name: session?.name || 'You', text, target: AG.target, round: d.round });
    const target = AG.target;
    AG.target = null;
    runRound({ question: text, target });
  }

  function kick(slug) {
    const d = AG.debate;
    if (d.seats.length <= 1) return;
    d.seats = d.seats.filter((s) => s !== slug);
    delete d.stances[slug];
    if (AG.target === slug) AG.target = null;
    d.transcript.push({ speaker: 'system', text: `${nameOf(slug)} leaves the floor` });
    renderDebate();
  }

  async function pullIn(slug) {
    const d = AG.debate;
    if (!d || d.seats.includes(slug)) return;
    if (d.seats.length >= MAX_SEATS) return flash('The floor holds five. Send someone off first.');
    d.seats.push(slug);
    d.transcript.push({ speaker: 'system', text: `${nameOf(slug)} steps onto the floor` });
    if (!d.round) return renderDebate();
    await runRound({ question: 'You have just joined this debate. Give your opening position on the motion and respond to what has been said so far.', target: slug });
  }
  A.pullIn = pullIn;

  /* ───────── Verdict ───────── */
  async function closeDebate() {
    const d = AG.debate;
    if (AG.busy || !d.round) return;
    AG.busy = true;
    view.innerHTML = `<div class="ag-verdict">${colonnade()}<div class="ag-stele"><div class="ag-stele-kicker">The scribe is writing the verdict<span class="ag-dots"></span></div><h2>${esc(d.motion)}</h2></div></div>`;
    try {
      d.verdict = await post('/verdict', { motion: d.motion, seats: d.seats, transcript: payloadTranscript(), stances: d.stances });
    } catch (e) {
      AG.busy = false;
      d.error = e.message;
      renderDebate();
      return;
    }
    AG.busy = false;
    renderVerdict();
  }

  function renderVerdict() {
    const d = AG.debate;
    const v = d.verdict;
    const t = tallyOf(d.seats, d.stances);
    const pos = Object.fromEntries((v.positions || []).map((p) => [p.speaker, p.stance]));
    const col = (key, title, items) => `<div class="ag-stele-col"><h4 class="is-${key}">${title}</h4>${(items || []).map((x) => `<p>${esc(x)}</p>`).join('') || '<p>—</p>'}</div>`;
    view.innerHTML = `<div class="ag-verdict">${colonnade()}
      <div class="ag-stele">
        <div class="ag-stele-kicker"><svg width="38" height="22" viewBox="0 0 38 22" fill="none" stroke="#8a6a35"><path d="M1 21h36M4 18h30M19 1 2 9h34z"/><path d="M8 10v8M15 10v8M23 10v8M30 10v8"/></svg>Verdict of the Agora · ${d.round} round${d.round === 1 ? '' : 's'}</div>
        <h2>${esc(v.headline)}</h2>
        <div class="ag-stele-motion">On the motion: “${esc(d.motion)}”</div>
        <div class="ag-stele-rule"></div>
        <p class="ag-stele-summary">${esc(v.summary)}</p>
        <div class="ag-stele-cols">${col('for', 'For the motion', v.for)}${col('against', 'Against the motion', v.against)}${col('undecided', 'Still open', v.open)}</div>
        ${v.tension ? `<p class="ag-stele-tension">${esc(v.tension)}</p>` : ''}
        <div class="ag-stele-cast">${d.seats.map((s) => `<div style="display:flex;flex-direction:column;align-items:center">${niche(s, { width: 84, attrs: 'tabindex="-1"' })}<div style="margin-top:6px">${tag(d.stances[s])}</div>${pos[s] ? `<div class="ag-stele-pos">${esc(pos[s])}</div>` : ''}</div>`).join('')}</div>
      </div>
      <div class="ag-final-tally">${['for', 'undecided', 'against'].map((k) => `<span class="is-${k}">${STANCE_LABEL[k]}<b>${t[k]}</b></span>`).join('')}</div>
      <div class="ag-actions">
        ${d.published ? `<button type="button" class="ag-btn" data-ag-read="${esc(d.published)}">Published · read it on the record</button>` : '<button type="button" class="ag-btn is-solid" data-ag-publish>Publish to the hall</button>'}
        <button type="button" class="ag-btn" data-ag-continue>Continue debating</button>
        <button type="button" class="ag-btn" data-ag-share>Share</button>
        <button type="button" class="ag-btn" data-ag-back-hall>Back to the hall</button>
      </div>
      <div class="ag-actions-note">${d.published ? 'Now on the hall’s record for other visitors to read.' : 'Publishing adds this debate to the hall’s record, where others can read and continue it.'}</div>
    </div>`;
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function publish() {
    const d = AG.debate;
    const session = (() => { try { return JSON.parse(localStorage.getItem('zhinang-local-session') || 'null'); } catch (e) { return null; } })();
    try {
      const res = await post('/publish', { hall: d.hall, motion: d.motion, seats: d.seats, transcript: payloadTranscript(), stances: d.stances, verdict: d.verdict, author: (session?.name || 'Anonymous visitor').slice(0, 40) }, 20000);
      d.published = res.id;
      await hallDetail(d.hall, true).catch(() => {});
      AG.halls = null;
      renderVerdict();
      flash('Published to the hall.');
    } catch (e) { flash(e.message); }
  }

  async function share(id) {
    const url = new URL(location.href);
    ['view', 'hall', 'debate', 'v'].forEach((k) => url.searchParams.delete(k));
    url.searchParams.set('view', 'themes');
    if (id) url.searchParams.set('debate', id); else url.searchParams.set('hall', AG.debate?.hall || AG.hall);
    try { await navigator.clipboard.writeText(url.toString()); flash('Link copied.'); } catch (e) { prompt('Copy this link', url.toString()); }
  }

  /* ───────── Reader for debates on record ───────── */
  let reader = null;
  async function openReader(id) {
    if (!reader) {
      reader = document.createElement('div');
      reader.className = 'story-transcript ag-reader';
      reader.hidden = true;
      document.body.append(reader);
      reader.addEventListener('click', (event) => {
        if (event.target === reader || event.target.closest('.st-close')) { reader.hidden = true; return; }
        const like = event.target.closest('[data-ag-like]');
        if (like) { like.classList.toggle('is-on'); const b = like.querySelector('b'); b.textContent = Number(b.textContent) + (like.classList.contains('is-on') ? 1 : -1); }
      });
      document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && reader && !reader.hidden) reader.hidden = true; });
    }
    reader.hidden = false;
    reader.innerHTML = '<div class="st-panel"><button class="st-close" type="button" aria-label="Close">×</button><div class="st-meta">Opening the record<span class="ag-dots"></span></div></div>';
    let d;
    try { d = await get('/debates/' + encodeURIComponent(id).replace(/%2F/g, '/')); } catch (e) {
      reader.querySelector('.st-meta').textContent = e.message;
      return;
    }
    reader._debate = d;
    const sum = d.summary || {};
    const v = d.verdict || {};
    const t = d.tally || tallyOf(d.participants || [], d.stances || {});
    const pos = (sum.positions || []).map((p) => `<div class="st-position">${miniAv(p.speaker)}<div><b>${esc(nameOf(p.speaker))}</b><p>${esc(p.stance || p.text || '')}</p></div></div>`).join('');
    const avatar = d.avatar ? `<img src="${esc(d.avatar)}" alt="">` : `<span style="width:52px;height:52px;border-radius:50%;background:#2a2620;display:grid;place-items:center;color:var(--ag-gold)">${esc((d.name || '?')[0])}</span>`;
    let lastRound = -1;
    const chat = (d.transcript || []).map((turn) => {
      let sep = '';
      if (turn.speaker !== 'user' && turn.speaker !== 'system' && turn.round > 0 && turn.round !== lastRound) { sep = `<div class="ag-round-sep">Round ${turn.round}</div>`; lastRound = turn.round; }
      return sep + turnHTML(turn.speaker === 'user' ? { ...turn, name: d.name } : turn);
    }).join('');
    const comments = (d.comments || []).map((c) => `<div class="st-comment${c.is_author ? ' is-author' : ''}"><div class="st-comment-head"><b>${esc(c.name)}</b>${c.is_author ? '<span class="st-badge">Author</span>' : ''}<span class="st-comment-likes">♥ ${esc(c.likes ?? 0)}</span></div><p>${esc(c.text)}</p></div>`).join('');
    reader.innerHTML = `<div class="st-panel">
      <button class="st-close" type="button" aria-label="Close">×</button>
      <div class="st-head">${avatar}<div><div class="st-name">${esc(d.name)}</div>
        <div class="st-meta">${[d.age, d.role, d.city].filter(Boolean).map(esc).join(' · ')}</div>
        <div class="st-meta">${esc(d.date || '')} · ${(d.transcript || []).length} turns</div></div></div>
      <div class="st-kicker">Agora debate · ${esc((AG.hallDetail[d.hall]?.title) || d.hall)} Hall</div>
      <div class="st-headline">${esc(d.headline || d.motion)}</div>
      <div class="st-question">“${esc(d.motion)}”</div>
      <div class="st-cast">${(d.participants || []).map((s) => `<span class="st-cast-chip">${face(s).replace('<span', '<span class="ag-faces-i"')}${esc(nameOf(s))} · ${esc(STANCE_LABEL[d.stances?.[s]] || 'Undecided')}</span>`).join('')}</div>
      <div class="ag-reader-tally">${['for', 'undecided', 'against'].map((k) => `<span class="is-${k}">${STANCE_LABEL[k]}<b>${t[k] || 0}</b></span>`).join('')}</div>
      <section class="st-summary">
        <div class="st-summary-label">Verdict</div>
        <p class="st-tldr">${esc(sum.tldr || d.context || '')}</p>
        <div class="ag-reader-cols"><div><h5 class="is-for">For</h5>${(v.for || []).map((x) => `<p>${esc(x)}</p>`).join('')}</div><div><h5 class="is-against">Against</h5>${(v.against || []).map((x) => `<p>${esc(x)}</p>`).join('')}</div><div><h5 class="is-undecided">Still open</h5>${(v.open || []).map((x) => `<p>${esc(x)}</p>`).join('')}</div></div>
        ${pos ? `<div class="st-summary-label">Where each voice landed</div><div class="st-positions">${pos}</div>` : ''}
        ${sum.tension ? `<div class="st-summary-label">The crux</div><p class="st-tension">${esc(sum.tension)}</p>` : ''}
        ${d.outcome ? `<div class="st-summary-label">What happened next</div><p class="st-outcome">${esc(d.outcome)}</p>` : ''}
      </section>
      <div class="st-actions">
        <button type="button" class="st-act" data-ag-like>♥ <b>${esc(d.likes || 0)}</b></button>
        <button type="button" class="st-act" data-ag-share-id="${esc(d.id)}">↗ Share</button>
      </div>
      <div class="st-summary-label" style="margin-top:22px">The debate · ${(d.transcript || []).length} turns</div>
      <div>${chat}</div>
      <div class="ag-reader-continue"><button type="button" class="ag-btn is-solid" data-ag-continue-record>Continue this debate yourself →</button><button type="button" class="ag-btn" data-ag-same-motion>Same motion, new minds</button></div>
      ${comments ? `<section class="st-comments"><div class="st-summary-label">Comments · ${(d.comments || []).length}</div>${comments}</section>` : ''}
      <div class="st-note">${d.published && !d.demo && String(d.id).includes('-') && !/-\d\d$/.test(d.id) ? 'Published by a visitor; replies are AI personas.' : 'Illustrative debate — the visitor is fictional; every reply comes from the AI personas.'}</div>
    </div>`;
    reader.querySelector('.st-panel').scrollTop = 0;
  }

  async function continueRecord(fresh) {
    const d = reader?._debate;
    if (!d) return;
    reader.hidden = true;
    await ensurePeople();
    await hallDetail(d.hall).catch(() => {});
    AG.hall = d.hall;
    AG.motion = d.motion;
    if (fresh) {
      AG.picked = (AG.hallDetail[d.hall]?.residents || []).map((r) => r.slug).filter((s) => !(d.participants || []).includes(s)).slice(0, 3);
      openAgora();
      setURL({ view: 'themes', hall: d.hall });
      return renderHall();
    }
    const transcript = (d.transcript || []).map((t) => ({ ...t, name: t.speaker === 'user' ? d.name : t.name }));
    const round = Math.max(0, ...transcript.map((t) => t.round || 0));
    newDebate({ hall: d.hall, motion: d.motion, seats: d.participants || [], transcript, stances: d.stances || {}, round, from: d.id });
    AG.debate.transcript.push({ speaker: 'system', text: 'You take the floor' });
    openAgora();
    setURL({ view: 'themes', hall: d.hall });
    renderDebate();
    document.getElementById('agAsk')?.focus();
  }

  /* ───────── wiring ───────── */
  document.addEventListener('click', (event) => {
    const el = (sel) => event.target.closest(sel);
    let n;
    if ((n = el('[data-ag-enter]'))) { event.preventDefault(); return openHall(n.dataset.agEnter); }
    if (!event.target.closest('.agora-view, .ag-modal, .ag-reader')) return;
    if (el('[data-ag-back-index]')) return A.closeAgora();
    if (el('[data-ag-back-hall]')) { const h = AG.debate?.hall || AG.hall; AG.debate = null; AG.busy = false; return openHall(h, { keepPicks: true }); }
    if ((n = el('[data-ag-motion]'))) { AG.motion = n.dataset.agMotion; return renderHall(); }
    if ((n = el('[data-ag-unpick]'))) { event.stopPropagation(); AG.picked = AG.picked.filter((s) => s !== n.dataset.agUnpick); return renderHall(); }
    if ((n = el('.ag-gallery .ag-niche'))) return togglePick(n.dataset.slug);
    if ((n = el('[data-ag-scroll]'))) { const g = document.getElementById('agGallery'); return g?.scrollBy({ left: Number(n.dataset.agScroll) * g.clientWidth * 0.8, behavior: 'smooth' }); }
    if (el('[data-ag-invite]')) return openPicker('hall');
    if (el('[data-ag-open]')) return startDebate();
    if ((n = el('[data-ag-read]'))) return openReader(n.dataset.agRead);
    if (el('[data-ag-pull]')) return openPicker('debate');
    if ((n = el('[data-ag-kick]'))) return kick(n.dataset.agKick);
    if ((n = el('[data-ag-at]'))) { AG.target = n.dataset.agAt; renderDebate(); return document.getElementById('agAsk')?.focus(); }
    if (el('[data-ag-untarget]')) { AG.target = null; return renderDebate(); }
    if (el('[data-ag-next]')) return runRound();
    if (el('[data-ag-retry]')) { const r = AG.debate?._retry || {}; return runRound(r); }
    if (el('[data-ag-close]')) return closeDebate();
    if (el('[data-ag-publish]')) return publish();
    if (el('[data-ag-continue]')) { AG.debate.published = AG.debate.published || null; return renderDebate(); }
    if (el('[data-ag-share]')) return share(AG.debate?.published);
    if ((n = el('[data-ag-share-id]'))) return share(n.dataset.agShareId);
    if (el('[data-ag-continue-record]')) return continueRecord(false);
    if (el('[data-ag-same-motion]')) return continueRecord(true);
  });
  document.addEventListener('submit', (event) => {
    if (event.target.id !== 'agComposer') return;
    event.preventDefault();
    const input = document.getElementById('agAsk');
    const text = input?.value.trim();
    if (!text || AG.busy) return;
    ask(text);
  });
  document.addEventListener('input', (event) => {
    if (event.target.id === 'agMotion') {
      AG.motion = event.target.value;
      document.querySelectorAll('[data-ag-motion]').forEach((c) => c.classList.toggle('is-on', c.dataset.agMotion === AG.motion));
    }
  });
  window.addEventListener('beforeunload', (event) => { if (AG.debate && AG.debate.round && !AG.debate.published && document.getElementById('themesPage')?.classList.contains('agora-open')) { event.preventDefault(); } });

  // Index: clicking a theme row opens its hall; hovering refreshes the aside.
  const grid = document.getElementById('themeGrid');
  grid?.addEventListener('click', (event) => {
    const row = event.target.closest('[data-theme]');
    if (!row) return;
    event.stopImmediatePropagation();
    openHall(row.dataset.theme);
  }, true);
  grid?.addEventListener('pointerover', () => requestAnimationFrame(syncAside));

  // Called by showThemesPage(): always land on the index.
  window.agoraOnThemes = function () {
    document.getElementById('themesPage')?.classList.remove('agora-open');
    closeModal();
    syncAside();
  };

  // Deep links: ?view=themes[&hall=id][&debate=id]
  window.agoraRoute = async function (params) {
    const hall = params.get('hall');
    const debate = params.get('debate');
    if (debate) { await ensurePeople(); openReader(debate); if (!hall) return; }
    if (hall) openHall(hall);
  };
  // Deferred scripts run after the inline router — catch up if the themes page is already showing.
  if (document.getElementById('themesPage')?.classList.contains('show')) syncAside();
})();
