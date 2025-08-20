"use client";

import React, { useEffect, useState } from 'react';
import Link from 'next/link';

export default function AllPapersPage() {
  const [items, setItems] = useState<Array<{ name: string; title: string | null; authors: string | null; thumbnail_data_url: string | null; slug: string | null }>>([]);
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
        // Enrich each file entry with title/authors/thumbnail from its JSON (best effort)
        const enriched = await Promise.all(
          files.map(async (name: string) => {
            try {
              const detailRes = await fetch(`/layouttests/data?file=${encodeURIComponent(name)}`, { cache: 'no-store' });
              if (!detailRes.ok) throw new Error('detail fetch failed');
              const json = await detailRes.json();
              const title = typeof json?.title === 'string' ? json.title : null;
              const authors = typeof json?.authors === 'string' ? json.authors : null;
              const thumb = typeof json?.thumbnail_data_url === 'string' ? json.thumbnail_data_url : null;
              // Resolve slug for this paper by UUID (filename without .json)
              let slug: string | null = null;
              try {
                const uuid = name.replace(/\.json$/i, '');
                const slugRes = await fetch(`/api/papers/${encodeURIComponent(uuid)}/slug`, { cache: 'no-store' });
                if (slugRes.ok) {
                  const payload = await slugRes.json();
                  if (typeof payload?.slug === 'string') slug = payload.slug;
                }
              } catch {}
              return { name, title, authors, thumbnail_data_url: thumb, slug } as { name: string; title: string | null; authors: string | null; thumbnail_data_url: string | null; slug: string | null };
            } catch {
              return { name, title: null, authors: null, thumbnail_data_url: null, slug: null } as { name: string; title: string | null; authors: string | null; thumbnail_data_url: string | null; slug: string | null };
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
            {items.map(({ name, title, authors, thumbnail_data_url, slug }) => (
              <Link key={name} href={slug ? `/paper/${encodeURIComponent(slug)}` : '#'} className={`group ${slug ? '' : 'pointer-events-none opacity-60'}`}>
                <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden shadow-sm h-full">
                  <div className="w-full aspect-square bg-gray-100 dark:bg-gray-700 flex items-center justify-center overflow-hidden">
                    {thumbnail_data_url ? (
                      <img src={thumbnail_data_url} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <div className="text-gray-400 text-sm">No thumbnail</div>
                    )}
                  </div>
                  <div className="p-3">
                    <div className="font-semibold text-gray-900 dark:text-gray-100 group-hover:underline break-words line-clamp-3">{title || name}</div>
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


