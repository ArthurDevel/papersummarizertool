import { NextResponse } from 'next/server'

const BASIC_REALM = 'Management'
const ADMIN_USER = 'admin'
const ADMIN_PASS = process.env.ADMIN_BASIC_PASSWORD || ''

function unauthorized() {
  return new NextResponse('Unauthorized', {
    status: 401,
    headers: { 'WWW-Authenticate': `Basic realm="${BASIC_REALM}", charset="UTF-8"` },
  })
}

function needsAdmin(url: URL, method: string): boolean {
  const p = url.pathname

  // UI: protect management page
  if (p === '/management') return true

  // Protect write ops on local JSON route
  if (p === '/layouttests/data' && (method === 'POST' || method === 'DELETE')) return true

  // Admin-only API endpoints
  // papers admin: list, restart, delete, import
  if (p === '/api/papers' && (method === 'GET')) return true
  if (p === '/api/papers/import_json') return true
  if (p.startsWith('/api/papers/') && (p.endsWith('/restart') || method === 'DELETE')) return true

  // requested_papers admin: list/start/delete
  if (p.startsWith('/api/requested_papers')) return true

  // Public API allowlist (explicitly do NOT protect)
  if (p === '/api/papers/request_arxiv') return false
  if (p === '/api/papers/enqueue_arxiv') return false
  if (p.startsWith('/api/papers/slug/')) return false
  if (/^\/api\/papers\/[A-Za-z0-9\-]+\/slug$/.test(p)) return false

  return false
}

export function middleware(req: Request) {
  // Disabled if no password set
  if (!ADMIN_PASS) return NextResponse.next()

  const url = new URL(req.url)
  if (!needsAdmin(url, req.method)) return NextResponse.next()

  const header = req.headers.get('authorization') || ''
  const toBase64 = (s: string) => {
    try {
      // @ts-ignore Buffer may exist in node-based local dev
      if (typeof Buffer !== 'undefined') return Buffer.from(s, 'utf-8').toString('base64')
    } catch {}
    try {
      // Edge runtime should have btoa
      // @ts-ignore btoa is global in web runtime
      if (typeof btoa !== 'undefined') return btoa(s)
    } catch {}
    return s
  }
  const expected = `Basic ${toBase64(`${ADMIN_USER}:${ADMIN_PASS}`)}`

  if (header !== expected) return unauthorized()
  return NextResponse.next()
}

export const config = {
  // Limit UI popup strictly to the management page; backend still enforces API auth
  matcher: ['/management'],
}


