//requests for auth will be handled here
import express from "express";

const router: express.Router = express.Router();
import {SpotifyUserLogin} from "../controllers/auth.spotifyLogin"

//first auth request will be redirecting the user to spotify screen with the correct scopes
//

router.get('/spotify/login', SpotifyUserLogin);

export default router;



