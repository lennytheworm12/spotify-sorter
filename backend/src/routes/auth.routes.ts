//requests for auth will be handled here
import express from "express";

const router: express.Router = express.Router();
import { SpotifyUserLogin } from "../controllers/auth.spotifyLogin"
import { SpotifyCallback } from "../controllers/auth.spotifyCallback"
//first auth request will be redirecting the user to spotify screen with the correct scopes
//

router.get('/spotify/login', SpotifyUserLogin);
router.get('/spotify/callback', SpotifyCallback);



export default router;



