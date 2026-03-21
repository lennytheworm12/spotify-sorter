//file for spotify services like getting user playlists etc
//



import axios from "axios";
import type { SpotifySimplifiedPlaylist, SpotifyUserPlaylistsResponse} from "../types/spotify.types";

//request to get user playlist

export const getUserPlaylists = async (accessToken: string): Promise<SpotifySimplifiedPlaylist[]> => {
    //asks spotify for user playlist via /v1/me/playlists
        const allPlaylists: SpotifySimplifiedPlaylist[] = [];
        let url = `https://api.spotify.com/v1/me/playlists?limit=50`

        while (url) {
            const response = await axios.get<SpotifyUserPlaylistsResponse>(url, {
                headers: {Authorization: `Bearer ${accessToken}`}
            })
            allPlaylists.push(...response.data.items);
            url = response.data.next ?? ''; //update to the next fetch url
        }
        return allPlaylists;

        
}




