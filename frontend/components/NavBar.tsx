import Link from 'next/link';
import React from 'react';

type NavBarProps = {
  className?: string;
};

export default function NavBar({ className = '' }: NavBarProps) {
  return (
    <nav className={`w-full border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 backdrop-blur ${className}`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <div className="text-base font-semibold text-gray-900 dark:text-gray-100">PaperSummarizer</div>
          <ul className="hidden md:flex items-center gap-6">
            <li>
              <Link href="#" className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
                All Papers
              </Link>
            </li>
            <li>
              <Link href="#" className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
                Donate Inference
              </Link>
            </li>
            <li>
              <Link href="#" className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
                Roadmap
              </Link>
            </li>
            <li>
              <Link href="#" className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
                About Us
              </Link>
            </li>
          </ul>
        </div>

        <div className="md:hidden">
          <button
            type="button"
            aria-label="Open menu"
            className="inline-flex items-center justify-center p-2 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-800"
          >
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M3 5h14a1 1 0 100-2H3a1 1 0 100 2zm14 4H3a1 1 0 000 2h14a1 1 0 100-2zm0 6H3a1 1 0 000 2h14a1 1 0 100-2z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
      </div>
    </nav>
  );
}


