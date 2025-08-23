import Link from 'next/link';
import React from 'react';
import { Github, User as UserIcon } from 'lucide-react';
import { headers } from 'next/headers';
import { auth } from '../authentication/server_auth';

type NavBarProps = {
  className?: string;
};

export default async function NavBar({ className = '' }: NavBarProps) {
  const nh = headers();
  const session = await auth.api.getSession({ headers: nh });
  const isLoggedIn = Boolean(session?.user?.id);
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
            <Link href="/arxiv-search" className="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-colors">
              Arxiv Search
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

        <div className="flex items-center gap-3">
          {isLoggedIn ? (
            <Link
              href="/user"
              className="inline-flex items-center justify-center w-9 h-9 rounded-full border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
              title="Your account"
              aria-label="Your account"
            >
              <UserIcon size={18} />
            </Link>
          ) : (
            <Link
              href="/login"
              className="px-3 py-1.5 rounded-md text-sm border border-gray-300 dark:border-gray-700 text-gray-800 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              Log in
            </Link>
          )}
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
      </div>
    </nav>
  );
}


