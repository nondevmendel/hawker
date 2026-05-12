import { withAuth } from 'next-auth/middleware'
import { NextResponse } from 'next/server'

const authProxy = withAuth({
  pages: { signIn: '/api/auth/signin' },
})

export function proxy(req) {
  return authProxy(req)
}

export const config = {
  matcher: ['/app.html', '/api/data'],
}
