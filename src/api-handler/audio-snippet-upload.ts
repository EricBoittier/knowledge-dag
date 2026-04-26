import * as crypto from "crypto";
import * as fs from "fs";
import * as path from "path";
import * as rawExpress from "express";
import * as sql from "@squill/squill";
import * as express from "route-express";
import * as dao from "../dao";

const SNIPPET_ROOT = path.join("data", "audio-snippets");

export interface InitAudioSnippetUploadArgs {
    readonly app : express.ParentApp<{}>;
    readonly pool : sql.IPool;
    readonly accessToken : string;
}

function extensionFromContentType (contentType : string | undefined) : string {
    if (contentType == undefined) {
        return "webm";
    }
    const base = contentType.split(";")[0].trim().toLowerCase();
    if (base.includes("wav")) {
        return "wav";
    }
    if (base.includes("mpeg") || base.includes("mp3")) {
        return "mp3";
    }
    if (base.includes("ogg")) {
        return "ogg";
    }
    if (base.includes("webm")) {
        return "webm";
    }
    if (base.includes("mp4") || base.includes("m4a")) {
        return "m4a";
    }
    return "webm";
}

export function initAudioSnippetUpload (args : InitAudioSnippetUploadArgs) : void {
    const { app, pool, accessToken } = args;
    const router = rawExpress.Router();
    router.post(
        "/node/:nodeId(\\d+)/source/audio-snippet",
        rawExpress.raw({
            limit : "32mb",
            type : "*/*",
        }),
        (req, res, next) => {
            void (async () => {
                const userToken = req.headers["access-token"];
                if (userToken !== accessToken) {
                    res.status(401).end();
                    return;
                }
                const nodeIdStr = req.params.nodeId;
                const nodeId = BigInt(nodeIdStr);
                const body = req.body as Buffer;
                if (body == undefined || body.length === 0) {
                    res.status(400).json({
                        errors : [{ detail : "Empty audio body" }],
                    });
                    return;
                }
                const ext = extensionFromContentType(req.headers["content-type"]);
                const id = crypto.randomBytes(16).toString("hex");
                const relativePath = `${nodeIdStr}/${id}.${ext}`;
                const absPath = path.join(
                    process.cwd(),
                    SNIPPET_ROOT,
                    nodeIdStr,
                    `${id}.${ext}`
                );
                await fs.promises.mkdir(path.dirname(absPath), { recursive : true });
                await fs.promises.writeFile(absPath, body);

                let title = "";
                let excerpt = "";
                const metaHeader = req.headers["x-audio-meta"];
                if (typeof metaHeader == "string" && metaHeader.length > 0) {
                    try {
                        const parsed = JSON.parse(
                            Buffer.from(metaHeader, "base64").toString("utf8")
                        ) as { title? : string; transcript? : string };
                        if (typeof parsed.title == "string") {
                            title = parsed.title.slice(0, 255);
                        }
                        if (typeof parsed.transcript == "string") {
                            excerpt = parsed.transcript;
                        }
                    } catch {
                        res.status(400).json({
                            errors : [{ detail : "Invalid x-audio-meta (base64 JSON)" }],
                        });
                        await fs.promises.unlink(absPath).catch(() => {});
                        return;
                    }
                }

                try {
                    const row = await pool.acquireTransaction(
                        sql.IsolationLevel.REPEATABLE_READ,
                        (connection) => {
                            return dao.source.create(
                                connection,
                                {
                                    nodeId,
                                    sourceType : "audio",
                                    url : "",
                                    title : (
                                        title.length > 0 ?
                                        title :
                                        `snippet-${id}.${ext}`
                                    ),
                                    excerpt,
                                    filePath : relativePath,
                                }
                            );
                        }
                    );
                    res.json(row as any);
                } catch (err) {
                    await fs.promises.unlink(absPath).catch(() => {});
                    throw err;
                }
            })().catch(next);
        }
    );
    (app as unknown as rawExpress.Express).use(router);
}
