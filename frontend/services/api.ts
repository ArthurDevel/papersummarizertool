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
