import { NextResponse } from 'next/server';
import { readFile, readdir, writeFile, mkdir, stat, unlink } from 'fs/promises';
import path from 'path';
import { randomUUID } from 'crypto';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const requestedFile = url.searchParams.get('file');

    const baseDir = path.resolve(process.cwd(), '..', 'data', 'paperjsons');
    await mkdir(baseDir, { recursive: true });

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

function isUuidV4(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  const uuidV4Regex = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  return uuidV4Regex.test(value);
}

async function fileExists(p: string): Promise<boolean> {
  try {
    await stat(p);
    return true;
  } catch {
    return false;
  }
}

export async function POST(request: Request) {
  try {
    const baseDir = path.resolve(process.cwd(), '..', 'data', 'paperjsons');
    await mkdir(baseDir, { recursive: true });

    const bodyText = await request.text();
    let parsed: any;
    try {
      parsed = JSON.parse(bodyText);
    } catch (e) {
      return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
    }

    let targetUuid: string;
    if (isUuidV4(parsed?.paper_id)) {
      targetUuid = parsed.paper_id;
      const targetPath = path.join(baseDir, `${targetUuid}.json`);
      if (await fileExists(targetPath)) {
        return NextResponse.json({ error: `A file with id ${targetUuid} already exists.` }, { status: 409 });
      }
      await writeFile(targetPath, bodyText, 'utf-8');
      return NextResponse.json({ file: `${targetUuid}.json`, paper_id: targetUuid }, { status: 201 });
    }

    targetUuid = randomUUID();
    const targetPath = path.join(baseDir, `${targetUuid}.json`);
    await writeFile(targetPath, bodyText, 'utf-8');
    return NextResponse.json({ file: `${targetUuid}.json`, paper_id: targetUuid }, { status: 201 });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: `Failed to save JSON: ${message}` }, { status: 500 });
  }
}

export async function DELETE(request: Request) {
  try {
    const url = new URL(request.url);
    const requestedFile = url.searchParams.get('file');
    if (!requestedFile) {
      return NextResponse.json({ error: 'Missing file parameter' }, { status: 400 });
    }

    const baseDir = path.resolve(process.cwd(), '..', 'data', 'paperjsons');
    await mkdir(baseDir, { recursive: true });

    const safeName = path.basename(requestedFile);
    const targetPath = path.join(baseDir, safeName);
    if (!(await fileExists(targetPath))) {
      return NextResponse.json({ error: 'File not found' }, { status: 404 });
    }

    await unlink(targetPath);
    return NextResponse.json({ deleted: safeName }, { status: 200 });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown error';
    return NextResponse.json({ error: `Failed to delete JSON: ${message}` }, { status: 500 });
  }
}


