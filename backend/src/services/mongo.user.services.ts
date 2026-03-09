//file to implement user services

import { UserModel } from "../models/User";
import mongoose from "mongoose";
import type { BaseUser } from "../types/user.types";

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
