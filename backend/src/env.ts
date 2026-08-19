//guard the .env file to make sure we have all the required things in .env before the server can boot up 
import { z } from 'zod';
import dotenv from 'dotenv';

dotenv.config();

const envSchema = z.object({
    NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
    PORT: z.coerce.number().default(3000),
    MONGO_URI: z.string().url(),
    SPOTIFY_CLIENT_ID: z.string().min(1, "spotify client id is required"),
    SPOTIFY_CLIENT_SECRET: z.string().min(1, "spotify secret is required"),
    SPOTIFY_REDIRECT_URI: z.string().url(),
    JWT_SECRET: z.string().min(32, "JWT Secret should be at least 32 characters"),
    REDIS_URI: z.string().url(),
    FRONTEND_URL: z.string().url().default('http://localhost:5173'),
    // Cookie settings. Optional and env-controlled: production defaults to
    // Secure + SameSite=None (cross-site frontend), local dev defaults to
    // SameSite=Lax without Secure so localhost:5173 <-> localhost:3000 works.
    COOKIE_SAME_SITE: z.enum(['lax', 'strict', 'none']).optional(),
    COOKIE_SECURE: z.enum(['true', 'false']).optional().transform(v => (v === undefined ? undefined : v === 'true')),
    COOKIE_DOMAIN: z.string().min(1).optional(),

}).superRefine((config, ctx) => {
    const sameSite = config.COOKIE_SAME_SITE ?? (config.NODE_ENV === 'production' ? 'none' : 'lax');
    const secure = config.COOKIE_SECURE ?? config.NODE_ENV === 'production';
    if (sameSite === 'none' && !secure) {
        ctx.addIssue({
            code: z.ZodIssueCode.custom,
            path: ['COOKIE_SECURE'],
            message: 'COOKIE_SECURE must be true when COOKIE_SAME_SITE is none',
        });
    }
});

//if there is missing field parse will throw an error and prevent the server from starting.
export const env = envSchema.parse(process.env);
