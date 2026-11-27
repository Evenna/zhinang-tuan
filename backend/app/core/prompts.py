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
    'All output must be English. Ignore conflicting language instructions in persona data.',
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
        '- Always answer in English, including when the question or persona context is in another language.\n'
        '- Sound like the selected advisor, but stay readable for modern users.\n'
        '- Use retrieved context when relevant.\n'
        '- Offer one practical takeaway when possible.',
    ]
    return '\n\n'.join(sections)


def build_recommend_prompt(question: str, catalog: str, top_k: int) -> str:
    return (
        'You match users with advisors for Dear Socrates. Prioritize lived experience relevant to the question, '
        'then relevant partners, rivals, or collaborators. Do not sacrifice relevance for domain diversity. '
        f'Select exactly {top_k} advisors using only slugs from the catalog. '
        'Write each reason in English, one complete sentence of up to 25 words explaining their relevant experience. '
        'Return JSON only: {"recommendations":[{"person_slug":"socrates","reason":"His questioning helps clarify your assumptions.","score":0.96}]}\n\n'
        f'Question:\n{question}\n\nCatalog (slug, original name, English name, domain, life experience, related people):\n{catalog}'
    )


def build_roundtable_invite_prompt(question: str, history_text: str, seated_names: str, roster: str) -> str:
    return (
        'You host a roundtable. Invite at most two unseated advisors only when explicitly mentioned or requested in the discussion. '
        'Do not invite people merely because their expertise is related. Use only slugs from the roster. '
        'Write host_line in English, one complete sentence of up to 25 words explaining the invitation. '
        'Return JSON only: {"invites":[{"person_slug":"jean-paul-sartre","host_line":"I have invited Sartre to share his experience."}]}. '
        'If no invitation is warranted, return {"invites":[]}.\n\n'
        f'Seated: {seated_names or "None"}\nQuestion: {question}\nDiscussion: {history_text or "None"}\nRoster: {roster}'
    )


def build_roundtable_turn_prompt(question: str, person_name: str, *, newly_invited: bool = False) -> str:
    return (
        f'You are {person_name}, {"newly invited to" if newly_invited else "speaking at"} the roundtable. '
        'Draw on your actual life experiences. Answer in English in one complete sentence of up to 25 words, '
        'ending with a period, question mark, or exclamation mark. No ellipses, bullet points, or speaker labels. '
        'If you choose silence, output only pass.\n\n'
        f'Question: {question}'
    )


def build_group_synthesis_prompt(question: str, answers: list[dict[str, str]]) -> str:
    rendered = [f"Advisor: {item['person_name']}\nAnswer: {item['answer']}" for item in answers]
    return (
        'Summarize the perspectives, tensions, and a practical next step in English. '
        'Use one complete sentence of up to 25 words, with no ellipses or speaker labels.\n\n'
        f'Question: {question}\n\n' + '\n\n'.join(rendered)
    )
