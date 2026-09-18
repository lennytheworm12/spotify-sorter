import express from "express";
import { verifyUser } from "../middleware/auth.middleware";
import { getLikedSongs } from "../controllers/library.getLikedSongs";

const router: express.Router = express.Router();

router.use(verifyUser);

router.get('/liked', getLikedSongs);

export default router;
