-- Enron Eval 数据库结构（仅建库建表，不包含数据）
-- 适用于 MySQL 8.0+

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS `enron_eval`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

USE `enron_eval`;

CREATE TABLE IF NOT EXISTS `enron_email` (
  `id` int DEFAULT NULL COMMENT '邮件唯一编号；本表逻辑主键，并与其他五张表的id逻辑关联',
  `people` text COMMENT '邮件所属员工的目录标识，例如campbell-l',
  `mailbox` text COMMENT '邮件所在的邮箱文件夹标识，例如all_documents',
  `nnn` int DEFAULT NULL COMMENT '邮件在所属员工及邮箱文件夹中的原始序号；不是邮件总数'
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Enron邮件位置索引；每行对应一封邮件，记录其所属员工目录、邮箱文件夹及原始序号';

CREATE TABLE IF NOT EXISTS `enron_emailinfo` (
  `id` int DEFAULT NULL COMMENT '当前邮件编号；逻辑关联enron_email.id',
  `messageid` text COMMENT '当前邮件原始Message-ID邮件头值',
  `date` text COMMENT '当前邮件原始Date邮件头文本，包含时区且未转换为日期类型',
  `subject` text COMMENT '当前邮件主题',
  `from` text COMMENT '当前邮件From头解析出的发件地址',
  `to` text COMMENT '当前邮件To头中的收件地址汇总文本；单个地址见enron_emailto',
  `xfrom` text COMMENT '当前邮件X-From头中的原始发件人显示值，可能为姓名、邮箱或内部地址',
  `xto` text COMMENT '当前邮件X-To头中的原始收件人显示值汇总；单个显示值见enron_emailxto',
  `body` mediumtext COMMENT '当前邮件完整正文，可能包含回复或转发时引用的历史邮件内容',
  KEY `idx_emailinfo_from` (`from`(100))
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='当前邮件的主要邮件头和正文；每个id通常对应一封当前邮件';

CREATE TABLE IF NOT EXISTS `enron_emailorig` (
  `id` int DEFAULT NULL COMMENT '包含该历史引用块的当前外层邮件编号；逻辑关联enron_email.id',
  `nth` int DEFAULT NULL COMMENT '历史邮件头在当前邮件正文中的引用层次或出现序号，从1开始',
  `subject` text COMMENT '引用的历史邮件主题',
  `from` text COMMENT '引用的历史邮件From头值',
  `to` text COMMENT '引用的历史邮件To头值',
  `xfrom` text COMMENT '引用的历史邮件X-From头原始显示值',
  `xto` text COMMENT '引用的历史邮件X-To头原始显示值'
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='从当前邮件正文的Original Message等引用块中解析出的历史邮件头；不是当前邮件头';

CREATE TABLE IF NOT EXISTS `enron_emailto` (
  `id` int DEFAULT NULL COMMENT '当前邮件编号；逻辑关联enron_email.id',
  `nthto` int DEFAULT NULL COMMENT '该收件地址在当前邮件To列表中的顺序，从1开始',
  `to` text COMMENT '当前邮件的单个收件地址，通常为邮箱，也可能为列表或非标准地址',
  KEY `idx_emailto_id` (`id`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='当前邮件To收件地址明细；将enron_emailinfo.to中的多个地址拆为多行';

CREATE TABLE IF NOT EXISTS `enron_emailxto` (
  `id` int DEFAULT NULL COMMENT '当前邮件编号；逻辑关联enron_email.id',
  `nthxto` int DEFAULT NULL COMMENT '该原始收件人显示值在当前邮件X-To列表中的顺序，从1开始',
  `xto` text COMMENT '当前邮件的单个X-To原始显示值，可能为姓名、邮箱、群组或内部地址',
  KEY `idx_emailxto_id` (`id`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='当前邮件X-To原始收件人显示值明细；不保证与enron_emailto逐行一一对应';

CREATE TABLE IF NOT EXISTS `enron_source` (
  `id` int DEFAULT NULL COMMENT '当前邮件编号；逻辑关联enron_email.id',
  `source_file_id` text COMMENT '导入数据中用于标识源记录或源文件的唯一标识',
  `source_name` text COMMENT '组合源名称，通常由people、mailbox和nnn以@连接组成',
  `xfilename` text COMMENT '原始邮件数据库或源文件名，例如lcampbel.nsf',
  `xfolder` text COMMENT '原始Lotus Notes邮箱文件夹路径或文件夹描述',
  `xorigin` text COMMENT '邮件来源员工的原始目录标识，例如Campbell-L',
  KEY `idx_source_id` (`id`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci
  COMMENT='邮件数据来源及原始Enron或Lotus Notes文件位置信息；每个id通常对应一封邮件';
