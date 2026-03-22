import express from "express";

import {verifyUser} from "../middleware/auth.middleware";
const router: express.Router = express.Router();

//routes for user library since liked songs are not playlists
router.use(verifyUser);

router.get('/liked', getLikedSongs);

export default router;
