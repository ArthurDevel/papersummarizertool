"use client";

import React, { useEffect, useMemo, useState } from 'react';
import { searchPapers, type SearchQueryResponse, type SearchItem } from '../../services/api';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [isNew, setIsNew] = useState(true);
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [selectedCategories, setSelectedCategories] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<SearchItem[]>([]);
  const [meta, setMeta] = useState<Pick<SearchQueryResponse, 'rewritten_query' | 'applied_categories' | 'applied_date_from' | 'applied_date_to'> | null>(null);

  const selectedCategoriesArray = useMemo(
    () => (selectedCategories || '').split(',').map(s => s.trim()).filter(Boolean),
    [selectedCategories]
  );

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    setResults([]);
    setMeta(null);
    try {
      const payload = {
        query: query.trim(),
        is_new: !!isNew,
        selected_categories: selectedCategoriesArray.length ? selectedCategoriesArray : undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        limit: 20,
      };
      const res = await searchPapers(payload);
      setResults(res.items || []);
      setMeta({
        rewritten_query: res.rewritten_query,
        applied_categories: res.applied_categories,
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
        <h1 className="text-3xl font-bold mb-4">Search papers</h1>
        <form onSubmit={onSubmit} className="space-y-3 mb-6">
          <div>
            <label className="block text-sm font-medium mb-1">Query</label>
            <input value={query} onChange={(e) => setQuery(e.target.value)} className="w-full border rounded px-3 py-2 bg-white dark:bg-gray-800" placeholder="e.g. recent papers in vector search for RAG" />
          </div>
          <div className="flex gap-4 flex-wrap">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={isNew} onChange={(e) => setIsNew(e.target.checked)} />
              Treat as new query (let the model suggest categories/date)
            </label>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Categories (comma-separated)</label>
              <input value={selectedCategories} onChange={(e) => setSelectedCategories(e.target.value)} className="w-full border rounded px-3 py-2 bg-white dark:bg-gray-800" placeholder="e.g. cs.IR, cs.CL" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1">Date from (YYYY-MM-DD)</label>
                <input value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-full border rounded px-3 py-2 bg-white dark:bg-gray-800" placeholder="2024-08-01" />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Date to (YYYY-MM-DD)</label>
                <input value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-full border rounded px-3 py-2 bg-white dark:bg-gray-800" placeholder="2025-08-21" />
              </div>
            </div>
          </div>
          <button type="submit" className="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50" disabled={isLoading || !query.trim()}>
            {isLoading ? 'Searching…' : 'Search'}
          </button>
        </form>

        {error && (
          <div className="mb-4 p-3 rounded border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">{error}</div>
        )}

        {meta && (
          <div className="mb-6 text-sm text-gray-600 dark:text-gray-300">
            {meta.rewritten_query && (
              <div><span className="font-semibold">Rewritten query:</span> {meta.rewritten_query}</div>
            )}
            {(meta.applied_categories && meta.applied_categories.length > 0) && (
              <div><span className="font-semibold">Categories:</span> {meta.applied_categories.join(', ')}</div>
            )}
            {(meta.applied_date_from || meta.applied_date_to) && (
              <div><span className="font-semibold">Date range:</span> {meta.applied_date_from || '…'} → {meta.applied_date_to || '…'}</div>
            )}
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {results.map((it) => (
            <a key={it.paper_uuid} href={it.slug ? `/paper/${encodeURIComponent(it.slug)}` : '#'} className={`group block border rounded bg-white dark:bg-gray-800 ${it.slug ? '' : 'pointer-events-none opacity-60'}`}>
              <div className="p-3">
                <div className="font-semibold text-gray-900 dark:text-gray-100 group-hover:underline break-words line-clamp-3">{it.title || it.paper_uuid}</div>
                {it.authors && (
                  <div className="text-xs text-gray-600 dark:text-gray-400 mt-1 break-words line-clamp-3">{it.authors}</div>
                )}
                <div className="text-[11px] text-gray-400 mt-2">score: {it.rerank_score ?? it.qdrant_score ?? 0}</div>
              </div>
            </a>
          ))}
        </div>
      </div>
    </main>
  );
}


