//file defines the type for spotify data types

//the spotify token returned from the login 
export interface SpotifyToken {
    access_token: string;
    token_type: string;
    scope: string;
    expires_in: number;
    refresh_token?: string;

}

//shared primative typings (similar to structs?) 
//--------------------------------------------------------------- //
export interface SpotifyExternalUrls {
    spotify: string
}

export interface SpotifyImage {
    url: string;
    height: number | null;
    width: number | null;
}

export interface SpotifyRestrictions {
    reason: 'market' | 'product' | 'explicit' | string
}


//pagination wrapper since spotify only returns items/songs 50 at a time
//--------------------------------------------------------------- //
export interface SpotifyPaginated<T> {
    href: string;
    limit: number;
    next: string | null;
    offset: number;
    previous: string | null;
    total: number;
    items: T[];
}


//spotify user information just the data spotify returns about a user
//--------------------------------------------------------------- //
export interface SpotifyUser {
    id: string;
    display_name: string | null;
    images: SpotifyImage[];
    uri: string;
    href: string;
    external_urls: SpotifyExternalUrls;
    type: 'user';
}


//Artist
//--------------------------------------------------------------- //

//simplified version returned from track and album objs
export interface SpotifySimplifiedArtist {
    id: string;
    name: string;
    href: string;
    uri: string;
    external_urls: SpotifyExternalUrls;
    type: 'artist';
}


//full artist objs returned from get artist includes the artist genres leveraging simplied
export interface SpotifyArtist extends SpotifySimplifiedArtist {
    genres: string[];
    images: SpotifyImage[];
    followers: { hrefs: string | null, total: number };
    popularity: number;
}

// ─── Album ────────────────────────────────────────────────────────────
//needed for the tracks album data member(likely wont use albums)
export interface SpotifyAlbum {
    id: string;
    name: string;
    album_type: 'album' | 'single' | 'compilation';
    total_tracks: number;
    release_date: string;
    release_date_precision: 'year' | 'month' | 'day';
    images: SpotifyImage[];
    artists: SpotifySimplifiedArtist[];
    external_urls: SpotifyExternalUrls;
    href: string;
    uri: string;
    type: 'album';
    restrictions?: SpotifyRestrictions;
}


//track types
//--------------------------------------------------------------- //
export interface SpotifyTrack {
    id: string;
    name: string;
    duration_ms: number;
    explicit: boolean;
    tracker_number: number;
    disc_number: number;
    is_local: boolean;
    is_playable?: boolean;
    album: SpotifyAlbum;
    artists: SpotifySimplifiedArtist[];
    external_urls: SpotifyExternalUrls;
    href: string;
    uri: string;
    type: 'track';
    restrctions?: SpotifyRestrictions;
}



//playlist items
//--------------------------------------------------------------- //
//wrapper for a track inside a playlist
//we need to use get playlist/{id}/items now since tracks are depricated
export interface SpotifyPlaylistItem {
  added_at: string | null  // ISO date string, null on old playlists
  added_by: Pick<SpotifyUser, 'id' | 'href' | 'uri' | 'external_urls' | 'type'> | null
  is_local: boolean
  item: SpotifyTrack | null  // null if track was removed/unavailable
}


//liked/saved songs
//--------------------------------------------------------------- //
//liked songs have a different structure
export interface SpotifyLikedTrack {
    added_at: string;
    track: SpotifyTrack;
}


//instead of paginating in the other files we can export this
export type SpotifyLikedSongsResponse = SpotifyPaginated<SpotifyLikedTrack>;
export type SpotifyPlaylistItemsResponse = SpotifyPaginated<SpotifyPlaylistItem>;
