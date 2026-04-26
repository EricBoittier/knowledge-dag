ALTER TABLE `source`
    MODIFY COLUMN `sourceType` ENUM ('url', 'pdf', 'image', 'note', 'audio') COLLATE utf8mb4_unicode_ci NOT NULL;
