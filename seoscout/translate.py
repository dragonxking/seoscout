#!/usr/bin/env python3
"""
Step 4: Translate articles to multiple languages.

Reads articles/en/*.mdx (or *.md), translates via LLM, outputs to articles/{lang}/*.mdx.
"""

import asyncio
import json
import os
import re
import time
from pathlib import Path
from string import Template
from datetime import datetime

from .core.config import Config
from .core.llm_client import LLMClient
from .core.utils import ensure_dir


# ── language map ────────────────────────────────────────────────

LANG_NAMES = {
    'es': 'Spanish',
    'pt': 'Portuguese (Brazil)',
    'de': 'German',
    'fr': 'French',
    'ja': 'Japanese',
    'ar': 'Arabic',
    'ko': 'Korean',
    'ru': 'Russian',
    'zh': 'Chinese',
    'vi': 'Vietnamese',
    'th': 'Thai',
    'id': 'Indonesian',
    'tr': 'Turkish',
    'it': 'Italian',
    'pl': 'Polish',
    'nl': 'Dutch',
    'hi': 'Hindi',
}


# ── helpers ─────────────────────────────────────────────────────

def load_prompt_template(prompt_path: str = None) -> str:
    """Load translation prompt template from file or built-in default."""
    if prompt_path:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return f.read()
    default = Path(__file__).parent / "templates" / "translate.md"
    with open(default, 'r', encoding='utf-8') as f:
        return f.read()


def clean_llm_output(content: str) -> str:
    """Strip code fences (handles any language tag like ```javascript, ```mdx, etc.)."""
    content = content.strip()
    # Match opening code fence with optional language tag (e.g. ```javascript, ```mdx, ```markdown)
    if content.startswith('```'):
        first_newline = content.find('\n')
        if first_newline != -1:
            content = content[first_newline + 1:]
        else:
            content = content[3:]
    if content.rstrip().endswith('```'):
        content = content.rstrip()[:-3].rstrip()
    return content


def validate_markdown(content: str) -> tuple:
    """Basic check: non-empty, has structure (JS export metadata or headings)."""
    if not content or not content.strip():
        return False, "Empty content"
    has_structure = (
        'export const metadata' in content[:200]
        or '## ' in content
        or '# ' in content
    )
    if not has_structure:
        return False, "No heading or metadata export found"
    if len(content) < 100:
        return False, f"Too short ({len(content)} chars)"
    return True, ""


# ── main logic ──────────────────────────────────────────────────

async def run_translate(
    project: str,
    lang: str,
    prompt_path: str = None,
    overwrite: bool = False,
    test: bool = False,
):
    """
    Translate English articles to target languages.

    Args:
        project: Project name
        lang: Comma-separated language codes (e.g. 'es,pt,de')
        prompt_path: Optional custom prompt template
        overwrite: Overwrite existing translations
        test: Only translate 1 article
    """
    Config.init(project)

    print("=" * 70)
    print(f"  Step 4: Translate [{project}]")
    print("=" * 70)

    # Parse languages (any code accepted, name resolved from map or title-cased)
    target_langs = list(dict.fromkeys(l.strip() for l in lang.split(',') if l.strip() and l.strip() != 'en'))
    if not target_langs:
        print("  ❌ No target languages specified")
        return

    resolved_names = {l: LANG_NAMES.get(l, l.upper()) for l in target_langs}
    print(f"  🌍 Target: {', '.join(f'{resolved_names[l]} ({l})' for l in target_langs)}\n")

    # Load prompt template
    prompt_template_str = load_prompt_template(prompt_path)
    prompt_template = Template(prompt_template_str)

    # Find English articles (flat + category subdirs)
    en_dir = Path(Config.DATA_DIR) / "articles" / "en"
    if not en_dir.exists():
        print(f"  ❌ No English articles found at {en_dir}")
        print("     Run `seoscout generate` first")
        return

    # Read .mdx (preferred) and .md files from English articles
    mdx_files = sorted(en_dir.glob("**/*.mdx"))
    md_files = sorted(en_dir.glob("**/*.md"))
    # Deduplicate by stem: prefer .mdx over .md
    seen = set()
    articles = []
    for f in mdx_files + md_files:
        key = str(f.relative_to(en_dir).with_suffix(''))
        if key not in seen:
            seen.add(key)
            articles.append(f)

    if not articles:
        print("  ❌ No .mdx/.md files in articles/en/")
        return

    if test:
        articles = articles[:1]
        print(f"  🧪 TEST MODE: {len(articles)} article(s)\n")

    print(f"  📄 Found {len(articles)} English articles")

    # Build tasks
    all_tasks = []
    for article_path in articles:
        try:
            en_content = article_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"  ⚠️  Can't read {article_path.name}: {e}")
            continue

        article_name = article_path.stem
        # Preserve category subdirectory structure
        relative = article_path.relative_to(en_dir)

        for lang_code in target_langs:
            # Output as .mdx (change extension if source is .md)
            out_relative = relative.with_suffix('.mdx')
            output_path = Path(Config.DATA_DIR) / "articles" / lang_code / out_relative

            if output_path.exists() and not overwrite:
                continue

            prompt = prompt_template.substitute(
                language_name=resolved_names[lang_code],
                lang_code=lang_code,
                content=en_content,
            )

            all_tasks.append({
                'prompt': prompt,
                'lang': lang_code,
                'article_name': article_name,
                'output_path': output_path,
                'en_content': en_content,
            })

    skipped = len(articles) * len(target_langs) - len(all_tasks)
    if skipped > 0:
        print(f"  ⏭️  Skipped {skipped} (already translated)\n")

    if not all_tasks:
        print("  ℹ️  All articles already translated")
        return

    print(f"  📝 {len(all_tasks)} translation tasks\n")
    print(f"     Batch size: {Config.TRANSLATE_BATCH_SIZE}")
    print(f"     Batch delay: {Config.TRANSLATE_BATCH_DELAY}s")
    print(f"     Model: {Config.LLM_MODEL}\n")

    # Execute in batches
    client = LLMClient()
    client.stats['start_time'] = time.time()

    batch_size = Config.TRANSLATE_BATCH_SIZE
    batch_delay = Config.TRANSLATE_BATCH_DELAY
    saved = 0
    failed = 0

    async with __import__('aiohttp').ClientSession() as session:
        for i in range(0, len(all_tasks), batch_size):
            batch = all_tasks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(all_tasks) + batch_size - 1) // batch_size

            print(f"  📦 Batch {batch_num}/{total_batches} ({len(batch)} tasks)...")

            tasks = [
                client.generate_single(session, t['prompt'], {
                    'keyword': t['article_name'],
                    'language': t['lang'],
                })
                for t in batch
            ]
            results = await asyncio.gather(*tasks)

            for task_info, content in zip(batch, results):
                lang_code = task_info['lang']
                article_name = task_info['article_name']
                output_path = task_info['output_path']

                if not content:
                    failed += 1
                    print(f"    ❌ [{lang_code.upper()}] {article_name} — no response")
                    continue

                cleaned = clean_llm_output(content)
                is_valid, err = validate_markdown(cleaned)

                if is_valid:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(cleaned, encoding='utf-8')
                    saved += 1
                    print(f"    ✅ [{lang_code.upper()}] {article_name}.mdx")
                else:
                    # Single repair attempt
                    repair_prompt = _build_repair_prompt(
                        prompt_template, task_info['en_content'],
                        lang_code, article_name, err,
                    )
                    repaired = await client.generate_single(
                        session, repair_prompt,
                        {'keyword': article_name, 'language': lang_code},
                    )
                    if repaired:
                        cleaned = clean_llm_output(repaired)
                        is_valid2, err2 = validate_markdown(cleaned)
                        if is_valid2:
                            output_path.parent.mkdir(parents=True, exist_ok=True)
                            output_path.write_text(cleaned, encoding='utf-8')
                            saved += 1
                            print(f"    ✅ [{lang_code.upper()}] {article_name}.mdx (repaired)")
                            continue

                    failed += 1
                    print(f"    ❌ [{lang_code.upper()}] {article_name} — {err}")

            if i + batch_size < len(all_tasks):
                await asyncio.sleep(batch_delay)

    # Summary
    client.stats['end_time'] = time.time()
    print("\n" + "=" * 70)
    print(f"  {'✅' if failed == 0 else '⚠️ '} Translate complete")
    print("=" * 70)
    print(f"  Saved:   {saved}")
    print(f"  Failed:  {failed}")
    for lang_code in target_langs:
        lang_dir = Path(Config.DATA_DIR) / "articles" / lang_code
        count = len(list(lang_dir.glob("**/*.mdx"))) if lang_dir.exists() else 0
        print(f"  {resolved_names[lang_code]} ({lang_code}): {count} files")
    client.print_stats()
    print("=" * 70)


def _build_repair_prompt(
    template: Template, en_content: str,
    lang_code: str, article_name: str, error: str,
) -> str:
    """Build a repair prompt for failed translations."""
    lang_name = LANG_NAMES.get(lang_code, lang_code)
    base = template.substitute(
        language_name=lang_name,
        lang_code=lang_code,
        content=en_content,
    )
    return (
        base
        + f"\n\n---\n\n"
        f"The previous translation for \"{article_name}\" to {lang_name} had issues:\n"
        f"  Error: {error}\n\n"
        f"Regenerate the FULL translated article from scratch. Fix the issues above.\n"
        f"Output ONLY valid MDX starting with `export const metadata = {{`.\n"
        f"Do NOT wrap in code blocks. Do NOT use YAML frontmatter (---)."
    )
