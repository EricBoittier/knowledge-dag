import * as sql from "@squill/squill";
import * as m from "../mapper";

export const source = sql.table("source")
    .addColumns(m.source)
    .setAutoIncrement(columns => columns.sourceId)
    .addExplicitDefaultValue(columns => [
        columns.capturedAt,
        columns.createdAt,
    ])
    .addMutable(columns => [
        columns.sourceType,
        columns.url,
        columns.title,
        columns.excerpt,
        columns.filePath,
        columns.capturedAt,
    ]);
