/** Export the authenticated owner's Spotify library for Stage 5B sampling.
 *
 * The output is a private, gitignored input artifact. It contains liked songs
 * plus playlists owned by the authenticated account. No access/refresh token
 * is serialized.
 */
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import mongoose from "mongoose";
import { env } from "../env";
import { UserModel } from "../models/User";
import {
    getPlaylistTracks,
    getUserLikedSongs,
    getUserPlaylists,
} from "../services/spotify.playlist.service";
import { getValidAccessToken } from "../services/token.service";
import redis from "../utils/redis";

const SCHEMA_VERSION = "stage5b-owner-library-snapshot-v1";

function argument(name: string): string | undefined {
    const index = process.argv.indexOf(name);
    return index >= 0 ? process.argv[index + 1] : undefined;
}

function ownerDigest(spotifyId: string): string {
    return createHash("sha256").update(spotifyId).digest("hex");
}

async function resolveOwnerId(explicitId?: string): Promise<string> {
    if (explicitId) return explicitId;
    const users = await UserModel.find({}, { spotifyId: 1, _id: 0 }).lean();
    if (users.length !== 1 || !users[0]?.spotifyId) {
        throw new Error(
            `expected exactly one stored Spotify owner, found ${users.length}; pass --spotify-id explicitly`,
        );
    }
    return users[0].spotifyId;
}

async function main(): Promise<void> {
    const outputArgument = argument("--output");
    if (!outputArgument) throw new Error("--output is required");
    const output = resolve(outputArgument);

    await mongoose.connect(env.MONGO_URI);
    await redis.ping();
    const spotifyId = await resolveOwnerId(argument("--spotify-id"));
    const accessToken = await getValidAccessToken(spotifyId);

    const [likedItems, playlists] = await Promise.all([
        getUserLikedSongs(accessToken),
        getUserPlaylists(accessToken),
    ]);
    const ownedPlaylists = playlists.filter((playlist) => playlist.owner.id === spotifyId);
    const sources: Array<{ source_key: string; tracks: unknown[] }> = [{
        source_key: "LIKED",
        tracks: likedItems.flatMap((item) => item.track ? [item.track] : []),
    }];
    for (const playlist of ownedPlaylists) {
        const items = await getPlaylistTracks(accessToken, playlist.id);
        sources.push({
            source_key: `PLAYLIST:${playlist.id}`,
            tracks: items.flatMap((item) => item.item ? [item.item] : []),
        });
    }

    const snapshot = {
        schema_version: SCHEMA_VERSION,
        collected_at: new Date().toISOString(),
        owner_spotify_id_sha256: ownerDigest(spotifyId),
        source_policy: "LIKED_PLUS_OWNER_OWNED_PLAYLISTS",
        source_count: sources.length,
        liked_item_count: sources[0]?.tracks.length ?? 0,
        owned_playlist_count: ownedPlaylists.length,
        sources,
    };
    await mkdir(dirname(output), { recursive: true });
    await writeFile(output, `${JSON.stringify(snapshot, null, 2)}\n`, { mode: 0o600 });
    console.log(JSON.stringify({
        status: "OWNER_LIBRARY_SNAPSHOT_EXPORTED",
        liked_item_count: snapshot.liked_item_count,
        owned_playlist_count: snapshot.owned_playlist_count,
        source_count: snapshot.source_count,
        output,
    }));
}

main()
    .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : "unknown error";
        console.error(`Stage 5B library export failed: ${message}`);
        process.exitCode = 1;
    })
    .finally(async () => {
        await Promise.allSettled([mongoose.disconnect(), redis.quit()]);
    });
