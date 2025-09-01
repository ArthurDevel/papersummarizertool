import os
import re
import requests
from dotenv import load_dotenv

load_dotenv()

# ### CONSTANTS ###
# Paths
INPUT_MARKDOWN_PATH = "output.md"           # Source markdown to simplify
OUTPUT_MARKDOWN_PATH = "output_simplified.md"  # First-pass simplified markdown
OUTPUT_MARKDOWN_CHECKED_PATH = "output_simplified_and_checked.md"  # With feedback pass
PROMPT_PATH = "simplification_prompt.md"     # Simplifier system prompt file
FEEDBACK_PROMPT_PATH = "simplification_feedback_prompt.md"  # Feedback model system prompt

# OpenRouter config
#OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_URL = "http://localhost:18000/v1/chat/completions"
OPENROUTER_MODEL = "google/gemini-2.5-flash"  # Model label on OpenRouter
FEEDBACK_MODEL = "google/gemini-2.5-pro"     # Feedback checker model


# Chunking
MAX_CHARS_PER_CHUNK = 7000  # Keep chunks well under token limits



# ### HELPER FUNCTIONS ###

def split_markdown_into_chunks(markdown_text, max_chars=MAX_CHARS_PER_CHUNK):
    """Split markdown into logical chunks.

    Strategy:
    - First split by top-level sections (lines starting with '## ').
    - If a section is still too large, split by paragraph boundaries (blank lines),
      avoiding splits inside fenced code blocks.
    """

    sections = []
    current_section = []
    lines = markdown_text.splitlines()

    for line in lines:
        if line.startswith("## ") and current_section:
            sections.append("\n".join(current_section).strip())
            current_section = [line]
        else:
            current_section.append(line)
    if current_section:
        sections.append("\n".join(current_section).strip())

    # Further split oversized sections by paragraphs, respecting code fences
    final_chunks = []
    fence_open = False
    fence_pattern = re.compile(r"^```")

    for section in sections:
        if len(section) <= max_chars:
            final_chunks.append(section)
            continue

        # Paragraph-based split
        buffer = []
        buffer_len = 0
        for line in section.splitlines():
            if fence_pattern.match(line):
                fence_open = not fence_open

            # Paragraph boundary (blank line) and not inside code fence
            if not fence_open and not line.strip() and buffer_len >= max_chars:
                final_chunks.append("\n".join(buffer).strip())
                buffer = []
                buffer_len = 0
                continue

            buffer.append(line)
            buffer_len += len(line) + 1

        if buffer:
            final_chunks.append("\n".join(buffer).strip())

    return [c for c in final_chunks if c]


def simplify_chunk_with_openrouter(chunk_text, api_key, system_prompt_text, model=OPENROUTER_MODEL):
    """Send a single chunk to OpenRouter for simplification and return the simplified text.

    The prompt preserves meaning and keeps formulas, tables, images, links and code blocks intact.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    user_prompt = (
        "Simplify the following markdown without altering meaning. Keep formulas, tables, images and links intact.\n\n"
        f"```markdown\n{chunk_text}\n```"
    )

    # Configure internal reasoning budget per model (Gemini Pro requires some thinking)
    reasoning_param = {"max_tokens": 500} if "gemini-2.5-pro" in model else {"max_tokens": 0}

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt_text},
            {"role": "user", "content": user_prompt},
        ],
        # Explicitly disable reasoning output/content for Gemini via OpenRouter extension
        "include_reasoning": False,
        # Internal thinking tokens budget
        "reasoning": reasoning_param,
        # Ask OpenRouter to include usage/cost in response
        "usage": {"include": True},
        "temperature": 0.2,
    }

    response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()

    # Extract assistant content + usage
    try:
        content = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage") or {}
        return content, usage
    except Exception:
        # Fallback: return original chunk if parsing fails
        return chunk_text, {}


def get_feedback_for_chunk(original_text, simplified_text, api_key, feedback_system_prompt, model=FEEDBACK_MODEL):
    """Ask a feedback model to check if meaning changed or was added."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    user_prompt = (
        "You will be given an ORIGINAL markdown section and a SIMPLIFIED version. "
        "Identify any meaning changes, additions, omissions, or incorrect statements. "
        "Be concrete and minimal. If no changes are needed, reply exactly: OK.\n\n"
        "ORIGINAL:\n" + original_text + "\n\n"
        "SIMPLIFIED:\n" + simplified_text + "\n\n"
        "Respond with a short list of issues and corrections. If none, reply: OK."
    )

    reasoning_param = {"max_tokens": 500} if "gemini-2.5-pro" in model else {"max_tokens": 0}

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": feedback_system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        # Explicitly disable reasoning output/content for Gemini via OpenRouter extension
        "include_reasoning": False,
        # Internal thinking tokens budget
        "reasoning": reasoning_param,
        # Ask OpenRouter to include usage/cost in response
        "usage": {"include": True},
        "temperature": 0.0,
    }

    response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage") or {}
        return content, usage
    except Exception:
        return "OK", {}


def revise_with_feedback(chunk_text, simplified_text, feedback_text, api_key, system_prompt_text, model=OPENROUTER_MODEL):
    """Continue the simplification conversation with feedback to produce a revised version."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    initial_user = (
        "Simplify the following markdown without altering meaning. Keep formulas, tables, images and links intact.\n\n"
        f"```markdown\n{chunk_text}\n```"
    )

    feedback_user = (
        "Revise your previous output to address the following feedback. "
        "Do not change meaning. Preserve formulas, tables, images, links, and structure. "
        "If the feedback says OK, return the same text you produced previously.\n\n"
        f"FEEDBACK:\n{feedback_text}"
    )

    messages = [
        {"role": "system", "content": system_prompt_text},
        {"role": "user", "content": initial_user},
        {"role": "assistant", "content": simplified_text},
        {"role": "user", "content": feedback_user},
    ]

    reasoning_param = {"max_tokens": 500} if "gemini-2.5-pro" in model else {"max_tokens": 0}

    payload = {
        "model": model,
        "messages": messages,
        # Explicitly disable reasoning output/content for Gemini via OpenRouter extension
        "include_reasoning": False,
        # Internal thinking tokens budget
        "reasoning": reasoning_param,
        # Ask OpenRouter to include usage/cost in response
        "usage": {"include": True},
        "temperature": 0.2,
    }

    response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    try:
        content = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage") or {}
        return content, usage
    except Exception:
        return simplified_text, {}


def extract_cost(usage_obj):
    """Return a float cost from OpenRouter usage object.
    Prefers usage.total_cost, falls back to usage.cost, else 0.0.
    """
    try:
        if not isinstance(usage_obj, dict):
            return 0.0
        val = usage_obj.get("total_cost")
        if val is None:
            val = usage_obj.get("cost")
        return float(val or 0.0)
    except Exception:
        return 0.0

# ### MAIN SCRIPT ###
def main():
    # Step 1: Read input markdown
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(script_dir, INPUT_MARKDOWN_PATH)
    output_path = os.path.join(script_dir, OUTPUT_MARKDOWN_PATH)
    output_checked_path = os.path.join(script_dir, OUTPUT_MARKDOWN_CHECKED_PATH)
    prompt_path = os.path.join(script_dir, PROMPT_PATH)
    feedback_prompt_path = os.path.join(script_dir, FEEDBACK_PROMPT_PATH)

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input markdown not found: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        markdown_text = f.read()

    # Step 2: Load system prompt
    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt_text = f.read().strip()

    if not os.path.exists(feedback_prompt_path):
        raise FileNotFoundError(f"Feedback prompt file not found: {feedback_prompt_path}")
    with open(feedback_prompt_path, "r", encoding="utf-8") as f:
        feedback_system_prompt = f.read().strip()

    # Step 3: Split into chunks
    chunks = split_markdown_into_chunks(markdown_text, MAX_CHARS_PER_CHUNK)

    # Step 4: Simplify each chunk via OpenRouter
    api_key = os.environ.get('OPENROUTER_API_KEY')
    if not api_key:
        raise EnvironmentError(f"Set OPENROUTER_API_KEY in your environment.")

    simplified_chunks = []
    revised_chunks = []
    # Track costs
    total_cost_simplify = 0.0
    total_cost_feedback = 0.0
    total_cost_revise = 0.0
    for idx, chunk in enumerate(chunks, start=1):
        print(f"Simplifying chunk {idx}/{len(chunks)} (length={len(chunk)})...")
        try:
            simplified, usage_simplify = simplify_chunk_with_openrouter(chunk, api_key, system_prompt_text)
        except Exception as e:
            print(f"Warning: simplification failed for chunk {idx}: {e}. Using original text.")
            simplified, usage_simplify = chunk, {}
        simplified_chunks.append(simplified)
        cost_s = extract_cost(usage_simplify)
        total_cost_simplify += cost_s

        # Feedback and revision pass (without altering first-pass output.md)
        try:
            feedback, usage_feedback = get_feedback_for_chunk(chunk, simplified, api_key, feedback_system_prompt)
            cost_f = extract_cost(usage_feedback)
            total_cost_feedback += cost_f
            preview = feedback[:200] if isinstance(feedback, str) else str(feedback)[:200]
            print(f"Feedback for chunk {idx}: {preview}{'...' if len(feedback) > 200 else ''}")
            revised, usage_revise = revise_with_feedback(chunk, simplified, feedback, api_key, system_prompt_text)
            cost_r = extract_cost(usage_revise)
            total_cost_revise += cost_r
        except Exception as e:
            print(f"Warning: feedback pass failed for chunk {idx}: {e}. Using first-pass text.")
            revised = simplified
        revised_chunks.append(revised)

    # Step 5: Write out the simplified markdown
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(simplified_chunks).strip() + "\n")

    with open(output_checked_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(revised_chunks).strip() + "\n")

    print(f"Saved simplified markdown to: {output_path}")
    print(f"Saved simplified+checked markdown to: {output_checked_path}")

    total_overall = total_cost_simplify + total_cost_feedback + total_cost_revise
    print("\n=== Cost Summary (OpenRouter usage) ===")
    print(f"Initial rewriting:        ${total_cost_simplify:.6f}")
    print(f"Feedback checks:         ${total_cost_feedback:.6f}")
    print(f"Rewriting with feedback: ${total_cost_revise:.6f}")
    print(f"TOTAL:                   ${total_overall:.6f}")


if __name__ == "__main__":
    main()


