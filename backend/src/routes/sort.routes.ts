import express from "express";
import { verifyUser } from "../middleware/auth.middleware";
import { sort } from "../controllers/sort";
import { getLatestAction, undoAction } from "../controllers/sort.actions";

const router: express.Router = express.Router();

router.use(verifyUser);

router.post('/', sort);
router.get('/actions/latest', getLatestAction);
router.post('/actions/:actionId/undo', undoAction);

export default router;
