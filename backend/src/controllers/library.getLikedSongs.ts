import type { Request, Response } from "express";
import { getValidAccessToken } from "../services/token.service";
import { getUserLikedSongs } from "../services/spotify.playlist.service";

export const getLikedSongs = async (req: Request, res: Response) => {
    try {
        const accessToken = await getValidAccessToken(req.user!.spotifyId);
        const songs = await getUserLikedSongs(accessToken);
        return res.status(200).json(songs);
    } catch (error) {
        return res.status(500).json({ message: "failed to fetch liked songs" });
    }
}
