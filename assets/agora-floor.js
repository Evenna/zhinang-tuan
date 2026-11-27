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

  /* The stage is the only place people appear: click a face to address them, × to send them off, + to pull someone in. */
  function stageHTML() {
    const d = AG.debate;
    const person = (s) => niche(s, {
      width: 66,
      cls: ['ag-seat-n', AG.target === s ? 'is-target' : '', d.speaking === s ? 'is-speaking' : '', d.thinking.has(s) ? 'is-thinking' : ''].join(' '),
      attrs: `data-ag-at="${esc(s)}" title="Talk to ${esc(nameOf(s))}"`,
      extra: d.seats.length > 1 ? `<span class="ag-niche-x" data-ag-kick="${esc(s)}" role="button" title="Send off the floor">×</span>` : '',
    });
    const row = [...camp('for'), ...camp('undecided'), ...camp('against')].map((s) => `<div class="ag-seat-col">${person(s)}${tag(d.stances[s])}</div>`).join('');
    const pull = d.seats.length < MAX_SEATS ? '<div class="ag-seat-col"><button type="button" class="ag-slot ag-slot--sm" data-ag-pull title="Invite someone">+</button><span class="ag-slot-cap">Invite</span></div>' : '';
    return `<div class="ag-stage-motion">${esc(d.motion)}</div>
      ${tallyBar(tallyOf(d.seats, d.stances))}
      <div class="ag-seat-row">${row}${pull}</div>`;
  }
  function composerHTML() {
    const d = AG.debate;
    return `${AG.target ? `<button type="button" class="ag-at-chip" data-ag-untarget title="Talk to everyone instead">@${esc(firstName(AG.target))} <i>×</i></button>` : ''}
      <input id="agAsk" maxlength="400" placeholder="${AG.target ? `Say something to ${esc(nameOf(AG.target))}…` : 'Say something to the floor — or tap a face to talk to one'}">
      <button type="submit" class="ag-send" ${AG.busy ? 'disabled' : ''} aria-label="Send">↑</button>
      <span class="ag-comp-sep"></span>
      <button type="button" class="ag-comp-act" data-ag-pull ${d.seats.length >= MAX_SEATS ? 'title="The floor holds five — send someone off first"' : ''}>+ Invite</button>
      <button type="button" class="ag-comp-act" data-ag-next ${AG.busy ? 'disabled' : ''}>Next round</button>
      <button type="button" class="ag-comp-act is-gold" data-ag-close ${AG.busy || !d.round ? 'disabled' : ''}>Verdict</button>`;
  }

  function renderDebate() {
    const d = AG.debate;
    const hall = AG.hallDetail[d.hall];
    const keep = document.getElementById('agAsk')?.value || '';
    view.innerHTML = `<div class="ag-debate ag-debate--v7">${colonnade()}
      <div class="ag-debate-main">
        <div class="ag-crumb"><button type="button" data-ag-back-index>Themes</button><span>/</span><button type="button" data-ag-back-hall>${esc(hall?.title || d.hall)} Hall</button></div>
        <div class="ag-stage" id="agStage">${stageHTML()}</div>
        <div class="ag-log" id="agLog">${logHTML()}</div>
        <form class="ag-composer" id="agComposer" autocomplete="off">${composerHTML()}</form>
      </div></div>`;
    const input = document.getElementById('agAsk');
    if (input && keep) input.value = keep;
    scrollLog();
  }
  // light updates — nothing re-mounts, so nothing pops
  function refreshStage() {
    const d = AG.debate;
    const st = document.getElementById('agStage');
    if (!st) return;
    const order = d.seats.map((s) => d.stances[s] || 'undecided').join();
    if (st.dataset.order !== order || st.dataset.n !== String(d.seats.length) || st.dataset.t !== String(AG.target)) {
      st.innerHTML = stageHTML();
      st.dataset.order = order; st.dataset.n = d.seats.length; st.dataset.t = AG.target;
      return;
    }
    st.querySelectorAll('.ag-seat-n').forEach((n) => {
      const s = n.dataset.slug;
      n.classList.toggle('is-speaking', d.speaking === s);
      n.classList.toggle('is-thinking', d.thinking.has(s));
    });
  }
  function refreshComposer() {
    const f = document.getElementById('agComposer');
    if (!f) return;
    const v = document.getElementById('agAsk')?.value || '';
    const focused = document.activeElement?.id === 'agAsk';
    f.innerHTML = composerHTML();
    const input = document.getElementById('agAsk');
    input.value = v;
    if (focused) input.focus();
  }
  function scrollLog(smooth = false) {
    const log = document.getElementById('agLog');
    if (log) log.scrollTo({ top: log.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
  }
  function appendHTML(html) {
    const log = document.getElementById('agLog');
    if (!log) return null;
    log.querySelector('.ag-log-empty')?.remove();
    log.insertAdjacentHTML('beforeend', html);
    scrollLog(true);
    return log.lastElementChild;
  }

  function turnHTML(turn) {
    if (turn.speaker === 'system') return `<div class="ag-round-sep">${esc(turn.text)}</div>`;
    if (turn.speaker === 'user') {
      return `<div class="ag-turn is-user"><div class="ag-turn-body"><div class="ag-turn-head"><span class="ag-turn-name">${esc(turn.name || 'You')}${turn.target ? ` → ${esc(nameOf(turn.target))}` : ''}</span></div><div class="ag-turn-text">${esc(turn.text)}</div></div></div>`;
    }
    return `<div class="ag-turn">${miniAv(turn.speaker)}<div class="ag-turn-body"><div class="ag-turn-head"><span class="ag-turn-name">${esc(turn.name || nameOf(turn.speaker))}</span>${tag(turn.stance)}${turn.move ? `<span class="ag-move">${esc(MOVE_LABEL[turn.move] || turn.move)}</span>` : ''}${turn.shift ? `<span class="ag-shift">${esc(turn.shift)}</span>` : ''}</div><div class="ag-turn-text">${esc(turn.text)}</div></div></div>`;
  }
  function pendingHTML(s) {
    const line = THINKING[(s.length + AG.debate.round) % THINKING.length];
    return `<div class="ag-turn is-pending" data-pending="${esc(s)}">${miniAv(s)}<div class="ag-turn-body"><div class="ag-turn-head"><span class="ag-turn-name">${esc(nameOf(s))}</span></div><div class="ag-turn-text">${esc(firstName(s))} ${esc(line)}<span class="ag-dots"></span></div></div></div>`;
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
    d.thinking.forEach((s) => out.push(pendingHTML(s)));
    if (d.error) out.push(`<div class="ag-error">${esc(d.error)} <button type="button" class="ag-link" data-ag-retry>Try again</button></div>`);
    if (!out.length) out.push('<p class="ag-floor-hint ag-log-empty" style="text-align:center;margin-top:30px">The floor is quiet.</p>');
    d._lastRound = lastRound;
    return out.join('');
  }

  function payloadTranscript() {
    return AG.debate.transcript.filter((t) => t.speaker !== 'system').map((t) => ({ speaker: t.speaker, text: t.text, stance: t.stance || null, round: t.round || 0 }));
  }

  // reveal a reply at speaking pace, word by word
  async function speak(el, text, d) {
    const box = el?.querySelector('.ag-turn-text');
    if (!box) return;
    const words = text.split(/(\s+)/);
    box.textContent = '';
    box.classList.add('is-typing');
    let shown = '';
    for (let i = 0; i < words.length; i += 1) {
      if (AG.debate !== d) return;
      shown += words[i];
      box.textContent = shown;
      if (words[i].trim()) await sleep(/[.!?;:]$/.test(words[i]) ? 210 : 62);
    }
    box.classList.remove('is-typing');
    scrollLog(true);
  }

  /* One voice at a time. Each speaker hears everyone before them; after the first, anyone may stay silent. */
  async function runRound({ question = null, target = null } = {}) {
    const d = AG.debate;
    if (AG.busy) return;
    AG.busy = true;
    d.error = '';
    refreshComposer();
    const opening = !d.round && !question;
    const round = question ? Math.max(d.round, 1) : d.round + 1;
    let order;
    if (target) order = [target, ...shuffle(d.seats.filter((s) => s !== target)).slice(0, 1)];
    else if (opening) order = [...d.seats];
    else order = shuffle([...d.seats]);
    const maxVoices = opening ? d.seats.length : question ? (target ? 2 : 3) : Math.min(d.seats.length, 4);
    if (d._lastRound !== round && !question) { appendHTML(`<div class="ag-round-sep">Round ${round}</div>`); d._lastRound = round; }
    let spoken = 0;
    for (let i = 0; i < order.length && spoken < maxVoices; i += 1) {
      const s = order[i];
      if (AG.debate !== d) return;
      if (!d.seats.includes(s)) continue;
      const mustSpeak = opening || (target ? s === target : spoken === 0);
      d.thinking = new Set([s]);
      refreshStage();
      const pending = appendHTML(pendingHTML(s));
      const started = Date.now();
      let res;
      try {
        res = await post('/turn', { motion: d.motion, seats: d.seats, speaker: s, transcript: payloadTranscript(), stances: d.stances, question, direct: s === target, allow_pass: !mustSpeak, round });
      } catch (e) {
        pending?.remove();
        if (mustSpeak && spoken === 0) {
          d.thinking = new Set(); d.error = e.message; d._retry = { question, target };
          AG.busy = false; refreshStage(); refreshComposer();
          appendHTML(`<div class="ag-error">${esc(e.message)} <button type="button" class="ag-link" data-ag-retry>Try again</button></div>`);
          return;
        }
        continue;
      }
      if (AG.debate !== d) return;
      await sleep(Math.max(0, 1400 - (Date.now() - started))); // a breath before anyone speaks
      d.thinking = new Set();
      const turn = res.turn;
      if (!turn) { // chose to stay silent
        pending?.remove();
        refreshStage();
        continue;
      }
      if (d._lastRound !== round && round > 0) { pending?.insertAdjacentHTML('beforebegin', `<div class="ag-round-sep">Round ${round}</div>`); d._lastRound = round; }
      const before = d.stances[s];
      const shift = before && turn.stance && before !== turn.stance ? `moved from ${STANCE_LABEL[before]}` : '';
      d.speaking = s;
      d.stances[s] = turn.stance || before || 'undecided';
      const full = { ...turn, shift };
      d.transcript.push(full);
      d.round = round;
      refreshStage();
      const tmp = document.createElement('div');
      tmp.innerHTML = turnHTML(full);
      const el = tmp.firstElementChild;
      if (pending) pending.replaceWith(el); else appendHTML(el.outerHTML);
      await speak(el, full.text, d);
      spoken += 1;
      await sleep(650);
      d.speaking = null;
      refreshStage();
    }
    if (AG.debate !== d) return;
    d.round = Math.max(d.round, round);
    if (!spoken) appendHTML('<div class="ag-round-sep">The floor listens in silence</div>');
    d.thinking = new Set();
    d.speaking = null;
    AG.busy = false;
    refreshStage();
    refreshComposer();
    const next = (d._queue || []).shift();
    if (next && d.seats.includes(next)) await runRound({ question: ENTRANCE, target: next });
  }
  const ENTRANCE = 'You have just joined this debate. Give your opening position on the motion and respond to what has been said so far.';
  function shuffle(a) { for (let i = a.length - 1; i > 0; i -= 1) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }

  function ask(text) {
    const d = AG.debate;
    if (AG.busy) return flash('Let them finish first.');
    const session = (() => { try { return JSON.parse(localStorage.getItem('zhinang-local-session') || 'null'); } catch (e) { return null; } })();
    const turn = { speaker: 'user', name: session?.name || 'You', text, target: AG.target, round: d.round };
    d.transcript.push(turn);
    appendHTML(turnHTML(turn));
    const target = AG.target;
    AG.target = null;
    refreshStage();
    const input = document.getElementById('agAsk'); if (input) input.value = '';
    runRound({ question: text, target });
  }

  function kick(slug) {
    const d = AG.debate;
    if (d.seats.length <= 1 || AG.busy) return AG.busy ? flash('Wait until this exchange ends.') : null;
    d.seats = d.seats.filter((s) => s !== slug);
    delete d.stances[slug];
    if (AG.target === slug) AG.target = null;
    const t = { speaker: 'system', text: `${nameOf(slug)} leaves the floor` };
    d.transcript.push(t);
    appendHTML(turnHTML(t));
    refreshStage(); refreshComposer();
  }

  async function pullIn(slug) {
    const d = AG.debate;
    if (!d || d.seats.includes(slug)) return;
    if (d.seats.length >= MAX_SEATS) return flash('The floor holds five. Send someone off first.');
    d.seats.push(slug);
    if (AG.busy) { // joins now, speaks as soon as the current speaker finishes
      d._queue = d._queue || [];
      d._queue.push(slug);
      const t = { speaker: 'system', text: `${nameOf(slug)} steps onto the floor` };
      d.transcript.push(t); appendHTML(turnHTML(t)); refreshStage();
      return;
    }
    const t = { speaker: 'system', text: `${nameOf(slug)} steps onto the floor` };
    d.transcript.push(t);
    appendHTML(turnHTML(t));
    refreshStage();
    if (!d.round) return;
    await runRound({ question: ENTRANCE, target: slug });
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
    if (el('[data-ag-pull]')) { if (AG.debate && AG.debate.seats.length >= MAX_SEATS) return flash('The floor holds five — hover a face and tap × to send someone off first.'); return openPicker('debate'); }
    if ((n = el('[data-ag-kick]'))) return kick(n.dataset.agKick);
    if ((n = el('[data-ag-at]'))) { AG.target = AG.target === n.dataset.agAt ? null : n.dataset.agAt; refreshStage(); refreshComposer(); return document.getElementById('agAsk')?.focus(); }
    if (el('[data-ag-untarget]')) { AG.target = null; refreshStage(); refreshComposer(); return document.getElementById('agAsk')?.focus(); }
    if (el('[data-ag-next]')) return runRound();
    if ((n = el('[data-ag-retry]'))) { n.closest('.ag-error')?.remove(); const r = AG.debate?._retry || {}; return runRound(r); }
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
