
export interface BaseUser {
    spotifyId: string;
    displayName: string | null;
    profilePictureUrl: string | null;
    refreshToken?: string;//may not be returned on repeat logins
}

// what Mongoose gives back when you query
export interface DatabaseUser extends BaseUser {
    refreshToken: string; //enforce refresh token for database users
    lastChecked: Date | null;
    createdAt: Date;
    updatedAt: Date;
}
export type PublicUser = Pick<DatabaseUser, 'spotifyId' | 'displayName' | 'profilePictureUrl'>
