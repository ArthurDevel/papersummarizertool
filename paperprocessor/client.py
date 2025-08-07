import logging
from typing import Dict, Any, List
import os
import io
import base64
import json
from PIL import Image
import asyncio
from concurrent.futures import ThreadPoolExecutor

from paperprocessor.internals.pdf_to_image import convert_pdf_to_images
from shared.services.openrouter_service import openrouter_service
from api.types.paper_processing_api_models import Paper

class PaperProcessorClient:
    """
    Client for handling the paper processing pipeline.
    """

    def __init__(self):
        """
        Initializes the PaperProcessorClient.
        """
        self.prompts_dir = os.path.join(os.path.dirname(__file__), 'prompts')
        self.executor = ThreadPoolExecutor(max_workers=os.cpu_count())
        logging.info(f"PaperProcessorClient initialized. Prompts loading from: {self.prompts_dir}")

    def _load_prompt(self, file_name: str) -> str:
        """Loads a prompt from a file in the prompts directory."""
        file_path = os.path.join(self.prompts_dir, file_name)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logging.error(f"Prompt file not found: {file_path}")
            raise
        except Exception as e:
            logging.error(f"Error loading prompt file {file_path}: {e}")
            raise

    def _image_to_base64(self, image: Image.Image) -> str:
        """Converts a PIL Image to a base64 encoded string."""
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    async def _extract_initial_content(self, images: List[Image.Image]) -> Dict[str, Any]:
        """Processes images to extract headers and asset information."""
        logging.info(f"Step 2: Starting initial content extraction for {len(images)} pages.")
        system_prompt = self._load_prompt("1_extract_content.md")
        user_prompt_parts = [
            {"type": "text", "text": "Here are the pages of the document. Please analyze them and provide the requested JSON output."}
        ] + [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{self._image_to_base64(img)}"}}
            for img in images
        ]

        response = await openrouter_service.get_multimodal_json_response(
            system_prompt=system_prompt,
            user_prompt_parts=user_prompt_parts,
            model="anthropic/claude-3.5-sonnet"
        )
        logging.info("Successfully extracted initial content.")
        if "headers" not in response or "asset_locations" not in response or "asset_mentions" not in response:
            raise ValueError("Invalid response format from content extraction LLM.")
        return response

    async def _generate_toc(self, headers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generates a hierarchical table of contents from a flat list of headers."""
        logging.info("Step 3: Generating Table of Contents.")
        system_prompt = self._load_prompt("2_generate_toc.md")
        user_prompt = json.dumps({"headers": headers})

        response = await openrouter_service.get_json_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model="anthropic/claude-3.5-sonnet"
        )
        logging.info("Successfully generated Table of Contents.")
        if not isinstance(response, list):
             raise ValueError("Invalid response format from ToC generation LLM. Expected a list.")
        return response

    async def _explain_asset(self, asset_info: Dict[str, Any], all_images: List[Image.Image], toc: List[Dict[str, Any]], asset_mentions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Explains a single asset by providing context images to an LLM."""
        identifier = asset_info["identifier"]
        asset_type = asset_info["type"]
        location_page = asset_info["page"]

        # Find all pages where the asset is mentioned
        mention_pages = {m["page"] for m in asset_mentions if m["identifier"] == identifier}
        
        # Get the image of the page where the asset is located
        location_image = all_images[location_page - 1]

        # Get images from all sections where the asset is mentioned
        # This is a simplification; a more robust solution would map pages to sections
        context_images = {page - 1: all_images[page - 1] for page in mention_pages}
        context_images[location_page - 1] = location_image # Ensure location page is included

        system_prompt = self._load_prompt("3_explain_asset.md")
        user_prompt_parts = [
            {"type": "text", "text": f"Please explain the following {asset_type}: {identifier}"}
        ] + [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{self._image_to_base64(img)}"}}
            for img in context_images.values()
        ]

        explanation_response = await openrouter_service.get_multimodal_json_response(
            system_prompt=system_prompt,
            user_prompt_parts=user_prompt_parts,
            model="anthropic/claude-3.5-sonnet"
        )

        return {
            f"{asset_type}_identifier": identifier,
            "location_page": location_page,
            "explanation": explanation_response.get("explanation", "Could not generate explanation."),
            "image_path": f"page_{location_page}.png", # Placeholder path
            "referenced_on_pages": sorted(list(mention_pages))
        }

    async def _explain_assets(self, asset_locations: List[Dict[str, Any]], asset_mentions: List[Dict[str, Any]], all_images: List[Image.Image], toc: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Generates explanations for all tables and figures."""
        logging.info("Step 4: Generating asset explanations.")
        
        tasks = [
            self._explain_asset(asset, all_images, toc, asset_mentions) 
            for asset in asset_locations
        ]
        
        results = await asyncio.gather(*tasks)
        
        tables = [res for res in results if "table_identifier" in res]
        figures = [res for res in results if "figure_identifier" in res]
        
        logging.info(f"Explained {len(tables)} tables and {len(figures)} figures.")
        return {"tables": tables, "figures": figures}

    async def _process_section(self, section: Dict[str, Any], all_images: List[Image.Image]) -> Dict[str, Any]:
        """Rewrites and summarizes a single section using its page images."""
        start_page = section["start_page"]
        end_page = section["end_page"]
        title = section["section_title"]
        logging.info(f"Processing section '{title}' (pages {start_page}-{end_page}).")

        section_images = all_images[start_page - 1:end_page]

        # Prepare prompts
        rewrite_system_prompt = self._load_prompt("4_rewrite_section.md")
        summary_system_prompt = self._load_prompt("5_summarize_section.md")
        
        user_prompt_parts = [
            {"type": "text", "text": f"The section to process is '{title}'."}
        ] + [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{self._image_to_base64(img)}"}}
            for img in section_images
        ]
        
        # Make two separate, non-blocking calls to the LLM
        rewrite_task = openrouter_service.get_llm_response(
            messages=[{"role": "system", "content": rewrite_system_prompt}, {"role": "user", "content": user_prompt_parts}],
            model="anthropic/claude-3.5-sonnet"
        )
        summary_task = openrouter_service.get_llm_response(
            messages=[{"role": "system", "content": summary_system_prompt}, {"role": "user", "content": user_prompt_parts}],
            model="anthropic/claude-3.5-sonnet"
        )

        rewrite_response, summary_response = await asyncio.gather(rewrite_task, summary_task)

        # Update the section object with the new content
        section["rewritten_content"] = rewrite_response.get("choices", [{}])[0].get("message", {}).get("content", "")
        section["summary"] = summary_response.get("choices", [{}])[0].get("message", {}).get("content", "")

        return section

    async def _process_sections(self, toc: List[Dict[str, Any]], all_images: List[Image.Image]) -> List[Dict[str, Any]]:
        """Processes all top-level sections to add rewritten content and summaries."""
        logging.info("Step 5: Processing all top-level sections.")
        
        # We only process top-level sections as per the plan
        tasks = [
            self._process_section(section, all_images)
            for section in toc if section.get("level") == 1
        ]
        
        processed_sections = await asyncio.gather(*tasks)
        
        # Create a map of processed sections by title for easy lookup
        processed_map = {s["section_title"]: s for s in processed_sections}

        # Update the original ToC with the processed data
        for section in toc:
            if section["section_title"] in processed_map:
                section.update(processed_map[section["section_title"]])

        logging.info("Finished processing all top-level sections.")
        return toc

    async def process_paper_pdf(self, pdf_contents: bytes) -> Dict[str, Any]:
        """
        Processes a PDF file through the multi-step pipeline.
        """
        logging.info("Paper processing pipeline started.")
        loop = asyncio.get_running_loop()

        # Step 1: PDF to Image Conversion (CPU-bound)
        logging.info("Step 1: Converting PDF to images.")
        images = await loop.run_in_executor(
            self.executor, convert_pdf_to_images, pdf_contents
        )

        # Step 2: Initial Content Extraction
        content_extraction_result = await self._extract_initial_content(images)
        
        # Step 3: Generate Table of Contents
        toc = await self._generate_toc(content_extraction_result["headers"])

        # Steps 4 & 5: Explain Assets and Process Sections (I/O-bound, run concurrently)
        asset_explanations_task = self._explain_assets(
            content_extraction_result["asset_locations"],
            content_extraction_result["asset_mentions"],
            images,
            toc
        )
        
        processed_sections_task = self._process_sections(toc, images)

        asset_explanations, processed_toc = await asyncio.gather(
            asset_explanations_task,
            processed_sections_task
        )

        # Final Assembly
        title = "Unknown Document"
        if processed_toc:
            # Attempt to find the first major section as the title
            first_section = sorted(processed_toc, key=lambda x: x['start_page'])[0]
            title = first_section.get('section_title', title)

        final_result = {
            "paper_id": "temp_id", # This should be properly generated or passed in
            "title": title,
            "sections": processed_toc,
            "tables": asset_explanations["tables"],
            "figures": asset_explanations["figures"]
        }

        logging.info("Paper processing pipeline finished.")
        return final_result

# Global instance
paper_processor_client = PaperProcessorClient()

async def process_paper_pdf(pdf_contents: bytes) -> Dict[str, Any]:
    return await paper_processor_client.process_paper_pdf(pdf_contents)
