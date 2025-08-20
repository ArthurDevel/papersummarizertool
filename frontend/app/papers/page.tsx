"use client";

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import type { MinimalPaperItem } from '../../types/paper';
import { listMinimalPapers } from '../../services/api';

export default function AllPapersPage() {
  const [items, setItems] = useState<MinimalPaperItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    (async () => {
      try {
        setIsLoading(true);
        setError(null);
        const enriched: MinimalPaperItem[] = await listMinimalPapers();
        if (isMounted) setItems(enriched);
      } catch (e) {
        if (isMounted) setError(e instanceof Error ? e.message : 'Unknown error');
      } finally {
        if (isMounted) setIsLoading(false);
      }
    })();
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <main className="w-full">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-3xl font-bold">All Papers</h1>
          <Link
            href="/requestpaper"
            className="px-4 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700"
          >
            Request a paper
          </Link>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">Listing contents of <span className="font-mono">data/paperjsons/</span>.</p>

        {error && (
          <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="text-gray-600 dark:text-gray-300">Loading…</div>
        ) : items.length === 0 ? (
          <div className="text-gray-600 dark:text-gray-300">No papers found. Add JSON files to <span className="font-mono">data/paperjsons/</span>.</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map(({ paper_uuid, title, authors, thumbnail_data_url, slug }) => (
              <Link key={paper_uuid} href={slug ? `/paper/${encodeURIComponent(slug)}` : '#'} className={`group ${slug ? '' : 'pointer-events-none opacity-60'}`}>
                <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden shadow-sm h-full">
                  <div className="w-full aspect-square bg-gray-100 dark:bg-gray-700 flex items-center justify-center overflow-hidden">
                    {thumbnail_data_url ? (
                      <img src={thumbnail_data_url} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <div className="text-gray-400 text-sm">No thumbnail</div>
                    )}
                  </div>
                  <div className="p-3">
                    <div className="font-semibold text-gray-900 dark:text-gray-100 group-hover:underline break-words line-clamp-3">{title || paper_uuid + '.json'}</div>
                    {authors && (
                      <div className="text-xs text-gray-600 dark:text-gray-400 mt-1 break-words line-clamp-3">{authors}</div>
                    )}
                    {!slug && (
                      <div className="text-xs text-gray-400 mt-2">No slug yet</div>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}


