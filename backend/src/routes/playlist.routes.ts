import express from "express";

import {verifyUser} from "../middleware/auth.middleware";

const router: express.Router = express.Router();
router.use(verifyUser);


//routing for getting playlists
// router.get('/', getPlaylists);
//router.get('/:id/tracks', getPlaylistTracks)


export default router;
