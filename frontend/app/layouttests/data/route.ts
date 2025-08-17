import { NextResponse } from 'next/server';
import { readFile, readdir } from 'fs/promises';
import path from 'path';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const requestedFile = url.searchParams.get('file');

    const baseDir = path.resolve(process.cwd(), '..', 'preloaded_papers');

    if (!requestedFile) {
      // If no file specified, return an index of available files
      const files = (await readdir(baseDir)).filter((f) => f.toLowerCase().endsWith('.json'));
      return NextResponse.json({ files }, { status: 200 });
    }

    // Prevent path traversal
    const safeName = path.basename(requestedFile);
    const jsonPath = path.join(baseDir, safeName);
    const raw = await readFile(jsonPath, 'utf-8');
    const data = JSON.parse(raw);
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: `Failed to read JSON: ${message}` }, { status: 500 });
  }
}


