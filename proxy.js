import { NextResponse } from 'next/server'
import { getToken } from 'next-auth/jwt'

export async function proxy(req) {
  const token = await getToken({ req, secret: process.env.NEXTAUTH_SECRET })
  if (!token) {
    const signIn = new URL('/api/auth/signin', req.url)
    signIn.searchParams.set('callbackUrl', req.nextUrl.pathname)
    return NextResponse.redirect(signIn)
  }
  return NextResponse.next()
}

export const config = {
  matcher: ['/app.html', '/api/data'],
}
