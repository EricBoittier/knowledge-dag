import * as sql from "@squill/squill";
import * as table from "../../table";

export async function create (
    connection : sql.IsolableInsertOneConnection,
    args : {
        readonly nodeId : bigint,
        readonly sourceType : string,
        readonly url : string,
        readonly title : string,
        readonly excerpt : string,
        readonly filePath : string,
        readonly capturedAt? : Date,
    }
) {
    const row = await table.source.insertAndFetch(
        connection,
        {
            nodeId : args.nodeId,
            sourceType : args.sourceType,
            url : args.url,
            title : args.title,
            excerpt : args.excerpt,
            filePath : args.filePath,
            capturedAt : args.capturedAt,
        }
    );
    return row;
}
