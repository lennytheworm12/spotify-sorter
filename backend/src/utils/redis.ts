//file to set up redis connection on boot



import Redis from "ioredis";
import { env } from "../env";

const redis = new Redis(env.REDIS_URI);
redis.on("connect", () => console.log("redis connected"));
redis.on("error", (err) => console.error("failed to connect redis", err));

export default redis;
