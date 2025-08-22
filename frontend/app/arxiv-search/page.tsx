"use client";

import React, { useState } from 'react';
import { searchPapers, type SearchQueryResponse, type SearchItem } from '../../services/api';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<SearchItem[]>([]);
  const [meta, setMeta] = useState<Pick<SearchQueryResponse, 'rewritten_query' | 'applied_date_from' | 'applied_date_to'> | null>(null);

  const minDate = '2022-09-01';
  const maxDate = new Date().toISOString().slice(0, 10);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    setResults([]);
    setMeta(null);
    try {
      const payload = {
        query: query.trim(),
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        limit: 20,
      };
      const res = await searchPapers(payload);
      setResults(res.items || []);
      setMeta({
        rewritten_query: res.rewritten_query,
        applied_date_from: res.applied_date_from,
        applied_date_to: res.applied_date_to,
      });
    } catch (e: any) {
      setError(e?.message || 'Search failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="w-full">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-6">
          <h1 className="text-3xl font-bold mb-2">Search papers</h1>
        <p className="text-sm text-gray-700 dark:text-gray-300 mb-6">
          This tool allows you to search Arxiv summaries. The summaries are vectorized using voyage-3.5 (vector size 2048).
        </p>
        <form onSubmit={onSubmit} className="space-y-3 mb-6">
          <div>
            <label className="block text-sm font-medium mb-1">Query</label>
            <input value={query} onChange={(e) => setQuery(e.target.value)} className="w-full border rounded px-3 py-2 bg-white dark:bg-gray-800" placeholder="e.g. recent papers in vector search for RAG" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Date from</label>
              <input type="date" min={minDate} max={maxDate} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-full border rounded px-3 py-2 bg-white dark:bg-gray-800" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Date to</label>
              <input type="date" min={minDate} max={maxDate} value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-full border rounded px-3 py-2 bg-white dark:bg-gray-800" />
            </div>
          </div>
          <div className="text-sm text-gray-700 dark:text-gray-300 rounded border border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/30 p-3 space-y-1">
            <div className="font-semibold">Indexed coverage</div>
            <ul className="list-disc list-inside">
              <li>Date range: 2022 to today</li>
              <li>Scope: arXiv Artificial Intelligence (cs.AI) only — more coming soon</li>
            </ul>
          </div>
          <button type="submit" className="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50" disabled={isLoading || !query.trim()}>
            {isLoading ? 'Searching…' : 'Search'}
          </button>
        </form>

        {error && (
          <div className="mb-4 p-3 rounded border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">{error}</div>
        )}

        {meta && (
          <div className="mb-6 text-sm text-gray-600 dark:text-gray-300 space-y-1">
            {meta.rewritten_query && (
              <div><span className="font-semibold">Rewritten query:</span> {meta.rewritten_query}</div>
            )}
            {(meta.applied_date_from || meta.applied_date_to) && (
              <div><span className="font-semibold">Date range:</span> {meta.applied_date_from || '…'} → {meta.applied_date_to || '…'}</div>
            )}
          </div>
        )}

          <div className="space-y-4">
          {results.map((it) => {
            const href = it.abs_url || '#';
            const clickable = Boolean(it.abs_url);
            const formattedDate = (() => {
              if (!it.published) return null;
              const d = new Date(it.published);
              if (isNaN(d.getTime())) return null;
              const day = d.getDate();
              const daySuffix = (n: number) => {
                if (n >= 11 && n <= 13) return 'th';
                switch (n % 10) {
                  case 1: return 'st';
                  case 2: return 'nd';
                  case 3: return 'rd';
                  default: return 'th';
                }
              };
              const month = d.toLocaleString('en-US', { month: 'short' });
              const year = d.getFullYear();
              return `${month} ${day}${daySuffix(day)}, ${year}`;
            })();
            return (
              <a
                key={it.paper_uuid}
                href={href}
                target={it.abs_url ? '_blank' : undefined}
                rel={it.abs_url ? 'noopener noreferrer' : undefined}
                className={`group block border rounded bg-white dark:bg-gray-800 ${clickable ? '' : 'pointer-events-none opacity-60'}`}
              >
                <div className="p-3 relative">
                  <div className="font-semibold text-gray-900 dark:text-gray-100 group-hover:underline break-words line-clamp-3">{it.title || it.paper_uuid}</div>
                  {it.authors && (
                    <div className="text-xs text-gray-600 dark:text-gray-400 mt-1 break-words line-clamp-3">{it.authors}</div>
                  )}
                  {it.summary && (
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-2 break-words line-clamp-4">{it.summary}</div>
                  )}
                  <div className="text-[11px] text-gray-400 mt-2">score: {it.rerank_score ?? it.qdrant_score ?? 0}</div>
                  {formattedDate && (
                    <div className="absolute bottom-2 right-2 text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-700 border border-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:border-gray-600">
                      {formattedDate}
                    </div>
                  )}
                </div>
              </a>
            );
          })}
          </div>
        </div>
      </div>
    </main>
  );
}


