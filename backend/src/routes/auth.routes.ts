//requests for auth will be handled here
import express from "express";

const router: express.Router = express.Router();
import { SpotifyUserLogin } from "../controllers/auth.spotifyLogin"
import { SpotifyCallback } from "../controllers/auth.spotifyCallback"
import {getMe} from "../controllers/auth.getMe";
import {verifyUser} from "../middleware/auth.middleware";
import {getUserInfo} from "../services/mongo.user.services";
//first auth request will be redirecting the user to spotify screen with the correct scopes
//

router.get('/spotify/login', SpotifyUserLogin);
router.get('/spotify/callback', SpotifyCallback);

// auth me route will return basic information about the user for now
router.get('/me', verifyUser, getMe);



export default router;



