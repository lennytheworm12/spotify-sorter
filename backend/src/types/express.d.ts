//defining user field for requests coming in it will contain spotify id we need to sign with jwt secret
//allowing controllers to access spotify id on restricted routes
declare global {
    namespace Express {
        interface Request {
            user?: { spotifyId: string };
        }
    }
}
export { };
