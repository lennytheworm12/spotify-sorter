//end point to return information about the user when called
//


import type { Request, Response } from "express";
import { getUserInfo } from "../services/mongo.user.services";

export const getMe = async (req: Request, res: Response) => {
    //given the request to get information about user
    //trust the auth middleware to check the user is valid
    //so  we can assert that req.user exists
    try {
        const user = await getUserInfo(req.user!.spotifyId);
        if (!user) return res.status(404).json({ message: 'user not found' })
        return res.status(200).json(user)
    } catch (error) {
        return res.status(500).json({ message: "database error" });
    }
}
