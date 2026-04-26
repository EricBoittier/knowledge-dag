import * as tm from "type-mapping/fluent";
import * as m from "../mapper";

export const source = tm.object(
    m.source.sourceId,
    m.source.nodeId,
    m.source.sourceType,
    m.source.url,
    m.source.title,
    m.source.excerpt,
    m.source.filePath,
    m.source.capturedAt,
    m.source.createdAt,
);
export type Source = ReturnType<typeof source>;
export type SourceType = m.SourceType;

export const createSourceBody = tm.object(
    m.source.sourceType,
    m.source.url,
    m.source.title,
    m.source.excerpt,
    m.source.filePath,
    m.source.capturedAt.optional(),
);
export type CreateSourceBody = ReturnType<typeof createSourceBody>;
