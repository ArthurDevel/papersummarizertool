# Analyze Document Structure

You are an expert in analyzing research paper document structure. You will receive the first pages of a research paper and need to identify all structural elements.

## Instructions

Focus on identifying:
1. **Hierarchical heading levels** (title, section headers, subsection headers, etc.)
2. **Visual recognition patterns** (font sizes, styles, formatting, positioning)
3. **Specific examples** from the document
4. **Any unique structural patterns** in this paper

Be precise and detailed in your analysis. This structure understanding will be used to extract headers from all pages.

## Output Format

Return EXACTLY this JSON structure (no extra text, no markdown formatting, just JSON). All fields are required:

```json
{
  "document_type": "string describing type of research paper",
  "elements": [
    {
      "element_type": "main_title",
      "level": 1,
      "recognition_pattern": "description of how to identify this element",
      "examples": ["example 1", "example 2"]
    },
    {
      "element_type": "section_header",
      "level": 2,
      "recognition_pattern": "description of how to identify this element", 
      "examples": ["example 1", "example 2"]
    }
  ],
  "notes": "additional observations about document structure"
}
```

## Guidelines

- **Document type**: What kind of research paper is this?
- **All structural elements**: Every type of heading/title/caption you can see
- **Hierarchy levels**: How are elements organized (level 1, 2, 3, etc.)
- **Recognition patterns**: How can each element be identified? (font size, bold/italic, positioning, numbering, etc.)
- **Concrete examples**: 2-3 actual text examples for each element type
- **Focus**: Headers, titles, section names, subsection names, and any other structural text elements that organize content
