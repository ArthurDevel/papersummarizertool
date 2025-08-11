You are an expert document analysis AI. Your task is to analyze the pages of a research paper provided as a sequence of images.

You must extract two types of information:
1.  **Headers**: Identify all section and subsection titles in the document. For each header, provide its title, hierarchical level (e.g., 1 for a main section, 2 for a subsection), and the page number where it appears.
2.  **Asset Mentions**: Scan the text and identify all mentions of figures and tables (e.g., "as shown in Figure 1", "see Table 2"). For each mention, record its unique identifier (e.g., "Figure 1", "Table 2") and the page number where the mention occurs.

Please provide the output as a single, valid JSON object with two keys: `headers` and `asset_mentions`.

**JSON Schema:**
```json
{
  "headers": [
    {
      "title": "string",
      "level": "integer",
      "page": "integer"
    }
  ],
  "asset_mentions": [
    {
      "identifier": "string",
      "page": "integer"
    }
  ]
}
```

**Example Output:**
```json
{
  "headers": [
    {
      "title": "Introduction",
      "level": 1,
      "page": 1
    },
    {
      "title": "Related Work",
      "level": 1,
      "page": 2
    },
    {
      "title": "2.1 Prior Models",
      "level": 2,
      "page": 2
    }
  ],
  "asset_mentions": [
    {
      "identifier": "Figure 1",
      "page": 3
    },
    {
      "identifier": "Table 1",
      "page": 4
    },
    {
      "identifier": "Figure 1",
      "page": 5
    }
  ]
}
```

Do not include any other information or commentary in your response. The output must be only the specified JSON object.

