import NextAuth from 'next-auth'
import GoogleProvider from 'next-auth/providers/google'

const ALLOWED_EMAIL = 'mmr305@gmail.com'

export const authOptions = {
  providers: [
    GoogleProvider({
      clientId:     process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    }),
  ],
  callbacks: {
    async signIn({ profile }) {
      return profile?.email === ALLOWED_EMAIL
    },
  },
  secret: process.env.NEXTAUTH_SECRET,
  pages: {
    error: '/auth-error',
  },
}

export default NextAuth(authOptions)
