"use client";

import { useState, useRef } from 'react';
import { processPaper, getJobStatus } from '../../services/api';
import { Paper, Section, Figure, Table } from '../../types/paper';
import { ChevronDown, Loader, UploadCloud, FileText, Download } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

const preprocessBacktickedMath = (src: string): string => {
  const looksMath = (s: string) => /[{}_^\\]|\\[a-zA-Z]+/.test(s);
  return (src || '').replace(/`([^`]+)`/g, (m, inner) => (looksMath(inner) ? `$${inner}$` : m));
};

export default function QuickTestPage() {
  const [file, setFile] = useState<File | null>(null);
  const [paperData, setPaperData] = useState<Paper | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openSection, setOpenSection] = useState<string | null>(null);

  const pollingInterval = useRef<NodeJS.Timeout | null>(null);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      setFile(event.target.files[0]);
    }
  };
  
  const cleanupPolling = () => {
    if (pollingInterval.current) {
      clearInterval(pollingInterval.current);
      pollingInterval.current = null;
    }
  };

  const pollJobStatus = async (id: string) => {
    try {
      const data = await getJobStatus(id);
      if (data) {
        setPaperData(data);
        setIsLoading(false);
        setJobId(null);
        setError(null);
        setOpenSection("Summary"); // Open the first section by default
        cleanupPolling();
      }
    } catch (err) {
      console.error("Error polling for job status:", err);
      setError(err instanceof Error ? err.message : "An unknown error occurred during polling.");
      setIsLoading(false);
      setJobId(null);
      cleanupPolling();
    }
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file) {
      alert("Please select a file first.");
      return;
    }

    setIsLoading(true);
    setPaperData(null);
    setJobId(null);
    setError(null);
    cleanupPolling();

    try {
      const initialResponse = await processPaper(file);
      setJobId(initialResponse.job_id);
      pollingInterval.current = setInterval(() => {
        pollJobStatus(initialResponse.job_id);
      }, 3000);
    } catch (err) {
      console.error("Error uploading file:", err);
      setError(err instanceof Error ? err.message : "An unknown error occurred.");
      setIsLoading(false);
    }
  };

  const toggleSection = (section: string) => {
    setOpenSection(openSection === section ? null : section);
  };

  const exportPaperAsJson = () => {
    if (!paperData) return;
    const safeTitle = (paperData.title || 'paper')
      .toLowerCase()
      .replace(/[^a-z0-9-_]+/g, '_')
      .slice(0, 80);
    const fileName = `${safeTitle}_${paperData.paper_id || 'export'}.json`;
    const blob = new Blob([JSON.stringify(paperData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };
  
  const formatCurrency = (n?: number) => (typeof n === 'number' ? `$${n.toFixed(4)}` : 'N/A');
  const formatSeconds = (s?: number) => (typeof s === 'number' ? `${s.toFixed(2)}s` : 'N/A');
  
  const renderRewrittenSectionContent = (section: Section) => (
    <div key={section.section_title} className="prose dark:prose-invert max-w-none mb-6 last:mb-0">
      {!section.rewritten_content && section.level === 1 && (
        <h4 className="font-semibold">{section.section_title} (p. {section.start_page}-{section.end_page})</h4>
      )}
      {section.rewritten_content && (
        <div className="mt-2">
          <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}>
            {preprocessBacktickedMath(section.rewritten_content || '')}
          </ReactMarkdown>
        </div>
      )}
      {/* Intentionally do NOT render subsections programmatically. They are included in the rewritten Markdown. */}
    </div>
  );

  const AccordionSection = ({ title, children }: { title: string; children: React.ReactNode }) => {
    const isOpen = openSection === title;
    return (
      <div
        className={`border rounded-lg bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 transition-all duration-300 ease-in-out ${
          isOpen ? "flex-grow flex flex-col" : "flex-shrink-0"
        }`}
      >
        <button
          onClick={() => toggleSection(title)}
          className="w-full text-left p-4 font-semibold flex justify-between items-center"
        >
          <span>{title}</span>
          <ChevronDown
            className={`transform transition-transform duration-200 ${
              isOpen ? "rotate-180" : ""
            }`}
          />
        </button>
        {isOpen && (
          <div className="p-4 border-t border-gray-200 dark:border-gray-700 flex-grow overflow-hidden">
            {children}
          </div>
        )}
      </div>
    );
  };
  
  return (
    <div className="flex h-screen bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
      {/* Sidebar */}
      <aside className="w-1/4 bg-gray-800 text-white p-6 overflow-y-auto">
        <h2 className="text-2xl font-bold mb-6">Paper Upload</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="pdf-upload" className="block text-sm font-medium mb-2">
              Upload PDF
            </label>
            <div className="flex items-center justify-center w-full">
                <label htmlFor="pdf-upload" className="flex flex-col items-center justify-center w-full h-32 border-2 border-gray-500 border-dashed rounded-lg cursor-pointer bg-gray-700 hover:bg-gray-600">
                    <div className="flex flex-col items-center justify-center pt-5 pb-6">
                        <UploadCloud className="w-8 h-8 mb-2 text-gray-400" />
                        <p className="mb-1 text-sm text-gray-400"><span className="font-semibold">Click to upload</span></p>
                        <p className="text-xs text-gray-400">or drag and drop</p>
                    </div>
                    <input id="pdf-upload" type="file" className="hidden" accept="application/pdf" onChange={handleFileChange} />
                </label>
            </div>
          </div>
          {file && (
            <div className="flex items-center space-x-2 text-sm p-2 bg-gray-700 rounded-md">
              <FileText className="w-4 h-4 text-gray-400" />
              <span className="truncate">{file.name}</span>
            </div>
          )}
          <button
            type="submit"
            disabled={!file || isLoading}
            className="w-full px-4 py-2 bg-blue-600 text-white rounded-md disabled:bg-gray-500 disabled:cursor-not-allowed flex items-center justify-center space-x-2 hover:bg-blue-700 transition-colors"
          >
            {isLoading ? (
              <>
                <Loader className="animate-spin w-5 h-5" />
                <span>Processing...</span>
              </>
            ) : (
              <span>Process Paper</span>
            )}
          </button>
        </form>
        {jobId && <p className="text-xs text-center mt-2 text-gray-400">Job ID: {jobId}</p>}
        {error && <div className="mt-4 text-red-400 text-sm bg-red-900/50 p-3 rounded-md">{error}</div>}
      </aside>

      {/* Content */}
      <main className="w-3/4 p-8 flex flex-col overflow-y-auto">
        {paperData ? (
            <>
                <div className="flex items-start justify-between mb-6">
                  <div>
                    <h1 className="text-3xl font-bold mb-2">{paperData.title}</h1>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Paper ID: {paperData.paper_id}</p>
                    {(paperData.usage_summary || typeof paperData.processing_time_seconds === 'number') && (
                      <div className="mt-2 text-xs text-gray-600 dark:text-gray-300 flex flex-wrap gap-3">
                        {paperData.usage_summary && (
                          <>
                            <span className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">
                              <span>Total Cost:</span>
                              <strong>{formatCurrency(paperData.usage_summary.total_cost)}</strong>
                            </span>
                            <span className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">
                              <span>Total Tokens:</span>
                              <strong>{paperData.usage_summary.total_tokens}</strong>
                            </span>
                          </>
                        )}
                        <span className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded">
                          <span>Processing Time:</span>
                          <strong>{formatSeconds(paperData.processing_time_seconds)}</strong>
                        </span>
                      </div>
                    )}
                  </div>
                  <button
                    onClick={exportPaperAsJson}
                    className="inline-flex items-center px-3 py-2 bg-emerald-600 text-white rounded-md hover:bg-emerald-700 transition-colors disabled:bg-gray-500"
                    disabled={isLoading}
                    title="Download JSON export"
                  >
                    <Download className="w-4 h-4 mr-2" />
                    <span>Export JSON</span>
                  </button>
                </div>
                <div className="flex flex-col space-y-2 flex-grow">
                    <AccordionSection title="Abstract">
                        <div className="text-gray-500 dark:text-gray-400 italic">
                            <p>This section is not yet implemented.</p>
                            <p className="mt-2 text-xs">A future update will include a generated abstract of the entire paper here.</p>
                        </div>
                    </AccordionSection>

                    <AccordionSection title="Assets Explained">
                      <div className="flex space-x-4 overflow-x-auto h-full pb-4">
                        {paperData.figures.map((figure: Figure) => (
                          <div key={figure.figure_identifier} className="flex-shrink-0 w-80 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 border border-gray-200 dark:border-gray-700 flex flex-col">
                            <div className="bg-gray-200 dark:bg-gray-600 h-48 rounded-md mb-4 flex items-center justify-center overflow-hidden">
                              {figure.image_data_url ? (
                                <img src={figure.image_data_url} alt={figure.figure_identifier} className="object-contain h-48 w-full" />
                              ) : (
                                <span className="text-gray-500 dark:text-gray-400 text-center p-2">{figure.figure_identifier}</span>
                              )}
                            </div>
                            <p className="text-sm text-gray-800 dark:text-gray-300 whitespace-pre-line">{figure.explanation}</p>
                          </div>
                        ))}
                        {paperData.tables.map((table: Table) => (
                          <div key={table.table_identifier} className="flex-shrink-0 w-80 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 border border-gray-200 dark:border-gray-700 flex flex-col">
                            <div className="bg-gray-200 dark:bg-gray-600 h-48 rounded-md mb-4 flex items-center justify-center overflow-hidden">
                              {table.image_data_url ? (
                                <img src={table.image_data_url} alt={table.table_identifier} className="object-contain h-48 w-full" />
                              ) : (
                                <span className="text-gray-500 dark:text-gray-400 text-center p-2">{table.table_identifier}</span>
                              )}
                            </div>
                            <p className="text-sm text-gray-800 dark:text-gray-300 whitespace-pre-line">{table.explanation}</p>
                          </div>
                        ))}
                      </div>
                    </AccordionSection>

                    <AccordionSection title="Summary">
                      <div className="space-y-6">
                        {paperData.sections.map((section: Section) => (
                          <div key={section.section_title} className="border dark:border-gray-700 rounded-lg p-4">
                            {(() => {
                              const converted = preprocessBacktickedMath(section.rewritten_content || '');
                              return (
                                <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}>
                                  {converted}
                                </ReactMarkdown>
                              );
                            })()}
                          </div>
                        ))}
                      </div>
                    </AccordionSection>
                </div>
            </>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-400">
            {isLoading ? (
              <div className="flex flex-col items-center">
                <Loader className="animate-spin w-10 h-10 mb-3" />
                <p>Processing your document. This may take a few minutes...</p>
              </div>
            ) : (
              <p>Upload a PDF to begin processing.</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
} 