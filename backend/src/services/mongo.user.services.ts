//file to implement user services

import { UserModel } from "../models/User";
import mongoose from "mongoose";
import type { BaseUser, DatabaseUser, PublicUser } from "../types/user.types";

export const upsertUser = async (user: BaseUser): Promise<void> => {
    await UserModel.findOneAndUpdate(
        { spotifyId: user.spotifyId },
        {
            $set: {
                displayName: user.displayName,
                profilePictureUrl: user.profilePictureUrl,
                ...(user.refreshToken && { refreshToken: user.refreshToken })
            }
        },
        { upsert: true, new: true }
    )
}


//method to retrieve a user based on their spotifyID
export const getUserInfo = async (spotifyId: string): Promise<PublicUser | null> => {

    const user = await UserModel.findOne({ spotifyId });
    if (!user) return null;

    return {
        spotifyId: user.spotifyId,
        displayName: user.displayName,
        profilePictureUrl: user.profilePictureUrl
    }


}

