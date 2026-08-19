import { env } from "../env";

// Builds a frontend URL with query markers so the SPA can react to the
// OAuth result (e.g. /?auth=success, /?auth=error&reason=state_mismatch).
export function frontendRedirect(params: Record<string, string>): string {
    const url = new URL(env.FRONTEND_URL);
    for (const [key, value] of Object.entries(params)) {
        url.searchParams.set(key, value);
    }
    return url.toString();
}
