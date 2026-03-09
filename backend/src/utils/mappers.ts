//methods to convert spotify data into our database compatible format 
//so incase spotify changes their data we can edit here instead of throughout our code
import type {SpotifyUser, SpotifyToken} from "../types/spotify.types.js"
import type {BaseUser } from "../models/User.js";


//mapping to map spotifyUser to db user
export const mapSpotifyUserToDBUser = (user: SpotifyUser,token: SpotifyToken): BaseUser => {
    //map spotifyUser to baseUser
    const convertedUser: BaseUser = {spotifyId: user.id, displayName: user.display_name, profilePictureUrl: user.images[0]?.url ?? null, refreshToken: token.refresh_token};
    return convertedUser;

}
