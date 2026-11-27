"""Occasional long-form turns.

Most of the time advisors answer briefly. Once a conversation has real depth,
people whose voice is naturally expansive (philosophers, novelists, essayists,
orators) get a small chance to take the floor for a longer, considered speech.
The model is told it *may* go long, and only if the point truly deserves it,
so a long turn stays rare, in character and on topic.
"""
from __future__ import annotations

import os
import random
import re

# Advisors whose writing / speaking is famously expansive.
EXPANSIVE = {
    'socrates', 'plato', 'aristotle', 'confucius', 'laozi', 'zhuangzi', 'marcus-aurelius',
    'immanuel-kant', 'nietzsche', 'blaise-pascal', 'jean-paul-sartre', 'albert-camus', 'hannah-arendt',
    'fyodor-dostoevsky', 'leo-tolstoy', 'virginia-woolf', 'jorge-luis-borges', 'lu-xun',
    'carl-jung', 'sigmund-freud', 'carl-sagan', 'richard-feynman', 'albert-einstein', 'charles-darwin',
    'abraham-lincoln', 'martin-luther-king-jr', 'winston-churchill', 'leonardo-da-vinci',
}

LONG_WORDS = 150


def _is_long(text: str) -> bool:
    return len((text or '').split()) > 70


def pick_long(slug: str, lines: list[str]) -> bool:
    """Decide whether this speaker is *offered* a long turn.

    lines: the spoken lines so far (user + advisors), oldest first.
    """
    if os.environ.get('ZT_FORCE_LONG'):
        return True
    spoken = [t for t in lines if t]
    if len(spoken) < 4:                      # not deep enough yet
        return False
    if any(_is_long(t) for t in spoken[-3:]):  # never two long speeches close together
        return False
    depth_bonus = min(0.08, 0.01 * (len(spoken) - 4))
    chance = (0.16 if slug in EXPANSIVE else 0.03) + depth_bonus
    return random.random() < chance


def long_clause(max_words: int = LONG_WORDS) -> str:
    return (
        'THIS TURN ONLY: the conversation has reached a point that may deserve real depth. '
        'If — and only if — there is something here genuinely worth unfolding, and it fits how you actually wrote and spoke, '
        f'you may take the floor for a longer, considered speech: 4 to 7 sentences, up to {max_words} words, '
        'developing one idea carefully, drawing on your own works, life or famous arguments. No lists, no headings, no speaker label, no ellipses. '
        'This overrides any shorter word limit stated above. If the point does not deserve it, ignore this and stay brief.'
    )


def finish_sentences(text: str, max_chars: int = 1200) -> str:
    """Keep whole sentences only, up to max_chars."""
    text = re.sub(r'\s+', ' ', str(text or '')).strip().strip('"“”\'')
    text = re.sub(r'\.{3,}|…+', '', text).strip()
    if not text:
        return ''
    text = text[:max_chars]
    sentences = re.findall(r'[^.!?]*[.!?]+["”’)]?', text)
    if sentences:
        return ''.join(sentences).strip()
    return text + '.'
