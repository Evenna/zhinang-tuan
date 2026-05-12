from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from typing import Optional

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import KnowledgeChunk, Person, PersonaProfile, Quote, WorkEvent
from app.utils.text import split_text_semantic, unique_clean

settings = get_settings()
FICTIONAL_MARKERS = {
    'fictional human',
    'comics character',
    'film character',
    'television character',
    'animated character',
    'fictional character',
    'legendary character',
    'deity',
    'mythological greek character',
    'mythological character',
    'superhero',
}

CATEGORY_DEFAULTS = {
    '哲学': {
        'traits': ['思辨', '追问', '抽象', '克制'],
        'decision_lens': ['价值判断', '概念澄清', '自我反思'],
        'tone': ['冷静', '深思', '克制'],
        'values': ['求真', '自省', '理性'],
        'blind_spots': ['可能过度抽象', '可能忽略现实执行成本'],
        'topics': ['人生选择', '意义', '价值观', '道德困境'],
        'devices': ['反问', '概念拆解', '类比'],
        'default_mode': 'question_first',
        'advice_style': 'reflective',
    },
    '科学': {
        'traits': ['求证', '系统', '严谨', '好奇'],
        'decision_lens': ['证据', '实验', '因果关系'],
        'tone': ['理性', '清晰', '有条理'],
        'values': ['真实', '验证', '探索'],
        'blind_spots': ['可能低估情绪因素', '可能偏向问题拆解而非安抚'],
        'topics': ['学习方法', '复杂问题', '系统优化', '科技选择'],
        'devices': ['框架', '步骤拆解', '假设检验'],
        'default_mode': 'framework_first',
        'advice_style': 'strategic',
    },
    '商业': {
        'traits': ['现实', '取舍', '长期主义', '结果导向'],
        'decision_lens': ['资源配置', '风险收益', '杠杆'],
        'tone': ['直接', '务实', '清醒'],
        'values': ['效率', '长期回报', '执行力'],
        'blind_spots': ['可能过度功利', '可能压缩情绪空间'],
        'topics': ['职业决策', '创业', '管理', '增长'],
        'devices': ['原则清单', '优先级排序', '反向思考'],
        'default_mode': 'judgment_first',
        'advice_style': 'direct',
    },
    '文学': {
        'traits': ['敏感', '洞察人性', '叙事感', '细腻'],
        'decision_lens': ['情感经验', '人物动机', '内在冲突'],
        'tone': ['温和', '有画面感', '含蓄'],
        'values': ['真实情感', '个体经验', '表达'],
        'blind_spots': ['可能放大感受', '可能不够直接给结论'],
        'topics': ['关系', '孤独', '表达', '自我理解'],
        'devices': ['隐喻', '故事', '场景化表达'],
        'default_mode': 'story_first',
        'advice_style': 'empathetic',
    },
    '艺术': {
        'traits': ['感性', '审美驱动', '创造', '反常规'],
        'decision_lens': ['表达张力', '个体风格', '创造冲动'],
        'tone': ['有画面感', '自由', '鲜明'],
        'values': ['表达', '创造', '个性'],
        'blind_spots': ['可能不够稳定', '可能忽略现实约束'],
        'topics': ['创作瓶颈', '审美判断', '个性成长', '风格选择'],
        'devices': ['意象', '比喻', '感受描述'],
        'default_mode': 'story_first',
        'advice_style': 'reflective',
    },
    '历史': {
        'traits': ['宏观', '战略', '权衡', '洞察局势'],
        'decision_lens': ['局势变化', '权力关系', '长期后果'],
        'tone': ['沉着', '判断性强', '有历史感'],
        'values': ['秩序', '胜算', '责任'],
        'blind_spots': ['可能过于强调大局', '可能牺牲个体感受'],
        'topics': ['领导力', '决策', '冲突', '责任'],
        'devices': ['案例', '警句', '形势判断'],
        'default_mode': 'judgment_first',
        'advice_style': 'strategic',
    },
}


class ImportService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def import_dataset(self, force_rebuild: bool = False) -> dict[str, object]:
        dataset = self._load_dataset(settings.import_dataset_path)
        dataset_version = dataset['meta'].get('generated_at', 'v1')
        people_data = dataset['people']

        if force_rebuild:
            self._clear_tables()

        people_count = 0
        profiles_count = 0
        chunks_count = 0

        for item in people_data:
            person = self._upsert_person(item, dataset_version)
            people_count += 1

            profile = self._upsert_persona_profile(person, item, dataset_version)
            profiles_count += 1 if profile else 0

            chunks_count += self._replace_knowledge_chunks(person, item)

        self.db.commit()
        return {
            'dataset_version': dataset_version,
            'people_count': people_count,
            'profiles_count': profiles_count,
            'chunks_count': chunks_count,
            'force_rebuild': force_rebuild,
        }

    def _load_dataset(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding='utf-8'))

    def _clear_tables(self) -> None:
        for model in (Quote, WorkEvent, KnowledgeChunk, PersonaProfile, Person):
            self.db.execute(delete(model))
        self.db.commit()

    def _upsert_person(self, source: dict, dataset_version: str) -> Person:
        person = self.db.scalar(select(Person).where(Person.slug == source['id']))
        if not person:
            person = Person(id=str(uuid4()), slug=source['id'], english_name=source['english_name'])
            self.db.add(person)

        person.slug = source['id']
        person.english_name = source['english_name']
        person.chinese_name = source['chinese_name']
        person.domain_category = source['domain_category']
        person.ai_archetype = source['ai_archetype']
        person.brief_intro = source['source_brief_intro']
        person.portrait_asset = source.get('portrait_asset')
        person.is_fictional = self._is_fictional(source.get('structured_facts', {}).get('instance_of', []))
        person.era_context = source.get('biography', {}).get('description')
        person.source_dataset_version = dataset_version
        person.status = 'active'
        self.db.flush()
        return person

    def _upsert_persona_profile(self, person: Person, source: dict, dataset_version: str) -> PersonaProfile:
        profile = self.db.scalar(
            select(PersonaProfile)
            .where(PersonaProfile.person_id == person.id)
            .order_by(desc(PersonaProfile.version))
        )
        if not profile:
            profile = PersonaProfile(id=str(uuid4()), person_id=person.id, slug=person.slug, version=1)
            self.db.add(profile)

        payload = self._build_persona_payload(person, source, dataset_version)
        profile.slug = payload['slug']
        profile.version = payload['version']
        profile.profile_status = payload['profile_status']
        profile.identity = payload['identity']
        profile.core_traits = payload['core_traits']
        profile.thinking_style = payload['thinking_style']
        profile.speaking_style = payload['speaking_style']
        profile.values = payload['values']
        profile.blind_spots = payload['blind_spots']
        profile.taboos = payload['taboos']
        profile.preferred_topics = payload['preferred_topics']
        profile.disallowed_claims = payload['disallowed_claims']
        profile.response_strategy = payload['response_strategy']
        profile.prompt_contract = payload['prompt_contract']
        profile.generation_notes = payload['generation_notes']
        profile.metadata_json = payload['metadata']
        self.db.flush()
        return profile

    def _replace_knowledge_chunks(self, person: Person, source: dict) -> int:
        self.db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.person_id == person.id))
        chunks = self._build_chunks(person, source)
        for chunk in chunks:
            self.db.add(chunk)
        self.db.flush()
        return len(chunks)

    def _build_persona_payload(self, person: Person, source: dict, dataset_version: str) -> dict:
        category_name = source.get('domain_category', '').split('/', 1)[0].strip()
        defaults = CATEGORY_DEFAULTS.get(category_name, CATEGORY_DEFAULTS['历史'])
        occupations = unique_clean(source.get('structured_facts', {}).get('occupations', []))
        story_seeds = unique_clean(source.get('biography', {}).get('story_seeds', []))
        personality_seed = unique_clean(source.get('personality_seed', []))

        core_traits = unique_clean(personality_seed + defaults['traits'] + occupations[:2])[:6]
        while len(core_traits) < 3:
            core_traits.append(defaults['traits'][len(core_traits) % len(defaults['traits'])])
        reasoning_patterns = unique_clean(occupations[:3] + defaults['decision_lens'])[:6]
        preferred_topics = unique_clean(defaults['topics'] + [source.get('ai_archetype', ''), category_name])[:8]
        rhetorical_devices = unique_clean(defaults['devices'])[:6]

        now_iso = datetime.now(timezone.utc).isoformat()
        short_summary = source.get('biography', {}).get('summary') or source.get('source_brief_intro', '')
        thinking_summary = (
            f"{person.chinese_name}看问题时更偏向{defaults['decision_lens'][0]}与{defaults['decision_lens'][1]}，"
            f"会从其身份背景和经历中提炼原则，而不是只给情绪性安慰。"
        )
        questioning_habit = (
            '倾向先重述问题本质，再追问真正的矛盾点。'
            if defaults['default_mode'] == 'question_first'
            else '倾向先判断局势与关键变量，再给出下一步建议。'
        )

        return {
            'person_id': person.id,
            'slug': person.slug,
            'version': 1,
            'profile_status': 'draft',
            'identity': {
                'display_name': person.chinese_name,
                'english_name': person.english_name,
                'one_line_identity': source.get('source_brief_intro', ''),
                'domain_category': person.domain_category,
                'archetype': person.ai_archetype,
                'era_context': person.era_context,
                'is_fictional': person.is_fictional,
            },
            'core_traits': core_traits,
            'thinking_style': {
                'summary': thinking_summary,
                'reasoning_patterns': reasoning_patterns,
                'decision_lens': defaults['decision_lens'],
                'questioning_habit': questioning_habit,
            },
            'speaking_style': {
                'tone': defaults['tone'],
                'cadence': 'balanced',
                'verbosity': 'medium',
                'rhetorical_devices': rhetorical_devices,
                'lexical_style': unique_clean([source.get('ai_archetype', ''), category_name]),
                'modernization_policy': 'modernized_with_flavor',
            },
            'values': unique_clean(defaults['values']),
            'blind_spots': unique_clean(defaults['blind_spots']),
            'taboos': [
                '不要伪造这个人物没有说过的话或没有经历过的事件。',
                '不要假装知道用户的隐私、未来或未经提供的事实。',
                '不要完全脱离人物气质，用通用鸡汤替代人物视角。',
            ],
            'preferred_topics': preferred_topics,
            'disallowed_claims': [
                'Do not fabricate historical facts or quotes.',
                'Do not claim direct awareness of modern events unless explicitly reframed for the user.',
            ],
            'response_strategy': {
                'default_mode': defaults['default_mode'],
                'answer_pattern': [
                    '先确认问题中的核心矛盾',
                    '用该人物惯用视角重述问题',
                    '结合检索到的经历或观点给出判断',
                    '落到一个可执行的下一步',
                ],
                'opener_style': '先抓住问题最重要的冲突点。',
                'follow_up_strategy': '在必要时追问用户最真实的目标、代价与边界。',
                'advice_style': defaults['advice_style'],
                'closing_style': '用一句简短、可执行的话收尾。',
            },
            'prompt_contract': {
                'system_rules': [
                    'Stay faithful to the persona while remaining helpful to the user.',
                    'Prefer cautious claims over fabricated certainty.',
                ],
                'persona_rules': [
                    f'Keep the answer aligned with {person.chinese_name} and the advisor archetype {person.ai_archetype}.',
                    f'Use the decision lenses {", ".join(defaults["decision_lens"])} when relevant.',
                    'Keep the answer readable for a modern audience.',
                ],
                'style_rules': [
                    f'Primary tones: {", ".join(defaults["tone"])}.',
                    f'Likely rhetorical devices: {", ".join(rhetorical_devices)}.',
                ],
                'knowledge_usage_rules': [
                    'Use retrieved knowledge chunks as factual grounding.',
                    'If context is thin, answer carefully and signal uncertainty.',
                ],
                'safety_rules': [
                    'Do not provide dangerous or illegal instructions.',
                    'Do not claim access to private data.',
                ],
                'output_format_rules': [
                    'Answer in Chinese unless the user explicitly asks for another language.',
                    'Keep the answer focused and avoid unnecessary preamble.',
                ],
            },
            'generation_notes': {
                'source_dataset_version': dataset_version,
                'source_confidence': 'medium',
                'curation_status': 'seeded',
                'notes': unique_clean([
                    short_summary[:180],
                    *story_seeds[:2],
                ]),
            },
            'metadata': {
                'created_at': now_iso,
                'updated_at': now_iso,
                'created_by': 'system_importer',
                'updated_by': 'system_importer',
            },
        }

    def _build_chunks(self, person: Person, source: dict) -> list[KnowledgeChunk]:
        biography = source.get('biography', {})
        structured = source.get('structured_facts', {})
        source_links = source.get('source_links', {})
        tags = unique_clean(
            [source.get('domain_category', ''), source.get('ai_archetype', '')]
            + structured.get('occupations', [])
        )
        chunks: list[KnowledgeChunk] = []

        def add_chunk(
            chunk_type: str,
            title: str,
            content: str,
            *,
            source_name: str,
            source_priority: int,
            importance_score: float,
            summary: Optional[str] = None,
        ) -> None:
            if not content.strip():
                return
            chunks.append(
                KnowledgeChunk(
                    id=str(uuid4()),
                    person_id=person.id,
                    chunk_type=chunk_type,
                    title=title,
                    content=content.strip(),
                    summary=summary,
                    source_name=source_name,
                    source_url=source_links.get('wikipedia'),
                    source_priority=source_priority,
                    theme_tags=tags,
                    era=biography.get('description'),
                    importance_score=importance_score,
                )
            )

        add_chunk(
            'roster_intro',
            f'{person.chinese_name} roster intro',
            source.get('source_brief_intro', ''),
            source_name='local_roster',
            source_priority=100,
            importance_score=0.95,
        )
        add_chunk(
            'summary',
            f'{person.chinese_name} summary',
            biography.get('summary', ''),
            source_name='wikipedia_summary',
            source_priority=80,
            importance_score=0.9,
            summary=biography.get('description'),
        )
        fact_profile = self._render_fact_profile(person, structured)
        add_chunk(
            'fact_profile',
            f'{person.chinese_name} fact profile',
            fact_profile,
            source_name='wikidata',
            source_priority=85,
            importance_score=0.82,
        )
        for index, story in enumerate(unique_clean(biography.get('story_seeds', [])), start=1):
            add_chunk(
                'story_seed',
                f'{person.chinese_name} story seed #{index}',
                story,
                source_name='derived_story_seed',
                source_priority=60,
                importance_score=0.72,
            )
        extract = biography.get('full_extract', '')
        for index, piece in enumerate(split_text_semantic(extract, chunk_size=700, overlap=80), start=1):
            add_chunk(
                'biography_extract',
                f'{person.chinese_name} extract #{index}',
                piece,
                source_name='wikipedia_extract',
                source_priority=70,
                importance_score=0.75,
            )
        return chunks

    def _render_fact_profile(self, person: Person, structured: dict) -> str:
        parts = [
            f'人物: {person.chinese_name} / {person.english_name}',
            f'职业: {", ".join(unique_clean(structured.get("occupations", []))) or "未知"}',
            f'身份类型: {", ".join(unique_clean(structured.get("instance_of", []))) or "未知"}',
            f'国籍/归属: {", ".join(unique_clean(structured.get("citizenship", []))) or "未知"}',
            f'出生时间: {structured.get("birth_date") or "未知"}',
            f'死亡时间: {structured.get("death_date") or "未知"}',
            f'出生地: {", ".join(unique_clean(structured.get("birth_place", []))) or "未知"}',
            f'死亡地: {", ".join(unique_clean(structured.get("death_place", []))) or "未知"}',
        ]
        return '\\n'.join(parts)

    def _is_fictional(self, instance_of: list[str]) -> bool:
        values = {item.strip().lower() for item in instance_of if item}
        return any(marker in values for marker in FICTIONAL_MARKERS)
