import * as tm from "type-mapping/fluent";
import {sourceId, nodeId} from "./id";
import {createdAt} from "./date-time";

export const sourceType = tm.mysql.varChar(1, 16);
export type SourceType = "url"|"pdf"|"image"|"note"|"audio";

export const source = tm.fields({
    sourceId,
    nodeId,
    sourceType,
    url : tm.mysql.varChar(0, 2048),
    title : tm.mysql.varChar(0, 255),
    excerpt : tm.mysql.text(),
    filePath : tm.mysql.varChar(0, 2048),
    capturedAt : createdAt,
    createdAt,
});
