"use client";

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { checkArxiv, getArxivMetadata, requestArxivPaper, type ArxivMetadata } from '../../../services/api';
import { ExternalLink } from 'lucide-react';

export default function CheckPaperPage() {
  const params = useParams<{ arxivId: string }>();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState<boolean>(true);
  const [metadata, setMetadata] = useState<ArxivMetadata | null>(null);
  const [isRequesting, setIsRequesting] = useState<boolean>(false);
  const [requestStatus, setRequestStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [requestMessage, setRequestMessage] = useState<string>('');
  const [notificationEmail, setNotificationEmail] = useState<string>('');

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
        setMetadata(null);
        const res = await checkArxiv(arxivId);
        if (res.exists && res.viewer_url) {
          router.replace(res.viewer_url);
          return;
        }
        const meta = await getArxivMetadata(arxivId);
        setMetadata(meta);
      } catch (e: any) {
        setError(e?.message || 'Failed to check paper');
      } finally {
        setChecking(false);
      }
    })();
  }, [params, router]);

  const arxivId = (params?.arxivId || '').trim();
  const absUrl = metadata?.arxiv_id ? `https://arxiv.org/abs/${encodeURIComponent(metadata.arxiv_id)}` : (arxivId ? `https://arxiv.org/abs/${encodeURIComponent(arxivId)}` : '#');

  const handleRequestPaper = async () => {
    if (!absUrl || absUrl === '#') return;
    setIsRequesting(true);
    setRequestStatus('idle');
    setRequestMessage('');
    try {
      const res = await requestArxivPaper(absUrl, notificationEmail);
      if (res.state === 'requested') {
        setRequestStatus('success');
        setRequestMessage('Thank you for your request! The paper has been added to the request queue.');
      } else if (res.state === 'exists' && res.viewer_url) {
        // Should be rare, but handle it
        router.push(res.viewer_url);
      } else {
        setRequestStatus('success');
        setRequestMessage('This paper is already in our queue or has been processed.');
      }
    } catch (e: any) {
      setRequestStatus('error');
      setRequestMessage(e?.message || 'An unknown error occurred.');
    } finally {
      setIsRequesting(false);
    }
  };


  return (
    <main className="w-full">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {error && (
          <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">{error}</div>
        )}
        {checking ? (
          <div className="text-gray-600 dark:text-gray-300">Checking if this paper is available…</div>
        ) : metadata ? (
          <div className="flex flex-col space-y-6">
            <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-4">
              <div className="min-w-0 flex-1 overflow-hidden break-words">
                <h1 className="text-3xl font-bold mb-1 break-words whitespace-normal">{metadata.title}</h1>
                <p className="text-sm text-gray-700 dark:text-gray-300 mb-1 break-words whitespace-normal">
                  {metadata.authors.map(a => a.name).join(', ')}
                </p>
                <a
                  href={absUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center gap-1.5 text-xs text-blue-600 hover:underline"
                  title="Open on arXiv"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Open on arXiv
                </a>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-4">
              <p className="text-sm text-gray-700 dark:text-gray-300 mb-3">
                This paper is not yet simplified on PaperSummarizer.
              </p>
              <div className="flex flex-col space-y-3">
                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Get notified</label>
                  <input
                    type="email"
                    name="email"
                    id="email"
                    value={notificationEmail}
                    onChange={(e) => setNotificationEmail(e.target.value)}
                    className="mt-1 block w-full px-3 py-2 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 sm:text-sm"
                    placeholder="you@example.com"
                  />
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Will only be used to notify you of this paper, nothing else</p>
                </div>
                <button
                  onClick={handleRequestPaper}
                  disabled={isRequesting || requestStatus === 'success'}
                  className="inline-block px-4 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isRequesting ? 'Requesting...' : requestStatus === 'success' ? 'Requested!' : 'Request this paper'}
                </button>
              </div>
              {requestStatus === 'success' && (
                <div className="mt-3 p-3 text-sm rounded-md border border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/40 dark:text-green-300">
                  {requestMessage}
                </div>
              )}
              {requestStatus === 'error' && (
                <div className="mt-3 p-3 text-sm rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">
                  {requestMessage}
                </div>
              )}
            </div>

            <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-4">
              <h2 className="text-xl font-semibold mb-2">Abstract</h2>
              <div className="prose dark:prose-invert max-w-none text-sm">
                <p>{metadata.summary}</p>
              </div>
            </div>
          </div>
        ) : (
          !error && (
            <div className="text-gray-600 dark:text-gray-300">No information found for this paper.</div>
          )
        )}
      </div>
    </main>
  );
}


