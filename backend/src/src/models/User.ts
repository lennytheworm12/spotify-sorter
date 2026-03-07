import mongoose, { Schema } from "mongoose";


//defines the user's Schema for user model used for adding to the db
//schema is essentially a header/init of the model 
const userSchema = new mongoose.Schema({

    spotifyId: { type: String, required: true, index: true, unique: true },
    displayName: String,

    auth: {
        refreshToken: { type: String, required: true },
        accessToken: { type: String },
        accessTokenExpiresAt: { type: Number }
    },

    spotifyInfo: {
        likedSongs: [Object],
        playlists: [Object],
    },
}, { timestamps: true });
