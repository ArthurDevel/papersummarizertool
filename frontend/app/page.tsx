"use client";

import { useEffect, useState, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { Paper, Section, Figure, Table } from '../types/paper';
import { Loader } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

// Minimal approach: convert backticked segments that look like TeX into $...$
const preprocessBacktickedMath = (src: string): string => {
  const looksMath = (s: string) => /[{}_^\\]|\\[a-zA-Z]+/.test(s);
  return (src || '').replace(/`([^`]+)`/g, (m, inner) => (looksMath(inner) ? `$${inner}$` : m));
};

export default function LayoutTestsPage() {
  const searchParams = useSearchParams();
  const [paperData, setPaperData] = useState<Paper | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [availableFiles, setAvailableFiles] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const mainRef = useRef<HTMLDivElement | null>(null);
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
    const fileParam = searchParams?.get('file');
    fetchIndexAndMaybeData(fileParam);
    return () => abortRef.current?.abort();
  }, [searchParams]);

  useEffect(() => {
    if (!paperData) return;
    const container = mainRef.current;
    if (!container) return;

    const computeActive = () => {
      const anchorY = 72; // approx navbar + padding
      let bestId: string | null = null;
      let bestDelta = Number.POSITIVE_INFINITY;
      paperData.sections.forEach((_, idx) => {
        const id = `sec-${idx}`;
        const el = sectionRefs.current[id];
        if (!el) return;
        const delta = Math.abs(el.getBoundingClientRect().top - anchorY);
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

  

  const renderRewrittenSectionContent = (section: Section) => (
    <div key={section.section_title} className="prose dark:prose-invert max-w-none mb-6 last:mb-0">
      {!section.rewritten_content && section.level === 1 && (
        <h4 className="font-semibold">{section.section_title} (p. {section.start_page}-{section.end_page})</h4>
      )}
      {section.rewritten_content && (
        <div className="mt-2">
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
          >
            {preprocessBacktickedMath(section.rewritten_content || '')}
          </ReactMarkdown>
        </div>
      )}
    </div>
  );

  const assetBelongsToSection = (
    startPage: number,
    endPage: number,
    locationPage: number,
    referencedOnPages: number[]
  ) => {
    const inRange = (p: number) => p >= startPage && p <= endPage;
    if (inRange(locationPage)) return true;
    if (Array.isArray(referencedOnPages)) {
      return referencedOnPages.some((p) => inRange(p));
    }
    return false;
  };

  const getAssetsForSection = (section: Section, figures: Figure[], tables: Table[]) => {
    const sectStart = section.start_page ?? Number.MIN_SAFE_INTEGER;
    const sectEnd = section.end_page ?? Number.MAX_SAFE_INTEGER;
    const sectionFigures = (figures || []).filter((f) =>
      assetBelongsToSection(sectStart, sectEnd, f.location_page, f.referenced_on_pages)
    );
    const sectionTables = (tables || []).filter((t) =>
      assetBelongsToSection(sectStart, sectEnd, t.location_page, t.referenced_on_pages)
    );
    const byPageThenId = <T extends { location_page: number; [k: string]: any }>(a: T, b: T) => {
      if (a.location_page !== b.location_page) return a.location_page - b.location_page;
      const aId = (a.figure_identifier || a.table_identifier || '').toString();
      const bId = (b.figure_identifier || b.table_identifier || '').toString();
      return aId.localeCompare(bId);
    };
    sectionFigures.sort(byPageThenId);
    sectionTables.sort(byPageThenId);
    return { sectionFigures, sectionTables };
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
    <div className="flex items-start gap-4 p-4 min-h-0 text-gray-900 dark:text-gray-100">
      {/* Left Sidebar: Sections */}
      <div className="w-64 flex-shrink-0 sticky top-0 self-start pt-4 pb-4">
        <div
          className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden"
          style={{ height: `calc(100vh - ${footerOverlap}px - 2rem)` }}
        >
          <div className="h-full overflow-y-auto p-4">
              <h2 className="text-xl font-semibold mb-4">Sections</h2>
              {paperData ? (
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
              ) : (
                <div className="text-sm text-gray-500 dark:text-gray-400">Loading sections…</div>
              )}
          </div>
        </div>
      </div>

      {/* Content */}
      <main ref={mainRef} className="flex-1 p-4 flex flex-col">
        {paperData ? (
          <>
            <div className="mb-4 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-4">
              <h1 className="text-3xl font-bold mb-2">{paperData.title}</h1>
              <p className="text-sm text-gray-500 dark:text-gray-400">Paper ID: {paperData.paper_id}</p>
            </div>

            <div className="flex flex-col space-y-6 flex-grow">
              {paperData.sections.map((section: Section, idx: number) => {
                const sectionId = `sec-${idx}`;
                const { sectionFigures, sectionTables } = getAssetsForSection(
                  section,
                  paperData.figures || [],
                  paperData.tables || []
                );

                return (
                  <div
                    key={section.section_title + '-' + idx}
                    ref={(el) => { sectionRefs.current[sectionId] = el; }}
                    className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-4"
                  >
                    {renderRewrittenSectionContent(section)}

                    {(sectionFigures.length > 0 || sectionTables.length > 0) && (
                      <div className="mt-6 space-y-6">
                        {sectionFigures.length > 0 && (
                          <div className="space-y-3">
                            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Figures</h4>
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                              {sectionFigures.map((figure: Figure, fIdx: number) => {
                                const cardKey = `${figure.figure_identifier}-${figure.location_page}-${fIdx}`;
                                const raw = figure.explanation || '';
                                const MAX_PREVIEW_CHARS = 300;
                                const isTruncated = raw.length > MAX_PREVIEW_CHARS;
                                const preview = isTruncated ? (raw.slice(0, MAX_PREVIEW_CHARS).trimEnd() + '…') : raw;
                                return (
                                <div key={cardKey} className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 border border-gray-200 dark:border-gray-700 flex flex-col">
                                  <div className="bg-gray-200 dark:bg-gray-600 h-48 rounded-md mb-4 flex items-center justify-center overflow-hidden">
                                    {figure.image_data_url ? (
                                      <img
                                        src={figure.image_data_url}
                                        alt={figure.figure_identifier}
                                        className="object-contain h-48 w-full cursor-zoom-in"
                                        onClick={() => openAssetModal({ kind: 'figure', data: figure })}
                                      />
                                    ) : (
                                      <span className="text-gray-500 dark:text-gray-400 text-center p-2">{figure.figure_identifier}</span>
                                    )}
                                  </div>
                                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">p. {figure.location_page}</p>
                                  <div className="relative">
                                    <div
                                      className="prose dark:prose-invert max-w-none text-sm cursor-pointer"
                                      onClick={() => openAssetModal({ kind: 'figure', data: figure })}
                                    >
                                      <ReactMarkdown
                                        remarkPlugins={[remarkGfm, remarkMath]}
                                        rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
                                      >
                                        {preprocessBacktickedMath(preview)}
                                      </ReactMarkdown>
                                    </div>
                                    {isTruncated && (
                                      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-white dark:from-gray-900 to-transparent" />
                                    )}
                                  </div>
                                </div>
                              );})}
                            </div>
                          </div>
                        )}

                        {sectionTables.length > 0 && (
                          <div className="space-y-3">
                            <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Tables</h4>
                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                              {sectionTables.map((table: Table, tIdx: number) => {
                                const cardKey = `${table.table_identifier}-${table.location_page}-${tIdx}`;
                                const raw = table.explanation || '';
                                const MAX_PREVIEW_CHARS = 300;
                                const isTruncated = raw.length > MAX_PREVIEW_CHARS;
                                const preview = isTruncated ? (raw.slice(0, MAX_PREVIEW_CHARS).trimEnd() + '…') : raw;
                                return (
                                <div key={cardKey} className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 border border-gray-200 dark:border-gray-700 flex flex-col">
                                  <div className="bg-gray-200 dark:bg-gray-600 h-48 rounded-md mb-4 flex items-center justify-center overflow-hidden">
                                    {table.image_data_url ? (
                                      <img
                                        src={table.image_data_url}
                                        alt={table.table_identifier}
                                        className="object-contain h-48 w-full cursor-zoom-in"
                                        onClick={() => openAssetModal({ kind: 'table', data: table })}
                                      />
                                    ) : (
                                      <span className="text-gray-500 dark:text-gray-400 text-center p-2">{table.table_identifier}</span>
                                    )}
                                  </div>
                                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">p. {table.location_page}</p>
                                  <div className="relative">
                                    <div
                                      className="prose dark:prose-invert max-w-none text-sm cursor-pointer"
                                      onClick={() => openAssetModal({ kind: 'table', data: table })}
                                    >
                                      <ReactMarkdown
                                        remarkPlugins={[remarkGfm, remarkMath]}
                                        rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
                                      >
                                        {preprocessBacktickedMath(preview)}
                                      </ReactMarkdown>
                                    </div>
                                    {isTruncated && (
                                      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-8 bg-gradient-to-t from-white dark:from-gray-900 to-transparent" />
                                    )}
                                  </div>
                                </div>
                              );})}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-400">
            {isLoading ? (
              <div className="flex flex-col items-center">
                <Loader className="animate-spin w-10 h-10 mb-3" />
                <p>Loading JSON...</p>
              </div>
            ) : (
              <p>No data loaded.</p>
            )}
          </div>
        )}
    </main>

      {/* Right Sidebar: Similar Papers */}
      <div className="w-64 flex-shrink-0 sticky top-0 self-start pt-4 pb-4">
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
                {availableFiles
                  .filter((f) => f !== (selectedFile ?? ''))
                  .map((name) => (
                    <li key={name}>
                      <button
                        onClick={() => fetchIndexAndMaybeData(name)}
                        className="w-full text-left px-3 py-2 rounded-md text-sm transition-colors bg-white dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-200"
                        title={`Open ${name}`}
                        aria-label={`Open ${name}`}
                      >
                        <div className="flex items-start gap-3">
                          <div className="w-16 h-12 bg-gray-200 dark:bg-gray-600 rounded-md flex-shrink-0" />
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{name}</div>
                            <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">Author A, Author B</div>
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              <span className="text-[10px] px-2 py-0.5 rounded bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-200">badge</span>
                              <span className="text-[10px] px-2 py-0.5 rounded bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-200">badge</span>
                              <span className="text-[10px] px-2 py-0.5 rounded bg-gray-100 text-gray-700 dark:bg-gray-600 dark:text-gray-200">badge</span>
                            </div>
                          </div>
                        </div>
                      </button>
                    </li>
                  ))}
              </ul>
              {availableFiles.filter((f) => f !== (selectedFile ?? '')).length === 0 && (
                <p className="text-sm text-gray-500 dark:text-gray-400">No other preloaded papers found. Add more JSON files to <span className="font-mono">data/paperjsons/</span>.</p>
              )}
          </div>
        </div>
      </div>
      {isModalOpen && paperData && modalData && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" onClick={closeModal}>
          <div className="bg-white dark:bg-gray-900 w-full max-w-6xl h-[80vh] rounded-lg overflow-hidden shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex h-full">
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
              <div className="w-[28rem] border-l border-gray-200 dark:border-gray-700 p-4 flex flex-col">
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


