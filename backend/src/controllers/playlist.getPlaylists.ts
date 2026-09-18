import type { Request, Response } from "express";
import { getValidAccessToken } from "../services/token.service";
import { getUserPlaylists } from "../services/spotify.playlist.service";

export const getPlaylists = async (req: Request, res: Response) => {
    try {
        const accessToken = await getValidAccessToken(req.user!.spotifyId);
        const playlists = await getUserPlaylists(accessToken);
        return res.status(200).json(playlists);
    } catch (error) {
        return res.status(500).json({ message: "failed to fetch playlists" });
    }
}
