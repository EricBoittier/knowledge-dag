import * as tm from "type-mapping/fluent";
import * as rd from "../route-declaration";
import * as rc from "route-client";
import * as mapper from "../mapper";
import * as apiMapper from "../api-mapper";

export const SourceApi = rc.toAxiosApi({
    create : rd.route()
        .setMethod("POST")
        .append("/node")
        .appendParam(mapper.node.nodeId, /\d+/)
        .append("/source")
        .setHeader(apiMapper.auth)
        .setBody(apiMapper.createSourceBody)
        .setResponse(apiMapper.source),

    fetchByNode : rd.route()
        .setMethod("GET")
        .append("/node")
        .appendParam(mapper.node.nodeId, /\d+/)
        .append("/source")
        .setResponse(tm.array(apiMapper.source)),
});

export type SourceApi = InstanceType<typeof SourceApi>;
