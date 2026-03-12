//controller to log out a user 
import type { Request, Response } from "express";
import { deleteAccessToken } from "../services/token.service";
export const logoutUser = async (req: Request, res: Response) => {
    //clear the cookies jwt
    try {
        res.clearCookie('jwt');
        await deleteAccessToken(req.user!.spotifyId);
        return res.status(200).json({ message: 'logged out' })
    } catch (error) {
        //if redis throws
        console.error("failed to delete redis token", error);
        return res.status(200).json({ message: "logged out" });

    }
}
