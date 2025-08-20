import Link from 'next/link';
import React from 'react';
import { Github } from 'lucide-react';

type NavBarProps = {
  className?: string;
};

export default function NavBar({ className = '' }: NavBarProps) {
  return (
    <nav className={`w-full ${className}`}>
      <div className="w-full px-10 pt-7 pb-3 flex items-center justify-between">
        <div className="text-base font-semibold text-gray-900 dark:text-gray-100">PaperSummarizer</div>

        <ul className="hidden md:flex items-center gap-6">
          <li>
            <Link href="/papers" className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
              All Papers
            </Link>
          </li>
          <li>
            <Link href="/donate" className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
              Donate Inference
            </Link>
          </li>
          <li>
            <Link href="/roadmap" className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
              Roadmap
            </Link>
          </li>
          <li>
            <Link href="/management" className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
              Management
            </Link>
          </li>
          <li>
            <Link href="/about" className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
              About Us
            </Link>
          </li>
          <li>
            <Link
              href="https://github.com/ArthurDevel/papersummarizertool"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors flex items-center gap-2"
            >
              <Github size={16} />
              <span>Star us on GitHub</span>
            </Link>
          </li>
        </ul>

        <div className="md:hidden">
          <button
            type="button"
            aria-label="Open menu"
            className="inline-flex items-center justify-center p-2 rounded-md text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white"
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


