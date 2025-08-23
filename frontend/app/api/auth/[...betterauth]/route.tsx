import { betterAuth } from "better-auth";
import { toNextJsHandler } from "better-auth/next-js";
// Note: We will need to install the magic link plugin package if it's separate
// For now, assuming it's part of the main 'better-auth' package.
import { magicLink } from "better-auth/plugins";
import { APIError } from "better-auth/api";
import { Resend } from 'resend';
import { MagicLinkEmail, AddToListMagicLinkEmail } from '../../../../authentication/emails';
import { render } from '@react-email/render';


const auth = betterAuth({
    plugins: [
        magicLink({
            sendMagicLink: async ({ email, token, url }, request) => {
                const resend = new Resend(process.env.RESEND_API_KEY);
                try {
                    const isAddToList = (request?.headers?.get('x-email-template') || '').toLowerCase() === 'addtolist';
                    const paperTitle = request?.headers?.get('x-paper-title') || undefined;

                    let subject: string;
                    let html: string;

                    if (isAddToList) {
                        subject = `Sign in to add “${(paperTitle || '').toString()}”`;
                        subject = subject.replace(/[\r\n]+/g, ' ').replace(/\s{2,}/g, ' ').trim().slice(0, 200);
                        html = await render(<AddToListMagicLinkEmail magicLink={url} paperTitle={paperTitle} />);
                    } else {
                        subject = 'Your Magic Link to Sign In';
                        html = await render(<MagicLinkEmail magicLink={url} />);
                    }

                    await resend.emails.send({
                        from: 'PaperSummarizer <login@resend.dev>', // TODO: Replace with your domain
                        to: [email],
                        subject,
                        html,
                    });
                } catch (error) {
                    throw new APIError("INTERNAL_SERVER_ERROR", {
                        message: "Could not send the magic link email. Please try again later.",
                    });
                }
            }
        })
    ],
    databaseHooks: {
        user: {
            create: {
                after: async (user) => {
                    console.log(`User created in BetterAuth with ID: ${user.id}. Syncing to Python backend...`);

                    const backendUrl = `http://127.0.0.1:${process.env.NEXT_PUBLIC_CONTAINERPORT_API}/users/sync`;

                    try {
                        const response = await fetch(backendUrl, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                id: user.id,
                                email: user.email,
                            }),
                        });

                        if (!response.ok) {
                            // If the backend returns an error, we throw an APIError.
                            // This will stop the sign-in process and show an error to the user.
                            const errorBody = await response.text();
                            console.error(`Failed to sync user ${user.id} to backend. Status: ${response.status}, Body: ${errorBody}`);
                            throw new APIError("INTERNAL_SERVER_ERROR", {
                                message: "Your account could not be created in our system. Please try again later.",
                            });
                        }

                        console.log(`Successfully synced user ${user.id} to Python backend.`);

                    } catch (error) {
                        console.error(`Network or other error while syncing user ${user.id} to backend:`, error);
                        // Also throw an error for network issues etc.
                        throw new APIError("INTERNAL_SERVER_ERROR", {
                            message: "A network error occurred while creating your account. Please try again later.",
                        });
                    }
                }
            }
        }
    },
    // The session secret will be automatically picked up from the
    // BETTER_AUTH_SECRET environment variable.
    // Set the session duration. Let's set it to 30 days as discussed.
    sessionMaxAge: 60 * 60 * 24 * 30, // 30 days in seconds
});

// The toNextJsHandler function adapts the BetterAuth handler to work with Next.js App Router.
// It creates the GET and POST handlers for our API route.
export const { GET, POST } = toNextJsHandler(auth.handler);
