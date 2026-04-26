import * as migrator from "agnostic-migrator";
import * as sql from "@squill/squill";
import {sqlMigrationFactory} from "./sql-migration";

export function buildMigrations (pool : sql.IPool) : readonly migrator.Migration[] {
    const sqlMigration = sqlMigrationFactory(pool);

    const migrations : readonly migrator.Migration[] = [
        sqlMigration("00000-initial-structure"),
        sqlMigration("00001-source"),
        sqlMigration("00002-source-audio-enum"),
    ];

    return migrations;
}
