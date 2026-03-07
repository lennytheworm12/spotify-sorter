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

});

//if there is missing field parse will throw an error and prevent the server from starting.
export const env = envSchema.parse(process.env);
