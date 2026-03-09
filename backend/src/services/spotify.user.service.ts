//fetching user information given a access token
import axios from "axios";
import type { SpotifyUser } from "../types/spotify.types";


export const getSpotifyUserData = async (accessToken: string): Promise<SpotifyUser> => {
    //try to access /me endpoint
    try {
        const response = await axios.get<SpotifyUser>(
            'https://api.spotify.com/v1/me',
            {
                headers: {
                    Authorization: `Bearer ${accessToken}`
                }
            }

        )
        return response.data;


    } catch (error) {
        throw error;
    }
}

