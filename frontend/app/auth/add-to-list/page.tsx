'use client';

import { useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { authClient } from '../../../services/auth';

export default function AddToListCallbackPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { data: session } = authClient.useSession();
  const [status, setStatus] = useState<'pending' | 'done' | 'error'>('pending');
  const [message, setMessage] = useState<string>('Signing you in and adding the paper to your list...');

  useEffect(() => {
    const run = async () => {
      const error = searchParams.get('error');
      const paperUuid = searchParams.get('paper_uuid') || '';
      const redirect = searchParams.get('redirect') || '/';
      if (error) {
        setStatus('error');
        setMessage(`Authentication failed: ${error}.`);
        return;
      }
      try {
        // Wait for session to exist
        if (!session?.user?.id) return;
        const headers = new Headers();
        headers.set('X-Auth-Provider-Id', session.user.id);
        const resp = await fetch(`/api/users/me/list/${encodeURIComponent(paperUuid)}`, {
          method: 'POST',
          headers,
        });
        if (!resp.ok) {
          const txt = await resp.text();
          throw new Error(txt || `Failed to add to list (${resp.status})`);
        }
        setStatus('done');
        setMessage('Added to your list! Redirecting...');
        setTimeout(() => router.replace(redirect), 1200);
      } catch (e: any) {
        setStatus('error');
        setMessage(e?.message || 'An error occurred.');
      }
    };
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, searchParams]);

  return (
    <div className="container mx-auto max-w-md p-8 text-center">
      <h1 className="text-2xl font-bold mb-4">Add to List</h1>
      <div className={`p-4 rounded ${status === 'error' ? 'bg-red-100 border border-red-400 text-red-700' : 'bg-blue-100 border border-blue-400 text-blue-700'}`}>
        <p>{message}</p>
      </div>
    </div>
  );
}


