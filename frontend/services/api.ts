import { JobStatusResponse, Paper } from '../types/paper';

export const API_URL = '/api'; // The backend is on port 8000, but we're proxying, see next.config.js

export const processPaper = async (file: File): Promise<JobStatusResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_URL}/papers/process`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }

    return response.json();
};

export const getJobStatus = async (jobId: string): Promise<Paper | null> => {
    const response = await fetch(`${API_URL}/papers/process/${jobId}`);

    if (response.status === 202) {
        // Job is still processing, return null to indicate polling should continue
        return null;
    }
    
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }

    // Job is complete, return the final result
    return response.json();
}

export type EnqueueArxivResponse = {
    job_db_id: number;
    paper_uuid: string;
    status: string;
}

export const enqueueArxiv = async (url: string): Promise<EnqueueArxivResponse> => {
    const response = await fetch(`${API_URL}/papers/enqueue_arxiv`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ url }),
    });
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    return response.json();
}

export type JobDbStatus = {
    paper_uuid: string;
    status: string;
    error_message?: string | null;
    created_at: string;
    updated_at: string;
    started_at?: string | null;
    finished_at?: string | null;
    arxiv_id: string;
    arxiv_version?: string | null;
    num_pages?: number | null;
    processing_time_seconds?: number | null;
    total_cost?: number | null;
    avg_cost_per_page?: number | null;
}

export const listPapers = async (status?: string): Promise<JobDbStatus[]> => {
    const url = new URL(`${API_URL}/papers`, window.location.origin);
    if (status) url.searchParams.set('status', status);
    const response = await fetch(url.toString());
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    return response.json();
}
