'use client';

import { useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';

export default function AuthCallbackPage() {
    const searchParams = useSearchParams();
    const router = useRouter();
    const [message, setMessage] = useState('Authentication successful! Redirecting...');
    const [error, setError] = useState('');

    useEffect(() => {
        const errorParam = searchParams.get('error');

        if (errorParam) {
            setError(`Authentication failed: ${errorParam}. Please try signing in again.`);
        } else {
            // If there's no error, we assume the server-side verification was successful.
            // The user should now have a session cookie.
            // We'll redirect them to the homepage.
            setTimeout(() => {
                router.push('/');
            }, 2000);
        }
    }, [searchParams, router]);

    return (
        <div className="container mx-auto max-w-md p-8 text-center">
            <h1 className="text-2xl font-bold mb-4">Authentication</h1>
            {error ? (
                <div className="p-4 bg-red-100 border border-red-400 text-red-700 rounded">
                    <p>{error}</p>
                </div>
            ) : (
                <div className="p-4 bg-blue-100 border border-blue-400 text-blue-700 rounded">
                    <p>{message}</p>
                </div>
            )}
        </div>
    );
}
