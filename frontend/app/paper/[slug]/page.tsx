"use client";

import { useEffect, useState, useRef } from 'react';
import { useParams } from 'next/navigation';
import { Paper, Section, Figure, Table, type MinimalPaperItem } from '../../../types/paper';
import { listMinimalPapers } from '../../../services/api';
import { authClient } from '../../../services/auth';
import { isPaperInUserList } from '../../../services/users';
import AddToListButton from '../../../components/AddToListButton';
import { Loader, ExternalLink } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import React from 'react';

// Minimal approach: convert backticked segments that look like TeX into $...$
const preprocessBacktickedMath = (src: string): string => {
  const looksMath = (s: string) => /[{}_^\\]|\\[a-zA-Z]+/.test(s);
  return (src || '').replace(/`([^`]+)`/g, (m, inner) => (looksMath(inner) ? `$${inner}$` : m));
};

export default function LayoutTestsPage() {
  const params = useParams<{ slug: string }>();
  const [paperData, setPaperData] = useState<Paper | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const { data: session } = authClient.useSession();
  const [isInList, setIsInList] = useState<boolean>(false);
  const [checkInListPending, setCheckInListPending] = useState<boolean>(false);
  
  const [availableFiles, setAvailableFiles] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [similarItems, setSimilarItems] = useState<Array<{ key: string; title: string | null; authors: string | null; thumbnail_data_url: string | null; slug: string | null }>>([]);
  const abortRef = useRef<AbortController | null>(null);
  const mainRef = useRef<HTMLDivElement | null>(null);
  const summaryRef = useRef<HTMLDivElement | null>(null);
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});
  const [activeSectionId, setActiveSectionId] = useState<string | null>(null);
  const [footerOverlap, setFooterOverlap] = useState<number>(0);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [modalData, setModalData] = useState<
    | { kind: 'figure'; data: Figure }
    | { kind: 'table'; data: Table }
    | null
  >(null);
  const pageImageContainerRef = useRef<HTMLDivElement | null>(null);
  const pageImageRef = useRef<HTMLImageElement | null>(null);
  const [modalZoom, setModalZoom] = useState<number>(1);
  const [readingMinutes, setReadingMinutes] = useState<number | null>(null);

  const fetchIndexAndMaybeData = async (explicitFile?: string | null) => {
    try {
      setIsLoading(true);
      setError(null);
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const indexRes = await fetch('/layouttests/data', { signal: controller.signal, cache: 'no-store' });
      if (!indexRes.ok) throw new Error(`Failed to list preloaded papers: ${indexRes.status}`);
      const indexJson = await indexRes.json();
      const files: string[] = Array.isArray(indexJson?.files) ? indexJson.files : [];
      setAvailableFiles(files);
      const fileToLoad = explicitFile ?? selectedFile ?? files[0] ?? null;
      if (!fileToLoad) throw new Error('No papers found in data/paperjsons/');
      setSelectedFile(fileToLoad);
      const response = await fetch(`/layouttests/data?file=${encodeURIComponent(fileToLoad)}`, { signal: controller.signal, cache: 'no-store' });
      if (!response.ok) {
        throw new Error(`Failed to load JSON: ${response.status} ${response.statusText}`);
      }
      const data: Paper = await response.json();
      setPaperData(data);
    } catch (err) {
      if ((err as any)?.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : 'Unknown error loading JSON');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const slug = params?.slug || '';
    let cancelled = false;
    (async () => {
      try {
        if (!slug) throw new Error('Missing slug');
        // Resolve slug to paper_uuid
        const res = await fetch(`/api/papers/slug/${encodeURIComponent(slug)}`, { cache: 'no-store' });
        if (res.status === 404) {
          window.location.replace('/404');
          return;
        }
        if (!res.ok) {
          const text = await res.text().catch(() => '');
          throw new Error(`Resolve failed (${res.status}) ${text}`);
        }
        const json = await res.json();
        if (json?.tombstone) {
          window.location.replace('/410');
          return;
        }
        const uuid: string | undefined = json?.paper_uuid;
        if (!uuid) throw new Error('Paper not found');
        if (!cancelled) {
          setIsLoading(true);
          await fetchIndexAndMaybeData(`${uuid}.json`);
          setIsLoading(false);
        }
      } catch (e: any) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Unknown error');
      }
    })();
    return () => {
      abortRef.current?.abort();
      cancelled = true;
    };
  }, [params]);

  // Compute estimated reading time (~200 words/min) based on rewritten section content
  useEffect(() => {
    if (!paperData) {
      setReadingMinutes(null);
      return;
    }
    try {
      const texts = (paperData.sections || []).map((s: any) => (s?.rewritten_content || ''));
      const combined = texts.filter(Boolean).join(' ');
      const words = (combined.match(/[^\s]+/g) || []).length;
      const minutes = Math.max(1, Math.round(words / 200));
      setReadingMinutes(minutes);
    } catch {
      setReadingMinutes(null);
    }
  }, [paperData]);

  // Log paper id instead of displaying it
  useEffect(() => {
    if (paperData?.paper_id) {
      try { console.log('[paper] id', paperData.paper_id); } catch {}
    }
  }, [paperData?.paper_id]);

  // If logged in and paper is loaded, check if it's already in user's list
  useEffect(() => {
    const run = async () => {
      if (!session?.user?.id || !paperData?.paper_id) return;
      try {
        setCheckInListPending(true);
        const exists = await isPaperInUserList(paperData.paper_id, session.user.id);
        setIsInList(Boolean(exists));
      } catch {
        // ignore
      } finally {
        setCheckInListPending(false);
      }
    };
    run();
  }, [session?.user?.id, paperData?.paper_id]);

  

  // Load metadata for similar papers (title/authors/thumbnail) via minimal endpoint
  useEffect(() => {
    const others = availableFiles.filter((f) => f !== (selectedFile ?? ''));
    if (others.length === 0) {
      setSimilarItems([]);
      return;
    }
    (async () => {
      try {
        const all: MinimalPaperItem[] = await listMinimalPapers();
        const othersByUuid = new Set(others.map((n) => n.replace(/\.json$/i, '')));
        const results = all
          .filter((it) => othersByUuid.has(it.paper_uuid))
          .map((it) => ({ key: it.paper_uuid, title: it.title, authors: it.authors, thumbnail_data_url: it.thumbnail_data_url, slug: it.slug }));
        setSimilarItems(results);
      } catch {
        setSimilarItems([]);
      }
    })();
  }, [availableFiles, selectedFile]);

  useEffect(() => {
    if (!paperData) return;
    const container = mainRef.current;
    if (!container) return;

    const computeActive = () => {
      const anchorY = 72; // approx navbar + padding
      let bestId: string | null = null;
      let bestDelta = Number.POSITIVE_INFINITY;

      const allCheckableSections = [
        { id: 'sec-summary', element: summaryRef.current },
        ...paperData.sections.map((_, idx) => ({ id: `sec-${idx}`, element: sectionRefs.current[`sec-${idx}`] })),
      ];

      allCheckableSections.forEach(({ id, element }) => {
        if (!element) return;
        const delta = Math.abs(element.getBoundingClientRect().top - anchorY);
        if (delta < bestDelta) {
          bestDelta = delta;
          bestId = id;
        }
      });

      if (bestId && bestId !== activeSectionId) setActiveSectionId(bestId);
    };

    const computeFooter = () => {
      const footerEl = document.getElementById('site-footer');
      if (!footerEl) {
        if (footerOverlap !== 0) setFooterOverlap(0);
        return;
      }
      const rect = footerEl.getBoundingClientRect();
      const vh = window.innerHeight || 0;
      const overlap = Math.max(0, vh - Math.max(rect.top, 0));
      const clamped = Math.min(overlap, vh);
      if (clamped !== footerOverlap) setFooterOverlap(clamped);
    };

    computeActive();
    computeFooter();
    let raf = 0 as number | 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0 as number | 0;
        computeActive();
        computeFooter();
      }) as unknown as number;
    };
    window.addEventListener('scroll', onScroll, { passive: true } as any);
    window.addEventListener('resize', onScroll, { passive: true } as any);
    return () => {
      window.removeEventListener('scroll', onScroll as any);
      window.removeEventListener('resize', onScroll as any);
      if (raf) cancelAnimationFrame(raf as unknown as number);
    };
  }, [paperData, activeSectionId]);

  

  // Note: processInlineImages function removed - backend now generates proper markdown images
  // Images now come as: ![Figure shortid](shortid:weu33j4l)
  // Future: Backend can add descriptions like: ![Figure shortid](shortid:weu33j4l "Custom description")

  const renderRewrittenSectionContent = (section: Section) => {
    const figures = paperData?.figures || [];
    
    return (
      <>
        {!section.rewritten_content && section.level === 1 && (
          <h4 className="font-semibold">{section.section_title} (p. {section.start_page}-{section.end_page})</h4>
        )}
        {section.rewritten_content && (
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
              urlTransform={(url) => {
                // Allow our custom shortid: scheme to pass through
                if (url.startsWith('shortid:')) {
                  return url;
                }
                // Use default transformation for other URLs
                return url;
              }}
              components={{
                img: ({ src, alt, title, ...props }) => {
                  // Handle shortid: URLs from backend
                  if (src?.startsWith('shortid:')) {
                    const shortId = src.replace('shortid:', '');
                    const figure = figures.find(f => f.short_id === shortId);
                    
                    if (!figure) {
                      return <span className="text-red-500">[Image {shortId} not found]</span>;
                    }
                    
                    // Use title as description, alt as fallback
                    const description = title || alt || figure.explanation || `Figure ${shortId}`;
                    
                    return (
                      <img
                        src={figure.image_data_url}
                        alt={description}
                        title={description}
                        className="inline-block max-w-full h-auto my-2 mx-auto border border-gray-300 rounded shadow-sm cursor-pointer"
                        onClick={() => {
                          setModalData({ kind: 'figure', data: figure });
                          setIsModalOpen(true);
                        }}
                      />
                    );
                  }
                  
                  // Handle regular images - filter out React node props
                  const { node, children, ...safeProps } = props;
                  return (
                    <img
                      src={src}
                      alt={alt}
                      title={title}
                      {...safeProps}
                      className="inline-block max-w-full h-auto my-2 mx-auto border border-gray-300 rounded shadow-sm cursor-pointer"
                      onClick={() => {
                        // Find figure by src to open modal
                        const figure = figures.find(f => f.image_data_url === src);
                        if (figure) {
                          setModalData({ kind: 'figure', data: figure });
                          setIsModalOpen(true);
                        }
                      }}
                    />
                  );
                },
              }}
            >
              {preprocessBacktickedMath(section.rewritten_content || '')}
            </ReactMarkdown>
        )}
      </>
    );
  };


  useEffect(() => {
    if (!isModalOpen || !paperData || !modalData) return;
    const pageNum = modalData.data.location_page;
    const rawBbox: any = (modalData.data as any).bounding_box;
    const bbox: [number, number, number, number] =
      Array.isArray(rawBbox) && rawBbox.length === 4 && rawBbox.every((n: any) => typeof n === 'number')
        ? (rawBbox as [number, number, number, number])
        : [0, 0, 0, 0];
    try {
      console.log('[modal] effect init', {
        pageNum,
        bbox,
        pagesCount: paperData.pages?.length ?? 0,
      });
    } catch {}
    // After image loads, scroll container to center bbox
    const imgEl = pageImageRef.current;
    const container = pageImageContainerRef.current;
    if (!imgEl || !container) return;
    const onLoad = () => {
      const [x1, y1, x2, y2] = bbox;
      const bboxW = Math.max(1, x2 - x1);
      const bboxH = Math.max(1, y2 - y1);
      const hasValidBbox = (x2 > x1) && (y2 > y1);
      if (!hasValidBbox) {
        console.warn('[modal] invalid or empty bbox, skipping auto-zoom', { x1, y1, x2, y2 });
        setModalZoom(1);
        return;
      }
      // Compute zoom so bbox fits within ~70% of container
      const targetW = container.clientWidth * 0.7;
      const targetH = container.clientHeight * 0.7;
      const scale = Math.max(1, Math.min(targetW / bboxW, targetH / bboxH));
      setModalZoom(scale);
      const centerX = (x1 + x2) / 2 * scale;
      const centerY = (y1 + y2) / 2 * scale;
      try {
        console.log('[modal] image onLoad', {
          imgComplete: imgEl.complete,
          containerSize: { w: container.clientWidth, h: container.clientHeight },
          bbox: { x1, y1, x2, y2, w: bboxW, h: bboxH },
          scale,
          scrollTarget: { left: Math.max(0, centerX - container.clientWidth / 2), top: Math.max(0, centerY - container.clientHeight / 2) },
        });
      } catch {}
      container.scrollTo({
        left: Math.max(0, centerX - container.clientWidth / 2),
        top: Math.max(0, centerY - container.clientHeight / 2),
        behavior: 'smooth',
      });
    };
    try {
      console.log('[modal] before load handler', {
        imgComplete: imgEl.complete,
        naturalSize: { w: (imgEl as any).naturalWidth, h: (imgEl as any).naturalHeight },
        containerSize: { w: container.clientWidth, h: container.clientHeight },
      });
    } catch {}
    if (imgEl.complete) onLoad();
    else imgEl.addEventListener('load', onLoad, { once: true });
    return () => imgEl.removeEventListener('load', onLoad as any);
  }, [isModalOpen, modalData, paperData]);

  const openAssetModal = (payload: { kind: 'figure'; data: Figure } | { kind: 'table'; data: Table }) => {
    try {
      console.log('[modal] open', {
        kind: payload.kind,
        id:
          payload.kind === 'figure'
            ? (payload.data as Figure).figure_identifier
            : (payload.data as Table).table_identifier,
        page: payload.data.location_page,
        bbox: (payload.data as any)?.bounding_box,
        pageImageSize: (payload.data as any)?.page_image_size,
      });
    } catch (e) {
      console.warn('[modal] open log error', e);
    }
    setModalData(payload);
    setIsModalOpen(true);
  };
  const closeModal = () => {
    console.log('[modal] close');
    setIsModalOpen(false);
    setModalData(null);
    setModalZoom(1);
  };

  return (
    <div className="flex items-start gap-4 p-2 sm:p-4 min-h-0 text-gray-900 dark:text-gray-100">
      {/* Left Sidebar: Sections - Hidden on mobile */}
      <div className="hidden lg:block w-64 flex-shrink-0 sticky top-0 self-start pt-4 pb-4">
        <div
          className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden"
          style={{ height: `calc(100vh - ${footerOverlap}px - 2rem)` }}
        >
          <div className="h-full overflow-y-auto p-4">
              {paperData ? (
                <>
                  {paperData.five_minute_summary && (
                    <div className="mb-6">
                      <h2 className="text-lg font-semibold mb-2 text-gray-800 dark:text-gray-200">5-Minute Summary</h2>
                      <div className="border-b border-gray-200 dark:border-gray-700 mb-2"></div>
                      <ul className="space-y-1">
                        <li>
                          <button
                            className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${
                              activeSectionId === 'sec-summary' ? 'bg-blue-600 text-white' : 'bg-white dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-200'
                            }`}
                            onClick={() => {
                              summaryRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                              setActiveSectionId('sec-summary');
                            }}
                            title="Go to 5-Minute Summary"
                          >
                            Summary
                          </button>
                        </li>
                      </ul>
                    </div>
                  )}

                  <div>
                    <h2 className="text-lg font-semibold mb-2 text-gray-800 dark:text-gray-200">Simplified Version</h2>
                    <div className="border-b border-gray-200 dark:border-gray-700 mb-2"></div>
                    <ul className="space-y-1">
                      {paperData.sections.map((section: Section, idx: number) => {
                        const id = `sec-${idx}`;
                        const isActive = activeSectionId === id;
                        return (
                          <li key={id}>
                            <button
                              className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${
                                isActive ? 'bg-blue-600 text-white' : 'bg-white dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-200'
                              }`}
                              onClick={() => {
                                const el = sectionRefs.current[id];
                                el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                                setActiveSectionId(id);
                              }}
                              title={`Go to ${section.section_title}`}
                            >
                              <span className="mr-2 font-semibold">{idx + 1}.</span>
                              <span>{section.section_title || `Section ${idx + 1}`}</span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                </>
              ) : (
                <div className="text-sm text-gray-500 dark:text-gray-400">Loading sections…</div>
              )}
          </div>
        </div>
      </div>

      {/* Content */}
      <main ref={mainRef} className="flex-1 min-w-0 p-2 sm:p-4 flex flex-col">
        {paperData ? (
          <>
            <div className="mb-4 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-3 sm:p-4">
              <div className="flex flex-col sm:flex-row items-start gap-3 sm:gap-4 max-w-full">
                {(paperData as any)?.thumbnail_data_url && (
                  <img
                    src={(paperData as any).thumbnail_data_url as string}
                    alt="Paper thumbnail"
                    className="w-20 h-20 sm:w-24 sm:h-24 rounded-md object-cover flex-shrink-0 mx-auto sm:mx-0"
                  />
                )}
                <div className="min-w-0 flex-1 overflow-hidden break-words text-center sm:text-left">
                  <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold mb-1 break-words whitespace-normal leading-tight">{paperData.title || 'Untitled'}</h1>
                  {paperData.authors && (
                    <p className="text-sm text-gray-700 dark:text-gray-300 mb-1 break-words whitespace-normal">{paperData.authors}</p>
                  )}
                  {typeof readingMinutes === 'number' && (
                    <p className="text-xs text-gray-500 dark:text-gray-400">📖 {readingMinutes} min read</p>
                  )}
                  
                  {paperData.arxiv_url && (
                    <a
                      href={paperData.arxiv_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2 inline-flex items-center gap-1.5 text-xs text-blue-600 hover:underline"
                      title="Open on arXiv"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      Open on arXiv
                    </a>
                  )}
                  <div className="mt-3 flex items-center gap-3">
                    <AddToListButton paperId={paperData.paper_id} paperTitle={paperData.title || undefined} />
                  </div>
                  
                </div>
              </div>
            </div>

            {/* 5-Minute Summary */}
            {paperData.five_minute_summary && (
              <div ref={summaryRef} className="mb-6 sm:mb-8 bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800 rounded-lg shadow-md overflow-hidden">
                <div className="p-3 sm:p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                    <h2 className="text-lg font-semibold text-blue-900 dark:text-blue-100">
                      5-Minute Summary
                    </h2>
                    <span className="text-xs text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/50 px-2 py-1 rounded-full">
                      ⚡ Quick read
                    </span>
                  </div>
                  <div className="prose dark:prose-invert max-w-none">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkMath]}
                      rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
                    >
                      {preprocessBacktickedMath(paperData.five_minute_summary)}
                    </ReactMarkdown>
                  </div>
                </div>
              </div>
            )}

            {/* Simplified Version */}
            <div className="mb-4 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden">
              <div className="p-3 sm:p-4">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-2 h-2 bg-gray-500 rounded-full"></div>
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                    Simplified Version
                  </h2>
                  {typeof readingMinutes === 'number' && (
                    <span className="text-xs text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded-full">
                      📖 {readingMinutes} min read
                    </span>
                  )}
                </div>
                <div>
                  {paperData.sections.map((section: Section, idx: number) => {
                    const sectionId = `sec-${idx}`;
                    const isLastSection = idx === paperData.sections.length - 1;

                    return (
                      <React.Fragment key={section.section_title + '-' + idx}>
                        <div
                          ref={(el) => {
                            sectionRefs.current[sectionId] = el;
                          }}
                          className="prose dark:prose-invert max-w-none"
                        >
                          {renderRewrittenSectionContent(section)}
                        </div>
                        {!isLastSection && <hr className="my-6" />}
                      </React.Fragment>
                    );
                  })}
                </div>
              </div>
            </div>
          </>
        ) : (
          isLoading ? (
            <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-400">
              <div className="flex flex-col items-center">
                <Loader className="animate-spin w-10 h-10 mb-3" />
                <p>Loading JSON...</p>
              </div>
            </div>
          ) : null
        )}
    </main>

      {/* Right Sidebar: Similar Papers - Hidden on mobile */}
      <div className="hidden lg:block w-64 flex-shrink-0 sticky top-0 self-start pt-4 pb-4">
        <div
          className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden"
          style={{ height: `calc(100vh - ${footerOverlap}px - 2rem)` }}
        >
          <div className="h-full overflow-y-auto p-4">
              <h2 className="text-xl font-semibold mb-4">Similar papers</h2>
              {error && (
                <div className="text-sm mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">
                  {error}
                </div>
              )}
              {isLoading && (
                <div className="flex items-center text-sm text-gray-500 dark:text-gray-400 mb-4">
                  <Loader className="animate-spin w-4 h-4 mr-2" /> Loading list...
                </div>
              )}
              <ul className="space-y-1">
                {similarItems.map(({ key, title, authors, thumbnail_data_url, slug }) => {
                  const target = slug || key;
                  return (
                    <li key={key}>
                      <a
                        href={`/paper/${encodeURIComponent(target)}`}
                        className="block w-full text-left px-3 py-2 rounded-md text-sm transition-colors bg-white dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-200"
                        title={`Open ${title || key}`}
                        aria-label={`Open ${title || key}`}
                      >
                        <div className="flex items-start gap-3">
                          <div className="w-16 h-16 bg-gray-200 dark:bg-gray-600 rounded-md flex-shrink-0 overflow-hidden">
                            {thumbnail_data_url && (
                              <img src={thumbnail_data_url} alt="" className="w-16 h-16 object-cover" />
                            )}
                          </div>
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{title || key + '.json'}</div>
                            {authors && (
                              <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">{authors}</div>
                            )}
                          </div>
                        </div>
                      </a>
                    </li>
                  );
                })}
              </ul>
              {availableFiles.filter((f) => f !== (selectedFile ?? '')).length === 0 && (
                <p className="text-sm text-gray-500 dark:text-gray-400">No other preloaded papers found. Add more JSON files to <span className="font-mono">data/paperjsons/</span>.</p>
              )}
          </div>
        </div>
      </div>

      {/* No sections on mobile: floating TOC button and drawer removed */}

      {isModalOpen && paperData && modalData && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-2 sm:p-4" onClick={closeModal}>
          <div className="bg-white dark:bg-gray-900 w-full max-w-6xl h-[95vh] sm:h-[80vh] rounded-lg overflow-hidden shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex flex-col sm:flex-row h-full">
              {/* Left: Full page image, scrollable, with bbox overlay */}
              <div ref={pageImageContainerRef} className="flex-1 relative overflow-auto bg-gray-100 dark:bg-gray-800">
                {(() => {
                  const pageNum = modalData.data.location_page;
                  const page = (paperData.pages || []).find((p) => p.page_number === pageNum);
                  const [x1, y1, x2, y2] = Array.isArray((modalData.data as any).bounding_box)
                    ? (modalData.data as any).bounding_box as [number, number, number, number]
                    : [0, 0, 0, 0];
                  const hasValidBbox = (x2 > x1) && (y2 > y1);
                  try {
                    console.log('[modal] render', {
                      pageNum,
                      hasPageImage: !!page?.image_data_url,
                      bbox: { x1, y1, x2, y2 },
                      modalZoom,
                    });
                  } catch {}
                  if (!page?.image_data_url) {
                    return (
                      <div className="w-full h-full flex items-center justify-center text-sm text-gray-600 dark:text-gray-300">
                        No page image available for page {pageNum}.
                      </div>
                    );
                  }
                  return (
                    <div className="relative inline-block" style={{ transform: `scale(${modalZoom})`, transformOrigin: 'top left' }}>
                      <img ref={pageImageRef} src={page.image_data_url} alt={`Page ${pageNum}`} className="block max-w-none" />
                      {/* BBox overlay */}
                      {hasValidBbox && (
                        <div
                          className="absolute border-2 border-blue-500/80 bg-blue-500/10 pointer-events-none"
                          style={{ left: x1, top: y1, width: Math.max(0, x2 - x1), height: Math.max(0, y2 - y1) }}
                        />
                      )}
                    </div>
                  );
                })()}
              </div>
              {/* Right: Explanation */}
              <div className="w-full sm:w-[28rem] border-t sm:border-t-0 sm:border-l border-gray-200 dark:border-gray-700 p-4 flex flex-col max-h-[40vh] sm:max-h-none">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="text-lg font-semibold">
                      {modalData.kind === 'figure' ? (modalData.data as Figure).figure_identifier : (modalData.data as Table).table_identifier}
                    </h3>
                    <p className="text-xs text-gray-500 dark:text-gray-400">Page {modalData.data.location_page}</p>
                  </div>
                  <button onClick={closeModal} className="text-sm px-2 py-1 rounded border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800">Close</button>
                </div>
                <div className="flex-1 overflow-auto">
                  <div className="prose dark:prose-invert max-w-none text-sm">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkMath]}
                      rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
                    >
                      {preprocessBacktickedMath(modalData.data.explanation || '')}
                    </ReactMarkdown>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


