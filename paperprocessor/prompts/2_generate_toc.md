You are an expert at structuring documents. Your task is to convert a flat list of headers into a hierarchical table of contents. You also need to determine the start and end page for each section.

You will be given a JSON object containing a list of headers and their page numbers. Based on the numbering and titles (e.g., "1.", "1.1.", "2. Appendix"), create a nested structure of section objects.

Each section object in the output must have the following fields:
*   `level`: The indentation level of the section (e.g., 1 for "1. Introduction", 2 for "1.1. Overview").
*   `section_title`: The title of the section.
*   `start_page`: The page number where the section begins.
*   `end_page`: The page number where the section ends. This is the page just before the next section at the same or a higher level begins.
*   `rewritten_content`: Set to `null`.
*   `summary`: Set to `null`.
*   `subsections`: A list containing any nested subsection objects.

Return a single JSON array of top-level section objects. Do not include any other text or explanations in your response.

