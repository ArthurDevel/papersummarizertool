import React from 'react';

type FooterProps = {
  className?: string;
};

export default function Footer({ className = '' }: FooterProps) {
  return (
    <footer id="site-footer" className={`w-full border-t border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 ${className}`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 text-sm text-gray-600 dark:text-gray-300">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-gray-900 dark:text-gray-100">PaperSummarizer</span>
            <span className="text-gray-400">·</span>
            <span>Open research tools for everyone</span>
          </div>
          <div className="flex items-center gap-4">
            <a href="#" className="hover:text-gray-900 dark:hover:text-white transition-colors">Privacy</a>
            <a href="#" className="hover:text-gray-900 dark:hover:text-white transition-colors">Terms</a>
            <a href="#" className="hover:text-gray-900 dark:hover:text-white transition-colors">Contact</a>
          </div>
        </div>
        <div className="mt-4 text-xs text-gray-400">
          © {new Date().getFullYear()} PaperSummarizer. All rights reserved.
        </div>
      </div>
    </footer>
  );
}


