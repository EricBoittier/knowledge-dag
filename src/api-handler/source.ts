import * as sql from "@squill/squill";
import {RouteInitDelegate} from "./route-init-delegate";
import {SourceApi} from "../api";
import * as dao from "../dao";

export const initSource : RouteInitDelegate = ({app, pool}) => {
    app.createRoute(SourceApi.routes.create)
        .asyncVoidHandler((req, res) => pool
            .acquireTransaction(
                sql.IsolationLevel.REPEATABLE_READ,
                connection => dao.source.create(
                    connection,
                    {
                        ...req.params,
                        ...req.body,
                    }
                )
            )
            .then((row) => {
                res.json(row as any);
            })
        );

    app.createRoute(SourceApi.routes.fetchByNode)
        .asyncVoidHandler((req, res) => pool
            .acquireReadOnlyTransaction(
                sql.IsolationLevel.REPEATABLE_READ,
                connection => dao.source.fetchByNodeId(
                    connection,
                    req.params.nodeId
                )
            )
            .then((rows) => {
                res.json(rows as any);
            })
        );
};
