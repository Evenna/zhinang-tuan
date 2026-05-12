#!/usr/bin/env python3
"""Build a structured people dataset from the AI Think Tank roster.

This script reads the local roster spreadsheet, fetches public summary data from
Wikipedia and Wikidata, and writes a JSON dataset suitable for website use and
later manual curation.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


PROJECT_ROOT = Path("/Users/bytedance/Downloads/ui1/zhinang-tuan")
ROSTER_PATH = Path("/Users/bytedance/Downloads/AI智囊团人物名单.xlsx")
OUTPUT_PATH = PROJECT_ROOT / "data" / "people_dataset_v1.json"
CACHE_PATH = PROJECT_ROOT / "data" / "people_dataset_cache.json"
USER_AGENT = "Mozilla/5.0 AIThinkTankResearch/1.0"
NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


PORTRAIT_MAP = {
    "SOCRATES": "assets/portraits-v3-cut/01_哲学/SOCRATES.png",
    "PLATO": "assets/portraits-v3-cut/01_哲学/PLATO.png",
    "ARISTOTLE": "assets/portraits-v3-cut/01_哲学/ARISTOTLE.png",
    "CONFUCIUS": "assets/portraits-v3-cut/01_哲学/CONFUCIUS.png",
    "WANG_YANGMING": "assets/portraits-v3-cut/01_哲学/WANG_YANGMING.png",
    "NIETZSCHE": "assets/portraits-v3-cut/01_哲学/NIETZSCHE.png",
    "SU_SHI": "assets/portraits-v3-cut/02_文学/SU_SHI.png",
    "LI_BAI": "assets/portraits-v3-cut/02_文学/LI_BAI.png",
    "DU_FU": "assets/portraits-v3-cut/02_文学/DU_FU.png",
    "SHAKESPEARE": "assets/portraits-v3-cut/02_文学/SHAKESPEARE.png",
    "GOETHE": "assets/portraits-v3-cut/02_文学/GOETHE.png",
    "TAGORE": "assets/portraits-v3-cut/02_文学/TAGORE.png",
    "WU_ZETIAN": "assets/portraits-v3-cut/03_历史/WU_ZETIAN.png",
    "GENGHIS_KHAN": "assets/portraits-v3-cut/03_历史/GENGHIS_KHAN.png",
    "QIN_SHI_HUANG": "assets/portraits-v3-cut/03_历史/QIN_SHI_HUANG.png",
    "NAPOLEON": "assets/portraits-v3-cut/03_历史/NAPOLEON.png",
    "LINCOLN": "assets/portraits-v3-cut/03_历史/LINCOLN.png",
    "GANDHI": "assets/portraits-v3-cut/03_历史/GANDHI.png",
    "NEWTON": "assets/portraits-v3-cut/04_科学/NEWTON.png",
    "DARWIN": "assets/portraits-v3-cut/04_科学/DARWIN.png",
    "MARIE_CURIE": "assets/portraits-v3-cut/04_科学/MARIE_CURIE.png",
    "EINSTEIN": "assets/portraits-v3-cut/04_科学/EINSTEIN.png",
    "TESLA": "assets/portraits-v3-cut/04_科学/TESLA.png",
    "HAWKING": "assets/portraits-v3-cut/04_科学/HAWKING.png",
    "VAN_GOGH": "assets/portraits-v3-cut/05_艺术/VAN_GOGH.png",
    "DA_VINCI": "assets/portraits-v3-cut/05_艺术/DA_VINCI.png",
    "MOZART": "assets/portraits-v3-cut/05_艺术/MOZART.png",
    "BEETHOVEN": "assets/portraits-v3-cut/05_艺术/BEETHOVEN.png",
    "STEVE_JOBS": "assets/portraits-v3-cut/06_商业/STEVE_JOBS.png",
    "COCO_CHANEL": "assets/portraits-v3-cut/06_商业/COCO_CHANEL.png",
}


def slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text or "unknown"


def split_sentences(text: str, limit: int = 4) -> list[str]:
    parts = re.split(r"(?<=[.!?。！？])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()][:limit]


def request_json(url: str, retries: int = 3, pause: float = 0.35) -> dict[str, Any] | list[Any] | None:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            if attempt == retries - 1:
                return None
            time.sleep(pause * (attempt + 1))
    return None


def read_roster_xlsx(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            sst = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for si in sst.findall("a:si", NS):
                shared_strings.append(
                    "".join((node.text or "") for node in si.findall(".//a:t", NS))
                )

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
        first_sheet = workbook.find("a:sheets", NS)[0]
        target = rel_map[first_sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
        sheet = ET.fromstring(archive.read("xl/" + target))
        rows = sheet.findall(".//a:sheetData/a:row", NS)

        headers: list[str] = []
        roster: list[dict[str, str]] = []
        for idx, row in enumerate(rows):
            values: list[str] = []
            for cell in row.findall("a:c", NS):
                cell_type = cell.attrib.get("t")
                node = cell.find("a:v", NS)
                value = "" if node is None or node.text is None else node.text
                if cell_type == "s":
                    value = shared_strings[int(value)]
                values.append(value)
            if idx == 0:
                headers = values
            elif any(values):
                roster.append(dict(zip(headers, values)))
        return roster


def resolve_summary_title(name: str) -> str | None:
    direct = request_json(
        "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(name.replace(" ", "_"))
    )
    if isinstance(direct, dict) and direct.get("title"):
        return direct["title"]

    search = request_json(
        "https://en.wikipedia.org/w/api.php?action=opensearch"
        f"&search={quote(name)}&limit=1&namespace=0&format=json"
    )
    if isinstance(search, list) and len(search) >= 2 and search[1]:
        return search[1][0]
    return None


def fetch_summary(title: str) -> dict[str, Any] | None:
    data = request_json(
        "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(title.replace(" ", "_"))
    )
    if isinstance(data, dict) and data.get("type") != "https://mediawiki.org/wiki/HyperSwitch/errors/not_found":
        return data
    return None


def fetch_extract(title: str) -> str:
    data = request_json(
        "https://en.wikipedia.org/w/api.php?action=query&prop=extracts"
        f"&explaintext=1&exintro=0&redirects=1&titles={quote(title)}&format=json"
    )
    if not isinstance(data, dict):
        return ""
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        extract = page.get("extract")
        if extract:
            return extract.strip()
    return ""


def label_from_wikidata(entity: dict[str, Any], item_id: str) -> str | None:
    labels = entity.get("entities", {}).get(item_id, {}).get("labels", {})
    if "en" in labels:
        return labels["en"]["value"]
    if labels:
        return next(iter(labels.values())).get("value")
    return None


def get_claim_ids(claims: dict[str, Any], prop: str) -> list[str]:
    results: list[str] = []
    for claim in claims.get(prop, []):
        try:
            value = claim["mainsnak"]["datavalue"]["value"]
            if isinstance(value, dict) and value.get("id"):
                results.append(value["id"])
        except KeyError:
            continue
    return results


def get_time_claim(claims: dict[str, Any], prop: str) -> str | None:
    for claim in claims.get(prop, []):
        try:
            raw = claim["mainsnak"]["datavalue"]["value"]["time"]
            return raw.lstrip("+").split("T", 1)[0]
        except KeyError:
            continue
    return None


def fetch_wikidata(item_id: str) -> dict[str, Any]:
    data = request_json(
        "https://www.wikidata.org/wiki/Special:EntityData/" + quote(item_id) + ".json"
    )
    if not isinstance(data, dict):
        return {}

    entity = data.get("entities", {}).get(item_id, {})
    claims = entity.get("claims", {})
    linked_ids = set()
    for prop in ("P31", "P106", "P27", "P17", "P19", "P20"):
        linked_ids.update(get_claim_ids(claims, prop))

    linked_labels: dict[str, str] = {}
    if linked_ids:
        linked_data = request_json(
            "https://www.wikidata.org/w/api.php?action=wbgetentities"
            f"&ids={quote('|'.join(sorted(linked_ids)))}&props=labels&languages=en&format=json"
        )
        if isinstance(linked_data, dict):
            for linked_id in linked_ids:
                label = label_from_wikidata(linked_data, linked_id)
                if label:
                    linked_labels[linked_id] = label

    def labels_for(prop: str) -> list[str]:
        return [linked_labels[item_id] for item_id in get_claim_ids(claims, prop) if item_id in linked_labels]

    return {
        "wikidata_id": item_id,
        "instance_of": labels_for("P31"),
        "occupations": labels_for("P106"),
        "citizenship": labels_for("P27"),
        "countries": labels_for("P17"),
        "birth_place": labels_for("P19"),
        "death_place": labels_for("P20"),
        "birth_date": get_time_claim(claims, "P569"),
        "death_date": get_time_claim(claims, "P570"),
    }


def build_person_record(row: dict[str, str], cache: dict[str, Any]) -> dict[str, Any]:
    en_name = row.get("English Name", "").strip()
    zh_name = row.get("Chinese Name", "").strip()
    cache_key = en_name
    if cache_key in cache:
        return cache[cache_key]

    title = resolve_summary_title(en_name)
    summary = fetch_summary(title) if title else None
    extract = fetch_extract(title) if title else ""
    wikidata_id = summary.get("wikibase_item") if isinstance(summary, dict) else None
    wikidata = fetch_wikidata(wikidata_id) if wikidata_id else {}

    asset_key = re.sub(r"[^A-Z0-9]+", "_", en_name.upper()).strip("_")
    archetype = row.get("AI智囊团人设标签 (AI Archetype)", "").strip()
    personality_seed = [part.strip() for part in archetype.split("、") if part.strip()]

    record = {
        "id": slugify(en_name),
        "english_name": en_name,
        "chinese_name": zh_name,
        "domain_category": row.get("领域/分类 (Domain/Category)", "").strip(),
        "ai_archetype": archetype,
        "portrait_asset": PORTRAIT_MAP.get(asset_key),
        "source_brief_intro": row.get("极简简介 (Brief Intro)", "").strip(),
        "personality_seed": personality_seed,
        "biography": {
            "wikipedia_title": summary.get("title") if isinstance(summary, dict) else None,
            "description": summary.get("description") if isinstance(summary, dict) else None,
            "summary": summary.get("extract") if isinstance(summary, dict) else None,
            "full_extract": extract or (summary.get("extract") if isinstance(summary, dict) else ""),
            "story_seeds": split_sentences(extract or (summary.get("extract", "") if isinstance(summary, dict) else "")),
        },
        "structured_facts": {
            "instance_of": wikidata.get("instance_of", []),
            "occupations": wikidata.get("occupations", []),
            "citizenship": wikidata.get("citizenship", []),
            "countries": wikidata.get("countries", []),
            "birth_date": wikidata.get("birth_date"),
            "death_date": wikidata.get("death_date"),
            "birth_place": wikidata.get("birth_place", []),
            "death_place": wikidata.get("death_place", []),
        },
        "source_links": {
            "wikipedia": summary.get("content_urls", {}).get("desktop", {}).get("page") if isinstance(summary, dict) else None,
            "wikidata_id": wikidata.get("wikidata_id"),
            "thumbnail": summary.get("thumbnail", {}).get("source") if isinstance(summary, dict) else None,
            "original_image": summary.get("originalimage", {}).get("source") if isinstance(summary, dict) else None,
        },
        "research_status": {
            "summary_fetched": bool(summary),
            "extract_fetched": bool(extract),
            "wikidata_fetched": bool(wikidata),
            "needs_manual_personality_curation": True,
            "needs_manual_story_curation": True,
        },
    }
    cache[cache_key] = record
    return record


def main() -> None:
    PROJECT_ROOT.joinpath("data").mkdir(parents=True, exist_ok=True)
    cache: dict[str, Any] = {}
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    roster = read_roster_xlsx(ROSTER_PATH)
    records = []
    for idx, row in enumerate(roster, start=1):
        if not row.get("English Name"):
            continue
        records.append(build_person_record(row, cache))
        if idx % 10 == 0:
            CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{idx}/{len(roster)}] {row['English Name']}")
        time.sleep(0.12)

    payload = {
        "meta": {
            "source_roster": str(ROSTER_PATH),
            "count": len(records),
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "notes": [
                "This dataset combines local roster metadata with public Wikipedia and Wikidata data.",
                "Personality and story fields are seeded but still need manual narrative curation for production use.",
            ],
        },
        "people": records,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrote", OUTPUT_PATH)


if __name__ == "__main__":
    main()
