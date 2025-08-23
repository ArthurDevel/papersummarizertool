import { NextRequest, NextResponse } from 'next/server';
import { headers as nextHeaders } from 'next/headers';
import { auth } from '../../../authentication/server_auth';

// The base URL of your Python backend, constructed using the same environment
const BACKEND_URL = `http://127.0.0.1:${process.env.NEXT_PUBLIC_CONTAINERPORT_API}`;

const handler = async (req: NextRequest) => {
    // Extract the path from the request, stripping the leading '/api'.
    // e.g., if the request is to /api/papers/search,
    // the resulting path will be '/papers/search'
    const path = req.nextUrl.pathname.replace(/^\/api/, '');
    const fullBackendUrl = `${BACKEND_URL}${path}${req.nextUrl.search}`;

    try {
        // Protect user list endpoints: inject verified auth provider id from session
        const isUserList = /^\/api\/users\/me\/list\//.test(req.nextUrl.pathname);
        console.log('[proxy] incoming', { path: req.nextUrl.pathname, isUserList });
        let forwardHeaders: HeadersInit = req.headers;
        if (isUserList) {
            const nh = await nextHeaders();
            const cookieFromReq = req.headers.get('cookie') || '';
            const cookieFromNext = nh.get('cookie') || '';
            console.log('[proxy] cookies', { fromReq: cookieFromReq.length > 0, fromNext: cookieFromNext.length > 0 });
            const session = await auth.api.getSession({ headers: nh });
            console.log('[proxy] session', { hasSession: Boolean(session), userId: session?.user?.id });
            if (!session) {
                return NextResponse.json({ message: 'Unauthorized' }, { status: 401 });
            }
            const h = new Headers(req.headers);
            h.set('X-Auth-Provider-Id', session.user.id);
            forwardHeaders = h;
        }
        // Create a new request to the backend.
        const backendResponse = await fetch(fullBackendUrl, {
            method: req.method,
            headers: forwardHeaders,
            body: req.body,
            // duplex is required for streaming the body.
            // @ts-ignore
            duplex: 'half'
        });

        // Pipe the backend response directly to the client.
        return new NextResponse(backendResponse.body, {
            status: backendResponse.status,
            statusText: backendResponse.statusText,
            headers: backendResponse.headers,
        });

    } catch (error) {
        console.error(`Error proxying request to ${fullBackendUrl}`, error);
        return NextResponse.json({ message: 'Error proxying request to the backend.' }, { status: 500 });
    }
};

export { handler as GET, handler as POST, handler as PUT, handler as DELETE, handler as PATCH };
