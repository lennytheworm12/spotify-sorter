import { z } from "zod";

export const sortRequestSchema = z
    .object({
        sourceType: z.enum(["liked", "playlist"], {
            message: "sourceType must be 'liked' or 'playlist'",
        }),
        outputMode: z.enum(["auto-create", "sort-into-existing"], {
            message: "outputMode must be 'auto-create' or 'sort-into-existing'",
        }),
        existingPlaylistWriteMode: z
            .enum(["copy", "direct"], {
                message: "existingPlaylistWriteMode must be 'copy' or 'direct'",
            })
            .optional(),
        playlistId: z.string().trim().min(1).optional(),
        editablePlaylistIds: z
            .array(z.string().trim().min(1))
            .min(1, "editablePlaylistIds must contain at least one playlist id")
            .optional(),
        // Optional per-destination names for safe-copy clones. Keys must be
        // original destination playlist ids selected via editablePlaylistIds;
        // values are trimmed, nonblank, and at most 100 characters. Omitted
        // keys keep the automatic "{original} — Spotify Sorter Copy" fallback.
        safeCopyNames: z
            .record(
                z.string(),
                z
                    .string()
                    .trim()
                    .min(1, "safe copy name must not be blank")
                    .max(100, "safe copy name must be at most 100 characters")
            )
            .optional(),
        createBackup: z.boolean().optional(),
    })
    .superRefine((data, ctx) => {
        if (data.sourceType === "playlist" && !data.playlistId) {
            ctx.addIssue({
                code: z.ZodIssueCode.custom,
                path: ["playlistId"],
                message: "playlistId is required when sourceType is playlist",
            });
        }
        if (data.outputMode === "sort-into-existing" && !data.editablePlaylistIds) {
            ctx.addIssue({
                code: z.ZodIssueCode.custom,
                path: ["editablePlaylistIds"],
                message: "editablePlaylistIds are required for sort-into-existing mode",
            });
        }
        if (data.sourceType === "liked" && data.createBackup) {
            ctx.addIssue({
                code: z.ZodIssueCode.custom,
                path: ["createBackup"],
                message: "createBackup is only valid when sourceType is playlist",
            });
        }
        if (data.outputMode === "auto-create" && data.existingPlaylistWriteMode) {
            ctx.addIssue({
                code: z.ZodIssueCode.custom,
                path: ["existingPlaylistWriteMode"],
                message:
                    "existingPlaylistWriteMode is only valid when outputMode is sort-into-existing",
            });
        }
        if (data.safeCopyNames && data.outputMode !== "sort-into-existing") {
            ctx.addIssue({
                code: z.ZodIssueCode.custom,
                path: ["safeCopyNames"],
                message: "safeCopyNames is only valid when outputMode is sort-into-existing",
            });
        }
        if (
            data.safeCopyNames &&
            data.outputMode === "sort-into-existing" &&
            (data.existingPlaylistWriteMode ?? "copy") !== "copy"
        ) {
            ctx.addIssue({
                code: z.ZodIssueCode.custom,
                path: ["safeCopyNames"],
                message:
                    "safeCopyNames is only valid when existingPlaylistWriteMode is copy",
            });
        }
        if (data.safeCopyNames) {
            for (const key of Object.keys(data.safeCopyNames)) {
                if (!data.editablePlaylistIds?.includes(key)) {
                    ctx.addIssue({
                        code: z.ZodIssueCode.custom,
                        path: ["safeCopyNames", key],
                        message: `safeCopyNames key '${key}' is not in editablePlaylistIds`,
                    });
                }
            }
        }
        if (
            data.sourceType === "playlist" &&
            data.outputMode === "sort-into-existing" &&
            data.playlistId &&
            data.editablePlaylistIds?.includes(data.playlistId)
        ) {
            ctx.addIssue({
                code: z.ZodIssueCode.custom,
                path: ["editablePlaylistIds"],
                message: "source playlist cannot be a destination",
            });
        }
    })
    // Default existing-mode writes to cloning so clients that omit the field
    // can never mutate the selected originals.
    .transform((data) => ({
        ...data,
        existingPlaylistWriteMode:
            data.outputMode === "sort-into-existing"
                ? (data.existingPlaylistWriteMode ?? "copy")
                : undefined,
    }));

export type SortRequest = z.infer<typeof sortRequestSchema>;
