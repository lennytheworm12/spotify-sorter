import express from "express";
import { verifyUser } from "../middleware/auth.middleware";
import { sort } from "../controllers/sort";

const router: express.Router = express.Router();

router.use(verifyUser);

router.post('/', sort);

export default router;
