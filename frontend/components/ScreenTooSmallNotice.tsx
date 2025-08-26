import React from 'react'

type ScreenTooSmallNoticeProps = {
  className?: string
  title?: string
  description?: string
}

export default function ScreenTooSmallNotice({
  className = '',
  title = "Screen too small",
  description = "We don't support mobile yet. Please use a larger screen.",
}: ScreenTooSmallNoticeProps) {
  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center p-6 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 ${className}`}>
      <div className="max-w-md w-full text-center">
        <h1 className="text-2xl font-semibold mb-3">{title}</h1>
        <p className="text-sm text-gray-600 dark:text-gray-300">{description}</p>
      </div>
    </div>
  )
}


