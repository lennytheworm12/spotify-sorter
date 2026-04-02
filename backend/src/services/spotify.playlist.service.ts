//file for spotify services like getting user playlists etc
//



import axios from "axios";
import type { SpotifySimplifiedPlaylist, SpotifyUserPlaylistsResponse, SpotifyLikedTrack, SpotifyLikedSongsResponse, SpotifyPlaylistItem, SpotifyPlaylistItemsResponse } from "../types/spotify.types";

//request to get user playlist

export const getUserPlaylists = async (accessToken: string): Promise<SpotifySimplifiedPlaylist[]> => {
    //asks spotify for user playlist via /v1/me/playlists
    const allPlaylists: SpotifySimplifiedPlaylist[] = [];
    let url = `https://api.spotify.com/v1/me/playlists?limit=50`

    while (url) {
        const response = await axios.get<SpotifyUserPlaylistsResponse>(url, {
            headers: { Authorization: `Bearer ${accessToken}` }
        })
        allPlaylists.push(...response.data.items);
        url = response.data.next ?? ''; //update to the next fetch url
    }
    return allPlaylists;


}



export const getUserLikedSongs = async (accessToken: string): Promise<SpotifyLikedTrack[]> => {

    //gets the user's liked songs through 
    const allTracks: SpotifyLikedTrack[] = [];
    let url = `https://api.spotify.com/v1/me/tracks?limit=50`
    while (url) {
        const response = await axios.get<SpotifyLikedSongsResponse>(url, {
            headers: { Authorization: `Bearer ${accessToken}` }
        })
        allTracks.push(...response.data.items);
        url = response.data.next ?? '';
    }
    return allTracks;


}


//method to get the tracks on a playlist
export const getPlaylistTracks = async (accessToken: string, playlistId: string): Promise<SpotifyPlaylistItem[]> => {
    const allTracks: SpotifyPlaylistItem[] = [];

    let url = `https://api.spotify.com/v1/playlists/${playlistId}/items`;

    while (url) {
        const response = await axios.get<SpotifyPlaylistItemsResponse>(url, {
            headers: { Authorization: `Bearer ${accessToken}` }
        })
        allTracks.push(...response.data.items);
        url = response.data.next ?? '';
    }
    return allTracks;
}


// Creates a new playlist for the user and returns the new playlist ID.
export const createPlaylist = async (
    accessToken: string,
    userId: string,
    name: string
): Promise<string> => {
    const response = await axios.post<{ id: string }>(
        `https://api.spotify.com/v1/users/${userId}/playlists`,
        { name, public: false },
        { headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' } }
    );
    return response.data.id;
}


const TRACK_BATCH_SIZE = 100; // Spotify limit for POST /v1/playlists/{id}/tracks

// Adds track URIs to a playlist in batches of 100.
export const addTracksToPlaylist = async (
    accessToken: string,
    playlistId: string,
    trackUris: string[]
): Promise<void> => {
    for (let i = 0; i < trackUris.length; i += TRACK_BATCH_SIZE) {
        const batch = trackUris.slice(i, i + TRACK_BATCH_SIZE);
        await axios.post(
            `https://api.spotify.com/v1/playlists/${playlistId}/tracks`,
            { uris: batch },
            { headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' } }
        );
    }
}

