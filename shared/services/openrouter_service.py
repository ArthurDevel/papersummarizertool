import httpx
import logging
from shared.config import settings
from typing import Dict, Any, List
import asyncio
import json
import re

logger = logging.getLogger(__name__)

# Utilities for robust JSON parsing from LLM responses

def _strip_markdown_fences(text: str) -> str:
    """If content is wrapped in Markdown code fences, extract the inner block."""
    if not isinstance(text, str):
        return text
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else text


def _extract_first_json_snippet(text: str) -> str:
    """Extract the first balanced JSON object/array substring from text."""
    if not isinstance(text, str):
        return text
    start_index = None
    stack: List[str] = []
    for i, ch in enumerate(text):
        if ch == '{' or ch == '[':
            start_index = i
            stack = [ch]
            break
    if start_index is None:
        return text.strip()
    for j in range(start_index + 1, len(text)):
        ch = text[j]
        if ch == '{' or ch == '[':
            stack.append(ch)
        elif ch == '}' or ch == ']':
            if not stack:
                continue
            open_ch = stack[-1]
            if (open_ch == '{' and ch == '}') or (open_ch == '[' and ch == ']'):
                stack.pop()
                if not stack:
                    return text[start_index:j + 1]
    return text[start_index:].strip()


def _safe_json_loads(raw_text: str) -> Any:
    """
    Try multiple strategies to parse JSON from an LLM response content string.
    - Direct json.loads
    - Strip markdown code fences, retry
    - Extract first balanced JSON snippet, retry with strict=False to allow control chars
    """
    candidate = raw_text.strip() if isinstance(raw_text, str) else raw_text
    try:
        return json.loads(candidate)
    except (TypeError, json.JSONDecodeError):
        pass

    candidate = _strip_markdown_fences(candidate).strip() if isinstance(candidate, str) else candidate
    try:
        return json.loads(candidate)
    except (TypeError, json.JSONDecodeError):
        pass

    if isinstance(candidate, str):
        candidate = _extract_first_json_snippet(candidate)
    try:
        # Allow control characters in strings
        return json.loads(candidate, strict=False)  # type: ignore[arg-type]
    except Exception:
        logger.error("Failed to parse JSON content. Preview: %s", (candidate[:500] if isinstance(candidate, str) else str(candidate)) )
        raise


class OpenRouterService:
    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not found in settings.")
        
        self.base_url = "https://openrouter.ai/api/v1"
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=300  # Increased timeout for potentially long image processing
        )

    async def get_llm_response(self, messages: List[Dict[str, Any]], model: str) -> Dict[str, Any]:
        """
        Gets a response from a specified LLM on OpenRouter with a given prompt.
        Supports both text-only and multimodal messages.
        """
        json_payload = {
            "model": model,
            "messages": messages
        }
        try:
            response = await self.client.post("/chat/completions", json=json_payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTPStatusError calling OpenRouter: {e}")
            logger.error(f"Request body: {json_payload}")
            raise
        except (KeyError, IndexError) as e:
            logger.error(f"Error parsing OpenRouter response: {e}")
            logger.error(f"Response body: {response.text}")
            raise

    async def get_multimodal_json_response(self, system_prompt: str, user_prompt_parts: List[Dict[str, Any]], model: str) -> Dict[str, Any]:
        """
        Gets a structured JSON response from a specified multimodal LLM on OpenRouter.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt_parts},
        ]
        json_payload = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        try:
            response = await self.client.post("/chat/completions", json=json_payload)
            response.raise_for_status()
            data = response.json()
            # The actual JSON content is in the 'content' field of the first choice's message
            json_content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            return _safe_json_loads(json_content)
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTPStatusError calling OpenRouter for JSON response: {e}")
            logger.error(f"Request body: {json.dumps(json_payload, indent=2)}")
            logger.error(f"Response body: {e.response.text}")
            raise
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing JSON from OpenRouter response: {e}")
            if 'response' in locals() and hasattr(response, 'text'):
                 logger.error(f"Response body: {response.text}")
            raise

    async def get_json_response(self, system_prompt: str, user_prompt: str, model: str) -> Dict[str, Any]:
        """
        Gets a structured JSON response from a specified LLM on OpenRouter.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        json_payload = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        try:
            response = await self.client.post("/chat/completions", json=json_payload)
            response.raise_for_status()
            data = response.json()
            # The actual JSON content is in the 'content' field of the first choice's message
            json_content = data.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            return _safe_json_loads(json_content)
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTPStatusError calling OpenRouter for JSON response: {e}")
            logger.error(f"Request body: {json.dumps(json_payload, indent=2)}")
            logger.error(f"Response body: {e.response.text}")
            raise
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing JSON from OpenRouter response: {e}")
            if 'response' in locals() and hasattr(response, 'text'):
                 logger.error(f"Response body: {response.text}")
            raise

    async def get_generation_cost(self, generation_id: str) -> float:
        """
        Retrieves the cost of a specific generation from OpenRouter.
        """
        try:
            # Add a small delay to allow for the generation stats to be processed.
            await asyncio.sleep(2)

            response = await self.client.get(f"/generation?id={generation_id}")
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"Received cost data for generation {generation_id}: {json.dumps(data)}")

            # The cost is nested inside the 'data' object.
            generation_data = data.get("data", {})
            return generation_data.get("total_cost", 0.0)
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTPStatusError getting generation cost for id {generation_id}: {e}")
            logger.error(f"Response: {e.response.text}")
            raise
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing generation cost response for id {generation_id}: {e}")
            # Use 'response' in a conditional check as it may not be defined if the request fails early
            if 'response' in locals() and hasattr(response, 'text'):
                logger.error(f"Response body: {response.text}")
            raise

# Create a singleton instance to be used by other modules
openrouter_service = OpenRouterService() 