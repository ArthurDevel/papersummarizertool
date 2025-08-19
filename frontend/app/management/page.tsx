"use client";

import { useEffect, useState } from 'react';

type ListItem = {
  id: string;
  title: string;
  created_at?: string;
  total_cost?: number;
  total_tokens?: number;
  processing_time_seconds?: number;
};

export default function ManagementPage() {
  const [papers, setPapers] = useState<ListItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setIsLoading(true);
        setError(null);
        // List from preloaded files and enrich each with summary fields
        const res = await fetch('/layouttests/data', { cache: 'no-store' });
        if (!res.ok) throw new Error(`Failed to list: ${res.status}`);
        const data = await res.json();
        const files: string[] = Array.isArray(data?.files) ? data.files : [];
        // Fetch each JSON to extract summary fields (best effort)
        const items: ListItem[] = await Promise.all(
          files.map(async (f) => {
            try {
              const detailRes = await fetch(`/layouttests/data?file=${encodeURIComponent(f)}`, { cache: 'no-store' });
              if (!detailRes.ok) throw new Error('detail fetch failed');
              const json = await detailRes.json();
              const usage = json?.usage_summary;
              return {
                id: f.replace(/\.json$/i, ''),
                title: f,
                total_cost: typeof usage?.total_cost === 'number' ? usage.total_cost : undefined,
                total_tokens: typeof usage?.total_tokens === 'number' ? usage.total_tokens : undefined,
                processing_time_seconds: typeof json?.processing_time_seconds === 'number' ? json.processing_time_seconds : undefined,
              } as ListItem;
            } catch {
              return { id: f.replace(/\.json$/i, ''), title: f } as ListItem;
            }
          })
        );
        setPapers(items);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unknown error');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  const onImportJson = () => {
    // TODO: wire to backend route; placeholder action
    alert('Import JSON clicked');
  };

  const onAddArxiv = () => {
    // TODO: wire to backend route; placeholder action
    const url = prompt('Enter arXiv URL (e.g., https://arxiv.org/abs/xxxx.xxxxx)');
    if (url) alert(`Add arXiv URL: ${url}`);
  };

  return (
    <div className="px-6 py-6 text-gray-900 dark:text-gray-100">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Management</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={onImportJson}
            className="px-4 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700 transition-colors"
          >
            Import JSON
          </button>
          <button
            onClick={onAddArxiv}
            className="px-4 py-2 rounded-md bg-gray-800 text-white hover:bg-gray-900 transition-colors"
          >
            Add Arxiv URL
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">
          {error}
        </div>
      )}

      {isLoading ? (
        <div>Loading…</div>
      ) : (
        <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-sm overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-700/50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Title</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">ID</th>
                <th className="px-6 py-3" />
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {papers.map((p) => (
                <tr key={p.id}>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    <div className="flex flex-col">
                      <span>{p.title}</span>
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {typeof p.total_cost === 'number' ? `Cost: $${p.total_cost.toFixed(4)}` : 'Cost: N/A'}
                        {typeof p.total_tokens === 'number' ? ` • Tokens: ${p.total_tokens}` : ''}
                        {typeof p.processing_time_seconds === 'number' ? ` • Time: ${p.processing_time_seconds.toFixed(2)}s` : ''}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">{p.id}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                    <a
                      className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                      href={`/layouttests?file=${encodeURIComponent(p.title)}`}
                    >
                      View
                    </a>
                  </td>
                </tr>
              ))}
              {papers.length === 0 && (
                <tr>
                  <td colSpan={3} className="px-6 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
                    No papers found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}


