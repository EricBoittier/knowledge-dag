CREATE TABLE `source` (
    `sourceId` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT ,
    `nodeId` BIGINT UNSIGNED NOT NULL ,
    `sourceType` ENUM ('url', 'pdf', 'image', 'note') COLLATE utf8mb4_unicode_ci NOT NULL ,
    `url` VARCHAR(2048) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' ,
    `title` VARCHAR(255) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' ,
    `excerpt` TEXT COLLATE utf8mb4_unicode_ci NOT NULL ,
    `filePath` VARCHAR(2048) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT '' ,
    `capturedAt` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ,
    `createdAt` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ,
    PRIMARY KEY (`sourceId`)
) ENGINE = InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE `source`
    ADD CONSTRAINT `source_node`
    FOREIGN KEY (`nodeId`)
    REFERENCES `node`(`nodeId`)
    ON DELETE RESTRICT
    ON UPDATE RESTRICT;

CREATE INDEX `source_nodeId_createdAt` ON `source` (`nodeId`, `createdAt`);
