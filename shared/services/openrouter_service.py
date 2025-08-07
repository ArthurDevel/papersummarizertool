import httpx
import logging
from shared.config import settings
from typing import Dict, Any, List
import asyncio
import json

logger = logging.getLogger(__name__)

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
            timeout=120  # Generous timeout for model generation
        )

    async def get_llm_response(self, messages: List[Dict[str, str]], model: str) -> Dict[str, Any]:
        """
        Gets a response from a specified LLM on OpenRouter with a given prompt.
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
            return json.loads(json_content)
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