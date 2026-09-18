import { z } from "zod";

export const undoSortActionSchema = z.object({
    buckets: z
        .array(z.string().trim().min(1))
        .min(1, "buckets must contain at least one bucket name")
        .refine(names => new Set(names).size === names.length, {
            message: "buckets must not contain duplicates",
        }),
});

export type UndoSortActionRequest = z.infer<typeof undoSortActionSchema>;
