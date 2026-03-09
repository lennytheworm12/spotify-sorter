import { Schema } from "mongoose";
import { model } from "mongoose";
import type { SpotifyImage } from "../types/spotify.types.js";

//this user interface will be for our own databse 
export interface BaseUser {
    spotifyId: string;
    displayName: string | null;
    profilePictureUrl: string | null;
    refreshToken: string;
}

// what Mongoose gives back when you query
interface DatabaseUser extends BaseUser {
    lastChecked: Date | null;
    createdAt: Date;
    updatedAt: Date;
}

//defines the user's Schema for user model used for adding to the db
//schema is essentially a header/init of the model 


const DatabaseUserSchema = new Schema<DatabaseUser>({
    spotifyId: { type: String, required: true, unique: true },
    displayName: { type: String },
    profilePictureUrl: { type: String },
    refreshToken: { type: String, required: true },
    lastChecked: { type: Date },



}, { timestamps: true })
