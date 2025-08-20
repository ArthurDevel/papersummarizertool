"use client";

import React, { useEffect, useState } from 'react';
import Link from 'next/link';

export default function AllPapersPage() {
  const [items, setItems] = useState<Array<{ name: string; title: string | null; authors: string | null }>>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    (async () => {
      try {
        setIsLoading(true);
        setError(null);
        const res = await fetch('/layouttests/data', { cache: 'no-store' });
        if (!res.ok) throw new Error(`Failed to load list: ${res.status}`);
        const data = await res.json();
        if (!Array.isArray(data?.files)) throw new Error('Unexpected response');
        const files: string[] = data.files;
        // Enrich each file entry with title/authors from its JSON (best effort)
        const enriched = await Promise.all(
          files.map(async (name: string) => {
            try {
              const detailRes = await fetch(`/layouttests/data?file=${encodeURIComponent(name)}`, { cache: 'no-store' });
              if (!detailRes.ok) throw new Error('detail fetch failed');
              const json = await detailRes.json();
              const title = typeof json?.title === 'string' ? json.title : null;
              const authors = typeof json?.authors === 'string' ? json.authors : null;
              return { name, title, authors } as { name: string; title: string | null; authors: string | null };
            } catch {
              return { name, title: null, authors: null } as { name: string; title: string | null; authors: string | null };
            }
          })
        );
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
        <h1 className="text-3xl font-bold mb-4">All Papers</h1>
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
          <ul className="divide-y divide-gray-200 dark:divide-gray-700 rounded-md overflow-hidden border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
            {items.map(({ name, title, authors }) => (
              <li key={name} className="px-4 py-3 text-gray-800 dark:text-gray-200">
                <Link href={`/?file=${encodeURIComponent(name)}`} className="hover:underline">
                  <div className="flex flex-col">
                    <span className="font-semibold text-blue-600 dark:text-blue-400">{title || name}</span>
                    {authors && (
                      <span className="text-sm text-gray-600 dark:text-gray-400">{authors}</span>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}


