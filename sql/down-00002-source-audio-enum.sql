DELETE FROM `source` WHERE `sourceType` = 'audio';

ALTER TABLE `source`
    MODIFY COLUMN `sourceType` ENUM ('url', 'pdf', 'image', 'note') COLLATE utf8mb4_unicode_ci NOT NULL;
