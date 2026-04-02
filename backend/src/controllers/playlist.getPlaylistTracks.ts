import type { Request, Response } from "express";
import { getValidAccessToken } from "../services/token.service";
import { getPlaylistTracks } from "../services/spotify.playlist.service";

export const getPlaylistTracks = async (req: Request, res: Response) => {
    try {
        const { id } = req.params;
        const accessToken = await getValidAccessToken(req.user!.spotifyId);
        const tracks = await getPlaylistTracks(accessToken, id);
        return res.status(200).json(tracks);
    } catch (error) {
        return res.status(500).json({ message: "failed to fetch playlist tracks" });
    }
}
