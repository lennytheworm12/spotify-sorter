import express from "express";
import { verifyUser } from "../middleware/auth.middleware";
import { getPlaylists } from "../controllers/playlist.getPlaylists";
import { getPlaylistTracks } from "../controllers/playlist.getPlaylistTracks";

const router: express.Router = express.Router();

router.use(verifyUser);

router.get('/', getPlaylists);
router.get('/:id/tracks', getPlaylistTracks);

export default router;
