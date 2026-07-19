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

def build_roundtable_planner_prompt(
    *,
    question: str,
    candidates: list[dict[str, Any]],
    session_summary: str,
    user_memories: list[str],
    preferred_people: list[str],
    max_participants: int,
) -> str:
    candidate_lines = []
    for person in candidates:
        candidate_lines.append(
            json.dumps(
                {
                    'slug': person['slug'],
                    'name': person['name'],
                    'domain': person['domain_category'],
                    'archetype': person['ai_archetype'],
                    'brief_intro': person['brief_intro'],
                    'preferred_topics': person.get('preferred_topics', []),
                    'core_traits': person.get('core_traits', []),
                },
                ensure_ascii=False,
            )
        )

    return (
        '你是“智囊团”产品里的圆桌主持人。你的任务不是让所有人都回答，'
        '而是像 AutoGen SelectorGroupChat 的 speaker selector 一样，判断此刻最应该让谁发言。\n\n'
        '设计原则:\n'
        '- 优先选择最少但最有效的人。\n'
        '- 如果一个人足够回答，就选择 single_expert。\n'
        '- 如果问题存在明显盲区，选择 primary_with_challenge。\n'
        '- 如果问题需要多视角但不宜失控，选择 mini_roundtable，最多使用 max_participants 人。\n'
        '- 如果用户问题信息不足，选择 clarify_first，只输出一个追问，不选择人物。\n'
        '- 每个 participant 都必须有明确 role 和 task，不能泛泛而谈。\n\n'
        f'用户问题:\n{question}\n\n'
        f'会话摘要:\n{session_summary or "无"}\n\n'
        f'用户长期记忆:\n{json.dumps(user_memories, ensure_ascii=False)}\n\n'
        f'用户偏好人物:\n{json.dumps(preferred_people, ensure_ascii=False)}\n\n'
        f'最多参与人数: {max_participants}\n\n'
        '候选人物:\n' + '\n'.join(candidate_lines) + '\n\n'
        '只返回严格 JSON，不要 markdown，不要解释。格式如下:\n'
        '{\n'
        '  "mode": "clarify_first | single_expert | primary_with_challenge | mini_roundtable",\n'
        '  "reasoning": "为什么这样安排",\n'
        '  "needs_clarification": false,\n'
        '  "clarifying_question": null,\n'
        '  "participants": [\n'
        '    {\n'
        '      "person_slug": "slug",\n'
        '      "role": "primary_responder | challenger | complement | clarifier | critic",\n'
        '      "task": "这一位只负责什么",\n'
        '      "selection_reason": "为什么选他/她"\n'
        '    }\n'
        '  ]\n'
        '}'
    )


def build_roundtable_advisor_user_prompt(
    *,
    question: str,
    session_summary: str,
    speaker_role: str,
    task: str,
    previous_turns: list[dict[str, str]],
) -> str:
    previous_text = '\n\n'.join(
        f"{turn['speaker_name']}({turn['speaker_role']}): {turn['content']}"
        for turn in previous_turns
    )
    return (
        f'用户问题:\n{question}\n\n'
        f'会话摘要:\n{session_summary or "无"}\n\n'
        f'你在这轮圆桌中的角色: {speaker_role}\n'
        f'主持人分配给你的任务: {task}\n\n'
        f'此前发言:\n{previous_text or "无"}\n\n'
        '请只完成主持人分配给你的任务。不要试图代表所有人总结。'
        '使用中文，具体、克制、可执行。'
    )


def build_roundtable_synthesis_prompt(
    *,
    question: str,
    plan: dict[str, Any],
    turns: list[dict[str, str]],
    session_summary: str,
) -> str:
    rendered_turns = '\n\n'.join(
        f"{turn['speaker_name']}({turn['speaker_role']}):\n{turn['content']}"
        for turn in turns
    )
    return (
        '你是智囊团圆桌主持人。请基于已选择的发言，而不是平均照顾所有观点，'
        '给用户一个清晰收束。\n\n'
        f'用户问题:\n{question}\n\n'
        f'会话摘要:\n{session_summary or "无"}\n\n'
        f'主持计划:\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n'
        f'圆桌发言:\n{rendered_turns or "无"}\n\n'
        '输出要求:\n'
        '- 先给最终判断。\n'
        '- 说明为什么当前最该采纳这个角度。\n'
        '- 如果有分歧，点出真正分歧。\n'
        '- 给一个下一步行动。\n'
        '- 中文，避免空泛总结。'
    )


def build_session_summary_prompt(
    *,
    question: str,
    previous_summary: str,
    final_answer: str,
    turns: list[dict[str, str]],
) -> str:
    return (
        '请把这一轮圆桌压缩成可供下一轮继续使用的会话记忆。'
        '只返回严格 JSON，不要 markdown。\n\n'
        f'上一轮摘要:\n{previous_summary or "无"}\n\n'
        f'用户问题:\n{question}\n\n'
        f'发言:\n{json.dumps(turns, ensure_ascii=False)}\n\n'
        f'最终回答:\n{final_answer}\n\n'
        'JSON 格式:\n'
        '{\n'
        '  "summary": "不超过 300 字的会话摘要",\n'
        '  "open_questions": ["仍需用户澄清的问题"],\n'
        '  "decisions": ["已经形成的判断或建议"],\n'
        '  "memory_highlights": ["下一轮应该记住的关键点"]\n'
        '}'
    )


def build_user_memory_extraction_prompt(
    *,
    user_id: str,
    question: str,
    final_answer: str,
) -> str:
    return (
        '请从用户问题和最终回答中提取值得长期保存的用户记忆。'
        '只保存明确、稳定、对后续建议有帮助的信息；不要猜测隐私。'
        '只返回严格 JSON，不要 markdown。\n\n'
        f'user_id: {user_id}\n'
        f'用户问题:\n{question}\n\n'
        f'最终回答:\n{final_answer}\n\n'
        'JSON 格式:\n'
        '{\n'
        '  "memories": [\n'
        '    {"memory_type": "preference | long_term_problem | confirmed_fact", "content": "...", "confidence": 0.7}\n'
        '  ]\n'
        '}'
    )
