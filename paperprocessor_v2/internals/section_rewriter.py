import logging
import os
import re
import json
from typing import List, Tuple

from shared.openrouter import client as openrouter_client
from paperprocessor_v2.models import ProcessedDocument, Section

logger = logging.getLogger(__name__)


### CONSTANTS ###
REWRITE_MODEL = "google/gemini-2.5-pro"


### HELPER FUNCTIONS ###
def _write_debug_text(content: str, filename: str) -> None:
    """
    Write plain text debug content to the v2 debugging_output directory.
    """
    debug_dir = os.path.join(os.path.dirname(__file__), '..', 'debugging_output')
    os.makedirs(debug_dir, exist_ok=True)
    path = os.path.join(debug_dir, filename)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def _write_debug_json(data: dict, filename: str) -> None:
    """
    Write JSON debug data to the v2 debugging_output directory.
    """
    debug_dir = os.path.join(os.path.dirname(__file__), '..', 'debugging_output')
    os.makedirs(debug_dir, exist_ok=True)
    path = os.path.join(debug_dir, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_rewrite_prompt() -> str:
    """
    Load the rewrite prompt used for section rewriting.
    """
    prompts_dir = os.path.join(os.path.dirname(__file__), '..', 'prompts')
    prompt_path = os.path.join(prompts_dir, 'rewrite_section.md')
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read()


def _find_section_spans(final_markdown: str) -> List[Tuple[int, int]]:
    """
    Find flat section spans strictly between lines marked as <<section>>.

    Returns a list of (start_offset, end_offset) character offsets for the
    content that follows a <<section>> tag up to (but not including) the next tag.
    Raises RuntimeError if no sections are found.
    """
    if not final_markdown:
        raise RuntimeError("final_markdown is empty")

    lines = final_markdown.splitlines(keepends=True)
    # Precompute line start offsets
    offsets: List[int] = []
    running = 0
    for line in lines:
        offsets.append(running)
        running += len(line)

    tag_line_indexes: List[int] = []
    for idx, line in enumerate(lines):
        if line.strip() == "<<section>>":
            tag_line_indexes.append(idx)

    if not tag_line_indexes:
        raise RuntimeError("No sections found")

    spans: List[Tuple[int, int]] = []
    for i, tag_idx in enumerate(tag_line_indexes):
        # The content starts at the next line after the tag
        content_start_line = tag_idx + 1
        if content_start_line >= len(lines):
            raise RuntimeError("Malformed section: no content after <<section>>")
        start_offset = offsets[content_start_line]

        # End at the line where the next tag begins, or end of document
        if i + 1 < len(tag_line_indexes):
            next_tag_line = tag_line_indexes[i + 1]
            end_offset = offsets[next_tag_line]
        else:
            end_offset = len(final_markdown)

        if not (0 <= start_offset < end_offset <= len(final_markdown)):
            raise RuntimeError("Invalid section boundaries")

        # Ensure there is non-empty content
        section_text = final_markdown[start_offset:end_offset]
        if section_text.strip() == "":
            raise RuntimeError("Empty section content detected")

        spans.append((start_offset, end_offset))

    return spans


def _slice_text(content: str, start: int, end: int) -> str:
    """
    Return substring content[start:end].
    """
    return content[start:end]


def _build_flat_sections(final_markdown: str, spans: List[Tuple[int, int]]) -> List[Section]:
    """
    Build a flat list of Section objects from spans in document order.
    """
    sections: List[Section] = []
    for i, (start, end) in enumerate(spans):
        original = _slice_text(final_markdown, start, end)
        sections.append(Section(order_index=i, original_content=original))
    return sections


def _rewrite_section_text(section_text: str) -> str:
    """
    Call the LLM to rewrite the provided section text.
    Raises RuntimeError if the response is empty.
    """
    prompt = _load_rewrite_prompt()
    response = openrouter_client.get_llm_response(
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": section_text},
        ],
        model=REWRITE_MODEL,
    )

    # get_llm_response returns an awaitable; enforce await here
    # The function signature above is simple; we keep it here for clarity
    raise NotImplementedError("_rewrite_section_text must be awaited via async wrapper")


async def _rewrite_section_text_async(section_text: str) -> str:
    """
    Async wrapper to call the LLM and return response text.
    """
    prompt = _load_rewrite_prompt()
    result = await openrouter_client.get_llm_response(
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": section_text},
        ],
        model=REWRITE_MODEL,
    )
    text = getattr(result, "response_text", None)
    if not text:
        raise RuntimeError("Rewrite failed: empty response text")
    return str(text)


def _flatten_sections_in_document_order(nodes: List[Section]) -> List[Section]:
    """
    Return a flat list of sections in document order (preorder traversal).
    """
    ordered: List[Section] = []

    def _walk(n: Section) -> None:
        ordered.append(n)
        for child in n.subsections:
            _walk(child)

    for root in nodes:
        _walk(root)

    # Sort by start offset to be explicit about document order
    ordered.sort(key=lambda s: s.start_offset)
    return ordered


### PUBLIC API ###
async def rewrite_sections(document: ProcessedDocument) -> None:
    """
    Step 6: Rewriting per section (text-only).
    Parses sections from document.final_markdown using <<section>> tags and
    markdown headers, rewrites each section with the LLM, builds hierarchy,
    and assembles rewritten_final_markdown. Modifies the document in place.
    """
    logger.info("Rewriting sections (v2, text-based)...")

    # Preconditions
    if document.final_markdown is None or document.final_markdown.strip() == "":
        raise RuntimeError("final_markdown is empty")

    # 1) Find section spans
    spans = _find_section_spans(document.final_markdown)

    # 2) Build flat sections
    sections = _build_flat_sections(document.final_markdown, spans)

    # 3) Rewrite each section sequentially
    for section in sections:
        rewritten = await _rewrite_section_text_async(section.original_content)
        section.rewritten_content = rewritten

    # 4) Persist on document
    document.sections = sections

    # 5) Assemble rewritten_final_markdown as concatenation of rewritten sections in order
    parts: List[str] = []
    for section in sections:
        if not section.rewritten_content:
            raise RuntimeError("Missing rewritten content for a section")
        parts.append(section.rewritten_content)
    document.rewritten_final_markdown = "\n\n".join(parts)

    # 6) Debug outputs
    sections_debug = [{
        "order_index": s.order_index,
        "original_length": len(s.original_content),
        "rewritten_length": len(s.rewritten_content or ""),
    } for s in sections]
    _write_debug_json({"sections": sections_debug}, "section_tree.json")
    _write_debug_text(document.rewritten_final_markdown or "", "rewritten_final_markdown.md")

    logger.info("Section rewriting completed.")
