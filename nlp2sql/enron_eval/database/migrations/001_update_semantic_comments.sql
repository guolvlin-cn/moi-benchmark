ALTER TABLE `enron_email`
  COMMENT = 'Enron邮件位置索引；每行对应一封邮件，记录其所属员工目录、邮箱文件夹及原始序号',
  MODIFY COLUMN `id` int DEFAULT NULL COMMENT '邮件唯一编号；本表逻辑主键，并与其他五张表的id逻辑关联',
  MODIFY COLUMN `people` text COMMENT '邮件所属员工的目录标识，例如campbell-l',
  MODIFY COLUMN `mailbox` text COMMENT '邮件所在的邮箱文件夹标识，例如all_documents',
  MODIFY COLUMN `nnn` int DEFAULT NULL COMMENT '邮件在所属员工及邮箱文件夹中的原始序号；不是邮件总数';

ALTER TABLE `enron_emailinfo`
  COMMENT = '当前邮件的主要邮件头和正文；每个id通常对应一封当前邮件',
  MODIFY COLUMN `id` int DEFAULT NULL COMMENT '当前邮件编号；逻辑关联enron_email.id',
  MODIFY COLUMN `messageid` text COMMENT '当前邮件原始Message-ID邮件头值',
  MODIFY COLUMN `date` text COMMENT '当前邮件原始Date邮件头文本，包含时区且未转换为日期类型',
  MODIFY COLUMN `subject` text COMMENT '当前邮件主题',
  MODIFY COLUMN `from` text COMMENT '当前邮件From头解析出的发件地址',
  MODIFY COLUMN `to` text COMMENT '当前邮件To头中的收件地址汇总文本；单个地址见enron_emailto',
  MODIFY COLUMN `xfrom` text COMMENT '当前邮件X-From头中的原始发件人显示值，可能为姓名、邮箱或内部地址',
  MODIFY COLUMN `xto` text COMMENT '当前邮件X-To头中的原始收件人显示值汇总；单个显示值见enron_emailxto',
  MODIFY COLUMN `body` mediumtext COMMENT '当前邮件完整正文，可能包含回复或转发时引用的历史邮件内容';

ALTER TABLE `enron_emailorig`
  COMMENT = '从当前邮件正文的Original Message等引用块中解析出的历史邮件头；不是当前邮件头',
  MODIFY COLUMN `id` int DEFAULT NULL COMMENT '包含该历史引用块的当前外层邮件编号；逻辑关联enron_email.id',
  MODIFY COLUMN `nth` int DEFAULT NULL COMMENT '历史邮件头在当前邮件正文中的引用层次或出现序号，从1开始',
  MODIFY COLUMN `subject` text COMMENT '引用的历史邮件主题',
  MODIFY COLUMN `from` text COMMENT '引用的历史邮件From头值',
  MODIFY COLUMN `to` text COMMENT '引用的历史邮件To头值',
  MODIFY COLUMN `xfrom` text COMMENT '引用的历史邮件X-From头原始显示值',
  MODIFY COLUMN `xto` text COMMENT '引用的历史邮件X-To头原始显示值';

ALTER TABLE `enron_emailto`
  COMMENT = '当前邮件To收件地址明细；将enron_emailinfo.to中的多个地址拆为多行',
  MODIFY COLUMN `id` int DEFAULT NULL COMMENT '当前邮件编号；逻辑关联enron_email.id',
  MODIFY COLUMN `nthto` int DEFAULT NULL COMMENT '该收件地址在当前邮件To列表中的顺序，从1开始',
  MODIFY COLUMN `to` text COMMENT '当前邮件的单个收件地址，通常为邮箱，也可能为列表或非标准地址';

ALTER TABLE `enron_emailxto`
  COMMENT = '当前邮件X-To原始收件人显示值明细；不保证与enron_emailto逐行一一对应',
  MODIFY COLUMN `id` int DEFAULT NULL COMMENT '当前邮件编号；逻辑关联enron_email.id',
  MODIFY COLUMN `nthxto` int DEFAULT NULL COMMENT '该原始收件人显示值在当前邮件X-To列表中的顺序，从1开始',
  MODIFY COLUMN `xto` text COMMENT '当前邮件的单个X-To原始显示值，可能为姓名、邮箱、群组或内部地址';

ALTER TABLE `enron_source`
  COMMENT = '邮件数据来源及原始Enron或Lotus Notes文件位置信息；每个id通常对应一封邮件',
  MODIFY COLUMN `id` int DEFAULT NULL COMMENT '当前邮件编号；逻辑关联enron_email.id',
  MODIFY COLUMN `source_file_id` text COMMENT '导入数据中用于标识源记录或源文件的唯一标识',
  MODIFY COLUMN `source_name` text COMMENT '组合源名称，通常由people、mailbox和nnn以@连接组成',
  MODIFY COLUMN `xfilename` text COMMENT '原始邮件数据库或源文件名，例如lcampbel.nsf',
  MODIFY COLUMN `xfolder` text COMMENT '原始Lotus Notes邮箱文件夹路径或文件夹描述',
  MODIFY COLUMN `xorigin` text COMMENT '邮件来源员工的原始目录标识，例如Campbell-L';
