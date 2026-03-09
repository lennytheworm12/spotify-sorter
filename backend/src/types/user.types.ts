
export interface BaseUser {
    spotifyId: string;
    displayName: string | null;
    profilePictureUrl: string | null;
    refreshToken?: string;//may not be returned on repeat logins
}

// what Mongoose gives back when you query
export interface DatabaseUser extends BaseUser {
    lastChecked: Date | null;
    createdAt: Date;
    updatedAt: Date;
}


