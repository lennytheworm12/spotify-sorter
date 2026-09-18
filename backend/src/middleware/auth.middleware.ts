//file to implement the middleware once the user has logged into 
//spotify using our call back and gotten a signed jwt
//even without login each user has a jwt assigned from callback implictly defining users via spotify callback


import type { Request, Response, NextFunction } from 'express';
import jwt from 'jsonwebtoken';
import { env } from '../env';


const jwtSecret = env.JWT_SECRET;

export const verifyUser = (req: Request, res: Response, next: NextFunction) => {
    //given a request check the cookies using jwt secret
    if (!req.cookies || !req.cookies.jwt) {
        return res.status(401).json({ message: "request not authenticated" });
    }
    try {
        const decoded = jwt.verify(req.cookies.jwt, jwtSecret) as { spotifyId: string };
        //parse the spotifyId for the endpoints that need auth
        req.user = { spotifyId: decoded.spotifyId }
        next();

    }
    catch (error) {
        return res.status(401).json({ message: "could not verify token" });
    }
}

