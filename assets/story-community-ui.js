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
