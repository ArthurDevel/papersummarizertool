import { NextRequest, NextResponse } from 'next/server';

// The base URL of your Python backend, constructed using the same environment
const BACKEND_URL = `http://127.0.0.1:${process.env.NEXT_PUBLIC_CONTAINERPORT_API}`;

const handler = async (req: NextRequest) => {
    // Extract the path from the request, stripping the leading '/api'.
    // e.g., if the request is to /api/papers/search,
    // the resulting path will be '/papers/search'
    const path = req.nextUrl.pathname.replace(/^\/api/, '');
    const fullBackendUrl = `${BACKEND_URL}${path}${req.nextUrl.search}`;

    try {
        // Create a new request to the backend.
        const backendResponse = await fetch(fullBackendUrl, {
            method: req.method,
            headers: req.headers,
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
