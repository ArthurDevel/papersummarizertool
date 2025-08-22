"use client";

import { useState } from 'react';
import Link from 'next/link';
import { requestArxivPaper, type RequestArxivResponse } from '../../services/api';

export default function RequestPaperPage() {
  const [url, setUrl] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [viewerUrl, setViewerUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    setViewerUrl(null);
    setError(null);
    const trimmed = (url || '').trim();
    if (!trimmed || !(trimmed.startsWith('http://') || trimmed.startsWith('https://'))) {
      setError('Please enter a valid arXiv abs/pdf URL.');
      return;
    }
    try {
      setIsSubmitting(true);
      const payload = await requestArxivPaper(trimmed);
      if (payload.state === 'exists' && payload.viewer_url) {
        const urlStr = payload.viewer_url || '';
        if (!urlStr.startsWith('/paper/')) {
          throw new Error('Unexpected viewer URL format from backend');
        }
        setViewerUrl(urlStr);
        setMessage('This paper is already available.');
      } else {
        setMessage('Your request was added.');
      }
      setUrl('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to submit request');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="w-full">
      <div className="max-w-xl mx-auto px-4 sm:px-6 lg:px-8 py-10 text-gray-900 dark:text-gray-100">
        <h1 className="text-3xl font-bold mb-4">Request a Paper</h1>
        <div className="mb-6 p-3 rounded-md border border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
          We add up to 5 papers per day, prioritized by the number of requests each paper receives.
          If you want to be sure your paper gets processed, you can{' '}
          <Link href="/donate" className="underline font-medium">donate inference</Link>{' '}
          and your donation will be used for your preferred papers.
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
          Enter an arXiv abs or pdf URL. We'll add it to the request list.
        </p>
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label htmlFor="arxivUrl" className="block text-sm font-medium mb-1">arXiv URL</label>
            <input
              id="arxivUrl"
              type="url"
              placeholder="https://arxiv.org/abs/2507.12345"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="w-full px-3 py-2 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60"
            >
              {isSubmitting ? 'Submitting…' : 'Submit Request'}
            </button>
          </div>
        </form>
        {message && (
          <div className="mt-6 p-3 rounded-md border border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/40 dark:text-green-300">
            {message}
            {viewerUrl && (
              <div className="mt-2">
                <a href={viewerUrl} className="text-blue-600 hover:underline">Open the paper</a>
              </div>
            )}
          </div>
        )}
        {error && (
          <div className="mt-6 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">
            {error}
          </div>
        )}
      </div>
    </main>
  );
}


