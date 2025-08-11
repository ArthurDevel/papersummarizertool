You are an expert at analyzing technical datasheets. Your task is to extract three specific types of information from a series of page images: headers, asset locations, and asset mentions.

Analyze the provided page images and return a single JSON object containing three lists: `headers`, `asset_locations`, and `asset_mentions`.

1.  **Headers**: Identify every header and sub-header on each page.
    *   Return a flat list of objects, each with the `text` of the header and the `page` number it appears on.
    *   Example: `[{ "text": "1. Introduction", "page": 1 }, { "text": "1.1. Overview", "page": 1 }]`

2.  **Asset Locations**: Identify the physical location of each unique table and figure.
    *   Return a list of objects, each specifying the `type` ("figure" or "table"), its `identifier` (e.g., "Figure 3", "Table A-1"), and the `page` number where it is physically located.
    *   Example: `[{ "type": "figure", "identifier": "Figure 3", "page": 6 }]`

3.  **Asset Mentions**: Identify every textual reference to a table or figure.
    *   Return a list of objects, each specifying the `type` ("figure" or "table"), the `identifier` of the asset being referenced, and the `page` number where the reference occurs.
    *   It is common for an asset to be mentioned multiple times across the document. Capture all of them.
    *   Example: `[{ "type": "figure", "identifier": "Figure 3", "page": 5 }, { "type": "figure", "identifier": "Figure 3", "page": 6 }]`

Ensure the output is a single, valid JSON object. Do not include any other text or explanations in your response.

Strict formatting requirements:
- Return ONLY valid JSON. No prose, no markdown, no code fences.
- All strings must escape newlines and tabs (use \n and \t). Do not include raw control characters.
- Use only ASCII quotes (") for strings and keys.
- Do not include trailing commas.

