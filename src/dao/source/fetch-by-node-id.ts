import * as sql from "@squill/squill";
import * as table from "../../table";

export async function fetchByNodeId (
    connection : sql.SelectConnection,
    nodeId : bigint
) {
    const rows = await sql
        .from(table.source)
        .whereEq(columns => columns.nodeId, nodeId)
        .orderBy(columns => [
            columns.capturedAt.desc(),
            columns.createdAt.desc(),
            columns.sourceId.desc(),
        ])
        .select(columns => [
            columns.sourceId,
            columns.nodeId,
            columns.sourceType,
            columns.url,
            columns.title,
            columns.excerpt,
            columns.filePath,
            columns.capturedAt,
            columns.createdAt,
        ])
        .fetchAll(connection);
    return rows;
}
