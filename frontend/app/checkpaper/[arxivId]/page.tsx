"use client";

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { checkArxiv } from '../../../services/api';

export default function CheckPaperPage() {
  const params = useParams<{ arxivId: string }>();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState<boolean>(true);

  useEffect(() => {
    const arxivId = (params?.arxivId || '').trim();
    if (!arxivId) {
      setError('Missing arXiv ID');
      setChecking(false);
      return;
    }
    (async () => {
      try {
        setChecking(true);
        setError(null);
        // Use read-only endpoint
        const res = await checkArxiv(arxivId);
        if (res.exists && res.viewer_url) {
          // Redirect to summarized viewer
          router.replace(res.viewer_url);
          return;
        }
        // Not in DB yet: stay on this page and show placeholder
      } catch (e: any) {
        setError(e?.message || 'Failed to check paper');
      } finally {
        setChecking(false);
      }
    })();
  }, [params, router]);

  const arxivId = (params?.arxivId || '').trim();
  const absUrl = arxivId ? `https://arxiv.org/abs/${encodeURIComponent(arxivId)}` : '#';

  return (
    <main className="w-full">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <h1 className="text-2xl font-bold mb-4">Check paper</h1>
        {error && (
          <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">{error}</div>
        )}
        {checking ? (
          <div className="text-gray-600 dark:text-gray-300">Checking if this paper is available…</div>
        ) : (
          <div className="space-y-3">
            <div className="text-gray-700 dark:text-gray-300">
              This paper is not yet simplified on PaperSummarizer.
            </div>
            <div>
              <a
                href={absUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block px-4 py-2 rounded-md bg-gray-100 text-gray-800 border border-gray-300 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-100 dark:border-gray-700 dark:hover:bg-gray-700"
              >
                Open on arXiv
              </a>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}


