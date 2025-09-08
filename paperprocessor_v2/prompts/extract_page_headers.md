# Extract Page Headers

You are an expert at extracting headers from research paper pages. Use the provided structure analysis to identify all headers accurately.

## Instructions

Based on the document structure analysis provided, extract all headers from this page.

## Task

1. **Identify ALL headers** on this page that match the structure patterns provided
2. **For each header**, determine its exact text, element type, and level
3. **Be thorough** - don't miss any headers, even if they're small or seem minor
4. **Return results** as structured JSON

## Output Format

Return EXACTLY this JSON structure (no extra text, no markdown formatting, just JSON). All fields are required:

```json
{
  "headers": [
    {
      "text": "exact header text as it appears",
      "element_type": "main_title",
      "level": 1
    },
    {
      "text": "another header text", 
      "element_type": "section_header",
      "level": 2
    }
  ]
}
```

## Guidelines

- **Exact text**: Copy header text exactly as it appears in the document
- **Element type**: Must match one of the types from the structure analysis
- **Level**: Must be the correct hierarchical level (1=highest, 6=lowest)
- **Complete**: Find all headers on the page, don't miss any
