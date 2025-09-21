'use client';

import Link from 'next/link';
import React, { useState } from 'react';
import { Github, User as UserIcon, X, Menu } from 'lucide-react';
import { authClient } from '../services/auth';

type NavBarProps = {
  className?: string;
};

/**
 * Navigation bar component with responsive mobile menu
 * @param className - Additional CSS classes to apply
 * @returns Navigation bar with hamburger menu for mobile
 */
export default function NavBar({ className = '' }: NavBarProps) {
  const { data: session } = authClient.useSession();
  const isLoggedIn = Boolean(session?.user?.id);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState<boolean>(false);

  /**
   * Toggles the mobile menu open/closed state
   */
  const toggleMobileMenu = (): void => {
    setIsMobileMenuOpen(!isMobileMenuOpen);
  };

  /**
   * Closes the mobile menu
   */
  const closeMobileMenu = (): void => {
    setIsMobileMenuOpen(false);
  };
  return (
    <nav className={`w-full ${className}`}>
      <div className="w-full px-4 sm:px-6 lg:px-10 pt-7 pb-3 flex items-center justify-between">
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
          {/*<li>
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
          </li>*/}
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
              onClick={toggleMobileMenu}
              aria-label={isMobileMenuOpen ? "Close menu" : "Open menu"}
              className="inline-flex items-center justify-center p-2 rounded-md text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white transition-colors"
            >
              {isMobileMenuOpen ? (
                <X className="h-5 w-5" />
              ) : (
                <Menu className="h-5 w-5" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Navigation Drawer */}
      {isMobileMenuOpen && (
        <>
          {/* Backdrop */}
          <div 
            className="fixed inset-0 z-40 bg-black/50 md:hidden"
            onClick={closeMobileMenu}
            aria-hidden="true"
          />
          
          {/* Drawer */}
          <div className="fixed top-0 right-0 z-50 h-full w-80 max-w-[85vw] bg-white dark:bg-gray-900 shadow-xl md:hidden">
            <div className="flex flex-col h-full">
              {/* Header */}
              <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
                <span className="text-lg font-semibold text-gray-900 dark:text-gray-100">Menu</span>
                <button
                  onClick={closeMobileMenu}
                  aria-label="Close menu"
                  className="p-2 rounded-md text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
              
              {/* Navigation Links */}
              <div className="flex-1 overflow-y-auto p-4">
                <nav className="space-y-2">
                  <Link 
                    href="/papers" 
                    onClick={closeMobileMenu}
                    className="block px-4 py-3 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                  >
                    All Papers
                  </Link>
                  <Link 
                    href="/arxiv-search" 
                    onClick={closeMobileMenu}
                    className="block px-4 py-3 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                  >
                    Arxiv Search
                  </Link>
                  <Link
                    href="https://github.com/ArthurDevel/papersummarizertool"
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={closeMobileMenu}
                    className="flex items-center gap-3 px-4 py-3 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                  >
                    <Github size={18} />
                    <span>Star us on GitHub</span>
                  </Link>
                </nav>
              </div>
              
              {/* User Actions */}
              <div className="border-t border-gray-200 dark:border-gray-700 p-4">
                {isLoggedIn ? (
                  <Link
                    href="/user"
                    onClick={closeMobileMenu}
                    className="flex items-center gap-3 w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                  >
                    <UserIcon size={18} />
                    <span>Your account</span>
                  </Link>
                ) : (
                  <Link
                    href="/login"
                    onClick={closeMobileMenu}
                    className="block w-full px-4 py-3 text-center rounded-lg border border-gray-300 dark:border-gray-700 text-gray-800 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                  >
                    Log in
                  </Link>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </nav>
  );
}


