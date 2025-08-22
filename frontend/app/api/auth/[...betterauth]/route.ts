import { betterAuth } from "better-auth";
import { toNextJsHandler } from "better-auth/next-js";
// Note: We will need to install the magic link plugin package if it's separate
// For now, assuming it's part of the main 'better-auth' package.
import { magicLink } from "better-auth/plugins";

const auth = betterAuth({
    plugins: [
        magicLink({
            sendMagicLink: async ({ email, token, url }, request) => {
                // This is where you would implement your email sending logic.
                // For example, using a service like SendGrid, Resend, or Nodemailer.
                console.log(`
                ================================================
                V V V V V V V V V V V V V V V V V V V V V V V V 
                
                SENDING MAGIC LINK TO: ${email}
                
                URL: ${url}
                
                TOKEN: ${token}
                
                Normally, you wouldn't log this. This is for dev purposes.
                
                A A A A A A A A A A A A A A A A A A A A A A A A 
                ================================================
                `);
                // In a real app, you'd await your email sending promise here.
                // For now, we'll just resolve immediately.
                return;
            }
        })
    ],
    // The session secret will be automatically picked up from the
    // BETTER_AUTH_SECRET environment variable.
    // Set the session duration. Let's set it to 30 days as discussed.
    sessionMaxAge: 60 * 60 * 24 * 30, // 30 days in seconds
});

// The toNextJsHandler function adapts the BetterAuth handler to work with Next.js App Router.
// It creates the GET and POST handlers for our API route.
export const { GET, POST } = toNextJsHandler(auth.handler);
