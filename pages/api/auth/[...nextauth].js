import NextAuth from 'next-auth'
import GoogleProvider from 'next-auth/providers/google'
import CredentialsProvider from 'next-auth/providers/credentials'
import { getOrCreateUser, getUserApiKey } from '../../../lib/storage'

export const authOptions = {
  providers: [
    GoogleProvider({
      clientId:     process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    }),
    CredentialsProvider({
      name: 'Password',
      credentials: {
        email:    { label: 'Email',    type: 'email' },
        password: { label: 'Password', type: 'password' },
      },
      async authorize(credentials) {
        if (
          credentials?.email    === process.env.ADMIN_EMAIL &&
          credentials?.password === process.env.ADMIN_PASSWORD
        ) {
          return { id: credentials.email, email: credentials.email, name: 'Mendel' }
        }
        return null
      },
    }),
  ],
  callbacks: {
    async signIn({ profile }) {
      // Google sign-in: any Google account allowed
      if (profile) return !!profile.email
      // Credentials sign-in: authorize() already validated
      return true
    },
    async jwt({ token, profile, user }) {
      if (profile) {
        // Google first sign-in
        const uid = await getOrCreateUser({
          sub:     token.sub,
          email:   profile.email,
          name:    profile.name,
          picture: profile.picture,
        })
        token.uid = uid
      } else if (user && !token.uid) {
        // Credentials first sign-in — look up by email
        const uid = await getOrCreateUser({
          sub:     user.email,
          email:   user.email,
          name:    user.name,
          picture: null,
        })
        token.uid = uid
      }
      return token
    },
    async session({ session, token }) {
      if (token.uid) {
        session.user.uid = token.uid
        session.user.apiKey = await getUserApiKey(token.uid)
      }
      return session
    },
  },
  secret: process.env.NEXTAUTH_SECRET,
  pages: {
    error: '/auth-error',
  },
}

export default NextAuth(authOptions)
