export interface Figure {
  figure_identifier: string;
  location_page: number;
  explanation: string;
  image_path: string;
  referenced_on_pages: number[];
}

export interface Table {
  table_identifier: string;
  location_page: number;
  explanation: string;
  image_path: string;
  referenced_on_pages: number[];
}

export interface Section {
  level: number;
  section_title: string;
  start_page: number;
  end_page: number;
  rewritten_content: string | null;
  summary: string | null;
  subsections: Section[];
}

export interface Paper {
  paper_id: string;
  title: string;
  sections: Section[];
  tables: Table[];
  figures: Figure[];
}

export interface JobStatusResponse {
  job_id: string;
  status: 'processing' | 'completed' | 'failed';
  result?: Paper; // The result is optional, as it's only present when the job is 'completed'
} 