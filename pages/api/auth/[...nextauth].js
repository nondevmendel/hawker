import NextAuth from 'next-auth'
import GoogleProvider from 'next-auth/providers/google'
import { getOrCreateUser, getUserApiKey } from '../../../lib/storage'

export const authOptions = {
  providers: [
    GoogleProvider({
      clientId:     process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    }),
  ],
  callbacks: {
    async signIn({ profile }) {
      // Any Google account can sign in
      return !!profile?.email
    },
    async jwt({ token, profile }) {
      if (profile) {
        // First sign-in: provision user
        const uid = await getOrCreateUser({
          sub:     token.sub,
          email:   profile.email,
          name:    profile.name,
          picture: profile.picture,
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
