-- MOI Enron 50 NL2SQL run with semantic configuration
-- Run: 2026-08-07_moi_with_semantic_01
-- Generated/executed successfully: 45; generation_error with captured candidate SQL: 5
-- WARNING: generation_error statements are retained for diagnosis and did not complete successfully in MOI.

-- e01_sender_count | ok
-- Question: 这个邮件库里一共有多少个不同的发件邮箱？
SELECT COUNT(DISTINCT `from`) AS distinct_sender_count FROM enron_emailinfo;

-- e02_total_emails | ok
-- Question: 这个库总共有多少封邮件？
SELECT COUNT(DISTINCT id) AS total_emails FROM enron_email;

-- e03_empty_subject | ok
-- Question: 哪些邮件的主题为空？空主题定义为subject为NULL或去除首尾空格后为空字符串；列出邮件ID、messageid和发件地址，按邮件ID升序排列。
SELECT
    e.id AS `邮件ID`,
    ei.messageid AS `messageid`,
    ei.`from` AS `发件地址`
FROM enron_email e
JOIN enron_emailinfo ei ON e.id = ei.id
WHERE ei.subject IS NULL OR TRIM(ei.subject) = ''
ORDER BY e.id ASC;

-- e04_reply_emails | ok
-- Question: 有多少封邮件是回复邮件？
SELECT COUNT(*) AS reply_count FROM enron_emailinfo WHERE TRIM(`subject`) LIKE 'Re:%';

-- e05_phillip_emails | ok
-- Question: Phillip Allen一共发了多少封邮件？
SELECT COUNT(DISTINCT `id`) AS sent_count
FROM enron_emailinfo
WHERE `from` = 'phillip.allen@enron.com';

-- e06_top10_mailboxes | generation_error
-- Question: 邮件最多的10个邮箱文件夹是哪些？
-- MOI error: query_sql: query sql: query_sql count: catalog knowledge sql executor: query failed: Error 1064 (HY000): SQL parser error: You have an error in your SQL syntax; check the manual that corresponds to your MatrixOne server version for the right syntax to use. syntax error at line 3 column 17 near " 邮箱文件夹, COUNT(*) AS 邮件数量 FROM enron_email GROUP BY mailbox ORDER BY 邮件数量 DESC LIMIT 10 ) AS query_sql_count_source";
SELECT
    mailbox AS folder,
    COUNT(*) AS cnt
FROM enron_email
GROUP BY mailbox
ORDER BY cnt DESC
LIMIT 10;

-- e07_sent_mail_count | ok
-- Question: sent文件夹里有多少封邮件？
SELECT COUNT(*) AS sent_count FROM enron_email WHERE mailbox = 'sent';

-- e08_california_emails | ok
-- Question: 有多少封邮件的正文提到了California？
SELECT COUNT(DISTINCT id) AS email_count
FROM enron_emailinfo
WHERE body IS NOT NULL
  AND TRIM(body) != ''
  AND LOWER(body) LIKE '%california%';

-- e09_source_identifiers | ok
-- Question: 列出邮件ID最小的10条来源记录，返回邮件ID、source_file_id和source_name，按邮件ID升序排列；source_file_id是源记录唯一标识，source_name是由邮件归档位置组成的源名称。
SELECT id, source_file_id, source_name
FROM enron_source
ORDER BY id ASC
LIMIT 10;

-- e10_distinct_mailboxes | ok
-- Question: 列出所有非NULL且非空的不重复邮箱文件夹名称，按文件夹名升序排列。
SELECT DISTINCT mailbox
FROM enron_email
WHERE mailbox IS NOT NULL AND TRIM(mailbox) <> ''
ORDER BY mailbox ASC;

-- e11_latest_emails | ok
-- Question: 最近发出的10封邮件是什么？给我日期、主题和发件人。
SELECT e.id, i.date, i.subject, i.`from`
FROM enron_email e
JOIN enron_emailinfo i ON e.id = i.id
WHERE e.mailbox = 'sent'
ORDER BY i.date DESC
LIMIT 10;

-- e12_2001_email_count | ok
-- Question: 原始Date邮件头显示年份为2001年的邮件共有多少封？按不同邮件ID计数。
SELECT COUNT(DISTINCT id) AS email_count_2001
FROM enron_emailinfo
WHERE date LIKE '%2001%';

-- e13_orig_extended_header_presence | ok
-- Question: 在正文引用的历史邮件头中，分别有多少行包含非空xfrom和非空xto？返回xfrom非空行数和xto非空行数；这里使用enron_emailorig中的字段，而不是当前邮件的enron_emailinfo字段。
SELECT
  COUNT(CASE WHEN xfrom IS NOT NULL AND TRIM(xfrom) != '' THEN 1 END) AS xfrom_nonempty_count,
  COUNT(CASE WHEN xto IS NOT NULL AND TRIM(xto) != '' THEN 1 END) AS xto_nonempty_count
FROM enron_emailorig;

-- e14_people_list | ok
-- Question: 这个邮件库包含哪些员工的邮件目录？
SELECT DISTINCT people FROM enron_email ORDER BY people;

-- e15_campbell_mailboxes | ok
-- Question: campbell-l员工目录中有多少个不同的非空邮箱文件夹？
SELECT COUNT(DISTINCT `mailbox`) AS distinct_nonempty_mailbox_count
FROM enron_email
WHERE `people` = 'campbell-l'
  AND `mailbox` IS NOT NULL
  AND TRIM(`mailbox`) <> '';

-- e16_max_mail_count | ok
-- Question: 将所有员工目录合并后，单个mailbox名称保存的不同邮件ID数量最大是多少？只返回最大数量。
SELECT COUNT(DISTINCT id) AS cnt
FROM enron_email
GROUP BY mailbox
ORDER BY cnt DESC
LIMIT 1;

-- e17_subject_keyword_meeting | ok
-- Question: 有多少封邮件的主题提到了meeting？
SELECT COUNT(DISTINCT id) AS email_count
FROM enron_emailinfo
WHERE LOWER(TRIM(Subject)) LIKE '%meeting%';

-- e18_senders_more_than_100 | ok
-- Question: 哪些有效发件地址发送了超过100封邮件？发件地址先去除首尾空格并转为小写，忽略NULL和空字符串；列出发件地址和不同邮件ID数量，先按数量降序、再按地址升序排列。
SELECT
    LOWER(TRIM(`from`)) AS sender_address,
    COUNT(DISTINCT id) AS email_count
FROM enron_emailinfo
WHERE `from` IS NOT NULL
  AND TRIM(`from`) <> ''
GROUP BY LOWER(TRIM(`from`))
HAVING COUNT(DISTINCT id) > 100
ORDER BY email_count DESC, sender_address ASC;

-- e19_top_xfrom | ok
-- Question: 当前邮件中最常见的10个非空X-From原始发件人显示值是什么？对xfrom去除首尾空格后分组，列出显示值和不同邮件ID数量，先按数量降序、再按显示值升序排列。
SELECT
    TRIM(`xfrom`) AS `xfrom_display`,
    COUNT(DISTINCT `id`) AS `email_count`
FROM `enron_emailinfo`
WHERE `xfrom` IS NOT NULL AND TRIM(`xfrom`) != ''
GROUP BY TRIM(`xfrom`)
ORDER BY `email_count` DESC, `xfrom_display` ASC
LIMIT 10;

-- e20_campbell_source_sequence | ok
-- Question: 列出campbell-l员工目录中all_documents文件夹里原始序号nnn最大的10封邮件，返回邮件ID、nnn、主题和标准发件地址，按nnn降序、邮件ID降序排列；nnn表示原始序号，不是邮件数量。
SELECT
    e.id,
    e.nnn,
    i.Subject,
    i.`from`
FROM enron_email e
JOIN enron_emailinfo i ON e.id = i.id
WHERE e.people = 'campbell-l'
  AND e.mailbox = 'all_documents'
ORDER BY e.nnn DESC, e.id DESC
LIMIT 10;

-- m01_owner_folder_distribution | generation_error
-- Question: 各员工的邮件都分布在哪些文件夹？按邮件量从多到少列出来。
-- MOI error: query_sql: query sql: query_sql count: catalog knowledge sql executor: query failed: Error 1064 (HY000): SQL parser error: You have an error in your SQL syntax; check the manual that corresponds to your MatrixOne server version for the right syntax to use. syntax error at line 3 column 16 near " 员工, mailbox AS 文件夹, COUNT(*) AS 邮件量 FROM enron_email GROUP BY people, mailbox ORDER BY COUNT(*) DESC ) AS query_sql_count_source";
SELECT
    people,
    mailbox,
    COUNT(*) AS cnt
FROM enron_email
GROUP BY people, mailbox
ORDER BY COUNT(*) DESC;

-- m02_phillip_recipients | ok
-- Question: Phillip Allen最常给哪些邮箱发邮件？列出前10个。
WITH allen_sent AS (
    SELECT DISTINCT ei.id
    FROM enron_emailinfo ei
    WHERE ei.`from` = 'phillip.allen@enron.com'
)
SELECT
    et.`to` AS recipient_email,
    COUNT(DISTINCT et.id) AS email_count
FROM allen_sent a
JOIN enron_emailto et ON a.id = et.id
GROUP BY et.`to`
ORDER BY email_count DESC, et.`to` ASC
LIMIT 10;

-- m03_california_senders | ok
-- Question: 哪些人发的邮件正文最常提到California？列出前5名。
SELECT
    `from` AS sender,
    COUNT(DISTINCT id) AS email_count
FROM enron_emailinfo
WHERE LOWER(body) LIKE '%california%'
  AND TRIM(body) IS NOT NULL
  AND TRIM(body) <> ''
GROUP BY `from`
ORDER BY email_count DESC
LIMIT 5;

-- m04_employee_source_folders | ok
-- Question: 每个非空来源员工标识xorigin关联了多少个不同的非空原始Lotus Notes文件夹描述xfolder？列出xorigin和文件夹数量，先按数量降序、再按xorigin升序排列。
SELECT
    xorigin,
    COUNT(DISTINCT xfolder) AS folder_count
FROM enron_source
WHERE xorigin IS NOT NULL AND TRIM(xorigin) != ''
  AND xfolder IS NOT NULL AND TRIM(xfolder) != ''
GROUP BY xorigin
ORDER BY folder_count DESC, xorigin ASC;

-- m05_avg_recipients_per_email | ok
-- Question: 哪些发件人的邮件平均会发给3个人以上？按平均收件人数从高到低排列。
WITH recipient_counts AS (
  SELECT
    t.id,
    COUNT(*) AS num_recipients
  FROM enron_emailto t
  GROUP BY t.id
)
SELECT
  i.`from` AS sender,
  AVG(rc.num_recipients) AS avg_recipients
FROM enron_emailinfo i
JOIN recipient_counts rc ON i.id = rc.id
GROUP BY i.`from`
HAVING AVG(rc.num_recipients) > 3
ORDER BY avg_recipients DESC;

-- m06_sent_vs_total | ok
-- Question: 名称恰好为sent的文件夹中，不同邮件ID数量占全库不同邮件ID总数的百分比是多少？结果乘以100并保留2位小数，不包括_sent_mail或sent_items。
SELECT
  ROUND(
    COUNT(DISTINCT CASE WHEN mailbox = 'sent' THEN id END) * 100.0 /
    COUNT(DISTINCT id),
    2
  ) AS percentage
FROM enron_email;

-- m07_most_common_recipient | ok
-- Question: 整个邮件库里，哪个邮箱收到的邮件最多？
SELECT `to` AS recipient, COUNT(DISTINCT id) AS email_count
FROM enron_emailto
GROUP BY `to`
ORDER BY email_count DESC
LIMIT 1;

-- m08_2001_monthly_trend | ok
-- Question: 按原始Date邮件头显示的月份统计2001年每个月的不同邮件数，只列出数据中实际出现的月份；月份输出为01至12，按月份升序排列。
SELECT
    LPAD(
        CASE SUBSTRING_INDEX(SUBSTRING_INDEX(ei.`date`, ' ', 3), ' ', -1)
            WHEN 'Jan' THEN 1 WHEN 'Feb' THEN 2 WHEN 'Mar' THEN 3 WHEN 'Apr' THEN 4
            WHEN 'May' THEN 5 WHEN 'Jun' THEN 6 WHEN 'Jul' THEN 7 WHEN 'Aug' THEN 8
            WHEN 'Sep' THEN 9 WHEN 'Oct' THEN 10 WHEN 'Nov' THEN 11 WHEN 'Dec' THEN 12
        END,
        2, '0'
    ) AS month,
    COUNT(DISTINCT ei.id) AS email_count
FROM enron_emailinfo ei
WHERE ei.`date` IS NOT NULL
  AND SUBSTRING_INDEX(SUBSTRING_INDEX(ei.`date`, ' ', 4), ' ', -1) = '2001'
GROUP BY CASE SUBSTRING_INDEX(SUBSTRING_INDEX(ei.`date`, ' ', 3), ' ', -1)
            WHEN 'Jan' THEN 1 WHEN 'Feb' THEN 2 WHEN 'Mar' THEN 3 WHEN 'Apr' THEN 4
            WHEN 'May' THEN 5 WHEN 'Jun' THEN 6 WHEN 'Jul' THEN 7 WHEN 'Aug' THEN 8
            WHEN 'Sep' THEN 9 WHEN 'Oct' THEN 10 WHEN 'Nov' THEN 11 WHEN 'Dec' THEN 12
         END
ORDER BY month ASC;

-- m09_allen_folder_emails | ok
-- Question: Allen的邮件都放在哪些文件夹？每个文件夹有多少封？
SELECT mailbox AS folder, COUNT(*) AS email_count
FROM enron_email
WHERE people = 'allen-p'
GROUP BY mailbox
ORDER BY email_count DESC;

-- m10_phillip_reply_orig_senders | ok
-- Question: Phillip Allen回复过谁的邮件最多？列出前5名。
SELECT LOWER(TRIM(et.`to`)) AS recipient,
       COUNT(DISTINCT ei.id) AS email_count
FROM enron_emailinfo ei
JOIN enron_emailto et ON ei.id = et.id
WHERE LOWER(TRIM(ei.`from`)) = 'phillip.allen@enron.com'
  AND et.`to` IS NOT NULL
  AND TRIM(et.`to`) <> ''
GROUP BY LOWER(TRIM(et.`to`))
ORDER BY email_count DESC, LOWER(TRIM(et.`to`)) ASC
LIMIT 5;

-- m11_recipient_sequence_extremes | ok
-- Question: 哪些邮件的收件人序号范围最大？分别计算每封邮件enron_emailto中的最大nthto和enron_emailxto中的最大nthxto，缺失时按0处理；列出两者最大值较大的前10封邮件，返回邮件ID、主题、最大nthto和最大nthxto，先按两者中的较大值降序、再按邮件ID升序排列。
WITH
max_to AS (
    SELECT id, COALESCE(MAX(nthto), 0) AS max_nthto
    FROM enron_emailto
    GROUP BY id
),
max_xto AS (
    SELECT id, COALESCE(MAX(nthxto), 0) AS max_nthxto
    FROM enron_emailxto
    GROUP BY id
),
combined AS (
    SELECT
        i.id,
        i.subject,
        COALESCE(t.max_nthto, 0) AS max_nthto,
        COALESCE(x.max_nthxto, 0) AS max_nthxto,
        GREATEST(COALESCE(t.max_nthto, 0), COALESCE(x.max_nthxto, 0)) AS max_of_both
    FROM enron_emailinfo i
    LEFT JOIN max_to t ON i.id = t.id
    LEFT JOIN max_xto x ON i.id = x.id
)
SELECT id, subject, max_nthto, max_nthxto
FROM combined
ORDER BY max_of_both DESC, id ASC
LIMIT 10;

-- m12_enron_announcements | ok
-- Question: Enron公告邮箱最常把邮件发给哪些地址？列出前5个。
SELECT
    epto.`to` AS recipient_address,
    COUNT(DISTINCT ept.id) AS email_count
FROM enron_emailinfo ept
JOIN enron_emailto epto ON ept.id = epto.id
WHERE ept.`from` = 'enron.announcements@enron.com'
GROUP BY epto.`to`
ORDER BY email_count DESC, epto.`to` ASC
LIMIT 5;

-- m13_source_file_stats | ok
-- Question: 每个非空原始源文件名xfilename关联了多少封不同邮件？列出前5个文件名和不同邮件ID数量，先按数量降序、再按文件名升序排列。
SELECT
    s.xfilename,
    COUNT(DISTINCT s.id) AS email_count
FROM enron_source s
WHERE s.xfilename IS NOT NULL AND TRIM(s.xfilename) <> ''
GROUP BY s.xfilename
ORDER BY email_count DESC, s.xfilename ASC
LIMIT 5;

-- m14_recipient_representation_gap | ok
-- Question: 哪些邮件的标准To收件地址数量与X-To原始收件人显示值数量差异最大？分别统计enron_emailto中的不同规范化to值和enron_emailxto中的不同去空格xto值，缺失按0处理；列出绝对差值最大的10封邮件，返回邮件ID、两个数量、绝对差值，以及enron_emailinfo.to和enron_emailinfo.xto各自的前200个字符，先按绝对差值降序、再按邮件ID升序排列。
WITH to_counts AS (
    SELECT id, COUNT(DISTINCT `to`) AS to_count
    FROM enron_emailto
    GROUP BY id
),
xto_counts AS (
    SELECT id, COUNT(DISTINCT REPLACE(xto, ' ', '')) AS xto_count
    FROM enron_emailxto
    GROUP BY id
),
all_ids AS (
    SELECT DISTINCT id FROM enron_emailto
    UNION
    SELECT DISTINCT id FROM enron_emailxto
),
combined AS (
    SELECT a.id,
           COALESCE(t.to_count, 0) AS to_count,
           COALESCE(x.xto_count, 0) AS xto_count,
           ABS(COALESCE(t.to_count, 0) - COALESCE(x.xto_count, 0)) AS abs_diff
    FROM all_ids a
    LEFT JOIN to_counts t ON a.id = t.id
    LEFT JOIN xto_counts x ON a.id = x.id
)
SELECT c.id, c.to_count, c.xto_count, c.abs_diff,
       LEFT(i.`to`, 200) AS to_preview,
       LEFT(i.xto, 200) AS xto_preview
FROM combined c
LEFT JOIN enron_emailinfo i ON c.id = i.id
ORDER BY c.abs_diff DESC, c.id ASC
LIMIT 10;

-- m15_sender_with_most_recipients | generation_error
-- Question: 哪个有效发件地址的邮件总共涉及最多不同收件地址？对发件地址和收件地址都去除首尾空格并转为小写；返回发件地址和不同收件地址数，按数量降序、发件地址升序排列后只取第1行。
-- MOI error: query_sql: query sql: query_sql count: catalog knowledge sql executor: query failed: Error 20301 (HY000): invalid input: ambiguous column reference to 'to'
SELECT
    TRIM(LOWER(ei.`from`)) AS sender_address,
    COUNT(DISTINCT TRIM(LOWER(et.`to`))) AS distinct_recipient_count
FROM enron_emailinfo ei
JOIN enron_emailto et ON ei.id = et.id
WHERE ei.`from` IS NOT NULL AND TRIM(ei.`from`) <> ''
  AND et.`to` IS NOT NULL AND TRIM(et.`to`) <> ''
GROUP BY TRIM(LOWER(ei.`from`))
ORDER BY distinct_recipient_count DESC, sender_address ASC
LIMIT 1;

-- m16_deleted_items_owners | ok
-- Question: 哪些人的deleted_items文件夹里有邮件？分别有多少封？
SELECT people, COUNT(id) AS email_count
FROM enron_email
WHERE mailbox = 'deleted_items'
GROUP BY people
ORDER BY people;

-- m17_reply_orig_header_details | ok
-- Question: 列出主题去除首尾空格后忽略大小写以“Re:”开头、且存在nth=1历史邮件头的当前邮件；返回当前邮件ID、当前主题，以及nth=1历史邮件头的subject、from、to、xfrom和xto，按当前邮件ID升序排列。历史邮件头字段均来自enron_emailorig。
SELECT
    e.id AS current_mail_id,
    e.subject AS current_subject,
    o.subject AS hist_subject,
    o.`from` AS hist_from,
    o.`to` AS hist_to,
    o.xfrom AS hist_xfrom,
    o.xto AS hist_xto
FROM enron_emailinfo e
JOIN enron_emailorig o ON e.id = o.id AND o.nth = 1
WHERE UPPER(TRIM(e.subject)) LIKE 'RE:%'
ORDER BY e.id ASC;

-- m18_october_2001_recipients | ok
-- Question: 在原始Date邮件头显示为2001年10月的邮件中，哪些规范化收件地址收到的不同邮件最多？同一封邮件中的同一地址只计一次；列出前5个地址和不同邮件数，先按数量降序、再按地址升序排列。
WITH october_emails AS (
    SELECT DISTINCT ei.id
    FROM enron_emailinfo ei
    WHERE ei.date LIKE '%Oct 2001%'
),
recipient_distinct_counts AS (
    SELECT et.`to` AS recipient, COUNT(DISTINCT et.id) AS distinct_email_count
    FROM enron_emailto et
    INNER JOIN october_emails oe ON et.id = oe.id
    WHERE et.`to` IS NOT NULL AND TRIM(et.`to`) <> ''
    GROUP BY et.`to`
)
SELECT recipient, distinct_email_count
FROM recipient_distinct_counts
ORDER BY distinct_email_count DESC, recipient ASC
LIMIT 5;

-- m19_larry_inbox_count | ok
-- Question: larry.campbell@enron.com发送的邮件中，有多少封保存在名称恰好为inbox的文件夹？连接enron_email与enron_emailinfo，按不同邮件ID计数。
SELECT COUNT(DISTINCT ei.id) AS total_from_larry
FROM enron_emailinfo ei
WHERE ei.`from` = 'larry.campbell@enron.com';

-- m20_top_source_origins | ok
-- Question: 这个数据集主要来自哪些员工的邮箱？列出邮件最多的前5个来源。
SELECT `from` AS sender, COUNT(DISTINCT id) AS email_count
FROM enron_emailinfo
WHERE `from` IS NOT NULL AND TRIM(`from`) <> ''
GROUP BY `from`
ORDER BY email_count DESC
LIMIT 5;

-- h01_two_way_communication | ok
-- Question: 有多少个邮箱既发过邮件，也收过邮件？
SELECT COUNT(*) AS `count` FROM (
    SELECT DISTINCT `from` FROM enron_emailinfo
    INTERSECT
    SELECT DISTINCT `to` FROM enron_emailto
) AS common;

-- h02_sender_no_receiver | ok
-- Question: 哪些规范化发件地址发送过邮件、但从未作为规范化标准收件地址出现？列出地址和其发送的不同邮件数，先按发送数降序、再按地址升序排列。
WITH
senders AS (
    SELECT DISTINCT TRIM(`from`) AS addr
    FROM enron_emailinfo
    WHERE `from` IS NOT NULL AND TRIM(`from`) <> ''
),
recipients AS (
    SELECT DISTINCT TRIM(`to`) AS addr
    FROM enron_emailto
    WHERE `to` IS NOT NULL AND TRIM(`to`) <> ''
),
sender_only AS (
    SELECT s.addr
    FROM senders s
    LEFT JOIN recipients r ON s.addr = r.addr
    WHERE r.addr IS NULL
)
SELECT
    e.`from` AS normalized_sender_address,
    COUNT(DISTINCT e.id) AS sent_email_count
FROM enron_emailinfo e
INNER JOIN sender_only so ON TRIM(e.`from`) = so.addr
GROUP BY e.`from`
ORDER BY sent_email_count DESC, e.`from` ASC;

-- h03_most_active_email_thread | ok
-- Question: 哪些邮件主题引发的回复讨论最多？列出前3个。
SELECT `subject`, COUNT(*) AS reply_count
FROM enron_emailorig
WHERE `subject` IS NOT NULL AND TRIM(`subject`) <> ''
  AND TRIM(`subject`) NOT IN ('RE:', 'FW:', 'Fwd:', 'RE: ', 'FW: ', 'Fwd: ')
GROUP BY `subject`
ORDER BY reply_count DESC
LIMIT 10;

-- h04_top_senders_per_owner | ok
-- Question: 对每个非空归档员工目录people，统计其保存邮件中各规范化发件地址发送的不同邮件数；在每个people内部按邮件数降序、发件地址升序编号，列出每个people的前3个发件地址、邮件数和名次，最后按people升序、名次升序排列。
WITH sender_counts AS (
    SELECT
        e.people,
        i.`from` AS sender_address,
        COUNT(DISTINCT e.id) AS email_count
    FROM enron_email e
    JOIN enron_emailinfo i ON e.id = i.id
    WHERE TRIM(e.people) != ''
    GROUP BY e.people, i.`from`
),
ranked_senders AS (
    SELECT
        people,
        sender_address,
        email_count,
        ROW_NUMBER() OVER (
            PARTITION BY people
            ORDER BY email_count DESC, sender_address ASC
        ) AS rnk
    FROM sender_counts
)
SELECT
    people,
    sender_address,
    email_count,
    rnk
FROM ranked_senders
WHERE rnk <= 3
ORDER BY people ASC, rnk ASC;

-- h05_busiest_day_senders | ok
-- Question: 邮件往来最忙的是哪一天？那天发邮件最多的5个邮箱是谁？
SELECT LOWER(TRIM(`from`)) AS sender_email, COUNT(DISTINCT id) AS sent_count
FROM enron_emailinfo
WHERE `Date` IS NOT NULL AND TRIM(`Date`) <> ''
  AND SUBSTRING_INDEX(SUBSTRING_INDEX(`Date`, ',', -1), ' ', 4) = ' 12 Dec 2000'
  AND `from` IS NOT NULL AND TRIM(`from`) <> ''
GROUP BY LOWER(TRIM(`from`))
ORDER BY sent_count DESC
LIMIT 5;

-- h06_internal_vs_external | generation_error
-- Question: 将每封邮件按规范化发件地址分类：地址以“@enron.com”结尾为internal，其他非空有效地址为external；忽略空发件地址。分别统计两类的不同邮件数及其占有效发件邮件总数的百分比，百分比保留2位小数，按类别升序排列。
-- MOI error: compute_result_table: compute result table: compute_result_table: rename_columns source "total" not in columns [category email_count]
WITH classified AS (
  SELECT
    CASE
      WHEN TRIM(`from`) LIKE '%@enron.com' THEN 'internal'
      ELSE 'external'
    END AS category,
    id
  FROM enron_emailinfo
  WHERE TRIM(`from`) IS NOT NULL AND TRIM(`from`) <> ''
),
stats AS (
  SELECT
    category,
    COUNT(DISTINCT id) AS email_count
  FROM classified
  GROUP BY category
)
SELECT
  category,
  email_count,
  ROUND(email_count * 100.0 / SUM(email_count) OVER (), 2) AS percentage
FROM stats
ORDER BY category ASC;

-- h07_sender_receiver_overlap_people | ok
-- Question: 仅考虑campbell-l、allen-p和badeer-r三个归档员工目录。对每个people，将其保存邮件中的规范化发件地址与规范化标准收件地址合并为通信地址集合；找出至少出现在其中两个不同people集合中的地址，列出地址和涉及的不同people数量，按people数量降序、地址升序排列。
WITH campbell_sender AS (
    SELECT DISTINCT e.people, i.`from` AS address
    FROM enron_email e
    JOIN enron_emailinfo i ON e.id = i.id
    WHERE e.people = 'campbell-l' AND i.`from` IS NOT NULL AND TRIM(i.`from`) <> ''
),
allen_sender AS (
    SELECT DISTINCT e.people, i.`from` AS address
    FROM enron_email e
    JOIN enron_emailinfo i ON e.id = i.id
    WHERE e.people = 'allen-p' AND i.`from` IS NOT NULL AND TRIM(i.`from`) <> ''
),
badeer_sender AS (
    SELECT DISTINCT e.people, i.`from` AS address
    FROM enron_email e
    JOIN enron_emailinfo i ON e.id = i.id
    WHERE e.people = 'badeer-r' AND i.`from` IS NOT NULL AND TRIM(i.`from`) <> ''
),
campbell_recipient AS (
    SELECT DISTINCT e.people, t.`to` AS address
    FROM enron_email e
    JOIN enron_emailto t ON e.id = t.id
    WHERE e.people = 'campbell-l' AND t.`to` IS NOT NULL AND TRIM(t.`to`) <> ''
),
allen_recipient AS (
    SELECT DISTINCT e.people, t.`to` AS address
    FROM enron_email e
    JOIN enron_emailto t ON e.id = t.id
    WHERE e.people = 'allen-p' AND t.`to` IS NOT NULL AND TRIM(t.`to`) <> ''
),
badeer_recipient AS (
    SELECT DISTINCT e.people, t.`to` AS address
    FROM enron_email e
    JOIN enron_emailto t ON e.id = t.id
    WHERE e.people = 'badeer-r' AND t.`to` IS NOT NULL AND TRIM(t.`to`) <> ''
),
campbell_addresses AS (
    SELECT address FROM campbell_sender
    UNION
    SELECT address FROM campbell_recipient
),
allen_addresses AS (
    SELECT address FROM allen_sender
    UNION
    SELECT address FROM allen_recipient
),
badeer_addresses AS (
    SELECT address FROM badeer_sender
    UNION
    SELECT address FROM badeer_recipient
),
all_with_people AS (
    SELECT address, 'campbell-l' AS people FROM campbell_addresses
    UNION
    SELECT address, 'allen-p' AS people FROM allen_addresses
    UNION
    SELECT address, 'badeer-r' AS people FROM badeer_addresses
)
SELECT address, COUNT(DISTINCT people) AS people_count
FROM all_with_people
GROUP BY address
HAVING people_count >= 2
ORDER BY people_count DESC, address ASC;

-- h08_campbell_allen_shared_recipients | generation_error
-- Question: Larry Campbell和Phillip Allen都给哪些邮箱发过邮件？分别发了多少封？
-- MOI error: query_sql: query sql: query_sql count: catalog knowledge sql executor: query failed: Error 20301 (HY000): invalid input: ambiguous column reference to 'to'
SELECT COUNT(DISTINCT et.`to`) AS unique_recipients
FROM enron_emailinfo ei
JOIN enron_emailto et ON ei.id = et.id
WHERE ei.`from` = 'phillip.allen@enron.com';

-- h09_email_chain_depth | ok
-- Question: 对enron_emailorig中存在记录的每封当前邮件，按id统计历史邮件头数量。返回这些邮件的平均历史邮件头数量、最大历史邮件头数量，以及历史邮件头数量不少于3的当前邮件数；平均值保留4位小数。
WITH header_counts AS (
    SELECT id, COUNT(*) AS header_count
    FROM enron_emailorig
    GROUP BY id
)
SELECT
    ROUND(AVG(header_count), 4) AS avg_headers,
    MAX(header_count) AS max_headers,
    SUM(CASE WHEN header_count >= 3 THEN 1 ELSE 0 END) AS count_at_least_3
FROM header_counts;

-- h10_top_folder_per_person | ok
-- Question: 每个人邮件最多的文件夹是哪个？并列的也都列出来。
WITH email_counts AS (
    SELECT people, mailbox, COUNT(*) AS cnt
    FROM enron_email
    GROUP BY people, mailbox
),
ranked AS (
    SELECT people, mailbox, cnt,
           DENSE_RANK() OVER (PARTITION BY people ORDER BY cnt DESC) AS rnk
    FROM email_counts
)
SELECT people, mailbox, cnt
FROM ranked
WHERE rnk = 1
ORDER BY people, mailbox;
