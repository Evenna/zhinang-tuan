from __future__ import annotations

import json
from typing import Any

GLOBAL_RULES = [
    'You are an advisor inside the AI Think Tank product.',
    'Stay faithful to the persona while remaining useful, clear, and grounded.',
    'Do not fabricate historical facts, quotes, works, or life events.',
    'If the retrieved context is insufficient, answer cautiously and say what is uncertain.',
    'Do not claim private knowledge about the user.',
    'Keep the answer practical and relevant to the user question.',
]


def build_persona_system_prompt(
    *,
    person_name: str,
    person_slug: str,
    profile: dict[str, Any],
    retrieved_chunks: list[dict[str, Any]],
) -> str:
    identity = profile.get('identity', {})
    thinking_style = profile.get('thinking_style', {})
    speaking_style = profile.get('speaking_style', {})
    response_strategy = profile.get('response_strategy', {})
    prompt_contract = profile.get('prompt_contract', {})

    context_lines = []
    for idx, chunk in enumerate(retrieved_chunks, start=1):
        context_lines.append(
            f"[{idx}] type={chunk['chunk_type']} title={chunk['title']} "
            f"source={chunk['source_name']}\n{chunk['content']}"
        )

    sections = [
        'GLOBAL RULES:\n' + '\n'.join(f'- {rule}' for rule in GLOBAL_RULES),
        f"PERSONA: {person_name} ({person_slug})",
        'IDENTITY:\n' + json.dumps(identity, ensure_ascii=False, indent=2),
        'CORE_TRAITS:\n' + json.dumps(profile.get('core_traits', []), ensure_ascii=False, indent=2),
        'THINKING_STYLE:\n' + json.dumps(thinking_style, ensure_ascii=False, indent=2),
        'SPEAKING_STYLE:\n' + json.dumps(speaking_style, ensure_ascii=False, indent=2),
        'VALUES:\n' + json.dumps(profile.get('values', []), ensure_ascii=False, indent=2),
        'BLIND_SPOTS:\n' + json.dumps(profile.get('blind_spots', []), ensure_ascii=False, indent=2),
        'TABOOS:\n' + json.dumps(profile.get('taboos', []), ensure_ascii=False, indent=2),
        'PREFERRED_TOPICS:\n' + json.dumps(profile.get('preferred_topics', []), ensure_ascii=False, indent=2),
        'DISALLOWED_CLAIMS:\n' + json.dumps(profile.get('disallowed_claims', []), ensure_ascii=False, indent=2),
        'RESPONSE_STRATEGY:\n' + json.dumps(response_strategy, ensure_ascii=False, indent=2),
        'PROMPT_CONTRACT:\n' + json.dumps(prompt_contract, ensure_ascii=False, indent=2),
        'RETRIEVED CONTEXT:\n' + ('\n\n'.join(context_lines) if context_lines else 'No external context retrieved.'),
        'OUTPUT REQUIREMENTS:\n'
        '- Answer in Chinese unless user asks otherwise.\n'
        '- Sound like the selected advisor, but stay readable for modern users.\n'
        '- Use retrieved context when relevant.\n'
        '- Offer one practical takeaway when possible.',
    ]
    return '\n\n'.join(sections)


def build_group_synthesis_prompt(question: str, answers: list[dict[str, str]]) -> str:
    rendered = []
    for item in answers:
        rendered.append(f"Advisor: {item['person_name']}\nAnswer:\n{item['answer']}")
    return (
        'You are a moderator summarizing multiple advisor perspectives. '
        'Synthesize similarities, tensions, and a practical next step.\n\n'
        f'User question:\n{question}\n\n'
        'Advisor answers:\n' + '\n\n'.join(rendered)
    )
