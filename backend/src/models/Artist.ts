import { Schema, model } from "mongoose";
import type { CachedArtist } from "../types/artist.types";

const ArtistSchema = new Schema<CachedArtist>(
    {
        spotifyId: { type: String, required: true, unique: true },
        name: { type: String, required: true },
        genres: { type: [String], default: [] },
        lastFetchedAt: { type: Date, required: true },
    },
    { timestamps: true }
);

export const ArtistModel = model<CachedArtist>("Artist", ArtistSchema);
